"""Selection and event-level evaluation for the current BedWars example."""

# Event times, not clip starts. Each tuple is one inclusive ground-truth region.
GROUND_TRUTH = [
    (24, 24), (34, 34), (43, 43), (52, 52), (65, 68), (79, 79),
    (98, 98), (115, 115), (152, 152), (164, 164), (194, 194),
    (206, 206), (225, 225),
]


def select_highlights(candidates, score_key, limit=5):
    """Keep up to limit strongest events, at least 15 seconds apart."""
    ranked = sorted(candidates, key=lambda item: item[score_key], reverse=True)
    selected = []
    for item in ranked:
        if all(abs(item["second"] - other["second"]) >= 15 for other in selected):
            selected.append(item)
            if len(selected) == limit:
                break
    return sorted(selected, key=lambda item: item["second"])


def evaluate_predictions(predictions, ground_truth, tolerance=5):
    """Match chronological predictions to the earliest-ending eligible region.

    Bounds are inclusive: (65, 68) accepts 60 through 73 at tolerance 5.
    Removing matched regions prevents duplicate credit. Ties use region start.
    """
    unmatched = sorted(ground_truth, key=lambda region: (region[1], region[0]))
    matches = []
    for second in sorted(predictions):
        match = None
        for region in unmatched:
            start, end = region
            if start - tolerance <= second <= end + tolerance:
                match = region
                break
        if match is not None:
            unmatched.remove(match)
        matches.append((second, match))

    count = len(matches)
    true_positives = sum(region is not None for _, region in matches)
    precision = true_positives / count if count else 0.0
    recall = true_positives / len(ground_truth) if ground_truth else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "predictions": count,
        "true_positives": true_positives,
        "false_positives": count - true_positives,
        "false_negatives": len(unmatched),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "matches": matches,
        "unmatched": unmatched,
    }


def print_evaluation(name, result, show_diagnostics=False):
    def label(region):
        start, end = region
        return f"{start}s" if start == end else f"{start}-{end}s"

    print(f"\n{name} evaluation (tolerance: +/-5s)")
    if show_diagnostics:
        timestamps = ", ".join(f"{second}s" for second, _ in result["matches"])
        matched = [label(region) for _, region in result["matches"] if region is not None]
        print("  Selected timestamps: " + (timestamps or "none"))
        print("  Matched ground truth: " + (", ".join(matched) or "none"))
    for second, region in result["matches"]:
        if region is None:
            print(f"  Prediction {second}s -> no matching ground truth -> MISS")
        else:
            print(f"  Prediction {second}s -> Ground truth {label(region)} -> HIT")
    print("  Unmatched ground truth: " + (", ".join(map(label, result["unmatched"])) or "none"))
    print(
        f"  Predictions: {result['predictions']} | TP: {result['true_positives']}"
        f" | FP: {result['false_positives']} | FN: {result['false_negatives']}"
    )
    print(
        f"  Precision: {result['precision']:.4f} | Recall: {result['recall']:.4f}"
        f" | F1: {result['f1']:.4f}"
    )
