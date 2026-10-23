# Second Windows machine: export-only validation V1

Local validation: 2026-10-23, Windows 11 AMD64, CPython 3.14.0 (64-bit),
FFmpeg/FFprobe 9.0 Gyan full build. The relocated-directory smoke test passed
on the existing machine. **No second computer or RTX 4090 validation occurred.**
Python >=3.11 is the inferred API floor, not a verified version matrix.

## Minimal setup on another Windows computer

Core exports need only Python's standard library and FFmpeg/FFprobe on PATH.
No pip packages, model weights, CUDA or GPU are needed. Do not install the optional
CLIP/VLM/transcription/language requirements for this workflow. Do not copy venvs.
Use an owned local directory on a filesystem supporting hard links (locally tested
on the current Windows filesystem). Export publication uses same-directory links.

Install the recorded Python and FFmpeg builds separately on the destination;
this milestone does not install or upgrade anything. FFmpeg needs libx264, AAC,
PCM audio, MP4/Matroska, concat, and accurate seeking. The smoke fixture also
uses lavfi testsrc2/sine. FFprobe needs format/stream JSON support. Merely finding
an executable or printing its version does not verify these features.

Replace the repository URL and select a desired parent directory:

```powershell
git clone <repository-url> gameplay-export
cd gameplay-export
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe environment_check.py
.\.venv\Scripts\python.exe verify.py
.\.venv\Scripts\python.exe -B -S portability_smoke.py
```

Ensure the checkout includes this milestone. No pip installation is necessary.
Record Python and FFmpeg/FFprobe versions, commit ID and command output on the
second machine. Only then report that machine as verified. Missing optional
packages in the export diagnostics are expected; missing FFmpeg/FFprobe is not.

## Smoke test scope and local result

```powershell
python -B -S portability_smoke.py
```

The runner creates one uniquely named temporary subtree inside the repository by
default. `--temp-parent <existing-directory>` can select another local parent;
only the unique subtree is cleaned, including on failure. Never point it at
production media: it accepts no production source/analysis arguments.

It copies an explicit ten-module export dependency set, generates an 80-second
160x90/10 FPS synthetic video with audio, and creates schema-valid synthetic
preselected anchors at 10, 25, 40, 55 and 70 seconds. These are test inputs, not
real detector predictions; no scores or semantic evidence are fabricated.

It invokes the real unified CLI in mode both with explicit manifest V2 and an
initially empty isolated output root. Five Shorts and one Long-form MP4 plus two
manifests are produced. It checks original cache reuse, relocates the workspace,
source and output directory, then checks reuse again. It also requires both
exporters to reject modified and missing source content without repair.

All cache-only checks compare the complete fixture file/directory inventory,
SHA-256 hashes and nanosecond mtimes (including the nine analysis/export artifacts).
Children run with `-B -S`: no bytecode writes or site packages. An audit hook rejects
heavyweight imports and, during cache checks, filesystem writes and subprocesses
other than FFprobe. These are test guards, not a hostile-code security sandbox.
The original validators run unchanged. Temporary encoding is sequential and uses
the exporters' actual settings. Production media and exports are never copied.

Local result: all four PASS summaries; both exporters succeeded before/after
relocation, both negative cases failed correctly, inventory/hash/mtime checks
passed and temporary files were removed. This proves local relocation with real
encoding/probing, not cross-machine codec parity or perceptual A/V quality.

## Transferring or recreating V2 exports

Transfer the source bytes, unchanged analysis JSON, and the complete V2 output
tree separately from Git. Keep the source filename stem: output discovery still
uses `<output-root>/<source-stem>/shorts|longform`. Historical absolute locators
are informational for V2; do not edit them or analysis paths in persisted JSON.
Use explicit CLI paths from the checkout root:

```powershell
python pipeline.py media/game.mp4 --analysis artifacts/analysis.json --mode both --manifest-version 2 --output-root portable_exports --cache-only
```

Failure is not permission to force, repair or hand-edit a manifest. Differences
in source bytes, analysis raw bytes, media metadata, settings or output integrity
must be investigated. Copying analysis must preserve its exact bytes.

To intentionally recreate exports, choose a new empty output root outside
`output/`, use V2 with `--dry-run`, then explicitly run without `--dry-run` or
`--cache-only`. This encodes new outputs. It does not migrate legacy artifacts.
V2 rejects force and nonempty destinations; normal reruns must use cache-only.
Legacy V1 keeps its original absolute-source-path binding and remains the default.

## Limits and troubleshooting

- Run CLI commands from the checkout root, or supply absolute paths. Relative
  input/output defaults depend on cwd; no machine-specific path fix was needed.
- verify.py cached integration targets default V1 `output/` and five Shorts;
  use the explicit V2 CLI above for transferred V2 trees.
- Spaces in relocated paths passed locally. Unicode paths, network shares,
  alternate filesystems, cloud-sync races and different FFmpeg builds are unverified.
- Keep concurrent writers and sync changes away from validation. There is no
  pair activation, coordinated lock, migration utility or crash-recovery protocol.
- Hard-link errors or missing codecs are environment blockers. Preserve failures;
  do not weaken cache checks or substitute stream-copy encoding.
- Smoke failures return nonzero and clean their owned subtree. Console diagnostics
  are retained in terminal output; generated fixtures are intentionally disposable.
- GTX/RTX hardware is irrelevant to current CPU libx264/AAC export. No CUDA setup,
  NVENC, inference or RTX 4090 execution was tested.
