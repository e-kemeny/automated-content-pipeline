"""Experimental annotation-informed boundary suggestions; no media processing."""
import argparse
from copy import deepcopy
from pathlib import Path
import sys

from shared_analysis import validate_analysis
from gameplay_events import create_template, validate_annotations, event_records
from candidate_evidence import compare_identity, build_candidate_evidence
from multimodal_event_fusion import fuse_events, overlaps
from multimodal_timeline import number, read_json, check_provenance
from highlight_evaluation import digest, publish
from source_identity import canonical


def build_plan(analysis, *, annotations=None, fusion=None, timeline=None,
               min_duration=1, max_duration=60, max_extension=10, heuristic_padding=None):
    """Pure, expansion-only planning. Reject incompatible baseline constraints."""
    try:
        return _build(analysis, annotations, fusion, timeline, min_duration,
                      max_duration, max_extension, heuristic_padding)
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        raise ValueError("Malformed narrative boundary input") from exc


def _build(analysis, annotations, fusion, timeline, minimum, maximum, extension, padding):
    analysis = validate_analysis(analysis)
    source = analysis["source_video"]
    envelope = analysis["candidate_windows"]
    if envelope["status"] != "analyzed" or not envelope["data"]:
        raise ValueError("Analyzed nonempty candidate windows required")
    check_provenance(envelope["provenance"], source)
    if not 0 < number(minimum) <= number(maximum) or number(extension) < 0:
        raise ValueError("Invalid duration/extension constraints")
    if padding is not None and not 0 <= number(padding) <= extension:
        raise ValueError("Heuristic padding must be within maximum extension")
    duration = source["duration_seconds"]
    records = []
    if annotations is not None:
        validate_annotations(annotations)
        empty = deepcopy(annotations)
        for row in empty["candidates"]:
            row["events"] = []
        if canonical(empty) != canonical(create_template(analysis)):
            raise ValueError("Annotations do not match analysis identity/candidates/provenance")
        if not source.get("sha256"):
            raise ValueError("Annotation association requires source SHA-256")
        records = event_records(annotations)
    if fusion is not None:
        expected = fuse_events(**fusion["inputs"],
            ocr_time_offset_seconds=fusion["alignment"]["ocr_time_offset_seconds"],
            alignment_reference=fusion["alignment"]["reference"])
        if canonical(expected) != canonical(fusion):
            raise ValueError("Fusion artifact differs from validated producer output")
        # Inspect every embedded source claim, including partial identities.
        headers = []
        inputs = fusion["inputs"]
        if inputs["transcript"] is not None:
            headers += inputs["transcript"]["input_provenance"]["sources"]
        if inputs["timeline"] is not None:
            headers += inputs["timeline"]["sources"]
        if inputs["ocr"] is not None and inputs["ocr"]["input_evidence"] is not None:
            identity = inputs["ocr"]["input_evidence"]["source_identity"]
            headers.append(dict(source_video=dict(sha256=identity["digest"],
                size_bytes=identity["size_bytes"], **identity["media"]), channels={}))
        if headers and compare_identity(analysis, dict(sources=headers)) != "consistent_reported_sha256":
            raise ValueError("Fusion association requires matching source SHA-256")
    context = None
    if timeline is not None:
        context = build_candidate_evidence(analysis, timeline)
        if context["identity_comparison"] != "consistent_reported_sha256":
            raise ValueError("Timeline association requires matching source SHA-256")
    candidates = []
    for index, original in enumerate(envelope["data"]):
        start, end = original["start"], original["end"]
        if not minimum <= end-start <= maximum or end <= start:
            raise ValueError("Original window violates duration constraints; choose compatible limits")
        linked = [r["event"] for r in records if r["candidate_index"] == index]
        eligible = [e for e in linked if e["temporal_precision"] == "exact_interval"
                    and e.get("certainty") == "certain"
                    and overlaps((start, end), (e["start_seconds"], e["end_seconds"]))]
        proposed_start, proposed_end = start, end
        status, reason = "insufficient_evidence", "No unique certain exact interval overlaps this candidate"
        support = None
        if len(eligible) == 1:
            support = eligible[0]
            proposed_start = min(start, support["start_seconds"])
            proposed_end = max(end, support["end_seconds"])
            status, reason = "evidence_supported", "Preserve one candidate-linked human interval"
        elif padding is not None and not eligible:
            proposed_start, proposed_end = max(0, start-padding), min(duration, end+padding)
            status, reason = "heuristic_only", "Explicit fixed padding; no semantic completeness claim"
        # Never partially truncate a supported interval to make it fit.
        if (start-proposed_start > extension or proposed_end-end > extension
                or not minimum <= proposed_end-proposed_start <= maximum):
            proposed_start, proposed_end = start, end
            status, reason = "insufficient_evidence", "Complete proposal exceeds configured limits"
        added = [(proposed_start, start), (end, proposed_end)]
        def newly_crossed(a, b):
            return any(x < y and overlaps((x, y), (a, b)) for x, y in added)
        blockers = [r["event"]["event_id"] for r in records
                    if r["event"] != support and newly_crossed(r["event"]["start_seconds"],
                                                             r["event"]["end_seconds"])]
        # Fused timing remains observational. Use groups conservatively as blockers,
        # never as exact event boundaries or as proof of absence.
        if fusion is not None:
            blockers += [g["group_id"] for g in fusion["groups"]
                if g["clock"] == "source_timeline"
                and newly_crossed(g["observation_envelope"]["start_seconds"],
                                  g["observation_envelope"]["end_seconds"])]
        if blockers:
            proposed_start, proposed_end = start, end
            status, reason = "insufficient_evidence", "Extension intersects other event evidence"
        candidates.append(dict(candidate_index=index,
            candidate_id=digest(dict(index=index, source_video=source, candidate=original)),
            original_candidate=deepcopy(original),
            proposed=dict(start=proposed_start, end=proposed_end, duration=proposed_end-proposed_start),
            changed=(proposed_start, proposed_end) != (start, end),
            status=status, reason=reason, supporting_event_id=None if support is None else support["event_id"],
            blocked_by=blockers, human_events=deepcopy(linked)))
    inputs = dict(analysis=analysis, annotations=annotations, fusion=fusion, timeline=timeline)
    result = dict(schema_version=1, artifact_type="narrative-clip-boundaries",
        source_video=deepcopy(source), identity_status="reported_claims_not_media_verified",
        candidate_provenance=deepcopy(envelope["provenance"]),
        policy=dict(min_duration=minimum, max_duration=maximum, max_extension=extension,
                    heuristic_padding=padding, source_duration=duration),
        inputs=deepcopy(inputs), input_digests={k: None if v is None else digest(v) for k,v in inputs.items()},
        availability={k: "missing" if v is None else "provided" for k,v in inputs.items()},
        timeline_context=context, candidates=candidates,
        limitations=["Experimental suggestions, not validated narrative editing.",
            "Speech/OCR/clip-level timing is not precise gameplay event timing.",
            "Only one certain candidate-linked exact human interval can support expansion.",
            "No inference, ranking, selection, export or source-byte verification.",
            "Missing evidence is unknown; nearby events are never chained together."])
    result["plan_id"] = digest(result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, required=True)
    for name in ("annotations", "fusion", "timeline"):
        parser.add_argument("--"+name, type=Path)
    parser.add_argument("--min-duration", type=float, default=1)
    parser.add_argument("--max-duration", type=float, default=60)
    parser.add_argument("--max-extension", type=float, default=10)
    parser.add_argument("--heuristic-padding", type=float)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    paths = {k:getattr(args,k) for k in ("analysis","annotations","fusion","timeline") if getattr(args,k) is not None}
    try:
        result = build_plan(**{k:read_json(v) for k,v in paths.items()},
            min_duration=args.min_duration, max_duration=args.max_duration,
            max_extension=args.max_extension, heuristic_padding=args.heuristic_padding)
        publish(result, args.output, list(paths.values()))
        print(f"Saved {len(result['candidates'])} experimental boundary suggestions to {args.output}")
        return 0
    except (OSError, ValueError) as exc:
        print(f"FAIL: narrative boundaries: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
