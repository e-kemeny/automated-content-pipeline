# Portable setup plan V1

This is a proposed staged deployment, not a verified second-machine install.
No packages, requirements or model settings were changed by the audit.

1. Establish an export-only Windows baseline. Copy/clone the committed source
   into a user-chosen project directory. Start with 64-bit CPython 3.14 matching
   the recorded environment and a recorded FFmpeg/FFprobe build on PATH. Other
   Python versions require separate validation. Run environment_check.py and
   verify.py using the intended interpreter, not an assumed global python.
2. Transfer owned source media and saved JSON/MP4 artifacts separately from Git.
   Preserve originals, SHA-256 identities and frozen reports. Paths are CLI
   arguments/pathlib; run from the repository root for relative defaults. There
   is no central local configuration system. Do not copy virtual environments.
   Analysis/manifests may retain absolute source/output paths. Moving files can
   make strict cache identity checks reject them; do not hand-edit provenance or
   weaken validation. Test on a copy and plan an explicit relocation workflow
   before promising portable cache reuse.
3. Run dry-run planning, then strict cached verification if compatible artifacts
   exist. It must not encode or repair. Missing/stale caches are an expected
   blocker, not permission to use --force. A separately authorized ordinary export
   can build new outputs later without touching frozen research. Compare hashes,
   manifests, streams/durations and test counts.
4. Add one isolated optional environment at a time using existing stage-specific
   requirements. First preserve installer logs, interpreter/build details, wheel
   sources, resolved distribution versions and model revisions. Test dependency
   resolution on the second machine before generating a lock or consolidating
   files. Do not upgrade the known environment to resolve a new-machine conflict.
   Run environment_check.py with that environment's interpreter and profile.
5. CPU first: small.en defaults to CPU/int8; language uses CPU/float32. Recorded
   visual experiments used CPU. Expect slow model inference and memory pressure;
   do not claim equal performance or accuracy on another machine. Any actual
   smoke inference is a later, explicit step with separate output artifacts.
6. Optional NVIDIA acceleration is a separate experiment. Inventory driver/GPU
   and choose compatible Python, torch/torchvision or CTranslate2 GPU builds from
   then-current official requirements. Verify native libraries, VRAM, precision,
   model/device support and output parity in a disposable environment. Preserve
   CPU fallback as an explicit environment/configuration choice, not a silent
   switch. Existing exporters remain CPU libx264/AAC; GPU inference does not
   imply NVENC export. Language/visual code may require a later bounded device
   interface change; do not alter frozen model contracts during setup.
7. Only after clean-machine tests and controlled smoke runs, record a per-stage
   reproducible install manifest/lock and supported platform matrix. Keep
   core tests, cache-only integration and optional ML smoke checks separate.

## Suggested next milestone

Create an explicit source/artifact relocation audit (read-only initially) and
perform an export-only verification on a second Windows machine. Record which
persisted paths are informational versus identity-bound before implementing any
migration. This resolves a real portability risk without mixing dependency
changes with model/device changes.

Remaining questions: binary wheel availability, transitive dependency conflicts,
FFmpeg filter/codec parity, inherited site packages, cache-path identity,
CPU/GPU numerical differences, inference memory/time and model-cache transfer.
Use environment_matrix.md for observed versions and verification limits.
