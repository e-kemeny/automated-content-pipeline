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
