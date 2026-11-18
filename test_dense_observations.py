"""Synthetic dense-cache tests; existing producer math remains unchanged."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import dense_observations as dense
from test_observation_persistence import fixture
from shared_analysis import create_analysis,signal
from source_identity import canonical
from timeline_query import save_query

def inputs():
    full=fixture()
    rows=[dict(second=i,score=i/10,normalized_score=i/6) for i in range(7)]
    visual=dict(status="not_analyzed",data=[],provenance={})
    return full,rows,visual,[],dict(version=1)


class DenseTests(unittest.TestCase):
    def test_counts_order_deltas_and_missing_visual(self):
        a=dense.build(*inputs())
        self.assertEqual(a["coverage"]["audio"]["count"],7)
        self.assertEqual(a["coverage"]["motion"]["count"],7)
        self.assertEqual(a["coverage"]["visual"]["status"],"not_analyzed")
        events=a["timeline"]["events"]
        self.assertEqual(len([e for e in events if e["event_type"]=="motion_activity_change"]),6)
        self.assertEqual([e["start_seconds"] for e in events],sorted(e["start_seconds"] for e in events))
        self.assertEqual(dense.validate(a),a)

    def test_deterministic_serialization(self):
        self.assertEqual(canonical(dense.build(*inputs())),canonical(dense.build(*inputs())))

    def test_invalid_motion_timing(self):
        for value in (-1,8,.5,True):
            args=list(inputs());args[1][0]["second"]=value
            with self.assertRaises(ValueError):dense.build(*args)

    def test_invalid_motion_values(self):
        for value in (float("nan"),-1,2):
            args=list(inputs());args[1][0]["score"]=value
            with self.assertRaises(ValueError):dense.build(*args)

    def test_empty_motion_not_fabricated(self):
        args=list(inputs());args[1]=[]
        with self.assertRaises(ValueError):dense.build(*args)

    def test_corrupt_cache(self):
        a=dense.build(*inputs());a["timeline"]["events"][0]["start_seconds"]=1
        with self.assertRaises(ValueError):dense.validate(a)

    def test_reuse_visual_and_identity(self):
        full=fixture()
        a=create_analysis(full["source_video"])
        a["visual"]["semantic_frames"]=signal([dict(timestamp=1,label="unconfirmed")],
            dict(model_id="openai/clip-vit-base-patch32",model_revision="fixture",
                 duration=7,video_sha256="a"*64))
        v=dense.visual_input(a,full["source_video"])
        self.assertEqual(v,a["visual"]["semantic_frames"])
        a["source_video"]["sha256"]="b"*64
        with self.assertRaises(ValueError):dense.visual_input(a,full["source_video"])

    def test_visual_timestamp_and_provenance(self):
        a=create_analysis(fixture()["source_video"])
        a["visual"]["semantic_frames"]=signal([dict(timestamp=8,label="x")])
        with self.assertRaises(ValueError):dense.visual_input(a,fixture()["source_video"])
        a["visual"]["semantic_frames"]["data"][0]["timestamp"]=1
        with self.assertRaises(ValueError):dense.visual_input(a,fixture()["source_video"])

    def test_boundary_neighborhood(self):
        a=dense.build(*inputs());r=dense.boundary_report(a,[3])[0]
        self.assertEqual([x["second"] for x in r["audio"]["before"]],[1,2])
        self.assertEqual(r["audio"]["mean_change"],0)
        self.assertAlmostEqual(r["motion"]["mean_change"],.25)
        with self.assertRaises(ValueError):dense.boundary_report(a,[9])

    def test_cache_hit_no_analysis_or_writes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);video=root/"v.mp4";video.write_bytes(b"fixture")
            out=root/"cache.json";a=dense.build(*inputs());save_query(a,out)
            before=out.read_bytes(),out.stat().st_mtime_ns
            with patch.object(dense,"file_identity",return_value=("a"*64,10)),patch.object(dense,"recipe",return_value=dict(version=1)),patch.object(
                dense.persistence,"collect_observations",side_effect=AssertionError("No analysis")),patch.object(
                dense.motion,"analyze_motion",side_effect=AssertionError("No motion")):
                reused,status=dense.collect(video,out)
            self.assertEqual(status,"reused")
            self.assertEqual(before,(out.read_bytes(),out.stat().st_mtime_ns))
            self.assertEqual(reused,a)

    def test_cache_invalidation_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);video=root/"v.mp4";video.write_bytes(b"fixture")
            out=root/"cache.json";save_query(dense.build(*inputs()),out)
            before=out.read_bytes()
            for identity,config in ((("b"*64,10),dict(version=1)),(("a"*64,10),dict(version=2))):
                with patch.object(dense,"file_identity",return_value=identity),patch.object(dense,"recipe",return_value=config),patch.object(
                    dense.persistence,"collect_observations",side_effect=AssertionError("No fallback")),self.assertRaises(ValueError):
                    dense.collect(video,out)
            self.assertEqual(before,out.read_bytes())

    def test_collect_delegates_once(self):
        full,rows,_,_,config=inputs()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);video=root/"v.mp4";video.write_bytes(b"fixture")
            with patch.object(dense,"file_identity",return_value=("a"*64,10)),patch.object(dense,"recipe",return_value=config),patch.object(
                dense.persistence,"collect_observations",return_value=full) as audio,patch.object(
                dense.motion,"analyze_motion",return_value=rows) as motion,patch.object(
                dense,"probe_format_streams",return_value=dict(streams=[])):
                _,status=dense.collect(video,root/"cache.json")
            self.assertEqual(status,"created");audio.assert_called_once();motion.assert_called_once()

    def test_missing_source(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):dense.collect(Path(d)/"missing",Path(d)/"out")


if __name__=="__main__":
    unittest.main()
