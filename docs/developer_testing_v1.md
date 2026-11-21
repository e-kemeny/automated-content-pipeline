# Developer testing workflow V1

From the repository root, use the existing Python environment with FFmpeg and
FFprobe available. No new dependencies or ML inference are introduced.

```powershell
python dev_test.py "D:\recordings\gameplay.mp4" --mode both
python dev_test.py "D:\recordings\gameplay.mp4" --mode shorts --dry-run
python dev_test.py "D:\recordings\gameplay.mp4" --mode both --cache-only
python dev_test.py "D:\recordings\gameplay.mp4" --mode longform --output-root "D:\pipeline-tests"
```

Default outputs live under `output/dev_tests/<video-stem>/dev_test_v1/`:

- `dense.json`: existing dense collector artifact.
- `shared_analysis.json`: existing five-anchor Audio-only integration output.
- `exports/<video-stem>/shorts/` and `longform/`: existing exporter outputs/manifests.
- `candidate_review.csv`: five candidate windows, anchors, original scores, planned
  Shorts paths and blank human quality-rating/notes columns. Check exporter status
  and manifests for output availability. Long-form-only runs label Shorts as not requested.

This preserves the Audio-only baseline, 15-second suppression, fixed Shorts
boundaries and existing Long-form expansion/merging. It does not improve selection
quality or implement Adaptive Understanding. Current Shorts remain horizontal.

## Reuse and safety

Fresh work delegates to `dense_to_shared.generate`. Reuse validates the dense artifact
with existing schema/source/producer validators and compares the complete saved
analysis against `dense_to_shared.adapt`. It does not enter create-if-missing collection
for read-only operations. Stale/missing evidence fails rather than silently rebuilding
existing analysis. This runner manages its own baseline cache without optional CLIP;
it does not discover or import unrelated caches or analysis artifacts.

An existing export directory always uses strict cache-only export, preserving MP4s
and manifests. Partial/invalid output folders fail; use a different `--output-root`
for a fresh isolated run. There is no force option. The report is published exclusively
and atomically, and existing reports (including human edits) are preserved. Reports
contain planned paths, not promises that a failed export produced files.

`--dry-run` creates nothing and does not collect observations. Without a cache it
prints pending stages and paths; with cached evidence it validates candidates. Export
preview requires an existing shared-analysis file. `--cache-only` requires existing
analysis/cache and delegates all selected exports to strict cache-only mode. It never
creates the review report. The flags are mutually exclusive; failures return nonzero.
Both-mode export failures are reported separately, and the other export is attempted.

Generated files inside this repository must remain under ignored `output/`. Custom
roots may be outside the repository. Do not run concurrent writers. This is not an
atomic multi-artifact transaction: successful earlier stages remain after failure.
Paths/provenance are deliberately compared strictly; moving an existing workspace can
invalidate reuse. On a second machine, use its working export/analysis environment and
source media, then a new output root if relocation validation fails. No GPU is needed.
Same-stem videos sharing a root are rejected on source mismatch; give them separate roots.
Sources need audio/video streams and five separated candidates; nothing is padded.

## Tests and manual review

```powershell
python -m unittest test_dev_test -v
python verify.py
python verify.py --cached-export --video videos/my_recording.mp4 --analysis output/shared_analysis_v1.json
```

Automated developer tests mock media extraction/export while retaining actual cache,
analysis, selection and report validation. They do not establish highlight quality.
Play the outputs and fill the CSV rating/notes fields manually. Keep baseline review
folders for future comparisons; use a separate root for future selection experiments.
The reported ARC Raiders result demonstrates working export infrastructure, not strong
Shorts selection. Actual full-video runs remain an explicit developer action.
