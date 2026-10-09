# Timestamped Speech Transcription V1

An optional English ASR stage writes the transcript into Shared Analysis V1.
Future Shorts and Long-form consumers load the same persisted document.

## Setup and use

From the repository root, use an isolated environment:
    
    python -m venv output/transcription_env
    output/transcription_env/Scripts/python.exe -m pip install -r requirements-transcription.txt
    output/transcription_env/Scripts/python.exe transcribe_video.py videos/my_recording.mp4 --analysis output/shared_analysis_v1.json

The pinned backend was verified on Windows Python 3.14: faster-whisper 1.2.1,
CTranslate2 4.8.2 and PyAV 16.1.0, with CPU/int8 support. PyAV 19 is incompatible with this backend and is intentionally excluded. The default model is small.en
(Systran/faster-whisper-small.en). First use downloads model files.

Use --create to create a missing analysis using actual FFprobe metadata and
SHA-256 source identity. Other signals remain explicitly not_analyzed.
Use --force to refresh only transcription. An analyzed transcript, including
an empty transcript from silence, is otherwise reused without model loading
or audio extraction. --device and --compute-type allow explicit overrides;
--word-timestamps requests optional backend word metadata.

## Interface and preservation

transcription.transcribe_media(path, ...) returns segments and provenance.
Segments retain model start/end/text exactly, including whitespace.
Optional metadata.words retains backend word timestamps and probabilities
when supplied; no confidence scores are invented. Nonfinite, unordered,
negative or out-of-duration timestamps are rejected, never silently clamped.

transcribe_video.update_transcript(...) loads and validates the existing
schema, verifies source identity, and atomically saves only the transcript
envelope. All visual, acoustic, language, semantic and candidate evidence
remains unchanged. Unsupported schema versions and mismatched source files
are rejected before inference. A persisted SHA-256 is preferred; legacy
documents without it require the same resolved source path and duration.
Such legacy metadata cannot establish historical content identity.

Provenance records model ID/revision, backend/CTranslate2 versions, requested
and actual language, device, compute type, decoding options, source hash and
duration, and extraction/model setup/inference/total processing times.

FFmpeg extracts a mono 16 kHz WAV in a unique temporary directory, following
the existing extractor's format. main.py is not imported because it executes
the production pipeline. Source audio is never overwritten; temporary WAVs
are cleaned up even on failure. Model cache and temporary directories live
beside the analysis document. Standalone calls default to repository output/.
Failures leave existing analysis bytes untouched.

This stage runs no CLIP/VLM, detector ranking, boundary, motion, retention,
ground-truth or language-scoring work. VAD is enabled to suppress nonspeech,
but ASR can still make mistakes; transcripts require human review.

