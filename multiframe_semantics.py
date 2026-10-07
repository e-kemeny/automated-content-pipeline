"""Frozen multiframe V1. No human labels, retention, or candidate scoring."""
import argparse
from copy import deepcopy
import hashlib
import io
import json
import math
from pathlib import Path
import platform
import re
import subprocess
import time

from semantic_events import create_event, save_events
from semantic_clip import write_json

MODEL_ID = "HuggingFaceTB/SmolVLM2-256M-Video-Instruct"
MODEL_REVISION = "067788b187b95ebe7b2e040b3e4299e342e5b8fd"
LABELS = ("combat", "kill", "death", "objective", "transition", "victory", "neutral")
WINDOW_SECONDS = 5.0
MAX_NEW_TOKENS = 48
PROMPT = (
    "These three Minecraft gameplay frames are in chronological order from one short interval. "
    "Examine them together. Choose the single best description of the interval: "
    "combat (players fighting), kill (a player defeated), death (the viewpoint player dies or respawns), "
    "objective (an important gameplay objective is acted on), transition (waiting or changing scenes), "
    "victory (a win), or neutral (ordinary gameplay with no major event). "
    "On the first line output only one of these labels: combat, kill, death, objective, transition, victory, neutral. "
    "On the second line give one short sentence of visible evidence. Do not give a confidence score."
)


def build_windows(duration):
    if isinstance(duration, bool) or not isinstance(duration, (int,float)) or not math.isfinite(duration) or duration < 0:
        raise ValueError("Duration must be finite and nonnegative")
    windows = []
    for i in range(math.ceil(duration / WINDOW_SECONDS)):
        start, end = i * WINDOW_SECONDS, min(duration, (i+1)*WINDOW_SECONDS)
        windows.append(dict(start=start, end=end,
            frame_timestamps=[start, (start+end)/2, end-min(0.1,(end-start)/10)]))
    return windows


def parse_response(response):
    """First nonempty line must be a label, optionally prefixed 'label:'.

    Case/outer whitespace are ignored; punctuation, explanations on the label
    line, unknown labels, and multiple labels are rejected. Never infer labels
    from the reason. No retries. Preserve unrecognized text in the artifact.
    """
    if not isinstance(response, str):
        raise ValueError("Response must be text")
    lines = [line.strip() for line in response.splitlines() if line.strip()]
    if not lines:
        return dict(label=None, evidence="", parse_status="invalid")
    match = re.fullmatch(r"(?:label:\s*)?(" + "|".join(LABELS) + ")", lines[0].lower())
    return dict(label=match.group(1) if match else None,
                evidence="\n".join(lines[1:]), parse_status="valid" if match else "invalid")


def predictions_to_events(predictions):
    """Merge adjacent identical valid non-neutral windows; invalid/neutral break runs.

    confidence=0 is an unavailable-value compatibility sentinel, NOT a model score.
    Model confidence is null in metadata and must not be interpreted or ranked.
    """
    runs = []
    last_end = 0
    active = None
    for prediction in predictions:
        start, end = prediction["start"], prediction["end"]
        if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in (start,end)) or not 0 <= start < end or start < last_end:
            raise ValueError("Prediction windows must be ordered, positive, and non-overlapping")
        last_end = end
        label = prediction["label"]
        if label is not None and label not in LABELS:
            raise ValueError("Unknown prediction label")
        if label in (None,"neutral"):
            active = None
            continue
        if active is None or active[-1]["label"] != label or active[-1]["end"] != start:
            active = []
            runs.append(active)
        active.append(deepcopy(prediction))
    return [create_event(run[0]["start"],run[-1]["end"],run[0]["label"],0.0,source=MODEL_ID,
        metadata=dict(model_id=MODEL_ID,model_revision=MODEL_REVISION,confidence_available=False,
                      model_confidence=None,confidence_semantics="0.0 compatibility sentinel; confidence unavailable",
                      predictions=run)) for run in runs]


def joint_response(model, processor, images, window):
    """Exactly three images in ONE chat and ONE generate call."""
    if len(images) != 3:
        raise ValueError("Exactly three frames required")
    content = [{"type":"text","text":PROMPT}]
    for timestamp in window["frame_timestamps"]:
        content += [{"type":"text","text":f"Frame at {timestamp:.6f} seconds:"}, {"type":"image"}]
    messages = [{"role":"user","content":content}]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    processor.image_processor.do_image_splitting = False
    processor.image_processor.size = {"longest_edge": 512}
    inputs = processor(text=text, images=images, return_tensors="pt").to(model.device)
    if inputs["pixel_values"].shape[1] != 3:
        raise ValueError("Expected exactly three processed images")
    output = model.generate(**inputs,max_new_tokens=MAX_NEW_TOKENS,do_sample=False,num_beams=1)
    return processor.batch_decode(output[:,inputs["input_ids"].shape[1]:],skip_special_tokens=True)[0]


def infer(video, output):
    output = Path(output)
    artifact_path = output/"multiframe_semantic_timeline.json"
    if artifact_path.exists() or (output/"multiframe_semantic_windows.jsonl").exists():
        raise FileExistsError("First run already exists; do not overwrite or rerun")
    import torch
    import transformers
    from PIL import Image
    from transformers import AutoProcessor, AutoModelForImageTextToText
    output.mkdir(parents=True,exist_ok=True)
    total_start = time.perf_counter()
    metadata = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","json",str(video)],
                              capture_output=True,text=True,check=True)
    duration = float(json.loads(metadata.stdout)["format"]["duration"])
    windows = build_windows(duration)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    torch.set_num_threads(4)
    setup_start = time.perf_counter()
    cache = str(output/"multiframe_model_cache")
    processor = AutoProcessor.from_pretrained(MODEL_ID,revision=MODEL_REVISION,cache_dir=cache,use_fast=False)
    model = AutoModelForImageTextToText.from_pretrained(MODEL_ID,revision=MODEL_REVISION,cache_dir=cache,
        torch_dtype=torch.float32,attn_implementation="eager").to(device).eval()
    setup_seconds = time.perf_counter()-setup_start
    print(f"Model ready on {device}; {len(windows)} windows; setup {setup_seconds:.2f}s",flush=True)
    predictions = []
    frame_seconds = inference_seconds = 0
    with (output/"multiframe_semantic_windows.jsonl").open("x",encoding="utf-8") as log:
        for index, window in enumerate(windows):
            start = time.perf_counter()
            images = []
            for timestamp in window["frame_timestamps"]:
                frame = subprocess.run(["ffmpeg","-v","error","-ss",str(timestamp),"-i",str(video),
                    "-frames:v","1","-f","image2pipe","-vcodec","png","-"],
                    check=True,capture_output=True)
                with Image.open(io.BytesIO(frame.stdout)) as image:
                    image = image.convert("RGB")
                    image.thumbnail((512,512))
                    images.append(image.copy())
            frame_seconds += time.perf_counter()-start
            start = time.perf_counter()
            with torch.inference_mode():
                response = joint_response(model,processor,images,window)
            elapsed = time.perf_counter()-start
            inference_seconds += elapsed
            prediction = dict(window, **parse_response(response), response=response, model_id=MODEL_ID,
                              model_score=None,inference_seconds=elapsed)
            predictions.append(prediction)
            log.write(json.dumps(prediction,sort_keys=True,allow_nan=False)+"\n")
            log.flush()
            print(f"Window {index+1}/{len(windows)} complete ({elapsed:.2f}s)",flush=True)
    with Path(video).open("rb") as source:
        video_hash = hashlib.file_digest(source,"sha256").hexdigest()
    artifact = dict(model_id=MODEL_ID,model_revision=MODEL_REVISION,prompt=PROMPT,labels=LABELS,
        duration=duration,video_sha256=video_hash,device=device,hardware=platform.processor() if device=="cpu" else torch.cuda.get_device_name(0),
        torch_version=torch.__version__,transformers_version=transformers.__version__,
        setup_seconds=setup_seconds,frame_seconds=frame_seconds,inference_seconds=inference_seconds,
        total_seconds=time.perf_counter()-total_start,windows_per_second=len(windows)/inference_seconds,
        predictions=predictions)
    write_json(artifact_path,artifact)
    save_events(predictions_to_events(predictions),output/"multiframe_semantic_events.json")
    print(f"Saved {len(predictions)} window responses",flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video",type=Path,default=Path("videos/my_recording.mp4"))
    parser.add_argument("--output",type=Path,default=Path("output"))
    args = parser.parse_args()
    infer(args.video,args.output)
