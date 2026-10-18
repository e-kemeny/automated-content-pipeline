"""Shared FFprobe format/stream JSON transport; caller validation stays local."""
import json
import subprocess


def probe_format_streams(path):
    """Return decoded metadata; preserve subprocess/JSON errors without wrapping."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(result.stdout)
