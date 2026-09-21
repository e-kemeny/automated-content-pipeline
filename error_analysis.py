"""Create human-review clips. Run with python error_analysis.py."""

from pathlib import Path
import subprocess


# Diagnostic groups only; these do not change the evaluator's ground truth.
DIAGNOSTIC_TIMESTAMPS = {
    "missed_gt": [24, 34, 52, 115, 152, 164, 206, 225],
    "prediction": [18, 40, 103, 122, 146, 170, 231],
}


def main():
    repo = Path(__file__).resolve().parent
    video_path = repo / "videos" / "my_recording.mp4"
    output_dir = repo / "output" / "error_analysis"
    if not video_path.is_file():
        raise SystemExit(f"Video not found: {video_path}")

    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        capture_output=True, text=True, check=True,
    )
    duration = float(result.stdout.strip())
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Video duration: {duration:.3f}s")
    print(f"Output directory: {output_dir}")

    created = 0
    for group, timestamps in DIAGNOSTIC_TIMESTAMPS.items():
        for timestamp in timestamps:
            start = max(0, timestamp - 5)
            end = min(duration, timestamp + 5)
            if end <= start:
                raise ValueError(f"No video available around {timestamp}s")
            output_path = output_dir / f"{group}_{timestamp:03d}.mp4"
            # Re-encode for accurate seeking instead of starting at a keyframe.
            subprocess.run(
                ["ffmpeg", "-v", "error", "-nostdin", "-y",
                 "-ss", str(start), "-i", str(video_path), "-t", str(end - start),
                 "-map", "0:v:0", "-map", "0:a:0?",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                 "-c:a", "aac", "-movflags", "+faststart", str(output_path)],
                check=True,
            )
            clamped = start != timestamp - 5 or end != timestamp + 5
            note = " (boundary clamped)" if clamped else ""
            print(f"Created {output_path.name}: {start:.3f}s to {end:.3f}s{note}")
            created += 1
    print(f"Successfully created {created} diagnostic clips.")


if __name__ == "__main__":
    main()
