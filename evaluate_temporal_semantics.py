"""Reuse saved CLIP evidence; compute stability before loading human annotations."""
import argparse
import hashlib
import json
from pathlib import Path

from annotate import load_annotations
from evaluate_semantic_clip import describe, frozen_candidates
from semantic_clip import MODEL_ID, MODEL_REVISION, PROMPTS, timeline_to_events, write_json
from semantic_events import EVENT_TYPES, save_events
from temporal_semantics import aggregate_timeline, temporal_to_events, stability_metrics


def format_report(artifact, summaries, raw, temporal, stability, source_hash):
    lines = ["# Five-second Temporal CLIP V1", "",
        f"Reused the existing {len(artifact['rows'])}-sample CLIP timeline; no inference or model download.",
        f"Model: {MODEL_ID}; revision {MODEL_REVISION}. Source artifact SHA-256: {source_hash}.",
        "", "## Frozen protocol", "",
        "For each 1 FPS timestamp, average every label's zero_shot_score over t-2 through t+2 "
        "(five samples, fewer at edges). Use the unweighted arithmetic mean, then argmax in frozen "
        "prompt order for ties. Do not average labels or apply another softmax. Missing, duplicate, "
        "or nonuniform timestamps are rejected. Seven prompts, model, and sample frequency are unchanged.",
        "Each sample represents [t,min(t+1,duration)); merge consecutive identical labels and exclude neutral. "
        "No thresholds or minimum duration. Event confidence holds mean winning relative evidence, "
        "not calibrated probability. Metadata preserves aggregated vectors and source neighborhoods.",
        "Stability was computed and saved before GT loading. No parameters changed after comparison.",
        "", "## Stability (before GT)", "",
        "Counts/durations exclude neutral; transitions and adjacent-label retention include neutral. "
        "N/A means no events or no adjacent sample pairs.", "",
        "| Metric | Raw | Temporal | Delta (temporal-raw) |", "|---|---:|---:|---:|"]
    for key in stability["raw"]:
        a, b = stability["raw"][key], stability["temporal"][key]
        if a is None or b is None:
            lines.append(f"| {key} | {a} | {b} | N/A |")
        else:
            lines.append(f"| {key} | {a:.6f} | {b:.6f} | {b-a:+.6f} |")
    lines += ["", "## Event counts and same-type coverage", "",
        "| Type | Raw events | Temporal events | GT intervals | GT seconds | Raw covered s | Temporal covered s | Delta s |",
        "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for kind in dict.fromkeys([*EVENT_TYPES, *raw["gt_counts"]]):
        a, b = raw["same_type_coverage"].get(kind), temporal["same_type_coverage"].get(kind)
        cells = (f"{a['duration']:.6f} | {a['covered_duration']:.6f} | {b['covered_duration']:.6f} | "
                 f"{b['covered_duration']-a['covered_duration']:+.6f}") if a else "N/A | N/A | N/A | N/A"
        lines.append(f"| {kind} | {raw['event_counts'].get(kind,0)} | {temporal['event_counts'].get(kind,0)} | "
                     f"{raw['gt_counts'].get(kind,0)} | {cells} |")
    lines += ["", "## Temporal overlap matrix", "",
        "Seconds shown as raw / temporal. Broad GT sequences are not frame-level class labels. "
        "Intro has no prompt; kills/deaths/objectives can occur inside combat. Gaps stay outside coverage.",
        "", "| GT type | " + " | ".join(EVENT_TYPES) + " |", "|---|" + "---:|"*len(EVENT_TYPES)]
    for kind, values in raw["overlap_seconds"].items():
        lines.append(f"| {kind} | " + " | ".join(
            f"{values[k]:.6f} / {temporal['overlap_seconds'][kind][k]:.6f}" for k in EVENT_TYPES) + " |")
    lines += ["", "## Fragmentation and semantic evidence", "",
        f"Non-neutral event count changed from {stability['raw']['event_count']} to "
        f"{stability['temporal']['event_count']}; label transitions changed from "
        f"{stability['raw']['label_transitions']} to {stability['temporal']['label_transitions']}.",
        "Fewer runs/transitions indicate reduced fragmentation, not verified semantic correctness. "
        "The coverage deltas above describe which matching-label evidence was retained, gained, or lost; "
        "they cannot prove preservation of actual kills or objectives without event-level annotations."]
    for kind in raw["overlap_seconds"]:
        for label in EVENT_TYPES:
            a = raw["overlap_seconds"][kind][label]
            b = temporal["overlap_seconds"][kind][label]
            if label != kind and (a or b):
                lines.append(f"- GT {kind} / predicted {label}: {a:.6f}s -> {b:.6f}s ({b-a:+.6f}s).")
    lines += ["", "## Frozen candidate diagnostics", "",
        "Same frozen point candidates, inclusive 5s radius to event extent. "
        "Max values are relative evidence, not factual confidence. No ranking changes.", ""]
    lines += [f"- {name}: " + ", ".join(f"{t:g}" for t in times) for name,times in raw["candidates"].items()]
    lines += ["", "| Candidate | Raw overlap | Temporal overlap | Raw nearby | Temporal nearby |",
              "|---:|---|---|---|---|"]
    for t, a in raw["associations"].items():
        b = temporal["associations"][t]
        def labels(item, key):
            return ", ".join(f"{e['event_type']} [{e['start']:g},{e['end']:g})" for e in item[key]) or "none"
        lines.append(f"| {t} | {labels(a,'overlapping_events')} | {labels(b,'overlapping_events')} | "
                     f"{labels(a,'nearby_events')} | {labels(b,'nearby_events')} |")
    lines += ["", "## Aggregated non-neutral timeline", "",
              "| Start | End | Type | Mean winning relative score |", "|---:|---:|---|---:|"]
    for e in summaries:
        lines.append(f"| {e['start']:.6f} | {e['end']:.6f} | {e['event_type']} | {e['confidence']:.6f} |")
    lines += ["", "## Limitations and reproduction", "",
        "One already-edited video. Pretrained image-text evidence is not video understanding. "
        "A centered window uses up to two seconds of future context and can blur short events. "
        "Relative scores are uncalibrated; no accuracy or generalization claim, no overall winner. "
        "No retention, tuning, detector changes, or production clipping changes.",
        "Run python evaluate_temporal_semantics.py from the repository. The runner refuses to overwrite "
        "its first comparison artifacts. All raw CLIP code/results remain unchanged.",
        "Saved ignored outputs: output/temporal_clip_stability.json, output/temporal_clip_timeline.json, "
        "output/temporal_clip_events.json, output/temporal_clip_comparison.json."]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeline", type=Path, default=Path("output/clip_semantic_timeline.json"))
    parser.add_argument("--annotations", type=Path, default=Path("ground_truth_v2.json"))
    parser.add_argument("--baseline", type=Path, default=Path("results/fixed_window_v2_baseline.md"))
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument("--report", type=Path, default=Path("results/temporal_clip_v1.md"))
    args = parser.parse_args()
    paths = [args.output/f"temporal_clip_{name}.json" for name in ("stability","timeline","events","comparison")]
    if args.report.exists() or any(p.exists() for p in paths):
        raise FileExistsError("Preserve the first comparison; output already exists")
    content = args.timeline.read_bytes()
    artifact = json.loads(content)
    if (artifact["model_id"] != MODEL_ID or artifact["model_revision"] != MODEL_REVISION
            or artifact["prompts"] != PROMPTS or artifact["sample_interval_seconds"] != 1):
        raise ValueError("Not the frozen CLIP V1 protocol")
    rows, duration = artifact["rows"], artifact["duration"]
    aggregated = aggregate_timeline(rows, duration)
    raw_events = timeline_to_events(rows, duration)
    temporal_events = temporal_to_events(aggregated, duration)
    stability = dict(raw=stability_metrics(rows,raw_events),
                     temporal=stability_metrics(aggregated,temporal_events))
    args.output.mkdir(parents=True, exist_ok=True)
    write_json(paths[0], stability)
    print("Stability computed before GT loading:", json.dumps(stability), flush=True)
    source_hash = hashlib.sha256(content).hexdigest()
    write_json(paths[1], dict(model_id=MODEL_ID, model_revision=MODEL_REVISION, prompts=PROMPTS,
                             source_sha256=source_hash, duration=duration,
                             aggregation="mean zero_shot_score over centered t-2..t+2", rows=aggregated))
    save_events(temporal_events, paths[2])
    # Only now read GT. Neither aggregation nor stability has access to it.
    annotations = load_annotations(args.annotations, duration)
    candidates = frozen_candidates(args.baseline.read_text(encoding="utf-8"))
    raw = describe(raw_events,annotations,candidates)
    temporal = describe(temporal_events,annotations,candidates)
    write_json(paths[3], dict(raw=raw, temporal=temporal))
    text = format_report(artifact,temporal_events,raw,temporal,stability,source_hash)
    args.report.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
