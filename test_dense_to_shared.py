"""Integration contract tests; synthetic measurements, no media/model execution."""
from contextlib import ExitStack, redirect_stdout, redirect_stderr
from copy import deepcopy
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import dense_to_shared as integration
import dense_observations as dense
import export_shorts
import export_longform
from shared_analysis import create_analysis, signal, load_analysis
from source_identity import file_identity, canonical
from test_observation_persistence import fixture
from timeline_query import save_query
import timeline_query


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.video = self.root / "video.mp4"
        self.video.write_bytes(b"synthetic source bytes")
        self.cache = self.root / "dense.json"
        self.output = self.root / "shared.json"
        self.full = fixture()
        checksum, size = file_identity(self.video)
        self.full["source_identity"].update(digest=checksum, size_bytes=size)
        self.full["source_identity"]["media"]["duration_seconds"] = 80
        self.full["source_video"].update(path=str(self.video), sha256=checksum,
                                         size_bytes=size, duration_seconds=80)
        self.full["audio"].update(sample_count=80*16000,
            amplitude_rows=[dict(second=i, volume=0) for i in range(80)],
            score_rows=[dict(second=i, spike=0, score=0) for i in range(5,80)])
        self.motion = [dict(second=i, score=0, normalized_score=0) for i in range(80)]
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(dense, "recipe", return_value=dict(version=1)))
        self.extract = self.stack.enter_context(patch.object(dense.persistence, "collect_observations", return_value=self.full))
        self.motion_call = self.stack.enter_context(patch.object(dense.motion, "analyze_motion", return_value=self.motion))
        self.stack.enter_context(patch.object(dense, "probe_format_streams", return_value=dict(streams=[])))

    def generate(self, semantic=None):
        return integration.generate(self.video, self.cache, self.output, semantic)

    def test_fresh_generation(self):
        result, status = self.generate()
        self.assertEqual(status, "created")
        self.assertEqual(load_analysis(self.output), result)
        self.extract.assert_called_once()
        self.motion_call.assert_called_once()
        self.assertEqual(result["source_video"]["sha256"], file_identity(self.video)[0])

    def test_cache_reuse_no_extraction_or_cache_write(self):
        first, _ = self.generate()
        before = self.cache.read_bytes(), self.cache.stat().st_mtime_ns
        self.output = self.root / "second.json"
        self.extract.side_effect = AssertionError("No extraction on reuse")
        self.motion_call.side_effect = AssertionError("No motion on reuse")
        second, status = self.generate()
        self.assertEqual(status, "reused")
        self.assertEqual(canonical(first), canonical(second))
        self.assertEqual(before, (self.cache.read_bytes(), self.cache.stat().st_mtime_ns))

    def test_stale_source_rejected_without_repair(self):
        self.generate()
        before = self.cache.read_bytes()
        self.video.write_bytes(b"changed source")
        self.output = self.root / "second.json"
        with self.assertRaisesRegex(ValueError, "Stale cache"):
            self.generate()
        self.assertFalse(self.output.exists())
        self.assertEqual(self.cache.read_bytes(), before)
        self.extract.assert_called_once()

    def test_stale_recipe_rejected(self):
        self.generate()
        self.output = self.root / "second.json"
        with patch.object(dense, "recipe", return_value=dict(version=2)), self.assertRaisesRegex(ValueError, "Stale cache"):
            self.generate()
        self.assertFalse(self.output.exists())

    def test_silent_audio_preserves_stable_baseline(self):
        result, _ = self.generate()
        rows = result["candidate_windows"]["data"]
        self.assertEqual([r["second"] for r in rows], [5,20,35,50,65])
        self.assertEqual([r["score"] for r in rows], [0]*5)
        self.assertEqual(rows[0]["start"], 0)
        self.assertEqual(len(result["acoustic"]["audio_activity"]["data"]), 80)

    def test_empty_scenes_and_missing_signals(self):
        self.full["scene_changes"]["data"] = []
        result, _ = self.generate()
        self.assertEqual(result["visual"]["scene_changes"]["status"], "analyzed")
        self.assertEqual(result["visual"]["scene_changes"]["data"], [])
        self.assertEqual(result["visual"]["semantic_frames"]["status"], "not_analyzed")
        self.assertEqual(result["transcript"]["status"], "not_analyzed")

    def test_chronology_and_original_scores(self):
        self.full["audio"]["score_rows"] = [dict(second=i, spike=1, score=i) for i in reversed(range(5,80))]
        result, _ = self.generate()
        self.assertEqual([r["second"] for r in result["candidate_windows"]["data"]], [19,34,49,64,79])
        self.assertEqual(result["candidate_windows"]["data"][-1]["end"], 80)
        audio = result["acoustic"]["audio_activity"]["data"]
        self.assertEqual([r["second"] for r in audio], list(range(80)))
        self.assertNotIn("score", audio[0])
        self.assertEqual(audio[10]["score"], 10)
        self.assertEqual([r["time"] for r in result["visual"]["scene_changes"]["data"]], [1,1,6])

    def test_insufficient_candidates_never_padded(self):
        self.full["audio"].update(sample_count=10*16000,
            amplitude_rows=[dict(second=i, volume=0) for i in range(10)],
            score_rows=[dict(second=i, spike=0, score=0) for i in range(5,10)])
        with self.assertRaisesRegex(ValueError, "found 1"):
            self.generate()
        self.assertFalse(self.output.exists())
        self.assertTrue(self.cache.exists())

    def test_duplicate_timestamps_rejected(self):
        self.full["audio"]["score_rows"][-1] = deepcopy(self.full["audio"]["score_rows"][0])
        with self.assertRaisesRegex(ValueError, "cover all producer chunks"):
            self.generate()
        self.assertFalse(self.output.exists())

    def test_wrong_collector_source_rejected(self):
        self.full["source_identity"]["digest"] = "a"*64
        self.full["source_video"]["sha256"] = "a"*64
        with self.assertRaisesRegex(ValueError, "Source changed"):
            self.generate()
        self.assertFalse(self.output.exists())

    def test_exporter_planning_compatibility(self):
        result, _ = self.generate()
        with patch.object(export_shorts, "probe_media", return_value=result["source_video"]):
            _, _, short = export_shorts.plan_export(self.video, self.output, output_root=self.root / "exports")
            _, _, long = export_longform.prepare_plan(self.video, self.output, output_root=self.root / "exports")
        self.assertEqual(len(short["clips"]), 5)
        self.assertEqual(long["planning"]["candidate_anchors"], [5,20,35,50,65])
        self.assertFalse((self.root / "exports").exists())

    def semantics(self, rows):
        result = create_analysis(self.full["source_video"])
        result["visual"]["semantic_frames"] = signal(rows, dict(
            model_id="openai/clip-vit-base-patch32", model_revision="test-fixture",
            video_sha256=self.full["source_video"]["sha256"], duration=80))
        path = self.root / "semantics.json"
        save_query(result, path)
        return path

    def test_clip_only_optional_evidence_and_empty_status(self):
        path = self.semantics([])
        before = path.read_bytes(), path.stat().st_mtime_ns
        result, _ = self.generate(path)
        self.assertEqual(result["visual"]["semantic_frames"]["status"], "analyzed")
        self.assertEqual(before, (path.read_bytes(), path.stat().st_mtime_ns))
        self.output = self.root / "second.json"
        with self.assertRaisesRegex(ValueError, "Stale visual"):
            self.generate()

    def test_clip_rows_preserved(self):
        rows = [dict(timestamp=3, label="unconfirmed hypothesis")]
        result, _ = self.generate(self.semantics(rows))
        self.assertEqual(result["visual"]["semantic_frames"]["data"], rows)
        self.assertEqual(result["visual"]["semantic_frames"]["provenance"]["model_revision"], "test-fixture")

    def test_wrong_semantic_identity(self):
        path = self.semantics([])
        data = load_analysis(path)
        data["source_video"]["sha256"] = "b"*64
        path.write_bytes(canonical(data))
        with self.assertRaises(ValueError):
            self.generate(path)
        self.assertFalse(self.output.exists())

    def test_existing_output_rejected_before_collection(self):
        self.output.write_bytes(b"untouched")
        with self.assertRaises(FileExistsError):
            self.generate()
        self.extract.assert_not_called()
        self.assertEqual(self.output.read_bytes(), b"untouched")

    def test_aliases_rejected_before_collection(self):
        for target in (self.video, self.cache):
            with self.subTest(target=target), self.assertRaises(ValueError):
                integration.generate(self.video, self.cache, target)
        self.extract.assert_not_called()

    def test_hardlink_input_alias_rejected(self):
        os.link(self.video, self.cache)
        with self.assertRaises(ValueError):
            self.generate()
        self.extract.assert_not_called()

    def test_source_change_before_publication(self):
        original = integration.adapt
        def change(*args):
            result = original(*args)
            self.video.write_bytes(b"changed during adaptation")
            return result
        with patch.object(integration, "adapt", side_effect=change), self.assertRaisesRegex(ValueError, "Source identity"):
            self.generate()
        self.assertFalse(self.output.exists())

    def test_cache_change_before_publication(self):
        original = integration.adapt
        def change(*args):
            result = original(*args)
            self.cache.write_text("{}")
            return result
        with patch.object(integration, "adapt", side_effect=change), self.assertRaisesRegex(ValueError, "Cache or producer"):
            self.generate()
        self.assertFalse(self.output.exists())

    def test_atomic_destination_race_does_not_replace(self):
        original = os.link
        def race(src, dst, *args, **kwargs):
            if Path(dst) == self.output:
                self.assertTrue(Path(src).read_text().endswith("\n"))
                self.output.write_bytes(b"concurrent owner")
            return original(src, dst, *args, **kwargs)
        with patch.object(timeline_query.os, "link", side_effect=race), self.assertRaises(FileExistsError):
            self.generate()
        self.assertEqual(self.output.read_bytes(), b"concurrent owner")
        self.assertEqual(list(self.root.glob(".query-*")), [])

    def test_cli_success_and_failure(self):
        args = [str(self.video), "--dense-cache", str(self.cache), "--analysis-output", str(self.output)]
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(integration.main(args), 0)
            self.assertEqual(integration.main(args), 1)


if __name__ == "__main__":
    unittest.main()
