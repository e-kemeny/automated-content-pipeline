"""Shared persisted evidence for future Shorts and Long-form consumers.

Standard library plus existing schema validators only; never runs analysis.
"""
from copy import deepcopy
import json
import math
from pathlib import Path

from semantic_events import validate_event
from windows import temporal_overlap

SCHEMA_VERSION = 1
LANGUAGE_SIGNALS = ("relevance", "humor", "reaction", "narrative_context")
VISUAL_SIGNALS = ("scene_changes", "motion", "semantic_frames")


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Expected a finite numeric value")
    return value


def _json(value):
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, (int, float)):
        _number(value)
    elif isinstance(value, list):
        for item in value:
            _json(item)
    elif isinstance(value, dict) and all(isinstance(k, str) for k in value):
        for item in value.values():
            _json(item)
    else:
        raise ValueError("Only JSON values with string object keys are supported")


def signal(rows=None, provenance=None):
    """None means not analyzed; [] means analyzed with no observations."""
    return dict(status="not_analyzed" if rows is None else "analyzed",
                data=[] if rows is None else deepcopy(rows),
                provenance=deepcopy(provenance or {}))


def create_analysis(source_video):
    result = dict(schema_version=SCHEMA_VERSION, source_video=deepcopy(source_video),
        visual={name: signal() for name in VISUAL_SIGNALS},
        acoustic={"audio_activity": signal()}, transcript=signal(),
        language={name: signal() for name in LANGUAGE_SIGNALS},
        semantic_events=signal(), candidate_windows=signal())
    return validate_analysis(result)


def _point(row, field, duration):
    timestamp = _number(row[field])
    if not 0 <= timestamp <= duration:
        raise ValueError("Timestamp outside source video")
    return (timestamp,)


def _interval(row, duration):
    start, end = _number(row["start"]), _number(row["end"])
    temporal_overlap(row, row)  # Reuse existing half-open interval validation.
    if end > duration:
        raise ValueError("Interval outside source video")
    return start, end


def _validate_signal(item, kind, duration):
    if set(item) != {"status", "data", "provenance"}:
        raise ValueError("Invalid signal envelope")
    language = kind in LANGUAGE_SIGNALS
    allowed = ("not_analyzed", "analyzed", "partial", "failed") if language else ("not_analyzed", "analyzed")
    if item["status"] not in allowed:
        raise ValueError("Unsupported signal status")
    if not isinstance(item["data"], list) or not isinstance(item["provenance"], dict):
        raise ValueError("Signal data must be a list and provenance an object")
    if item["status"] == "not_analyzed" and item["data"]:
        raise ValueError("not_analyzed cannot contain observations")
    scored_stage = language and (item["provenance"].get("producer") == "language-v1" or
                                 item["status"] in ("partial", "failed"))
    previous = None
    for row in item["data"]:
        if not isinstance(row, dict):
            raise ValueError("Observations must be objects")
        if kind in ("audio_activity", "motion"):
            key = _point(row, "second", duration)
        elif kind == "scene_changes":
            key = _point(row, "time", duration)
        elif kind == "semantic_frames":
            key = _point(row, "timestamp", duration) if "timestamp" in row else _interval(row, duration)
            for t in row.get("frame_timestamps", []):
                t = _number(t)
                if not row["start"] <= t < row["end"]:
                    raise ValueError("Sampled frame outside its window")
        else:
            key = _interval(row, duration)
            if kind == "semantic_events":
                validate_event(row)
            elif kind == "candidate_windows":
                if "second" in row:
                    t = _number(row["second"])
                    if not key[0] <= t <= key[1]:
                        raise ValueError("Candidate timestamp outside its window")
                if "duration" in row and not math.isclose(_number(row["duration"]), key[1]-key[0], abs_tol=1e-9):
                    raise ValueError("Window duration disagrees with bounds")
            elif kind == "transcript" and not isinstance(row["text"], str):
                raise ValueError("Transcript text must be a string")
        if scored_stage:
            if row["status"] not in ("scored", "invalid_output", "inference_error"):
                raise ValueError("Invalid language row status")
            if row["status"] == "scored":
                if not 0 <= _number(row["score"]) <= 1 or row.get("failure_reason") is not None:
                    raise ValueError("Invalid successful language score")
            elif row.get("score") is not None or not isinstance(row.get("failure_reason"), str) or not row["failure_reason"]:
                raise ValueError("Failed language observations require a reason and no score")
            if row["status"] != "inference_error" and not isinstance(row.get("raw_output"), str):
                raise ValueError("Successful or invalid-output rows must preserve raw text")
            if not isinstance(row.get("text"), str) or row.get("raw_output") is not None and not isinstance(row["raw_output"], str):
                raise ValueError("Invalid language evidence")
        if previous is not None and key < previous:
            raise ValueError("Observations must be chronological (start then end for intervals)")
        previous = key

    if scored_stage:
        if not all("status" in row for row in item["data"]):
            raise ValueError("Cannot mix scored-stage and legacy language rows")
        total = len(item["data"])
        successes = sum(row["status"] == "scored" for row in item["data"])
        expected = "analyzed" if successes == total else ("partial" if successes else "failed")
        if item["status"] != expected:
            raise ValueError("Language completion status disagrees with outcomes")


def validate_analysis(result):
    """Reject unsupported versions, invalid timing/order, and non-JSON metadata."""
    try:
        _json(result)
        required = {"schema_version", "source_video", "visual", "acoustic",
                    "transcript", "language", "semantic_events", "candidate_windows"}
        if not isinstance(result, dict) or set(result) != required:
            raise ValueError("Invalid analysis fields")
        if type(result["schema_version"]) is not int or result["schema_version"] != SCHEMA_VERSION:
            raise ValueError("Unsupported analysis schema version")
        source = result["source_video"]
        if not isinstance(source["path"], str) or not source["path"]:
            raise ValueError("Source path must be a nonempty string")
        duration = _number(source["duration_seconds"])
        if duration <= 0:
            raise ValueError("Source duration must be positive")
        for field in ("width", "height"):
            if field in source and (type(source[field]) is not int or source[field] <= 0):
                raise ValueError("Video dimensions must be positive integers")
        if "fps" in source and _number(source["fps"]) <= 0:
            raise ValueError("FPS must be positive")
        if "sha256" in source and (not isinstance(source["sha256"], str) or
                len(source["sha256"]) != 64 or any(c not in "0123456789abcdef" for c in source["sha256"])):
            raise ValueError("SHA-256 must be 64 lowercase hexadecimal characters")
        for section, names in (("visual", VISUAL_SIGNALS), ("acoustic", ("audio_activity",)),
                               ("language", LANGUAGE_SIGNALS)):
            if set(result[section]) != set(names):
                raise ValueError("Missing or unknown signal")
            for name in names:
                _validate_signal(result[section][name], name, duration)
        for name in ("transcript", "semantic_events", "candidate_windows"):
            _validate_signal(result[name], name, duration)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Malformed analysis data") from exc
    return deepcopy(result)


def from_existing_signals(source_video, *, audio_rows=None, scene_rows=None, motion_rows=None,
                          visual_rows=None, semantic_events=None, candidate_windows=None,
                          transcript_segments=None, language_signals=None, provenance=None):
    """Adapt supplied observations only; preserve values, metadata, and list order.

    Producers such as main.py return score-ranked audio/scene rows. The caller
    must explicitly arrange chronological rows before adapting; this function
    rejects unordered input and never reorders candidates or changes ranking.
    language_signals maps each named signal to interval rows, without computing it.
    """
    result = create_analysis(source_video)
    provenance = provenance or {}
    supplied = dict(audio_activity=audio_rows, scene_changes=scene_rows, motion=motion_rows,
                    semantic_frames=visual_rows, semantic_events=semantic_events,
                    candidate_windows=candidate_windows, transcript=transcript_segments)
    for section in ("visual", "acoustic", "language"):
        for name in result[section]:
            rows = (language_signals or {}).get(name) if section == "language" else supplied[name]
            result[section][name] = signal(rows, provenance.get(name))
    if language_signals and set(language_signals) - set(LANGUAGE_SIGNALS):
        raise ValueError("Unknown language signal")
    for name in ("transcript", "semantic_events", "candidate_windows"):
        result[name] = signal(supplied[name], provenance.get(name))
    return validate_analysis(result)


def from_saved_semantics(source_video, timeline_path, events_path):
    """Read saved CLIP/temporal/VLM evidence and events; no inference/conversion.

    Preserve artifact headers as provenance. Supports rows or predictions, as
    actually emitted by existing experiments. Invalid VLM responses remain in
    visual evidence; an analyzed-empty event list does not imply detection success.
    """
    artifact = json.loads(Path(timeline_path).read_text(encoding="utf-8"))
    if artifact["duration"] != source_video["duration_seconds"]:
        raise ValueError("Artifact duration differs from source")
    if artifact.get("video_sha256") and source_video.get("sha256") and artifact["video_sha256"] != source_video["sha256"]:
        raise ValueError("Artifact belongs to a different source video")
    field = "rows" if "rows" in artifact else "predictions"
    rows = artifact[field]
    events = json.loads(Path(events_path).read_text(encoding="utf-8"))
    provenance = {k: v for k, v in artifact.items() if k != field}
    return from_existing_signals(source_video, visual_rows=rows, semantic_events=events,
        provenance=dict(semantic_frames=provenance, semantic_events=dict(artifact=str(events_path))))


def windows_from_results(results, detector, k, variant="fixed"):
    """Copy one saved fixed/dynamic result's windows; do not reselect candidates.

    Existing V1 pairs use fixed/dynamic; V2 triples use fixed/v1/v2.
    """
    matches = [r for r in results if r["fixed"]["detector"] == detector and r["fixed"]["k"] == k]
    if len(matches) != 1:
        raise ValueError("Expected exactly one detector/K result")
    if variant not in matches[0]:
        raise ValueError("Unavailable window variant")
    return deepcopy(matches[0][variant]["windows"])


def serialize_analysis(result):
    return json.dumps(validate_analysis(result), indent=2, sort_keys=True, allow_nan=False) + "\n"


def save_analysis(result, path):
    text = serialize_analysis(result)  # Validate before opening the file.
    Path(path).write_text(text, encoding="utf-8")


def load_analysis(path):
    """Both future output modes use this same loader; no recomputation hooks."""
    return validate_analysis(json.loads(Path(path).read_text(encoding="utf-8")))
