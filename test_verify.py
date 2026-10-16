"""Mocked verification orchestration; no recursive test runs or real exports."""
import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import verify


class VerifyTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        self.redirect = contextlib.redirect_stdout(self.output)
        self.redirect.__enter__()
        self.addCleanup(self.redirect.__exit__, None, None, None)

    def test_commands(self):
        self.assertEqual(verify.test_commands(), [
            ("Unit tests", [sys.executable, "-m", "unittest", "discover", "-q"]),
            ("Motion checks (4)", [sys.executable, "test_motion.py"]),
        ])

    def test_default_runs_both_and_exit_codes(self):
        for codes in ([0, 0], [1, 0], [0, 1]):
            with patch.object(verify.subprocess, "run", side_effect=[
                subprocess.CompletedProcess([], code) for code in codes]) as run:
                self.assertEqual(verify.main([]), int(any(codes)))
                self.assertEqual(run.call_count, 2)
                for call in run.call_args_list:
                    self.assertEqual(call.kwargs, dict(cwd=verify.ROOT, check=False))

    def test_subprocess_start_failure(self):
        with patch.object(verify.subprocess, "run", side_effect=OSError("cannot start")):
            self.assertFalse(verify.run_check("fixture", ["missing"]))
        self.assertIn("FAIL: fixture", self.output.getvalue())

    def test_cli_rejects_incomplete_options(self):
        for args in (["--cached-export"], ["--cached-export", "--video", "x"],
                     ["--video", "x"], ["--analysis", "x"], ["--unknown"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                verify.main(args)
            self.assertEqual(error.exception.code, 2)

    def test_missing_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "Missing input"):
                verify.artifact_paths(Path(directory)/"absent", Path(directory)/"analysis")

    def test_missing_artifact_prevents_pipeline(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory)/"missing.mp4"
            with patch.object(verify, "artifact_paths", return_value=[missing]),                  patch.object(verify, "run_check") as run:
                self.assertFalse(verify.verify_cached_export(Path("video"), Path("analysis")))
            run.assert_not_called()

    def test_snapshots_hash_and_mtime(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"artifact"
            path.write_bytes(b"first")
            first = verify.snapshot([path])
            self.assertEqual(first, verify.snapshot([path]))
            path.write_bytes(b"other")
            os.utime(path, ns=(path.stat().st_atime_ns, first[path][1]))
            self.assertNotEqual(first, verify.snapshot([path]))
            second = verify.snapshot([path])
            os.utime(path, ns=(path.stat().st_atime_ns, second[path][1]+1000000000))
            self.assertNotEqual(second, verify.snapshot([path]))

    def test_cache_command_and_integrity_on_pipeline_failure(self):
        for success in (True, False):
            with patch.object(verify, "artifact_paths", return_value=[Path("artifact")]),                  patch.object(verify, "snapshot", return_value={Path("artifact"): ("hash", 123)}) as snap,                  patch.object(verify, "run_check", return_value=success) as run:
                self.assertEqual(verify.verify_cached_export(Path("video"), Path("analysis")), success)
                self.assertEqual(snap.call_count, 2)
                run.assert_called_once_with("Cached pipeline", [
                    sys.executable, "pipeline.py", "video", "--analysis", "analysis",
                    "--mode", "both", "--cache-only"])

    def test_modified_artifact_fails(self):
        path = Path("artifact")
        for after in ({path: ("changed", 1)}, {path: ("hash", 2)}):
            with patch.object(verify, "artifact_paths", return_value=[path]),                  patch.object(verify, "snapshot", side_effect=[{path: ("hash", 1)}, after]),                  patch.object(verify, "run_check", return_value=True):
                self.assertFalse(verify.verify_cached_export(Path("video"), Path("analysis")))

    def test_integration_independently_reported(self):
        with patch.object(verify, "run_check", side_effect=[False, True]) as run,              patch.object(verify, "verify_cached_export", return_value=False) as cache:
            self.assertEqual(verify.main(["--cached-export", "--video", "video", "--analysis", "analysis"]), 1)
            self.assertEqual(run.call_count, 2)
            cache.assert_called_once_with(Path("video").resolve(), Path("analysis").resolve())

    def test_paths_use_existing_planners(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video, analysis = root/"video", root/"analysis"
            video.touch()
            analysis.touch()
            with patch("export_shorts.plan_export", return_value=(video, root/"shorts",
                       {"clips": [{"output_filename": f"{i}.mp4"} for i in range(5)]})) as shorts,                  patch("export_longform.prepare_plan", return_value=(video, root/"longform",
                       {"assembly": {"output_path": str(root/"longform"/"longform_v1.mp4")}})):
                paths = verify.artifact_paths(video, analysis)
                self.assertEqual(len(paths), 9)
                self.assertIn(root/"shorts"/"0.mp4", paths)
                self.assertIn(root/"longform"/"longform_manifest.json", paths)
                shorts.assert_called_once_with(video, analysis, output_root=verify.ROOT/"output")


if __name__ == "__main__":
    unittest.main()
