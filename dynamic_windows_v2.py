"""First-shot joint audio/scene boundary hypothesis; no labels or retention."""
import math
from statistics import mean

SEARCH_RADIUS = 20       # Longer context than V1; maximum total duration 40s.
MIN_DURATION = 8.0
STEP_SECONDS = 1
CONTEXT_SECONDS = 5      # Regional means bridge brief internal audio dips.
AUDIO_RATIO = 0.60       # Require a 40% outward reduction, not absolute silence.
SCENE_THRESHOLD = 0.50   # Existing max-normalized scene intensity.
SCENE_TOLERANCE = 1.0
FALLBACK_BEFORE = 10.0
FALLBACK_AFTER = 5.0


def build_dynamic_windows_v2(candidates, activity_rows, scene_rows, video_duration):
    """Preserve candidate order/metadata; choose nearest joint boundary per side.

    At boundary b, compare floor(b)-5..floor(b)-1 with floor(b)..floor(b)+4.
    Inward means toward the candidate; outward means away. Both complete
    five-sample regions are required. A scene must be within +/-1s of b.
    Search begins 4s away, preserving minimum context. If none qualifies,
    retain that side's fixed boundary; missing evidence never forces a cut.
    """
    duration = float(video_duration)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Video duration must be positive and finite")
    signal = {}
    for row in activity_rows:
        t, value = float(row["second"]), float(row["normalized_score"])
        if not math.isfinite(t) or not t.is_integer() or not 0 <= t < duration:
            raise ValueError("Audio seconds must be integers inside the video")
        if not math.isfinite(value) or t in signal:
            raise ValueError("Audio scores must be finite with unique seconds")
        signal[int(t)] = max(0.0, value)
    scenes = []
    for row in scene_rows:
        t, value = float(row["time"]), float(row["normalized_score"])
        if not math.isfinite(t) or not 0 <= t <= duration or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("Scene times/scores must be finite and in range")
        scenes.append((t, value))
    scenes.sort()
    windows = []
    for candidate in candidates:
        center = float(candidate["second"])
        if not math.isfinite(center) or not 0 <= center <= duration:
            raise ValueError("Candidate must be finite and inside video")

        def search(direction):
            evidence = []
            for distance in range(int(MIN_DURATION / 2), SEARCH_RADIUS + 1, STEP_SECONDS):
                boundary = center + direction * distance
                if not 0 < boundary < duration:
                    break
                second = math.floor(boundary)
                before = [signal.get(t) for t in range(second - CONTEXT_SECONDS, second)]
                after = [signal.get(t) for t in range(second, second + CONTEXT_SECONDS)]
                inward, outward = (after, before) if direction < 0 else (before, after)
                complete = None not in inward + outward
                inner = mean(inward) if complete else None
                outer = mean(outward) if complete else None
                nearby = [(t, score) for t, score in scenes if abs(t - boundary) <= SCENE_TOLERANCE]
                strongest = max(nearby, key=lambda item: (item[1], -item[0]), default=None)
                audio_ok = complete and inner > 0 and outer <= AUDIO_RATIO * inner
                scene_ok = strongest is not None and strongest[1] >= SCENE_THRESHOLD
                evidence.append(dict(boundary=boundary, inward_mean=inner, outward_mean=outer,
                                     scene_time=strongest[0] if strongest else None,
                                     scene_score=strongest[1] if strongest else None,
                                     audio_ok=audio_ok, scene_ok=scene_ok))
                if audio_ok and scene_ok:
                    return boundary, dict(reason="audio_and_scene", fallback=False, evidence=evidence)
            fallback = max(0.0, center - FALLBACK_BEFORE) if direction < 0 else min(duration, center + FALLBACK_AFTER)
            if not evidence or all(e["inward_mean"] is None for e in evidence):
                reason = "fallback_insufficient_audio_context"
            elif not any(e["scene_ok"] for e in evidence):
                reason = "fallback_no_strong_scene"
            else:
                reason = "fallback_no_joint_boundary"
            return fallback, dict(reason=reason, fallback=True, evidence=evidence)

        start, backward = search(-1)
        end, forward = search(1)
        raw_start, raw_end = start, end
        minimum = min(MIN_DURATION, duration)
        if end - start < minimum:
            start = max(0.0, min(start - (minimum - (end - start)) / 2, duration - minimum))
            end = min(duration, start + minimum)
            if end - start < minimum:
                if end < duration:
                    end = min(duration, math.nextafter(end, math.inf))
                else:
                    start = max(0.0, math.nextafter(start, -math.inf))
        windows.append(dict(candidate, start=start, end=end, duration=end - start,
                            boundary_diagnostics=dict(backward=backward, forward=forward,
                                raw_start=raw_start, raw_end=raw_end,
                                minimum_enforced=(end - start > raw_end - raw_start))))
    return windows
