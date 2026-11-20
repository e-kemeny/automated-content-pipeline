# Dense-to-Shared Integration V1

Create a new Shared Analysis V1 document from the existing dense collector:

```powershell
python dense_to_shared.py videos/new_recording.mp4 --dense-cache output/new_recording/dense_v1.json --analysis-output output/new_recording/shared_analysis_v1.json
```

Optional `--semantic-analysis path/to/shared_analysis.json` reuses only source-bound
`openai/clip-vit-base-patch32` frame observations with the existing collector's
required model revision, source digest, duration and timestamp provenance. It does
not copy transcript/language/event results or run inference. CLIP labels remain
unconfirmed hypotheses. Supply the same evidence on cache reuse.

## Contract and selection

`dense_observations.collect()` owns extraction and cache verification. A valid cache
avoids audio/scene/motion recomputation; source hashing and FFmpeg version checks
still run. Source or producer/visual-input mismatches reject the cache without repair.
Audio amplitude rows receive the original spike/score fields where available
(starting at second 5). Scene rows are sorted by time; motion remains chronological.
Provenance retains native clocks, coverage, stream metadata, producer recipe and
cache content digest. Native clocks are not independently cross-modal calibrated.

Selection calls `evaluation.select_highlights(score_rows, "score", limit=5)` before
chronological adaptation: original Audio-only scores, stable producer tie order,
15-second greedy separation. `windows.build_candidate_windows()` supplies fixed
10-second pre-context and 5-second post-context, clamped to source duration.
Exactly five distinct anchors are required. No timestamp is fabricated, duplicated
or padded; insufficient candidates cause failure without publishing shared analysis.
Silence retains the existing zero-score tie behavior, not a claim of useful highlights.
Scene and motion measurements do not influence this baseline ranking.

Candidate provenance explicitly records Audio-only/fixed/selected_windows/k=5.
Both existing exporters accept this representation; the unified CLI can consume
it unchanged. This command performs no export. Missing optional signals remain
`not_analyzed`; an analyzed empty scene or CLIP list remains `analyzed` with `[]`.
Sources without an audio stream are unsupported by the existing collector.

## Safety and limitations

All four paths must be distinct, including existing hard-link aliases. Symlink paths
are rejected. An existing shared destination is rejected before collection. Outputs
inside the repository must be under `output/`. No overwrite or force option exists.
The source digest/size, cached content and current producer recipe are checked again
before publishing. The existing atomic JSON writer flushes a temporary sibling and
uses exclusive `os.link` publication: a racing destination causes failure, not replacement.
Filesystems must support hard links. This is not a multi-file transaction or protection
against hostile concurrent directory/source changes; do not run concurrent writers.
A successfully collected cache can remain if later adaptation/publication fails.
The cache and source are never repaired by this integration.

Optional evidence is validated by the existing schema/collector; arbitrary OCR,
semantic-event and VLM artifacts are not supported. No production modules, scoring,
export policies, research results or existing artifacts are changed.

## Verification

```powershell
python -m unittest test_dense_to_shared -v
python verify.py
python verify.py --cached-export --video videos/my_recording.mp4 --analysis output/shared_analysis_v1.json
```

Tests use synthetic measurements and mocked extraction/probing while exercising the
real collector cache logic, schema adapter, selection, exporter planners and atomic
publication. They require neither Tesseract nor model inference.
