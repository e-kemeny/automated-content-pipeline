"""Optional ResNet-18 frame experiment; never used by the production pipeline."""
import argparse
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from urllib.parse import urlparse

from media_probe import probe_format_streams
from source_identity import file_identity

ROOT = Path(__file__).resolve().parent
EXPERIMENT = "vision-inference-v1"


def sample_timestamps(duration, count):
    if type(count) is not int or not 1 <= count <= 100:
        raise ValueError("Frame count must be an integer from 1 to 100")
    if isinstance(duration, bool) or not math.isfinite(duration) or duration <= 0:
        raise ValueError("Video duration must be positive and finite")
    return [duration * (i / (count + 1)) for i in range(1, count + 1)]


def inspect_video(video):
    if video.is_symlink() or not video.is_file():
        raise ValueError(f"Missing video or unsupported symlink: {video}")
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise ValueError(f"{tool} unavailable on PATH")
    data = probe_format_streams(video)
    try:
        duration = float(data["format"]["duration"])
        stream = next(s for s in data["streams"] if s.get("codec_type") == "video"
                      and not s.get("disposition", {}).get("attached_pic", 0))
        width, height, index = stream["width"], stream["height"], stream["index"]
        if any(type(x) is not int or x <= 0 for x in (width, height)):
            raise ValueError("Invalid video dimensions")
        if type(index) is not int or index < 0:
            raise ValueError("Invalid video stream index")
        sample_timestamps(duration, 1)
    except (KeyError, TypeError, StopIteration, ValueError) as exc:
        raise ValueError("Unsupported video: positive duration and a video stream are required") from exc
    return dict(duration_seconds=duration, width=width, height=height, stream_index=index)


def check_output(output, overwrite):
    # Protect repository sources and existing unrelated artifacts even with --overwrite.
    if output.is_symlink():
        raise ValueError("Output must not be a symlink")
    resolved = output.resolve()
    if resolved.is_relative_to(ROOT) and not resolved.is_relative_to(ROOT / "output"):
        raise ValueError("Outputs inside the repository must be under ignored output/")
    if output.suffix.lower() != ".json":
        raise ValueError("Output must have a .json suffix")
    if output.exists():
        if not overwrite:
            raise FileExistsError("Output exists; use --overwrite for this experiment's JSON only")
        prior = json.loads(output.read_text(encoding="utf-8"))
        if not isinstance(prior, dict) or prior.get("experiment") != EXPERIMENT or prior.get("schema_version") != 1:
            raise ValueError("Refusing to overwrite an unrelated artifact")


def save_result(output, result, overwrite=False):
    payload = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    check_output(output, overwrite)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=output.parent, prefix=".vision-", suffix=".tmp",
                                         delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        check_output(output, overwrite)
        if overwrite:
            os.replace(temporary, output)
        else:
            # Atomic no-clobber publication: a racing destination is never replaced.
            os.link(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def select_device(torch, device):
    if not re.fullmatch(r"cuda:[0-9]+", device):
        raise ValueError("Device must be cuda:<nonnegative index>; no CPU fallback")
    if torch.version.cuda is None or not torch.cuda.is_available():
        raise ValueError("CUDA unavailable; use a compatible optional GPU environment")
    index = int(device.split(":")[1])
    if index >= torch.cuda.device_count():
        raise ValueError(f"Unavailable CUDA device: {device}")
    return f"cuda:{index}"


def load_model(torch, vision, allow_download):
    weights = vision.models.ResNet18_Weights.IMAGENET1K_V1
    filename = Path(urlparse(weights.url).path).name
    cache = Path(torch.hub.get_dir()) / "checkpoints" / filename
    if cache.is_file():
        # Never call a network-capable loader on the cache-only path.
        with cache.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
            expected = re.search(r"-([0-9a-f]+)\.", filename)
            if expected is None or not digest.startswith(expected.group(1)):
                raise ValueError("Cached weights failed official filename SHA-256 prefix check")
            handle.seek(0)
            state = torch.load(handle, map_location="cpu", weights_only=True)
    elif allow_download:
        state = torch.hub.load_state_dict_from_url(
            weights.url, map_location="cpu", progress=False, check_hash=True, weights_only=True)
    else:
        raise FileNotFoundError(f"Cached weights missing: {cache}; use --allow-model-download to opt in")
    model = vision.models.resnet18(weights=None)
    model.load_state_dict(state)
    return model, weights


def extract_frame(video, timestamp, stream_index, target):
    try:
        subprocess.run(
            ["ffmpeg", "-v", "error", "-nostdin", "-n", "-ss", str(timestamp),
             "-i", str(video), "-map", f"0:{stream_index}", "-frames:v", "1",
             "-pix_fmt", "rgb24", str(target)],
            check=True, capture_output=True, text=True, timeout=60)
        if not target.is_file() or target.stat().st_size == 0:
            raise ValueError("FFmpeg produced no frame")
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise RuntimeError(f"Frame extraction failed at {timestamp:.6f}s: {exc}") from exc


def top_predictions(probabilities, categories):
    scores, indices = probabilities.topk(3)
    scores, indices = scores.cpu().tolist(), indices.cpu().tolist()
    if len(scores) != 3 or len(indices) != 3:
        raise ValueError("Expected three predictions")
    rows = []
    for score, index in zip(scores, indices):
        if not math.isfinite(score) or not 0 <= score <= 1 or not 0 <= index < len(categories):
            raise ValueError("Invalid model prediction")
        rows.append(dict(category=categories[index], confidence=float(score)))
    return rows


def run_experiment(video, output, device="cuda:0", frames=5,
                   allow_model_download=False, overwrite=False):
    started = time.perf_counter()
    video, output = Path(video).absolute(), Path(output).absolute()
    check_output(output, overwrite)
    if video.resolve() == output.resolve():
        raise ValueError("Output must not replace source video")
    sample_timestamps(1, frames)
    media = inspect_video(video)
    identity = file_identity(video)
    torch = importlib.import_module("torch")
    vision = importlib.import_module("torchvision")
    image_module = importlib.import_module("PIL.Image")
    device = select_device(torch, device)
    torch.cuda.synchronize(device)
    torch.cuda.reset_peak_memory_stats(device)
    model, weights = load_model(torch, vision, allow_model_download)
    model = model.to(device).eval()
    transform = weights.transforms()
    rows = []
    with tempfile.TemporaryDirectory(prefix="vision-inference-") as directory, torch.inference_mode():
        for i, timestamp in enumerate(sample_timestamps(media["duration_seconds"], frames)):
            path = Path(directory) / f"frame_{i}.png"
            extract_frame(video, timestamp, media["stream_index"], path)
            with image_module.open(path) as image:
                tensor = transform(image.convert("RGB")).unsqueeze(0).to(device)
            torch.cuda.synchronize(device)
            before = time.perf_counter()
            probabilities = model(tensor)[0].softmax(dim=0)
            torch.cuda.synchronize(device)
            latency = (time.perf_counter() - before) * 1000
            predictions = top_predictions(probabilities, weights.meta["categories"])
            rows.append(dict(timestamp_seconds=timestamp, top3=predictions,
                             inference_latency_ms=latency))
            path.unlink(missing_ok=True)
            del tensor, probabilities
    if file_identity(video) != identity:
        raise ValueError("Source video changed during experiment")
    result = dict(
        schema_version=1, experiment=EXPERIMENT,
        video=dict(path=str(video), sha256=identity[0], size_bytes=identity[1], **media),
        sampling=dict(method="duration*i/(count+1), i=1..count", frame_count=frames,
                      timestamps_are="requested seek times, not measured source-frame PTS"),
        model=dict(name="resnet18", weights="ResNet18_Weights.IMAGENET1K_V1",
                   weights_url=weights.url),
        runtime=dict(pytorch_version=torch.__version__, torchvision_version=vision.__version__,
                     cuda_build_version=torch.version.cuda, device=device,
                     gpu_name=torch.cuda.get_device_name(device),
                     total_elapsed_seconds=time.perf_counter()-started,
                     peak_allocated_gpu_memory_mib=torch.cuda.max_memory_allocated(device)/1024**2),
        frames=rows)
    save_result(output, result, overwrite)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--frames", type=int, default=5)
    parser.add_argument("--output", type=Path, default=Path("output/vision_inference_v1.json"))
    parser.add_argument("--allow-model-download", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run_experiment(**vars(args))
    except Exception as exc:
        print(f"FAIL: vision experiment ({type(exc).__name__}): {exc}")
        return 1
    print(f"PASS: experimental ImageNet inference for {len(result['frames'])} frames -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
