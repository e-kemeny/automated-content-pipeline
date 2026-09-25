"""Run with python -m unittest -v test_retention."""

import csv
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from retention import position_to_seconds, load_retention_csv, load_detailed_activity_csv
from retention import group_retention_by_intervals, summarize_retention_intervals


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


class IntervalGroupingTests(unittest.TestCase):
    def annotation(self, start, end):
        return {"start": start, "end": end, "type": "combat", "description": "Test interval"}

    def row(self, timestamp):
        return {"timestamp_seconds": timestamp, "Video position (%)": "12.50",
                "Absolute audience retention (%)": "80.000"}

    def test_inside_and_preservation(self):
        annotation = self.annotation(10, 20)
        annotation["extra_metadata"] = "keep this"
        row = self.row(12.5)
        result = group_retention_by_intervals([row], [annotation])
        group = result["intervals"][0]
        self.assertEqual(group, {"annotation": annotation, "samples": [row]})
        self.assertEqual(result["unassigned"], [])
        self.assertIsNot(group["annotation"], annotation)
        self.assertIsNot(group["samples"][0], row)
        self.assertNotIn("samples", annotation)
        self.assertEqual(row, self.row(12.5))

    def test_adjacent_boundaries(self):
        rows = [self.row(0), self.row(10), self.row(20)]
        result = group_retention_by_intervals(rows, [self.annotation(0, 10), self.annotation(10, 20)])
        self.assertEqual(result["intervals"][0]["samples"], [rows[0]])
        self.assertEqual(result["intervals"][1]["samples"], [rows[1]])
        self.assertEqual(result["unassigned"], [rows[2]])

    def test_multiple_samples_and_chronological_order(self):
        rows = [self.row(15), self.row(4), self.row(2)]
        annotations = [self.annotation(10, 20), self.annotation(0, 10)]
        result = group_retention_by_intervals(rows, annotations)
        self.assertEqual([group["annotation"]["start"] for group in result["intervals"]], [0, 10])
        self.assertEqual(result["intervals"][0]["samples"], [rows[2], rows[1]])
        self.assertEqual(result["intervals"][1]["samples"], [rows[0]])
        self.assertEqual([row["timestamp_seconds"] for row in rows], [15, 4, 2])
        self.assertEqual([item["start"] for item in annotations], [10, 0])

    def test_interval_without_samples(self):
        annotation = self.annotation(10, 20)
        self.assertEqual(group_retention_by_intervals([], [annotation]),
                         {"intervals": [{"annotation": annotation, "samples": []}], "unassigned": []})

    def test_intentional_gap(self):
        rows = [self.row(18.5), self.row(18), self.row(19)]
        result = group_retention_by_intervals(rows, [self.annotation(0, 18), self.annotation(19, 27)])
        self.assertEqual(result["unassigned"], [rows[1], rows[0]])
        self.assertEqual(result["intervals"][1]["samples"], [rows[2]])

    def test_final_endpoint_not_extended(self):
        rows = [self.row(231.432), self.row(231.433), self.row(231.433288)]
        result = group_retention_by_intervals(rows, [self.annotation(212, 231.433)])
        self.assertEqual(result["intervals"][0]["samples"], rows[:1])
        self.assertEqual(result["unassigned"], rows[1:])

    def test_overlap_assigned_once(self):
        row = self.row(12)
        result = group_retention_by_intervals([row], [self.annotation(10, 20), self.annotation(0, 15)])
        self.assertEqual([group["samples"] for group in result["intervals"]], [[row], []])

    def test_no_annotations(self):
        rows = [self.row(5), self.row(2)]
        self.assertEqual(group_retention_by_intervals(rows, []),
                         {"intervals": [], "unassigned": [rows[1], rows[0]]})


class IntervalSummaryTests(unittest.TestCase):
    def group(self, values):
        return {
            "annotation": {"start": 0.0, "end": 10.0, "type": "combat",
                           "description": "Test only", "extra_metadata": "preserved"},
            "samples": [{"timestamp_seconds": index, "Absolute audience retention (%)": value}
                        for index, value in enumerate(values)],
        }

    def test_mean_min_max(self):
        summary = summarize_retention_intervals([self.group(["80.50", "100.25", "90.00"])])[0]
        self.assertEqual(summary["sample_count"], 3)
        self.assertAlmostEqual(summary["mean_retention"], 90.25)
        self.assertEqual(summary["min_retention"], 80.5)
        self.assertEqual(summary["max_retention"], 100.25)

    def test_first_last_and_positive_change(self):
        summary = summarize_retention_intervals([self.group(["80", "110", "90"])])[0]
        self.assertEqual(summary["start_retention"], 80)
        self.assertEqual(summary["end_retention"], 90)
        self.assertEqual(summary["retention_change"], 10)

    def test_negative_change(self):
        summary = summarize_retention_intervals([self.group(["90", "50", "80"])])[0]
        self.assertEqual(summary["start_retention"], 90)
        self.assertEqual(summary["end_retention"], 80)
        self.assertEqual(summary["retention_change"], -10)

    def test_one_sample(self):
        summary = summarize_retention_intervals([self.group(["72.125"])])[0]
        self.assertEqual(summary["sample_count"], 1)
        for key in ("mean_retention", "min_retention", "max_retention", "start_retention", "end_retention"):
            self.assertEqual(summary[key], 72.125)
        self.assertEqual(summary["retention_change"], 0)

    def test_empty_interval(self):
        group = self.group([])
        summary = summarize_retention_intervals([group])[0]
        self.assertEqual(summary["annotation"], group["annotation"])
        self.assertEqual(summary["sample_count"], 0)
        for key in ("mean_retention", "min_retention", "max_retention", "start_retention", "end_retention", "retention_change"):
            self.assertIsNone(summary[key])

    def test_preservation_and_chronological_order(self):
        early = self.group([])["annotation"]
        late = dict(early, start=10.0, end=20.0, type="victory")
        rows = [{"timestamp_seconds": 12, "Absolute audience retention (%)": "102.500"},
                {"timestamp_seconds": 3, "Absolute audience retention (%)": "080.250"},
                {"timestamp_seconds": 30, "Absolute audience retention (%)": "60"}]
        grouped = group_retention_by_intervals(rows, [late, early])
        before = deepcopy(grouped)
        summaries = summarize_retention_intervals(grouped["intervals"])
        self.assertEqual([summary["annotation"] for summary in summaries], [early, late])
        self.assertEqual([summary["start_retention"] for summary in summaries], [80.25, 102.5])
        self.assertIsNot(summaries[0]["annotation"], grouped["intervals"][0]["annotation"])
        self.assertEqual(grouped, before)

    def test_invalid_values_rejected(self):
        for value in ("", "not numeric", "nan", "inf", "-inf"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                summarize_retention_intervals([self.group([value])])

    def test_no_intervals(self):
        self.assertEqual(summarize_retention_intervals([]), [])

if __name__ == "__main__":
    unittest.main()
