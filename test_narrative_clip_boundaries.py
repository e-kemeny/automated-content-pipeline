"""Synthetic planning fixtures only: no inference, OCR or media processing."""
import contextlib
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import narrative_clip_boundaries as planner
from gameplay_events import create_template
from test_gameplay_events import analysis_fixture, add_event
from multimodal_timeline import build_timeline
from multimodal_event_fusion import fuse_events
from transcript_event_recognition import recognize_events


class NarrativeTests(unittest.TestCase):
    def setUp(self):
        self.analysis = analysis_fixture()
        self.annotations = create_template(self.analysis)

    def event(self, start, end, **kwargs):
        e = add_event(self.annotations, start=start, end=end, precision="exact_interval", **kwargs)
        e["certainty"] = "certain"
        return e

    def plan(self, **kwargs):
        return planner.build_plan(self.analysis, annotations=self.annotations, **kwargs)

    def test_event_near_start(self):
        self.event(1, 4)
        row = self.plan()["candidates"][0]
        self.assertEqual(row["proposed"], dict(start=1,end=10,duration=9))
        self.assertEqual(row["status"], "evidence_supported")

    def test_event_near_end(self):
        self.event(8, 12)
        self.assertEqual(self.plan()["candidates"][0]["proposed"]["end"], 12)

    def test_complete_event(self):
        self.event(4, 8)
        row = self.plan()["candidates"][0]
        self.assertFalse(row["changed"])
        self.assertEqual(row["status"], "evidence_supported")

    def test_uncertain_clip_point_or_missing_timing(self):
        for precision,start,end,certainty in (("clip_level",1,12,"certain"),
                ("exact_point",10,10,"certain"),("exact_interval",1,12,"uncertain"),
                ("exact_interval",1,12,None)):
            self.annotations = create_template(self.analysis)
            e = add_event(self.annotations,start=start,end=end,precision=precision)
            e["certainty"] = certainty
            row = self.plan()["candidates"][0]
            self.assertFalse(row["changed"])
            self.assertEqual(row["status"], "insufficient_evidence")
        del e["start_seconds"]
        with self.assertRaises(ValueError):
            self.plan()

    def test_baseline_and_scores_preserved(self):
        original = deepcopy(self.analysis)
        with patch("subprocess.run",side_effect=AssertionError("No processing")):
            result = self.plan()
        self.assertEqual(self.analysis, original)
        self.assertEqual([c["original_candidate"] for c in result["candidates"]],
                         original["candidate_windows"]["data"])
        self.assertEqual(result["candidate_provenance"],original["candidate_windows"]["provenance"])
        self.assertNotEqual(result["candidates"][0]["candidate_id"],result["candidates"][1]["candidate_id"])
        self.assertTrue(all(not c["changed"] for c in result["candidates"]))

    def test_unknown_game_generic_other_event(self):
        self.event(8,12)["event_type"] = "other"
        self.assertTrue(self.plan()["candidates"][0]["changed"])

    def test_multiple_unrelated_events_are_not_chained(self):
        self.event(1,4)
        self.event(8,12,event_id="second")["event_type"] = "game_victory"
        row = self.plan(heuristic_padding=3)["candidates"][0]
        self.assertFalse(row["changed"])
        self.assertEqual(row["status"], "insufficient_evidence")

    def test_nearby_nonoverlapping_event_ignored(self):
        self.event(11,12)
        self.assertFalse(self.plan()["candidates"][0]["changed"])

    def test_extension_crossing_other_event_blocked(self):
        self.event(8,14)
        self.event(11,12,event_id="unrelated",candidate=1)
        row = self.plan()["candidates"][0]
        self.assertFalse(row["changed"])
        self.assertIn("unrelated",row["blocked_by"])

    def test_limits_reject_partial_event_extension(self):
        self.event(8,16)
        for kwargs in (dict(max_extension=2),dict(max_duration=10)):
            row = self.plan(**kwargs)["candidates"][0]
            self.assertFalse(row["changed"])
            self.assertEqual(row["status"],"insufficient_evidence")

    def test_invalid_limits_and_incompatible_baseline(self):
        for kwargs in (dict(min_duration=9),dict(max_duration=7),dict(min_duration=0),
                       dict(max_extension=-1),dict(max_duration=float("nan")),
                       dict(heuristic_padding=11),dict(heuristic_padding=True)):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):
                self.plan(**kwargs)

    def test_heuristic_clamps_to_video(self):
        row = self.plan(heuristic_padding=10)["candidates"][0]
        self.assertEqual(row["proposed"],dict(start=0,end=20,duration=20))
        self.assertEqual(row["status"],"heuristic_only")

    def test_conflicting_annotation_identity_or_candidates(self):
        other = deepcopy(self.analysis)
        other["source_video"]["sha256"] = "b"*64
        self.annotations = create_template(other)
        with self.assertRaises(ValueError):
            self.plan()
        other = deepcopy(self.analysis)
        other["candidate_windows"]["data"][0]["score"] = 999
        self.annotations = create_template(other)
        with self.assertRaises(ValueError):
            self.plan()

    def test_timeline_context_and_identity(self):
        timeline = build_timeline(analysis=self.analysis)
        row = self.plan(timeline=timeline)
        self.assertIsNotNone(row["timeline_context"])
        self.assertFalse(row["candidates"][0]["changed"])
        other = deepcopy(self.analysis)
        other["source_video"]["sha256"] = "b"*64
        with self.assertRaises(ValueError):
            self.plan(timeline=build_timeline(analysis=other))

    def test_fusion_is_context_not_exact_timing(self):
        timeline = build_timeline(analysis=self.analysis)
        fusion = fuse_events(transcript=recognize_events(timeline),timeline=timeline)
        result = self.plan(fusion=fusion)
        self.assertEqual(result["inputs"]["fusion"],fusion)
        self.assertFalse(result["candidates"][0]["changed"])
        fusion["schema_version"] = 2
        with self.assertRaises(ValueError):
            self.plan(fusion=fusion)

    def test_speech_hypothesis_cannot_supply_event_boundary(self):
        self.analysis["transcript"]["data"] = [dict(start=8,end=12,text="We won the game.")]
        timeline = build_timeline(analysis=self.analysis)
        fusion = fuse_events(transcript=recognize_events(timeline),timeline=timeline)
        self.assertEqual(len(fusion["groups"]),1)
        result = self.plan(fusion=fusion)
        self.assertFalse(result["candidates"][0]["changed"])
        self.assertIsNone(fusion["groups"][0]["gameplay_event_interval"])

    def test_fused_group_blocks_padding_without_becoming_boundary(self):
        self.analysis["transcript"]["data"] = [dict(start=11,end=12,text="We won the game.")]
        timeline = build_timeline(analysis=self.analysis)
        fusion = fuse_events(transcript=recognize_events(timeline),timeline=timeline)
        result = self.plan(fusion=fusion,heuristic_padding=3)
        row = result["candidates"][0]
        self.assertFalse(row["changed"])
        self.assertEqual(row["blocked_by"],[fusion["groups"][0]["group_id"]])

    def test_fusion_identity_conflict(self):
        other = deepcopy(self.analysis)
        other["source_video"]["sha256"] = "b"*64
        fusion = fuse_events(timeline=build_timeline(analysis=other))
        with self.assertRaises(ValueError):
            self.plan(fusion=fusion)

    def test_empty_candidates_rejected(self):
        self.analysis["candidate_windows"]["data"] = []
        with self.assertRaises(ValueError):
            planner.build_plan(self.analysis)

    def test_deterministic_and_missing_inputs(self):
        self.assertEqual(self.plan(),self.plan())
        result = planner.build_plan(self.analysis)
        self.assertEqual(result["availability"]["fusion"],"missing")
        self.assertEqual(result["availability"]["annotations"],"missing")

    def test_atomic_output_no_overwrite_and_failure_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, output = root/"analysis.json",root/"plan.json"
            source.write_text(json.dumps(self.analysis),encoding="utf-8")
            original = source.read_bytes(),source.stat().st_mtime_ns
            args = ["--analysis",str(source),"--output",str(output)]
            with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                with patch("timeline_query.os.link",side_effect=OSError("fixture failure")):
                    self.assertEqual(planner.main(args),1)
                self.assertFalse(output.exists())
                self.assertEqual(list(root.glob(".query-*")),[])
                self.assertEqual(planner.main(args),0)
                saved = output.read_bytes(),output.stat().st_mtime_ns
                self.assertEqual(planner.main(args),1)
                self.assertEqual(saved,(output.read_bytes(),output.stat().st_mtime_ns))
                self.assertEqual(planner.main(["--analysis",str(source),"--output",str(source)]),1)
            self.assertEqual(original,(source.read_bytes(),source.stat().st_mtime_ns))
            self.assertEqual(json.loads(saved[0]),planner.build_plan(self.analysis))


if __name__ == "__main__":
    unittest.main()
