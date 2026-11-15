"""Experimental saved-evidence grouping; no inference, ranking or event confirmation."""
import argparse
from copy import deepcopy
from pathlib import Path
import re
import sys

from highlight_evaluation import digest, publish
from multimodal_timeline import json_value, number, read_json, reconcile, validate_timeline
from ocr_evidence_interpretation import interpret_evidence
from source_identity import validate_identity
from transcript_event_recognition import transcript_rows, classify_text, DETECTOR, VERSION, RULES, GUARDS


# Narrow generic synonyms only. Specific objectives are not equivalent to all objectives.
ALIASES = {"game_victory": "victory", "player_death": "death",
           "player_elimination": "kill", "game_transition": "transition"}


def envelope(data, kind):
    json_value(data)
    if (not isinstance(data, dict) or type(data.get("schema_version")) is not int
            or data["schema_version"] != 1 or data.get("artifact_type") != kind):
        raise ValueError("Unsupported " + kind + " schema")


def sha(value):
    if not isinstance(value, str) or not re.fullmatch("[0-9a-f]{64}", value):
        raise ValueError("Missing/invalid provenance digest")
    return value


def validate_transcript(data):
    envelope(data, "transcript-event-hypotheses")
    sources = data["input_provenance"]["sources"]
    reconciled = reconcile(sources)
    if (data["source_identity"] != reconciled["source_identity"]
            or data["source_identity_status"] != reconciled["identity_status"]
            or type(data["input_provenance"]["timeline_schema_version"]) is not int
            or data["input_provenance"]["timeline_schema_version"] != 1):
        raise ValueError("Transcript identity/provenance mismatch")
    sha(data["input_provenance"]["timeline_sha256"])
    detector = data["detector"]
    expected_detector = dict(name=DETECTOR, version=VERSION, method="scoped_english_phrase_rules",
                             rules=list(RULES), guards=[dict(classification=k, pattern=v) for k, v in GUARDS])
    if detector != expected_detector or type(detector["version"]) is not int:
        raise ValueError("Unsupported transcript detector provenance")
    if data["status"] not in ("analyzed", "analyzed_empty", "not_analyzed"):
        raise ValueError("Invalid transcript status")
    if not isinstance(data["transcript_coverage"], dict):
        raise ValueError("Missing transcript coverage")
    if any(not isinstance(data[k], list) for k in ("hypotheses", "excluded_matches")):
        raise ValueError("Malformed transcript records")
    rules = {r["id"]: r["event_type"] for r in detector["rules"]}
    seen = {}
    for accepted, records in ((True, data["hypotheses"]), (False, data["excluded_matches"])):
        for row in records:
            identifier = sha(row["hypothesis_id"])
            if identifier in seen and seen[identifier] != row:
                raise ValueError("Conflicting duplicate hypothesis ID")
            seen[identifier] = row
            observation = row["original_observation"]
            subset = dict(schema_version=1, timeline_type="multimodal-observations",
                          sources=sources, events=[observation], **reconciled)
            transcript_rows(subset)
            source = sources[observation["source"]["artifact_index"]]
            if (row["source_video_claim"] != source["source_video"]
                    or row["source_identity_status"] != reconciled["identity_status"]
                    or row["source"] != "transcript_rule_hypothesis"
                    or row["evidence_text"] != observation["payload"]["text"]
                    or row["transcript_interval"] != dict(start_seconds=observation["start_seconds"],
                                                         end_seconds=observation["end_seconds"])
                    or row["temporal_uncertainty"] != dict(gameplay_event_start_seconds=None,
                        gameplay_event_end_seconds=None, relation_to_speech="unknown")
                    or rules.get(row["rule_id"]) != row["event_type"]):
                raise ValueError("Transcript record disagrees with original evidence")
            # Replay only the existing lightweight text contract, never a model or ASR.
            matches = classify_text(row["evidence_text"])
            fields = ("event_type", "rule_id", "linguistic_classification", "exclusion_guards",
                      "evidence_span", "matched_clause", "sentence_text", "reason")
            if not any(all(row[k] == m[k] for k in fields) for m in matches):
                raise ValueError("Transcript hypothesis does not match its saved text")
            if accepted != (row["linguistic_classification"] == "asserted_completed"):
                raise ValueError("Excluded transcript match cannot become a hypothesis")
    if data["hypotheses"] and data["status"] != "analyzed":
        raise ValueError("Transcript hypotheses require analyzed status")
    return sources


def validate_ocr(data):
    envelope(data, "ocr-evidence-interpretation")
    expected = interpret_evidence(data["input_evidence"], profile=data["profile"])
    for key in ("status", "profile", "input_evidence_digest", "interpretations"):
        if data[key] != expected[key]:
            raise ValueError("OCR interpretation disagrees with saved evidence/profile")
    if type(data["unknown_game_fallback"]) is not bool:
        raise ValueError("Invalid unknown-game status")
    raw = data["input_evidence"]
    if raw is None:
        return []
    manifest = raw["visual_evidence_provenance"]["manifest"]
    if (type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1
            or manifest["artifact_type"] != "visual-evidence"
            or manifest["source_identity"] != raw["source_identity"]):
        raise ValueError("OCR embedded manifest identity mismatch")
    from visual_evidence import TIME_BASIS
    if manifest["extraction_provenance"]["time_basis"] != TIME_BASIS:
        raise ValueError("Unsupported OCR time basis")
    sha(raw["visual_evidence_provenance"]["manifest_sha256"])
    identity = validate_identity(raw["source_identity"])
    if manifest["video_duration_seconds"] != identity["media"]["duration_seconds"]:
        raise ValueError("OCR manifest duration mismatch")
    frames = {f["frame_id"]: f for f in manifest["frames"]}
    if len(frames) != len(manifest["frames"]):
        raise ValueError("Duplicate OCR manifest frame ID")
    for observation in raw["observations"]:
        frame = frames[observation["parent_frame_id"]]
        if observation["timestamp"] != {k: frame[k] for k in ("normalized_pts", "time_base", "timestamp_seconds")}:
            raise ValueError("OCR observation timestamp differs from embedded frame")
        if observation["kind"] == "full":
            expected_image = {k: v for k, v in frame.items() if k != "regions"}
        else:
            candidates = [r for r in frame["regions"] if r["region_name"] == observation["region_name"]]
            if len(candidates) != 1:
                raise ValueError("OCR crop has no unique embedded region")
            expected_image = candidates[0]
        if observation["image"] != expected_image:
            raise ValueError("OCR image/crop provenance differs from embedded frame")
    return [dict(kind="vision", artifact="embedded_ocr_source",
                 source_video=dict(sha256=identity["digest"], size_bytes=identity["size_bytes"], **identity["media"]),
                 channels={})]


def overlaps(left, right):
    """Half-open intervals; points inside [start,end), equal points overlap."""
    a, b = left
    c, d = right
    if a == b:
        return a == c if c == d else c <= a < d
    if c == d:
        return a <= c < b
    return max(a, c) < min(b, d)


def fuse_events(*, transcript=None, ocr=None, timeline=None,
                ocr_time_offset_seconds=None, alignment_reference=None):
    """Pure adapters and deterministic complete-link grouping of semantic hypotheses."""
    try:
        return _fuse(transcript, ocr, timeline, ocr_time_offset_seconds, alignment_reference)
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        raise ValueError("Malformed fusion input") from exc


def _fuse(transcript, ocr, timeline, offset, alignment_reference):
    if (offset is None) != (alignment_reference is None):
        raise ValueError("OCR offset and alignment reference must be supplied together")
    if offset is not None:
        number(offset)
        if ocr is None or not isinstance(alignment_reference, str) or not alignment_reference.strip():
            raise ValueError("Alignment requires OCR and a nonempty reference")
    inputs = dict(transcript=transcript, ocr=ocr, timeline=timeline)
    sources = []
    if transcript is not None:
        sources.extend(validate_transcript(transcript))
    if ocr is not None:
        sources.extend(validate_ocr(ocr))
    if timeline is not None:
        validate_timeline(timeline)
        sources.extend(timeline["sources"])
        if transcript is not None and digest(timeline) != transcript["input_provenance"]["timeline_sha256"]:
            raise ValueError("Timeline does not match transcript input provenance")
    # Multiple artifacts require a reported digest for every source, even if empty.
    identity = reconcile(sources) if sources else dict(
        identity_status="unknown", source_identity=None, duration_seconds=None)
    duration = identity["duration_seconds"]
    evidence, contexts, duplicates = [], [], []
    seen = {}

    def add(modality, event_type, bounds, clock, reference, original, method):
        start, end = bounds
        if not 0 <= number(start) <= number(end) or duration is not None and end > duration:
            raise ValueError("Aligned evidence is outside source duration")
        # Exact duplicate records are preserved in inputs but counted only once.
        identifier = digest(dict(modality=modality, original=original))
        row = dict(evidence_id=identifier, modality=modality, original_event_type=event_type,
                   canonical_event_type=ALIASES.get(event_type, event_type), clock=clock,
                   alignment_interval=dict(start_seconds=start, end_seconds=end),
                   original_reference=reference, original_evidence=deepcopy(original),
                   detection_method=deepcopy(method),
                   uncertainty="observation timing only; actual gameplay event timing and attribution unknown")
        if identifier in seen:
            duplicates.append(dict(evidence_id=identifier, reference=reference))
        else:
            seen[identifier] = row
            evidence.append(row)

    if transcript is not None:
        for i, row in enumerate(transcript["hypotheses"]):
            interval = row["transcript_interval"]
            add("transcript", row["event_type"], (interval["start_seconds"], interval["end_seconds"]),
                "source_timeline", dict(input="transcript", hypothesis_index=i, hypothesis_id=row["hypothesis_id"]),
                row, transcript["detector"])
    if ocr is not None and ocr["input_evidence"] is not None:
        raw = ocr["input_evidence"]
        observations = {r["observation_id"]: r for r in raw["observations"]}
        for i, interpretation in enumerate(ocr["interpretations"]):
            observation = observations[interpretation["observation_id"]]
            second = observation["timestamp"]["timestamp_seconds"]
            for j, hypothesis in enumerate(interpretation["hypotheses"]):
                time = second + (offset if offset is not None else 0)
                add("ocr", hypothesis["event_type"], (time, time),
                    "source_timeline" if offset is not None else "ocr_first_decoded_frame",
                    dict(input="ocr", interpretation_index=i, hypothesis_index=j,
                         observation_id=observation["observation_id"]),
                    dict(observation=observation, hypothesis=hypothesis),
                    dict(method="literal_phrase_rules", profile=ocr["profile"], backend=raw["backend"]))
    if timeline is not None:
        seen_context = set()
        for i, row in enumerate(timeline["events"]):
            # Stable source_order is a locator, not independent evidence.
            key = digest({k: v for k, v in row.items() if k != "source_order"})
            if key in seen_context:
                duplicates.append(dict(context_id=key, reference=dict(input="timeline", event_index=i)))
                continue
            seen_context.add(key)
            contexts.append(dict(context_id=key, reference=dict(input="timeline", event_index=i),
                                 original_observation=deepcopy(row), role="temporal_context_only"))
    evidence.sort(key=lambda e: (e["clock"], e["alignment_interval"]["start_seconds"],
                                e["alignment_interval"]["end_seconds"], e["canonical_event_type"], e["evidence_id"]))
    groups = []
    def bounds(e):
        return tuple(e["alignment_interval"][k] for k in ("start_seconds", "end_seconds"))
    for row in evidence:
        group = next((g for g in groups if g["event_type"] == row["canonical_event_type"]
                      and g["clock"] == row["clock"]
                      and all(overlaps(bounds(row), bounds(member)) for member in g["members"])), None)
        if group is None:
            group = dict(event_type=row["canonical_event_type"], clock=row["clock"], members=[])
            groups.append(group)
        group["members"].append(row)
    for group in groups:
        members = group["members"]
        modalities = sorted({e["modality"] for e in members})
        group.update(group_id=digest([e["evidence_id"] for e in members]), status="hypothesis_evidence_group",
                     evidence_count=len(members), hypothesis_modalities=modalities,
                     source_agreement="cross_modality_label_overlap" if len(modalities) > 1 else "single_modality",
                     gameplay_event_interval=None,
                     observation_envelope=dict(start_seconds=min(bounds(e)[0] for e in members),
                                               end_seconds=max(bounds(e)[1] for e in members)))
        group["context_references"] = [
            c["context_id"] for c in contexts if group["clock"] == "source_timeline"
            and all(overlaps(bounds(e), (c["original_observation"]["start_seconds"],
                                        c["original_observation"]["end_seconds"])) for e in members)]
    return dict(schema_version=1, artifact_type="multimodal-event-fusion",
                source_identity=identity, inputs=deepcopy(inputs),
                input_digests={k: digest(v) if v is not None else None for k, v in inputs.items()},
                modalities={k: dict(status="missing" if v is None else "provided",
                                    temporal_coverage="unknown") for k, v in inputs.items()},
                coverage=dict(
                    transcript=None if transcript is None else deepcopy(transcript["transcript_coverage"]),
                    ocr=None if ocr is None else dict(status=ocr["status"],
                        observations=[dict(observation_id=r["observation_id"], status=r["status"])
                                      for r in ocr["interpretations"]],
                        extraction=None if ocr["input_evidence"] is None else deepcopy(ocr["input_evidence"]["coverage"])),
                    timeline=None if timeline is None else [deepcopy(s["channels"]) for s in timeline["sources"]]),
                alignment=dict(ocr_time_offset_seconds=offset, reference=alignment_reference,
                               status="caller_declared" if offset is not None else "cross_clock_unverified"),
                policy=dict(aliases=dict(ALIASES), grouping="exact canonical label; pairwise overlap; no proximity tolerance",
                            boundaries="half-open intervals; equal points overlap"),
                groups=groups, context_observations=contexts, duplicate_references=duplicates,
                limitations=[
                    "Groups are review hypotheses, not confirmed events, independent votes or confidence scores.",
                    "Speech, frame and clip observations do not establish precise gameplay-event times.",
                    "Clock alignment is caller-declared, never inferred from matching video identity.",
                    "Raw timeline observations are context only and never increase semantic agreement.",
                    "Repeated frames/crops may be correlated; counts are not independent evidence counts.",
                    "Missing modalities, zero hypotheses or sparse observations are not negative evidence.",
                    "Reported source identities and provenance are checked for consistency, not video-byte authenticity.",
                ])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("transcript", "ocr", "timeline"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--ocr-time-offset-seconds", type=float)
    parser.add_argument("--alignment-reference")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    paths = {k: getattr(args, k) for k in ("transcript", "ocr", "timeline") if getattr(args, k) is not None}
    if not paths:
        parser.error("At least one saved input is required")
    try:
        result = fuse_events(**{k: read_json(v) for k, v in paths.items()},
                             ocr_time_offset_seconds=args.ocr_time_offset_seconds,
                             alignment_reference=args.alignment_reference)
        publish(result, args.output, list(paths.values()))
        print(f"Saved {len(result['groups'])} hypothesis evidence groups to {args.output}")
        return 0
    except (OSError, ValueError) as exc:
        print(f"FAIL: event fusion: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
