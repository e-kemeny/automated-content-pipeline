"""Vertical export contracts; media operations mocked, identity/cache logic real."""
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import patch

import export_shorts as shorts
import test_export_shorts as fixtures
from source_identity import prepare_v2
from verify import snapshot

VERTICAL_PROBE = dict(streams=[
    dict(codec_type="video", codec_name="h264", width=1080, height=1920, sample_aspect_ratio="1:1"),
    dict(codec_type="audio", codec_name="aac")])


class VerticalTests(unittest.TestCase):
    setUp = fixtures.ShortsTests.setUp
    export = fixtures.ShortsTests.export
    encoder = fixtures.ShortsTests.encoder

    def encoded(self, **kwargs):
        with (patch.object(shorts.subprocess, "run", side_effect=self.encoder) as run,
              patch.object(shorts, "probe_clip", return_value=dict(duration_seconds=15, streams=[])),
              patch.object(shorts, "probe_format_streams", return_value=VERTICAL_PROBE)):
            result = self.export(**kwargs)
        return result, run

    def test_default_horizontal_unchanged(self):
        (directory, manifest), run = self.encoded()
        self.assertEqual(directory.name, "shorts")
        self.assertEqual(manifest["encoding"], dict(video="libx264", audio="aac", crf=18, preset="fast"))
        self.assertNotIn("-vf", run.call_args.args[0])
        _, explicit = self.export(dry_run=True, export_format="horizontal")
        self.assertEqual(explicit["encoding"], manifest["encoding"])

    def test_vertical_filter_audio_and_timing(self):
        _, horizontal = self.export(dry_run=True)
        (directory, vertical), run = self.encoded(export_format="vertical")
        self.assertEqual(directory.name, "shorts_vertical")
        self.assertEqual(vertical["selection"], horizontal["selection"])
        self.assertEqual(vertical["encoding"]["width"], 1080)
        self.assertEqual(vertical["encoding"]["height"], 1920)
        self.assertEqual(vertical["encoding"]["format"], "vertical")
        for row, original, invocation in zip(vertical["clips"], horizontal["clips"], run.call_args_list):
            for key in ("start", "end", "duration", "candidate_timestamp", "candidate_evidence"):
                self.assertEqual(row[key], original[key])
            cmd = invocation.args[0]
            self.assertEqual(cmd[cmd.index("-ss")+1], str(row["start"]))
            self.assertEqual(cmd[cmd.index("-t")+1], str(row["duration"]))
            self.assertEqual(cmd[cmd.index("-vf")+1], shorts.VERTICAL_FILTER)
            self.assertIn("force_original_aspect_ratio=increase", shorts.VERTICAL_FILTER)
            self.assertIn("crop=1080:1920:(iw-ow)/2:(ih-oh)/2", shorts.VERTICAL_FILTER)
            self.assertIn("setsar=1", shorts.VERTICAL_FILTER)
            self.assertIn("0:a:0", cmd)
            self.assertEqual(cmd[cmd.index("-c:a")+1], "aac")
            self.assertEqual(cmd[cmd.index("-c:v")+1], "libx264")
            self.assertEqual(cmd[cmd.index("-pix_fmt")+1], "yuv420p")

    def test_cli_and_invalid_format(self):
        directory, manifest = self.export(dry_run=True)
        with (patch.object(shorts, "export_shorts", return_value=(directory, manifest)) as export,
              contextlib.redirect_stdout(io.StringIO())):
            shorts.main([str(self.video), "--analysis", str(self.path), "--format", "vertical", "--dry-run"])
        self.assertEqual(export.call_args.kwargs["export_format"], "vertical")
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
            shorts.main([str(self.video), "--analysis", str(self.path), "--format", "square"])
        self.assertEqual(exc.exception.code, 2)
        with self.assertRaises(ValueError):
            self.export(dry_run=True, export_format="square")

    def cache(self, **kwargs):
        with (patch.object(shorts.subprocess, "run", side_effect=AssertionError("encoding forbidden")),
              patch.object(shorts, "probe_clip", return_value=dict(duration_seconds=15, streams=[])),
              patch.object(shorts, "probe_format_streams", return_value=VERTICAL_PROBE),
              patch.object(Path, "mkdir", side_effect=AssertionError("mkdir forbidden")),
              patch.object(shorts.tempfile, "NamedTemporaryFile", side_effect=AssertionError("writes forbidden"))):
            return self.export(cache_only=True, **kwargs)

    def test_v1_both_formats_cache_readonly(self):
        self.encoded()
        self.encoded(export_format="vertical")
        paths = [p for p in self.root.rglob("*") if p.is_file()]
        before = snapshot(paths)
        for format_name in ("horizontal", "vertical"):
            _, result = self.cache(export_format=format_name)
            self.assertTrue(all(row["status"] == "reused" for row in result["clips"]))
        self.assertEqual(before, snapshot(paths))

    def test_wrong_format_manifest_rejected_normal_and_cache(self):
        (_, horizontal), _ = self.encoded()
        (directory, _), _ = self.encoded(export_format="vertical")
        (directory/"shorts_manifest.json").write_text(json.dumps(horizontal))
        with self.assertRaisesRegex(ValueError, "encoding"):
            self.cache(export_format="vertical")
        with self.assertRaisesRegex(ValueError, "format/encoding"):
            self.export(export_format="vertical")
        # No silent repair or reuse of horizontal media in the vertical directory.

    def test_missing_vertical_does_not_use_horizontal(self):
        self.encoded()
        with self.assertRaises(OSError):
            self.cache(export_format="vertical")
        self.assertFalse((self.output/"game"/"shorts_vertical").exists())

    def test_missing_clip_fails_without_repair(self):
        (directory, manifest), _ = self.encoded(export_format="vertical")
        (directory/manifest["clips"][0]["output_filename"]).unlink()
        paths = [p for p in self.root.rglob("*") if p.is_file()]
        before = snapshot(paths)
        with self.assertRaises(ValueError):
            self.cache(export_format="vertical")
        self.assertEqual(before, snapshot(paths))

    def test_v2_signatures_and_relocation(self):
        _, hd, horizontal = shorts.plan_export(self.video, self.path, 2, self.output)
        _, vd, vertical = shorts.plan_export(self.video, self.path, 2, self.output, "vertical")
        h = prepare_v2(self.video, hd, horizontal, self.output, cache_only=True, dry_run=False, force=False)
        v = prepare_v2(self.video, vd, vertical, self.output, cache_only=True, dry_run=False, force=False)
        self.assertEqual(h["source_identity"], v["source_identity"])
        self.assertNotEqual(h["plan_signature"], v["plan_signature"])
        self.encoded(export_format="vertical", manifest_version=2)
        relocated = self.root/"relocated"
        relocated.mkdir()
        self.video = self.video.rename(relocated/"game.mp4")
        self.actual["path"] = str(self.video)
        moved_outputs = relocated/"exports"
        shutil.copytree(self.output, moved_outputs)
        self.output = moved_outputs
        paths = [p for p in self.root.rglob("*") if p.is_file()]
        before = snapshot(paths)
        _, result = self.cache(export_format="vertical", manifest_version=2)
        self.assertEqual(result["source_identity"]["version"], 1)
        self.assertEqual(before, snapshot(paths))
        self.assertTrue(all(r["status"] == "reused" for r in result["clips"]))

    def test_failed_encode_no_partial_mp4(self):
        def fail(cmd, **kwargs):
            Path(cmd[-1]).write_bytes(b"partial bytes")
            raise subprocess.CalledProcessError(1, cmd, stderr="fixture failure")
        with patch.object(shorts.subprocess, "run", side_effect=fail):
            directory, manifest = self.export(export_format="vertical")
        self.assertTrue(all(row["status"] == "failed" for row in manifest["clips"]))
        self.assertEqual(list(directory.glob("*.mp4")), [])
        self.assertEqual(list(directory.glob(".shorts_*")), [])

    def test_wrong_dimensions_fail_before_publication(self):
        wrong = deepcopy(VERTICAL_PROBE)
        wrong["streams"][0]["width"] = 1920
        with (patch.object(shorts.subprocess, "run", side_effect=self.encoder),
              patch.object(shorts, "probe_clip", return_value=dict(duration_seconds=15, streams=[])),
              patch.object(shorts, "probe_format_streams", return_value=wrong)):
            directory, manifest = self.export(export_format="vertical")
        self.assertTrue(all(r["status"] == "failed" for r in manifest["clips"]))
        self.assertEqual(list(directory.glob("*.mp4")), [])

    def test_format_validation_on_cache_and_normal_reuse(self):
        self.encoded(export_format="vertical")
        wrong = deepcopy(VERTICAL_PROBE)
        wrong["streams"][0]["sample_aspect_ratio"] = "2:1"
        with (patch.object(shorts.subprocess, "run", side_effect=AssertionError("no encoding")),
              patch.object(shorts, "probe_clip", return_value=dict(duration_seconds=15, streams=[])),
              patch.object(shorts, "probe_format_streams", return_value=wrong)):
            with self.assertRaises(ValueError):
                self.export(export_format="vertical", cache_only=True)
            _, manifest = self.export(export_format="vertical")
            self.assertTrue(all(r["status"] == "failed" for r in manifest["clips"]))

    def test_unrelated_files_protected(self):
        directory, manifest = self.export(export_format="vertical", dry_run=True)
        directory.mkdir(parents=True)
        target = directory/manifest["clips"][0]["output_filename"]
        target.write_bytes(b"unrelated")
        with self.assertRaises(ValueError):
            self.export(export_format="vertical", force=True)
        self.assertEqual(target.read_bytes(), b"unrelated")


if __name__ == "__main__":
    unittest.main()
