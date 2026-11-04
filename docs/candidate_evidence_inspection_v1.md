# Candidate Evidence Inspection V1

Read-only inspection of the existing Candidate Evidence V1 JSON contract:
schema_version=1, report_type=candidate-evidence, inputs, identity_comparison,
and candidates. No existing schemas or producers change.

## Usage

    python inspect_candidate_evidence.py --evidence output/candidate_evidence_v1.json
    python inspect_candidate_evidence.py --evidence output/candidate_evidence_v1.json --format json
    python inspect_candidate_evidence.py --evidence output/candidate_evidence_v1.json --preview-limit 2 --preview-chars 120

The evidence file must already exist. Default output is readable terminal text;
JSON output is a structured inspection summary. There is no output-file option
and no files are created or modified. Exit codes: 0 success, 1 invalid input or
I/O error (stderr), 2 argument parsing error.

preview-limit defaults to 3 (0–20) per category per candidate; preview-chars
defaults to 160 (1–500) per transcript excerpt or prediction label. Omitted-event
counts and text/label truncation flags are explicit. Full observation counts
never depend on preview limits. Original strings are sliced without invented
text; terminal JSON quoting escapes control characters.

## What is reported

Original candidate position, ID/rank/anchor if present, start/end, computed
window duration, and available original scores are retained. Scores keep their
original field names; no new score or ranking is computed. The score whitelist
is score, normalized_score, highlight_score, scene_score, motion_score and
motion_highlight_score. Candidate provenance remains available in JSON.

Each candidate includes total and modality counts, scene-change count, original
coverage status, and bounded transcript, visual prediction, audio and scene
previews with source timestamps and source_order. Audio/scene previews include
only available volume, spike, score and normalized_score values. Visual previews
show the existing top3 ImageNet category/confidence predictions, explicitly
labeled model_predictions. Unknown event types are rejected rather than guessed.

Report-level counts show candidates with and without observations for transcript,
audio, visual and scene change. Scene changes are a subset of visual observations,
so these categories are not additive. Duplicate observations remain separate.
Candidates and previews retain stored order; shared-boundary observations may
appear in multiple candidates under the existing closed query semantics.

## Validation and identity

The pure inspect_evidence function validates the complete report before producing
a summary. It reuses Shared Analysis candidate validation and timeline/query
validation using the metadata already embedded in the report; it does not load
referenced artifacts or infer missing evidence. Unsupported versions, missing
fields, invalid counts/timestamps, inconsistent coverage or identities, malformed
payloads and events outside windows fail. Input objects are not mutated.

Reported source identity and timeline identity status are preserved. Consistent
reported SHA-256 claims do not mean video bytes were independently verified.
No source hashing, FFmpeg, GPU initialization, ML imports or inference occurs.

## Coverage limitations

The original observation statuses remain distinct:
observed_events, no_events_in_window, absent_from_timeline, not_established.
Temporal coverage remains unknown. An analyzed channel with no window matches
does not establish continuous coverage or prove that nothing interesting happened.

ImageNet labels are generic model predictions, not verified gameplay facts.
Counts are descriptive and do not establish multimodal understanding or ranking
improvement. The inspector cannot detect observations omitted from the supplied
artifact or validate claims against the original media.

## Local real-artifact inspection

On 2026-11-04, the saved Shared Analysis V1 artifact was loaded read-only. Its
timeline and Candidate Evidence report were built in memory; no production
evidence file was written. No compatible saved ResNet inference artifact was
available locally, so no visual predictions were substituted from other research.

| Original candidate index | Window (seconds) | Transcript | Audio | Visual | Scene changes |
| --- | --- | --- | --- | --- | --- |
| 0 | 30–45 | 3 | 0 | 0 | 0 |
| 1 | 59–74 | 2 | 0 | 0 | 0 |
| 2 | 74–89 | 2 | 0 | 0 | 0 |
| 3 | 136–151 | 1 | 0 | 0 | 0 |
| 4 | 160–175 | 2 | 0 | 0 | 0 |

All five have transcript observations. Audio and visual status is not_established:
the source audio_activity and scene_changes channels are not_analyzed.
All modalities have unknown temporal coverage. Both identity statuses are
consistent_reported_sha256, representing agreeing claims only.

The original candidates are preselected Audio-only anchors. Their stored scores
do not replace missing timeline observations. These saved artifacts currently
support transcript inspection, but do not supply audio/visual observations for
a comparative multimodal ranking experiment.

## Tests

    python -m unittest test_inspect_candidate_evidence test_candidate_evidence test_timeline_query -q
    python verify.py --cached-export --video videos/my_recording.mp4 --analysis output/shared_analysis_v1.json

Tests use synthetic fixtures, including visual predictions, and an isolated
import-safety check. No production media is processed.
