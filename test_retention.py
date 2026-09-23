"""Run with python -m unittest -v test_retention."""

import csv
from pathlib import Path
import tempfile
import unittest

from retention import position_to_seconds, load_retention_csv, load_detailed_activity_csv


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.directory.cleanup)

    def write_csv(self, name, headers, rows):
        path = Path(self.directory.name) / name
        with path.open("w", newline="", encoding="utf-8-sig") as output:
            writer = csv.writer(output)
            writer.writerow(headers)
            writer.writerows(rows)
        return path

    def test_zero_percent(self):
        self.assertEqual(position_to_seconds(0, 231.433288), 0)

    def test_half_duration(self):
        self.assertEqual(position_to_seconds(50, 120), 60)
        self.assertAlmostEqual(position_to_seconds(50, 231.433288), 115.716644)

    def test_percentage_conversion(self):
        self.assertAlmostEqual(position_to_seconds(12.5, 80), 10)
        self.assertAlmostEqual(position_to_seconds(99, 231.433288), 229.11895512)
        self.assertEqual(position_to_seconds(100, 80), 80)

    def test_retention_csv_and_original_values(self):
        headers = ["Video position (%)", "Absolute audience retention (%)"]
        original = [["0", "105.2500"], ["50.00", "72.340"], ["99", ""]]
        path = self.write_csv("All.csv", headers, original)
        before = path.read_bytes()
        rows = load_retention_csv(path, 200)
        self.assertEqual([row["timestamp_seconds"] for row in rows], [0, 100, 198])
        self.assertEqual([{key: row[key] for key in headers} for row in rows],
                         [dict(zip(headers, values)) for values in original])
        self.assertEqual(path.read_bytes(), before)

    def test_activity_csv_and_original_values(self):
        headers = ["Video position (%)", "Started watching", "Stopped watching",
                   "Number of times each moment was seen", "Extra column"]
        original = [["0.0", "0012", "0", "1,234", "unchanged"],
                    ["25.50", "3", "2", "100.50", ""]]
        path = self.write_csv("Detailed activity.csv", headers, original)
        before = path.read_bytes()
        rows = load_detailed_activity_csv(path, 100)
        self.assertEqual([row["timestamp_seconds"] for row in rows], [0, 25.5])
        self.assertEqual([{key: row[key] for key in headers} for row in rows],
                         [dict(zip(headers, values)) for values in original])
        self.assertEqual(path.read_bytes(), before)

    def test_invalid_conversion_inputs(self):
        for position in (-1, 101, float("nan"), float("inf"), ""):
            with self.subTest(position=position), self.assertRaises(ValueError):
                position_to_seconds(position, 100)
        for duration in (0, -1, float("nan"), float("inf")):
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                position_to_seconds(50, duration)

    def test_missing_header(self):
        path = self.write_csv("All.csv", ["Video position (%)"], [["50"]])
        with self.assertRaisesRegex(ValueError, "Missing CSV columns"):
            load_retention_csv(path, 100)

    def test_header_only_csv(self):
        path = self.write_csv("All.csv", ["Video position (%)", "Absolute audience retention (%)"], [])
        self.assertEqual(load_retention_csv(path, 100), [])


if __name__ == "__main__":
    unittest.main()
