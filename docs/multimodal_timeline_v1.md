# Multimodal timeline V1

A standalone data layer places existing observations on the same video-time axis.
It does not perform multimodal reasoning, inference, ranking, score fusion or
export planning. Shared Analysis and existing producers remain unchanged.

## Supported inputs

- --analysis: a complete Shared Analysis schema_version 1 document, validated
  with its existing validator. Reads acoustic.audio_activity.data (second),
  visual.scene_changes.data (time), and transcript.data (start/end/text).
  Signal status and provenance are preserved. Rows with a spike field become
  audio_spike_score; other audio rows become audio_activity. Negative spike values
  remain negative; the type does not mean a positive spike or a detected fight.
- --transcript: either Shared Analysis V1 (transcript only), or the existing
  transcription.transcribe_media return object serialized to JSON:
  {"segments": [...], "provenance": {...}}. Its source_sha256 and
  source_duration_seconds provenance fields describe the source when present.
  The existing transcribe_video CLI saves Shared Analysis, not a separate
  transcript file; no new transcript export is required.
- --vision: vision_inference.py schema_version 1, experiment vision-inference-v1:
  video, model, sampling, runtime and frames. Each frame has timestamp_seconds
  and top3 category/confidence entries. The original frame row, including latency,
  is preserved; model/runtime/sampling headers are retained as provenance.

main.py returns score-ranked audio rows (second/spike/score plus optional later
scores) and scene rows (time/score). It does not persist a standalone audio/scene
JSON contract. These rows are supported through their existing Shared Analysis
envelopes. Public audio_events and scene_events helpers also convert supplied rows;
build_timeline validates the assembled result. No text logs or raw arrays are
guessed into a source artifact.

Motion, semantic_frames, semantic_events, candidate windows and language scores
inside Shared Analysis are deliberately not adapted in V1. CLIP/temporal/VLM
research files use different schemas and are rejected by --vision; their
predictions are not relabeled as ResNet evidence. Unknown input versions, absent
timestamps and malformed structures fail; no observations are silently repaired.

Local inspection found 19 transcript segments in shared_analysis_v1.json, with
audio_activity and scene_changes marked not_analyzed. This tool will not invent
those missing observations or recover them from selected candidate scores.

## Exact output schema

Top-level fields:

- schema_version: integer 1.
- timeline_type: "multimodal-observations".
- duration_seconds: known source duration, or null.
- identity_status: "consistent_reported_sha256" or "unverified_single_artifact".
- source_identity: existing source_identity.py version-1 contract, or null.
- sources: ordered artifact records.
- events: sorted normalized observations.

Each sources entry contains:

- kind: analysis, transcript or vision (the selected adapter).
- artifact: CLI input path; the adapter name for unlabeled in-memory input.
- source_video: original native source metadata (or transcript provenance's
  source_sha256/source_duration_seconds mapped to sha256/duration_seconds).
- channels: channel name -> {status, provenance}. Status retains analyzed versus
  not_analyzed for Shared Analysis. Valid standalone results are analyzed,
  including empty results.

Each event contains exactly the following fields:

    {
      "modality": "audio",
      "event_type": "audio_spike_score",
      "observation_kind": "point",
      "start_seconds": 3,
      "end_seconds": 3,
      "source_order": 0,
      "source": {
        "artifact_index": 0,
        "channel": "audio_activity",
        "row_index": 0,
        "provenance": {}
      },
      "payload": {"second": 3, "spike": -2, "score": 4}
    }

This example is synthetic, not a real video finding. Allowed modalities are
audio, visual and transcript. Adapter event types are audio_activity,
audio_spike_score, scene_change, speech_segment and imagenet_frame_prediction.
The full original observation is deep-copied into payload; probabilities, scores,
text, words and metadata are not rescaled or interpreted as highlight scores.
No confidence, gameplay labels or event durations are manufactured.

## Timing and ordering

All times are seconds relative to the source video's beginning. Points have
equal start/end; intervals preserve their original boundaries, interpreted as
[start,end). A zero-length transcript remains explicitly an interval, distinct
from a point. A point at the known duration is allowed; no extrapolation is made.
Vision timestamps remain requested seek times, not measured decoded-frame PTS.

Finite numeric times (not booleans or strings) must satisfy 0 <= start <= end
and end <= known duration. Original numeric precision is retained, with no
rounding. Events sort by start, end, modality and source_order.

Input order is fixed: analysis, transcript, vision. Within analysis it is audio,
scene, transcript; original row order is retained for ties. source_order records
that pre-sort position. CLI flag ordering does not change this order.
Existing Shared Analysis and transcription validators still require chronological
rows within their original schemas. No cross-input deduplication occurs; providing
the same transcript in two inputs will retain both observations.

## Identity policy

No source media is opened, probed or hashed. Reported SHA-256 fields are compared,
not independently verified. Filename/path equality is never proof of identity.
Known shared duration, dimensions, FPS and byte count must agree exactly; reported
channel provenance hashes/durations must also agree. Different hashes or conflicting
metadata fail, including contradictions inside a single artifact.

Combining separate inputs requires every artifact to report a valid source
SHA-256, even if an artifact has no events. Without it, only a single input is
permitted and explicitly labeled unverified_single_artifact. Missing duration
means no upper bound can be checked, but nonnegative finite timing is still required.
A full identity is never fabricated from filename, duration or absent metadata.

When reported digest, byte count, duration, width and height are available,
source_identity contains version=1, algorithm=sha256, digest, size_bytes and media
(duration_seconds/width/height, optionally fps), validated by the existing
source_identity.validate_identity function. Partial native evidence remains in
sources; source_identity is null when the existing contract cannot be populated.
The label consistent_reported_sha256 means consistency of artifact claims only,
not fresh verification of source bytes. No new content identity algorithm,
manifest version or cache contract is introduced.

## CLI and partial results

    python multimodal_timeline.py --analysis output/shared_analysis_v1.json
    python multimodal_timeline.py --transcript output/shared_analysis_v1.json --output output/transcript_timeline_v1.json
    python multimodal_timeline.py --vision output/vision_inference_v1.json
    python multimodal_timeline.py --analysis output/shared_analysis_v1.json --vision output/vision_inference_v1.json --output output/combined_timeline_v1.json

Inputs are individually optional, with at least one required. Audio/scene-only
Shared Analysis and valid empty/analyzed-empty inputs are supported; an empty list
or empty object is not a valid artifact. Input failures abort the whole merge.
Duplicate JSON keys and nonfinite JSON constants are rejected.

Default output is output/multimodal_timeline_v1.json (Git-ignored). Inside the
checkout, output must remain under output/. External local output paths are
permitted. Inputs and unrelated artifacts cannot be overwritten. --overwrite
explicitly replaces an existing valid timeline; otherwise publication is exclusive.
A flushed/fsynced sibling temporary file is atomically replaced (overwrite) or
hard-linked into place (no-overwrite), then removed. Hard-link unsupported
filesystems fail safely. Failure may leave an empty newly created directory, but
not a partial JSON. Concurrent overwrite writers are not supported.

Output uses sorted JSON keys and indentation, without a wall-clock creation time.
Exit 0 means successful publication, 1 validation/I/O failure, 2 CLI misuse.
The tool uses only standard-library dependencies and existing pure validators.
It does not read video bytes, initialize models, spawn FFmpeg or change artifacts.

## Limits and future work

This is a coordinate/representation contract, not semantic understanding.
Producer timestamps and identity claims can be inaccurate; scores are not
calibrated across modalities. No temporal association, interpolation, causal
interpretation, quality scoring or ranking occurs here. A future separately
evaluated semantic-highlight stage may consume this timeline without changing
what these original observations mean.

    python -m unittest test_multimodal_timeline -q
    python verify.py
