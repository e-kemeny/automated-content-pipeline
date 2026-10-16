"""Run unit/motion regression checks and optionally verify read-only cached exports."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def test_commands():
    return [
        ("Unit tests", [sys.executable, "-m", "unittest", "discover", "-q"]),
        ("Motion checks (4)", [sys.executable, "test_motion.py"]),
    ]


def run_check(label, command):
    try:
        result = subprocess.run(command, cwd=ROOT, check=False)
        passed = result.returncode == 0
        detail = "" if passed else f" (exit {result.returncode})"
    except OSError as exc:
        passed, detail = False, f": {exc}"
    print(f"{'PASS' if passed else 'FAIL'}: {label}{detail}", flush=True)
    return passed


def artifact_paths(video, analysis):
    # Use existing read-only planners; never infer filenames from untrusted manifests.
    from export_shorts import plan_export
    from export_longform import prepare_plan

    for path in (video, analysis):
        if not path.is_file():
            raise ValueError(f"Missing input file: {path}")
    _, short_dir, short_plan = plan_export(video, analysis, output_root=ROOT/"output")
    _, long_dir, long_plan = prepare_plan(video, analysis, output_root=ROOT/"output")
    paths = [analysis, short_dir/"shorts_manifest.json", long_dir/"longform_manifest.json"]
    paths += [short_dir/row["output_filename"] for row in short_plan["clips"]]
    paths.append(Path(long_plan["assembly"]["output_path"]))
    if len(paths) != 9 or len(set(paths)) != 9:
        raise ValueError("Verification V1 requires five Shorts and one Long-form export")
    return paths


def snapshot(paths):
    result = {}
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Missing or symlink artifact: {path}")
        before = path.stat()
        with path.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError(f"Artifact changed while hashing: {path}")
        result[path] = (digest, after.st_mtime_ns)
    return result


def verify_cached_export(video, analysis):
    try:
        paths = artifact_paths(video, analysis)
        before = snapshot(paths)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"FAIL: Cached-export prerequisites: {exc}", flush=True)
        return False
    print("PASS: Cached-export prerequisites (9 artifacts)", flush=True)
    passed = run_check("Cached pipeline", [
        sys.executable, "pipeline.py", str(video), "--analysis", str(analysis),
        "--mode", "both", "--cache-only",
    ])
    # Check integrity even if the pipeline failed.
    try:
        after = snapshot(paths)
        changed = [str(path) for path in paths if before[path] != after[path]]
        if changed:
            raise ValueError("Changed artifacts: " + ", ".join(changed))
    except (OSError, ValueError) as exc:
        print(f"FAIL: Artifact integrity: {exc}", flush=True)
        return False
    print("PASS: Artifact integrity (all 9 SHA-256 hashes and nanosecond mtimes unchanged)", flush=True)
    return passed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cached-export", action="store_true")
    parser.add_argument("--video", type=Path)
    parser.add_argument("--analysis", type=Path)
    args = parser.parse_args(argv)
    if args.cached_export and (args.video is None or args.analysis is None):
        parser.error("--cached-export requires --video and --analysis")
    if not args.cached_export and (args.video is not None or args.analysis is not None):
        parser.error("--video and --analysis require --cached-export")
    outcomes = [run_check(label, command) for label, command in test_commands()]
    if args.cached_export:
        outcomes.append(verify_cached_export(args.video.resolve(), args.analysis.resolve()))
    passed = all(outcomes)
    print(f"{'PASS' if passed else 'FAIL'}: Verification", flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
