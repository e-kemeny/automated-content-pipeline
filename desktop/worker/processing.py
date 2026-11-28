"""Desktop-only adapter over the frozen analysis/export functions. No model inference."""
import contextlib
import importlib
import json
import os
from pathlib import Path
import shutil
import sys

STAGES = ("Validating source", "Collecting observations and generating shared analysis",
          "Exporting Shorts", "Exporting long-form", "Finalizing outputs")
EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}


def regular_path(value, directory=False):
    if not isinstance(value, str) or not value or not Path(value).is_absolute():
        raise ValueError("Expected an absolute native-selected path")
    path = Path(value)
    if any(p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction()) for p in (path, *path.parents)):
        raise ValueError("Symlink/junction paths are not supported")
    if not (path.is_dir() if directory else path.is_file()):
        raise ValueError("Missing source or output folder")
    return path


def validate_config(config):
    if not isinstance(config, dict) or set(config) != {"video", "workspace", "mode", "size_bytes", "modified_ms"}:
        raise ValueError("Invalid processing configuration")
    if config["mode"] not in ("shorts", "longform", "both"):
        raise ValueError("Unsupported export mode")
    video = regular_path(config["video"])
    if video.suffix.lower() not in EXTENSIONS:
        raise ValueError("Unsupported video extension")
    workspace = Path(config["workspace"])
    if not workspace.is_absolute() or workspace.exists() or workspace.is_symlink():
        raise ValueError("Job workspace must be a new absolute directory")
    regular_path(str(workspace.parent), directory=True)
    if video.is_relative_to(workspace):
        raise ValueError("Workspace conflicts with source")
    stat = video.stat()
    if any(type(config[k]) is not int for k in ("size_bytes", "modified_ms")) or (
        stat.st_size != config["size_bytes"] or stat.st_mtime_ns // 1_000_000 != config["modified_ms"]):
        raise ValueError("Source changed since native selection; select it again")
    return video, workspace


def dependencies():
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise RuntimeError(f"Missing {tool}; install it separately and restart the application")
    root = Path(os.environ.get("CONTENT_PIPELINE_ROOT", ""))
    if not root.is_absolute() or not all((root / name).is_file() for name in
            ("dev_test.py", "dense_to_shared.py", "pipeline.py", "export_shorts.py", "export_longform.py")):
        raise RuntimeError("Trusted development pipeline checkout is unavailable; rebuild from this checkout")
    # Set only by Rust, never supplied by the frontend or a source video.
    sys.path.insert(0, str(root))
    return importlib.import_module("dev_test"), importlib.import_module("export_shorts"), importlib.import_module("export_longform")


def artifact(path, kind, duration=None):
    from transcription import media_sha256
    return dict(path=str(path.resolve()), kind=kind, size_bytes=path.stat().st_size,
                sha256=media_sha256(path), duration_seconds=duration)


def run(config, report):
    """Report real stage boundaries; exporters remain the only encoding implementation."""
    report(STAGES[0])
    video, workspace = validate_config(config)
    dev, shorts, longs = dependencies()
    from transcription import probe_media
    source = probe_media(video)
    if "width" not in source:
        raise ValueError("Source must contain video and audio")
    # Fail before creating anything if source changed during the validation probe.
    validate_config(config)
    workspace.mkdir(exist_ok=False)
    (workspace / "desktop_job.json").write_text(json.dumps(
        dict(schema_version=1, purpose="owned desktop workspace; native terminal state determines completion", source=source, mode=config["mode"]), indent=2) + "\n", encoding="utf-8")
    # Killed jobs retain this ownership marker and private scratch files for inspection.
    # No deletion/repair of failed runs and no cache discovery outside this job.
    scratch = workspace / "scratch"
    scratch.mkdir()
    import tempfile
    tempfile.tempdir = str(scratch)
    paths = dev.paths_for(video, workspace)
    report(STAGES[1])
    dev.obtain_analysis(video, paths)
    outputs = []
    mode = config["mode"]
    if mode in ("shorts", "both"):
        report(STAGES[2])
        directory, manifest = shorts.export_shorts(video, paths["analysis"], output_root=paths["exports"])
        if any(row["status"] not in ("exported", "reused") for row in manifest["clips"]):
            raise RuntimeError("Shorts export failed; inspect the private job manifest")
        # Existing strict cache verification checks hashes, source and durations, with no writes.
        _, verified = shorts.export_shorts(video, paths["analysis"], output_root=paths["exports"], cache_only=True)
        for row in verified["clips"]:
            path = directory / row["output_filename"]
            outputs.append(artifact(path, "shorts", shorts.probe_clip(path)["duration_seconds"]))
    if mode in ("longform", "both"):
        report(STAGES[3])
        directory, manifest = longs.export_longform(video, paths["analysis"], output_root=paths["exports"])
        if manifest["assembly"]["status"] not in ("complete", "reused"):
            raise RuntimeError("Long-form export failed; inspect the private job manifest")
        _, verified = longs.export_longform(video, paths["analysis"], output_root=paths["exports"], cache_only=True)
        path = directory / "longform_v1.mp4"
        outputs.append(artifact(path, "longform", verified["assembly"]["actual_duration_seconds"]))
    report(STAGES[4])
    _, directory, plan = shorts.plan_export(video, paths["analysis"], output_root=paths["exports"])
    dev.publish_review(dev.review_text(plan, directory, mode != "longform"), paths["review"])
    outputs.append(artifact(paths["review"], "review"))
    outputs.append(artifact(paths["analysis"], "analysis"))
    if len(outputs) != {"shorts": 7, "longform": 3, "both": 8}[mode]:
        raise RuntimeError("Unexpected artifact count")
    return outputs


def dispatch(request, send):
    sequence = 0
    def event(kind, stage, artifacts=None, error=None):
        nonlocal sequence
        sequence += 1
        send(dict(protocol_version=1, request_id=request["request_id"], job_id=request["job_id"],
                  command="process_video", sequence=sequence, event=kind, stage=stage,
                  completed=0, total=0, error=error, artifacts=artifacts or []))
    def report(stage):
        event("started" if sequence == 0 else "progress", stage)
    try:
        # Python prints go to stderr. Native FFmpeg diagnostics already use stderr/capture_output.
        with contextlib.redirect_stdout(sys.stderr):
            outputs = run(request["config"], report)
        event("completed", "Finished", outputs)
        return 0
    except Exception as exc:
        print(f"Processing failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        event("failed", "Failed", error=dict(code="processing_failed", message=str(exc)[:2000] or type(exc).__name__))
        return 1
