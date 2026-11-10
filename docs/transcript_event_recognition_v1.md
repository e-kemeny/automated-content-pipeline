# Experimental Transcript Gameplay Event Recognition V1

An isolated, deterministic English phrase baseline over **saved transcript observations**. It is not a language model, visual recognition, or evidence that the system understands BedWars. It never changes human ground truth, Shared Analysis, ranking, clip boundaries or exports.

## Commands

If a compatible timeline already exists:

    python transcript_event_recognition.py --timeline output/multimodal_timeline_v1.json --output output/transcript_event_hypotheses_v1.json

On the inspected laptop, that default timeline file was absent. To create a separate timeline from saved analysis (no transcription, media processing or inference):

    python multimodal_timeline.py --analysis output/shared_analysis_v1.json --output output/transcript_event_timeline_v1.json
    python transcript_event_recognition.py --timeline output/transcript_event_timeline_v1.json --output output/transcript_event_hypotheses_v1.json

Output publication uses the existing atomic JSON helper. Existing outputs require explicit --overwrite; input aliases, symlinks and unrelated artifact types are protected. In-repository output must be under ignored output/. Use separate experimental filenames and no concurrent writers.

## Input actually supported

Multimodal Timeline V1 stores transcript observations as:

- modality: transcript, event_type: speech_segment, observation_kind: interval.
- start_seconds / end_seconds: original ASR utterance bounds.
- payload: original start, end, text and optional metadata.
- source: artifact index, channel transcript, original row index and provenance.
- source_order: stable order, including duplicate observations.

The recognizer validates the timeline, matching native payload timestamps/text, analyzed transcript-channel status and source consistency. It does not read candidate scores or reinterpret visual/audio rows as speech. Original text, payload, timestamps, provenance and duplicate rows survive in matched records. Matches follow stored observation order and textual order within each segment; no merging or deduplication occurs.

The existing 19-segment transcript was produced by faster-whisper small.en, CPU/int8, with word timestamps disabled. Its text mixes texture-pack narration and gameplay reactions. There is no diarization or verified player/narrator attribution, so speaker_role remains unverified. ASR wording itself may be inaccurate.

## Rules and exclusions

The six rule IDs and exact regular expressions are included in every output artifact. Accepted clauses are narrow; bare bed, win, dead and kill are insufficient.

| Event type | Accepted examples | Rule |
| --- | --- | --- |
| bed_destroyed | I broke his bed; Their bed is gone | bed-completed-v1 |
| game_victory | We won the game | victory-completed-v1 |
| player_death | I died | death-completed-v1 |
| player_elimination | I eliminated him; We killed that player | elimination-completed-v1 |
| respawn | I respawned | respawn-completed-v1 |
| game_transition | Next game; We started the next game | transition-cue-v1 |

Limited pronoun, past-verb and just variants are supported, along with case/whitespace normalization and a few conversational prefixes such as “Oh” and “Nice.” “Next game” is treated as an explicit spoken transition cue, not proof that a visual transition completed.

Diagnostic cues are broader than acceptance patterns. They can retain “got the bed” or “bed break” for review without asserting an event. No rule confidence probability is generated.

Sentence-wide exclusion guards run before full-clause acceptance:

1. question: question marks or scoped interrogative prefixes.
2. negated: obvious negation, including common contractions.
3. hypothetical_future: if/unless/when, will, going to, about to, wants/plans expressed by supported phrases.
4. uncertain: almost, nearly, think, guess, maybe and similar supported uncertainty words.
5. ambiguous: quotation/reported-speech cues and selected everyday/figurative contexts.

All triggered guards are recorded; the first supplies the primary diagnostic classification. Unguarded cues that do not match a complete accepted clause are also ambiguous. asserted_completed records alone enter hypotheses; others enter excluded_matches. For example, “I didn't break his bed,” “We haven't won yet,” “I'm going to break their bed,” “If I win this game,” “I almost died,” “Did I kill him?” and “I think his bed is gone” are excluded.

Simple sentence punctuation and conjunctions permit multiple explicit events per segment. Exclusions intentionally apply to the whole sentence: “I didn't break his bed but I died” excludes both cues, rather than guessing grammatical scope. “When I break their bed” is conditional; “When did I break their bed?” is a question. Synthetic testing caught and corrected this distinction before the real smoke test. No rules were tuned to ground truth, retention or desired real-data detection counts.

This is not a general parser. Narrow acceptance and some everyday-context guards reduce false assertions, but identical wording can occur outside gameplay, in irony, or in quotations missed by ASR. Context is assumed by the caller, not independently established. Unsupported paraphrases, cross-segment assertions and unclear scope favor abstention.

## Output and timing

The artifact has schema_version: 1, artifact_type: transcript-event-hypotheses, detector name/version/rules/guards, input provenance and timeline digest, reported source identity, hypotheses, excluded matches, transcript coverage and limitations.

Each match preserves event type, rule ID, linguistic classification, exact full evidence text, matched clause and its character span, sentence text, original observation, source claim and exclusion reason. Stable IDs include the input timeline digest and observation/match indexes; duplicates remain separate.

transcript_interval locates the **utterance**. temporal_uncertainty explicitly leaves gameplay-event start/end null and its relation to speech unknown. A speaker may recount an earlier event or discuss something elsewhere. Speech timestamps are never exported as exact gameplay-event timestamps.

Statuses distinguish:
- not_analyzed: absent/unavailable transcript evidence.
- analyzed_empty: an analyzed channel with no usable transcript text.
- analyzed: rules examined available nonblank observations, even if no hypotheses matched.

Counts describe observations and rule cues only. Continuous transcript coverage/completeness stays unknown. Silence, missing text or zero detections are not negative gameplay labels.

Source statuses retain the timeline convention: consistent_reported_sha256 or unverified_single_artifact. Neither verifies current video bytes. Missing digests remain explicit; conflicting header/channel claims fail validation. All source records remain available even when the optional complete identity object is null.

## Actual saved-data smoke test

A temporary timeline was built from the existing saved analysis, then the CLI ran against it. No ASR, model, video processing or cache updates occurred; temporary files were removed.

- 19 usable transcript observations.
- 0 completed-event hypotheses.
- 4 excluded matches; 15 segments without rule cues.

| Utterance interval (s) | Event cue | Classification | Preserved clause |
| --- | --- | --- | --- |
| 31.6-42.21 | bed_destroyed | ambiguous | Oh bet I love the bed break it's so clean. |
| 44.35-52.9 | bed_destroyed | hypothetical_future | Nice got the bed you want to play you want to play the exploding |
| 78.78-87.01 | player_elimination | hypothetical_future | Ah I will let you kill me boy. |
| 127.54-131.94 | player_elimination | hypothetical_future | Imagine if you got somebody's fireballs when you killed them. |

The second exclusion demonstrates deliberately broad sentence guard scope: “want to” blocks a fragment containing “got the bed”; this does not establish that the bed statement itself is future-tense. These mixed narration/reaction fragments do not satisfy the narrow completed-assertion rules. No event absence, accuracy or usefulness claim follows from zero hypotheses.

## Ground-truth evaluation: deferred

Gameplay Event Ground Truth V1 requires source: human and separate exact/clip-level precision semantics. Hypotheses intentionally use a different artifact and source; they cannot silently become human annotations.

The current human annotation contract has no exhaustive scope declaration, and utterance intervals cannot establish gameplay timing compatibility. Defining a reviewed evaluation scope and speech-to-event temporal relation is a separate milestone. No annotation comparisons, precision, recall or F1 are implemented. Empty human templates must never become negative examples.

## Tests

    python -m unittest test_transcript_event_recognition -q
    python verify.py --cached-export --video videos/my_recording.mp4 --analysis output/shared_analysis_v1.json

Synthetic tests cover positives/exclusions, everyday speech, multiple/duplicate observations, timing and schema validation, identity handling, missing/empty transcripts, deterministic output, publication protection and import safety. Standard library and existing lightweight schema helpers only; no new dependencies.
