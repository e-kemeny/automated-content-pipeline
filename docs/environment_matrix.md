# Environment matrix V1

Audit: 2026-10-19. Requirements/imports and local distribution metadata inspected;
no installs, upgrades, model loading or CUDA initialization. Package presence
does not prove native-library, model, codec or GPU compatibility.

| Boundary | Dependencies / existing specification | CPU / GPU status |
|---|---|---|
| Core exports, schema, windows, evaluation, verification | Standard library; requirements.txt is empty. FFmpeg + FFprobe for export; cache-only uses FFprobe | CPU working; exporters explicitly use libx264/AAC, not NVENC |
| Audio/scene/motion analysis | Standard library + FFmpeg/FFprobe; mono PCM extraction, scdet and raw grayscale frames | Existing CPU workflows; no new analysis run in this audit |
| Retention | Standard-library CSV/statistics; plotting lazily imports matplotlib (no requirements entry) | Metadata reports matplotlib 3.11.1 in default interpreter |
| Transcription | requirements-transcription.txt: faster-whisper 1.2.1, ctranslate2 4.8.2, av 16.1.0, onnxruntime 1.31.0, huggingface-hub 0.36.2, tokenizers 0.22.2; FFmpeg/FFprobe | Recorded small.en CPU/int8 run; explicit device/compute options exist, GPU unverified |
| Language | requirements-language.txt: torch 2.13.0, transformers 4.57.6; existing transcript | Recorded Qwen2.5-1.5B-Instruct CPU/float32 run; current implementation uses CPU, GPU is not automatic |
| CLIP / temporal semantics | requirements-clip.txt: torch 2.13.0, transformers 4.57.6, Pillow 12.3.0; FFmpeg/FFprobe for frame preparation | Recorded CPU experiment; temporal aggregation reuses evidence; GPU unverified |
| Multiframe VLM | requirements-multiframe.txt includes CLIP pins, adds torchvision 0.28.0 and num2words 0.5.14 | Recorded SmolVLM experiment; runtime success does not validate generated semantic judgments |

## Python and executable compatibility

Current verification uses Windows 11 AMD64, 64-bit CPython 3.14.0, FFmpeg and
FFprobe 9.0 Gyan full build. The code's hashlib.file_digest requires Python >=3.11;
this is an inferred API floor, NOT a tested support matrix. Python 3.11-3.13,
other operating systems and architectures have not been validated here. Optional
binary wheels may impose narrower Python/platform requirements.

FFmpeg must provide libx264/AAC for exports and the filters/formats used by
analysis (including scdet). FFprobe must support format/stream JSON output.
A successful -version command does not verify those capabilities. No project
minimum FFmpeg version is established. Keep tool builds recorded per experiment.

## Observed environments versus historical verification

| Interpreter | Current diagnostics | Evidence limits |
|---|---|---|
| Default python (3.14.0) | export profile passes; transcription fails (all six listed distributions missing); language fails (transformers missing). torch 2.13.0 and Pillow 12.3.0 metadata present | Regression/cached exports verified; package metadata alone does not demonstrate ML readiness |
| output/transcription_env/Scripts/python.exe | transcription profile passes; all six versions match its requirements | Metadata checked now; actual CPU ASR run recorded in transcription_v1.md, not rerun here |
| output/clip_env/Scripts/python.exe | language profile passes; torch/transformers and CLIP/multiframe package versions match their requirements | Metadata checked now; historical model runs documented in results/ and language_scoring_v1.md |

Historical notes describe a CPU-only PyTorch build despite NVIDIA hardware.
No current hardware detection or GPU initialization was performed. Successful
diagnostics mean no known missing essentials, not full environment certification.

## Known conflicts and unresolved questions

- Existing ASR documentation records PyAV 19 as incompatible with its backend;
  retain av 16.1.0 and the isolated ASR environment. This audit did not reproduce
  or resolve that conflict.
- CLIP/language repeat matching torch/transformers pins; multiframe includes
  CLIP. Requirements do not encode complete transitive locks or CPU/CUDA wheel
  indexes. torchvision/native torch compatibility still needs runtime testing.
- The CLIP environment historically inherited CPU PyTorch; copying a venv is
  not a reproducible installation strategy.
- Plotting is undeclared; base requirements is intentionally empty for core.
  There is no tested combined install or one-command full deployment.
- NVIDIA driver, CUDA libraries, CTranslate2 GPU support, VRAM needs and model
  dtype/device changes remain untested. A GPU wheel alone will not change code
  that explicitly selects CPU.
- Model revisions, prompts and artifacts are separate reproducibility inputs.
  Preserve recorded provenance; never infer them from package versions alone.

## Diagnostics contract

    python environment_check.py
    python environment_check.py --profile transcription
    python environment_check.py --profile language

Standard library only. Reports interpreter/OS/architecture, shutil.which results,
read-only -version calls (10-second timeout), and importlib.metadata versions.
No heavyweight imports, model downloads, files or CUDA contexts are created by
the diagnostic code. Normal Python execution may create bytecode caches; use
python -B when requiring no bytecode writes.

AVAILABLE means discoverable executable/version or installed distribution metadata.
MISSING means absent executable/package (or Python below the API floor).
UNKNOWN/UNVERIFIED means failed version/metadata inspection or untested runtime
compatibility. Only missing essentials cause exit 1; unknowns remain visible with
exit 0. CLI misuse returns 2. Export/transcription require both media tools;
language scoring consumes saved text, so those tools are optional in that profile.
Version mismatches are not silently certified: compare output with this matrix.
