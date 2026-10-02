"""Run once with python evaluate_dynamic_windows.py; frozen baseline is read-only."""

import hashlib
import json
import os
from pathlib import Path
import runpy
from statistics import mean, median

from annotate import load_annotations
from dynamic_windows import build_dynamic_windows
from evaluate_fixed_windows import evaluate_baselines
from evaluation_v2 import evaluate_windows


def compare_boundaries(fixed_results, activity_rows, duration, annotations):
    pairs = []
    for fixed in fixed_results:
        # Reuse the already-selected candidate dictionaries; never reselect.
        dynamic = build_dynamic_windows(fixed["windows"], activity_rows, duration)
        evaluation = evaluate_windows(dynamic, annotations, iou_threshold=0.5)
        ious = [match["iou"] for match in evaluation["matches"]]
        pairs.append({"fixed": fixed, "dynamic": {
            "windows": dynamic, "evaluation": evaluation,
            "mean_iou": mean(ious) if ious else 0.0,
            "median_iou": median(ious) if ious else 0.0,
        }})
    return pairs


def verify_frozen_results(fixed_results, frozen_text):
    """Abort if recomputed fixed metrics or candidates differ from the saved run."""
    frozen_text = frozen_text.replace("\r\n", "\n")
    for result in fixed_results:
        coverage = result["evaluation"]["overall_coverage"]
        count = result["evaluation"]["threshold_summary"]["at_or_above_threshold"]
        expected = (f"| {result['detector']} | {result['k']} | {result['mean_iou']:.6f} | "
                    f"{result['median_iou']:.6f} | {count}/{len(result['windows'])} | "
                    f"{coverage['covered_duration']:.6f} / {coverage['duration']:.6f} | "
                    f"{coverage['coverage_fraction']:.2%} |")
        section = frozen_text.split(f"## {result['detector']} — Top {result['k']}\n", 1)[-1].split("\n## ", 1)[0]
        timestamps = "Selected timestamps (seconds): " + ", ".join(f"{w['second']:g}" for w in result['windows'])
        if expected not in frozen_text or timestamps not in section:
            raise ValueError("Fixed results differ from the frozen baseline; stop rather than tune")


def format_report(pairs, duration, baseline_hash, hashes):
    lines = ["# Dynamic window V1: first-shot boundary experiment", "",
        f"One already-edited Minecraft BedWars video, {duration:.6f}s; 14 unchanged V2 annotations.",
        "Fixed results were recomputed and verified against `results/fixed_window_v2_baseline.md`, "
        "which was not modified. Every fixed/dynamic pair uses identical selected timestamps and score metadata.",
        "", "## Algorithm frozen before evaluation", "",
        "- Signal: existing per-second `normalized_score` from audio candidates, floored at zero. "
        "This is the existing volume-plus-spike score, not raw loudness; detector scores are unchanged.",
        "- Resolution: 1s; sample at floor(time). Local baseline: median within +/-15s of the candidate.",
        "- Quiet threshold = baseline + 0.25 * max(0, candidate activity - baseline). "
        "The relative rule seeks a return toward local activity; it is not a learned cutoff.",
        "- Expand each side independently, at most 15s per side (30s total). "
        "Two consecutive samples <= threshold stop expansion at the inner edge of that quiet run. "
        "One quiet sample is bridged; missing signal stops at the last examined boundary.",
        "- Minimum 8s retains brief context: pad symmetrically and shift padding inward at video edges. "
        "If the video is shorter, use its available duration. All windows contain their candidate and are clamped.",
        "- The 30s cap bounds context, 1s steps match the existing signal, and two quiet samples avoid "
        "terminating on a single dip. Parameters were declared before V2 evaluation and were not tuned.",
        "- No GT labels or retention enter boundary generation. Production clipping is unchanged; "
        "the runner reruns main.py once and regenerates its normal fixed clips only.",
        "", "## Fixed versus dynamic", "",
        "IoU >= 0.5 is an experimental reporting threshold, not a validated cutoff. "
        "Mean/median include unmatched zeros. Coverage uses unions of predicted and annotated time. "
        "Deltas are dynamic minus fixed; coverage deltas are percentage points.", "",
        "| Detector | K | Metric | Fixed | Dynamic | Delta |",
        "|---|---:|---|---:|---:|---:|"]
    for pair in pairs:
        fixed, dynamic = pair["fixed"], pair["dynamic"]
        for label, key in (("Mean IoU", "mean_iou"), ("Median IoU", "median_iou")):
            a, b = fixed[key], dynamic[key]
            lines.append(f"| {fixed['detector']} | {fixed['k']} | {label} | {a:.6f} | {b:.6f} | {b-a:+.6f} |")
        a, b = [r["evaluation"]["threshold_summary"]["at_or_above_threshold"] for r in (fixed, dynamic)]
        lines.append(f"| {fixed['detector']} | {fixed['k']} | IoU >= 0.5 count | {a} | {b} | {b-a:+d} |")
        a, b = [r["evaluation"]["overall_coverage"]["coverage_fraction"] for r in (fixed, dynamic)]
        lines.append(f"| {fixed['detector']} | {fixed['k']} | Coverage | {a:.2%} | {b:.2%} | {(b-a)*100:+.2f} pp |")
    for pair in pairs:
        fixed, dynamic = pair["fixed"], pair["dynamic"]
        lines += ["", f"## {fixed['detector']} — Top {fixed['k']}", "",
            "Candidate timestamps: " + ", ".join(str(w['second']) for w in dynamic['windows']), "",
            "| Candidate | Fixed start/end | Dynamic start/end | Duration | Baseline / threshold | Left / right stop | Minimum padded | Best IoU |",
            "|---:|---|---|---:|---|---|---|---:|"]
        for old, match in zip(fixed['windows'], dynamic['evaluation']['matches']):
            window = match['prediction']
            d = window['boundary_diagnostics']
            lines.append(f"| {window['second']} | {old['start']:.3f}-{old['end']:.3f} | "
                f"{window['start']:.3f}-{window['end']:.3f} | {window['duration']:.3f} | "
                f"{d['baseline']:.6f} / {d['quiet_threshold']:.6f} | "
                f"{d['left_stop']} / {d['right_stop']} | {d['minimum_enforced']} | {match['iou']:.6f} |")
        lines += ["", "| GT start/end | Type | Fixed covered seconds | Dynamic covered seconds | Dynamic coverage |",
                  "|---|---|---:|---:|---:|"]
        for old, coverage in zip(fixed['evaluation']['coverage'], dynamic['evaluation']['coverage']):
            gt = coverage['annotation']
            lines.append(f"| {gt['start']:g}-{gt['end']:g} | {gt['type']} | "
                         f"{old['covered_duration']:.6f} | {coverage['covered_duration']:.6f} | {coverage['coverage_fraction']:.2%} |")
    lines += ["", "## Interpretation limits", "",
        "These measurements describe boundary changes, not a detector ranking or overall quality score. "
        "Increased coverage can follow longer windows without better boundaries. IoU depends on annotation length. "
        "The audio score can reflect music or commentary; a locally constant signal is quiet under this relative rule. "
        "The first five audio seconds are unavailable; minimum padding can include quiet or missing regions. "
        "This experiment cannot establish generalization or guarantee complete gameplay sequences.",
        "", "Reproduce with `python evaluate_dynamic_windows.py`. The runner saves detailed numerical "
        "boundary traces to ignored `output/dynamic_window_v1.json` and overwrites this experimental report, "
        "never the frozen fixed report.", "", f"Frozen baseline SHA-256: `{baseline_hash}`", "", "Source SHA-256:", ""]
    lines += [f"- `{name}`: `{value}`" for name, value in hashes.items()]
    return "\n".join(lines) + "\n"


def main():
    repo = Path(__file__).resolve().parent
    frozen_path = repo / "results/fixed_window_v2_baseline.md"
    frozen_bytes = frozen_path.read_bytes()
    original_directory = Path.cwd()
    try:
        os.chdir(repo)
        state = runpy.run_path(str(repo / "main.py"), run_name="__main__")
    finally:
        os.chdir(original_directory)
    duration = state["duration_seconds"]
    annotations = load_annotations(repo / "ground_truth_v2.json", duration)
    fixed = evaluate_baselines(state["audio_scores"], duration, annotations)
    verify_frozen_results(fixed, frozen_bytes.decode("utf-8"))
    pairs = compare_boundaries(fixed, state["audio_scores"], duration, annotations)
    hashes = {}
    for name in ("main.py", "motion.py", "evaluation.py", "evaluation_v2.py", "windows.py",
                 "dynamic_windows.py", "evaluate_dynamic_windows.py", "ground_truth_v2.json", "videos/my_recording.mp4"):
        with (repo / name).open("rb") as source:
            hashes[name] = hashlib.file_digest(source, "sha256").hexdigest()
    report = format_report(pairs, duration, hashlib.sha256(frozen_bytes).hexdigest(), hashes)
    if frozen_path.read_bytes() != frozen_bytes:
        raise RuntimeError("Frozen baseline changed during experiment")
    (repo / "output/dynamic_window_v1.json").write_text(json.dumps(pairs, indent=2), encoding="utf-8")
    (repo / "results/dynamic_window_v1.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
