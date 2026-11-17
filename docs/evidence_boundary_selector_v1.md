# Evidence-Informed Boundary Selector V1

Experimental, read-only speech-continuity ablation. Production ranking, boundaries, exports and benchmark data are unchanged. No models, media processing or new dependencies.

## Evidence audit at beb8e2e

The saved Shared Analysis artifact is bound to the recording SHA-256. It contains 19 actual faster-whisper small.en ASR segments with source-bound provenance (no word alignment), 232 real CLIP sampled-frame predictions, derived semantic hypotheses, and 19 Qwen language judgments per dimension. Predictions/judgments are not confirmed gameplay events.

Audio activity, scene changes and motion envelopes are not_analyzed with zero rows. Dynamic V1/V2 caches retain selected scores and sparse boundary diagnostics, not complete per-second streams; their JSON lacks content identity. They cannot supply authenticated boundary-neighborhood observations. No full-observation, OCR, visual-evidence extraction, transcript-event or fusion JSON was found under the current output tree. Their implementations and synthetic tests do not establish real gameplay evidence. Temporal CLIP and multiframe caches also exist; model labels/scores do not establish exact event endpoints. Raw audio.wav is not analyzed by this experiment.

Only ASR timing is used. CLIP labels, language scores, candidate ranking scores, human annotation planners, OCR and sparse legacy diagnostics are excluded. The existing timeline/observation adapters cannot recover missing streams; no hidden reanalysis is attempted.

## Fixed rule (declared before this evaluation)

For each of the four saved variants, score = minus the number of endpoints strictly inside any nonempty ASR segment: 0, -1 or -2. An endpoint is counted once even with overlapping segments. Exact segment endpoints are not cut. There are no learned weights, duration bonuses, semantic confidence values, proximity tolerances or candidate-specific rules.

Choose only a unique highest score and only when at least one variant overlaps available speech. Otherwise abstain: all tied labels remain in stored order, with no original-window tie-break. Missing/analyzed-empty speech yields null scores and abstention. An absence of transcript does not establish silence. Segment IDs/times and cut/intersection references explain every score.

This feature tests speech continuity only. ASR segment boundaries can be coarse/arbitrary and do not measure action completeness, victory payoff, death screens, dead time or game transitions. A unique score is only a heuristic preference, not reliable gameplay recognition.

## Commands and separation

```powershell
python -B evidence_boundary_selector.py predict --plan output/boundary_experiment_evaluation_v1/evaluation_plan.json --analysis output/shared_analysis_v1.json
python -B evidence_boundary_selector.py evaluate --plan output/boundary_experiment_evaluation_v1/evaluation_plan.json --analysis output/shared_analysis_v1.json --benchmark benchmarks/boundary_review_v1
python -m unittest -q test_evidence_boundary_selector
```

Both commands print deterministic JSON, write no files and never export clips. Use -B to suppress Python bytecode cache writes. Plan and Shared Analysis validators check identities, candidate mappings and timing; ASR source digest/duration/backend/model provenance must be present. Human/narrative proposals are rejected before producer validation. The scoring function performs no file access and has no benchmark argument. It reads only validated machine ASR timings for scores; unrelated signal values cannot affect predictions.

Evaluation serializes predictions to immutable canonical bytes and hashes them **before** importing/loading the human benchmark. It then compares supplied preferences by candidate, refusing a different plan. The output includes those frozen predictions, digest, all agreements/disagreements/abstentions, and the original-window baseline. Candidate 2's provisional preference is reported separately from definitive totals.

Freeze is in-memory for this read-only command, not a signed preregistration or durable artifact. Human results were already visible in project history; runtime separation prevents direct label access while scoring, but this is not blinded or held-out validation. No tuning was performed against the comparison results. One edited video and five families cannot establish significance or generalization.

## Real run (no tuning afterward)

Frozen prediction SHA-256: b19fdb5a712d94b401da2bcd518285c138398bd6e096190d3980dfa58b75ede0.

| Candidate | Original | Earlier | Later | Both | Decision | Supplied preference |
|---|---:|---:|---:|---:|---|---|
| 0 | -2 | -2 | -2 | -2 | Abstain: four-way tie | Later [30,48) |
| 1 | -2 | -2 | -2 | -2 | Abstain: four-way tie | Both [56,77) |
| 2 | -1 | -1 | -2 | -2 | Abstain: original/earlier tie | Original [74,89), provisional |
| 3 | -2 | -2 | -2 | -2 | Abstain: four-way tie | Original [136,151) |
| 4 | -2 | -2 | -2 | -2 | Abstain: four-way tie | Later [160,178) |

For candidate 2, both 89-second endings fall outside the saved speech segments; 92 seconds falls inside [90.46,96.86). Both starts cut the same [67.63,78.78) segment. This separates two pairs, not a unique preferred variant. For the other candidates, both endpoints cut speech for every variant. The JSON carries exact segment references for each endpoint.

Definitive preferences: 0 agreements, 0 disagreements, 4 abstentions. The provisional case also abstains. Decision coverage is 0/5; accuracy conditional on decisions is undefined, not zero. Always-original agrees with 1/4 definitive preferences and also matches the provisional candidate 2 label separately. No improvement over baseline is demonstrated.

Recommended next experiment: collect source-bound, dense audio/scene/motion observations with explicit time origins on a longer uncut recording, then freeze a separate continuity feature before human review. Do not rerun or retune this rule to fit the known five preferences. Semantic event starts/resolutions still require real validated visual evidence; ASR word alignment alone cannot establish them.
