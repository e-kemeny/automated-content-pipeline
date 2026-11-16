# Human Boundary Benchmark V1

Frozen human review fixture for one already-edited Minecraft BedWars recording, five candidate families and twenty exported clips. Prepared against repository HEAD 9dd1cf3. No video files or generated video exports are included.

## Contents and provenance

- evaluation_plan.json and export_manifest.json: byte-for-byte copies of the actual saved artifacts. Embedded analysis, source identity, candidate/variant IDs and clip hashes retain their original provenance (including historical path locators).
- supplied_request.txt: exact bytes of the user-supplied request containing all reviews, preference labels and observations.
- human_reviews.json: the twenty supplied reviews indexed by candidate and readable variant label. Notes preserve wording; layout line breaks are normalized to spaces.
- reviews.json: those same reviews imported into the existing gameplay-boundary-reviews schema through validated clip IDs.
- preferences.json: separate supplied human choices, never inferred from numerical scores.
- benchmark.json: version, provenance and SHA-256 inventory of the six data files.

The supplied cleaned notes are **paraphrases**, not verbatim original review speech. Earlier verbatim observations were not supplied; none have been reconstructed. Keep contradictory-sounding notes/assessments as entered. For example, candidate 4 both remains ends=too_late even though its note says the ending is okay but could improve.

At creation, all twenty actual MP4 hashes were checked against the real export manifest. The portable summary requires only these persisted files, not videos or the local output directory. Manifest/plan agreement is validated via existing evaluation functions; source identity remains a persisted claim during offline review. Checksums detect accidental changes, not malicious edits to both data and checksums.

## Read-only command

From the repository root:

```powershell
python -B human_boundary_benchmark.py
python -B human_boundary_benchmark.py --benchmark benchmarks/boundary_review_v1
python -m unittest -q test_human_boundary_benchmark
```

The command validates file hashes, the plan, export references, all twenty unique candidate/variant mappings, and imported reviews. It prints deterministic JSON containing per-variant means, metric-specific paired differences, all fifteen per-candidate comparisons, review coverage and explicit human preferences. It writes no files and runs no media processing or inference.

Import is implemented by the pure import_reviews(plan, manifest, rows) function, which rejects missing, duplicate, malformed, incomplete or mismapped reviews. Version 1 intentionally requires all twenty complete reviews. This fixture is frozen: future revisions should use a new named/versioned benchmark, preserving V1 and its provenance rather than updating production reviews.

## Recomputed results

Metric order: action completeness, pacing, overall watchability.

| Variant | Mean ratings | Paired change versus original |
|---|---|---|
| Original | 3.8, 4.8, 3.8 | — |
| Earlier | 3.6, 4.4, 3.6 | -0.2, -0.4, -0.2 |
| Later | 4.0, 4.4, 4.2 | +0.2, -0.4, +0.4 |
| Both | 3.6, 4.2, 3.8 | -0.2, -0.6, 0.0 |

Coverage: 20/20 clips, 15/15 complete paired comparisons, no missing evaluations.

Human preferences: candidate 0 later [30,48); candidate 1 both [56,77); candidate 2 original [74,89), provisional; candidate 3 original [136,151); candidate 4 later [160,178). Candidate 0 is the best tested option, not a perfect clip. Candidate 2 original/earlier tie numerically: original has the better ending assessment, earlier the better start, neither ideal.

## Interpretation and next research

Uniform extension was not reliably beneficial in this small review. The supplied observations highlight event setup/resolution, payoff visibility, unrelated transitions and dead time. Good original boundaries should be preserved. Speech and OCR timestamps do not establish exact event boundaries.

These are human judgments on one edited recording and five selected families, not representative data, independent samples, or evidence of statistical significance/generalization. No visual/OCR gameplay-recognition accuracy was measured. Nothing here tunes production ranking, boundaries, selection, retention models or exports.

Future work may investigate evidence-informed alternatives and real gameplay-event recognition on longer uncut recordings and multiple games. Those tasks and production integration are outside this milestone.
