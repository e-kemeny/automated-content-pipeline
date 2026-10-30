# Gameplay Content Pipeline

A Python engineering and research project for gameplay analysis and reusable video exports.

> 🚧 **In Development**

## Overview

Gameplay Content Pipeline is being built incrementally toward an automated workflow from gameplay footage to edited content. The current export workflow consumes persisted shared analysis to produce reviewable clips and a chronological assembled video, without rerunning analysis.

## Current Progress

- Portable file handling with `pathlib` and video duration probing with ffprobe.
- FFmpeg-based mono 16 kHz audio extraction and per-second audio activity/spike scoring against a rolling five-second baseline.
- FFmpeg scene-change detection and normalized multimodal ranking with experimental **70% audio / 30% visual** weighting. Each audio candidate uses the strongest nearby visual evidence within ±5 seconds.
- Greedy score-ranked selection with **15-second minimum separation** to suppress redundant highlights, followed by chronological output.
- Automatic Audio + Scene clip generation: 10 seconds before each selected event and 5 seconds after, clamped to video bounds.
- Human-labeled Top-5 and Top-10 evaluation, diagnostic clips for error analysis, and a terminal tool for human interval annotations.
- Shared Analysis V1 persists source identity, visual/acoustic evidence, timestamped speech, independent language signals, semantic events, candidate windows, and provenance. Missing signals remain explicitly not_analyzed.
- Optional local English transcription and experimental contextual relevance, humor, reaction, and narrative-context scoring are implemented as separate cached analysis stages.
- Shorts and Long-form exporters validate saved evidence and source identity, write manifests, and reuse verified outputs. The unified CLI delegates to both.

The Audio + Scene clip generation above describes the original main.py runner.
The current saved shared-analysis artifact instead contains **five preselected
Audio-only anchors** (40, 69, 84, 146, 170 seconds), not a complete candidate pool
or fresh multimodal ranking. Export does not reconstruct missing evidence.
Shorts can consume an explicitly declared compatible complete pool, but that is
not what this artifact contains; Long-form V1 uses preselected anchors.

**Shorts defaults to horizontal highlight MP4s**, retaining the source aspect
ratio, with fixed [-10,+5] second context. Optional vertical center cropping is
available through export_shorts.py --format vertical. Long-form expands anchors by 15 seconds
on each side, merges gaps up to 5 seconds, and assembles chronological footage.
This is a baseline assembly policy, not a validated narrative editor.

Not implemented: intelligent reframing, subtitles, music, publishing, a GUI, or
semantic/language-driven selection and validated narrative editing.

## Experimental Evaluation

The V1 harness matches predicted timestamps to human labels with ±5-second tolerance and one match per ground-truth event, reporting precision, recall, and F1. Both cutoffs use the same greedy selection rules.

An evaluation-only motion experiment samples **5 FPS at 160×90 grayscale**, measures mean absolute consecutive-frame difference, and averages it per second. Maximum-normalized motion replaces scene evidence in a separate Audio + Motion ranking, using the same association window and 70/30 weighting. Production clips still use Audio + Scene.

| Detector | Top-5 F1 | Top-10 F1 |
|---|---:|---:|
| Audio-only | 0.3333 | 0.4348 |
| Audio + Scene | 0.3333 | 0.4348 |
| Audio + Motion | 0.2222 | 0.4348 |

**Motion did not improve the baseline:** Top-5 F1 fell and Top-10 F1 tied. These experimental results come from **one already-edited Minecraft BedWars video**; they do not establish generalization. These baseline detectors are signal-based heuristics. Separate pretrained local-model experiments exist; no model was trained for this project.

## Current Research Direction

Human error analysis revealed that point timestamps poorly represented longer gameplay sequences worth retaining. Ground Truth V2 represents these as human-labeled time intervals with semantic types: `intro`, `transition`, `combat`, `objective`, `victory`, and `other`. Objectives can include meaningful events such as bed breaks.

V2 interval evaluation, descriptive retention alignment, fixed-window baselines,
dynamic-boundary V1/V2, CLIP/temporal CLIP, and multiframe semantic experiments
now exist. Frozen findings, including negative results, remain in results/.
Audio quiet periods were poor standalone boundaries; conservative V2 evidence
often fell back to fixed cuts. Semantic and language judgments remain experimental
and do not drive exports. Retention is descriptive viewer behavior, not ground
truth or a quality score; early and late absolute values are not directly ranked.

The focus is reusable evidence and reviewable outputs before changing selection
or claiming generalization beyond this single already-edited video.

## Run exports

From the repository root, with FFmpeg/ffprobe on PATH and a compatible saved
analysis plus its matching source video available locally:

    python pipeline.py videos/my_recording.mp4 --analysis output/shared_analysis_v1.json --mode both --dry-run
    python pipeline.py videos/my_recording.mp4 --analysis output/shared_analysis_v1.json --mode both

Modes: shorts, longform, both (default). --force explicitly refreshes owned
outputs under exporter safety checks. Both mode reports independent outcomes
and exits nonzero on partial failure. Outputs and manifests live under
output/<source-stem>/shorts/ and output/<source-stem>/longform/.
Missing analysis is an error, not a request to run models. Media and saved
runtime artifacts are Git-ignored and are not supplied by a fresh clone.

## Test and develop

    python -m unittest discover -q
    python test_motion.py

The second command runs four standalone checks not discovered by unittest.
The audit baseline is 263 unit tests plus four motion checks. Tests use fixtures
and mocks; they do not require model downloads. Export uses Python's standard
library and FFmpeg/ffprobe; optional analysis stages have separate environments.

See [developer setup](docs/developer_setup.md) for the observed environment and
dependency caveats; there is no verified one-command full installation.

## Architecture and repository map

Analysis producers -> shared_analysis.py / persisted JSON -> export consumers.
Both output modes read the same artifact; export never recomputes its evidence.
Schema validation, chronological timing, missing-data states and provenance keep
experimental signals distinct from selection inputs.

- pipeline.py, export_shorts.py, export_longform.py: current export entry points.
- shared_analysis.py, windows.py, semantic_events.py: reusable representations.
- main.py: original analysis/evaluation/clipping runner; executes at module load.
- transcription.py / transcribe_video.py: optional speech stage.
- language_scoring.py / score_language.py: optional experimental language stage.
- evaluate_*.py, dynamic_windows*.py, semantic_clip.py, temporal_semantics.py,
  multiframe_semantics.py, motion.py: research tooling.
- evaluation.py / evaluation_v2.py: separate point and interval evaluators.
- annotate.py, ground_truth_v2.json, retention.py, analyze_retention.py,
  error_analysis.py: human annotation and descriptive diagnostics.
- test_*.py, docs/, results/: tests, usage/schema notes, frozen research reports.
- videos/, output/: ignored local media, artifacts, caches and environments.

Details: [unified CLI](docs/pipeline_cli_v1.md),
[shared schema](docs/shared_analysis_architecture.md),
[repository audit and cleanup plan](docs/repository_audit.md).

## Windows export-only setup

Run `./setup.ps1 -CheckOnly`, then `./setup.ps1 -InstallMissing` to enable
approval-gated WinGet installation of missing Python 3.14 x64 and FFmpeg/FFprobe.
The flag is not consent: exact commands are shown before a separate approval.
Default `./setup.ps1` keeps guided system setup. `-SkipSmokeTest` skips functional
smoke testing; diagnostics still run. PATH is never refreshed automatically.
The export profile needs no third-party Python packages or ML dependencies.
See [Windows installer V2](docs/windows_installer_v2.md) for bootstrap, approvals,
restart/recovery behavior and unverified second-machine installation limits.

## GPU environment diagnostics

Run `python -B -S gpu_check.py` for read-only NVIDIA hardware, driver and memory
metadata. CUDA runtime, PyTorch CUDA and actual inference remain unverified.
See [GPU environment V1](docs/gpu_environment_v1.md) for laptop/desktop scope
and future RTX 4090 validation steps. No models or drivers are installed.

Optional PyTorch runtime diagnostics: `python gpu_runtime_check.py --check-only`
queries devices without tensor execution; the default command verifies tiny CUDA
arithmetic. See [GPU runtime verification V1](docs/gpu_runtime_verification_v1.md).
This is separate from exports and does not install dependencies or run models.

## RTX 4090 deployment verification

The desktop passed basic CUDA arithmetic in its separate GPU environment; actual
ML inference, model compatibility and performance remain unverified.
Run `python deployment_check.py` for detection, or add `--execute-cuda` to opt
into the tiny execution check, using the intended environment's interpreter.
See [verified RTX 4090 configuration and workflow](docs/rtx4090_deployment_v1.md).

## Experimental GPU vision inference

Optional vision_inference.py --video videos/my_recording.mp4 runs pretrained
ResNet-18 on temporary sampled frames in a CUDA environment. Weights must already
be cached unless --allow-model-download is supplied. This is an ImageNet
classification experiment, not production video understanding or highlight scoring.
See [GPU vision inference V1](docs/gpu_vision_inference_v1.md) for desktop commands,
output safety and interpretation limits.

## Optional vertical Shorts

    python export_shorts.py videos/my_recording.mp4 --analysis output/shared_analysis_v1.json --format vertical

Produces 1080x1920 center-cropped H.264/AAC clips. Selection and timing stay unchanged;
vertical outputs use a separate cache directory. Horizontal export remains default.
See [vertical Shorts V1](docs/vertical_shorts_v1.md) for cache rules and crop limitations.
