# Experimental Clip Boundary Evaluation V1

This standalone, CPU-friendly experiment compares fixed boundary offsets. It does not detect semantic boundaries, change production scores, or establish an intelligent editing model. No analysis or inference runs implicitly.

## Commands

Run from the repository root:

```powershell
python clip_boundary_experiment.py plan --analysis output/shared_analysis_v1.json --video videos/my_recording.mp4 --output output/clip_boundary_plan_v1.json
python clip_boundary_experiment.py review-template --plan output/clip_boundary_plan_v1.json --output output/clip_boundary_review_v1.json
# Optional: explicitly encode isolated experimental clips.
python clip_boundary_experiment.py export --plan output/clip_boundary_plan_v1.json --video videos/my_recording.mp4 --output-root output/boundary_experiment_v1
# Edit only ratings, notes and preferred_variant in the review JSON, then:
python clip_boundary_experiment.py compare --plan output/clip_boundary_plan_v1.json --reviews output/clip_boundary_review_v1.json --output output/clip_boundary_comparison_v1.json
```

Planning requires `--video` for read-only content/duration verification. It never encodes. `--seconds-before` and `--seconds-after` default to 3 and each accepts finite values from 0 to 10 seconds. JSON commands reject existing outputs unless `--overwrite` is explicit; input artifacts cannot be overwritten. Export has no overwrite or repair option and requires a new destination.

## Representation and bounds

Shared Analysis V1 stores `candidate_windows` as a status/data/provenance envelope. Each data row has `start` and `end` in seconds and may include `second`, `duration`, `score`, and other metadata. The current five rows are preselected Audio-only anchors, in source chronology, not a newly ranked multimodal pool. Full original rows, source claims, scores and provenance are preserved; candidates are neither sorted nor deduplicated.

Variants are `original`, `earlier_start`, `later_end`, and `both`. Start is clamped to zero and end to verified source duration. Actual signed offsets and durations are recorded. Zero offsets and clamping can produce identical windows; these remain distinct named alternatives. Candidate IDs include original index, content identity and row; variant IDs include candidate ID, name and proposed boundaries. IDs are deterministic consistency fingerprints, not cryptographic signatures proving authorship.

Expected default arithmetic for the supplied five windows (not a production export performed for this milestone):

| Index | Original | Earlier start | Later end | Both |
| --- | --- | --- | --- | --- |
| 0 | 30–45 | 27–45 | 30–48 | 27–48 |
| 1 | 59–74 | 56–74 | 59–77 | 56–77 |
| 2 | 74–89 | 71–89 | 74–92 | 71–92 |
| 3 | 136–151 | 133–151 | 136–154 | 133–154 |
| 4 | 160–175 | 157–175 | 160–178 | 157–178 |

These apply offsets (0,0), (-3,0), (0,+3), and (-3,+3), respectively, without clamping for the claimed 231.433288-second recording. Reproduction requires the live source to pass verification; matching metadata alone is insufficient.

## Identity and publication safety

Planning and explicit export each hash the source once and probe its actual duration/video metadata using existing utilities. A matching SHA-256 claim and duration (within 0.000001 seconds) are required; available dimension/frame-rate/size claims must agree. Missing identity or duration fails closed. Export checks the plan's verified content identity again, requires audio/video, rejects invalid bounds, and checks source file identity before/after processing. It does not reanalyze audio or scenes. Source symlinks are rejected.

Within the repository, exports must be under `output/boundary_experiment*`; a new external directory is also supported. Filenames are `candidate_000_original.mp4`, `candidate_000_earlier_start.mp4`, etc. Indexes prevent duplicate-candidate filename collisions. All H.264/AAC clips are staged, probed using existing Shorts validation, and hashed before publishing the new directory with `boundary_export_manifest.json`. Failure cleans staging instead of leaving a complete-looking export. A newly created empty parent directory may remain. Existing outputs are never repaired or replaced. JSON artifacts reuse atomic publication utilities.

Encoding uses the existing horizontal Shorts codec conventions (libx264, fast, CRF 18, yuv420p; AAC 192k, faststart), with seeking and re-encoding rather than stream copying. Production exporters are unchanged. Frame/sample quantization still applies; actual durations and errors are recorded. Concurrent writers, malicious filesystem races and power-loss durability of the whole bundle are outside this experiment's guarantees. Use a dedicated destination with no other writers.

## Human review and interpretation

Every new rating starts `null`, including original variants. Enter integer ratings 1–5, optional candidate/variant notes and an optional explicit `preferred_variant` name. Do not edit identities, order, metadata or windows: comparison rejects tampering. A candidate counts as reviewed when it has any rating, preference or nonblank note. Ratings and preferences remain separate; preferences are never inferred.

Comparison reports missing ratings, explicit preferences, all equal-rated variant pairs, and alternative-minus-original differences only where both ratings exist. Longer-duration counts include only genuinely longer paired variants and report higher/lower/tied ratings descriptively. Missing reviews never become zeros. Neither a longer clip nor a higher original audio score implies better editing; no statistical significance, model improvement or causal effect is claimed.

### Historical user review context only

These are user-provided ratings, not generated labels and not automatically copied into new reviews.

| Candidate | Window | Audio score | Rating | User note |
| --- | --- | --- | --- | --- |
| 0 | 30–45 | 5774.281875 | 5 | Engaging, fight scene, bed break, another fight scene; clip ended early. |
| 1 | 59–74 | 6411.09445 | 3 | Fight against one aqua player; clip started late and ended early. |
| 2 | 74–89 | 8945.897975 | 4 | Finished previous fight, defended bed, killed attacker, broke bed, won game. No explicit timing complaint. |
| 3 | 136–151 | 6532.2561375 | 3 | Invisible-player fight detected, but final cut ended during anticipation. |
| 4 | 160–175 | 8375.8160375 | 4 | Captured introduction of third game, smooth fight, player death and opponent jumping toward bed; ended early. |

The stored candidate-3 float is 6532.2561375000005; plans preserve the stored value without rounding. This small selected sample of one already-edited video is not generalizable evidence.

## Validation

`python -m unittest test_clip_boundary_experiment` covers planning, bounds/identity, duplicates, review validation, ties/missing ratings, isolation, failure cleanup, atomic publication and import safety. `python verify.py --cached-export --video videos/my_recording.mp4 --analysis output/shared_analysis_v1.json` additionally checks existing production artifacts read-only.

A disposable six-second 160×90/10 FPS synthetic video exercised all four CLI workflows and four H.264/AAC exports. Probed durations were 2, 3, 5 and 6 seconds, with zero measured duration error and both stream start times at zero. Fixtures were removed. No production experimental clips or human comparison results were generated during implementation.
