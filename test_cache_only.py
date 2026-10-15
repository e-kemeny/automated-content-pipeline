"""Strict cache-only regression tests using temporary fixtures, never real media."""
import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import export_shorts as shorts
import export_longform as longform
import pipeline
import test_export_shorts as short_tests
import test_export_longform as long_tests


class CacheOnlyTests(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(self, mode):
        case = (short_tests.ShortsTests if mode == "shorts" else long_tests.AssemblyTests)()
        case.setUp()
        try:
            (directory, manifest), _ = case.encoded()
            module = shorts if mode == "shorts" else longform
            probe = (lambda path: dict(duration_seconds=15, streams=[])) if mode == "shorts" else case.probe
            with patch.object(shorts, "probe_clip", side_effect=probe),                  patch.object(module.subprocess, "run", side_effect=AssertionError("No encoding")),                  patch.object(Path, "mkdir", side_effect=AssertionError("No mkdir")),                  patch.object(module.tempfile, "NamedTemporaryFile", side_effect=AssertionError("No writes")),                  patch.object(module.tempfile, "TemporaryDirectory", side_effect=AssertionError("No work directory")),                  patch.object(module.os, "replace", side_effect=AssertionError("No replace")):
                yield case, directory, module
        finally:
            case.doCleanups()

    def snapshot(self, root):
        return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in root.rglob("*") if p.is_file()}

    def test_valid_no_writes(self):
        for mode in ("shorts", "longform"):
            with self.subTest(mode=mode), self.fixture(mode) as (case, directory, module):
                before = self.snapshot(case.root)
                _, result = case.export(cache_only=True)
                self.assertEqual(before, self.snapshot(case.root))
                if mode == "shorts":
                    self.assertTrue(all(r["status"] == "reused" for r in result["clips"]))
                else:
                    self.assertEqual(result["assembly"]["status"], "reused")

    def test_invalid_cache_no_repair(self):
        for mode in ("shorts", "longform"):
            for failure in ("missing_mp4", "missing_manifest", "invalid_json", "invalid_object",
                            "stale_config", "stale_source", "stale_analysis", "failed_status", "corrupt_mp4"):
                with self.subTest(mode=mode, failure=failure), self.fixture(mode) as (case, directory, module):
                    path = directory/("shorts_manifest.json" if mode == "shorts" else "longform_manifest.json")
                    mp4 = next(directory.glob("*.mp4"))
                    if failure == "missing_mp4":
                        mp4.unlink()
                    elif failure == "missing_manifest":
                        path.unlink()
                    elif failure == "invalid_json":
                        path.write_text("{")
                    elif failure == "invalid_object":
                        path.write_text("[]")
                    elif failure == "corrupt_mp4":
                        mp4.write_bytes(b"changed")
                    else:
                        data = json.loads(path.read_text())
                        if failure == "stale_config":
                            data["encoding"]["crf"] = 99
                        elif failure == "stale_source":
                            data["source"]["sha256"] = "0"*64
                        elif failure == "stale_analysis":
                            data["shared_analysis"]["sha256"] = "0"*64
                        elif mode == "shorts":
                            data["clips"][0]["status"] = "failed"
                        else:
                            data["assembly"]["status"] = "failed"
                        path.write_text(json.dumps(data))
                    before = self.snapshot(case.root)
                    with self.assertRaises((ValueError, OSError)):
                        case.export(cache_only=True)
                    self.assertEqual(before, self.snapshot(case.root))

    def test_disappears_during_probe_never_encodes(self):
        for mode in ("shorts", "longform"):
            with self.subTest(mode=mode), self.fixture(mode) as (case, directory, module):
                def disappear(path):
                    Path(path).unlink()
                    return dict(duration_seconds=15 if mode == "shorts" else 80, streams=[])
                with patch.object(shorts, "probe_clip", side_effect=disappear):
                    with self.assertRaises(OSError):
                        case.export(cache_only=True)
                self.assertEqual(len(list(directory.glob("*.mp4"))), 1 if mode == "shorts" else 0)

    def test_invalid_probe_no_writes(self):
        for mode in ("shorts", "longform"):
            with self.subTest(mode=mode), self.fixture(mode) as (case, directory, module):
                before = self.snapshot(case.root)
                with patch.object(shorts, "probe_clip", side_effect=ValueError("Invalid streams")):
                    with self.assertRaises(ValueError):
                        case.export(cache_only=True)
                self.assertEqual(before, self.snapshot(case.root))

    def test_missing_output_directory_is_not_created(self):
        for mode in ("shorts", "longform"):
            with self.subTest(mode=mode), self.fixture(mode) as (case, directory, module):
                missing = case.root/"absent"
                with self.assertRaises(OSError):
                    if mode == "shorts":
                        shorts.export_shorts(case.video, case.path, top_k=2,
                                             output_root=missing, cache_only=True)
                    else:
                        longform.export_longform(case.video, case.path,
                                                 output_root=missing, cache_only=True)
                self.assertFalse(missing.exists())

    def test_changed_longform_configuration_rejected(self):
        with self.fixture("longform") as (case, directory, module):
            before = self.snapshot(case.root)
            with self.assertRaisesRegex(ValueError, "stale"):
                case.export(cache_only=True, merge_gap=0)
            self.assertEqual(before, self.snapshot(case.root))

    def test_api_conflicts(self):
        for exporter in (shorts.export_shorts, longform.export_longform):
            for flag in ("force", "dry_run"):
                with self.subTest(exporter=exporter, flag=flag), self.assertRaisesRegex(ValueError, "conflicts"):
                    exporter("missing.mp4", "missing.json", cache_only=True, **{flag: True})

    def test_cli_conflicts(self):
        for main in (shorts.main, longform.main, pipeline.main):
            for flag in ("--force", "--dry-run"):
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                    main(["missing.mp4", "--analysis", "missing.json", "--cache-only", flag])
                self.assertEqual(raised.exception.code, 2)

    def test_pipeline_forwarding_partial_failure(self):
        with patch.object(pipeline, "shorts_main", return_value=1) as short,              patch.object(pipeline, "longform_main", return_value=0) as long,              contextlib.redirect_stdout(io.StringIO()) as output:
            result = pipeline.main(["video.mp4", "--analysis", "analysis.json", "--cache-only"])
        self.assertEqual(result, 1)
        for mock in (short, long):
            self.assertEqual(mock.call_args.args[0][-1], "--cache-only")
            self.assertNotIn("--force", mock.call_args.args[0])
        self.assertIn("partial failure", output.getvalue())

    def test_exporter_cli_forwarding(self):
        for module, name in ((shorts, "export_shorts"), (longform, "export_longform")):
            with patch.object(module, name, side_effect=ValueError("fixture rejection")) as call,                  contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                module.main(["video.mp4", "--analysis", "analysis.json", "--cache-only"])
            self.assertEqual(raised.exception.code, 1)
            self.assertTrue(call.call_args.kwargs["cache_only"])


if __name__ == "__main__":
    unittest.main()
