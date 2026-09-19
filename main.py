from pathlib import Path
from array import array
import subprocess
import json
import wave

from evaluation import GROUND_TRUTH, select_highlights, evaluate_predictions, print_evaluation

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

def analyze_video_motion(video_path):
    command = [
        "ffmpeg",
        "-y",
        "-i", str(video_path),
        "-vf", "scdet=t=10",
        "-f", "null",
        "-"
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    # scene_changes = []
    # for line in result.stderr.splitlines():
    #     if "pts_time" in line:
    #         parts = line.split("pts_time:")
    #         after_pts_time = parts[1]
    #         timestamp_parts = after_pts_time.split()
    #         timestamp = float(timestamp_parts[0])
    #         scene_changes.append(timestamp)
    #         print(timestamp)

    scene_changes = []
    for line in result.stderr.splitlines():
        if "lavfi.scd.score" in line:
            parts = line.split("lavfi.scd.score:")
            score_parts = parts[1].split(",")
            score = float(score_parts[0])
            time_parts = score_parts[1].split("lavfi.scd.time:")
            timestamp = float(time_parts[1])
            scene_changes.append({
                "time": timestamp,
                "score": score
            })

    sorted_scene_changes = sorted(
        scene_changes,
        key=lambda item: item["score"],
        reverse=True
    )

    print(sorted_scene_changes[:5])
    return sorted_scene_changes

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

        spikes = []
        for i in range(5, len(volumes)):
            current_volume = volumes[i]["volume"]
            last_five_volumes = volumes[i - 5:i]

            sum_last_five_volumes = sum(item["volume"] for item in last_five_volumes)
            average_last_five_volumes = sum_last_five_volumes / len(last_five_volumes)
            spike = current_volume - average_last_five_volumes

            second = volumes[i]["second"]


            score = current_volume + spike

            spikes.append({
                "second": second,
                "spike": spike,
                "score": score
            })

        sorted_scores = sorted(
            spikes,
            key = lambda item: item["score"],
            reverse = True
        )

        print("Top combined scores: ", sorted_scores[:5])
        return sorted_scores

audio_scores = analyze_audio(Path("output/audio.wav"))
scene_scores = analyze_video_motion(video_path)
print(audio_scores[:2])
print(scene_scores[:2])

max_audio_score = audio_scores[0]["score"]
max_scene_score = scene_scores[0]["score"]

for item in audio_scores:
    item["normalized_score"] = item["score"] / max_audio_score

for item in scene_scores:
    item["normalized_score"] = item["score"] / max_scene_score

for audio_item in audio_scores:
    audio_second = audio_item["second"]
    best_scene_score = 0

    for scene_item in scene_scores:
        scene_second = scene_item["time"]

        if abs(audio_second - scene_second) <= 5:
            best_scene_score = max(
                best_scene_score,
                scene_item["normalized_score"]
            )

    audio_item["scene_score"] = best_scene_score

for audio_item in audio_scores:
    audio_item["highlight_score"] = (
        0.7 * audio_item["normalized_score"]
        + 0.3 * audio_item["scene_score"]
    )

audio_highlights = select_highlights(audio_scores, "score")
selected_highlights = select_highlights(audio_scores, "highlight_score")

for name, highlights in [("AUDIO-ONLY", audio_highlights), ("MULTIMODAL", selected_highlights)]:
    predictions = [item["second"] for item in highlights]
    print_evaluation(name, evaluate_predictions(predictions, GROUND_TRUTH))

# Ranking diagnostics only; clip generation still uses the top five above.
for name, score_key in [("AUDIO-ONLY", "score"), ("MULTIMODAL", "highlight_score")]:
    top_ten = select_highlights(audio_scores, score_key, limit=10)
    predictions = [item["second"] for item in top_ten]
    print_evaluation(
        f"{name} TOP 10",
        evaluate_predictions(predictions, GROUND_TRUTH),
        show_diagnostics=True,
    )

print("Selected highlights:")
for index, item in enumerate(selected_highlights, start=1):
    second = item["second"]
    print(f"  {index}. {second}s | highlight score: {item['highlight_score']:.6f}")
    start_time = max(0, second - 10)
    end_time = min(duration_seconds, second + 5)
    cut_clip(video_path, start_time, end_time, index)
