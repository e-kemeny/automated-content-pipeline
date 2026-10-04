"""Model-independent semantic event interface. No detection or scoring.

Schema: start/end (finite seconds, 0 <= start <= end), event_type,
confidence (finite [0,1]), optional source (string), metadata (JSON object).
Extend EVENT_TYPES deliberately; specific subtypes can live in metadata.
Duration intervals are [start,end); zero-duration events are instantaneous.
"""
from copy import deepcopy
import json
import math
from pathlib import Path

EVENT_TYPES = ("combat", "kill", "death", "objective", "transition", "victory")


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Expected a finite numeric value")
    return value


def _bounds(start, end):
    if _number(start) < 0 or _number(end) < start:
        raise ValueError("Require 0 <= start <= end")
    return start, end


def _json_value(value):
    """Reject values JSON would silently coerce or cannot faithfully preserve."""
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, (int, float)):
        _number(value)
    elif isinstance(value, list):
        for item in value:
            _json_value(item)
    elif isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for item in value.values():
            _json_value(item)
    else:
        raise ValueError("Metadata must contain only JSON values and string keys")


def validate_event(event):
    """Validate and return an independent copy; never repair invalid data."""
    if not isinstance(event, dict):
        raise ValueError("Event must be an object")
    required = {"start", "end", "event_type", "confidence"}
    if not required <= event.keys() or event.keys() - required - {"source", "metadata"}:
        raise ValueError("Missing or unknown event fields; put extensions in metadata")
    _bounds(event["start"], event["end"])
    if event["event_type"] not in EVENT_TYPES:
        raise ValueError("Unknown event type")
    if not 0 <= _number(event["confidence"]) <= 1:
        raise ValueError("Confidence must be in [0,1]")
    if "source" in event and not isinstance(event["source"], str):
        raise ValueError("Source must be a string")
    if "metadata" in event and not isinstance(event["metadata"], dict):
        raise ValueError("Metadata must be a JSON object")
    _json_value(event.get("metadata", {}))
    return deepcopy(event)


def create_event(start, end, event_type, confidence, *, source=None, metadata=None):
    event = dict(start=start, end=end, event_type=event_type, confidence=confidence)
    if source is not None:
        event["source"] = source
    if metadata is not None:
        event["metadata"] = metadata
    return validate_event(event)


def sort_events(events):
    """Chronological copies, sorted by start then end; ties keep input order."""
    return sorted((validate_event(e) for e in events), key=lambda e: (e["start"], e["end"]))


def serialize_events(events):
    """Indented, sorted-key JSON; timeline order is chronological and stable."""
    return json.dumps(sort_events(events), indent=2, sort_keys=True, allow_nan=False) + "\n"


def save_events(events, path):
    text = serialize_events(events)  # Validate before opening an existing file.
    Path(path).write_text(text, encoding="utf-8")


def load_events(path):
    events = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(events, list):
        raise ValueError("Event file must contain a list")
    return sort_events(events)


def _overlaps(event, start, end):
    a, b = event["start"], event["end"]
    if start == end:
        return a == b == start or a <= start < b
    if a == b:
        return start <= a < end
    return max(a, start) < min(b, end)


def events_overlapping(events, start, end):
    """Half-open overlap; a zero-length query asks which events occur at it."""
    _bounds(start, end)
    return [e for e in sort_events(events) if _overlaps(e, start, end)]


def _distance(event, start, end):
    return max(start - event["end"], event["start"] - end, 0)


def events_near_timestamp(events, timestamp, radius):
    """Shortest distance to event extent <= radius, including touching endpoints.

    Proximity is inclusive: distance zero can include an excluded interval end.
    This is intentionally broader than half-open overlap.
    """
    _bounds(timestamp, timestamp)
    if _number(radius) < 0:
        raise ValueError("Radius must be nonnegative")
    return [e for e in sort_events(events) if _distance(e, timestamp, timestamp) <= radius]


def group_events_by_type(events):
    """Only present types, in vocabulary order; each group is chronological."""
    ordered = sort_events(events)
    return {kind: [e for e in ordered if e["event_type"] == kind]
            for kind in EVENT_TYPES if any(e["event_type"] == kind for e in ordered)}


def associate_events(events, candidate, radius=5.0):
    """Use start/end when supplied, otherwise candidate['second'] as a point.

    Nearby events exclude overlaps and have distance <= radius from the window
    or point. Types and maximum confidence cover the union of both lists.
    Candidate dictionaries, scores, and event inputs are never modified.
    """
    if "start" in candidate or "end" in candidate:
        if "start" not in candidate or "end" not in candidate:
            raise ValueError("Window requires both start and end")
        start, end = _bounds(candidate["start"], candidate["end"])
    else:
        start = end = candidate["second"]
        _bounds(start, end)
    if _number(radius) < 0:
        raise ValueError("Radius must be nonnegative")
    overlap, nearby = [], []
    for event in sort_events(events):
        if _overlaps(event, start, end):
            overlap.append(event)
        elif _distance(event, start, end) <= radius:
            nearby.append(event)
    groups = group_events_by_type(overlap + nearby)
    return dict(overlapping_events=overlap, nearby_events=nearby,
                event_types=list(groups),
                max_confidence_by_type={kind: max(e["confidence"] for e in group)
                                        for kind, group in groups.items()})


def summarize_sequence(events, start, end):
    """Ordered overlapping events/types, retaining repeats; no sequence rating.

    Simultaneous ties keep input order and do not imply causal ordering.
    """
    sequence = events_overlapping(events, start, end)
    return dict(events=sequence, event_types=[e["event_type"] for e in sequence])
