"""Run existing GPU diagnostics with the current interpreter; no installation."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
TIMEOUT = 60
HARDWARE = ("NVIDIA hardware: DETECTED (visibility through nvidia-smi only)",
            "NVIDIA driver: AVAILABLE; version:")
DETECTION = ("DETECTED: selected CUDA device; GPU execution UNVERIFIED (check-only)",)
EXECUTION = ("PASS: tiny CUDA arithmetic, synchronization and CPU comparison",)


def run_stage(label, filename, arguments, markers):
    script = ROOT / filename
    print(f"--- {label} ---", flush=True)
    if not script.is_file():
        print(f"FAIL: {label}: missing script {script}")
        return False
    try:
        result = subprocess.run(
            [sys.executable, "-B", str(script), *arguments],
            capture_output=True, text=True, check=False, timeout=TIMEOUT)
        for output in (result.stdout, result.stderr):
            if output.strip():
                print(output.rstrip())
        lines = result.stdout.splitlines()
        confirmed = all(any(line.startswith(marker) for line in lines) for marker in markers)
        if result.returncode != 0 or not confirmed:
            print(f"FAIL: {label}: exit {result.returncode}; required positive evidence={confirmed}")
            return False
    except subprocess.TimeoutExpired:
        print(f"FAIL: {label}: timed out after {TIMEOUT} seconds")
        return False
    except (OSError, UnicodeError) as exc:
        print(f"FAIL: {label}: {exc}")
        return False
    print(f"PASS: {label}")
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-cuda", action="store_true",
                        help="explicitly run the existing tiny CUDA arithmetic check")
    args = parser.parse_args(argv)
    print(f"Interpreter: {sys.executable}")
    hardware = run_stage("GPU hardware/driver detection", "gpu_check.py", [], HARDWARE)
    detection = run_stage("PyTorch CUDA detection", "gpu_runtime_check.py",
                          ["--check-only"], DETECTION)
    passed = hardware and detection
    if args.execute_cuda:
        if passed:
            passed = run_stage("CUDA execution verification", "gpu_runtime_check.py", [], EXECUTION)
        else:
            print("SKIPPED: CUDA execution verification; detection prerequisites failed")
    else:
        print("CUDA execution: UNVERIFIED (use --execute-cuda to opt in)")
    print("Actual ML inference, model compatibility and performance: UNVERIFIED")
    scope = "requested deployment checks" if args.execute_cuda else "detection checks only"
    print(f"{'PASS' if passed else 'FAIL'}: {scope}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
