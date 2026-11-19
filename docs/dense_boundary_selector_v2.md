# Boundary Selector V2: Dense Continuity

Separate exploratory selector. V1, production ranking/exports, research predictions and the human benchmark remain unchanged.

## Fixed rule, before benchmark evaluation

At an integer cut t, use bins t-1 and t. Normalize raw audio amplitude and raw motion means separately by their maxima over the complete cached source. Let:

- A = min(audio[t-1], audio[t]) / max_source_audio
- M = min(motion[t-1], motion[t]) / max_source_motion
- D = 1 when an existing scdet emission is within 0.5 seconds of t, otherwise 0
- cut penalty = (1-D) * (A+M)/2
- variant score = -(start penalty + end penalty)/2; higher is preferred

The minimum measures sustained activity across the cut; a drop on either side reduces the penalty. Equal audio/motion weights, half-bin scene radius and 1e-12 absolute tie tolerance are fixed experimental assumptions, not learned or validated parameters. Scene evidence removes the continuity penalty; it does not establish a good narrative cut. No duration term, original fallback, candidate-specific rule, CLIP label, human annotation or language score is used.

All four variants require valid evidence. Missing adjacent bins, unsupported clocks/noninteger cuts or a zero-activity normalization modality cause abstention. Unique maxima select; ties abstain in stable input order. An analyzed-empty scene list means no detector emission, not proof of no semantic transition.

## Alignment audit

Clean repository at 9569266. Live video digest/size matches both dense cache and evaluation plan: SHA-256 6f96698e4325e8126f8348069dc620d23d5af2f208696dcc40b61ae8c4871b09, 167227207 bytes.

Audio/video stream start times and independently probed first decoded frame timestamps are zero. Stream timebases are 1/44100 and 1/15360 respectively. All 19 distinct variant boundaries are integers with adjacent audio and motion bins. Audio has 232 bins; motion has 232 one-second means from 5 FPS samples; scene output contains 43 sparse emissions. No sample interpolation or missing-value filling.

The live freeze command repeats content and initial timestamp checks. Scoring requires those zero origins and a single audio/video stream with positive timebase. Unsupported origins abstain; mismatched content identities reject.

This supports only a coarse bin-level comparison under the existing producers' timestamp conventions. WAV decoding removes PTS, motion normalizes video PTS and scene output retains FFmpeg times. No per-sample drift calibration or frame-accurate event alignment is established. Subsecond scene proximity is only an experimental neighborhood cue. Nothing detects confirmed game transitions or resolutions.

## Commands

```powershell
python -B dense_boundary_selector.py freeze --plan output/boundary_experiment_evaluation_v1/evaluation_plan.json --dense output/dense_observations_v1.json --analysis output/shared_analysis_v1.json --video videos/my_recording.mp4 --output output/boundary_selector_v2_predictions.json
python -B dense_boundary_selector.py evaluate --predictions output/boundary_selector_v2_predictions.json --benchmark benchmarks/boundary_review_v1
python -m unittest -q test_dense_boundary_selector
```

Freeze writes a new, exclusive atomic artifact containing policy, input digests, alignment audit, per-boundary raw/normalized evidence, all scores/selections and unchanged V1 predictions. It has no benchmark argument. Evaluate requires the saved artifact and checks its digest/config before importing/loading labels. It writes nothing. No overwrite, model download, extraction or video encoding occurs. Source hashing/initial FFprobe decoding are read-only.

Reported checksums are consistency fingerprints, not authenticated signatures. The project's human results were already known historically; this is an exploratory reuse, not blinded independent validation. Definitive and provisional comparisons remain separate.

## Frozen real result

Artifact: output/boundary_selector_v2_predictions.json (ignored runtime output).
Prediction digest: a90496d8f9774833dd61c680944186430472a4b38832fc99574e49120c4a1e9f.
Configuration and predictions were persisted before the evaluation command loaded human data. No rule changes were made after comparison.

Scores rounded here only; the artifact preserves full precision and all raw endpoint measurements.

| Candidate | Original | Earlier | Later | Both | V2 prediction | Human preference | Outcome |
|---|---:|---:|---:|---:|---|---|---|
| 0 | -0.566932 | -0.278514 | -0.288418 | 0 | Both [27,48) | Later [30,48) | Disagreement |
| 1 | -0.506486 | -0.517649 | -0.360753 | -0.371916 | Later [59,77) | Both [56,77) | Disagreement |
| 2 | -0.502722 | -0.402249 | -0.466379 | -0.365907 | Both [71,92) | Original [74,89), provisional | Provisional disagreement |
| 3 | -0.440500 | -0.385590 | -0.510133 | -0.455223 | Earlier [133,151) | Original [136,151) | Disagreement |
| 4 | -0.327217 | -0.487436 | -0.297645 | -0.457864 | Later [160,178) | Later [160,178) | Agreement |

Evidence and limitations by candidate:
- 0: scdet at 27.5 and 48.183333 zeroed both penalties. Scene adjacency did not establish complete action or payoff.
- 1: lower sustained activity at 77 versus 74 favors the later end; 59 beat 56 slightly. This did not capture the human need for earlier fight context.
- 2: lower activity at 71 and 92 favored both extensions; the rule has no knowledge of victory payoff or an unrelated new game. The human choice is provisional, not an unambiguous target.
- 3: 133 has a lower continuity penalty than 136, but the reviewer judged the extra beginning inactive. Low activity can introduce dead time rather than improve a cut.
- 4: low motion at 160 and lower endpoint continuity at 178 favored later, agreeing with the reviewer. One agreement does not validate event understanding.

Definitive totals: V2 1 agreement / 3 disagreements / 0 abstentions; always-original also 1 / 3 / 0; V1 0 / 0 / 4. Provisional candidate: V2 disagreement, original agreement, V1 abstention. Decision coverage increased, but no preference-agreement improvement over baseline was demonstrated. Accuracy on V1 decisions is undefined because it made none.

Next experiment: preserve this negative result and collect a separately reviewed, uncut multi-game test set with explicit event/transition timing. Test whether low-activity cuts and actual action resolutions coincide before adding another weighted signal. Do not tune scene radius or modality weights to these five known preferences. A conservative unsupported-scene abstention policy would be a new, separately frozen experiment, not a retrospective correction of V2.
