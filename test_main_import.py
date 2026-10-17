"""Import safety and controlled direct-execution regression checks."""
import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave
from array import array

ROOT = Path(__file__).resolve().parent


def execute_fixture(source):
    """Run script text with real fixture WAV input and mocked external processing."""
    import motion
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root/"videos").mkdir()
        (root/"output").mkdir()
        (root/"videos/my_recording.mp4").write_bytes(b"fixture")
        with wave.open(str(root/"output/audio.wav"), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(1)
            audio.writeframes(array("h", [100 + (i % 17)*50 for i in range(100)]).tobytes())
        commands = []
        def external(command, **kwargs):
            commands.append((command, kwargs))
            if command[0] == "ffprobe":
                return subprocess.CompletedProcess(command, 0, '{"format":{"duration":"100"}}', "")
            return subprocess.CompletedProcess(command, 0, "", "lavfi.scd.score: 8, lavfi.scd.time: 40")
        output = io.StringIO()
        namespace = {"__name__": "__main__"}
        previous = Path.cwd()
        try:
            os.chdir(root)
            with patch("subprocess.run", side_effect=external),                  patch.object(motion, "analyze_motion", return_value=[dict(second=40, score=1, normalized_score=1)]),                  contextlib.redirect_stdout(output):
                try:
                    exec(compile(source, "main.py", "exec"), namespace)
                    code = None
                except SystemExit as exc:
                    code = exc.code
        finally:
            os.chdir(previous)
        return code, output.getvalue(), commands


class MainImportTests(unittest.TestCase):
    def test_import_isolated_without_side_effects(self):
        script = r"""
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
def audit(event, args):
    if event in ("subprocess.Popen", "os.mkdir", "os.remove", "os.rename"):
        raise AssertionError(event)
    if event == "open":
        mode, flags = args[1], args[2]
        if (isinstance(mode, str) and any(c in mode for c in "wax+")) or flags &  (1 | 2 | 64 | 512 | 1024):
            raise AssertionError("file write")
sys.addaudithook(audit)
with patch.object(Path, "exists", side_effect=AssertionError("filesystem probe")),      patch("subprocess.run", side_effect=AssertionError("subprocess")),      patch("wave.open", side_effect=AssertionError("audio processing")):
    import main
for name in ("get_video_duration", "cut_clip", "extract_audio", "analyze_video_motion", "analyze_audio", "run_pipeline", "main"):
    assert callable(getattr(main, name)), name
assert "audio_scores" not in vars(main)
"""
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, "-B", "-c", script, str(ROOT)],
                                    cwd=directory, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_direct_execution_fixture(self):
        code, output, commands = execute_fixture((ROOT/"main.py").read_text())
        self.assertIsNone(code)
        self.assertIn("Selected highlights:", output)
        self.assertIn("AUDIO + MOTION TOP 10", output)
        self.assertEqual(commands[0][0][0], "ffprobe")
        self.assertEqual(commands[1][0], ["ffmpeg", "-y", "-i", str(Path("videos/my_recording.mp4")),
            "-vn", "-ac", "1", "-ar", "16000", str(Path("output/audio.wav"))])
        self.assertEqual(commands[2][0], ["ffmpeg", "-y", "-i", str(Path("videos/my_recording.mp4")),
            "-vf", "scdet=t=10", "-f", "null", "-"])
        cuts = [cmd for cmd, _ in commands if "copy" in cmd]
        self.assertEqual(len(cuts), 5)

    def test_missing_source_preserves_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, "-B", str(ROOT/"main.py")],
                                    cwd=directory, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr.strip(), "Error: video not found")


if __name__ == "__main__":
    unittest.main()
