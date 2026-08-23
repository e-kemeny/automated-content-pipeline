from pathlib import Path
import subprocess
import json

video_path = Path("videos/my_recording.mp4")

if video_path.exists():
    print("Video Found: ", video_path)
else:
    print("Error: video not found")


def get_video_duration(video_path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(video_path)
        ],
        capture_output = True,
        text = True
    )

    metadata = json.loads(result.stdout)

    if "format" in metadata and "duration" in metadata["format"]:
        duration_seconds = float(metadata["format"]["duration"])
        return duration_seconds
    
    return None

duration_seconds = get_video_duration(video_path)

if duration_seconds is not None:
    duration_minutes = duration_seconds // 60
    leftover_seconds = duration_seconds % 60

    print(f"Duration: {int(duration_minutes)}:{int(leftover_seconds):02d}")
else:
    print("No duration found.")

def cut_clip(video_path, start_time, end_time):
    if end_time <= start_time:
        print("Error: end_time must be greater than start_time")
        return
    duration = end_time - start_time

    output_path = Path("output/clip.mp4")

    command = ["ffmpeg",
               "-y",
               "-ss",
               str(start_time),
               "-i", str(video_path),
               "-t", str(duration),
               "-c", "copy",
               str(output_path)
    ]

    subprocess.run(command)

cut_clip(video_path, 10, 20)