"""Three-way descriptive comparison; no inference and no ranking changes."""
import json
from pathlib import Path

from annotate import load_annotations
from evaluate_semantic_clip import describe, frozen_candidates
from multiframe_semantics import MODEL_ID, MODEL_REVISION, PROMPT, predictions_to_events
from semantic_events import EVENT_TYPES, load_events
from temporal_semantics import stability_metrics
from semantic_clip import write_json


def project_to_grid(predictions, timestamps):
    """For comparable stability sampling only, assign window labels to raw 1 FPS grid."""
    return [dict(timestamp=t,label=next((p["label"] for p in predictions if p["start"] <= t < p["end"]),None))
            for t in timestamps]


def compare(raw, temporal, multi, raw_events, temporal_events, annotations, candidates):
    multi_events = predictions_to_events(multi["predictions"])
    grid = project_to_grid(multi["predictions"],[r["timestamp"] for r in raw["rows"]])
    sets = [(raw["rows"],raw_events),(temporal["rows"],temporal_events),(grid,multi_events)]
    return {name: dict(stability=stability_metrics(rows,events), diagnostics=describe(events,annotations,candidates))
            for name,(rows,events) in zip(("Raw CLIP","Temporal CLIP","Multiframe"),sets)}


def format_report(multi, comparisons):
    comparisons = {name: comparisons[name] for name in ("Raw CLIP", "Temporal CLIP", "Multiframe")}
    invalid = sum(p["label"] is None for p in multi["predictions"])
    outcome = ("All responses failed the frozen label format. No semantic events were accepted. "
               "Zero coverage is an output-contract failure, not evidence that gameplay events were absent. "
               "The 1.0 adjacent-state fraction is repeated INVALID state, not semantic stability. "
               "This run cannot establish whether multiframe context improves semantic correctness."
               if invalid == len(multi["predictions"]) and invalid else
               f"{invalid} responses failed parsing; excluded windows are not neutral predictions.")
    lines = ["# Multiframe semantic V1", "", outcome, "",
        f"Model: {MODEL_ID}; revision {MODEL_REVISION}.",
        "Selected as a small pretrained 256M-parameter model supporting multi-image input in maintained Transformers. "
        "Runs locally with standard eager attention and float32, no paid API, training, or FlashAttention requirement. "
        "The existing CPU PyTorch environment was reused.",
        "Sources: https://huggingface.co/HuggingFaceTB/SmolVLM2-256M-Video-Instruct and "
        "https://huggingface.co/docs/transformers/v4.57.1/en/model_doc/smolvlm",
        "", "## Frozen experiment", "",
        "Non-overlapping [0,5), [5,10), ... windows, final window truncated to video duration. "
        "Three frames at start, midpoint, and end-min(0.1,span/10) seconds, extracted with FFmpeg seek. "
        "Timestamps are requested seek positions. RGB frames fit inside 512x512 preserving aspect ratio; "
        "processor image splitting disabled. All three images and their timestamps enter ONE chat context "
        "and ONE generation call, independently for each window.",
        "Greedy generation, one beam, at most 48 new tokens. No retries or label correction. "
        "Parse first nonempty line as exactly one vocabulary label, optionally preceded by 'label:', "
        "case-insensitively. Any other response remains invalid; it is not converted to neutral. "
        "Remaining lines are evidence, retained verbatim. Neutral/invalid windows produce no event; "
        "adjacent identical valid labels merge, with all original window responses in metadata.",
        "Confidence is unavailable: semantic-event confidence=0.0 is ONLY a schema compatibility sentinel. "
        "Metadata stores confidence_available=false and model_confidence=null. No score is inferred from text.",
        "", "Exact instruction:", "", PROMPT, "", "## Runtime", "",
        f"Device: {multi['device']}; hardware: {multi['hardware']}; torch {multi['torch_version']}; "
        f"transformers {multi['transformers_version']}.",
        f"Video duration {multi['duration']:.6f}s; video SHA-256 {multi['video_sha256']}.",
        f"{len(multi['predictions'])} windows. Model setup/loading: {multi['setup_seconds']:.3f}s; "
        f"frame extraction: {multi['frame_seconds']:.3f}s; inference including preprocessing: "
        f"{multi['inference_seconds']:.3f}s; total measured run: {multi['total_seconds']:.3f}s.",
        f"Inference throughput: {multi['windows_per_second']:.6f} windows/s; "
        f"source duration / inference time: {multi['duration']/multi['inference_seconds']:.4f}x realtime.",
        f"Invalid responses: {sum(p['label'] is None for p in multi['predictions'])}; "
        f"neutral windows: {sum(p['label']=='neutral' for p in multi['predictions'])}.",
        "", "## Fragmentation comparison", "",
        "For adjacent-label stability, window labels are projected onto the unchanged 1 FPS grid; "
        "invalid/missing windows remain None (a distinct state). Durations use actual merged event bounds. "
        "Five-second classification structurally limits switching; lower fragmentation does not itself "
        "demonstrate temporal understanding or better semantics.",
        "", "| Metric | Raw CLIP | Temporal CLIP | Multiframe |", "|---|---:|---:|---:|"]
    for metric in ("event_count", "label_transitions", "mean_event_duration",
                   "median_event_duration", "longest_event_duration", "adjacent_same_label_fraction"):
        values = [c["stability"][metric] for c in comparisons.values()]
        lines.append(f"| {metric} | " + " | ".join("N/A" if v is None else f"{v:.6f}" for v in values) + " |")
    lines += ["", "## Counts and same-type GT coverage", "",
        "| Type | Raw events | Temporal events | Multiframe events | GT seconds | Raw / temporal / multiframe covered seconds |",
        "|---|---:|---:|---:|---:|---|"]
    diagnostics = [c["diagnostics"] for c in comparisons.values()]
    kinds = list(dict.fromkeys([*EVENT_TYPES,*diagnostics[0]["gt_counts"]]))
    for kind in kinds:
        counts = [d["event_counts"].get(kind,0) for d in diagnostics]
        coverage = [d["same_type_coverage"].get(kind) for d in diagnostics]
        gt = f"{coverage[0]['duration']:.6f}" if coverage[0] else "N/A"
        covered = " / ".join(f"{c['covered_duration']:.6f}" for c in coverage) if coverage[0] else "N/A"
        lines.append(f"| {kind} | {counts[0]} | {counts[1]} | {counts[2]} | {gt} | {covered} |")
    lines += ["", "## Overlap matrix (seconds)", "",
        "Each cell is raw / temporal / multiframe. Different-label overlap is not conventional accuracy: "
        "GT describes broad sequences, and kills/deaths may be inside combat; intro has no model class.",
        "", "| GT type | " + " | ".join(EVENT_TYPES) + " |", "|---|"+"---:|"*len(EVENT_TYPES)]
    for kind in diagnostics[0]["overlap_seconds"]:
        lines.append(f"| {kind} | "+" | ".join(" / ".join(f"{d['overlap_seconds'][kind][label]:.6f}"
                     for d in diagnostics) for label in EVENT_TYPES)+" |")
    lines += ["", "## Frozen candidates and changed interpretations", "",
        "Same point candidates and inclusive 5-second event-distance association. No scoring changes; "
        "confidence sentinels must not be compared to CLIP relative scores.", ""]
    lines += [f"- {name}: "+", ".join(f"{t:g}" for t in times)
              for name,times in diagnostics[0]["candidates"].items()]
    lines += ["", "| Candidate | Raw overlap | Temporal overlap | Multiframe overlap | Multiframe nearby |",
              "|---:|---|---|---|---|"]
    for t in diagnostics[0]["associations"]:
        associations = [d["associations"][t] for d in diagnostics]
        def summary(a,key):
            return ", ".join(f"{e['event_type']} [{e['start']:g},{e['end']:g})" for e in a[key]) or "none"
        lines.append(f"| {t} | "+" | ".join(summary(a,"overlapping_events") for a in associations)+
                     f" | {summary(associations[2],'nearby_events')} |")
    lines += ["", "## Original model responses", "",
        "These are model statements, not verified descriptions. Candidate-table changes above and these "
        "reasons provide qualitative examples; this design changes the model as well as input context, "
        "so it cannot isolate the causal benefit of multiple frames.", "",
        "| Window | Frames | Parsed label | Original response |", "|---|---|---|---|"]
    for p in multi["predictions"]:
        response = p["response"].replace("|","\\|").replace("\n"," / ").replace("\r","")
        lines.append(f"| {p['start']:g}-{p['end']:g} | "+", ".join(f"{t:.6f}" for t in p["frame_timestamps"])+
                     f" | {p['label'] or 'INVALID'} | {response} |")
    lines += ["", "## Limitations and reproduction", "",
        "One already-edited Minecraft video; no generalization claim. Pretrained model, no fine-tuning. "
        "Three snapshots can miss an event or hallucinate a narrative. Model reasons are not proof. "
        "No ranking, weights, production boundaries/clipping, GT, or previous experiments changed. "
        "No tuning after GT comparison; no second model or Multiframe V2 attempted.",
        "Environment: output/clip_env/Scripts/python.exe. Inference: python multiframe_semantics.py; "
        "evaluation: python evaluate_multiframe_semantics.py. Inference refuses to overwrite first-run artifacts. "
        "Outputs are ignored under output/multiframe_semantic_*.json and the per-window .jsonl journal.",
        "Optional dependencies are pinned in requirements-multiframe.txt. Processor preflight required "
        "torchvision 0.28.0 and num2words 0.5.14. Image splitting was corrected and verified on synthetic "
        "inputs before real inference; no experiment parameters or parser rules changed after evaluation."]
    return "\n".join(lines)+"\n"


def main():
    repo = Path(__file__).resolve().parent
    def read(name):
        return json.loads((repo/"output"/name).read_text(encoding="utf-8"))
    raw, temporal, multi = [read(n) for n in ("clip_semantic_timeline.json",
        "temporal_clip_timeline.json","multiframe_semantic_timeline.json")]
    if multi["model_id"] != MODEL_ID or multi["model_revision"] != MODEL_REVISION or multi["prompt"] != PROMPT:
        raise ValueError("Multiframe artifact differs from frozen protocol")
    if not raw["duration"] == temporal["duration"] == multi["duration"] or raw["video_sha256"] != multi["video_sha256"]:
        raise ValueError("Experiments do not share the same video")
    candidates = frozen_candidates((repo/"results/fixed_window_v2_baseline.md").read_text(encoding="utf-8"))
    annotations = load_annotations(repo/"ground_truth_v2.json",multi["duration"])
    comparisons = compare(raw,temporal,multi,load_events(repo/"output/clip_semantic_events.json"),
                          load_events(repo/"output/temporal_clip_events.json"),annotations,candidates)
    write_json(repo/"output/multiframe_semantic_comparison.json",comparisons)
    text = format_report(multi,comparisons)
    (repo/"results/multiframe_semantic_v1.md").write_text(text,encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
