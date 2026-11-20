"""Adapt a verified dense cache to exporter-compatible Shared Analysis V1."""
import argparse
from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import dense_observations as dense
from evaluation import select_highlights
from export_shorts import select_windows
from highlight_evaluation import publish
from multimodal_timeline import read_json
from shared_analysis import from_existing_signals, load_analysis
from source_identity import canonical, file_identity
from windows import build_candidate_windows

ROOT = Path(__file__).resolve().parent


def preflight(video, cache, output, semantic=None):
    """Reject aliases and existing destinations before any collection."""
    paths = [video, cache, output] + ([semantic] if semantic else [])
    for path in paths:
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError("Symlink paths are not supported")
    for i, path in enumerate(paths):
        for other in paths[i+1:]:
            if path.resolve() == other.resolve() or (
                    path.exists() and other.exists() and path.samefile(other)):
                raise ValueError("Source, cache, analysis and semantic paths must be distinct")
    if not video.is_file():
        raise ValueError("Missing source video")
    if semantic is not None and not semantic.is_file():
        raise ValueError("Missing semantic analysis")
    if output.exists():
        raise FileExistsError("Shared-analysis destination already exists; choose a new path")
    for destination in (cache, output):
        resolved = destination.resolve()
        if resolved.is_relative_to(ROOT) and not resolved.is_relative_to(ROOT / "output"):
            raise ValueError("Repository artifacts must be under output/")


def adapt(artifact, video, cache):
    """Preserve measurements; select the existing Audio-only fixed baseline."""
    dense.validate(artifact)
    full = artifact["full_observations"]
    scores = full["audio"]["score_rows"]
    selected = select_highlights(scores, "score", limit=5)
    if len(selected) != 5 or len({row["second"] for row in selected}) != 5:
        raise ValueError(f"Need five valid separated candidates; found {len(selected)}. No padding is permitted")
    source = dict(full["source_video"], path=str(Path(video).resolve()))
    windows = build_candidate_windows(selected, source["duration_seconds"])
    by_second = {row["second"]: row for row in scores}
    audio = [dict(row, **{k: deepcopy(v) for k, v in by_second.get(row["second"], {}).items()
                        if k != "second"}) for row in full["audio"]["amplitude_rows"]]
    common = dict(dense_cache=str(Path(cache).resolve()),
                  dense_content_sha256=artifact["content_sha256"],
                  source_identity=deepcopy(artifact["source_identity"]),
                  recipe=deepcopy(artifact["recipe"]),
                  coverage=deepcopy(artifact["coverage"]),
                  stream_metadata=deepcopy(artifact["stream_metadata"]))
    channels = artifact["timeline"]["sources"][0]["channels"]
    provenance = {}
    for name in ("audio_activity", "scene_changes", "motion"):
        provenance[name] = dict(common, original_provenance=deepcopy(channels[name]["provenance"]),
                                output_order="chronological")
    visual = artifact["visual"]
    provenance["semantic_frames"] = dict(visual["provenance"], dense_origin=deepcopy(common))
    provenance["candidate_windows"] = dict(common, detector="Audio-only", variant="fixed",
        representation="selected_windows", k=5, score_key="score", separation_seconds=15,
        seconds_before=10, seconds_after=5, selector="evaluation.select_highlights",
        tie_order="original dense audio score_rows order; stable descending score sort")
    result = from_existing_signals(source, audio_rows=audio,
        scene_rows=sorted(full["scene_changes"]["data"], key=lambda row: row["time"]),
        motion_rows=artifact["motion_rows"],
        visual_rows=visual["data"] if visual["status"] == "analyzed" else None,
        candidate_windows=windows, provenance=provenance)
    select_windows(result, 5)  # Existing shared Shorts/Long-form selection contract.
    return result


def generate(video, cache, output, semantic=None):
    video, cache, output = map(Path, (video, cache, output))
    semantic = Path(semantic) if semantic is not None else None
    preflight(video, cache, output, semantic)
    existing = load_analysis(semantic) if semantic else None
    artifact, status = dense.collect(video, cache, existing)
    result = adapt(artifact, video, cache)
    # Recheck after adaptation, immediately before exclusive atomic publication.
    before = dense.persistence.stat_identity(video)
    checksum, size = file_identity(video)
    identity = artifact["source_identity"]
    if (checksum, size) != (identity["digest"], identity["size_bytes"]):
        raise ValueError("Source identity changed before publication")
    if canonical(read_json(cache)) != canonical(artifact) or dense.recipe() != artifact["recipe"]:
        raise ValueError("Cache or producer provenance changed before publication")
    if semantic and canonical(load_analysis(semantic)) != canonical(existing):
        raise ValueError("Semantic analysis changed before publication")
    if dense.persistence.stat_identity(video) != before:
        raise ValueError("Source changed before publication")
    preflight(video, cache, output, semantic)
    publish(result, output, [video, cache] + ([semantic] if semantic else []))
    return result, status


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--dense-cache", type=Path, required=True)
    parser.add_argument("--analysis-output", type=Path, required=True)
    parser.add_argument("--semantic-analysis", type=Path,
                        help="Existing Shared Analysis containing source-bound CLIP frame evidence")
    args = parser.parse_args(argv)
    try:
        result, status = generate(args.video, args.dense_cache, args.analysis_output, args.semantic_analysis)
        anchors = [row["second"] for row in result["candidate_windows"]["data"]]
        print(f"PASS: dense cache {status}; five preselected Audio-only anchors: {anchors}")
        print(f"Shared analysis: {args.analysis_output}")
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"FAIL: dense-to-shared: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
