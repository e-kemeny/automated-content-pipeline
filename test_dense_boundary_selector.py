"""Synthetic V2 fixtures; no benchmark labels used in scoring tests."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import dense_boundary_selector as selector
import dense_observations as dense
from test_evidence_boundary_selector import fixture as plan_fixture
from test_observation_persistence import fixture as full_fixture
from highlight_evaluation import publish
from source_identity import canonical


def fixture():
    plan,analysis=plan_fixture()
    full=full_fixture()
    full["source_identity"]=deepcopy(plan["source_identity"])
    full["source_video"]=dict(analysis["source_video"])
    full["audio"]["sample_count"]=1600000
    full["audio"]["amplitude_rows"]=[dict(second=i,volume=i+1) for i in range(100)]
    full["audio"]["score_rows"]=[dict(second=i,spike=0,score=1) for i in range(5,100)]
    full["scene_changes"]["data"]=[]
    motion=[dict(second=i,score=(i+1)/100,normalized_score=(i+1)/100) for i in range(100)]
    streams=[dict(codec_type=k,start_time="0",time_base="1/100") for k in ("audio","video")]
    cache=dense.build(full,motion,dict(status="not_analyzed",data=[],provenance={}),streams,{})
    audit=dict(source_identity=deepcopy(plan["source_identity"]),first_decoded_seconds=dict(audio=0,video=0))
    return plan,cache,analysis,audit


class DenseSelectorTests(unittest.TestCase):
    def test_formula(self):
        r=selector.cut_features(2,{1:2,2:4},{1:.3,2:.5},[],4,.5,True)
        self.assertAlmostEqual(r["penalty"],.55)

    def test_scene_discontinuity(self):
        r=selector.cut_features(2,{1:2,2:4},{1:.3,2:.5},[dict(time=2.5,score=12)],4,.5,True)
        self.assertEqual(r["penalty"],0)
        self.assertTrue(r["scene_near"])

    def test_missing_samples(self):
        r=selector.cut_features(2,{1:2},{1:.3,2:.5},[],4,.5,True)
        self.assertIsNone(r["penalty"])

    def test_fractional_boundary_abstains(self):
        r=selector.cut_features(2.2,{1:2,2:4},{1:.3,2:.5},[],4,.5,True)
        self.assertIsNone(r["penalty"])

    def test_zero_modality_abstains(self):
        self.assertIsNone(selector.cut_features(2,{1:0,2:0},{1:.3,2:.5},[],0,.5,True)["penalty"])

    def test_determinism_and_no_mutation(self):
        args=fixture(); before=deepcopy(args)
        self.assertEqual(canonical(selector.predict(*args)),canonical(selector.predict(*args)))
        self.assertEqual(args,before)

    def test_clock_offset_abstains(self):
        p,c,a,proof=fixture();proof["first_decoded_seconds"]["audio"]=.1
        r=selector.predict(p,c,a,proof)
        self.assertTrue(all(x["selected_label"] is None for x in r["candidates"]))

    def test_missing_timebase_abstains(self):
        p,c,a,proof=fixture()
        c["stream_metadata"][0].pop("time_base")
        c=dense.build(c["full_observations"],c["motion_rows"],c["visual"],c["stream_metadata"],c["recipe"])
        self.assertFalse(selector.predict(p,c,a,proof)["alignment_supported"])

    def test_source_identity_conflict(self):
        p,c,a,proof=fixture();proof["source_identity"]["digest"]="b"*64
        with self.assertRaises(ValueError):selector.predict(p,c,a,proof)

    def test_invalid_timestamps_rejected(self):
        p,c,a,proof=fixture();c["motion_rows"][0]["second"]=-1
        with self.assertRaises(ValueError):selector.predict(p,c,a,proof)

    def test_duration_neutral_ties(self):
        p,c,a,proof=fixture()
        for r in c["full_observations"]["audio"]["amplitude_rows"]:r["volume"]=1
        for r in c["motion_rows"]:r.update(score=1,normalized_score=1)
        c=dense.build(c["full_observations"],c["motion_rows"],c["visual"],c["stream_metadata"],c["recipe"])
        r=selector.predict(p,c,a,proof)
        self.assertTrue(all(x["selected_label"] is None for x in r["candidates"]))
        self.assertEqual(r["candidates"][0]["tied_best_labels"],["original","earlier_start","later_end","both"])
        self.assertEqual(len({v["score"] for v in r["candidates"][0]["variants"]}),1)

    def test_no_human_access_or_inference(self):
        args=fixture()
        with patch("pathlib.Path.open",side_effect=AssertionError("No files")),patch(
                "subprocess.run",side_effect=AssertionError("No inference")):
            selector.predict(*args)

    def test_v1_unchanged(self):
        p,c,a,proof=fixture();before=selector.v1.predict(p,a)
        self.assertEqual(selector.predict(p,c,a,proof)["v1_predictions"],before)
        self.assertEqual(selector.v1.predict(p,a),before)

    def test_persisted_required_before_labels(self):
        with tempfile.TemporaryDirectory() as d,patch("human_boundary_benchmark.load_benchmark",side_effect=AssertionError("No labels")):
            with self.assertRaises(FileNotFoundError):selector.evaluate_file(Path(d)/"missing",Path("unused"))

    def test_modified_freeze_rejected(self):
        r=selector.predict(*fixture());r["policy"]["audio_weight"]=1
        with self.assertRaises(ValueError):selector.validate_frozen(r)

    def test_evaluation_and_provisional(self):
        args=fixture();result=selector.predict(*args)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"frozen.json";publish(result,path,[])
            before=path.read_bytes(),path.stat().st_mtime_ns
            def load(_):
                self.assertTrue(path.exists())
                return dict(plan_id=result["plan_id"],human_preferences=[
                    dict(candidate_index=i,variant="original",provisional=i==2) for i in range(5)])
            with patch("human_boundary_benchmark.load_benchmark",side_effect=load):
                r=selector.evaluate_file(path,Path("unused"))
            self.assertEqual(r["counts"]["definitive"]["original"]["agreement"],4)
            self.assertEqual(r["counts"]["provisional"]["original"]["agreement"],1)
            self.assertEqual(before,(path.read_bytes(),path.stat().st_mtime_ns))
            with self.assertRaises(FileExistsError):publish(result,path,[])


if __name__=="__main__":
    unittest.main()
