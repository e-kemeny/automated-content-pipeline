"""Export Shorts, Long-form, or both from persisted shared analysis."""
import argparse
from pathlib import Path

from export_shorts import main as shorts_main
from export_longform import main as longform_main


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--mode", choices=("shorts", "longform", "both"), default="both")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    args = parser.parse_args(argv)
    if args.cache_only and (args.force or args.dry_run):
        parser.error("--cache-only conflicts with --force and --dry-run")

    forwarded = [str(args.video), "--analysis", str(args.analysis)]
    if args.dry_run:
        forwarded.append("--dry-run")
    if args.force:
        forwarded.append("--force")

    if args.cache_only:
        forwarded.append("--cache-only")

    outcomes = []
    for mode, label, exporter in (
        ("shorts", "Shorts", shorts_main),
        ("longform", "Long-form", longform_main),
    ):
        if args.mode not in (mode, "both"):
            continue
        print(f"--- {label} ---", flush=True)
        try:
            code = exporter(list(forwarded))
        except SystemExit as exc:
            # Exporter CLIs use argparse.exit for validation/runtime errors.
            code = exc.code
        except Exception as exc:
            # Isolate unexpected exporter failures so both outcomes are reported.
            print(f"{label} error: {type(exc).__name__}: {exc}")
            code = 1
        failed = code not in (None, 0)
        outcomes.append(failed)
        print(f"{label}: {'failed' if failed else 'success'}", flush=True)

    failures = sum(outcomes)
    status = "success" if not failures else (
        "partial failure" if failures < len(outcomes) else "failed"
    )
    print(f"Pipeline: {status} ({failures}/{len(outcomes)} exports failed)")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
