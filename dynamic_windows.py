"""First-shot audio boundary experiment. Parameters frozen before V2 evaluation.

Uses existing normalized audio scores (not new detector scores), floored at zero.
No annotations, retention, ranking, or selection are used here.
"""

import math
from statistics import median

MIN_DURATION = 8.0       # Retain brief context even if the signal immediately drops.
MAX_DURATION = 30.0      # Bound expansion to 15 seconds per side.
STEP_SECONDS = 1.0       # Match the existing audio signal resolution.
BASELINE_RADIUS = 15.0   # Local median over the same neighborhood as the search.
RELATIVE_THRESHOLD = 0.25  # Stop toward baseline, not only at absolute silence.
QUIET_SAMPLES = 2        # Bridge a single quiet second.


def build_dynamic_windows(candidates, activity_rows, video_duration):
    """Copy candidates in order, adding start/end/duration and boundary diagnostics.

    Activity rows use second and normalized_score, as returned by main.py.
    Samples at floor(t) represent t's second. Missing samples stop expansion.
    Minimum padding may cross a detected quiet boundary; this is recorded.
    For videos shorter than MIN_DURATION, the available video is the minimum.
    The candidate stays within the closed start/end bounds, including video end.
    """
    duration = float(video_duration)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Video duration must be positive and finite")
    signal = {}
    for row in activity_rows:
        second, value = float(row["second"]), float(row["normalized_score"])
        if not math.isfinite(second) or second < 0 or second >= duration or not second.is_integer():
            raise ValueError("Activity seconds must be integer seconds inside the video")
        if not math.isfinite(value) or second in signal:
            raise ValueError("Activity must have unique seconds and finite scores")
        signal[int(second)] = max(0.0, value)
    windows = []
    for candidate in candidates:
        center = float(candidate["second"])
        if not math.isfinite(center) or not 0 <= center <= duration:
            raise ValueError("Candidate must be finite and inside the video")
        local = [value for second, value in signal.items() if abs(second - center) <= BASELINE_RADIUS]
        baseline = median(local) if local else 0.0
        activity = signal.get(min(math.floor(center), math.ceil(duration) - 1), 0.0)
        threshold = baseline + RELATIVE_THRESHOLD * max(0.0, activity - baseline)

        def expand(direction):
            limit = max(0.0, center - MAX_DURATION / 2) if direction < 0 else min(duration, center + MAX_DURATION / 2)
            position = center
            quiet_count = 0
            quiet_inner = center
            trace = []
            while position != limit:
                target = max(limit, position - STEP_SECONDS) if direction < 0 else min(limit, position + STEP_SECONDS)
                if target in (0.0, duration):
                    return target, "video_boundary", trace
                value = signal.get(math.floor(target))
                if value is None:
                    return position, "missing_signal", trace
                trace.append({"time": target, "activity": value})
                if value <= threshold:
                    if quiet_count == 0:
                        quiet_inner = position
                    quiet_count += 1
                    if quiet_count == QUIET_SAMPLES:
                        return quiet_inner, "quiet_region", trace
                else:
                    quiet_count = 0
                position = target
            reason = "video_boundary" if limit in (0.0, duration) else "maximum_duration"
            return position, reason, trace

        start, left_reason, left_trace = expand(-1)
        end, right_reason, right_trace = expand(1)
        raw_start, raw_end = start, end
        minimum = min(MIN_DURATION, duration)
        if end - start < minimum:
            padding = (minimum - (end - start)) / 2
            start, end = start - padding, end + padding
            if start < 0:
                end -= start
                start = 0.0
            if end > duration:
                start -= end - duration
                end = duration
        # Round outward if subtraction leaves the minimum one float step short.
        if end - start < minimum:
            if end < duration:
                end = min(duration, math.nextafter(start + minimum, math.inf))
            else:
                start = max(0.0, math.nextafter(end - minimum, -math.inf))
        windows.append(dict(candidate, start=start, end=end, duration=end - start,
                            boundary_diagnostics={
                                "baseline": baseline, "candidate_activity": activity,
                                "quiet_threshold": threshold,
                                "left_stop": left_reason, "right_stop": right_reason,
                                "raw_start": raw_start, "raw_end": raw_end,
                                "minimum_enforced": end - start > raw_end - raw_start,
                                "left_trace": left_trace, "right_trace": right_trace,
                            }))
    return windows
