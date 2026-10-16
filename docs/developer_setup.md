# Developer setup and testing

Run commands from the repository root. The 2026-10-14 audit used Windows,
CPython 3.14.0 and FFmpeg 9.0 (Gyan full build), with ffprobe on PATH. These
describe the working machine, not a portable lockfile or minimum-version claim.

    python --version
    ffmpeg -version
    ffprobe -version
    python -m unittest discover -q
    python test_motion.py

Expected audit baseline: 263 unittest tests and four standalone motion checks.
Model/FFmpeg calls are mocked in relevant unit tests; real export verification
is a separate integration check. Do not run main.py or research runners as tests:
they may regenerate clips, run analysis, and overwrite frozen report paths.

## Export-only use

Python standard library plus FFmpeg/ffprobe is sufficient; requirements.txt is
empty. No ML environment is needed. Obtain the matching source media and saved
Shared Analysis V1 artifact through your existing local workflow; a clone does
not include videos/ or output/. A transcript-only analysis lacks candidate
evidence and cannot export highlights.

    python pipeline.py videos/my_recording.mp4 --analysis output/shared_analysis_v1.json --mode both --dry-run
    python pipeline.py videos/my_recording.mp4 --analysis output/shared_analysis_v1.json --mode both

Dry run validates and previews. A normal repeat verifies and reuses owned cache
outputs. Do not use --force for a cache check: it requests fresh encoding.
See the individual exporter docs for configurable output roots/context settings.

## Optional environments

Do not install every requirements file into one environment.

| Stage | Existing dependency specification / notes |
|---|---|
| CLIP | requirements-clip.txt: torch 2.13.0, transformers 4.57.6, Pillow 12.3.0 |
| Multiframe | requirements-multiframe.txt includes CLIP pins; adds torchvision 0.28.0 and num2words 0.5.14 |
| Language | requirements-language.txt repeats torch/transformers pins; prior run reused output/clip_env read-only |
| Transcription | requirements-transcription.txt: faster-whisper 1.2.1, ctranslate2 4.8.2, av 16.1.0, onnxruntime 1.31.0, huggingface-hub 0.36.2, tokenizers 0.22.2 |
| Retention plot | matplotlib is lazily imported but is not declared in a requirements file |

Local output/clip_env and output/transcription_env exist; historical setup/model
details are in transcription_v1.md, language_scoring_v1.md and results/.
Windows Scripts/python.exe examples require adjustment on other platforms.
The recorded PyTorch build is CPU-only despite an installed NVIDIA GPU;
package versions alone do not specify the accelerator build. ASR documentation
records PyAV 19 as incompatible with the chosen backend. Keep its av pin and
environment separate. Other cross-environment conflicts have not been resolved
or tested as a combined install.

No dependencies were installed/upgraded for this audit. Future consolidation
should separate core/test, plotting, ASR, and research extras, record Python and
wheel source/build information, and verify isolated installs before promising
reproducibility. Preserve old experiment environments and model revisions.

Do not commit local media, model caches, credentials, or audience exports.
Keep frozen results/, annotations, prompts and provenance under version control.
Ignored output/ also contains valuable analysis and environment state: it is
not disposable merely because Git ignores it.

## Regression verification

Use python verify.py to run unittest discovery and all four motion checks.
For existing local caches, also run:

    python verify.py --cached-export --video videos/my_recording.mp4 --analysis output/shared_analysis_v1.json

This uses strict cache-only export and checks all nine artifact hashes/mtimes.
See [Verification V1](verification_v1.md) for prerequisites and failure behavior.
