"""Normalize saved observations only; no media access, inference or ranking."""
import argparse
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import tempfile

from shared_analysis import validate_analysis
from source_identity import validate_identity
from transcription import validate_segments

SCHEMA_VERSION = 1
ROOT = Path(__file__).resolve().parent
MODALITIES = ("audio", "visual", "transcript")


def json_value(value):
    if value is None or isinstance(value, (str, bool)):
        return
    if type(value) in (int, float):
        if not math.isfinite(value):
            raise ValueError("JSON numbers must be finite")
    elif isinstance(value, list):
        for item in value:
            json_value(item)
    elif isinstance(value, dict) and all(isinstance(k, str) for k in value):
        for item in value.values():
            json_value(item)
    else:
        raise ValueError("Expected JSON values with string keys")


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("Timestamp/metadata must be finite numeric values")
    return value


def source_metadata(source):
    if not isinstance(source, dict):
        raise ValueError("Source metadata must be an object")
    if "sha256" in source:
        digest = source["sha256"]
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("Invalid reported source SHA-256")
    for key in ("duration_seconds", "width", "height", "fps", "size_bytes"):
        if key in source:
            value = number(source[key])
            if value < 0 or (key != "size_bytes" and value == 0):
                raise ValueError(f"Invalid source {key}")
            if key in ("width", "height", "size_bytes") and type(value) is not int:
                raise ValueError(f"Source {key} must be an integer")
    return deepcopy(source)


def reconcile(sources):
    """Compare reported evidence, never claim to have rehashed the source video."""
    metadata = [source_metadata(s["source_video"]) for s in sources]
    if len(metadata) > 1 and any("sha256" not in s for s in metadata):
        raise ValueError("Cannot merge separate artifacts without every source SHA-256")
    known = {}
    for source in metadata:
        for key in ("sha256", "duration_seconds", "width", "height", "fps", "size_bytes"):
            if key in source:
                if key in known and known[key] != source[key]:
                    raise ValueError(f"Source identity mismatch: {key}")
                known[key] = source[key]
    # Reported per-channel claims must not contradict headers or each other,
    # even when a single artifact has no top-level digest.
    claims = dict(known)
    for artifact in sources:
        if (artifact["kind"] not in ("analysis", "transcript", "vision") or
                not isinstance(artifact["artifact"], str) or not artifact["artifact"] or
                not isinstance(artifact["channels"], dict)):
            raise ValueError("Invalid source record")
        for name, channel in artifact["channels"].items():
            if not isinstance(name, str) or not name or channel["status"] not in ("analyzed", "not_analyzed"):
                raise ValueError("Invalid source channel")
            provenance = channel["provenance"]
            check_provenance(provenance, artifact["source_video"])
            for old, key in (("source_sha256", "sha256"), ("source_duration_seconds", "duration_seconds")):
                if old in provenance:
                    if key in claims and claims[key] != provenance[old]:
                        raise ValueError(f"Source identity mismatch across provenance: {key}")
                    claims[key] = provenance[old]
    identity = None
    if {"sha256", "size_bytes", "duration_seconds", "width", "height"} <= known.keys():
        identity = validate_identity(dict(version=1, algorithm="sha256",
            digest=known["sha256"], size_bytes=known["size_bytes"],
            media={k:known[k] for k in ("duration_seconds", "width", "height", "fps") if k in known}))
    status = "consistent_reported_sha256" if "sha256" in known else "unverified_single_artifact"
    return dict(identity_status=status, source_identity=identity,
                duration_seconds=known.get("duration_seconds"))


def check_provenance(provenance, source):
    if not isinstance(provenance, dict):
        raise ValueError("Provenance must be an object")
    claims = {}
    for old, new in (("source_sha256", "sha256"), ("source_duration_seconds", "duration_seconds")):
        if old in provenance:
            claims[new] = provenance[old]
    source_metadata(claims)
    for key in claims.keys() & source.keys():
        if claims[key] != source[key]:
            raise ValueError(f"Source identity mismatch in provenance: {key}")


def event(row, modality, event_type, start_key, end_key, source, row_index):
    if not isinstance(row, dict):
        raise ValueError("Observation must be an object")
    try:
        start = row[start_key]
        end = row[end_key] if end_key else start
    except KeyError as exc:
        raise ValueError(f"Missing timestamp: {exc.args[0]}") from exc
    if not 0 <= number(start) <= number(end):
        raise ValueError("Event timestamps must be nonnegative and ordered")
    return dict(modality=modality, event_type=event_type,
                observation_kind="interval" if end_key else "point",
                start_seconds=start, end_seconds=end,
                source=dict(source, row_index=row_index), payload=deepcopy(row))


def audio_events(rows, source):
    return [event(row, "audio", "audio_spike_score" if "spike" in row else "audio_activity",
                  "second", None, source, i) for i, row in enumerate(rows)]


def scene_events(rows, source):
    return [event(row, "visual", "scene_change", "time", None, source, i)
            for i, row in enumerate(rows)]


def transcript_events(rows, source):
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("text"), str):
            raise ValueError("Transcript requires original text")
    return [event(row, "transcript", "speech_segment", "start", "end", source, i)
            for i, row in enumerate(rows)]


def adapt(kind, artifact, label, index):
    """Return source record and observations for one actual supported artifact."""
    json_value(artifact)
    if not isinstance(artifact, dict):
        raise ValueError(f"{kind}: expected an object, not raw rows")
    channels = {}
    rows = []
    def add(name, envelope, adapter):
        check_provenance(envelope["provenance"], source)
        channels[name] = dict(status=envelope["status"], provenance=deepcopy(envelope["provenance"]))
        rows.extend(adapter(envelope["data"], dict(artifact_index=index, channel=name,
                                                   provenance=deepcopy(envelope["provenance"]))))
    try:
        if kind == "analysis" or kind == "transcript" and "schema_version" in artifact:
            data = validate_analysis(artifact)
            source = source_metadata(data["source_video"])
            if kind == "analysis":
                add("audio_activity", data["acoustic"]["audio_activity"], audio_events)
                add("scene_changes", data["visual"]["scene_changes"], scene_events)
            add("transcript", data["transcript"], transcript_events)
            # The producer's word metadata validator is pure and imports no ASR backend.
            validate_segments(data["transcript"]["data"], source["duration_seconds"])
        elif kind == "transcript":
            if set(artifact) != {"segments", "provenance"}:
                raise ValueError("Transcript must be Shared Analysis V1 or transcribe_media segments/provenance")
            provenance = artifact["provenance"]
            if not isinstance(provenance, dict) or not isinstance(artifact["segments"], list):
                raise ValueError("Invalid transcription result")
            source = source_metadata({new:provenance[old] for old, new in (
                ("source_sha256", "sha256"), ("source_duration_seconds", "duration_seconds")) if old in provenance})
            if "duration_seconds" in source:
                validate_segments(artifact["segments"], source["duration_seconds"])
            add("transcript", dict(status="analyzed", data=artifact["segments"], provenance=provenance), transcript_events)
        elif kind == "vision":
            if type(artifact.get("schema_version")) is not int or artifact["schema_version"] != 1 or artifact.get("experiment") != "vision-inference-v1":
                raise ValueError("Unsupported vision schema/experiment")
            source = source_metadata(artifact["video"])
            if not isinstance(artifact["frames"], list):
                raise ValueError("Vision frames must be a list")
            provenance = {k:deepcopy(v) for k, v in artifact.items() if k not in ("frames", "video")}
            for key in ("model", "sampling", "runtime"):
                if not isinstance(artifact[key], dict):
                    raise ValueError(f"Missing vision {key}")
            if artifact["model"].get("name") != "resnet18":
                raise ValueError("Unsupported vision model")
            for row in artifact["frames"]:
                if not isinstance(row, dict) or not isinstance(row.get("top3"), list) or len(row["top3"]) != 3:
                    raise ValueError("Vision frame requires original top3 predictions")
                for prediction in row["top3"]:
                    if not isinstance(prediction.get("category"), str) or not 0 <= number(prediction["confidence"]) <= 1:
                        raise ValueError("Invalid vision prediction")
            def frames(data, src):
                return [event(row, "visual", "imagenet_frame_prediction", "timestamp_seconds", None, src, i)
                        for i, row in enumerate(data)]
            add("frames", dict(status="analyzed", data=artifact["frames"], provenance=provenance), frames)
        else:
            raise ValueError("Unsupported adapter")
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f"Malformed {kind} artifact: {exc}") from exc
    return dict(kind=kind, artifact=label, source_video=source, channels=channels), rows


def sort_key(row):
    return (row["start_seconds"], row["end_seconds"], row["modality"], row["source_order"])


def validate_timeline(result):
    try:
        json_value(result)
        required = {"schema_version", "timeline_type", "sources", "events",
                    "identity_status", "source_identity", "duration_seconds"}
        if not isinstance(result, dict) or set(result) != required:
            raise ValueError("Invalid timeline fields")
        if not isinstance(result["events"], list) or not isinstance(result["sources"], list):
            raise ValueError("Timeline sources/events must be lists")
        if type(result["schema_version"]) is not int or result["schema_version"] != SCHEMA_VERSION:
            raise ValueError("Unsupported timeline schema version")
        if result["timeline_type"] != "multimodal-observations" or not result["sources"]:
            raise ValueError("Timeline requires at least one artifact")
        expected = reconcile(result["sources"])
        for key, value in expected.items():
            if result[key] != value:
                raise ValueError("Timeline source metadata disagrees")
        duration = result["duration_seconds"]
        orders = set()
        for row in result["events"]:
            start, end = number(row["start_seconds"]), number(row["end_seconds"])
            if not 0 <= start <= end or duration is not None and end > duration:
                raise ValueError("Event timestamps outside video bounds or reversed")
            if row["modality"] not in MODALITIES or not isinstance(row["event_type"], str) or not row["event_type"]:
                raise ValueError("Invalid event modality/type")
            if row["observation_kind"] not in ("point", "interval") or row["observation_kind"] == "point" and start != end:
                raise ValueError("Invalid point/interval convention")
            order, src = row["source_order"], row["source"]
            if type(order) is not int or order < 0 or order in orders:
                raise ValueError("Invalid stable source order")
            orders.add(order)
            if (type(src["artifact_index"]) is not int or not 0 <= src["artifact_index"] < len(result["sources"])
                    or type(src["row_index"]) is not int or src["row_index"] < 0
                    or not isinstance(src["provenance"], dict) or not isinstance(row["payload"], dict)):
                raise ValueError("Invalid event source/payload")
            channel = result["sources"][src["artifact_index"]]["channels"][src["channel"]]
            if channel["provenance"] != src["provenance"]:
                raise ValueError("Event provenance disagrees with channel")
        if sorted(result["events"], key=sort_key) != result["events"]:
            raise ValueError("Timeline events must be sorted")
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Malformed timeline") from exc
    return result


def build_timeline(*, analysis=None, transcript=None, vision=None, labels=None):
    sources, events = [], []
    for kind, artifact in (("analysis", analysis), ("transcript", transcript), ("vision", vision)):
        if artifact is None:
            continue
        source, observations = adapt(kind, artifact, (labels or {}).get(kind, kind), len(sources))
        sources.append(source)
        for row in observations:
            row["source_order"] = len(events)
            events.append(row)
    if not sources:
        raise ValueError("At least one input artifact is required")
    result = dict(schema_version=SCHEMA_VERSION, timeline_type="multimodal-observations",
                  sources=sources, events=sorted(events, key=sort_key), **reconcile(sources))
    return validate_timeline(result)


def read_json(path):
    def reject_constant(value):
        raise ValueError(f"Invalid JSON constant: {value}")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding="utf-8-sig"),
                      parse_constant=reject_constant, object_pairs_hook=pairs)


def save_timeline(result, path, overwrite=False):
    text = json.dumps(validate_timeline(result), sort_keys=True, indent=2, allow_nan=False) + "\n"
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Refusing symlink output")
    if path.resolve().is_relative_to(ROOT) and not path.resolve().is_relative_to(ROOT/"output"):
        raise ValueError("Repository output must be under ignored output/")
    original = path.read_bytes() if path.exists() else None
    if path.exists():
        if not overwrite:
            raise FileExistsError("Output exists; use --overwrite")
        validate_timeline(read_json(path))  # Do not replace unrelated artifacts.
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=path.parent, prefix=".timeline-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if overwrite:
            if path.is_symlink():
                raise ValueError("Refusing symlink output")
            if (path.read_bytes() if path.exists() else None) != original:
                raise ValueError("Output changed during publication")
            os.replace(temporary, path)
        else:
            os.link(temporary, path)  # Exclusive atomic publication, no race clobber.
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("analysis", "transcript", "vision"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--output", type=Path, default=Path("output/multimodal_timeline_v1.json"))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    paths = {name:getattr(args, name) for name in ("analysis", "transcript", "vision") if getattr(args, name) is not None}
    if not paths:
        parser.error("At least one of --analysis, --transcript or --vision is required")
    try:
        if any(args.output.resolve() == path.resolve() or
               args.output.exists() and path.exists() and args.output.samefile(path) for path in paths.values()):
            raise ValueError("Output must not replace an input artifact")
        if args.output.exists() and not args.overwrite:
            raise FileExistsError("Output exists; use --overwrite")
        result = build_timeline(**{name:read_json(path) for name, path in paths.items()},
                                labels={name:str(path) for name, path in paths.items()})
        save_timeline(result, args.output, args.overwrite)
    except (OSError, ValueError) as exc:
        print(f"FAIL: timeline: {exc}")
        return 1
    print(f"Saved {len(result['events'])} observations: {args.output}; {result['identity_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
