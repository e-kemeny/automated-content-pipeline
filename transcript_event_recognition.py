"""Conservative English phrase baseline over saved transcript observations only."""
import argparse
from copy import deepcopy
from pathlib import Path
import re
import sys

from multimodal_timeline import number, read_json, validate_timeline
from highlight_evaluation import digest, publish

DETECTOR = "transcript-gameplay-rules"
VERSION = 1
# Full-clause acceptance is intentionally narrower than diagnostic cue matching.
RULES = (
    dict(id="bed-completed-v1", event_type="bed_destroyed",
         cue=r"\b(?:break|broke|broken|breaking|destroy|destroyed)\b.{0,35}\bbed\b|\bbed\s+(?:(?:is|was)\s+)?(?:not\s+)?gone\b|\bbed break\b|\bgot (?:the|his|their) bed\b",
         completed=r"(?:i|we) (?:just )?(?:broke|destroyed) (?:his|her|their|your|the enemy's) bed|(?:his|her|their|our|your) bed (?:is|was) gone"),
    dict(id="victory-completed-v1", event_type="game_victory",
         cue=r"\b(?:win|won|winning)\b.{0,25}\b(?:game|match)\b|\b(?:we|i) (?:haven't|have not) won\b",
         completed=r"(?:i|we) (?:just )?won (?:the|this) (?:game|match)"),
    dict(id="death-completed-v1", event_type="player_death",
         cue=r"\b(?:i|we|he|she|they|you)\b.{0,25}\b(?:died|die)\b",
         completed=r"i (?:just )?died"),
    dict(id="elimination-completed-v1", event_type="player_elimination",
         cue=r"\b(?:kill|killed|eliminate|eliminated) (?:him|her|them|me|the player|that player)\b",
         completed=r"(?:i|we) (?:just )?(?:killed|eliminated) (?:him|her|them|the player|that player)"),
    dict(id="respawn-completed-v1", event_type="respawn",
         cue=r"\b(?:respawn|respawned|respawning)\b",
         completed=r"i (?:just )?respawned"),
    dict(id="transition-cue-v1", event_type="game_transition",
         cue=r"\bnext game\b|\b(?:started|starting|start) (?:a |the )?(?:new|next) game\b",
         completed=r"next game|(?:i|we) (?:just )?started (?:a new|the next) game"),
)
GUARDS = (
    ("question", r"\?|^\s*(?:did|do|does|have|has|had|can|could|would|will|is|are|why|how|what)\b|^\s*when\s+(?:did|do|does|will|can|have|has)\b"),
    ("negated", r"\b(?:not|never|no|without|didn't|don't|doesn't|haven't|hasn't|hadn't|isn't|wasn't|weren't|can't|couldn't|won't|wouldn't)\b"),
    ("hypothetical_future", r"\b(?:if|unless|when|would|will|gonna|going to|about to|next time|let's|want to|need to|hope to)\b"),
    ("uncertain", r"\b(?:almost|nearly|think|guess|maybe|perhaps|probably|apparently|seems?|might|may|could|looks like)\b"),
    ("ambiguous", r'["\u201c\u201d]|\b(?:said|says|say|quote|example|story|song|lyrics|joke|laughing|figuratively|heaven|furniture|mattress|chess|football)\b'),
)
LIMITATIONS = [
    "Deterministic English phrase rules, not AI, visual recognition or verified gameplay events.",
    "Speech intervals locate utterances; actual gameplay-event timing and relation to speech are unknown.",
    "Gameplay context is assumed, not proven; literal speech, irony, ASR errors and speaker attribution remain unresolved.",
    "Sentence-wide exclusion guards favor abstention and may suppress a separate genuine assertion in the same sentence.",
    "No matches or an empty transcript do not imply that gameplay events did not occur.",
    "Reported source identity is not independently verified; transcript temporal coverage and completeness are unknown.",
    "Human ground truth is separate; no precision, recall, F1 or evaluation is implemented.",
]


def classify_text(text):
    """Return ordered linguistic matches with spans into the unchanged text."""
    if not isinstance(text, str):
        raise ValueError("Transcript text must be a string")
    records = []
    for sentence in re.finditer(r"[^.!?;]+[.!?;]*", text):
        normalized = sentence.group().lower().replace("\u2019", "'")
        guards = [name for name, pattern in GUARDS if re.search(pattern, normalized)]
        # Split simple conjunctions only after checking whole-sentence exclusions.
        offset = 0
        for clause in re.split(r"\s+(?:and(?:\s+then)?|but|then)\s+", sentence.group(), flags=re.I):
            local = sentence.group().find(clause, offset)
            offset = local + len(clause)
            normalized_clause = clause.lower().replace("\u2019", "'")
            normalized_clause = re.sub(r"\s+", " ", normalized_clause).strip(" \t\r\n,.!?;")
            normalized_clause = re.sub(r"^(?:(?:oh|nice|okay|ok|yes|yeah|wow)[, ]+)+", "", normalized_clause)
            matches = []
            for rule_index, rule in enumerate(RULES):
                cue = re.search(rule["cue"], normalized_clause)
                if cue is None:
                    continue
                classification = guards[0] if guards else (
                    "asserted_completed" if re.fullmatch(rule["completed"], normalized_clause) else "ambiguous")
                matches.append((cue.start(), rule_index, dict(event_type=rule["event_type"],
                    rule_id=rule["id"], linguistic_classification=classification,
                    exclusion_guards=list(guards), evidence_span=[sentence.start()+local, sentence.start()+offset],
                    matched_clause=clause, sentence_text=sentence.group(),
                    reason=("Sentence-wide exclusion cue" if guards else
                            "Full-clause completed assertion or explicit transition cue" if classification=="asserted_completed"
                            else "Cue present without a supported completed assertion"))))
            records.extend(row for _, _, row in sorted(matches, key=lambda item: item[:2]))
    return records


def transcript_rows(timeline):
    """Validate native transcript payloads beyond generic timeline validation."""
    validate_timeline(timeline)
    rows = []
    for row in timeline["events"]:
        if row["modality"] != "transcript":
            continue
        try:
            payload = row["payload"]
            channel = timeline["sources"][row["source"]["artifact_index"]]["channels"][row["source"]["channel"]]
            if (row["event_type"] != "speech_segment" or row["observation_kind"] != "interval" or
                    row["source"]["channel"] != "transcript" or channel["status"] != "analyzed" or
                    not isinstance(payload["text"], str) or
                    number(payload["start"]) != row["start_seconds"] or
                    number(payload["end"]) != row["end_seconds"] or
                    "metadata" in payload and not isinstance(payload["metadata"], dict)):
                raise ValueError("Transcript payload, interval or channel disagrees with timeline")
        except (KeyError, TypeError) as exc:
            raise ValueError("Malformed transcript payload") from exc
        rows.append(row)
    return rows


def recognize_events(timeline, *, input_reference=None):
    """Pure saved-data recognition; preserve input order, text and timestamps."""
    rows = transcript_rows(timeline)
    timeline_digest = digest(timeline)
    hypotheses, excluded = [], []
    matched_segments = 0
    for observation_index, observation in enumerate(rows):
        text = observation["payload"]["text"]
        matches = classify_text(text)
        matched_segments += bool(matches)
        source = timeline["sources"][observation["source"]["artifact_index"]]
        for match_index, match in enumerate(matches):
            record = dict(match,
                hypothesis_id=digest(dict(timeline=timeline_digest, observation=observation_index, match=match_index)),
                source="transcript_rule_hypothesis", evidence_text=text,
                transcript_interval=dict(start_seconds=observation["start_seconds"], end_seconds=observation["end_seconds"]),
                temporal_uncertainty=dict(gameplay_event_start_seconds=None, gameplay_event_end_seconds=None,
                                          relation_to_speech="unknown"),
                observation_index=observation_index, original_observation=deepcopy(observation),
                source_video_claim=deepcopy(source["source_video"]),
                source_identity_status=timeline["identity_status"])
            (hypotheses if match["linguistic_classification"]=="asserted_completed" else excluded).append(record)
    channels = [dict(artifact_index=i, **deepcopy(source["channels"]["transcript"]))
                for i, source in enumerate(timeline["sources"]) if "transcript" in source["channels"]]
    usable = sum(bool(row["payload"]["text"].strip()) for row in rows)
    status = "analyzed" if usable else ("analyzed_empty" if any(c["status"]=="analyzed" for c in channels) else "not_analyzed")
    return dict(schema_version=1, artifact_type="transcript-event-hypotheses",
        detector=dict(name=DETECTOR, version=VERSION, method="scoped_english_phrase_rules", rules=deepcopy(list(RULES)),
                      guards=[dict(classification=name, pattern=pattern) for name, pattern in GUARDS]),
        status=status, input_provenance=dict(reference=input_reference, timeline_schema_version=timeline["schema_version"],
            timeline_sha256=timeline_digest, sources=deepcopy(timeline["sources"])),
        source_identity_status=timeline["identity_status"], source_identity=deepcopy(timeline["source_identity"]),
        hypotheses=hypotheses, excluded_matches=excluded,
        transcript_coverage=dict(observation_count=len(rows), usable_text_count=usable,
            segments_with_rule_cues=matched_segments, segments_without_rule_cues=len(rows)-matched_segments,
            temporal_coverage="unknown", speaker_role="unverified", channels=channels),
        limitations=list(LIMITATIONS))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = recognize_events(read_json(args.timeline), input_reference=str(args.timeline))
        publish(result, args.output, [args.timeline], args.overwrite)
    except (OSError, ValueError) as exc:
        print(f"FAIL: transcript events: {exc}", file=sys.stderr)
        return 1
    print(f"Saved {args.output}: {result['status']}; {len(result['hypotheses'])} hypotheses; "
          f"{len(result['excluded_matches'])} excluded matches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
