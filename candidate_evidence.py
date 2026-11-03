"""Retrieve persisted timeline evidence for Shared Analysis V1 candidate windows."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

from shared_analysis import validate_analysis
from multimodal_timeline import MODALITIES, read_json, source_metadata, validate_timeline
from timeline_query import query_timeline, save_query

ROOT = Path(__file__).resolve().parent
CHANNEL_MODALITY = {"audio_activity": "audio", "scene_changes": "visual",
                    "frames": "visual", "transcript": "transcript"}


def compare_identity(analysis, timeline):
    """Reject conflicting reported claims; never verify source bytes."""
    headers = [analysis["source_video"]] + [s["source_video"] for s in timeline["sources"]]
    claims = list(headers)
    provenance = [analysis["candidate_windows"]["provenance"]]
    provenance += [c["provenance"] for s in timeline["sources"] for c in s["channels"].values()]
    for item in provenance:
        claims.append({new:item[old] for old, new in
                       (("source_sha256", "sha256"), ("source_duration_seconds", "duration_seconds"))
                       if old in item})
    known = {}
    for claim in claims:
        source_metadata(claim)
        for key in ("sha256", "duration_seconds", "width", "height", "fps", "size_bytes"):
            if key in claim:
                if key in known and known[key] != claim[key]:
                    raise ValueError(f"Conflicting source identity: {key}")
                known[key] = claim[key]
    return ("consistent_reported_sha256" if all("sha256" in s for s in headers)
            else "unverified_missing_source_digest")


def evidence_coverage(timeline, counts):
    """Channel availability is not continuous temporal coverage."""
    result = {}
    for modality in MODALITIES:
        channels = [dict(artifact_index=i, channel=name, status=channel["status"])
                    for i, source in enumerate(timeline["sources"])
                    for name, channel in source["channels"].items()
                    if CHANNEL_MODALITY.get(name) == modality]
        present = bool(channels) or any(e["modality"] == modality for e in timeline["events"])
        if counts[modality]:
            observation_status = "observed_events"
        elif not present:
            observation_status = "absent_from_timeline"
        elif any(c["status"] == "analyzed" for c in channels):
            observation_status = "no_events_in_window"
        else:
            observation_status = "not_established"
        result[modality] = dict(observation_status=observation_status,
                               temporal_coverage="unknown", channels=channels)
    return result


def build_candidate_evidence(candidates, timeline, *, candidate_reference=None, timeline_reference=None):
    """Pure retrieval; preserve original candidate and observation order."""
    analysis = validate_analysis(candidates)
    validate_timeline(timeline)
    envelope = analysis["candidate_windows"]
    if envelope["status"] != "analyzed":
        raise ValueError("Shared Analysis candidate_windows must be analyzed")
    identity_status = compare_identity(analysis, timeline)
    reports = []
    for index, candidate in enumerate(envelope["data"]):
        matched = query_timeline(timeline, candidate["start"], candidate["end"])
        reports.append(dict(candidate_index=index, candidate=deepcopy(candidate),
                            window=dict(start=candidate["start"], end=candidate["end"]),
                            events=matched["events"], matched_event_count=matched["matched_event_count"],
                            counts_by_modality=matched["counts_by_modality"],
                            evidence_coverage=evidence_coverage(timeline, matched["counts_by_modality"])))
    return dict(schema_version=1, report_type="candidate-evidence",
                inputs=dict(candidates=dict(reference=candidate_reference,
                    schema_version=analysis["schema_version"],
                    source_video=deepcopy(analysis["source_video"]),
                    status=envelope["status"], provenance=deepcopy(envelope["provenance"])),
                    timeline=dict(reference=timeline_reference,
                        schema_version=timeline["schema_version"],
                        identity_status=timeline["identity_status"],
                        source_identity=deepcopy(timeline["source_identity"]),
                        sources=deepcopy(timeline["sources"]))),
                identity_comparison=identity_status, candidates=reports)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True, help="Shared Analysis V1 JSON")
    parser.add_argument("--timeline", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    if args.overwrite and args.output is None:
        parser.error("--overwrite requires --output")
    try:
        if args.output is not None:
            path = args.output
            if any(path.resolve() == source.resolve() or
                   path.exists() and source.exists() and path.samefile(source)
                   for source in (args.candidates, args.timeline)):
                raise ValueError("Output must not replace an input artifact")
            if path.resolve().is_relative_to(ROOT) and not path.resolve().is_relative_to(ROOT/"output"):
                raise ValueError("Repository output must be under ignored output/")
            if path.exists() and args.overwrite:
                prior = read_json(path)
                if not isinstance(prior, dict) or prior.get("report_type") != "candidate-evidence" or prior.get("schema_version") != 1:
                    raise ValueError("Refusing to overwrite an unrelated artifact")
        result = build_candidate_evidence(read_json(args.candidates), read_json(args.timeline),
                                          candidate_reference=str(args.candidates),
                                          timeline_reference=str(args.timeline))
        if args.output is not None:
            save_query(result, args.output, args.overwrite)
        print(json.dumps(result, separators=(",", ":"), allow_nan=False))
    except (OSError, ValueError) as exc:
        print(f"FAIL: candidate evidence: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
