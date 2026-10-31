"""Unified format delegation plus real cache validation over synthetic byte fixtures."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

import pipeline
import export_shorts as shorts
import export_longform as longform
import test_pipeline as cli_fixtures
import test_artifact_relocation as cache_fixtures
import test_vertical_shorts as vertical_fixtures
from source_identity import prepare_v2
from verify import snapshot


class FormatCLITests(unittest.TestCase):
    run_cli = cli_fixtures.PipelineTests.run_cli

    def test_default_and_explicit_horizontal_unchanged(self):
        for extra in ([], ["--format", "horizontal"]):
            code, _, short, long = self.run_cli(extra)
            self.assertEqual(code, 0)
            expected = [str(Path("videos/example.mp4")), "--analysis", str(Path("output/analysis.json"))]
            short.assert_called_once_with(expected)
            long.assert_called_once_with(expected)

    def test_vertical_shorts_and_both(self):
        for mode in ("shorts", "both"):
            code, _, short, long = self.run_cli(["--mode", mode, "--format", "vertical"])
            self.assertEqual(code, 0)
            self.assertEqual(short.call_args.args[0][-2:], ["--format", "vertical"])
            if mode == "both":
                self.assertNotIn("--format", long.call_args.args[0])
            else:
                long.assert_not_called()

    def test_all_existing_flags_forwarded(self):
        for flags in (["--cache-only", "--manifest-version", "2", "--output-root", "custom"],
                      ["--dry-run"], ["--force"]):
            code, _, short, long = self.run_cli(["--format", "vertical", *flags])
            self.assertEqual(code, 0)
            self.assertEqual(short.call_args.args[0][3:], flags + ["--format", "vertical"])
            self.assertEqual(long.call_args.args[0][3:], flags)

    def test_invalid_combinations_before_export(self):
        for flags in (["--mode", "longform", "--format", "vertical"], ["--format", "square"]):
            with (patch.object(pipeline, "shorts_main") as short,
                  patch.object(pipeline, "longform_main") as long,
                  contextlib.redirect_stderr(io.StringIO()) as output):
                with self.assertRaises(SystemExit) as raised:
                    pipeline.main(["v.mp4", "--analysis", "a.json", *flags])
                self.assertEqual(raised.exception.code, 2)
                short.assert_not_called()
                long.assert_not_called()
                self.assertIn("--format", output.getvalue())

    def test_horizontal_longform_allowed(self):
        code, _, short, long = self.run_cli(["--mode", "longform", "--format", "horizontal"])
        self.assertEqual(code, 0)
        short.assert_not_called()
        self.assertNotIn("--format", long.call_args.args[0])

    def test_vertical_partial_failure_preserved(self):
        for error in (1, SystemExit(1), RuntimeError("fixture")):
            code, output, _, long = self.run_cli(["--format", "vertical"], shorts=error)
            self.assertEqual(code, 1)
            self.assertIn("partial failure", output)
            long.assert_called_once()


class UnifiedCacheTests(unittest.TestCase):
    setUp = cache_fixtures.RelocationTests.setUp

    def vertical_fixture(self, version=1):
        _, directory, manifest = shorts.plan_export(
            self.video, self.analysis, output_root=self.output, export_format="vertical")
        if version == 2:
            manifest = prepare_v2(self.video, directory, manifest, self.output,
                                  cache_only=True, dry_run=False, force=False)
        directory.mkdir(parents=True)
        for row in manifest["clips"]:
            target = directory/row["output_filename"]
            target.write_bytes(b"synthetic vertical fixture")
            row.update(status="exported", output_sha256=shorts.media_sha256(target))
        (directory/"shorts_manifest.json").write_text(json.dumps(manifest))
        if version == 2:
            path = self.output/self.video.stem/"longform"/"longform_manifest.json"
            prior = json.loads(path.read_text())
            prior = prepare_v2(self.video, path.parent, prior, self.output,
                               cache_only=True, dry_run=False, force=False)
            path.write_text(json.dumps(prior))
        return directory

    def cached_cli(self, mode="shorts", version=1, format_name="vertical"):
        paths = [p for p in self.root.rglob("*") if p.is_file()]
        before = snapshot(paths)
        def probe(path):
            return dict(duration_seconds=self.long_duration if Path(path).name == "longform_v1.mp4" else 15,
                        streams=[dict(codec_type="audio"), dict(codec_type="video")])
        with (patch.object(shorts, "probe_clip", side_effect=probe),
              patch.object(shorts, "probe_format_streams", return_value=vertical_fixtures.VERTICAL_PROBE),
              patch("subprocess.run", side_effect=AssertionError("No encoding/external commands")),
              patch.object(Path, "mkdir", side_effect=AssertionError("No mkdir")),
              patch("tempfile.NamedTemporaryFile", side_effect=AssertionError("No writes")),
              patch("transcription.load_model", side_effect=AssertionError("No ASR")),
              patch("language_scoring.LocalTextModel", side_effect=AssertionError("No model")),
              patch("motion.analyze_motion", side_effect=AssertionError("No analysis")),
              contextlib.redirect_stdout(io.StringIO()) as output,
              contextlib.redirect_stderr(io.StringIO())):
            code = pipeline.main([str(self.video), "--analysis", str(self.analysis),
                                  "--mode", mode, "--format", format_name, "--cache-only",
                                  "--manifest-version", str(version), "--output-root", str(self.output)])
        self.assertEqual(before, snapshot(paths))
        return code, output.getvalue()

    def test_v1_vertical_hit_and_both(self):
        self.vertical_fixture()
        for mode in ("shorts", "both"):
            code, output = self.cached_cli(mode)
            self.assertEqual(code, 0)
            self.assertIn("Shorts: success", output)
            if mode == "both":
                self.assertIn("Long-form: success", output)

    def test_horizontal_v1_backward_compatibility(self):
        code, _ = self.cached_cli(mode="both", format_name="horizontal")
        self.assertEqual(code, 0)

    def test_missing_vertical_cache_partial_failure(self):
        code, output = self.cached_cli(mode="both")
        self.assertEqual(code, 1)
        self.assertIn("Shorts: failed", output)
        self.assertIn("Long-form: success", output)
        self.assertIn("partial failure", output)
        self.assertFalse((self.output/self.video.stem/"shorts_vertical").exists())

    def test_horizontal_manifest_not_vertical_hit(self):
        directory = self.vertical_fixture()
        horizontal = self.output/self.video.stem/"shorts"/"shorts_manifest.json"
        (directory/"shorts_manifest.json").write_bytes(horizontal.read_bytes())
        self.assertEqual(self.cached_cli()[0], 1)

    def test_missing_vertical_clip_not_repaired(self):
        directory = self.vertical_fixture()
        next(directory.glob("*.mp4")).unlink()
        self.assertEqual(self.cached_cli()[0], 1)

    def test_v2_both_relocated_content_cache(self):
        self.vertical_fixture(version=2)
        self.assertEqual(self.cached_cli(mode="both", version=2)[0], 0)
        moved = self.root/"relocated"
        moved.mkdir()
        self.video = self.video.rename(moved/"game.mp4")
        destination = moved/"exports"
        shutil.copytree(self.output, destination)
        self.output = destination
        self.assertEqual(self.cached_cli(mode="both", version=2)[0], 0)


if __name__ == "__main__":
    unittest.main()
