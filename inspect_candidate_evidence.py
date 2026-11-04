"""Inspect existing Candidate Evidence V1 without inference, ranking or writes."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

from candidate_evidence import compare_identity, evidence_coverage
from multimodal_timeline import json_value, number, read_json, reconcile, validate_timeline
from shared_analysis import create_analysis, signal, validate_analysis
from timeline_query import query_timeline

SCORES = ("score", "normalized_score", "highlight_score", "scene_score",
          "motion_score", "motion_highlight_score")
EVENT_TYPES = {
    "speech_segment": ("transcript", "transcript", "interval", "start"),
    "imagenet_frame_prediction": ("visual", "frames", "point", "timestamp_seconds"),
    "scene_change": ("visual", "scene_changes", "point", "time"),
    "audio_activity": ("audio", "audio_activity", "point", "second"),
    "audio_spike_score": ("audio", "audio_activity", "point", "second"),
}
LIMITATIONS = [
    "No observations does not mean nothing interesting happened.",
    "Temporal coverage is unknown, including for analyzed channels with no matches.",
    "Identity fields are reported claims; source video bytes were not verified.",
    "ImageNet labels are model predictions, not verified gameplay facts or gameplay understanding.",
    "Counts describe retained evidence, not highlight quality; candidates are not ranked.",
]


def validate_evidence(evidence):
    """Validate the existing report by reusing its source schema contracts."""
    try:
        json_value(evidence)
        if set(evidence) != {"schema_version", "report_type", "inputs", "identity_comparison", "candidates"}:
            raise ValueError("Invalid Candidate Evidence fields")
        if type(evidence["schema_version"]) is not int or evidence["schema_version"] != 1 or evidence["report_type"] != "candidate-evidence":
            raise ValueError("Unsupported Candidate Evidence schema")
        inputs, rows = evidence["inputs"], evidence["candidates"]
        if not isinstance(rows, list):
            raise ValueError("Candidates must be a list")
        candidate_input, timeline_input = inputs["candidates"], inputs["timeline"]
        for item in (candidate_input, timeline_input):
            if type(item["schema_version"]) is not int or item["schema_version"] != 1:
                raise ValueError("Unsupported input schema version")
            if item["reference"] is not None and not isinstance(item["reference"], str):
                raise ValueError("Invalid input reference")
        if candidate_input["status"] != "analyzed":
            raise ValueError("Candidate input must be analyzed")
        # Reconstruct only the existing candidate envelope for schema validation.
        analysis = create_analysis(candidate_input["source_video"])
        analysis["candidate_windows"] = signal([row["candidate"] for row in rows], candidate_input["provenance"])
        validate_analysis(analysis)
        timeline = dict(schema_version=timeline_input["schema_version"], timeline_type="multimodal-observations",
                        sources=timeline_input["sources"], events=[], **reconcile(timeline_input["sources"]))
        for key in ("identity_status", "source_identity"):
            if timeline_input[key] != timeline[key]:
                raise ValueError("Timeline identity claims disagree")
        validate_timeline(timeline)
        if evidence["identity_comparison"] != compare_identity(analysis, timeline):
            raise ValueError("Identity comparison disagrees with source claims")
        for index, row in enumerate(rows):
            if type(row["candidate_index"]) is not int or row["candidate_index"] != index:
                raise ValueError("Candidate index must preserve original position")
            candidate = row["candidate"]
            number(row["window"]["start"])
            number(row["window"]["end"])
            if row["window"] != dict(start=candidate["start"], end=candidate["end"]):
                raise ValueError("Window disagrees with original candidate")
            for key in SCORES:
                if key in candidate:
                    number(candidate[key])
            timeline["events"] = row["events"]
            matched = query_timeline(timeline, candidate["start"], candidate["end"])
            if matched["events"] != row["events"]:
                raise ValueError("Evidence contains events outside its candidate window")
            if type(row["matched_event_count"]) is not int or row["matched_event_count"] != matched["matched_event_count"]:
                raise ValueError("Invalid total event count")
            counts = row["counts_by_modality"]
            if (not isinstance(counts, dict) or counts != matched["counts_by_modality"]
                    or any(type(n) is not int for n in counts.values())):
                raise ValueError("Invalid modality counts")
            if row["evidence_coverage"] != evidence_coverage(timeline, counts):
                raise ValueError("Missing or inconsistent modality coverage")
            for event in row["events"]:
                if event["event_type"] not in EVENT_TYPES:
                    raise ValueError("Unsupported observation type for V1 inspection")
                modality, channel, kind, time_key = EVENT_TYPES[event["event_type"]]
                payload = event["payload"]
                source = timeline["sources"][event["source"]["artifact_index"]]
                if source["channels"][event["source"]["channel"]]["status"] != "analyzed":
                    raise ValueError("Observation belongs to an unanalyzed channel")
                if (event["modality"], event["source"]["channel"], event["observation_kind"]) != (modality, channel, kind):
                    raise ValueError("Observation type disagrees with modality/channel")
                if number(payload[time_key]) != event["start_seconds"]:
                    raise ValueError("Payload timestamp disagrees with event")
                if kind == "interval":
                    if number(payload["end"]) != event["end_seconds"] or not isinstance(payload["text"], str):
                        raise ValueError("Invalid transcript payload")
                elif channel == "frames":
                    if not isinstance(payload["top3"], list) or len(payload["top3"]) != 3:
                        raise ValueError("Visual prediction requires original top3")
                    for prediction in payload["top3"]:
                        if not isinstance(prediction["category"], str) or not 0 <= number(prediction["confidence"]) <= 1:
                            raise ValueError("Invalid visual prediction")
                else:
                    for key in ("volume", "spike", "score", "normalized_score"):
                        if key in payload:
                            number(payload[key])
        return evidence
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        raise ValueError("Malformed Candidate Evidence V1") from exc


def inspect_evidence(evidence, preview_limit=3, preview_chars=160):
    """Pure bounded inspection; counts always describe all retained observations."""
    if type(preview_limit) is not int or not 0 <= preview_limit <= 20:
        raise ValueError("preview_limit must be an integer from 0 to 20")
    if type(preview_chars) is not int or not 1 <= preview_chars <= 500:
        raise ValueError("preview_chars must be an integer from 1 to 500")
    validate_evidence(evidence)
    reports = []
    categories = ("transcript", "audio", "visual", "scene_change")
    with_observations = dict.fromkeys(categories, 0)
    for row in evidence["candidates"]:
        events = row["events"]
        groups = {name:[e for e in events if e["modality"] == name] for name in categories[:3]}
        groups["scene_change"] = [e for e in events if e["event_type"] == "scene_change"]
        predictions = [e for e in events if e["event_type"] == "imagenet_frame_prediction"]
        preview_groups = dict(transcript=groups["transcript"], visual_predictions=predictions,
                              audio=groups["audio"], scene_change=groups["scene_change"])
        previews = {}
        for name, observations in preview_groups.items():
            items = []
            for event in observations[:preview_limit]:
                payload = event["payload"]
                item = dict(start=event["start_seconds"], end=event["end_seconds"],
                            event_type=event["event_type"], source_order=event["source_order"])
                if name == "transcript":
                    item.update(text=payload["text"][:preview_chars],
                                text_truncated=len(payload["text"]) > preview_chars)
                elif name == "visual_predictions":
                    item["model_predictions"] = [
                        dict(label=p["category"][:preview_chars], label_truncated=len(p["category"]) > preview_chars,
                             confidence=p["confidence"]) for p in payload["top3"]]
                else:
                    item["original_values"] = {k:payload[k] for k in ("volume","spike","score","normalized_score") if k in payload}
                items.append(item)
            previews[name] = dict(items=items, omitted_events=max(0,len(observations)-preview_limit))
        for name in categories:
            with_observations[name] += bool(groups[name])
        candidate = row["candidate"]
        reports.append(dict(candidate_index=row["candidate_index"],
                            identifiers={k:deepcopy(candidate[k]) for k in ("id","rank","second") if k in candidate},
                            start=candidate["start"], end=candidate["end"],
                            duration=candidate["end"]-candidate["start"],
                            original_scores={k:candidate[k] for k in SCORES if k in candidate},
                            matched_event_count=row["matched_event_count"],
                            counts_by_modality=deepcopy(row["counts_by_modality"]),
                            scene_change_count=len(groups["scene_change"]),
                            evidence_coverage=deepcopy(row["evidence_coverage"]), previews=previews))
    return dict(candidate_count=len(reports), with_observations=with_observations,
                without_observations={k:len(reports)-n for k,n in with_observations.items()},
                identity_comparison=evidence["identity_comparison"],
                timeline_identity_status=evidence["inputs"]["timeline"]["identity_status"],
                candidate_provenance=deepcopy(evidence["inputs"]["candidates"]["provenance"]),
                limitations=list(LIMITATIONS), candidates=reports)


def render_text(report):
    """Readable bounded previews; JSON quoting escapes terminal control characters."""
    lines = [f"Candidates: {report['candidate_count']}",
             f"Identity: {report['identity_comparison']}; timeline: {report['timeline_identity_status']}"]
    for category, count in report["with_observations"].items():
        lines.append(f"{category}: {count} with observations; {report['without_observations'][category]} without")
    lines += ["Limitations: " + text for text in report["limitations"]]
    for row in report["candidates"]:
        identifiers = json.dumps(row["identifiers"], ensure_ascii=True)
        if len(identifiers) > 200:
            identifiers = identifiers[:200] + "... [identifier preview truncated]"
        lines += ["", f"Candidate {row['candidate_index']} {identifiers}: [{row['start']}, {row['end']}] s; duration {row['duration']} s",
                  f"Original scores: {json.dumps(row['original_scores']) or '{}'}",
                  f"Events: {row['matched_event_count']}; {json.dumps(row['counts_by_modality'])}; scene changes: {row['scene_change_count']}"]
        for modality, coverage in row["evidence_coverage"].items():
            lines.append(f"  {modality}: {coverage['observation_status']}; temporal coverage: {coverage['temporal_coverage']}")
        for category, preview in row["previews"].items():
            lines.append(f"  {category} previews (omitted events: {preview['omitted_events']}):")
            lines.extend("    " + json.dumps(item, ensure_ascii=True) for item in preview["items"])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--preview-limit", type=int, default=3)
    parser.add_argument("--preview-chars", type=int, default=160)
    args = parser.parse_args(argv)
    try:
        report = inspect_evidence(read_json(args.evidence), args.preview_limit, args.preview_chars)
        print(json.dumps(report, separators=(",", ":"), allow_nan=False) if args.format == "json" else render_text(report))
    except (OSError, ValueError) as exc:
        print(f"FAIL: candidate evidence inspection: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
