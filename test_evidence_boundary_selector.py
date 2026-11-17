"""Synthetic timing tests; no human benchmark access during prediction."""
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import evidence_boundary_selector as selector
import gameplay_boundary_evaluation as evaluation
import clip_boundary_experiment as boundary
from shared_analysis import create_analysis,signal


def fixture():
    source=dict(path="fixture.mp4",sha256="a"*64,duration_seconds=100,width=160,height=90,size_bytes=1)
    a=create_analysis(source)
    a["candidate_windows"]=signal([dict(start=5+15*i,end=15+15*i,second=10+15*i,score=i) for i in range(5)],
                                 dict(detector="Audio-only",variant="fixed",k=5))
    a["transcript"]=signal([dict(start=4,end=6,text="one"),dict(start=17,end=19,text="two")],
        dict(backend="faster-whisper",model_id="synthetic-test",model_revision="fixture",
             source_sha256="a"*64,source_duration_seconds=100))
    p=evaluation.build_plan(a,source,experiment=boundary.build_plan(a,source))
    return p,a


class SelectorTests(unittest.TestCase):
    def test_scores_and_unique_selection(self):
        p,a=fixture(); result=selector.predict(p,a)
        row=result["candidates"][0]
        self.assertEqual([r["score"] for r in row["variants"]],[-1,0,-2,-1])
        self.assertEqual(row["selected_label"],"earlier_start")

    def test_deterministic_no_mutation(self):
        p,a=fixture(); before=deepcopy((p,a))
        self.assertEqual(selector.predict(p,a),selector.predict(p,a))
        self.assertEqual(before,(p,a))

    def test_missing_evidence(self):
        p,a=fixture(); a["transcript"]=signal()
        r=selector.predict(p,a)
        self.assertTrue(all(c["status"]=="abstained" for c in r["candidates"]))
        self.assertTrue(all(v["score"] is None for c in r["candidates"] for v in c["variants"]))

    def test_analyzed_empty(self):
        p,a=fixture(); a["transcript"]["data"]=[]
        self.assertEqual(selector.predict(p,a)["machine_evidence"]["status"],"analyzed")
        self.assertTrue(all(c["selected_label"] is None for c in selector.predict(p,a)["candidates"]))

    def test_source_identity(self):
        p,a=fixture(); a["source_video"]["sha256"]="b"*64
        with self.assertRaises(ValueError):selector.predict(p,a)

    def test_timestamp_and_provenance_mismatch(self):
        for mode in ("bounds","order","duration","digest"):
            p,a=fixture()
            if mode=="bounds":a["transcript"]["data"][0]["start"]=-1
            elif mode=="order":a["transcript"]["data"].reverse()
            elif mode=="duration":a["transcript"]["provenance"]["source_duration_seconds"]=101
            else:a["transcript"]["provenance"]["source_sha256"]="b"*64
            with self.subTest(mode=mode),self.assertRaises(ValueError):selector.predict(p,a)

    def test_duplicate_variant(self):
        p,a=fixture(); p["candidates"][0]["variants"][1]=deepcopy(p["candidates"][0]["variants"][0])
        with self.assertRaises(ValueError):selector.predict(p,a)

    def test_stable_tie_no_original_fallback(self):
        p,a=fixture(); a["transcript"]["data"]=[dict(start=0,end=99,text="long utterance")]
        r=selector.predict(p,a)["candidates"][0]
        self.assertIsNone(r["selected_label"])
        self.assertEqual(r["tied_best_labels"],["original","earlier_start","later_end","both"])

    def test_exact_endpoints_not_cut(self):
        p,a=fixture(); a["transcript"]["data"]=[dict(start=5,end=15,text="exact")]
        r=selector.predict(p,a)["candidates"][0]
        self.assertEqual(r["variants"][0]["score"],0)
        self.assertIsNone(r["selected_label"])

    def test_no_label_files_or_inference_during_prediction(self):
        p,a=fixture()
        with patch("pathlib.Path.open",side_effect=AssertionError("No file reads")),patch(
                "subprocess.run",side_effect=AssertionError("No inference")):
            selector.predict(p,a)

    def test_human_proposals_rejected_before_validation(self):
        p,a=fixture(); p["inputs"]["proposals"]={"human":"poison"}
        with patch.object(selector,"validate_plan",side_effect=AssertionError("Must reject first")),self.assertRaises(ValueError):
            selector.predict(p,a)

    def test_irrelevant_machine_scores_do_not_change_prediction(self):
        p,a=fixture(); expected=selector.predict(p,a)
        a["language"]["humor"]=signal([dict(start=1,end=2,score=1)])
        self.assertEqual(expected,selector.predict(p,a))

    def test_evaluation_freeze_and_provisional(self):
        p,a=fixture(); called=[]
        original=selector.predict
        def predict(*args):
            called.append("prediction")
            return original(*args)
        def load(path):
            self.assertEqual(called,["prediction"])
            return dict(plan_id=p["plan_id"],human_preferences=[
                dict(candidate_index=i,variant="earlier" if i==0 else "original",provisional=i==2) for i in range(5)])
        with patch.object(selector,"predict",side_effect=predict),patch("human_boundary_benchmark.load_benchmark",side_effect=load):
            r=selector.evaluate(p,a,Path("unused"))
        self.assertEqual(r["definitive_counts"],dict(agreement=1,disagreement=0,abstention=3))
        self.assertEqual(r["original_baseline"]["agreements"],3)
        self.assertTrue(r["comparison"][2]["provisional"])

    def test_evaluation_identity_conflict(self):
        p,a=fixture()
        with patch("human_boundary_benchmark.load_benchmark",return_value=dict(plan_id="wrong")),self.assertRaises(ValueError):
            selector.evaluate(p,a,Path("unused"))

    def test_cli_predict_no_writes(self):
        p,a=fixture()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); pp=root/"plan.json"; aa=root/"analysis.json"
            pp.write_text(json.dumps(p));aa.write_text(json.dumps(a))
            before={f.name:(f.read_bytes(),f.stat().st_mtime_ns) for f in root.iterdir()}
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(selector.main(["predict","--plan",str(pp),"--analysis",str(aa)]),0)
            self.assertEqual(before,{f.name:(f.read_bytes(),f.stat().st_mtime_ns) for f in root.iterdir()})


if __name__=="__main__":
    unittest.main()
