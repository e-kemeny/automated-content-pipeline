"""Thin CLI delegation; exporter tests cover encoding and validation policies."""
import contextlib
import io
import unittest
from unittest.mock import patch

import pipeline


class PipelineTests(unittest.TestCase):
    def run_cli(self, extra=(), shorts=0, longform=0):
        output = io.StringIO()
        with patch("pipeline.shorts_main") as short, patch("pipeline.longform_main") as long:
            for mock, result in ((short, shorts), (long, longform)):
                if isinstance(result, BaseException):
                    mock.side_effect = result
                else:
                    mock.return_value = result
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                code = pipeline.main(["videos/example.mp4", "--analysis", "output/analysis.json", *extra])
        return code, output.getvalue(), short, long

    def test_default_both_and_forwarding(self):
        code, output, short, long = self.run_cli()
        self.assertEqual(code, 0)
        expected = ["videos/example.mp4", "--analysis", "output/analysis.json"]
        # pathlib normalizes separators on Windows.
        expected[0] = str(pipeline.Path(expected[0]))
        expected[2] = str(pipeline.Path(expected[2]))
        short.assert_called_once_with(expected)
        long.assert_called_once_with(expected)
        self.assertIn("Shorts: success", output)
        self.assertIn("Long-form: success", output)

    def test_modes(self):
        for mode in ("shorts", "longform", "both"):
            with self.subTest(mode=mode):
                code, _, short, long = self.run_cli(["--mode", mode])
                self.assertEqual(code, 0)
                self.assertEqual(short.call_count, int(mode != "longform"))
                self.assertEqual(long.call_count, int(mode != "shorts"))

    def test_dry_run_and_force(self):
        for flags in (["--dry-run"], ["--force"], ["--dry-run", "--force"]):
            with self.subTest(flags=flags):
                code, _, short, long = self.run_cli(flags)
                self.assertEqual(code, 0)
                for mock in (short, long):
                    self.assertEqual(mock.call_args.args[0][3:], flags)

    def test_reported_partial_failure(self):
        code, output, _, long = self.run_cli(shorts=1)
        self.assertEqual(code, 1)
        long.assert_called_once()
        self.assertIn("Pipeline: partial failure", output)

    def test_second_export_failure(self):
        code, output, short, _ = self.run_cli(longform=1)
        self.assertEqual(code, 1)
        short.assert_called_once()
        self.assertIn("Long-form: failed", output)
        self.assertIn("partial failure", output)

    def test_exporter_validation_exit_does_not_stop_both(self):
        code, output, _, long = self.run_cli(shorts=SystemExit(1))
        self.assertEqual(code, 1)
        long.assert_called_once()
        self.assertIn("partial failure", output)

    def test_unexpected_error_does_not_stop_both(self):
        code, output, _, long = self.run_cli(shorts=RuntimeError("encoding failed"))
        self.assertEqual(code, 1)
        long.assert_called_once()
        self.assertIn("RuntimeError: encoding failed", output)

    def test_missing_or_incompatible_analysis_errors(self):
        for error in (FileNotFoundError("analysis missing"), ValueError("Unsupported schema version")):
            with self.subTest(error=error):
                code, output, _, _ = self.run_cli(shorts=error, longform=error)
                self.assertEqual(code, 1)
                self.assertIn(str(error), output)
                self.assertIn("Pipeline: failed (2/2", output)

    def test_invalid_mode(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            pipeline.main(["video.mp4", "--analysis", "analysis.json", "--mode", "invalid"])
        self.assertEqual(raised.exception.code, 2)

    def test_required_analysis(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            pipeline.main(["video.mp4"])
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()

