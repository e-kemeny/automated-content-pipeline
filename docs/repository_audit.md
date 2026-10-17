# Repository audit V1

Audit date: 2026-10-14. Scope: documentation and ignore hygiene only.
No Python movement, algorithm/schema changes, dependency installs, or deletion.

## Inventory

| Category | Files / role |
|---|---|
| Current export workflow | pipeline.py delegates to export_shorts.py and export_longform.py; verified-cache export and manifests |
| Shared interfaces | shared_analysis.py (schema/persistence/adapters), windows.py (fixed windows/overlap), semantic_events.py (event schema/queries) |
| Optional analysis stages | transcription.py + transcribe_video.py; language_scoring.py + score_language.py (experimental judgments) |
| Original runner / baseline signals | main.py performs audio/scene ranking, motion comparison and stream-copy clipping; evaluation.py has frozen selection and V1 labels; motion.py is experimental |
| Interval and boundary research | evaluation_v2.py, evaluate_fixed_windows.py, dynamic_windows.py, dynamic_windows_v2.py, evaluate_dynamic_windows.py, evaluate_dynamic_windows_v2.py |
| Semantic research | semantic_clip.py, temporal_semantics.py, multiframe_semantics.py and their evaluate_* entry points |
| Human/descriptive tooling | annotate.py, ground_truth_v2.json (14 human intervals), error_analysis.py, retention.py, analyze_retention.py |
| Tests | test_*.py covers shared schema, transcription/language, exporters/CLI, annotations, retention, windows/evaluation, boundaries and semantics; test_motion.py additionally runs four plain-function checks |
| Usage docs | shared_analysis_architecture.md, transcription_v1.md, language_scoring_v1.md, shorts_export_v1.md, longform_export_v1.md, pipeline_cli_v1.md; developer_setup.md added by this audit |
| Frozen reports | results/fixed_window_v2_baseline.md, dynamic_window_v1.md, dynamic_window_v2.md, clip_semantic_v1.md, temporal_clip_v1.md, multiframe_semantic_v1.md, language_scoring_v1.md, retention_case_study.md |
| Runtime artifacts (ignored) | videos/ source media; output/ extracted audio, diagnostic/rendered clips, JSON analysis/manifests, frame samples, plots, model caches and local environments; named Audience retention export directory |

The original main.py is retained as a legacy entry point and reproducibility
dependency, not dead code. No experimental file is a deletion candidate in this
milestone. Older milestone documents describe the state at their original
delivery; README and developer_setup.md describe the current entry points.

## Five priority debt findings

1. **Analysis and side effects are coupled.** main.py runs at import, uses fixed
   videos/my_recording.mp4 and output/audio.wav / clip_N.mp4 paths, and overwrites
   outputs. Fixed/dynamic experiment runners use runpy to execute it and can
   replace reports. Future extraction needs golden-output parity tests first.
2. **Media/persistence responsibilities cross module boundaries.** FFprobe/audio
   extraction logic recurs in the original runner and newer tooling; exporters
   use media helpers from transcription.py, and Long-form uses Shorts planning
   for validation. JSON writing/atomic publication approaches also vary. Preserve
   intentional stream-copy versus accurate re-encode differences when factoring.
3. **Environment specifications are fragmented.** The base requirements.txt is
   empty; optional files share repeated torch/transformers pins, multiframe
   includes CLIP, ASR pins a separate stack, and plotting lacks a declared extra.
   There is no unified tested lock/build profile. See developer_setup.md for
   exact versions and the documented PyAV conflict; do not merge blindly.
4. **Persisted evidence is not an end-to-end candidate pipeline.** The real
   artifact has five preselected Audio-only anchors from dynamic-window research.
   Adapters exist but there is no unified raw-video-to-complete-shared-analysis
   CLI. A compatible complete pool is a distinct Shorts input contract; Long-form
   consumes preselected anchors. Schema V1 also includes an additive language
   extension, requiring compatibility tests before future migrations.
5. **Verification and recovery need clearer boundaries.** Unit discovery omits
   four standalone motion checks; real media/model checks are manual and local.
   Export cache safety is tested, but full cross-process locking is absent and
   interruption can leave unowned clips. Frozen reports and ignored raw artifacts
   need an explicit reproducibility/archive policy, not blanket cleanup.

## Portability and dependency observations

No user-specific absolute Windows path was found in tracked Python source by
the audit search. Paths are mostly pathlib-based, but many defaults assume the
repository working directory and this video. analyze_retention.py defaults to
231.433288 seconds (overridable); language scoring's topic is BedWars/texture
packs. Those are experiment assumptions, not generic media intelligence.
Documentation uses Windows virtual-environment executable paths and records
CPU-only model runs; CUDA performance/installation is not established.

requirements-clip.txt and requirements-language.txt agree on current shared
pins; multiframe inherits them. This does not prove all extras can coexist.
The ASR docs identify av 19 versus the pinned 16.1.0 backend issue. Torch wheel
source, transitive dependencies, FFmpeg build and model-cache availability are
not fully encoded by requirements files. No reinstall or dependency resolution
was performed during the audit.

## Ignore hygiene

Existing rules already cover videos/, output/, bytecode/test caches, common
virtual environments, .env and the named raw YouTube export directory. Current
model weights/environments are beneath output/. No tracked MP4/WAV/CSV/model
weight files were found in the inventory check.

Add only .venv-*/ for alternate local environments and .env.* with an exception
for .env.example. Avoid global *.json, *.csv or model-extension ignores that
could hide fixtures, annotations or provenance. Source/docs/results remain
visible. New artifact locations should get narrow rules when introduced.

## Proposed organization (future only)

- src/gameplay_pipeline/core/: schemas, windows, source identity and media I/O.
- src/gameplay_pipeline/analysis/: optional evidence producers and adapters.
- src/gameplay_pipeline/export/: Shorts/Long-form planning and assembly.
- research/: frozen experiment runners with compatibility entry points.
- tests/: unit fixtures and separately invoked integration checks.
- docs/ and results/: guides and immutable experiment reports.

This is a proposal, not a directory migration or approved API change.

## Staged cleanup and risks

1. Next: add a documented, opt-in verification entry point that runs unittest
   plus motion checks, separates cached-media integration checks, and records
   tool versions. Keep inference/encoding forbidden in cache verification.
2. Inventory installed optional environments and record reproducible per-stage
   build profiles in a separate milestone; validate fresh installs before
   consolidating requirements. Preserve historical model revisions/prompts.
3. Extract shared media/validation helpers behind current APIs with regression
   tests for source identity, exact manifests, boundaries and failure recovery.
4. Only then introduce package directories and compatibility wrappers. Keep
   frozen runner behavior and report provenance reproducible.

Risks include import-time analysis, changed tie/order behavior, overwritten
research artifacts, loss of local ignored evidence, invalidated cache identity,
and accidental cross-environment upgrades. No such refactor is part of V1.

## Import-safety update (2026-10-17)

main.py now exposes run_pipeline() for explicit execution and main() for the
unchanged CLI. Import no longer checks video existence, probes/extracts/processes
media, evaluates candidates, prints diagnostics or cuts clips. Reusable helpers
and the default video_path remain accessible. No model was loaded by the old
runner; this change adds none.

The three fixed/dynamic research runners now call run_pipeline() explicitly and
consume its returned duration_seconds, audio_scores and scene_scores rather than
runpy execution globals. Algorithm statements, order and FFmpeg arguments remain
unchanged. Historical inventory above describes the pre-refactor state.

Remaining debt: execution still uses CWD-relative fixed media/output paths,
overwrites normal clips, couples analysis/evaluation/export, and retains existing
error handling and stream-copy boundary behavior. Research runners still execute
the full workflow and can replace reports. No package reorganization or behavior
cleanup was performed.
