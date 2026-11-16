# Experimental Gameplay Boundary Evaluation V1

A reproducible, human-review workflow over persisted candidate windows. No ranking, selection, retention scoring, inference or production export behavior changes. Plans preserve original scores and ordering; no ratings are inferred.

## Commands

Run from the repository root. The first three commands below were successfully run on the real video for this milestone; their outputs now exist and must not be overwritten.

```powershell
python clip_boundary_experiment.py plan --analysis output/shared_analysis_v1.json --video videos/my_recording.mp4 --output output/boundary_experiment_evaluation_v1/offset_plan.json
python gameplay_boundary_evaluation.py plan --analysis output/shared_analysis_v1.json --video videos/my_recording.mp4 --experiment output/boundary_experiment_evaluation_v1/offset_plan.json --output output/boundary_experiment_evaluation_v1/evaluation_plan.json
python gameplay_boundary_evaluation.py review-template --plan output/boundary_experiment_evaluation_v1/evaluation_plan.json --output output/boundary_experiment_evaluation_v1/reviews.json
# Explicitly encode new review clips (not executed during this milestone):
python gameplay_boundary_evaluation.py export --plan output/boundary_experiment_evaluation_v1/evaluation_plan.json --video videos/my_recording.mp4 --output-root output/boundary_experiment_evaluation_v1/clips
# After a human edits clips/reviews.json:
python gameplay_boundary_evaluation.py compare --plan output/boundary_experiment_evaluation_v1/evaluation_plan.json --reviews output/boundary_experiment_evaluation_v1/clips/reviews.json --output output/boundary_experiment_evaluation_v1/comparison.json
```

For original-only evaluation, omit --experiment. To include an existing narrative artifact add --proposals PATH to plan. The tool never creates a narrative proposal itself. Use a new output path for each run; no overwrite/force options exist. The reusable API supports any nonempty persisted selection, including this project's five anchors; it does not require or select a new top five.

## Plans and identity

Plan schema 1, artifact_type gameplay-boundary-evaluation-plan. Embedded analysis, verified source metadata and supplied optional artifacts permit deterministic reconstruction. Producer validators verify the entire experiment/proposal and candidate mapping, not just declared IDs. Narrative inputs must contain this exact analysis. Narrative status is unavailable, unchanged, or changed; heuristic-only proposal provenance remains heuristic-only.

Planning hashes/probes the live source through the existing boundary verifier. Export rechecks content identity and duration, checks for source changes, and validates the full plan before encoding. Persisted hashes are consistency fingerprints, not authenticated authorship. No other analysis runs.

Candidate IDs reuse the existing boundary experiment IDs. Variant IDs include candidate, label and content-bound clip identity. Identical start/end windows across all candidates are encoded and rated once, retaining every label, candidate reference and original provenance. Distinct overlapping windows are not merged. Missing/unchanged proposals are explicit, not improvements.

## Real five-candidate plan

Source duration: 231.433288 seconds. Existing persisted Audio-only candidates, default experimental offsets of 3 seconds, no narrative artifact supplied:

| Anchor | Original | Earlier start | Later end | Both |
|---|---|---|---|---|
| 40 | 30–45 | 27–45 | 30–48 | 27–48 |
| 69 | 59–74 | 56–74 | 59–77 | 56–77 |
| 84 | 74–89 | 71–89 | 74–92 | 71–92 |
| 146 | 136–151 | 133–151 | 136–154 | 133–154 |
| 170 | 160–175 | 157–175 | 160–178 | 157–178 |

20 unique clips; narrative status unavailable for all five. These are actual generated plan boundaries, not exported videos or human quality results.

## Export and review

Explicit export delegates encoding to the existing boundary experiment's extracted encode_clip helper: unchanged horizontal H.264/AAC settings, original audio, accurate re-encoding and existing stream/duration checks. All clips, evaluation_plan.json, reviews.json and export_manifest.json are staged in a temporary directory; only a complete bundle is published. Failures discard staging. A newly created empty parent directory may remain.

Export destination must be nonexistent. Inside the repository it must be under output/boundary_experiment*. External new directories are allowed. There is no cache repair or replacement. Concurrent writers and full power-loss durability are not supported. The source and production artifacts are untouched.

Reviews have one row per unique clip with null integer 1–5 ratings for action_completeness, pacing and overall_watchability; starts/ends are null or too_early, too_late, appropriate; notes are optional text. Suggested anchors: 1 poor, 3 usable with editing, 5 strong for that metric. Reviewers should apply a consistent rubric; these subjective ratings are not calibrated measurements. Edit only those review fields.

## Comparisons and limitations

For each candidate, compare its original to each distinct alternative window once, retaining all equivalent labels. Identical-to-original alternatives are listed separately and excluded from paired differences. Differences are alternative minus original. Each metric reports available pairs, unavailable pairs and mean (null when none). Overall valid_rated_pairs requires all three metrics; unrated_or_partial_pairs is its complement. Missing starts/ends and metrics are listed as incomplete evaluations. Boundary judgments are preserved in review input, not converted into numeric scores.

The summary pools available distinct alternatives across candidates; it is not an independent-sample statistical estimate or a per-policy winner. Shared originals and globally deduplicated clips create correlated comparisons. No significance, generalization or improvement is claimed from five selected candidates from one already-edited video. Historical ratings are not imported. All generated reviews remain blank until a human supplies them.

Tests use synthetic fixtures and mocked encoding. Real validation in this milestone covers plan creation, source checks and cache integrity, not new review-clip playback or completed human evaluations.
