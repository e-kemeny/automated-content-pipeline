"""Deployment orchestration tests never invoke real diagnostics or PyTorch."""
import contextlib
import io
import subprocess
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import deployment_check as check


def response(text, code=0):
    return SimpleNamespace(stdout=text, stderr="", returncode=code)


def success():
    return [response("\n".join(check.HARDWARE)), response(check.DETECTION[0]),
            response(check.EXECUTION[0])]


class DeploymentTests(unittest.TestCase):
    def invoke(self, args=(), responses=None, exists=True):
        with (patch.object(check.Path, "is_file", return_value=exists),
              patch.object(check.subprocess, "run", side_effect=responses or success()) as run,
              contextlib.redirect_stdout(io.StringIO()) as output):
            code = check.main(list(args))
        return code, output.getvalue(), run

    def test_detection_and_no_execution(self):
        code, output, run = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(run.call_count, 2)
        self.assertIn("CUDA execution: UNVERIFIED", output)
        self.assertIn("PASS: detection checks only", output)
        self.assertIn("performance: UNVERIFIED", output)

    def test_optional_execution(self):
        code, output, run = self.invoke(["--execute-cuda"])
        self.assertEqual(code, 0)
        self.assertEqual(run.call_count, 3)
        self.assertIn("PASS: CUDA execution verification", output)

    def test_current_interpreter_and_absolute_scripts(self):
        _, _, run = self.invoke(["--execute-cuda"])
        commands = [c.args[0] for c in run.call_args_list]
        self.assertEqual(commands, [
            [check.sys.executable, "-B", str(check.ROOT/"gpu_check.py")],
            [check.sys.executable, "-B", str(check.ROOT/"gpu_runtime_check.py"), "--check-only"],
            [check.sys.executable, "-B", str(check.ROOT/"gpu_runtime_check.py")]])
        for invocation in run.call_args_list:
            self.assertEqual(invocation.kwargs,
                             dict(capture_output=True, text=True, check=False, timeout=60))

    def test_missing_scripts(self):
        code, output, run = self.invoke(["--execute-cuda"], exists=False)
        self.assertEqual(code, 1)
        run.assert_not_called()
        self.assertIn("missing script", output)
        self.assertIn("SKIPPED", output)

    def test_nonzero_despite_positive_output(self):
        items = success()
        items[0].returncode = 1
        code, output, run = self.invoke(["--execute-cuda"], items)
        self.assertEqual(code, 1)
        self.assertEqual(run.call_count, 2)
        self.assertNotIn("PASS: requested deployment checks", output)

    def test_missing_torch_or_cuda(self):
        for message in ("PyTorch is not installed", "CUDA unavailable"):
            items = success()
            items[1] = response(message, 1)
            code, output, run = self.invoke(["--execute-cuda"], items)
            self.assertEqual(code, 1)
            self.assertIn(message, output)
            self.assertEqual(run.call_count, 2)

    def test_timeout(self):
        code, output, run = self.invoke(responses=[
            subprocess.TimeoutExpired([], 60), success()[1]])
        self.assertEqual(code, 1)
        self.assertIn("timed out", output)
        self.assertEqual(run.call_count, 2)

    def test_launch_failure(self):
        self.assertEqual(self.invoke(responses=[OSError("launch"), success()[1]])[0], 1)

    def test_no_gpu_or_empty_report_not_success(self):
        for text in ("NVIDIA hardware: NOT DETECTED", ""):
            code, output, _ = self.invoke(responses=[response(text), success()[1]])
            self.assertEqual(code, 1)
            self.assertNotIn("PASS: detection checks only", output)

    def test_execution_failure(self):
        items = success()
        items[2] = response("ERROR: CUDA synchronization failed", 3)
        code, output, _ = self.invoke(["--execute-cuda"], items)
        self.assertEqual(code, 1)
        self.assertNotIn("PASS: CUDA execution verification", output)

    def test_no_file_writes(self):
        with (patch("builtins.open", side_effect=AssertionError("file write")),
              patch.object(check.Path, "write_text", side_effect=AssertionError("file write")),
              patch.object(check.Path, "mkdir", side_effect=AssertionError("directory creation"))):
            self.assertEqual(self.invoke()[0], 0)


if __name__ == "__main__":
    unittest.main()
