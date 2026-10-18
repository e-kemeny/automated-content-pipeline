"""Exact FFprobe transport and compatibility checks; no media tools required."""
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import media_probe
import transcription
import export_shorts


class MediaProbeTests(unittest.TestCase):
    def test_valid_metadata_and_exact_command(self):
        data = {"format": {"duration": "2"}, "streams": []}
        path = Path("folder")/"clip.mp4"
        with patch("media_probe.subprocess.run", return_value=SimpleNamespace(stdout=json.dumps(data))) as run:
            self.assertEqual(media_probe.probe_format_streams(path), data)
        run.assert_called_once_with(
            ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
            check=True, capture_output=True, text=True)

    def test_malformed_json(self):
        with patch("media_probe.subprocess.run", return_value=SimpleNamespace(stdout="{")):
            with self.assertRaises(json.JSONDecodeError):
                media_probe.probe_format_streams("clip")

    def test_subprocess_errors_propagate_unchanged(self):
        # No timeout is configured; if the transport raises one, it is not wrapped.
        for error in (subprocess.CalledProcessError(1, ["ffprobe"], stderr="bad"),
                      subprocess.TimeoutExpired(["ffprobe"], 2), FileNotFoundError("ffprobe")):
            with self.subTest(error=error), patch("media_probe.subprocess.run", side_effect=error):
                with self.assertRaises(type(error)) as raised:
                    media_probe.probe_format_streams("clip")
                self.assertIs(raised.exception, error)

    def test_missing_streams_and_invalid_duration_remain_caller_concerns(self):
        for data in ({"format": {"duration": "2"}}, {"streams": [], "format": {"duration": "nan"}}):
            with patch("media_probe.subprocess.run", return_value=SimpleNamespace(stdout=json.dumps(data))):
                self.assertEqual(media_probe.probe_format_streams("clip"), data)
        with patch("media_probe.subprocess.run", return_value=SimpleNamespace(stdout='{"format":{"duration":"2"}}')):
            with self.assertRaises(KeyError):
                export_shorts.probe_clip("clip")

    def test_caller_validation_and_return_compatibility(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"source.mp4"
            path.write_bytes(b"fixture")
            data = {"format": {"duration": "2"}, "streams": [
                {"codec_type": "video", "width": 160, "height": 90, "avg_frame_rate": "30/1"},
                {"codec_type": "audio"}]}
            with patch("media_probe.subprocess.run", return_value=SimpleNamespace(stdout=json.dumps(data))) as run:
                source = transcription.probe_media(path)
                clip = export_shorts.probe_clip(path)
            self.assertEqual(run.call_args_list[0], run.call_args_list[1])
            self.assertEqual(source, dict(path=str(path.resolve()), duration_seconds=2,
                sha256=transcription.media_sha256(path), width=160, height=90, fps=30))
            self.assertEqual(clip, dict(duration_seconds=2, streams=[
                {"codec_type": "video", "avg_frame_rate": "30/1"}, {"codec_type": "audio"}]))
            for value in ("0", "-1", "nan", "inf"):
                data["format"]["duration"] = value
                with patch("media_probe.subprocess.run", return_value=SimpleNamespace(stdout=json.dumps(data))):
                    with self.assertRaisesRegex(ValueError, "^Media duration must be positive and finite$"):
                        transcription.probe_media(path)
                    with self.assertRaisesRegex(ValueError, "^Export lacks valid audio/video streams or duration$"):
                        export_shorts.probe_clip(path)

    def test_stream_requirements_stay_different(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"audio.wav"
            path.write_bytes(b"fixture")
            for streams in ([], [{"codec_type": "audio"}]):
                data = dict(format=dict(duration="2"), streams=streams)
                with patch("media_probe.subprocess.run", return_value=SimpleNamespace(stdout=json.dumps(data))):
                    if streams:
                        self.assertNotIn("width", transcription.probe_media(path))
                    else:
                        with self.assertRaisesRegex(ValueError, "^Media has no audio stream$"):
                            transcription.probe_media(path)
                    with self.assertRaisesRegex(ValueError, "^Export lacks valid audio/video streams or duration$"):
                        export_shorts.probe_clip(path)


if __name__ == "__main__":
    unittest.main()
