# GPU runtime verification V1

Development stays on the laptop. The planned RTX 4090 desktop will own models,
videos, inference workloads and exports. This optional tool is independent of
the pipeline; it neither installs packages nor loads models.

## Run

Use the interpreter in your chosen optional PyTorch environment:

    python gpu_runtime_check.py --check-only
    python gpu_runtime_check.py
    python gpu_runtime_check.py --device cuda:0

Importing this module (including test discovery) does not import PyTorch.
Invoking its CLI imports PyTorch lazily and reports interpreter, framework build,
CUDA availability, visible device names and selected device. Check-only performs
no tensor allocation, arithmetic or synchronization. Runtime/device queries may
initialize CUDA or contact its driver: this is not the driver-only gpu_check.py.

Execution allocates two four-element int64 tensors on the selected CUDA device,
adds them, synchronizes that device and transfers the result to CPU. It compares
against Python's independently computed integer sums. PASS certifies only this
tiny operation in that process, not model inference, performance or VRAM capacity.
No CPU fallback is allowed. Device indices refer to PyTorch-visible devices and
can differ from physical enumeration when visibility settings are applied.

Exit codes: 0 = detection succeeded in check-only, or arithmetic passed in default
mode; 1 = missing PyTorch, CPU-only build or unavailable CUDA; 2 = invalid arguments
or unavailable device index; 3 = import/initialization/operation/transfer failure
or incorrect result. Check-only never claims execution PASS.

## Separate optional setup (manual, future action)

Do not alter the export environment or setup.ps1. Choose a 64-bit Python version
supported by the intended PyTorch wheel, then create a separate environment,
for example outside the checkout:

    python -m venv "$env:USERPROFILE/venvs/pipeline-gpu"

Use that environment's Scripts/python.exe for all subsequent commands; activation
is optional. Follow the official [PyTorch installation selector](https://pytorch.org/get-started/locally/)
for Windows, pip and an appropriate CUDA build. Run its selected pip command
through the new interpreter with -m pip. Check current Python/wheel/driver/GPU
compatibility first; no universal CUDA/PyTorch version is prescribed here.
Record the exact installation command and resolved package versions. Do not copy
a laptop venv to the desktop. These setup steps were not executed in this milestone.

Driver-advertised CUDA from nvidia-smi describes driver support;
torch.version.cuda describes the framework's CUDA build. Neither alone proves
runtime compatibility or indicates an installed standalone CUDA toolkit.
See the [PyTorch CUDA API](https://docs.pytorch.org/docs/stable/cuda.html).
An actual successful calculation provides narrower, concrete runtime evidence.

## Troubleshooting and limits

- Missing torch: check the printed interpreter; install only in the intended
  optional environment using official instructions when authorized.
- CPU-only build / CUDA unavailable: inspect the selected wheel, driver and device
  visibility. Do not reinstall the working export dependencies as a workaround.
- Invalid index: select from the reported visible devices; no automatic fallback.
- DLL, initialization, synchronization or kernel errors: preserve the message and
  exact environment versions; consult official compatibility information.
- No timeout/watchdog is imposed on native driver calls; a broken driver can hang.
  Interrupt the standalone process and investigate before rerunning.
- Imports/native libraries can have their own initialization/cache behavior.
  This is not a strict no-write sandbox for third-party code.
- No models, mixed precision, large allocations, stress tests or benchmarks run.

Validation for this milestone uses a mocked backend only. Actual GPU execution
on both laptop and RTX 4090 desktop remains **UNVERIFIED**. No real runtime
check-only invocation was required or performed. Ordinary repository tests do
not require or import PyTorch.
