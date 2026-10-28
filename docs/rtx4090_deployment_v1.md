# RTX 4090 deployment verification V1

Desktop verification record supplied by the project owner on 2026-10-28.
These results were obtained on the desktop, not rerun by the laptop development
session. The desktop is the primary GPU inference machine; the laptop remains
the primary development machine.

| Component | Verified desktop value |
|---|---|
| OS / architecture | Windows 11 / AMD64 |
| GPU | NVIDIA GeForce RTX 4090 |
| Total VRAM | 24564 MiB |
| NVIDIA driver | 617.42 |
| Driver-reported CUDA | 13.4 |
| Python | 3.14.7 |
| PyTorch | 2.14.1+cu126 |
| PyTorch CUDA build | 12.6 |
| CUDA device | cuda:0 |
| torch.cuda.is_available() | True |

Verified command:

    .\.venv-gpu\Scripts\python.exe gpu_runtime_check.py

Verified output:

    PASS: tiny CUDA arithmetic, synchronization and CPU comparison

Basic CUDA arithmetic passed. Driver-reported CUDA is driver support, not the
installed PyTorch CUDA runtime; the framework reports its own CUDA build.
Actual ML model inference, model compatibility and performance remain unverified.
The existing export-only environment was not modified. The separate .venv-gpu
is Git-ignored by the existing .venv-*/ rule. No environment is copied or installed
by this workflow. Earlier GPU documents retain their historical validation scope;
this record supplies the later desktop arithmetic result.

## Future-machine workflow

Run from the checkout with your intended interpreter:

    python deployment_check.py
    python deployment_check.py --execute-cuda

For the desktop environment explicitly:

    .\.venv-gpu\Scripts\python.exe deployment_check.py
    .\.venv-gpu\Scripts\python.exe deployment_check.py --execute-cuda

The runner uses sys.executable and absolute diagnostic script paths; it never
switches environments. Default mode runs gpu_check.py then gpu_runtime_check.py
--check-only. Detection may initialize the framework/driver but allocates no
CUDA tensors. Only --execute-cuda enables the tiny arithmetic check, and only
after both detection stages succeed. No models or media are processed.

Each subprocess has a 60-second timeout and uses -B to suppress Python bytecode
writes. The orchestrator uses only the standard library, reads script existence,
captures console output and writes no files, directories or output artifacts.
Existing PyTorch diagnostics require an installed optional PyTorch environment;
the runner installs nothing. Third-party runtime/driver internals are not a
filesystem sandbox and may maintain their own caches.

Exit 0 means all requested checks passed; default success certifies detection
only. Exit 1 means a missing script, timeout, launch/decoding error, nonzero child
exit or missing positive evidence. Argument misuse returns 2. Both detection
stages report independently; execution is skipped after detection failure.
No-device reports from gpu_check.py can have exit 0, so this runner also requires
positive hardware and driver markers. Runtime detection and execution likewise
require their existing positive console markers; changed diagnostic wording fails
conservatively and needs a corresponding test/update.

No full inference deployment, capacity, throughput or general model support is
certified. A timeout terminates the diagnostic child but is not a driver recovery
mechanism. Missing PyTorch/CUDA or DLL errors should be investigated in the printed
interpreter; there is no CPU fallback, package repair or driver change.
The orchestration tests mock every subprocess and require neither GPU nor PyTorch.
