"""Run with python -m unittest -v test_annotate."""

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import annotate


class AnnotationTests(unittest.TestCase):
    def valid(self, **changes):
        values = dict(start=30.125, end=42.75, kind="combat", description="Test only", duration=100)
        values.update(changes)
        return annotate.validate_annotation(**values)

    def test_valid_annotation(self):
        self.assertEqual(self.valid(), {"start": 30.125, "end": 42.75,
                                       "type": "combat", "description": "Test only"})
        for kind in annotate.ALLOWED_TYPES:
            self.assertEqual(self.valid(kind=kind)["type"], kind)
        self.assertEqual(self.valid(start=0, end=100)["end"], 100)

    def test_end_not_after_start(self):
        for end in (30.125, 20):
            with self.subTest(end=end), self.assertRaises(ValueError):
                self.valid(end=end)

    def test_negative_start(self):
        with self.assertRaises(ValueError):
            self.valid(start=-0.1)

    def test_invalid_type(self):
        with self.assertRaises(ValueError):
            self.valid(kind="unknown")

    def test_beyond_duration(self):
        with self.assertRaises(ValueError):
            self.valid(end=100.01)

    def test_nonfinite_timestamps(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            for field in ("start", "end"):
                with self.subTest(value=value, field=field), self.assertRaises(ValueError):
                    self.valid(**{field: value})

    def test_json_round_trip_and_sorting(self):
        with tempfile.TemporaryDirectory(dir=annotate.REPO) as directory:
            path = Path(directory) / "annotations.json"
            later = self.valid()
            earlier = self.valid(start=1.25, end=2.5, description="Test unicode: café")
            annotate.save_annotations(path, [later, earlier])
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), [earlier, later])
            self.assertEqual(annotate.load_annotations(path, 100), [earlier, later])
            self.assertIn('\n  {', path.read_text(encoding="utf-8"))
            annotate.save_annotations(path, [])
            self.assertEqual(annotate.load_annotations(path, 100), [])

    def test_delete_by_displayed_index(self):
        first = self.valid(start=1, end=2)
        second = self.valid()
        original = [first, second]
        self.assertEqual(annotate.delete_annotation(original, 1), [second])
        self.assertEqual(annotate.delete_annotation(original, 2), [first])
        self.assertEqual(original, [first, second])
        for index in (0, -1, 3):
            with self.assertRaises(ValueError):
                annotate.delete_annotation(original, index)
        with self.assertRaises(ValueError):
            annotate.delete_annotation([], 1)

    def test_invalid_json_is_not_overwritten(self):
        with tempfile.TemporaryDirectory(dir=annotate.REPO) as directory:
            path = Path(directory) / "annotations.json"
            path.write_text("broken json", encoding="utf-8")
            with self.assertRaises(ValueError):
                annotate.load_annotations(path, 100)
            self.assertEqual(path.read_text(encoding="utf-8"), "broken json")

    def test_interactive_add_list_delete_quit(self):
        # All invented test intervals stay in a temporary file, never the real V2 file.
        with tempfile.TemporaryDirectory(dir=annotate.REPO) as directory:
            path = Path(directory) / "ground_truth_v2.json"
            path.write_text("[]", encoding="utf-8")
            answers = ["add", "5.125", "8.75", "objective", "Test only", "list", "delete", "1", "quit"]
            output = io.StringIO()
            with patch.object(annotate, "REPO", Path(directory)), \
                 patch.object(annotate.subprocess, "run") as probe, \
                 patch("builtins.input", side_effect=answers), contextlib.redirect_stdout(output):
                probe.return_value.stdout = "100.0\n"
                annotate.main()
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), [])
            self.assertIn("1. 5.125s - 8.75s | objective | Test only", output.getvalue())
            self.assertEqual(output.getvalue().count("Saved."), 2)


if __name__ == "__main__":
    unittest.main()
