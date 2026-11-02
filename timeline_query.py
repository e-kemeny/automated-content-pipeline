"""Read-only retrieval of existing timeline observations using closed intervals."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile

from multimodal_timeline import MODALITIES, number, read_json, validate_timeline


def query_timeline(timeline, start_seconds, end_seconds, modality=None):
    """Return independent copies of matching observations, in stored order."""
    validate_timeline(timeline)
    start, end = number(start_seconds), number(end_seconds)
    if not 0 <= start <= end:
        raise ValueError("Query requires 0 <= start <= end")
    duration = timeline["duration_seconds"]
    if duration is not None and end > duration:
        raise ValueError("Query exceeds known video duration")
    if modality is not None and modality not in MODALITIES:
        raise ValueError("Invalid modality")
    events = [deepcopy(event) for event in timeline["events"]
              if (modality is None or event["modality"] == modality)
              and event["start_seconds"] <= end and event["end_seconds"] >= start]
    return dict(query=dict(start_seconds=start, end_seconds=end, modality=modality),
                timeline_schema_version=timeline["schema_version"],
                identity_status=timeline["identity_status"],
                source_identity=deepcopy(timeline["source_identity"]),
                sources=deepcopy(timeline["sources"]),
                matched_event_count=len(events),
                counts_by_modality={name:sum(e["modality"] == name for e in events)
                                    for name in MODALITIES},
                events=events)


def save_query(result, path, overwrite=False):
    """Publish complete JSON atomically; exclusive publication unless opted in."""
    text = json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n"
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Refusing symlink output")
    if path.exists() and not overwrite:
        raise FileExistsError("Output exists; use --overwrite")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=path.parent, prefix=".query-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if overwrite:
            if path.is_symlink():
                raise ValueError("Refusing symlink output")
            os.replace(temporary, path)
        else:
            os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeline", required=True, type=Path)
    parser.add_argument("--start", required=True, type=float)
    parser.add_argument("--end", required=True, type=float)
    parser.add_argument("--modality", choices=MODALITIES)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    if args.overwrite and args.output is None:
        parser.error("--overwrite requires --output")
    try:
        if args.output is not None and (
                args.output.resolve() == args.timeline.resolve() or
                args.output.exists() and args.timeline.exists() and args.output.samefile(args.timeline)):
            raise ValueError("Output must not replace the input timeline")
        result = query_timeline(read_json(args.timeline), args.start, args.end, args.modality)
        if args.output is not None:
            save_query(result, args.output, args.overwrite)
        print(json.dumps(result, separators=(",", ":"), allow_nan=False))
    except (OSError, ValueError) as exc:
        print(f"FAIL: timeline query: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
