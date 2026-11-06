# Full Observation Persistence V1

An explicit new analysis run saves all observations produced by the existing
audio and scene algorithms. No candidate ranking, motion analysis, clip cutting,
transcription, or model inference is invoked. Default production behavior stays
unchanged.

## Commands

    python observation_persistence.py --video videos/my_recording.mp4 --output output/full_observations_v1.json

This processes the supplied video; the production recording was NOT processed
during this milestone. Run it explicitly when ready, including on the desktop.

Reuse the artifact without reading or processing video:

    python observation_persistence.py --timeline-from output/full_observations_v1.json --output output/full_observations_timeline_v1.json
    python candidate_evidence.py --candidates output/shared_analysis_v1.json --timeline output/full_observations_timeline_v1.json

Use --overwrite only to replace a compatible artifact at an explicitly chosen
destination. Input aliases, symlinks and unrelated artifacts are protected.
Existing outputs fail before analysis unless overwrite is explicitly requested.
Inside the repository, destinations must be under ignored output/. No existing
production files are modified automatically. Concurrent overwrite writers are
unsupported.

## Existing algorithms and narrow hooks

main.analyze_audio reads mono signed-16-bit PCM and calculates mean absolute
amplitude in sample_rate-sized chunks. A final partial chunk is included.
For every chunk from index 5 onward, it computes:

    spike = current amplitude - mean(previous five amplitudes)
    score = current amplitude + spike

These are all scored intervals, not a threshold-filtered set of peaks. The first
five chunks establish the baseline and have no spike/score output. Signed/negative
spikes are preserved. Values are raw PCM-amplitude units, not dB, probabilities,
or normalized highlight scores.

The existing function already returns every score row sorted descending.
A new optional observation_sink callback receives copies of already-computed
amplitude rows and decoded sample metadata. Default returns, prints, arithmetic
and ordering remain unchanged.

main.analyze_video_motion uses the unchanged FFmpeg filter scdet=t=10 and returns
all scene-change lines its parser extracts, sorted by score. Its new optional
check=True raises on FFmpeg failure instead of allowing a misleading empty
successful artifact. Default behavior and command arguments remain unchanged.

Temporary audio uses the existing transcription.extract_audio helper: mono
16 kHz PCM WAV, with overwrite protection and subprocess failure propagation.
This imports no ASR backend and runs no transcription. A private temporary
directory prevents collisions with output/audio.wav.

## Versioned artifact and completeness

Full-observation schema_version=1, artifact_type=full-observations:

- source_video: informational path, SHA-256, byte count, duration, dimensions, FPS
  when available.
- source_identity: existing version-1 SHA-256/size/media identity contract.
- producer_sha256: digest of the main.py producer source.
- audio: analyzed status; amplitude_rows; score_rows; sample_rate_hz; channels;
  sample_count; algorithm/cadence/unit/order/coverage provenance.
- scene_changes: analyzed status, data rows, threshold/algorithm/order/coverage
  provenance.
- unanalyzed_modalities: transcript, motion, semantic_events, language.

Raw observations retain producer order and precision. Amplitude rows are
chronological; score rows and scene rows are descending by score with stable ties.
Duplicates genuinely emitted by the scene producer are retained. Valid empty
detector output is analyzed-empty, not unanalyzed.

This is complete output of these algorithms, not complete semantic evidence:
amplitudes cover decoded audio chunks; scores exclude the first five; scene events
are sparse thresholded emissions, not every frame-comparison measurement.
Original producer timing is retained without offset correction. Decoder padding
and stream offsets can affect the relationship to container time; invalid
out-of-container-bound event starts are rejected, never clamped.

The artifact adapter reuses audio_events and scene_events plus existing timeline
sorting/validation. Both amplitude and spike rows become audio observations,
with distinct existing audio_activity/audio_spike_score types. Their counts
must not be interpreted as independent moments. source_order and row_index retain
the original row order through chronological normalization. Transcript and other
unanalyzed signals remain absent; candidate inspection still reports unknown
temporal coverage. Existing timeline and Shared Analysis schemas do not change.

## Identity, processing cost and publication

The source is hashed once using source_identity.file_identity, and probed once
using media_probe.probe_format_streams. The resulting digest/byte count are reused
to construct the existing validate_identity contract; there is no second hashing
pass through source_identity(). Stat identity is checked across processing.
This is best-effort change detection, not protection against concurrent hostile
writers or a locked snapshot.

Unavoidable costs are one full hash read, an audio extraction/decode pass, the
existing scene-analysis pass, and the audio producer's in-memory WAV read.
No extra analysis pass is introduced for the callback. Legacy producer prints
are captured in this optional CLI; ordinary main.py output remains unchanged.

Sorted-key JSON serialization is deterministic for the same data; there are no
wall-clock fields. Exact output across different FFmpeg versions is not promised.
Source path is informational and may differ after relocation.

Publication reuses the atomic query writer: complete JSON is flushed/fsynced to
a temporary sibling before exclusive hard-link publication, or atomic replacement
with explicit overwrite. The previous final artifact remains intact on ordinary
analysis/publication failure. Temporary WAVs are cleaned on normal exceptions
and KeyboardInterrupt. A forced process termination may leave temporary files,
but not partial JSON at the final path. Exclusive publication requires filesystem
hard-link support. No atomic bundle or concurrent-writer coordination is added.

Exit codes: 0 success, 1 input/analysis/publication failure, 2 invalid arguments.
FFmpeg/FFprobe must be installed; no new Python dependency is required.

## Synthetic validation (2026-11-06)

A disposable seven-second 160x90, 10 FPS video changed from black to white at
3 seconds and contained a 440 Hz tone. Actual CLI processing produced:

- 7 amplitude rows; 2 scored intervals (seconds 5 and 6).
- 1 scene event: time 3.0, raw score 85.547.
- 10 normalized timeline observations.
- Closed query [2,6]: 8 observations; candidate inspection counted 7 audio and
  1 visual event, with no transcript.
- Source digest matched an independent hash of the temporary fixture.

Both artifact and timeline CLI paths succeeded. All temporary media/artifacts
were removed after validation. No production video analysis was performed.

## Tests

    python -m unittest test_observation_persistence test_main_import test_multimodal_timeline -q
    python verify.py --cached-export --video videos/my_recording.mp4 --analysis output/shared_analysis_v1.json

Tests cover unchanged producer results/commands, actual WAV arithmetic,
values/cadence/units, sparse/empty/unanalyzed semantics, original ordering and
duplicates, identity, invalid input, publication failures, interrupted analysis,
timeline reuse and isolated import safety.
