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

            if all(abs(second - selected) >= 5 for selected in selected_seconds):
                selected_seconds.append(second)

                if len(selected_seconds) == 5:
                    break

        print("Selected Highlights: ", selected_seconds)

        for index, second in enumerate(selected_seconds, start = 1):  
            start_time = max(0, second - 10)
            end_time = second + 5

            cut_clip(
                video_path,
                start_time,
                end_time,
                index
            )
                    

    

analyze_audio(Path("output/audio.wav"))