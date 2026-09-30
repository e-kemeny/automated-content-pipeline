"""Descriptive V2 interval evaluation, independent of V1 point metrics."""

import math

from windows import temporal_overlap, temporal_iou


def _interval_union(intervals):
    """Return disjoint ranges for coverage only; never change candidate windows."""
    ranges = []
    for interval in intervals:
        temporal_overlap(interval, interval)  # Reuse bounds validation.
        start, end = float(interval["start"]), float(interval["end"])
        if end > start:
            ranges.append((start, end))
    merged = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1]["end"]:
            merged[-1]["end"] = max(merged[-1]["end"], end)
        else:
            merged.append({"start": start, "end": end})
    return merged


def evaluate_windows(predictions, ground_truth, iou_threshold=0.5):
    """Return raw best matches, per-GT/overall coverage, and separate counts.

    Inputs are dictionaries with start/end; GT metadata (type, description, etc.)
    and prediction metadata are preserved in copies. Input order is retained.
    Each prediction independently selects the highest positive IoU; ties keep
    the first GT in input order. GT is never consumed. Touching endpoints and
    zero-duration windows are unmatched under the windows.py [start, end) rules.

    Coverage = duration(prediction union intersect GT) / duration(GT).
    Overall coverage uses the union of GT as well, avoiding double-counting
    overlapping annotations. Empty/zero-duration denominators yield 0.0.

    Threshold counts require positive overlap and IoU >= iou_threshold; they
    are not V1 precision/recall. 0.5 is an API default, not a validated cutoff.
    Pass None to omit threshold counts. No ranking or boundary changes occur.
    """
    if iou_threshold is not None:
        iou_threshold = float(iou_threshold)
        if not math.isfinite(iou_threshold) or not 0 <= iou_threshold <= 1:
            raise ValueError("IoU threshold must be between 0 and 1, or None.")
    predictions, ground_truth = list(predictions), list(ground_truth)
    predicted_union = _interval_union(predictions)
    gt_union = _interval_union(ground_truth)
    matches = []
    for prediction in predictions:
        best_gt = None
        best_iou = 0.0
        overlap = 0.0
        for annotation in ground_truth:
            iou = temporal_iou(prediction, annotation)
            if iou > best_iou:
                best_gt = annotation
                best_iou = iou
                overlap = temporal_overlap(prediction, annotation)
        matches.append({
            "prediction": dict(prediction),
            "ground_truth": dict(best_gt) if best_gt is not None else None,
            "overlap_duration": overlap,
            "iou": best_iou,
        })

    coverage = []
    for annotation in ground_truth:
        duration = float(annotation["end"]) - float(annotation["start"])
        covered = sum(temporal_overlap(window, annotation) for window in predicted_union)
        coverage.append({
            "annotation": dict(annotation),
            "duration": duration,
            "covered_duration": covered,
            "coverage_fraction": covered / duration if duration else 0.0,
        })
    total_duration = sum(interval["end"] - interval["start"] for interval in gt_union)
    total_covered = sum(temporal_overlap(window, interval)
                        for window in predicted_union for interval in gt_union)
    threshold_summary = None
    if iou_threshold is not None:
        reached = sum(match["ground_truth"] is not None and match["iou"] >= iou_threshold
                      for match in matches)
        threshold_summary = {
            "iou_threshold": iou_threshold,
            "prediction_count": len(matches),
            "at_or_above_threshold": reached,
            "below_threshold_or_unmatched": len(matches) - reached,
        }
    return {
        "matches": matches,
        "coverage": coverage,
        "overall_coverage": {
            "duration": total_duration,
            "covered_duration": total_covered,
            "coverage_fraction": total_covered / total_duration if total_duration else 0.0,
        },
        "threshold_summary": threshold_summary,
    }
