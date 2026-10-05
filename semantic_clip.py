"""Frozen CLIP V1: relative image/text evidence, never calibrated confidence."""
import argparse
from copy import deepcopy
import hashlib
import json
import math
import platform
from pathlib import Path
import subprocess
import time

from semantic_events import create_event, save_events

MODEL_ID = "openai/clip-vit-base-patch32"
MODEL_REVISION = "3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268"
SAMPLE_INTERVAL = 1.0
PROMPTS = {
    "combat": "a Minecraft player fighting another player",
    "kill": "a Minecraft player defeating another player",
    "death": "a Minecraft death or respawn screen",
    "objective": "a Minecraft player breaking an important objective",
    "transition": "a Minecraft game transition or waiting screen",
    "victory": "a Minecraft victory or win screen",
    "neutral": "ordinary Minecraft gameplay with no major event",
}


def sample_timestamps(duration):
    if not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
        raise ValueError("Duration must be positive and finite")
    return [float(i) for i in range(math.ceil(duration))]


def select_device(torch_module):
    return "cuda" if torch_module.cuda.is_available() else "cpu"


def classify_logits(timestamp, logits):
    """Keep scaled similarities and stable softmax over the frozen seven prompts."""
    if not isinstance(timestamp, (int, float)) or not math.isfinite(timestamp) or timestamp < 0:
        raise ValueError("Invalid timestamp")
    if len(logits) != len(PROMPTS) or any(
        isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in logits
    ):
        raise ValueError("Expected seven finite model logits")
    maximum = max(logits)
    weights = [math.exp(v - maximum) for v in logits]
    total = sum(weights)
    labels = list(PROMPTS)
    winner = max(range(len(labels)), key=lambda i: logits[i])  # Ties use prompt order.
    scores = {label: dict(similarity=value, zero_shot_score=weight / total)
              for label, value, weight in zip(labels, logits, weights)}
    return dict(timestamp=timestamp, label=labels[winner],
                winning_score=scores[labels[winner]]["zero_shot_score"],
                scores=scores, model_id=MODEL_ID)


def validate_timeline(rows, duration):
    expected = sample_timestamps(duration)
    if not rows:
        return []
    if [r["timestamp"] for r in rows] != expected:
        raise ValueError("Timeline must contain the complete 1 FPS grid, in order")
    for row in rows:
        if set(row["scores"]) != set(PROMPTS) or row["model_id"] != MODEL_ID:
            raise ValueError("Wrong model or prompt labels")
        reconstructed = classify_logits(row["timestamp"], [row["scores"][k]["similarity"] for k in PROMPTS])
        if row != reconstructed:
            raise ValueError("Inconsistent classification evidence")
    return deepcopy(rows)


def timeline_runs(rows, duration):
    """Each sample represents [t,min(t+1,duration)); merge adjacent same-label bins."""
    rows = validate_timeline(rows, duration)
    runs = []
    for row in rows:
        if not runs or runs[-1]["label"] != row["label"]:
            runs.append(dict(start=row["timestamp"], end=0, label=row["label"], samples=[]))
        runs[-1]["end"] = min(duration, row["timestamp"] + SAMPLE_INTERVAL)
        runs[-1]["samples"].append(row)
    return runs


def timeline_to_events(rows, duration):
    events = []
    for run in timeline_runs(rows, duration):
        if run["label"] == "neutral":
            continue
        evidence = run["samples"]
        relative = sum(r["winning_score"] for r in evidence) / len(evidence)
        events.append(create_event(run["start"], run["end"], run["label"], relative, source=MODEL_ID,
            metadata=dict(confidence_semantics="mean winning zero_shot_score; uncalibrated relative evidence",
                          sample_interval_seconds=SAMPLE_INTERVAL, samples=evidence)))
    return events


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def infer_video(video, output):
    """Run the fixed experiment once; lazy imports keep ordinary tests model-free."""
    output = Path(output)
    timeline_path, events_path = output/"clip_semantic_timeline.json", output/"clip_semantic_events.json"
    if timeline_path.exists() or events_path.exists():
        raise FileExistsError("Preserve the first result: use a separate output directory for another experiment")
    import torch
    import transformers
    from PIL import Image

    from transformers import CLIPModel, CLIPProcessor

    output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "json", str(video)], check=True, capture_output=True, text=True)
    duration = float(json.loads(probe.stdout)["format"]["duration"])
    timestamps = sample_timestamps(duration)
    frames = output/"clip_frames"
    frames.mkdir(exist_ok=True)
    if list(frames.glob("*.png")):
        raise FileExistsError("Frame directory must be empty to avoid stale frames")
    # Fixed CFR output grid; FFmpeg selects source frames independently of labels.
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf",
                    "fps=1:start_time=0:round=up", "-frames:v", str(len(timestamps)),
                    str(frames/"%06d.png")], check=True)
    paths = sorted(frames.glob("*.png"))
    if len(paths) != len(timestamps):
        raise ValueError("FFmpeg frame count does not match the sampling grid")
    revision = MODEL_REVISION
    cache = str(output/"clip_model_cache")
    model = CLIPModel.from_pretrained(MODEL_ID, revision=revision, cache_dir=cache, use_safetensors=False)
    processor = CLIPProcessor.from_pretrained(MODEL_ID, revision=revision, cache_dir=cache, use_fast=False)
    device = select_device(torch)
    model = model.to(device).eval()
    if device == "cpu":
        torch.set_num_threads(4)
    print(f"Model ready: {MODEL_ID} revision={revision}, device={device}", flush=True)
    rows = []
    with torch.inference_mode():
        for timestamp, path in zip(timestamps, paths):
            with Image.open(path) as image:
                inputs = processor(text=list(PROMPTS.values()), images=image.convert("RGB"),
                                   return_tensors="pt", padding=True).to(device)
                logits = model(**inputs).logits_per_image[0].cpu().tolist()
            rows.append(classify_logits(timestamp, logits))
            if len(rows) % 20 == 0:
                print(f"Classified {len(rows)}/{len(paths)} frames", flush=True)
    events = timeline_to_events(rows, duration)
    with Path(video).open("rb") as source:
        video_hash = hashlib.file_digest(source, "sha256").hexdigest()
    artifact = dict(model_id=MODEL_ID, model_revision=revision, prompts=PROMPTS,
                    sample_interval_seconds=SAMPLE_INTERVAL, sampling_filter="fps=1:start_time=0:round=up",
                    duration=duration, video_sha256=video_hash, device=device,
                    hardware=torch.cuda.get_device_name(0) if device == "cuda" else platform.processor(),
                    torch_version=torch.__version__, transformers_version=transformers.__version__,
                    runtime_seconds=time.perf_counter()-started, rows=rows)
    write_json(timeline_path, artifact)
    save_events(events, events_path)
    print(f"Saved {len(rows)} samples and {len(events)} non-neutral events", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, default=Path("videos/my_recording.mp4"))
    parser.add_argument("--output", type=Path, default=Path("output"))
    args = parser.parse_args()
    infer_video(args.video, args.output)
