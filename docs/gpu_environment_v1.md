# GPU environment diagnostics V1

Development remains on the laptop. The planned RTX 4090 desktop will own model
files, video inputs, inference and generated outputs. This tool gathers driver
metadata only; it does not move assets, select a model or change export behavior.

```powershell
python gpu_check.py
# Suppress bytecode and site-package startup for the strictest read-only run:
python -B -S gpu_check.py
python -m unittest test_gpu_check -q
```

Only the standard library is needed. nvidia-smi must be discoverable on PATH.
The only external command is `<resolved-nvidia-smi> -q -x`, with a ten-second
timeout and captured output. XML is parsed locally; there are no output files,
installer calls, model imports, CUDA context creation or inference. NVIDIA's
management query does access its driver; this is not a CUDA computation test.

## Reading the result

- OS, machine architecture, Python version/bitness and interpreter are shown.
- DETECTED means nvidia-smi returned GPU records. It is not an independent PCI
  hardware inventory. Each visible GPU gets its own name, identifier and memory.
- AVAILABLE driver means a valid query returned a driver version. Query failures
  leave both driver/hardware UNVERIFIED rather than claiming the machine has no GPU.
- Driver-reported CUDA is the driver's advertised CUDA support, not proof of an
  installed toolkit or working framework runtime. Legacy driver_version/cuda_version
  and newer kmd_version/cuda_umd_version XML fields are supported.
- Free/total framebuffer memory is reported in MiB as a point-in-time driver
  observation, not guaranteed allocatable model capacity. Other processes and
  Windows memory accounting can affect it. Missing/N/A values remain UNVERIFIED.
- CUDA runtime compatibility, PyTorch CUDA availability and actual GPU inference
  always remain UNVERIFIED, including when hardware/driver detection succeeds.

See NVIDIA's [nvidia-smi reference](https://docs.nvidia.com/deploy/nvidia-smi/index.html)
for XML queries and memory reporting, and its [driver compatibility explanation](https://docs.nvidia.com/datacenter/tesla/drivers/latest/cuda-toolkit-driver-and-architecture-matrix.html)
for the meaning of the CUDA version reported by the driver.

Exit 0 means the diagnostic obtained a valid report, including a recognized
no-devices result; it does NOT mean GPU inference is ready. Exit 1 means the tool
was missing, timed out, failed, or returned malformed core XML. In a no-devices
text response, hardware is NOT DETECTED but driver availability stays UNVERIFIED.
A missing nvidia-smi on PATH cannot distinguish absent hardware from missing
installation/PATH/driver access. Missing optional CUDA/memory fields do not erase
otherwise valid hardware evidence. Unexpected XML schemas fail conservatively.

## Local observation and deployment expectations

2026-10-26 laptop run: Windows 11 AMD64, Python 3.14.0 x64; NVIDIA GeForce RTX 5060
Laptop GPU; driver 617.42; driver-reported CUDA 13.4; 7899 MiB free of 8151 MiB
reported total. Memory can change between runs. No inference was attempted.
**The RTX 4090 desktop has not been tested.** A laptop PASS cannot certify it.

On the desktop, first record this report alongside the interpreter and driver
versions. Verify the actual GPU name and current free memory; do not infer that
a model fits from its name or total VRAM alone. Export remains independent of GPU
ML support and continues to use its existing encoding policy.

Future, separately authorized steps: choose an isolated ML environment, verify
then-current framework/driver/runtime compatibility, record exact wheel and
runtime versions, and explicitly test PyTorch CUDA availability. Those tests may
initialize CUDA and are deliberately absent here. Follow with a bounded GPU tensor
operation and a small model inference only after model/setup approval; measure
memory and runtime before scaling to gameplay videos. Preserve CPU environments
and frozen results. No CUDA, driver, PyTorch or model installation is included
in this milestone; no claim of tested framework or desktop compatibility is made.
