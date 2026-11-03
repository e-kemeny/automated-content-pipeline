# Candidate Evidence V1

A standalone retrieval report pairs saved candidate windows with saved timeline observations. No ranking, inference, media probing, source hashing or exports occur.

## Supported candidate artifact

Only complete Shared Analysis schema_version 1 documents are supported, using the existing validator. Candidates are candidate_windows.data rows with start/end in seconds, optional second/duration, and original score/ID/rank fields. The envelope must be analyzed; analyzed-empty is valid. Missing/not_analyzed candidates, manifest clips, raw lists and research-result formats are rejected rather than guessed.

The current saved output/shared_analysis_v1.json contains five preselected Audio-only fixed windows, not a complete candidate pool or fresh multimodal ranking. Its candidate provenance records detector, k, variant and source artifact. All these fields and each original row are preserved. Existing chronological ordering is validated, never repaired.

## CLI

Given an existing Shared Analysis file and an existing timeline:

    python candidate_evidence.py --candidates output/shared_analysis_v1.json --timeline output/multimodal_timeline_v1.json
    python candidate_evidence.py --candidates output/shared_analysis_v1.json --timeline output/multimodal_timeline_v1.json --output output/candidate_evidence_v1.json

The command prints compact JSON to stdout. Optional --output uses the existing atomic query writer. --overwrite requires --output and only permits replacement of an existing Candidate Evidence V1 report. Input aliases and unrelated artifacts are protected. Within the checkout, output must be under ignored output/. External destinations are permitted. No files are written by default; input artifacts are never updated.

Exit codes: 0 success, 1 validation/I/O failure (stderr), 2 CLI misuse. No new dependencies are required.

## Pure API and result

build_candidate_evidence(candidates, timeline, candidate_reference=None, timeline_reference=None) accepts loaded dictionaries; references are keyword-only informational labels.

Result structure (field outline, not real-video results):

- schema_version: 1; report_type: candidate-evidence
- inputs.candidates: reference, schema_version, source_video, status, provenance
- inputs.timeline: reference, schema_version, identity_status, source_identity, sources
- identity_comparison
- candidates: list of reports, each containing:
  - candidate_index: zero-based input position, not a generated rank
  - candidate: complete unchanged original row
  - window: original start/end
  - events: original matching timeline objects
  - matched_event_count and counts_by_modality
  - evidence_coverage: per-modality observation status, channel availability and temporal coverage

Queries delegate to timeline_query.query_timeline: closed [start,end], points on either boundary included, touching intervals included. Duplicate observations and candidates remain separate. All original numeric precision, scores, payloads and provenance are preserved; copies prevent output mutation affecting inputs. Invalid/nonfinite/negative/reversed/out-of-duration windows fail without clamping.

## Coverage is explicitly incomplete

Each audio, visual and transcript entry reports:

- observed_events: at least one matching observation.
- no_events_in_window: a known analyzed channel exists but has no matching observations.
- absent_from_timeline: no corresponding channel or event is present.
- not_established: corresponding channels exist but are not analyzed (or their analysis availability is otherwise unknown).

The existing V1 channels are audio_activity (audio), scene_changes/frames (visual), and transcript. Channel statuses and artifact indexes are retained. temporal_coverage is always unknown: these artifacts do not establish continuous per-window coverage. Even analyzed-empty is not proof that nothing interesting occurred. Sparse visual sampling, missing audio analysis, and transcript-only timelines remain incomplete evidence. No completeness percentage or quality score is invented.

## Identity and limitations

Existing validators check both input schemas. Reported source SHA-256, duration, width, height, FPS and size are compared wherever available, including source_sha256/source_duration_seconds channel and candidate provenance. Explicit conflicts fail, even for empty candidate lists. Paths are informational, not identity proof. Comparisons are exact, following timeline conventions.

identity_comparison is consistent_reported_sha256 only when all input source headers report agreeing digests; otherwise it is unverified_missing_source_digest. Neither status independently verifies video bytes. The timeline's own identity_status and source_identity are preserved without upgrading trust. Missing metadata cannot establish equivalence; results remain conditional on supplied artifact claims.

The writer flushes/fsyncs a temporary sibling then publishes atomically; failure cleans up temporary files. Exclusive publication requires hard-link support. A failed write may leave an empty newly created parent directory. Concurrent overwrite writers are unsupported. Do not treat this inspection layer as a new detector, complete temporal coverage, or evidence of improved selection.

## Tests

    python -m unittest test_candidate_evidence test_timeline_query test_multimodal_timeline test_shared_analysis -q
    python verify.py --cached-export --video videos/my_recording.mp4 --analysis output/shared_analysis_v1.json

Tests and CLI demonstrations use temporary synthetic artifacts. No production evidence report is generated for validation.
