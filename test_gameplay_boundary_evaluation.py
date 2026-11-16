"""Offline evaluation fixtures: FFmpeg mocked, human ratings synthetic."""
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import gameplay_boundary_evaluation as evaluation
import clip_boundary_experiment as boundary
import narrative_clip_boundaries as narrative
from test_clip_boundary_experiment import fixture


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.analysis,self.actual = fixture()
        self.experiment = boundary.build_plan(self.analysis,self.actual)

    def plan(self, **kwargs):
        return evaluation.build_plan(self.analysis,self.actual,**kwargs)

    def test_original_only(self):
        p=self.plan()
        self.assertEqual(len(p["clips"]),2)
        self.assertTrue(all(c["narrative_status"]=="unavailable" for c in p["candidates"]))
        self.assertEqual([c["original_candidate"] for c in p["candidates"]],self.analysis["candidate_windows"]["data"])

    def test_valid_changed_narrative(self):
        proposals=narrative.build_plan(self.analysis,heuristic_padding=2)
        p=self.plan(proposals=proposals)
        self.assertEqual(len(p["clips"]),4)
        self.assertEqual(p["candidates"][0]["narrative_status"],"changed")
        self.assertEqual(p["candidates"][0]["variants"][1]["provenance"]["status"],"heuristic_only")

    def test_unchanged_narrative_deduplicates(self):
        p=self.plan(proposals=narrative.build_plan(self.analysis))
        self.assertEqual(len(p["clips"]),2)
        self.assertEqual(len(p["clips"][0]["references"]),2)
        report=evaluation.compare(p,evaluation.review_template(p))
        self.assertEqual(len(report["identical_to_original"]),2)
        self.assertEqual(report["pairs"],[])

    def test_global_duplicate_windows(self):
        row=deepcopy(self.analysis["candidate_windows"]["data"][0])
        self.analysis["candidate_windows"]["data"]=[row,deepcopy(row)]
        p=self.plan()
        self.assertEqual(len(p["clips"]),1)
        self.assertEqual(len(p["clips"][0]["references"]),2)
        self.assertNotEqual(p["candidates"][0]["candidate_id"],p["candidates"][1]["candidate_id"])

    def test_zero_offsets_keep_all_labels(self):
        experiment=boundary.build_plan(self.analysis,self.actual,0,0)
        p=self.plan(experiment=experiment)
        self.assertEqual(len(p["clips"]),2)
        self.assertEqual(len(p["clips"][0]["references"]),4)

    def test_invalid_mapping_and_identity(self):
        for mutate in ("index","source","duration"):
            e=deepcopy(self.experiment)
            if mutate=="index": e["candidates"][0]["candidate_index"]=4
            elif mutate=="source": e["source_video"]["sha256"]="b"*64
            else: e["candidates"][0]["variants"][1]["duration"]=-1
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):
                self.plan(experiment=e)

    def test_invalid_narrative(self):
        n=narrative.build_plan(self.analysis)
        n["candidates"][0]["proposed"]["end"]=99
        with self.assertRaises(ValueError):
            self.plan(proposals=n)

    def test_determinism_and_plan_tamper(self):
        p=self.plan(experiment=self.experiment)
        self.assertEqual(p,self.plan(experiment=self.experiment))
        p["clips"][0]["start"]=-1
        with self.assertRaises(ValueError):
            evaluation.validate_plan(p)

    def test_blank_reviews(self):
        p=self.plan(experiment=self.experiment)
        r=evaluation.review_template(p)
        self.assertTrue(all(v is None for c in r["clips"] for v in c["ratings"].values()))
        report=evaluation.compare(p,r)
        self.assertEqual(report["valid_rated_pairs"],0)
        self.assertEqual(report["unrated_or_partial_pairs"],6)
        self.assertIsNone(report["metrics"]["pacing"]["mean_paired_difference"])

    def test_partial_and_full_pairs(self):
        p=self.plan(experiment=self.experiment)
        r=evaluation.review_template(p)
        r["clips"][0]["ratings"]={m:3 for m in evaluation.METRICS}
        r["clips"][1]["ratings"]["pacing"]=5
        report=evaluation.compare(p,r)
        self.assertEqual(report["metrics"]["pacing"]["valid_rated_pairs"],1)
        self.assertEqual(report["metrics"]["pacing"]["mean_paired_difference"],2)
        self.assertEqual(report["valid_rated_pairs"],0)
        r["clips"][1]["ratings"]={m:4 for m in evaluation.METRICS}
        report=evaluation.compare(p,r)
        self.assertEqual(report["valid_rated_pairs"],1)
        self.assertTrue(report["incomplete_evaluations"])

    def test_invalid_reviews(self):
        p=self.plan()
        for value in (0,6,True,"4"):
            r=evaluation.review_template(p)
            r["clips"][0]["ratings"]["pacing"]=value
            with self.assertRaises(ValueError): evaluation.compare(p,r)
        r=evaluation.review_template(p)
        r["clips"][0]["clip_id"]="wrong"
        with self.assertRaises(ValueError): evaluation.compare(p,r)

    def test_atomic_cli_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            source=root/"plan.json"
            source.write_text(json.dumps(self.plan()),encoding="utf-8")
            target=root/"reviews.json"
            args=["review-template","--plan",str(source),"--output",str(target)]
            with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                with patch("timeline_query.os.link",side_effect=OSError("fixture")):
                    self.assertEqual(evaluation.main(args),1)
                self.assertFalse(target.exists())
                self.assertEqual(evaluation.main(args),0)
                before=target.read_bytes(),target.stat().st_mtime_ns
                self.assertEqual(evaluation.main(args),1)
                self.assertEqual(before,(target.read_bytes(),target.stat().st_mtime_ns))
                self.assertEqual(evaluation.main(["review-template","--plan",str(source),"--output",str(source)]),1)

    def test_export_isolation_and_missing_video(self):
        p=self.plan()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with self.assertRaises(ValueError):
                evaluation.export_plan(p,root/"missing",root/"new")
            with patch.object(boundary,"verify_video",side_effect=AssertionError("must reject before probe")):
                for dest in (root,evaluation.ROOT/"output"/"my_recording"/"new"):
                    with self.assertRaises(ValueError):
                        evaluation.export_plan(p,root/"missing",dest)

    def test_export_reuses_encoder(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); video=root/"video.mp4"; video.write_bytes(b"fixture")
            def encode(video,target,start,duration):
                target.write_bytes(b"encoded")
                return dict(verification={},duration_error_seconds=0,sha256="a"*64)
            with patch.object(boundary,"verify_video",return_value=self.actual),patch.object(boundary,"encode_clip",side_effect=encode) as encoder:
                result=evaluation.export_plan(self.plan(),video,root/"new")
            self.assertEqual(encoder.call_count,2)
            self.assertEqual(result["status"],"complete")
            self.assertTrue((root/"new"/"reviews.json").is_file())

    def test_missing_ffmpeg_or_partial_failure_no_publication(self):
        for error in (FileNotFoundError("ffmpeg"),RuntimeError("partial failure")):
            with tempfile.TemporaryDirectory() as d:
                root=Path(d); video=root/"video.mp4"; video.write_bytes(b"fixture")
                with patch.object(boundary,"verify_video",return_value=self.actual),patch.object(boundary,"encode_clip",side_effect=[dict(verification={},duration_error_seconds=0,sha256="a"*64),error]):
                    with self.assertRaises(type(error)):
                        evaluation.export_plan(self.plan(),video,root/"new")
                self.assertFalse((root/"new").exists())
                self.assertFalse(list(root.glob(".evaluation-stage-*")))


if __name__=="__main__":
    unittest.main()
