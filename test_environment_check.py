"""Metadata-only diagnostics with mocked discovery and subprocesses."""
import contextlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import environment_check as check


class EnvironmentCheckTests(unittest.TestCase):
    def test_executable_command(self):
        with patch.object(check.shutil, "which", return_value="tools/ffmpeg") as which,              patch.object(check.subprocess, "run", return_value=SimpleNamespace(stdout="ffmpeg version fixture")) as run:
            self.assertEqual(check.executable_status("ffmpeg")[0], "AVAILABLE")
        which.assert_called_once_with("ffmpeg")
        run.assert_called_once_with(["tools/ffmpeg", "-version"], capture_output=True,
                                    text=True, check=True, timeout=10)

    def test_missing_executable(self):
        with patch.object(check.shutil, "which", return_value=None), patch.object(check.subprocess, "run") as run:
            self.assertEqual(check.executable_status("ffprobe")[0], "MISSING")
        run.assert_not_called()

    def test_version_failures_unknown(self):
        for error in (OSError("failure"), subprocess.CalledProcessError(1, []),
                      subprocess.TimeoutExpired([], 10)):
            with patch.object(check.shutil, "which", return_value="tool"),                  patch.object(check.subprocess, "run", side_effect=error):
                self.assertEqual(check.executable_status("ffmpeg")[0], "UNKNOWN/UNVERIFIED")
        with patch.object(check.shutil, "which", return_value="tool"),              patch.object(check.subprocess, "run", return_value=SimpleNamespace(stdout="")):
            self.assertEqual(check.executable_status("ffmpeg")[0], "UNKNOWN/UNVERIFIED")

    def test_package_metadata(self):
        with patch.object(check.metadata, "version", return_value="1.2"):
            self.assertEqual(check.package_status("torch"), ("AVAILABLE", "1.2 (distribution metadata only)"))
        with patch.object(check.metadata, "version", side_effect=check.metadata.PackageNotFoundError):
            self.assertEqual(check.package_status("torch")[0], "MISSING")
        with patch.object(check.metadata, "version", side_effect=ValueError("broken metadata")):
            self.assertEqual(check.package_status("torch")[0], "UNKNOWN/UNVERIFIED")

    def run_profile(self, profile, missing=(), tool_status="AVAILABLE"):
        output = io.StringIO()
        with patch.object(check, "executable_status", return_value=(tool_status, "fixture")),              patch.object(check, "package_status", side_effect=lambda name:
                          ("MISSING" if name in missing else "AVAILABLE", "fixture")),              contextlib.redirect_stdout(output):
            code = check.main(["--profile", profile])
        return code, output.getvalue()

    def test_profiles_optional_and_essential(self):
        self.assertEqual(self.run_profile("export", check.PACKAGES)[0], 0)
        for profile in ("transcription", "language"):
            self.assertEqual(self.run_profile(profile)[0], 0)
            for package in check.PROFILES[profile]:
                self.assertEqual(self.run_profile(profile, [package])[0], 1)
        self.assertEqual(self.run_profile("language", ["faster-whisper"])[0], 0)

    def test_tools_and_unknown_exit_codes(self):
        for profile in check.PROFILES:
            self.assertEqual(self.run_profile(profile, tool_status="MISSING")[0], int(profile != "language"))
            self.assertEqual(self.run_profile(profile, tool_status="UNKNOWN/UNVERIFIED")[0], 0)

    def test_report_and_invalid_profile(self):
        code, output = self.run_profile("export")
        self.assertIn("runtime compatibility is unverified", output)
        self.assertIn("Python:", output)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            check.main(["--profile", "invalid"])
        self.assertEqual(error.exception.code, 2)

    def test_isolated_no_heavy_imports_or_writes(self):
        script = r"""
import sys
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
def audit(event,args):
    if event in ("os.mkdir","os.remove","os.rename","subprocess.Popen"):
        raise AssertionError(event)
    if event=="open" and (args[2] & (1|2|64|512|1024)):
        raise AssertionError("write")
sys.addaudithook(audit)
import environment_check as c
with patch.object(c.shutil,"which",return_value=None):
    assert c.main([])==1
assert not any(n in sys.modules for n in ("torch","transformers","faster_whisper","ctranslate2","onnxruntime"))
"""
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, "-B", "-c", script, str(Path(__file__).resolve().parent)],
                                    cwd=directory, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
