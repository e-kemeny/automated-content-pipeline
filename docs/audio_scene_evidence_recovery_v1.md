# Audio & Scene Evidence Recovery V1

Opt-in sparse recovery from existing cached data. No video is opened, hashed,
processed or reanalyzed. Existing producers, schemas, rankings and exports stay
unchanged.

## Investigation and root cause

Inspected main.py, shared_analysis.py, multimodal_timeline.py, timeline_query.py,
candidate_evidence.py, inspect_candidate_evidence.py, source_identity.py, the
Dynamic V1/V2 producers, related tests/docs and local output artifacts.

- main.py computes and returns full audio_scores and scene_scores in memory.
  It does not persist those full lists.
- output/shared_analysis_v1.json and both saved before-transcription and
  before-language snapshots have empty audio_activity and scene_changes
  envelopes marked not_analyzed. Their selected windows retain original scores.
- output/dynamic_window_v1.json and dynamic_window_v2.json retain selected
  candidate snapshots, evaluation mirrors and boundary diagnostics, not full
  original observation streams.
- Dynamic V2 fixed.windows retain second/spike/score/normalized_score.
  Its v2.windows boundary diagnostics retain strongest nearby scene_time and
  scene_score. The producer copies the already normalized scene intensity;
  inward_mean/outward_mean are regional aggregates, not per-second samples.
- output/dynamic_window_v2_run.txt also has top-five audio/raw-scene printouts.
  Those unversioned console excerpts are not imported by this JSON adapter.
- results/dynamic_window_v2.md reports a source-video SHA-256 agreeing with
  Shared Analysis. It does not hash/bind the cached JSON, whose own identity
  metadata is absent. The recovery tool does not borrow that digest.
- The existing timeline already understands audio_spike_score and scene_change.
  Missing evidence was caused by absent Shared Analysis rows, not a broken parser.

Full streams cannot be recovered from these sparse selections/aggregates.
A future opt-in analysis-and-persistence stage would be needed to capture them,
with explicit source identity. This milestone does not perform that stage.

## Commands and supported schemas

    python recover_timeline_evidence.py --dynamic-v2 output/dynamic_window_v2.json
    python recover_timeline_evidence.py --dynamic-v2 output/dynamic_window_v2.json --output output/recovered_sparse_timeline_v1.json
    python recover_timeline_evidence.py --analysis output/shared_analysis_v1.json

Default is JSON stdout only. --analysis delegates to the existing Shared Analysis
adapter; it does not recover missing signals from candidate score fields.
Exactly one input mode is allowed.

The Dynamic V2 input is the existing unversioned list of fixed/v1/v2 result pairs.
Only fixed.windows audio rows and v2.windows boundary diagnostics are extracted.
Evaluation prediction mirrors and V1 copies are not separate observations.
Unknown pair formats or injected identity fields are rejected rather than guessed.
The adapter identifies itself with recovery_version=1 in channel provenance.
Output remains the existing timeline schema_version=1.

For each audio record the entire original fixed-window row is preserved as payload.
Each scene payload contains time=scene_time, normalized_score=scene_score and the
unchanged original row under recovery_diagnostic. No raw score is reconstructed.
Null scene references create no event; regional audio means create no point event.

Original JSON pointers are recorded in event.source.artifact_pointer.
Timeline ordering uses the existing start/end/modality/source_order contract.
Source order records extraction order; duplicate selected rows and repeated
diagnostic references remain separate. Counts are references, not independent
measurements. Values are copied without renormalizing, rescaling or scoring.

## Identity, coverage and downstream use

Dynamic V2 carries no source identity or duration. Its source_video is empty,
identity_status is unverified_single_artifact, source_identity/duration_seconds
are null. Unknown upper bounds are not fabricated from maximum event time.
Finite nonnegative timing and valid numeric values are still required.

Under existing timeline rules, this unverified artifact cannot be merged with
a separate transcript artifact: every merged artifact must report its own
source-video digest. No override or implicit metadata copying is offered.
The separate recovered audio+scene timeline can be queried or associated with
existing Shared Analysis windows; candidate_evidence reports
unverified_missing_source_digest. That association is conditional, not a claim
of verified source equivalence.

    python candidate_evidence.py --candidates output/shared_analysis_v1.json --timeline output/recovered_sparse_timeline_v1.json

Both recovered channels are analyzed (including valid empty lists), meaning
retained cached records were examined, not continuous coverage. Transcript is
absent from this artifact. Candidate coverage remains unknown; observed_events
requires actual matches. Empty windows are not negative gameplay evidence.
All identity conflicts in supported Shared Analysis inputs continue to fail via
the existing validators. Missing hashes prevent a cross-artifact merge.

## Actual local inspection, 2026-11-05

Built recovery, candidate evidence and inspection entirely in memory. No
production outputs were written.

Recovered 45 audio records (11 distinct timestamps) and 433 scene references
(33 distinct timestamps). These figures intentionally preserve repeated records
across detector/K configurations and boundary searches.

| Window (seconds) | Audio records | Scene references | Visual total | Transcript in recovered timeline | Previous transcript-only count |
| --- | --- | --- | --- | --- | --- |
| 30–45 | 5 | 32 | 32 | 0 | 3 |
| 59–74 | 6 | 54 | 54 | 0 | 2 |
| 74–89 | 6 | 66 | 66 | 0 | 2 |
| 136–151 | 5 | 0 | 0 | 0 | 1 |
| 160–175 | 6 | 17 | 17 | 0 | 2 |

Audio is observed in all five windows. Visual is observed in four; 136–151 has
no_events_in_window for this sparse channel. Transcript is absent_from_timeline.
The previous transcript counts are unchanged in their original artifact; zeros
here result from selecting a separate source and refusing an unverifiable merge,
not changed query boundaries. Closed boundaries and touching intervals remain
unchanged. No ImageNet/other model predictions were recovered or invented.

## Output safety and limits

Optional output delegates to save_timeline: atomic publication, no overwrite
unless --overwrite, input alias protection, rejection of unrelated destination
artifacts, ignored output/ required for destinations inside the repository.
Exclusive publication requires hard-link support. No concurrent overwrite
coordination is provided. Failure may leave an empty directory, never partial JSON.
Exit 0 success, 1 validation/I/O failure, 2 CLI misuse.

Recovery is selection-biased and incomplete. Neither peaks nor scene changes
establish excitement, semantic events or highlight quality. Repeated references
must not be interpreted as stronger evidence or used as a new ranking signal.

## Tests

    python -m unittest test_recover_timeline_evidence test_multimodal_timeline test_candidate_evidence test_inspect_candidate_evidence -q
    python verify.py --cached-export --video videos/my_recording.mp4 --analysis output/shared_analysis_v1.json

Tests use synthetic fixtures matching the persisted Dynamic V2 structure and
existing Shared Analysis schemas. There is no FFmpeg analysis or inference.
