"""Read-only prerequisite diagnostics; package metadata never loads ML modules."""
import argparse
from importlib import metadata
import platform
import shutil
import subprocess
import sys

TRANSCRIPTION = ("faster-whisper", "ctranslate2", "av", "onnxruntime", "huggingface-hub", "tokenizers")
LANGUAGE = ("torch", "transformers")
PACKAGES = tuple(dict.fromkeys(TRANSCRIPTION + LANGUAGE + ("Pillow", "torchvision", "num2words", "matplotlib")))
PROFILES = {"export": (), "transcription": TRANSCRIPTION, "language": LANGUAGE}


def executable_status(name):
    path = shutil.which(name)
    if path is None:
        return "MISSING", "add executable to PATH"
    try:
        result = subprocess.run([path, "-version"], capture_output=True, text=True,
                                check=True, timeout=10)
        line = result.stdout.splitlines()[0] if result.stdout.strip() else ""
        if not line:
            return "UNKNOWN/UNVERIFIED", f"{path}: empty version response"
        return "AVAILABLE", f"{line} [{path}]"
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        return "UNKNOWN/UNVERIFIED", f"{path}: version check failed ({type(exc).__name__})"


def package_status(name):
    try:
        version = metadata.version(name)
        if not version:
            return "UNKNOWN/UNVERIFIED", "empty distribution version"
        return "AVAILABLE", version + " (distribution metadata only)"
    except metadata.PackageNotFoundError:
        return "MISSING", "not installed in this interpreter"
    except Exception as exc:
        return "UNKNOWN/UNVERIFIED", f"metadata unavailable ({type(exc).__name__})"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=tuple(PROFILES), default="export")
    args = parser.parse_args(argv)
    print(f"Profile: {args.profile}")
    print(f"Python: {platform.python_version()} | {sys.executable}")
    print(f"Platform: {platform.system()} {platform.release()} | {platform.machine()} | {64 if sys.maxsize > 2**32 else 32}-bit interpreter")
    supported = sys.version_info >= (3, 11)
    print(f"{'AVAILABLE' if supported else 'MISSING'}: Python >=3.11 required by hashlib.file_digest; only recorded Python 3.14 environment tested")
    missing = not supported
    for name in ("ffmpeg", "ffprobe"):
        status, detail = executable_status(name)
        essential = args.profile != "language"
        print(f"{status}: {name} [{'essential' if essential else 'optional'}] - {detail}")
        missing |= essential and status == "MISSING"
    for name in PACKAGES:
        essential = name in PROFILES[args.profile]
        status, detail = package_status(name)
        print(f"{status}: {name} [{'essential' if essential else 'optional'}] - {detail}")
        missing |= essential and status == "MISSING"
    print("UNKNOWN/UNVERIFIED: model loading, pinned-version compatibility, codecs, CUDA/drivers and GPU support; no inference or GPU initialization performed.")
    print("Result: " + ("missing essential prerequisites" if missing else "no known missing essentials; runtime compatibility is unverified"))
    return int(missing)


if __name__ == "__main__":
    raise SystemExit(main())
