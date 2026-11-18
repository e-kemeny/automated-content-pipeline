# Dense Multimodal Observation Collection V1

One opt-in CPU observation artifact for future Shorts and long-form consumers. No candidate selection, boundary scoring, retention changes, model inference or clip export. Existing Shared Analysis and experimental predictions remain untouched.

## Reuse and commands

```powershell
python -B dense_observations.py --video videos/my_recording.mp4 --analysis output/shared_analysis_v1.json --output output/dense_observations_v1.json
python -m unittest -q test_dense_observations
```

The first run creates the cache; identical subsequent runs validate and reuse it. The command prints coverage and native-clock neighborhoods for the original candidate starts/ends. Omitting --analysis explicitly leaves CLIP unavailable. Use the same artifact for both future output modes; neither needs a separate extraction pass.

Reused components:
- observation_persistence.collect_observations: existing temporary mono 16 kHz WAV extraction, main.analyze_audio callback, unchanged rolling five-second spike formula and scdet=t=10 producer.
- motion.analyze_motion: unchanged 5 FPS, 160x90 grayscale frame differences and one-second aggregation/max normalization.
- Shared Analysis validation and saved CLIP semantic_frames: copied unchanged, with source digest/duration/model checks; no CLIP inference.
- Existing source hashing, FFprobe, timeline validators/adapters and exclusive atomic JSON publication.

Only new derived measurements are adjacent audio/motion-bin differences and read-only neighborhood summaries. They are observations, not probabilities or confidence scores. No production Python module was modified.

## Artifact

schema_version=1, artifact_type=dense-observations. Contains full original audio/scene artifact, motion rows, reused CLIP envelope, stream metadata, source content identity, producer recipe, coverage, canonical content digest and an embedded valid Multimodal Timeline V1.

Timeline channels include audio_activity (amplitude and original spike rows), audio_changes, scene_changes, motion, motion_changes and frames (clip_hypothesis). All timeline events sort chronologically with stable source ordering and retain payload/provenance. Raw audio spike and scene arrays preserve the producers' descending-score order, rather than pretending every stored list is chronological.

The embedded timeline can be consumed in memory as artifact["timeline"] by existing queries. Its provenance retains separate native clocks; consumers must not assume exact cross-modal alignment merely because timestamps share numerical units.

## Timebases and sampling

- Audio: mean absolute signed-16-bit PCM amplitude per one-second decoded WAV chunk. First five chunks have no rolling-baseline spike score; partial final chunk retained.
- Audio changes: current minus preceding chunk amplitude, starting at second 1.
- Motion: samples at 5 FPS after setpts=PTS-STARTPTS; raw pixel difference divided by 255, averaged by the later frame's integer second. First frame has no predecessor. Final bin may be partial. Existing normalized_score is per-video max normalization, not confidence.
- Motion changes: current minus preceding raw one-second mean. These are continuity proxies, not optical flow or recognized action.
- Scene: all existing scdet producer emissions at threshold 10. Sparse discontinuity events, not dense all-frame scene scores. A cut can be an edit, menu or camera change; game-transition detection remains unavailable.
- CLIP: saved one-second sampled hypotheses with original prompts/model revision/filter; semantic predictions are unconfirmed.

Audio begins at decoded audio zero; motion begins at normalized video zero; scene timestamps retain FFmpeg's emitted convention. Probed stream start_time/time_base/duration are preserved. No offsets are silently repaired. This collector does not establish frame-accurate cross-modal alignment.

boundary_report returns rows before [t-radius,t) and after [t,t+radius], default radius 2 seconds, maximum observed activity and after-mean minus before-mean. Counts can differ because the bins are point-indexed and the right edge is inclusive. Maxima are local sampled measurements, not detected semantic peaks. Native-clock uncertainty applies. Missing neighborhoods return null measurements, never fabricated zeros. It does not choose cuts.

## Cache and failure policy

Cache identity requires a full source SHA-256/size match, the same producer code hashes, FFmpeg version and exact optional CLIP envelope. The entire artifact is reconstructed/validated before reuse. Modified bytes at the same path invalidate it; matching bytes at a relocated path can reuse it. A hit hashes the source and queries FFmpeg version but never extracts audio, analyzes scenes/motion, writes outputs or runs inference.

Stale/corrupt caches fail closed: use a new output path. There is no force, overwrite, repair or migration. Publication uses the existing exclusive atomic writer. Existing artifacts are not replaced. Source stat checks detect ordinary changes during collection/reuse; this is not hostile concurrent-writer protection.

On a cold run the wrapper and reused collector each hash the source, and stream metadata is probed again to retain clocks. These bounded redundant metadata operations avoid changing the existing collector interface; audio, scene and motion analysis each run once. Current recipe invalidation is conservative and includes source-file changes even when only comments changed.

This V1 collector requires video with an audio stream because the reused full-observation producer requires both. Missing audio, failed decoding, empty motion or invalid timestamps abort publication explicitly; no successful partial cache is fabricated. Optional CLIP absence is persisted as not_analyzed. An analyzed-empty scene list is valid. OCR, ASR and fused-event creation are outside this collection stage.

## Real run: existing edited BedWars recording

Source SHA-256: 6f96698e4325e8126f8348069dc620d23d5af2f208696dcc40b61ae8c4871b09.
Container duration: 231.433288 seconds. The recording is already edited; discontinuities must not be interpreted as naturally occurring gameplay transitions.

| Observation | Count | Sampling/coverage |
|---|---:|---|
| Audio amplitudes | 232 | seconds 0–231; decoded 231.4333125 seconds |
| Audio spike scores | 227 | seconds 5–231 |
| Audio changes | 231 | seconds 1–231 |
| Motion means | 232 | seconds 0–231 from 5 FPS frames |
| Motion changes | 231 | seconds 1–231 |
| Scene events | 43 | sparse scdet emissions |
| Reused CLIP hypotheses | 232 | original one-second samples |
| Combined timeline | 1,428 | ordered native-clock observations |

Decoded audio exceeds the container duration by 0.0000245 seconds due to sample quantization. Observation timestamps themselves remain in bounds; no timestamp was clamped. Probed video duration is 231.366667 seconds, audio duration 231.433288, both start_time=0; video time_base=1/15360, audio=1/44100.

Collection: 21.247 seconds. Cache reuse: 0.880 seconds in the validation run (includes integrity checks). Extraction functions were mocked to raise during the reuse call, confirming no analysis fallback. All nine protected production artifacts and the cache retained their SHA-256 hashes and nanosecond mtimes. No GPU was used; this implementation uses the existing CPU path and adds no GPU assumption.

Next experiment: freeze a separate boundary-continuity feature using this cache before loading human labels. Keep the failed speech-only selector unchanged. Establish timing alignment and evaluate on longer uncut footage/multiple games before claiming semantic understanding or generalization.
