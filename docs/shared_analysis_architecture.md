# Shared Analysis Architecture V1

The same persisted analysis supplies both future Shorts and Long-form consumers.
Analysis producers run once, save evidence, and output consumers call
load_analysis(path). This milestone defines that boundary; neither output mode
nor any new detector/transcription is implemented.

## Schema

Plain dictionaries and JSON; schema_version is integer 1. Unsupported versions
are rejected without migration. source_video requires path (a locator, not a
machine-specific requirement) and duration_seconds; optional sha256, width,
height, fps and other JSON metadata are preserved. Every timestamp is seconds
relative to this source video.

Each signal has exactly status, data and provenance:

- status: not_analyzed or analyzed.
- data: ordered list of observations, preserving original evidence and scores.
- provenance: producer/model/revision/parameters/artifact references as supplied.

None supplied to an adapter becomes not_analyzed with empty data. An explicit
empty list becomes analyzed with empty data. These states differ. In particular,
the frozen multiframe experiment's empty accepted-event list does not establish
successful semantic detection: its invalid responses remain visual evidence.
Provenance can retain failure details. No confidence or successful-detection
claim is synthesized.

Signal locations and observation formats:

| Location | Timing/schema |
|---|---|
| visual.scene_changes | Existing time, score, normalized_score rows |
| visual.motion | Existing second, score, normalized_score rows |
| visual.semantic_frames | Timestamped CLIP/temporal rows or start/end multiframe windows; full vectors/responses retained |
| acoustic.audio_activity | Existing second, spike, score, normalized_score and available metadata |
| transcript | start, end, text; optional speaker/producer metadata |
| language.relevance | start/end observations supplied by a future producer |
| language.humor | Independent start/end observations |
| language.reaction | Independent start/end observations |
| language.narrative_context | Independent start/end observations |
| semantic_events | Existing semantic_events.py schema, including confidence interpretation metadata |
| candidate_windows | Existing start/end/duration/second dictionaries and score/boundary metadata |

Transcript and all four language signals start as not_analyzed. No transcription,
language extraction, scores, or relationships are inferred. Future language rows
can hold text evidence, classifications, or explicit producer scores; their
interpretation belongs to provenance, not this persistence layer.

## Validation and ordering

Require finite numeric timestamps within [0,source duration] and 0 <= start <= end.
Intervals use the existing half-open semantics; instantaneous events are allowed.
An included candidate second must fall within its window; duration must agree
with end-start. Semantic events reuse validate_event; interval validation reuses
temporal_overlap. Finite scores and JSON-compatible metadata are required.

Point observations must be nondecreasing by timestamp; interval observations by
(start,end). Overlaps are allowed. Unordered input is rejected, never repaired.
Existing main.py audio/scene lists are score-ranked: callers must explicitly
arrange observational evidence chronologically before adapting. Window adapters
preserve supplied selections and boundaries; they never rank or select.

## Adapters and persistence

- create_analysis(source_video): all missing signals explicitly marked.
- from_existing_signals(...): copy available audio, scene, motion, semantic,
  candidate, transcript, and independent language observations. None means missing.
- from_saved_semantics(source_video, timeline_path, events_path): read existing
  CLIP, temporal CLIP, or multiframe artifacts. Preserve artifact headers as
  provenance; check duration and hashes when both hashes are supplied. Read
  already-generated events without redoing conversion or model inference.
- windows_from_results(results, detector, k, variant): copy windows from saved
  fixed/dynamic records. Supports V1 fixed/dynamic and V2 fixed/v1/v2 records.
- validate_analysis, serialize_analysis, save_analysis, load_analysis: shared API.
  JSON uses indentation, sorted object keys, stable list order, no NaN/Infinity.
  Save validates before opening an existing file. Parent directories must exist.

Source identities must be supplied honestly. Without a supplied matching hash,
duration/path alone cannot prove two artifacts came from identical media.
Caller-selected artifact paths/provenance identify which frozen experiment is
being reused; this module does not combine conflicting model outputs implicitly.

## Example: both modes reuse one file

    from shared_analysis import (
        from_saved_semantics, save_analysis, load_analysis,
    )

    source = {
        "path": "videos/my_recording.mp4",
        "duration_seconds": 231.433288,
    }
    analysis = from_saved_semantics(
        source,
        "output/clip_semantic_timeline.json",
        "output/clip_semantic_events.json",
    )
    save_analysis(analysis, "output/shared_analysis.json")

    # Future Shorts consumer:
    shorts_evidence = load_analysis("output/shared_analysis.json")
    # Future Long-form consumer:
    long_form_evidence = load_analysis("output/shared_analysis.json")

Both loads return equivalent independent dictionaries from the same artifact.
There are no inference, FFmpeg, transcription, model, ranking, boundary, or
clipping calls in shared_analysis.py. Output decisions remain future work.

Run python -m unittest test_shared_analysis -v, then the existing relevant suite.
