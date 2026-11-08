"""Synthetic boundary-plan, human-review and isolated-export tests."""
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import clip_boundary_experiment as experiment
from shared_analysis import create_analysis,signal


def fixture():
    a=create_analysis(dict(path="fixture.mp4",duration_seconds=30,sha256="a"*64))
    a["candidate_windows"]=signal([dict(start=1,end=10,second=5,score=3),dict(start=20,end=29,second=25,score=2)],
                                 dict(detector="Audio-only",variant="fixed",k=2))
    return a,dict(a["source_video"],width=160,height=90,fps=10,size_bytes=7)


class PlanTests(unittest.TestCase):
    def test_original_preservation_offsets_and_clamps(self):
        a,actual=fixture()
        original=deepcopy(a)
        p=experiment.build_plan(a,actual)
        self.assertEqual(a,original)
        self.assertEqual(p["candidates"][0]["original_candidate"],a["candidate_windows"]["data"][0])
        first=p["candidates"][0]["variants"]
        self.assertEqual([(v["start"],v["end"]) for v in first],[(1,10),(0,10),(1,13),(0,13)])
        self.assertEqual(first[1]["applied_start_offset"],-1)
        last=p["candidates"][1]["variants"][-1]
        self.assertEqual((last["start"],last["end"],last["applied_end_offset"]),(17,30,1))

    def test_unknown_duration_identity_and_conflicts(self):
        for field in ("duration_seconds","sha256"):
            a,actual=fixture()
            del a["source_video"][field]
            with self.subTest(field=field),self.assertRaises(ValueError):
                experiment.build_plan(a,actual)
        a,actual=fixture()
        for field,value in (("duration_seconds",31),("sha256","b"*64)):
            with self.subTest(field=field),self.assertRaises(ValueError):
                experiment.build_plan(a,dict(actual,**{field:value}))

    def test_offsets_and_invalid_original_window(self):
        a,actual=fixture()
        for value in (-1,11,True,float("inf")):
            with self.subTest(value=value),self.assertRaises(ValueError):
                experiment.build_plan(a,actual,value,3)
        a["candidate_windows"]["data"][0]=dict(start=1,end=1)
        with self.assertRaises(ValueError):
            experiment.build_plan(a,actual)

    def test_duplicates_order_stable_ids(self):
        a,actual=fixture()
        a["candidate_windows"]["data"]=[a["candidate_windows"]["data"][0]]*2
        p=experiment.build_plan(a,actual)
        self.assertEqual(p,experiment.build_plan(a,actual))
        self.assertNotEqual(p["candidates"][0]["candidate_id"],p["candidates"][1]["candidate_id"])
        q=experiment.build_plan(a,actual,1,1)
        self.assertNotEqual(p["candidates"][0]["variants"][2]["variant_id"],q["candidates"][0]["variants"][2]["variant_id"])

    def test_tampered_plans(self):
        for mode in ("schema","end","id","source","offset","order"):
            p=experiment.build_plan(*fixture())
            if mode=="schema": p["schema_version"]=2
            elif mode=="end": p["candidates"][0]["variants"][0]["end"]=100
            elif mode=="id": p["plan_id"]="bad"
            elif mode=="source": p["source_video"]["sha256"]="b"*64
            elif mode=="order": p["candidates"].reverse()
            else: p["offsets"]["seconds_after"]=5
            with self.subTest(mode=mode),self.assertRaises(ValueError):
                experiment.validate_plan(p)

    def test_null_reviews_and_no_baseline_copy(self):
        p=experiment.build_plan(*fixture())
        review=experiment.review_template(p)
        self.assertTrue(all(v["rating"] is None for r in review["candidates"] for v in r["variants"]))
        result=experiment.compare_reviews(p,review)
        self.assertEqual((result["variants_rated"],result["missing_ratings"],result["candidates_reviewed"]),(0,8,0))
        self.assertEqual(result["longer_duration_comparison"]["paired_comparisons"],0)

    def test_comparison_ties_deltas_notes_preferences(self):
        p=experiment.build_plan(*fixture())
        review=experiment.review_template(p)
        row=review["candidates"][0]
        row.update(preferred_variant="both",notes="Need the ending")
        for v,rating in zip(row["variants"],[3,3,4,5]): v["rating"]=rating
        result=experiment.compare_reviews(p,review)
        self.assertEqual(result["variants_rated"],4)
        self.assertEqual(result["candidates_reviewed"],1)
        self.assertEqual(result["candidates"][0]["preferred_variant"],"both")
        self.assertEqual(result["candidates"][0]["tied_variants"],[["original","earlier_start"]])
        self.assertEqual(result["longer_duration_comparison"],dict(better=2,worse=0,tied=1,paired_comparisons=3))
        self.assertEqual(result["candidates"][0]["notes"],"Need the ending")

    def test_unpaired_ratings_do_not_infer_preference(self):
        p=experiment.build_plan(*fixture())
        review=experiment.review_template(p)
        review["candidates"][0]["variants"][3]["rating"]=5
        result=experiment.compare_reviews(p,review)
        self.assertIsNone(result["candidates"][0]["preferred_variant"])
        self.assertIsNone(result["candidates"][0]["differences_from_original"][2]["rating_difference"])
        self.assertEqual(result["longer_duration_comparison"]["paired_comparisons"],0)

    def test_equal_durations_not_counted_as_longer(self):
        a,actual=fixture()
        p=experiment.build_plan(a,actual,0,0)
        review=experiment.review_template(p)
        for v in review["candidates"][0]["variants"]: v["rating"]=4
        self.assertEqual(experiment.compare_reviews(p,review)["longer_duration_comparison"]["paired_comparisons"],0)

    def test_bad_ratings_and_review_tampering(self):
        p=experiment.build_plan(*fixture())
        for rating in (0,6,True,4.0,"4"):
            review=experiment.review_template(p)
            review["candidates"][0]["variants"][0]["rating"]=rating
            with self.subTest(rating=rating),self.assertRaises(ValueError):
                experiment.compare_reviews(p,review)
        for mode in ("bounds","order","preferred","plan_id","notes"):
            review=experiment.review_template(p)
            if mode=="bounds": review["candidates"][0]["variants"][0]["start"]=2
            elif mode=="order": review["candidates"].reverse()
            elif mode=="preferred": review["candidates"][0]["preferred_variant"]="unknown"
            elif mode=="notes": review["candidates"][0]["notes"]=None
            else: review["plan_id"]="bad"
            with self.subTest(mode=mode),self.assertRaises(ValueError):
                experiment.compare_reviews(p,review)


class ExportTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.video=self.root/"source.mp4"
        self.video.write_bytes(b"fixture")
        self.analysis,self.actual=fixture()
        self.plan=experiment.build_plan(self.analysis,self.actual)
        self.plan_path=self.root/"plan.json"
        self.plan_path.write_text(json.dumps(self.plan))
        self.destination=self.root/"experiment"

    def encode(self,cmd,**kwargs):
        Path(cmd[-1]).write_bytes(b"encoded")
        self.duration=float(cmd[cmd.index("-t")+1])

    def probe(self,path):
        return dict(duration_seconds=self.duration,streams=[dict(codec_type="video",avg_frame_rate="10/1"),dict(codec_type="audio")])

    def test_live_identity_and_missing_source(self):
        with patch.object(experiment,"probe_media",return_value=deepcopy(self.actual)) as probe:
            result=experiment.verify_video(self.video,self.analysis["source_video"])
        probe.assert_called_once()
        self.assertEqual(result["sha256"],"a"*64)
        with patch.object(experiment,"probe_media",return_value=dict(self.actual,sha256="b"*64)),self.assertRaises(ValueError):
            experiment.verify_video(self.video,self.analysis["source_video"])
        with self.assertRaises(ValueError):
            experiment.verify_video(self.root/"missing",self.analysis["source_video"])

    def test_verified_export_unique_files_manifest(self):
        with patch.object(experiment,"verify_video",return_value=self.actual),patch.object(
                experiment.subprocess,"run",side_effect=self.encode) as run,patch.object(experiment,"probe_clip",side_effect=self.probe):
            result=experiment.export_plan(self.plan,self.video,self.destination)
        self.assertEqual(run.call_count,8)
        self.assertEqual(len(list(self.destination.glob("*.mp4"))),8)
        self.assertEqual(len({r["output_filename"] for r in result["clips"]}),8)
        self.assertEqual(result["status"],"complete")
        self.assertTrue((self.destination/"boundary_export_manifest.json").exists())
        self.assertFalse(list(self.root.glob(".boundary-stage-*")))

    def test_failed_encoding_cleans_stage(self):
        def fail(cmd,**kwargs):
            self.encode(cmd,**kwargs)
            raise subprocess.CalledProcessError(1,cmd)
        with patch.object(experiment,"verify_video",return_value=self.actual),patch.object(
                experiment.subprocess,"run",side_effect=fail),self.assertRaises(subprocess.CalledProcessError):
            experiment.export_plan(self.plan,self.video,self.destination)
        self.assertFalse(self.destination.exists())
        self.assertFalse(list(self.root.glob(".boundary-stage-*")))

    def test_failed_probe_no_final_export(self):
        with patch.object(experiment,"verify_video",return_value=self.actual),patch.object(
                experiment.subprocess,"run",side_effect=self.encode),patch.object(
                experiment,"probe_clip",side_effect=ValueError("no audio")),self.assertRaises(ValueError):
            experiment.export_plan(self.plan,self.video,self.destination)
        self.assertFalse(self.destination.exists())

    def test_export_isolation(self):
        self.destination.mkdir()
        sentinel=self.destination/"sentinel"
        sentinel.write_text("keep")
        for target in (self.destination,experiment.ROOT/"output"/"my_recording"/"new"):
            with self.subTest(target=target),patch.object(experiment,"verify_video",side_effect=AssertionError("no probe")),self.assertRaises(ValueError):
                experiment.export_plan(self.plan,self.video,target)
        self.assertEqual(sentinel.read_text(),"keep")

    def test_identity_conflict_before_encoding(self):
        with patch.object(experiment,"verify_video",return_value=dict(self.actual,sha256="b"*64)),patch.object(
                experiment.subprocess,"run",side_effect=AssertionError("no encoding")),self.assertRaises(ValueError):
            experiment.export_plan(self.plan,self.video,self.destination)
        self.assertFalse(self.destination.exists())

    def run_cli(self,args):
        out,err=io.StringIO(),io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            code=experiment.main(args)
        return code

    def test_all_offline_workflows(self):
        analysis=self.root/"analysis.json"
        analysis.write_text(json.dumps(self.analysis))
        planned=self.root/"planned.json"
        with patch.object(experiment,"verify_video",return_value=self.actual):
            self.assertEqual(self.run_cli(["plan","--analysis",str(analysis),"--video",str(self.video),"--output",str(planned)]),0)
        review=self.root/"review.json"
        report=self.root/"report.json"
        self.assertEqual(self.run_cli(["review-template","--plan",str(planned),"--output",str(review)]),0)
        before=review.read_bytes()
        self.assertEqual(self.run_cli(["compare","--plan",str(planned),"--reviews",str(review),"--output",str(report)]),0)
        self.assertEqual(before,review.read_bytes())
        self.assertEqual(json.loads(report.read_text())["variants_rated"],0)

    def test_atomic_failure_overwrite_protection(self):
        output=self.root/"review.json"
        args=["review-template","--plan",str(self.plan_path),"--output",str(output)]
        with patch("timeline_query.os.link",side_effect=OSError("failure")):
            self.assertEqual(self.run_cli(args),1)
        self.assertFalse(output.exists())
        self.assertEqual(self.run_cli(args),0)
        before=output.read_bytes()
        self.assertEqual(self.run_cli(args),1)
        self.assertEqual(self.run_cli(args+["--overwrite"]),0)
        self.assertEqual(before,output.read_bytes())
        self.assertEqual(self.run_cli(["review-template","--plan",str(self.plan_path),"--output",str(self.plan_path),"--overwrite"]),1)
        self.assertFalse(list(self.root.glob(".query-*")))

    def test_import_safety(self):
        code="""import sys
def audit(event,args):
    if event in ('subprocess.Popen','os.mkdir','os.remove'):
        raise AssertionError(event)
    if event=='open' and ((isinstance(args[1],str) and any(c in args[1] for c in 'wax+')) or args[2] & 3):
        raise AssertionError('write')
sys.addaudithook(audit)
import clip_boundary_experiment
assert not any(name in sys.modules for name in ('torch','transformers','faster_whisper'))
"""
        result=subprocess.run([sys.executable,"-B","-c",code],capture_output=True,text=True,cwd=experiment.ROOT)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout+result.stderr,"")


if __name__=="__main__":
    unittest.main()
