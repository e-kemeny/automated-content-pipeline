"""Compare frozen Fixed/V1 with V2; run only after synthetic tests."""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import runpy
from statistics import mean, median

from annotate import load_annotations
from dynamic_windows_v2 import build_dynamic_windows_v2
from evaluate_fixed_windows import evaluate_baselines
from evaluate_dynamic_windows import compare_boundaries, verify_frozen_results, format_report as format_v1
from evaluation_v2 import evaluate_windows


def evaluate_v2_pairs(pairs, audio, scenes, duration, annotations):
    results = []
    for pair in pairs:
        fixed = pair["fixed"]
        windows = build_dynamic_windows_v2(fixed["windows"], audio, scenes, duration)
        evaluation = evaluate_windows(windows, annotations, iou_threshold=0.5)
        ious = [m["iou"] for m in evaluation["matches"]]
        results.append(dict(fixed=fixed, v1=pair["dynamic"], v2=dict(windows=windows,
                       evaluation=evaluation, mean_iou=mean(ious) if ious else 0.0,
                       median_iou=median(ious) if ious else 0.0)))
    return results


def fallback_counts(windows):
    return Counter(w["boundary_diagnostics"][side]["reason"]
                   for w in windows for side in ("backward", "forward"))


def format_report(results, duration, hashes):
    lines = ["# Dynamic Windows V2: joint audio and scene boundaries", "",
        f"First-shot experiment on one already-edited Minecraft BedWars video ({duration:.6f}s), "
        "14 unchanged human intervals. Candidates and recomputed Fixed/V1 metrics were checked "
        "against both frozen reports. Neither prior report was modified.", "",
        "## Parameters frozen before evaluation", "",
        "- Search each side from 4 to 20 seconds away, at 1-second steps; maximum total 40s, minimum 8s.",
        "- At boundary b compare audio samples floor(b)-5 through floor(b)-1 with floor(b) through floor(b)+4. "
        "Use existing normalized audio scores floored at zero. Complete five-sample regions are required.",
        "- Inward region is toward the candidate; outward is away. Require inward mean > 0 and outward "
        "mean <= 0.60 * inward mean. A regional reduction allows brief internal dips.",
        "- Also require an existing normalized scene intensity >= 0.50 within +/-1s. Both conditions "
        "must coincide; select the nearest qualifying grid boundary independently on each side. "
        "No new scene detection or detector score changes.",
        "- No qualifying boundary: use candidate-10 on the left or candidate+5 on the right, clamped "
        "to video bounds. Missing audio or scenes cannot establish a boundary. Minimum padding is "
        "symmetric and shifted inside the video; shorter videos use available duration.",
        "- The 20s search gives longer context than V1; five-second means seek sustained reductions. "
        "The 40% reduction and half-max scene threshold are unvalidated first-shot choices. "
        "No labels or retention enter boundary generation; no parameters changed after evaluation.", "",
        "## Three-way results", "",
        "Mean/median include unmatched zeros. IoU >= 0.5 is an experimental reporting threshold, "
        "not a validated cutoff. Coverage is union-covered annotated time / annotated-union duration. "
        "Deltas use unrounded values; coverage differences are percentage points.", "",
        "| Detector | K | Metric | Fixed | V1 | V2 | V2-Fixed | V2-V1 |",
        "|---|---:|---|---:|---:|---:|---:|---:|"]
    for r in results:
        metrics = [
            ("Mean IoU", [r[k]["mean_iou"] for k in ("fixed", "v1", "v2")], 6, ""),
            ("Median IoU", [r[k]["median_iou"] for k in ("fixed", "v1", "v2")], 6, ""),
            ("IoU >= 0.5 count", [r[k]["evaluation"]["threshold_summary"]["at_or_above_threshold"]
                                  for k in ("fixed", "v1", "v2")], 0, ""),
            ("Coverage (%)", [100*r[k]["evaluation"]["overall_coverage"]["coverage_fraction"]
                              for k in ("fixed", "v1", "v2")], 6, " pp")]
        for label, (a, b, c), digits, unit in metrics:
            lines.append(f"| {r['fixed']['detector']} | {r['fixed']['k']} | {label} | "
                         f"{a:.{digits}f} | {b:.{digits}f} | {c:.{digits}f} | "
                         f"{c-a:+.{digits}f}{unit} | {c-b:+.{digits}f}{unit} |")
    for r in results:
        windows = r["v2"]["windows"]
        counts = fallback_counts(windows)
        lines += ["", f"## {r['fixed']['detector']} - Top {r['fixed']['k']}", "",
            "Candidate timestamps: " + ", ".join(str(w["second"]) for w in windows), "",
            f"Side decisions ({2*len(windows)} total): " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())), "",
            "| Candidate | V2 start/end | Duration | Backward reason | Forward reason | Minimum padded |",
            "|---:|---|---:|---|---|---|"]
        for w in windows:
            d = w["boundary_diagnostics"]
            lines.append(f"| {w['second']} | {w['start']:.6f}-{w['end']:.6f} | {w['duration']:.6f} | "
                         f"{d['backward']['reason']} | {d['forward']['reason']} | {d['minimum_enforced']} |")
        lines += ["", "Accepted boundary evidence:", ""]
        accepted = []
        for w in windows:
            for side in ("backward", "forward"):
                d = w["boundary_diagnostics"][side]
                if not d["fallback"]:
                    e = d["evidence"][-1]
                    accepted.append(f"- {w['second']}s {side}: boundary {e['boundary']:.6f}s; inward/outward "
                                    f"means {e['inward_mean']:.6f}/{e['outward_mean']:.6f}; "
                                    f"scene {e['scene_time']:.6f}s, intensity {e['scene_score']:.6f}.")
        lines += accepted or ["None; both sides use fallback for every candidate."]
        lines += ["", "| GT start/end | Type | Fixed covered s | V1 covered s | V2 covered s | V2 coverage |",
                  "|---|---|---:|---:|---:|---:|"]
        for a, b, c in zip(*(r[k]["evaluation"]["coverage"] for k in ("fixed", "v1", "v2"))):
            gt = c["annotation"]
            lines.append(f"| {gt['start']:g}-{gt['end']:g} | {gt['type']} | {a['covered_duration']:.6f} | "
                         f"{b['covered_duration']:.6f} | {c['covered_duration']:.6f} | {c['coverage_fraction']:.6%} |")
    unique = {w["second"]: w for r in results for w in r["v2"]["windows"]}
    lines += ["", "## Fallback and limitations", "",
        f"Across {len(unique)} unique candidates ({2*len(unique)} sides): " +
        ", ".join(f"{k}={v}" for k, v in sorted(fallback_counts(unique.values()).items())), "",
        "Repeated candidates across detector/K configurations are not independent observations. "
        "Audio/scene coincidences need not be semantic transitions. Regional averaging can miss boundaries; "
        "fallback equality is not evidence that the hypothesis works. Coverage depends on window duration. "
        "This single edited video cannot establish generalization or an overall winner.", "",
        "Run: python evaluate_dynamic_windows_v2.py after tests. The unchanged main.py regenerates normal "
        "production clips; no V2 clips are generated. Full search evidence and metrics: "
        "output/dynamic_window_v2.json (ignored). Previous reports stay frozen.", "",
        "## SHA-256 provenance", ""]
    lines += [f"- {name}: {value}" for name, value in hashes.items()]
    return "\n".join(lines) + "\n"


def main():
    repo = Path(__file__).resolve().parent
    names = ("results/fixed_window_v2_baseline.md", "results/dynamic_window_v1.md")
    frozen = {name: (repo/name).read_bytes() for name in names}
    cwd = Path.cwd()
    try:
        os.chdir(repo)
        state = runpy.run_path(str(repo/"main.py"), run_name="__main__")
    finally:
        os.chdir(cwd)
    duration = state["duration_seconds"]
    annotations = load_annotations(repo/"ground_truth_v2.json", duration)
    fixed = evaluate_baselines(state["audio_scores"], duration, annotations)
    verify_frozen_results(fixed, frozen[names[0]].decode("utf-8"))
    pairs = compare_boundaries(fixed, state["audio_scores"], duration, annotations)
    old_report = frozen[names[1]].decode("utf-8")
    for line in format_v1(pairs, duration, "", {}).splitlines():
        if line.startswith("| Audio") or line.startswith("Candidate timestamps:"):
            if line not in old_report:
                raise ValueError("V1 differs from frozen results; abort")
    results = evaluate_v2_pairs(pairs, state["audio_scores"], state["scene_scores"], duration, annotations)
    hashes = {}
    for name in (*names, "main.py", "motion.py", "evaluation.py", "evaluation_v2.py",
                 "windows.py", "dynamic_windows.py", "dynamic_windows_v2.py",
                 "evaluate_dynamic_windows_v2.py", "ground_truth_v2.json", "videos/my_recording.mp4"):
        with (repo/name).open("rb") as source:
            hashes[name] = hashlib.file_digest(source, "sha256").hexdigest()
    if any((repo/name).read_bytes() != data for name, data in frozen.items()):
        raise RuntimeError("Frozen report changed")
    (repo/"output/dynamic_window_v2.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    report = format_report(results, duration, hashes)
    (repo/"results/dynamic_window_v2.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
