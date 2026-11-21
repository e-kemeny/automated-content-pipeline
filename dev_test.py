"""One-command developer analysis/export workflow; frozen Audio-only baseline."""
import argparse
import csv
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import dense_observations as dense
import dense_to_shared as integration
import pipeline
from export_shorts import plan_export
from shared_analysis import load_analysis
from source_identity import canonical, file_identity
from multimodal_timeline import read_json

ROOT = Path(__file__).resolve().parent


def paths_for(video, output_root):
    video, root = Path(video), Path(output_root)
    run = root / video.stem / "dev_test_v1"
    for path in (video, run):
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError("Symlink paths are not supported")
    if not video.is_file():
        raise ValueError("Missing source video")
    if run.resolve().is_relative_to(ROOT) and not run.resolve().is_relative_to(ROOT / "output"):
        raise ValueError("Repository test outputs must be under ignored output/")
    paths = dict(run=run, cache=run/"dense.json", analysis=run/"shared_analysis.json",
                 exports=run/"exports", review=run/"candidate_review.csv")
    for path in paths.values():
        if path.is_symlink() or path.resolve() == video.resolve() or (
                path.exists() and path.samefile(video)):
            raise ValueError("Output conflicts with source or symlink")
    return paths


def obtain_analysis(video, paths, read_only=False):
    cache, analysis = paths["cache"], paths["analysis"]
    if analysis.exists() and not cache.is_file():
        raise ValueError("Shared analysis exists without its dense cache; refusing recomputation")
    if read_only and not cache.is_file():
        raise ValueError("Dense cache missing; read-only operation cannot collect observations")
    if analysis.exists() or read_only:
        # Read-only reuse uses collector validators, never its create-if-missing path.
        artifact = dense.validate(read_json(cache))
        identity = artifact["source_identity"]
        if file_identity(video) != (identity["digest"], identity["size_bytes"]) or dense.recipe() != artifact["recipe"]:
            raise ValueError("Stale dense cache: source or producer changed")
        if canonical(artifact["visual"]) != canonical(dense.visual_input(None, artifact["full_observations"]["source_video"])):
            raise ValueError("This baseline workflow requires a cache without optional CLIP input")
        cache_status = "reused"
        expected = integration.adapt(artifact, video, cache)
        if analysis.exists():
            actual = load_analysis(analysis)
            if canonical(actual) != canonical(expected):
                raise ValueError("Saved shared analysis differs from verified dense baseline; choose a new output root")
            return actual, cache_status, "reused"
        return expected, cache_status, "not written (preview)"
    result, cache_status = integration.generate(video, cache, analysis)
    return result, cache_status, "created"


def review_text(manifest, directory, requested):
    """Blank human fields; scores are the original baseline ranking scores."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(["candidate", "start_seconds", "end_seconds", "duration_seconds", "anchor_seconds",
                     "selection_method", "score_key", "ranking_score", "output_path",
                     "output_note", "human_quality_rating", "human_notes"])
    for i, row in enumerate(manifest["clips"], 1):
        writer.writerow([i, row["start"], row["end"], row["duration"], row["candidate_timestamp"],
            manifest["selection"]["detector"], row["ranking_score_key"], row["ranking_score"],
            str(directory/row["output_filename"]),
            "Planned path; consult exporter manifest for success" if requested else "Shorts not requested",
            "", ""])
    return buffer.getvalue()


def publish_review(text, path):
    """Never replace a report, including human edits or a racing destination."""
    if path.is_symlink():
        raise ValueError("Refusing symlink review report")
    if path.exists():
        if not path.is_file():
            raise ValueError("Review destination is not a file")
        return "preserved (may contain human edits)"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="",
                dir=path.parent, prefix=".dev-review-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return "created"


def run(video, output_root, mode="both", dry_run=False, cache_only=False):
    paths = paths_for(video, output_root)
    print(f"Developer workspace: {paths['run'].resolve()}")
    if dry_run and not paths["cache"].exists() and not paths["analysis"].exists():
        print("DRY RUN: dense collection, shared analysis and exports required; no work performed.")
        print(f"Planned cache: {paths['cache']}\nPlanned analysis: {paths['analysis']}")
        print(f"Planned exports: {paths['exports']}\nPlanned review: {paths['review']}")
        return 0
    if cache_only and not paths["analysis"].is_file():
        raise ValueError("Cache-only requires existing shared analysis")
    analysis, cache_status, analysis_status = obtain_analysis(video, paths, dry_run or cache_only)
    print(f"Dense: {cache_status}; shared analysis: {analysis_status}")
    print("Audio-only anchors: " + str([r["second"] for r in analysis["candidate_windows"]["data"]]))
    if not paths["analysis"].exists():
        print("DRY RUN: validated cached candidates; analysis publication and export pending. No writes.")
        return 0
    _, short_directory, manifest = plan_export(video, paths["analysis"], output_root=paths["exports"])
    outcomes = []
    for selected in ("shorts", "longform"):
        if mode not in (selected, "both"):
            continue
        directory = short_directory if selected == "shorts" else short_directory.parent/"longform"
        reuse = cache_only or directory.exists()
        args = [str(video), "--analysis", str(paths["analysis"]), "--mode", selected,
                "--output-root", str(paths["exports"])]
        args += ["--dry-run"] if dry_run else (["--cache-only"] if reuse else [])
        try:
            code = pipeline.main(args)
        except (Exception, SystemExit) as exc:
            print(f"FAIL: {selected}: {exc}")
            code = 1
        status = "preview" if dry_run else ("reused" if reuse else "exported")
        outcomes.append((selected, status if code == 0 else "FAILED"))
    if not (dry_run or cache_only):
        print(f"Review: {publish_review(review_text(manifest, short_directory, mode != 'longform'), paths['review'])}: {paths['review']}")
    else:
        print(f"Review: not written (read-only): {paths['review']}")
    print("Summary: " + "; ".join(f"{name}={status}" for name, status in outcomes))
    return int(any(status == "FAILED" for _, status in outcomes))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--mode", choices=("shorts", "longform", "both"), default="both")
    parser.add_argument("--output-root", type=Path, default=ROOT/"output"/"dev_tests")
    flags = parser.add_mutually_exclusive_group()
    flags.add_argument("--dry-run", action="store_true")
    flags.add_argument("--cache-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        return run(args.video, args.output_root, args.mode, args.dry_run, args.cache_only)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"FAIL: developer workflow: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
