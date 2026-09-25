"""Read YouTube retention exports without changing their original CSV values.

Loaders return a list of dictionaries: source cells remain strings under their
original headers; timestamp_seconds is a float. Positions are numeric percentages
(e.g. 50 means 50%), not fractions. No timeline rescaling or scoring is applied.
"""

import csv
import math
from pathlib import Path

POSITION = "Video position (%)"


def position_to_seconds(video_position, video_duration):
    """Convert a 0-100 percentage to seconds using the supplied duration."""
    position = float(video_position)
    duration = float(video_duration)
    if not math.isfinite(position) or not 0 <= position <= 100:
        raise ValueError("Video position must be a finite percentage from 0 to 100.")
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Video duration must be positive and finite.")
    return (position / 100) * duration


def _load_csv(path, video_duration, required_columns):
    position_to_seconds(0, video_duration)  # Validate even for header-only files.
    with Path(path).open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        headers = reader.fieldnames or []
        missing = set(required_columns) - set(headers)
        if missing:
            raise ValueError("Missing CSV columns: " + ", ".join(sorted(missing)))
        if "timestamp_seconds" in headers or len(headers) != len(set(headers)):
            raise ValueError("CSV contains duplicate headers or reserved timestamp_seconds column.")
        rows = []
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"CSV row ending at line {reader.line_num} has the wrong number of fields.")
            row["timestamp_seconds"] = position_to_seconds(row[POSITION], video_duration)
            rows.append(row)
    return rows


def load_retention_csv(path, video_duration):
    """Load All.csv, preserving position, retention, and any extra columns."""
    return _load_csv(path, video_duration, (POSITION, "Absolute audience retention (%)"))


def load_detailed_activity_csv(path, video_duration):
    """Load Detailed activity.csv, preserving all original activity values."""
    return _load_csv(path, video_duration, (
        POSITION, "Started watching", "Stopped watching",
        "Number of times each moment was seen",
    ))


def group_retention_by_intervals(rows, annotations):
    """Return chronological interval groups and unassigned samples.

    Each group has an annotation dictionary and a samples list. All intervals
    use [start, end), including the final interval: endpoints are never extended
    or inferred from samples. Gaps and samples at the final end stay unassigned.
    Overlaps assign a sample only to the first interval sorted by (start, end).
    Inputs are not mutated; metadata and row dictionaries are copied unchanged.
    """
    groups = [
        {"annotation": dict(annotation), "samples": []}
        for annotation in sorted(annotations, key=lambda item: (item["start"], item["end"]))
    ]
    unassigned = []
    for row in sorted(rows, key=lambda item: item["timestamp_seconds"]):
        timestamp = row["timestamp_seconds"]
        for group in groups:
            annotation = group["annotation"]
            if annotation["start"] <= timestamp < annotation["end"]:
                group["samples"].append(dict(row))
                break
        else:
            unassigned.append(dict(row))
    return {"intervals": groups, "unassigned": unassigned}


def summarize_retention_intervals(interval_groups):
    """Summarize grouped['intervals'] without modifying annotations or rows.

    Groups and samples retain the chronological order supplied by
    group_retention_by_intervals(). The mean is an unweighted sample mean;
    change is last minus first, in percentage points, not a quality score.
    Invalid or nonfinite retention values raise ValueError rather than being
    skipped or replaced with zero. Empty intervals have None statistics.
    """
    summaries = []
    for group in interval_groups:
        values = [float(row["Absolute audience retention (%)"]) for row in group["samples"]]
        if any(not math.isfinite(value) for value in values):
            raise ValueError("Retention values must be finite numbers.")
        summaries.append({
            "annotation": dict(group["annotation"]),
            "sample_count": len(values),
            "mean_retention": math.fsum(values) / len(values) if values else None,
            "min_retention": min(values) if values else None,
            "max_retention": max(values) if values else None,
            "start_retention": values[0] if values else None,
            "end_retention": values[-1] if values else None,
            "retention_change": values[-1] - values[0] if values else None,
        })
    return summaries
