"""Optional PyTorch CUDA detection and tiny arithmetic verification; no models."""
import argparse
import importlib
import platform
import re
import sys


def cuda_device(value):
    if not re.fullmatch(r"cuda:[0-9]+", value):
        raise argparse.ArgumentTypeError("device must be cuda:<nonnegative index>")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true",
                        help="query runtime/devices without allocating CUDA tensors")
    parser.add_argument("--device", type=cuda_device, default="cuda:0")
    args = parser.parse_args(argv)
    print(f"Python: {platform.python_version()} | {sys.executable}")
    print("Actual GPU inference: UNVERIFIED (no models are run)")
    print("GPU execution: UNVERIFIED until the arithmetic check passes")
    try:
        torch = importlib.import_module("torch")
    except ModuleNotFoundError as exc:
        if exc.name == "torch":
            print("UNAVAILABLE: PyTorch is not installed in this interpreter")
            return 1
        print(f"ERROR: PyTorch dependency import failed: {exc}")
        return 3
    except Exception as exc:
        print(f"ERROR: PyTorch import failed: {exc}")
        return 3

    stage = "runtime/device detection"
    try:
        print(f"PyTorch: {torch.__version__}")
        print(f"torch.version.cuda: {torch.version.cuda} (build version, not compatibility proof)")
        available = torch.cuda.is_available()
        print(f"torch.cuda.is_available(): {available}")
        if torch.version.cuda is None or not available:
            print("UNAVAILABLE: CPU-only PyTorch or CUDA unavailable; no CPU fallback")
            return 1
        count = torch.cuda.device_count()
        print(f"Detected CUDA devices: {count}")
        for index in range(count):
            print(f"cuda:{index}: {torch.cuda.get_device_name(index)}")
        index = int(args.device.split(":")[1])
        if index >= count:
            print(f"INVALID DEVICE: {args.device}; available indices: 0..{count - 1}")
            return 2
        device = f"cuda:{index}"
        print(f"Selected device: {device}")
        if args.check_only:
            print("DETECTED: selected CUDA device; GPU execution UNVERIFIED (check-only)")
            return 0

        # Small exact integers avoid tolerance decisions; expected values use Python.
        left, right = [1, -2, 3, 0], [4, 5, -6, 7]
        expected = [a + b for a, b in zip(left, right)]
        stage = "tensor allocation/arithmetic"
        a = torch.tensor(left, dtype=torch.int64, device=device)
        b = torch.tensor(right, dtype=torch.int64, device=device)
        result = a + b
        if any(str(tensor.device) != device for tensor in (a, b, result)):
            raise RuntimeError("tensor was not on the requested CUDA device")
        stage = "CUDA synchronization"
        torch.cuda.synchronize(device)
        stage = "CPU transfer/comparison"
        actual = result.cpu().tolist()
        if actual != expected:
            raise RuntimeError(f"arithmetic mismatch: expected {expected}, received {actual}")
        print("PASS: tiny CUDA arithmetic, synchronization and CPU comparison")
        return 0
    except Exception as exc:
        print(f"ERROR: {stage} failed ({type(exc).__name__}): {exc}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
