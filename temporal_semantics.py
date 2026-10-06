"""Frozen five-second mean of full CLIP relative-score vectors; no inference/GT."""
from copy import deepcopy
import math
from statistics import mean, median

from semantic_clip import MODEL_ID, PROMPTS, sample_timestamps, validate_timeline
from semantic_events import create_event

RADIUS_SECONDS = 2
SCORE_FIELD = "zero_shot_score"


def aggregate_timeline(rows, duration):
    """Require the complete ordered 1 FPS grid; never interpolate missing samples.

    Average all seven relative scores independently over [t-2,t+2], inclusive.
    Edge windows use available samples only. No second softmax or thresholds.
    Ties use the frozen prompt order. Preserve the full source neighborhood.
    """
    try:
        rows = validate_timeline(rows, duration)
    except (KeyError, TypeError) as exc:
        raise ValueError("Invalid raw CLIP timeline") from exc
    result = []
    for i, row in enumerate(rows):
        neighborhood = rows[max(0, i-RADIUS_SECONDS):i+RADIUS_SECONDS+1]
        scores = {label: mean(r["scores"][label][SCORE_FIELD] for r in neighborhood)
                  for label in PROMPTS}
        winner = max(PROMPTS, key=scores.get)
        result.append(dict(timestamp=row["timestamp"], label=winner, winning_score=scores[winner],
                           mean_zero_shot_scores=scores, model_id=MODEL_ID,
                           neighborhood=deepcopy(neighborhood)))
    return result


def temporal_to_events(rows, duration):
    """Same bin/group/exclude-neutral rule as raw V1; confidence remains uncalibrated."""
    expected = sample_timestamps(duration)
    if rows and [r["timestamp"] for r in rows] != expected:
        raise ValueError("Aggregated timeline must use the complete ordered 1 FPS grid")
    runs = []
    for row in rows:
        scores = row["mean_zero_shot_scores"]
        if set(scores) != set(PROMPTS) or any(
            isinstance(v, bool) or not isinstance(v, (int,float)) or not math.isfinite(v) or not 0 <= v <= 1
            for v in scores.values()
        ) or not math.isclose(sum(scores.values()), 1, abs_tol=1e-9):
            raise ValueError("Invalid aggregated score vector")
        winner = max(PROMPTS, key=scores.get)
        if row["label"] != winner or row["winning_score"] != scores[winner] or row["model_id"] != MODEL_ID:
            raise ValueError("Inconsistent aggregated winner")
        if not runs or runs[-1][-1]["label"] != row["label"]:
            runs.append([])
        runs[-1].append(row)
    events = []
    for run in runs:
        if run[0]["label"] == "neutral":
            continue
        events.append(create_event(run[0]["timestamp"], min(duration, run[-1]["timestamp"]+1),
            run[0]["label"], mean(r["winning_score"] for r in run), source=MODEL_ID,
            metadata=dict(confidence_semantics="mean winning temporally averaged zero_shot_score; uncalibrated",
                          aggregation="unweighted centered t-2 through t+2; available edges only",
                          samples=deepcopy(run))))
    return events


def stability_metrics(rows, events):
    """Transitions/stability include neutral; durations/counts exclude neutral.

    No adjacent pairs: stability fraction is None. No events: duration statistics
    are None. These measure fragmentation, not semantic correctness.
    """
    transitions = sum(a["label"] != b["label"] for a,b in zip(rows, rows[1:]))
    adjacent = max(0, len(rows)-1)
    durations = [e["end"]-e["start"] for e in events]
    return dict(event_count=len(events), label_transitions=transitions,
                mean_event_duration=mean(durations) if durations else None,
                median_event_duration=median(durations) if durations else None,
                longest_event_duration=max(durations) if durations else None,
                adjacent_same_label_fraction=(adjacent-transitions)/adjacent if adjacent else None)
