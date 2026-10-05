"""Descriptive comparison only; reads saved inference, never runs the model."""
import argparse
from collections import Counter
import json
from pathlib import Path

from annotate import load_annotations
from evaluation_v2 import evaluate_windows
from semantic_events import EVENT_TYPES, associate_events
from semantic_clip import MODEL_ID, PROMPTS, timeline_to_events, timeline_runs
from windows import temporal_overlap


def frozen_candidates(text):
    """Read actual selections from the frozen artifact, without rerunning detectors."""
    groups = {}
    section = None
    for line in text.splitlines():
        if line.startswith("## ") and " — Top " in line:
            section = line[3:]
        elif line.startswith("Selected timestamps (seconds): ") and section:
            groups[section] = [float(t) for t in line.split(": ", 1)[1].split(", ")]
    if len(groups) != 6 or any(len(v) != int(k.rsplit(" ", 1)[1]) for k, v in groups.items()):
        raise ValueError("Expected the six frozen detector/K selections")
    return groups


def describe(events, annotations, candidates):
    kinds = list(dict.fromkeys([a["type"] for a in annotations]))
    counts = Counter(e["event_type"] for e in events)
    gt_counts = Counter(a["type"] for a in annotations)
    coverage = {}
    matrix = {}
    for kind in kinds:
        gt = [a for a in annotations if a["type"] == kind]
        coverage[kind] = evaluate_windows([e for e in events if e["event_type"] == kind], gt)["overall_coverage"]
        matrix[kind] = {label: sum(temporal_overlap(e, a) for e in events
                                   if e["event_type"] == label for a in gt) for label in EVENT_TYPES}
    associations = {str(t): associate_events(events, {"second": t}, radius=5)
                    for t in sorted({t for times in candidates.values() for t in times})}
    return dict(event_counts=dict(counts), gt_counts=dict(gt_counts), same_type_coverage=coverage,
                overlap_seconds=matrix, candidates=candidates, associations=associations)


def report(artifact, events, annotations, candidates):
    data = describe(events, annotations, candidates)
    lines = ["# CLIP semantic V1: first pretrained semantic experiment", "",
        f"Model: {MODEL_ID}; revision: {artifact['model_revision']}.",
        f"Device: {artifact['device']} ({artifact['hardware']}); PyTorch {artifact['torch_version']}; "
        f"Transformers {artifact['transformers_version']}; runtime including setup: {artifact['runtime_seconds']:.2f}s.",
        f"Video: {artifact['duration']:.6f}s; SHA-256: {artifact['video_sha256']}.",
        "", "## Frozen protocol", "",
        "1 frame/s on the 0,1,2,... < duration grid, using FFmpeg fps=1:start_time=0:round=up. "
        "Timestamps describe that resampled grid, not exact original frame PTS. No labels influence sampling.",
        "Argmax across these seven prompts (ties use listed order); preserve all scaled CLIP logits as "
        "similarity and their seven-way softmax as zero_shot_score:", ""]
    lines += [f"- {k}: {v}" for k, v in PROMPTS.items()]
    lines += ["", "Each sample represents [t,min(t+1,duration)). Consecutive equal labels merge; neutral "
        "runs produce no event. No threshold, smoothing, or minimum duration. The interface's required "
        "confidence stores mean winning zero_shot_score, explicitly marked uncalibrated in metadata; "
        "underlying frame evidence is preserved.", "", "## Counts and same-type GT coverage", "",
        "| Type | Predicted events | GT intervals | Same-type covered / GT seconds |",
        "|---|---:|---:|---|"]
    for kind in dict.fromkeys([*EVENT_TYPES, *data["gt_counts"]]):
        c = data["same_type_coverage"].get(kind)
        coverage = f"{c['covered_duration']:.6f} / {c['duration']:.6f} ({c['coverage_fraction']:.2%})" if c else "N/A (no GT intervals)"
        lines.append(f"| {kind} | {data['event_counts'].get(kind,0)} | {data['gt_counts'].get(kind,0)} | {coverage} |")
    lines += ["", "## Temporal overlap matrix (seconds)", "",
              "Rows are broad GT sequences; columns are predicted frame-event types. "
              "Off-diagonal overlap is descriptive, not necessarily a misclassification. "
              "Intro has no prompt counterpart; kill/death may occur within GT combat.",
              "", "| GT type | " + " | ".join(EVENT_TYPES) + " |", "|---|" + "---:|"*len(EVENT_TYPES)]
    for kind, values in data["overlap_seconds"].items():
        lines.append(f"| {kind} | " + " | ".join(f"{values[k]:.6f}" for k in EVENT_TYPES) + " |")
    frame_counts = Counter(row["label"] for row in artifact["rows"])
    lines += ["", "## Observed label patterns", "",
              f"{len(artifact['rows'])} sampled frames produced {len(events)} non-neutral event runs. "
              "Frame winners: " + ", ".join(f"{k}={frame_counts.get(k, 0)}" for k in PROMPTS) + ".",
              "Short alternating runs describe label instability, not verified gameplay events."]
    for kind, values in data["overlap_seconds"].items():
        other = [(label, seconds) for label, seconds in values.items() if label != kind and seconds > 0]
        if other:
            label, seconds = max(other, key=lambda item: item[1])
            lines.append(f"- Within GT {kind}, the largest different-label overlap is {label}: "
                         f"{seconds:.6f}s. This is a mismatch diagnostic, not proof of frame-level error.")
    lines += ["", "## Predicted timeline (neutral included)", "", "| Start | End | Label | Samples |",
              "|---:|---:|---|---:|"]
    for run in timeline_runs(artifact["rows"], artifact["duration"]):
        lines.append(f"| {run['start']:.3f} | {run['end']:.3f} | {run['label']} | {len(run['samples'])} |")
    lines += ["", "## Frozen candidate diagnostics", "", "Point association, inclusive 5-second distance "
              "to event extent. Overlap and additional nearby events are separate. No score changes.", ""]
    lines += [f"- {name}: " + ", ".join(f"{t:g}" for t in times) for name, times in candidates.items()]
    lines += ["", "| Candidate | Overlapping events | Additional nearby events | Max relative evidence by type |",
              "|---:|---|---|---|"]
    for timestamp, association in data["associations"].items():
        def labels(key):
            return ", ".join(f"{e['event_type']} [{e['start']:g},{e['end']:g})" for e in association[key]) or "none"
        scores = ", ".join(f"{k}={v:.4f}" for k,v in association["max_confidence_by_type"].items()) or "none"
        lines.append(f"| {timestamp} | {labels('overlapping_events')} | {labels('nearby_events')} | {scores} |")
    lines += ["", "## Interpretation limits", "",
        "Pretrained by OpenAI, not trained or fine-tuned by this project. CLIP is a frame-level image-text "
        "model, not true video understanding. Zero-shot scores are relative similarities, not calibrated "
        "probabilities or factual confidence. A forced seven-way choice is not reliable event verification. "
        "Broad human intervals and frame events have different granularity; no conventional accuracy is claimed. "
        "This is one already-edited Minecraft video, with no generalization claim. No prompts, sampling, "
        "conversion, ranking, or clipping were tuned against these annotations.",
        "", "Reference: https://huggingface.co/docs/transformers/en/model_doc/clip",
        "", "Reproduce inference: python semantic_clip.py (refuses to overwrite existing results).",
        "Regenerate this report without inference: python evaluate_semantic_clip.py.",
        "Raw artifacts: output/clip_semantic_timeline.json and output/clip_semantic_events.json (ignored).",
        "Install optional dependencies with python -m pip install -r requirements-clip.txt. This run used "
        "output/clip_env/Scripts/python.exe, an isolated environment inheriting the existing CPU PyTorch. "
        "CUDA was unavailable in that build despite an NVIDIA GPU being installed. Model cache and frames "
        "are under output/. The downloader used ordinary HTTP because optional hf_xet was absent."]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeline", type=Path, default=Path("output/clip_semantic_timeline.json"))
    parser.add_argument("--annotations", type=Path, default=Path("ground_truth_v2.json"))
    parser.add_argument("--baseline", type=Path, default=Path("results/fixed_window_v2_baseline.md"))
    parser.add_argument("--report", type=Path, default=Path("results/clip_semantic_v1.md"))
    args = parser.parse_args()
    artifact = json.loads(args.timeline.read_text(encoding="utf-8"))
    if artifact["model_id"] != MODEL_ID or artifact["prompts"] != PROMPTS or artifact["sample_interval_seconds"] != 1:
        raise ValueError("Timeline is not the frozen V1 protocol")
    events = timeline_to_events(artifact["rows"], artifact["duration"])
    annotations = load_annotations(args.annotations, artifact["duration"])
    candidates = frozen_candidates(args.baseline.read_text(encoding="utf-8"))
    text = report(artifact, events, annotations, candidates)
    args.report.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
