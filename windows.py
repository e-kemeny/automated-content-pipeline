"""Temporal candidate representation only; no ranking, selection, or merging."""

import math


def build_candidate_windows(candidates, video_duration, seconds_before=10, seconds_after=5):
    """Copy point candidates in input order and add start, end, and duration.

    Preserve second and score metadata. The three derived window fields replace
    any existing fields of those names. Inputs are not mutated. Reject nonfinite
    values, nonpositive video duration, negative padding, and timestamps outside
    [0, video_duration]. Zero padding is allowed, including zero-length windows.
    """
    video_duration = float(video_duration)
    seconds_before, seconds_after = float(seconds_before), float(seconds_after)
    if not math.isfinite(video_duration) or video_duration <= 0:
        raise ValueError("Video duration must be positive and finite.")
    if any(not math.isfinite(value) or value < 0 for value in (seconds_before, seconds_after)):
        raise ValueError("Window padding must be nonnegative and finite.")
    windows = []
    for candidate in candidates:
        second = float(candidate["second"])
        if not math.isfinite(second) or not 0 <= second <= video_duration:
            raise ValueError("Candidate timestamp must be finite and inside the video.")
        start = max(0.0, second - seconds_before)
        end = min(video_duration, second + seconds_after)
        windows.append(dict(candidate, start=start, end=end, duration=end - start))
    return windows


def _interval_bounds(interval):
    start, end = float(interval["start"]), float(interval["end"])
    if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end < start:
        raise ValueError("Interval bounds must be finite with 0 <= start <= end.")
    return start, end


def temporal_overlap(first, second):
    """Intersection duration in seconds for dictionaries with start/end fields.

    Intervals use [start, end); touching endpoints have zero overlap.
    """
    first_start, first_end = _interval_bounds(first)
    second_start, second_end = _interval_bounds(second)
    return max(0.0, min(first_end, second_end) - max(first_start, second_start))


def temporal_iou(first, second):
    """Intersection / union duration; zero for no overlap or zero-length union."""
    first_start, first_end = _interval_bounds(first)
    second_start, second_end = _interval_bounds(second)
    intersection = temporal_overlap(first, second)
    union = (first_end - first_start) + (second_end - second_start) - intersection
    return intersection / union if union else 0.0
