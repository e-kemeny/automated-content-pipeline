"""Experimental image-change signal: 5 fps, 160x90 grayscale frames."""

import subprocess

FPS = 5
WIDTH = 160
HEIGHT = 90


def frame_change(previous, current):
    # Iterating bytes yields Python integers, so subtraction cannot wrap around.
    if not current or len(previous) != len(current):
        raise ValueError("Frame sizes must be equal and nonzero")
    return sum(abs(now - before) for before, now in zip(previous, current)) / (len(current) * 255)


def iter_grayscale_frames(video_path):
    command = [
        "ffmpeg", "-v", "error", "-nostdin", "-i", str(video_path),
        "-map", "0:v:0", "-an",
        "-vf", f"setpts=PTS-STARTPTS,fps={FPS}:start_time=0,scale={WIDTH}:{HEIGHT},format=gray",
        "-pix_fmt", "gray", "-f", "rawvideo", "pipe:1",
    ]
    frame_size = WIDTH * HEIGHT
    # Stream frames to bound memory; FFmpeg errors go directly to stderr.
    with subprocess.Popen(command, stdout=subprocess.PIPE) as process:
        try:
            while True:
                frame = process.stdout.read(frame_size)
                if not frame:
                    break
                if len(frame) != frame_size:
                    raise ValueError("FFmpeg returned an incomplete grayscale frame")
                yield frame
            if process.wait() != 0:
                raise subprocess.CalledProcessError(process.returncode, command)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()


def score_motion_frames(frames):
    """Average changes by the later frame's second, then max-normalize.

    Frame i represents i / 5 seconds relative to video start. The first frame
    has no predecessor and contributes no difference. A second with no pairs
    has score zero; a partial final second averages only its available pairs.
    """
    totals = {}
    counts = {}
    previous = None
    for index, current in enumerate(frames):
        second = index // FPS
        totals.setdefault(second, 0.0)
        counts.setdefault(second, 0)
        if previous is not None:
            totals[second] += frame_change(previous, current)
            counts[second] += 1
        previous = current

    scores = [
        {"second": second, "score": total / counts[second] if counts[second] else 0.0}
        for second, total in totals.items()
    ]
    maximum = max((item["score"] for item in scores), default=0.0)
    for item in scores:
        item["normalized_score"] = item["score"] / maximum if maximum else 0.0
    return scores


def analyze_motion(video_path):
    return score_motion_frames(iter_grayscale_frames(video_path))


def add_motion_scores(audio_scores, motion_scores):
    """Add evaluation-only scores without changing audio or scene scores."""
    for item in audio_scores:
        item["motion_score"] = max(
            (motion["normalized_score"] for motion in motion_scores
             if abs(item["second"] - motion["second"]) <= 5),
            default=0.0,
        )
        item["motion_highlight_score"] = (
            0.7 * item["normalized_score"] + 0.3 * item["motion_score"]
        )
