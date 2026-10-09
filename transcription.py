"""Optional English speech stage; standard-library imports until ASR is requested."""
from copy import deepcopy
from fractions import Fraction
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path
import subprocess
import tempfile
import time

MODEL_NAME = "small.en"
MODEL_ID = "Systran/faster-whisper-small.en"


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Timestamp must be finite and numeric")
    return value


def require_media(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Media file not found: {path}")
    return path


def media_sha256(path):
    with require_media(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def probe_media(path):
    """Actual source metadata for either audio or video; no inference."""
    path = require_media(path)
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams",
                            "-of", "json", str(path)], check=True, capture_output=True, text=True)
    data = json.loads(probe.stdout)
    duration = float(data["format"]["duration"])
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Media duration must be positive and finite")
    if not any(s["codec_type"] == "audio" for s in data["streams"]):
        raise ValueError("Media has no audio stream")
    source = dict(path=str(path), duration_seconds=duration, sha256=media_sha256(path))
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    if video:
        source.update(width=video["width"], height=video["height"])
        rate = Fraction(video.get("avg_frame_rate", "0/1"))
        if rate > 0:
            source["fps"] = float(rate)
    return source


def extract_audio(path, destination):
    """Same mono/16 kHz convention as main.py, with a caller-owned private path."""
    path, destination = require_media(path), Path(destination)
    if destination.exists() or path == destination.resolve():
        raise FileExistsError("Extraction must not overwrite an existing file")
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-n", "-i", str(path),
                    "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(destination)],
                   check=True, capture_output=True, text=True)


def validate_segments(segments, duration):
    """Preserve text, ordering, timestamps; reject rather than clamp or sort."""
    if _number(duration) <= 0:
        raise ValueError("Duration must be positive")
    previous = None
    for segment in segments:
        start, end = _number(segment["start"]), _number(segment["end"])
        if not 0 <= start <= end <= duration or not isinstance(segment["text"], str):
            raise ValueError("Invalid transcript segment or duration bounds")
        key = (start, end)
        if previous is not None and key < previous:
            raise ValueError("Transcript segments are not chronological")
        previous = key
        previous_word = None
        for word in segment.get("metadata", {}).get("words", []):
            a, b = _number(word["start"]), _number(word["end"])
            if not start <= a <= b <= end or not isinstance(word["word"], str):
                raise ValueError("Invalid word timestamps")
            if previous_word is not None and (a, b) < previous_word:
                raise ValueError("Words are not chronological")
            previous_word = (a, b)
            if "probability" in word and not 0 <= _number(word["probability"]) <= 1:
                raise ValueError("Invalid backend word probability")
    return deepcopy(segments)


def load_model(cache_dir, device, compute_type):
    """Lazy backend import and download; return exact backend/model provenance."""
    from faster_whisper import WhisperModel
    from faster_whisper.utils import download_model
    local = download_model(MODEL_NAME, cache_dir=str(cache_dir))
    model = WhisperModel(local, device=device, compute_type=compute_type, cpu_threads=4)
    return model, dict(backend="faster-whisper", backend_version=version("faster-whisper"),
                       ctranslate2_version=version("ctranslate2"), model=MODEL_NAME,
                       model_id=MODEL_ID, model_revision=Path(local).name)


def transcribe_media(path, *, device="cpu", compute_type="int8", word_timestamps=False,
                     cache_dir=None, work_dir=None):
    """Return {'segments': [...], 'provenance': {...}} for video or audio.

    Segments use start/end/text, with backend words preserved when supplied.
    English transcription, beam size 5, temperature 0, VAD enabled. No scores are
    manufactured. Generator consumption is included in inference/processing time.
    """
    started = time.perf_counter()
    path = require_media(path)
    source = probe_media(path)
    root = Path(__file__).resolve().parent / "output"
    cache_dir = Path(cache_dir) if cache_dir is not None else root / "transcription_models"
    work_dir = Path(work_dir) if work_dir is not None else root / "transcription_tmp"
    cache_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    options = dict(language="en", task="transcribe", beam_size=5, temperature=0,
                   vad_filter=True, word_timestamps=word_timestamps)
    with tempfile.TemporaryDirectory(prefix="asr_", dir=work_dir) as temporary:
        audio = Path(temporary) / "audio.wav"
        before = time.perf_counter()
        extract_audio(path, audio)
        extraction_seconds = time.perf_counter() - before
        before = time.perf_counter()
        try:
            model, backend = load_model(cache_dir, device, compute_type)
        except Exception as exc:
            raise RuntimeError(f"Could not initialize {MODEL_NAME}: {exc}") from exc
        setup_seconds = time.perf_counter() - before
        before = time.perf_counter()
        generated, info = model.transcribe(str(audio), **options)
        segments = []
        for segment in generated:
            row = dict(start=segment.start, end=segment.end, text=segment.text)
            words = getattr(segment, "words", None)
            if words is not None:
                row["metadata"] = dict(words=[
                    dict(start=w.start, end=w.end, word=w.word,
                         **({"probability": w.probability} if getattr(w, "probability", None) is not None else {}))
                    for w in words])
            segments.append(row)
        inference_seconds = time.perf_counter() - before
        segments = validate_segments(segments, source["duration_seconds"])
    provenance = dict(backend, language=info.language, requested_language="en",
        device=device, compute_type=compute_type, options=options,
        source_sha256=source["sha256"], source_duration_seconds=source["duration_seconds"],
        extraction_seconds=extraction_seconds, model_setup_seconds=setup_seconds,
        inference_seconds=inference_seconds, processing_seconds=time.perf_counter()-started)
    return dict(segments=segments, provenance=provenance)
