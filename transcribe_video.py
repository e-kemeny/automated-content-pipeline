"""Populate only the shared transcript stage; both future output modes reuse it."""
import argparse
from copy import deepcopy
import math
import os
from pathlib import Path
import tempfile
import subprocess

from shared_analysis import create_analysis, load_analysis, save_analysis, signal, validate_analysis
from transcription import (require_media, media_sha256, probe_media,
                           transcribe_media, validate_segments)


def verify_source(source, path, fingerprint):
    """Use content identity when supplied, otherwise require the same resolved path."""
    if "sha256" in source:
        if source["sha256"] != fingerprint:
            raise ValueError("Source-video identity mismatch (SHA-256)")
    elif Path(source["path"]).resolve() != path:
        raise ValueError("Source-video identity mismatch (path; no persisted hash)")


def update_transcript(path, analysis_path, *, force=False, create=False,
                      device="cpu", compute_type="int8", word_timestamps=False):
    """Return (analysis, reused). Failure leaves the previous document untouched."""
    path, analysis_path = require_media(path), Path(analysis_path)
    if analysis_path.exists():
        analysis = load_analysis(analysis_path)  # Reject incompatible schema before ASR.
        fingerprint = media_sha256(path)
        verify_source(analysis["source_video"], path, fingerprint)
    elif create:
        analysis = create_analysis(probe_media(path))
        fingerprint = analysis["source_video"]["sha256"]
    else:
        raise FileNotFoundError("Analysis document is missing; use --create to create it")
    cached = analysis["transcript"]["status"] == "analyzed" and not force
    if not cached or "sha256" not in analysis["source_video"]:
        actual = probe_media(path)
        if not math.isclose(actual["duration_seconds"], analysis["source_video"]["duration_seconds"], rel_tol=0, abs_tol=1e-6):
            raise ValueError("Source duration differs from shared analysis")
    if cached:
        return analysis, True  # Includes a successful empty transcript; no backend/extraction.
    result = transcribe_media(path, device=device, compute_type=compute_type,
        word_timestamps=word_timestamps, cache_dir=analysis_path.parent/"transcription_models",
        work_dir=analysis_path.parent/"transcription_tmp")
    provenance = result["provenance"]
    if provenance["source_sha256"] != fingerprint or media_sha256(path) != fingerprint:
        raise ValueError("Source changed during transcription")
    duration = analysis["source_video"]["duration_seconds"]
    if not math.isclose(provenance["source_duration_seconds"], duration, rel_tol=0, abs_tol=1e-6):
        raise ValueError("Source duration differs from shared analysis")
    updated = deepcopy(analysis)
    updated["transcript"] = signal(validate_segments(result["segments"], duration), provenance)
    validate_analysis(updated)
    analysis_path.parent.mkdir(parents=True, exist_ok=True)
    # Validate/write a unique sibling, then atomically replace the document.
    with tempfile.NamedTemporaryFile(dir=analysis_path.parent, prefix=".asr_", suffix=".json",
                                     delete=False) as handle:
        temporary = Path(handle.name)
    try:
        save_analysis(updated, temporary)
        os.replace(temporary, analysis_path)
    finally:
        temporary.unlink(missing_ok=True)
    return updated, False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("media", type=Path)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--create", action="store_true", help="Create a missing analysis using actual media metadata")
    parser.add_argument("--force", action="store_true", help="Refresh only transcript even if already analyzed")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--word-timestamps", action="store_true")
    args = parser.parse_args(argv)
    try:
        result, reused = update_transcript(args.media, args.analysis, force=args.force, create=args.create,
            device=args.device, compute_type=args.compute_type, word_timestamps=args.word_timestamps)
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"Transcription failed: {exc}\n")
    transcript = result["transcript"]
    print(f"{'Reused' if reused else 'Saved'} {len(transcript['data'])} transcript segments: {args.analysis}")
    if not reused:
        print(f"Model {transcript['provenance']['model']}; "
              f"processing {transcript['provenance']['processing_seconds']:.2f}s")
    for row in transcript["data"][:5]:
        print(f"[{row['start']:.3f}, {row['end']:.3f}] {row['text']}")


if __name__ == "__main__":
    main()

