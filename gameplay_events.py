"""Human gameplay annotations and read-only temporal retrieval; no detection."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

from shared_analysis import create_analysis, signal, validate_analysis
from multimodal_timeline import (check_provenance, json_value, number, read_json,
                                source_metadata, validate_timeline)
from source_identity import canonical
from highlight_evaluation import digest, publish
from candidate_evidence import compare_identity, evidence_coverage
from timeline_query import query_timeline

EVENT_TYPES = ("fight", "player_elimination", "player_death", "bed_destroyed",
               "game_victory", "game_transition", "respawn", "other")
PRECISIONS = ("exact_point", "exact_interval", "clip_level")
IDENTITY_FIELDS = ("sha256", "duration_seconds", "width", "height", "fps", "size_bytes")
LIMITATIONS = [
    "Human annotations are not model predictions; empty annotations are not negative labels.",
    "clip_level bounds describe uncertainty, not the actual duration or number of events.",
    "Source identity and duration are reported claims, not independently verified by this CLI.",
    "Closed overlap includes boundary touches; queries do not assign events exclusively.",
    "Temporal overlap is not causal evidence, classifier accuracy or highlight quality.",
    "Audio spikes, scene changes, speech and ImageNet categories do not reliably identify BedWars events.",
]


def identity_claim(source):
    source_metadata(source)
    return dict(status="reported_sha256_unverified" if "sha256" in source else
                "unverified_missing_source_digest", claims=deepcopy(source))


def create_template(analysis):
    """Preserve the complete candidate rows/order, including duplicate windows."""
    analysis = validate_analysis(analysis)
    envelope = analysis["candidate_windows"]
    if envelope["status"] != "analyzed":
        raise ValueError("Candidate windows must be analyzed")
    check_provenance(envelope["provenance"], analysis["source_video"])
    result = dict(schema_version=1, artifact_type="gameplay-event-annotations",
        source_video_identity=identity_claim(analysis["source_video"]),
        analysis_schema_version=analysis["schema_version"],
        candidate_provenance=deepcopy(envelope["provenance"]),
        candidates=[dict(candidate_index=i, original_candidate=deepcopy(row), events=[])
                    for i, row in enumerate(envelope["data"])])
    result["template_id"] = digest(result)
    return result


def original_analysis(document):
    analysis = create_analysis(document["source_video_identity"]["claims"])
    analysis["candidate_windows"] = signal(
        [row["original_candidate"] for row in document["candidates"]],
        document["candidate_provenance"])
    return analysis


def nonempty_text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonempty text")


def validate_annotations(document, *, verified_source=None):
    """Validate claims without media access.

    Optional verified_source must come from an independent caller verification,
    never from this document. It supplies additional content/duration checks;
    persisted claims are never promoted to verified merely by loading JSON.
    """
    try:
        json_value(document)
        expected = create_template(original_analysis(document))
        empty = deepcopy(document)
        for row in empty["candidates"]:
            if not isinstance(row["events"], list):
                raise ValueError("Candidate events must be a list")
            row["events"] = []
        if canonical(empty) != canonical(expected):
            raise ValueError("Annotation template mismatch: schema, identity, candidates or provenance")
        source = document["source_video_identity"]["claims"]
        duration = source["duration_seconds"]
        if verified_source is not None:
            source_metadata(verified_source)
            if ("sha256" not in source or "sha256" not in verified_source or
                    "duration_seconds" not in verified_source):
                raise ValueError("Independent verification requires source SHA-256 and duration")
            for key in IDENTITY_FIELDS:
                if key in source and key in verified_source and source[key] != verified_source[key]:
                    raise ValueError(f"Verified source identity mismatch: {key}")
            duration = verified_source["duration_seconds"]
        known_claims = {key: source[key] for key in IDENTITY_FIELDS if key in source}

        def reconcile_provenance(provenance):
            check_provenance(provenance, source)
            for old, key in (("source_sha256", "sha256"), ("source_duration_seconds", "duration_seconds")):
                if old in provenance:
                    if key in known_claims and known_claims[key] != provenance[old]:
                        raise ValueError(f"Conflicting annotation provenance: {key}")
                    known_claims[key] = provenance[old]

        reconcile_provenance(document["candidate_provenance"])
        ids = set()
        required = {"event_id", "event_type", "start_seconds", "end_seconds", "temporal_precision",
                    "description", "source", "source_video_identity", "provenance"}
        optional = {"certainty", "player", "team", "notes"}
        for row in document["candidates"]:
            for event in row["events"]:
                if not isinstance(event, dict) or not required <= event.keys() or event.keys() - required - optional:
                    raise ValueError("Invalid gameplay event fields")
                nonempty_text(event["event_id"], "event_id")
                if event["event_id"] in ids:
                    raise ValueError("Duplicate event_id across annotation document")
                ids.add(event["event_id"])
                if event["event_type"] not in EVENT_TYPES or event["source"] != "human":
                    raise ValueError("Expected an allowed gameplay event type and human source")
                start, end = number(event["start_seconds"]), number(event["end_seconds"])
                if not 0 <= start <= end <= duration:
                    raise ValueError("Event outside source duration claim or verified bounds")
                precision = event["temporal_precision"]
                if (precision not in PRECISIONS or (precision == "exact_point") != (start == end)):
                    raise ValueError("Precision must agree with point/interval bounds")
                nonempty_text(event["description"], "description")
                if canonical(event["source_video_identity"]) != canonical(document["source_video_identity"]):
                    raise ValueError("Event source identity differs from annotation document")
                provenance = event["provenance"]
                reconcile_provenance(provenance)
                nonempty_text(provenance.get("annotator"), "provenance.annotator")
                if provenance.get("method") != "manual_review":
                    raise ValueError("Human annotation provenance requires method=manual_review")
                if event.get("certainty") not in (None, "uncertain", "certain"):
                    raise ValueError("Certainty must be null, uncertain or certain; not a probability")
                for key in ("player", "team"):
                    if key in event and not isinstance(event[key], dict):
                        raise ValueError(f"{key} details must be a JSON object")
                if "notes" in event and not isinstance(event["notes"], str):
                    raise ValueError("Notes must be text")
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Malformed gameplay annotations") from exc
    return document


def event_records(document):
    """Candidate order then entered event order, without deduplication."""
    return [dict(candidate_index=row["candidate_index"], event=deepcopy(event))
            for row in document["candidates"] for event in row["events"]]


def report_header(document, artifact_type):
    return dict(schema_version=1, artifact_type=artifact_type,
        annotation_document_sha256=digest(document),
        source_video_identity=deepcopy(document["source_video_identity"]),
        candidate_provenance=deepcopy(document["candidate_provenance"]),
        limitations=list(LIMITATIONS))


def query_events(document, start_seconds, end_seconds):
    """Closed [start,end] retrieval, consistent with Timeline Query V1."""
    validate_annotations(document)
    start, end = number(start_seconds), number(end_seconds)
    if not 0 <= start <= end <= document["source_video_identity"]["claims"]["duration_seconds"]:
        raise ValueError("Query outside source duration claim or reversed")
    matches = [row for row in event_records(document)
               if row["event"]["start_seconds"] <= end and row["event"]["end_seconds"] >= start]
    return dict(report_header(document, "gameplay-event-query"),
        query=dict(start_seconds=start, end_seconds=end, overlap="closed"),
        matched_event_count=len(matches),
        event_types=list(dict.fromkeys(row["event"]["event_type"] for row in matches)), events=matches)


def align_timeline(document, timeline):
    """Retrieve temporal associations only; refuse linking missing source digests."""
    validate_annotations(document)
    validate_timeline(timeline)
    status = compare_identity(original_analysis(document), timeline)
    if status != "consistent_reported_sha256":
        raise ValueError("Alignment requires matching reported SHA-256 on every artifact; identity remains unverified")
    aligned = []
    for row in event_records(document):
        event = row["event"]
        match = query_timeline(timeline, event["start_seconds"], event["end_seconds"])
        aligned.append(dict(row, observations=match["events"],
            counts_by_modality=match["counts_by_modality"],
            evidence_coverage=evidence_coverage(timeline, match["counts_by_modality"])))
    return dict(report_header(document, "gameplay-event-alignment"),
        identity_comparison=status, timeline_schema_version=timeline["schema_version"],
        timeline_content_sha256=digest(timeline), timeline_sources=deepcopy(timeline["sources"]),
        timeline_identity_status=timeline["identity_status"],
        timeline_source_identity=deepcopy(timeline["source_identity"]), events=aligned)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    template = commands.add_parser("template")
    template.add_argument("--analysis", type=Path, required=True)
    query = commands.add_parser("query")
    query.add_argument("--start", type=float, required=True)
    query.add_argument("--end", type=float, required=True)
    align = commands.add_parser("align")
    align.add_argument("--timeline", type=Path, required=True)
    for command in (query, align):
        command.add_argument("--annotations", type=Path, required=True)
    for command in (template, query, align):
        command.add_argument("--output", type=Path, required=command is template)
        command.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    if args.overwrite and args.output is None:
        parser.error("--overwrite requires --output")
    try:
        if args.command == "template":
            inputs = [args.analysis]
            result = create_template(read_json(args.analysis))
        else:
            inputs = [args.annotations]
            document = read_json(args.annotations)
            if args.command == "query":
                result = query_events(document, args.start, args.end)
            else:
                inputs.append(args.timeline)
                result = align_timeline(document, read_json(args.timeline))
        if args.output is not None:
            publish(result, args.output, inputs, args.overwrite)
        print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    except (OSError, ValueError) as exc:
        print(f"FAIL: gameplay events: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
