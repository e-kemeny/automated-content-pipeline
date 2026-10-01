"""Freeze fixed-window V2 results: python evaluate_fixed_windows.py.

Runs the existing main.py once, including its normal clip-generation side effects.
No detector logic is copied or modified.
"""

import hashlib
import os
from pathlib import Path
import runpy
from statistics import mean, median

from annotate import load_annotations
from evaluation import select_highlights
from evaluation_v2 import evaluate_windows
from windows import build_candidate_windows


def evaluate_baselines(candidates, video_duration, annotations):
    results = []
    for name, score_key in (("Audio-only", "score"), ("Audio + Scene", "highlight_score"),
                            ("Audio + Motion", "motion_highlight_score")):
        for limit in (5, 10):
            selected = select_highlights(candidates, score_key, limit=limit)
            windows = build_candidate_windows(selected, video_duration)
            evaluation = evaluate_windows(windows, annotations, iou_threshold=0.5)
            ious = [match["iou"] for match in evaluation["matches"]]
            results.append({"detector": name, "k": limit, "windows": windows,
                            "mean_iou": mean(ious) if ious else None,
                            "median_iou": median(ious) if ious else None,
                            "evaluation": evaluation})
    return results


def format_baseline(results, video_duration, hashes):
    def number(value):
        return "N/A" if value is None else f"{value:.6f}"

    lines = ["# Fixed-window Ground Truth V2 baseline", "", "## Experiment setup", "",
        f"Real source: `videos/my_recording.mp4`, duration **{video_duration:.6f} seconds**.",
        "One already-edited Minecraft BedWars video; 14 human-labeled semantic V2 intervals.",
        "Candidates come directly from the existing main.py run. Audio scoring, scene/motion "
        "signals, 70/30 weights, and +/-5s visual association remain unchanged.",
        "For each detector, the existing score ranking and greedy 15-second timestamp "
        "suppression select Top 5 and Top 10, then return chronological candidates.",
        "Fixed **[-10,+5] second** windows: start=max(0, second-10), "
        "end=min(video_duration, second+5). No dynamic cuts or window selection changes.",
        "", "IoU **0.5 is an experimental reporting threshold, not a validated cutoff**. "
        "Each prediction independently uses its highest positive GT IoU; ties use GT order. "
        "GT is not consumed. Mean/median include zero IoUs for unmatched predictions.",
        "Coverage counts the intersection of prediction union and annotated union, "
        "divided by annotated-union duration. Overlaps are not double-counted; gaps are excluded.",
        "", "## Summary", "",
        "| Detector | K | Mean best IoU | Median best IoU | IoU >= 0.5 | Covered / annotated seconds | Coverage |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for result in results:
        evaluation = result["evaluation"]
        coverage = evaluation["overall_coverage"]
        count = evaluation["threshold_summary"]["at_or_above_threshold"]
        lines.append(f"| {result['detector']} | {result['k']} | {number(result['mean_iou'])} | "
                     f"{number(result['median_iou'])} | {count}/{len(result['windows'])} | "
                     f"{coverage['covered_duration']:.6f} / {coverage['duration']:.6f} | "
                     f"{coverage['coverage_fraction']:.2%} |")
    for result in results:
        lines += ["", f"## {result['detector']} — Top {result['k']}", "",
                  "Selected timestamps (seconds): " + ", ".join(f"{w['second']:g}" for w in result['windows']),
                  "", "| Candidate (s) | Window start (s) | Window end (s) | Best GT interval (s) | Best IoU |",
                  "|---:|---:|---:|---|---:|"]
        for match in result["evaluation"]["matches"]:
            window, gt = match["prediction"], match["ground_truth"]
            label = f"{gt['start']:g}-{gt['end']:g}" if gt else "unmatched"
            lines.append(f"| {window['second']:g} | {window['start']:.6f} | {window['end']:.6f} | "
                         f"{label} | {match['iou']:.6f} |")
        lines += ["", "| GT interval (s) | Type | Description | Duration (s) | Covered (s) | Coverage |",
                  "|---|---|---|---:|---:|---:|"]
        for coverage in result["evaluation"]["coverage"]:
            gt = coverage["annotation"]
            description = gt["description"].replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {gt['start']:g}-{gt['end']:g} | {gt['type']} | {description} | "
                         f"{coverage['duration']:.6f} | {coverage['covered_duration']:.6f} | "
                         f"{coverage['coverage_fraction']:.2%} |")
    lines += ["", "## Reproduction and limitations", "",
              "Run `python evaluate_fixed_windows.py` from this checkout with FFmpeg/ffprobe "
              "and the original media available. It reruns main.py, regenerates normal clips, "
              "and replaces this report. Preserve this baseline in version control before later experiments.",
              "", "This is a descriptive baseline on one edited video, not evidence of generalization. "
              "Long or short annotations affect IoU; temporal coverage measures retained annotated time, "
              "not boundary accuracy. More windows can cover more time. These are separate measurements, "
              "not an overall quality score or a detector ranking. Retention is not used. "
              "No parameters were tuned after observing results.",
              "", "Source SHA-256 hashes (identify the exact assets/code used):", ""]
    lines += [f"- `{name}`: `{digest}`" for name, digest in hashes.items()]
    return "\n".join(lines) + "\n"


def main():
    repo = Path(__file__).resolve().parent
    original_directory = Path.cwd()
    try:
        os.chdir(repo)  # Existing main.py resolves its media paths from the CWD.
        state = runpy.run_path(str(repo / "main.py"), run_name="__main__")
    finally:
        os.chdir(original_directory)
    duration = state["duration_seconds"]
    annotations = load_annotations(repo / "ground_truth_v2.json", duration)
    results = evaluate_baselines(state["audio_scores"], duration, annotations)
    hashes = {}
    for name in ("videos/my_recording.mp4", "ground_truth_v2.json", "main.py", "motion.py",
                 "evaluation.py", "windows.py", "evaluation_v2.py", "evaluate_fixed_windows.py"):
        with (repo / name).open("rb") as source:
            hashes[name] = hashlib.file_digest(source, "sha256").hexdigest()
    report = format_baseline(results, duration, hashes)
    output = repo / "results" / "fixed_window_v2_baseline.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(report)
    print(f"Saved baseline: {output}")


if __name__ == "__main__":
    main()
