"""Fixture-only report/CLI checks: python -m unittest -v test_analyze_retention."""

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from analyze_retention import format_report, main
from retention import group_retention_by_intervals, summarize_retention_intervals


class AnalysisTests(unittest.TestCase):
    def fixtures(self, directory):
        csv_path = Path(directory) / "All.csv"
        csv_path.write_text("Video position (%),Absolute audience retention (%)\n"
                            "10,80\n30,90\n50,70\n", encoding="utf-8")
        annotations = Path(directory) / "annotations.json"
        annotations.write_text(json.dumps([
            {"start": 0, "end": 8, "type": "intro", "description": "SYNTHETIC test intro"},
            {"start": 12, "end": 20, "type": "combat", "description": "SYNTHETIC empty interval"},
        ]), encoding="utf-8")
        return csv_path, annotations

    def test_report_statistics_empty_and_unassigned(self):
        annotations = [dict(start=0, end=8, type="intro", description="Test description"),
                       dict(start=12, end=20, type="combat", description="Empty interval")]
        rows = [dict(timestamp_seconds=2, **{"Absolute audience retention (%)": "80"}),
                dict(timestamp_seconds=6, **{"Absolute audience retention (%)": "90"}),
                dict(timestamp_seconds=10, **{"Absolute audience retention (%)": "70"})]
        aligned = group_retention_by_intervals(rows, annotations)
        aligned["summaries"] = summarize_retention_intervals(aligned["intervals"])
        report = format_report(aligned)
        for text in ("0-8s | intro", "Test description", "Observations: 2", "Mean: 85.00%",
                     "Beginning: 80.00%", "Ending: 90.00%", "Change: +10.00 pp",
                     "Observations: 0 | No observations", "Unassigned observations: 1",
                     "ONE already-edited video"):
            self.assertIn(text, report)
        self.assertLess(report.index("0-8s"), report.index("12-20s"))

    def test_cli_overrides_and_real_png(self):
        try:
            import matplotlib
        except ImportError:
            self.skipTest("matplotlib unavailable")
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            csv_path, annotations = self.fixtures(directory)
            output = Path(directory) / "plot.png"
            with contextlib.redirect_stdout(io.StringIO()) as report:
                result = main([str(csv_path), "--annotations", str(annotations),
                               "--duration", "20", "--output", str(output)])
            self.assertEqual(result, 0)
            self.assertEqual(output.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
            self.assertIn("Mean: 85.00%", report.getvalue())
            self.assertIn("Unassigned observations: 1", report.getvalue())

    def test_missing_matplotlib_keeps_report(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            csv_path, annotations = self.fixtures(directory)
            with patch("analyze_retention.save_plot", side_effect=ModuleNotFoundError(name="matplotlib")), \
                 contextlib.redirect_stdout(io.StringIO()) as report, \
                 contextlib.redirect_stderr(io.StringIO()) as errors:
                result = main([str(csv_path), "--annotations", str(annotations), "--duration", "20"])
            self.assertEqual(result, 1)
            self.assertIn("Mean: 85.00%", report.getvalue())
            self.assertIn("matplotlib is not installed", errors.getvalue())

    def test_missing_csv_reports_failure(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            with contextlib.redirect_stderr(io.StringIO()) as errors:
                result = main([str(Path(directory) / "missing.csv")])
            self.assertEqual(result, 1)
            self.assertIn("Analysis failed", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
