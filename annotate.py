"""Human interval annotations only. Launch with python annotate.py."""

import json
import math
from pathlib import Path
import subprocess

ALLOWED_TYPES = ("intro", "transition", "combat", "objective", "victory", "other")
REPO = Path(__file__).resolve().parent


def validate_annotation(start, end, kind, description, duration):
    start, end = float(start), float(end)
    if not math.isfinite(start) or not math.isfinite(end):
        raise ValueError("Timestamps must be finite numbers.")
    if start < 0:
        raise ValueError("Start must be at least zero.")
    if end <= start:
        raise ValueError("End must be greater than start.")
    if end > duration:
        raise ValueError(f"End must not exceed the video duration ({duration}s).")
    if kind not in ALLOWED_TYPES:
        raise ValueError("Type must be one of: " + ", ".join(ALLOWED_TYPES))
    if not isinstance(description, str):
        raise ValueError("Description must be text.")
    return {"start": start, "end": end, "type": kind, "description": description}


def load_annotations(path, duration):
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Annotation JSON must contain a list.")
    annotations = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("Each annotation must be an object.")
        annotations.append(validate_annotation(
            item["start"], item["end"], item["type"], item["description"], duration
        ))
    return sorted(annotations, key=lambda item: (item["start"], item["end"]))


def save_annotations(path, annotations):
    ordered = sorted(annotations, key=lambda item: (item["start"], item["end"]))
    text = json.dumps(ordered, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    path.write_text(text, encoding="utf-8")


def delete_annotation(annotations, index):
    """Return a new list without the one-based displayed index."""
    if not 1 <= index <= len(annotations):
        raise ValueError("Index must be one of the displayed annotation numbers.")
    return annotations[:index - 1] + annotations[index:]


def list_annotations(annotations):
    if not annotations:
        print("No annotations yet.")
    for index, item in enumerate(annotations, start=1):
        print(f"{index}. {item['start']}s - {item['end']}s | "
              f"{item['type']} | {item['description']}")


def main():
    video_path = REPO / "videos" / "my_recording.mp4"
    annotation_path = REPO / "ground_truth_v2.json"
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
            capture_output=True, text=True, check=True,
        )
        duration = float(result.stdout.strip())
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("Video duration must be positive and finite.")
        annotations = load_annotations(annotation_path, duration)
    except subprocess.CalledProcessError as error:
        raise SystemExit(f"Could not probe video: {error.stderr.strip()}")
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit(f"Could not open annotation session: {error}")

    print(f"Video duration: {duration}s")
    print(f"Annotations: {annotation_path}")
    print("Enter times in seconds (decimals allowed). Changes save immediately.")
    while True:
        try:
            command = input("[a]dd, [l]ist, [d]elete, [q]uit: ").strip().lower()
            if command in ("q", "quit"):
                break
            if command in ("l", "list"):
                list_annotations(annotations)
                continue
            if command in ("a", "add"):
                start = input("Start time (seconds): ").strip()
                end = input("End time (seconds): ").strip()
                kind = input("Type (" + ", ".join(ALLOWED_TYPES) + "): ").strip().lower()
                description = input("Short description: ").strip()
                annotation = validate_annotation(start, end, kind, description, duration)
                updated = sorted(annotations + [annotation], key=lambda item: (item["start"], item["end"]))
            elif command in ("d", "delete"):
                list_annotations(annotations)
                if not annotations:
                    continue
                index = int(input("Index to delete: "))
                updated = delete_annotation(annotations, index)
            else:
                print("Choose add, list, delete, or quit.")
                continue
            save_annotations(annotation_path, updated)
            annotations = updated
            print("Saved.")
        except (ValueError, OSError) as error:
            print(f"Not saved: {error}")
        except (EOFError, KeyboardInterrupt):
            print("\nLeaving annotation session.")
            break


if __name__ == "__main__":
    main()
