from pathlib import Path
from array import array
import subprocess
import json
import wave

video_path = Path("videos/my_recording.mp4")

if video_path.exists():
    print("Video Found: ", video_path)
else:
    raise SystemExit("Error: video not found")


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

def cut_clip(video_path, start_time, end_time, clip_number):
    if end_time <= start_time:
        print("Error: end_time must be greater than start_time")
        return
    duration = end_time - start_time

    output_path = Path(f"output/clip_{clip_number}.mp4")

    command = ["ffmpeg",
               "-y",
               "-ss",
               str(start_time),
               "-i", str(video_path),
               "-t", str(duration),
               "-c", "copy",
               str(output_path)
    ]

    result = subprocess.run(
        command,
        capture_output = True,
        text = True
    )

    if result.returncode == 0:
        print("Clip created: ", output_path)
    else:
        print("Error creating clip")


highlights = [
    {"start_time": 10,
    "end_time": 20},
    {"start_time": 45,
    "end_time": 60},
    {"start_time": 100,
    "end_time": 115}
]


for index, highlight in enumerate(highlights, start = 1):
    cut_clip(
        video_path,
        highlight["start_time"],
        highlight["end_time"],
        index
    )

def extract_audio(video_path):
    output_path = Path("output/audio.wav")
    command = [
        "ffmpeg",
        "-y",
        "-i", str(video_path),
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        str(output_path)
    ]

    result = subprocess.run(
        command,
        capture_output = True,
        text = True
    )

    if result.returncode == 0:
        print("Audio extracted:", output_path)
    else:
        print("Error extracting audio")

extract_audio(video_path)

def analyze_audio(audio_path):
    with wave.open(str(audio_path), "rb") as audio:
        channels = audio.getnchannels()
        sample_rate = audio.getframerate()
        num_frames = audio.getnframes()

        audio_data = audio.readframes(num_frames)
        samples = array("h", audio_data)

        volumes = []
        for start in range(0, len(samples), sample_rate):
            end = start + sample_rate
            chunk = samples[start:end]
            second = start // sample_rate
            average_volume = sum(abs(sample) for sample in chunk) / len(chunk)
            volumes.append({
                "second": second,
                "volume": average_volume
            })

        sorted_volumes = sorted(
            volumes,
            key = lambda item: item["volume"],
            reverse = True
        )

        selected_seconds = []

        for item in sorted_volumes:
            second = item["second"]

            if second >= selected_seconds[]

        print(sorted_volumes[:5])
    
analyze_audio(Path("output/audio.wav"))