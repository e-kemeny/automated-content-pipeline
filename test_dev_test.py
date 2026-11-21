"""Developer orchestration tests: real cache validation, mocked extraction/export."""
import csv
from contextlib import redirect_stdout, redirect_stderr
import io
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import dev_test as dev
import test_dense_to_shared as fixtures
from shared_analysis import load_analysis
from source_identity import canonical


class DeveloperTests(unittest.TestCase):
    def setUp(self):
        fixtures.IntegrationTests.setUp(self)
        self.output_root = self.root / "runs"
        self.paths = dev.paths_for(self.video, self.output_root)
        self.probe = self.stack.enter_context(patch("export_shorts.probe_media", return_value=self.full["source_video"]))
        self.pipeline = self.stack.enter_context(patch.object(dev.pipeline, "main", return_value=0))

    def invoke(self, *args):
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            code = dev.main([str(self.video), "--output-root", str(self.output_root), *args])
        return code, output.getvalue()

    def seed(self):
        dev.integration.generate(self.video, self.paths["cache"], self.paths["analysis"])

    def test_fresh_run_and_modes(self):
        for mode in ("shorts", "longform", "both"):
            with self.subTest(mode=mode):
                self.pipeline.reset_mock()
                code, output = self.invoke("--mode", mode)
                self.assertEqual(code, 0)
                self.assertEqual(self.pipeline.call_count, 2 if mode == "both" else 1)
                self.assertIn("Summary:", output)
                for call in self.pipeline.call_args_list:
                    self.assertNotIn("--force", call.args[0])
        self.extract.assert_called_once()

    def test_valid_reuse_preserves_analysis_and_cache(self):
        self.seed()
        before = [(p.read_bytes(), p.stat().st_mtime_ns) for p in (self.paths["cache"], self.paths["analysis"])]
        self.extract.side_effect = AssertionError("No extraction")
        self.assertEqual(self.invoke()[0], 0)
        self.assertEqual(before, [(p.read_bytes(), p.stat().st_mtime_ns) for p in (self.paths["cache"], self.paths["analysis"])])

    def test_stale_source(self):
        self.seed()
        self.video.write_bytes(b"other source")
        code, output = self.invoke()
        self.assertEqual(code, 1)
        self.assertIn("Stale dense cache", output)
        self.pipeline.assert_not_called()
        self.extract.assert_called_once()

    def test_stale_recipe(self):
        self.seed()
        with patch.object(dev.dense, "recipe", return_value={"version": 99}):
            self.assertEqual(self.invoke()[0], 1)
        self.pipeline.assert_not_called()

    def test_changed_analysis(self):
        self.seed()
        data = load_analysis(self.paths["analysis"])
        data["candidate_windows"]["data"][0]["score"] = 123
        self.paths["analysis"].write_bytes(canonical(data))
        self.assertEqual(self.invoke()[0], 1)
        self.pipeline.assert_not_called()

    def test_missing_cache_with_analysis_does_not_recompute(self):
        self.seed()
        self.paths["cache"].unlink()
        self.extract.reset_mock()
        self.assertEqual(self.invoke()[0], 1)
        self.extract.assert_not_called()

    def test_dry_run_fresh_writes_nothing(self):
        code, output = self.invoke("--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("no work performed", output)
        self.assertFalse(self.output_root.exists())
        self.extract.assert_not_called()
        self.pipeline.assert_not_called()

    def test_dry_run_cached_forwards_preview_without_report(self):
        self.seed()
        self.assertEqual(self.invoke("--dry-run")[0], 0)
        for call in self.pipeline.call_args_list:
            self.assertIn("--dry-run", call.args[0])
        self.assertFalse(self.paths["review"].exists())

    def test_dry_run_cache_only_without_analysis(self):
        self.seed()
        self.paths["analysis"].unlink()
        self.assertEqual(self.invoke("--dry-run")[0], 0)
        self.assertFalse(self.paths["analysis"].exists())
        self.pipeline.assert_not_called()
        self.extract.assert_called_once()

    def test_existing_export_directory_requires_strict_reuse(self):
        self.seed()
        directory = self.paths["exports"] / self.video.stem / "shorts"
        directory.mkdir(parents=True)
        (directory / "unrelated.txt").write_text("keep")
        self.pipeline.side_effect = [1, 0]
        code, output = self.invoke()
        self.assertEqual(code, 1)
        self.assertIn("--cache-only", self.pipeline.call_args_list[0].args[0])
        self.assertNotIn("--cache-only", self.pipeline.call_args_list[1].args[0])
        self.assertIn("shorts=FAILED; longform=exported", output)
        self.assertEqual((directory / "unrelated.txt").read_text(), "keep")

    def test_cache_only_missing_never_creates(self):
        self.assertEqual(self.invoke("--cache-only")[0], 1)
        self.assertFalse(self.output_root.exists())
        self.extract.assert_not_called()

    def test_cache_only_forwards_and_does_not_write_report(self):
        self.seed()
        self.assertEqual(self.invoke("--cache-only")[0], 0)
        self.assertFalse(self.paths["review"].exists())
        for call in self.pipeline.call_args_list:
            self.assertIn("--cache-only", call.args[0])

    def test_review_fields_and_human_edits(self):
        self.assertEqual(self.invoke()[0], 0)
        with self.paths["review"].open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0]["selection_method"], "Audio-only")
        self.assertEqual(rows[0]["anchor_seconds"], "5")
        self.assertEqual(rows[0]["human_quality_rating"], "")
        self.assertEqual(rows[0]["human_notes"], "")
        self.paths["review"].write_text("my notes")
        before = self.paths["review"].stat().st_mtime_ns
        self.assertEqual(self.invoke()[0], 0)
        self.assertEqual(self.paths["review"].read_text(), "my notes")
        self.assertEqual(self.paths["review"].stat().st_mtime_ns, before)

    def test_atomic_review_race(self):
        self.paths["run"].mkdir(parents=True)
        original = os.link
        def race(source, dest):
            Path(dest).write_text("other reviewer")
            original(source, dest)
        with patch.object(dev.os, "link", side_effect=race), self.assertRaises(FileExistsError):
            dev.publish_review("new report", self.paths["review"])
        self.assertEqual(self.paths["review"].read_text(), "other reviewer")
        self.assertEqual(list(self.paths["run"].glob(".dev-review-*")), [])

    def test_failure_propagation(self):
        self.pipeline.side_effect = [RuntimeError("export failure"), 0]
        code, output = self.invoke()
        self.assertEqual(code, 1)
        self.assertEqual(self.pipeline.call_count, 2)
        self.assertIn("shorts=FAILED", output)

    def test_invalid_arguments(self):
        for args in (("--mode", "invalid"), ("--dry-run", "--cache-only")):
            with self.subTest(args=args), self.assertRaises(SystemExit) as exc:
                self.invoke(*args)
            self.assertEqual(exc.exception.code, 2)

    def test_missing_source(self):
        self.video.unlink()
        self.assertEqual(self.invoke()[0], 1)
        self.assertFalse(self.output_root.exists())

    def test_disappearing_cache_in_read_only_never_collects(self):
        self.seed()
        with patch.object(dev, "read_json", side_effect=FileNotFoundError("cache disappeared")), patch.object(
                dev.dense, "collect", side_effect=AssertionError("No collection path")):
            self.assertEqual(self.invoke("--cache-only")[0], 1)
        self.pipeline.assert_not_called()


if __name__ == "__main__":
    unittest.main()
