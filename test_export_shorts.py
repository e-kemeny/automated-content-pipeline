"""Mocked export tests; no detector/model inference or real encoding."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from shared_analysis import create_analysis, save_analysis
from windows import build_candidate_windows
import export_shorts as shorts

class ShortsTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.video=self.root/"game.mp4"
        self.video.write_bytes(b"source fixture")
        self.path=self.root/"analysis.json"
        self.output=self.root/"output"
        self.source=dict(path=str(self.video),duration_seconds=60,sha256=shorts.media_sha256(self.video))
        self.actual=dict(self.source,width=1920,height=1080)
        self.analysis=create_analysis(self.source)
        self.analysis["candidate_windows"]=dict(status="analyzed",
            data=build_candidate_windows([dict(second=15,score=8,highlight_score=0.5),
                                          dict(second=40,score=7,highlight_score=0.9)],60),
            provenance=dict(detector="Audio-only",variant="fixed",k=2,artifact="fixture"))
        save_analysis(self.analysis,self.path)
        self.probe=patch.object(shorts,"probe_media",return_value=self.actual).start()
        self.addCleanup(patch.stopall)

    def export(self,**kwargs):
        return shorts.export_shorts(self.video,self.path,top_k=2,output_root=self.output,**kwargs)

    def encoder(self,cmd,**kwargs):
        Path(cmd[-1]).write_bytes(b"encoded fixture")

    def encoded(self,**kwargs):
        with patch.object(shorts.subprocess,"run",side_effect=self.encoder) as run,patch.object(shorts,"probe_clip",return_value=dict(duration_seconds=15,streams=[dict(codec_type="video"),dict(codec_type="audio")])):
            result=self.export(**kwargs)
        return result,run

    def test_missing_source(self):
        with self.assertRaises(FileNotFoundError):
            shorts.plan_export(self.root/"missing",self.path)

    def test_schema_version(self):
        bad=deepcopy(self.analysis)
        bad["schema_version"]=2
        self.path.write_text(json.dumps(bad))
        with self.assertRaises(ValueError):
            self.export(dry_run=True)

    def test_source_identity_and_duration(self):
        for change in [dict(sha256="0"*64),dict(duration_seconds=61),dict(width=None)]:
            actual=dict(self.actual,**change)
            if "width" in change:
                actual.pop("width")
            with patch.object(shorts,"probe_media",return_value=actual),self.assertRaises(ValueError):
                self.export(dry_run=True)

    def test_missing_source_hash(self):
        self.analysis["source_video"].pop("sha256")
        save_analysis(self.analysis,self.path)
        with self.assertRaisesRegex(ValueError,"SHA-256"):
            self.export(dry_run=True)

    def test_missing_evidence(self):
        self.analysis["candidate_windows"]["data"]=[]
        with self.assertRaises(ValueError):
            shorts.select_windows(self.analysis,2)

    def test_selected_top_k_constraints(self):
        for k in [0,-1,True,1,3,10]:
            with self.subTest(k=k),self.assertRaises(ValueError):
                shorts.select_windows(self.analysis,k)

    def test_selected_not_reranked_by_multimodal_metadata(self):
        windows,policy=shorts.select_windows(self.analysis,2)
        self.assertEqual([r["second"] for r in windows],[15,40])
        self.assertEqual(policy["ranking_score_key"],"score")
        self.assertFalse(policy["fresh_ranking"])

    def pool(self):
        a=deepcopy(self.analysis)
        a["candidate_windows"]["provenance"]=dict(detector="Audio + Scene",variant="fixed",representation="candidate_pool")
        a["candidate_windows"]["data"]=build_candidate_windows([
            dict(second=5,highlight_score=10,ranking_order=0),
            dict(second=19,highlight_score=9,ranking_order=1),
            dict(second=20,highlight_score=8,ranking_order=2),
            dict(second=45,highlight_score=7,ranking_order=3)],60)
        return a

    def test_pool_ranking_15_second_suppression(self):
        windows,policy=shorts.select_windows(self.pool(),2)
        self.assertEqual([r["second"] for r in windows],[5,20])
        self.assertTrue(policy["fresh_ranking"])
        with self.assertRaises(ValueError):
            shorts.select_windows(self.pool(),4)

    def test_pool_requires_explicit_evidence_and_tie_order(self):
        pool=self.pool()
        pool["candidate_windows"]["data"][0].pop("ranking_order")
        with self.assertRaises(ValueError):
            shorts.select_windows(pool,2)
        pool=self.pool()
        pool["candidate_windows"]["data"][0].pop("highlight_score")
        with self.assertRaises(ValueError):
            shorts.select_windows(pool,2)

    def test_pool_stable_original_tie_order(self):
        pool=self.pool()
        rows=pool["candidate_windows"]["data"]
        rows[0]["highlight_score"]=rows[1]["highlight_score"]=10
        rows[0]["ranking_order"],rows[1]["ranking_order"]=1,0
        windows,_=shorts.select_windows(pool,1)
        self.assertEqual(windows[0]["second"],19)

    def test_boundary_clamping(self):
        a=deepcopy(self.analysis)
        a["candidate_windows"]["data"]=build_candidate_windows([dict(second=0),dict(second=60)],60)
        rows,_=shorts.select_windows(a,2)
        self.assertEqual([(r["start"],r["end"],r["duration"]) for r in rows],[(0,5,5),(50,60,10)])

    def test_persisted_suppression_violation(self):
        self.analysis["candidate_windows"]["data"]=build_candidate_windows([dict(second=5),dict(second=19)],60)
        with self.assertRaises(ValueError):
            shorts.select_windows(self.analysis,2)

    def test_dry_run_deterministic_no_writes(self):
        before=self.path.read_bytes()
        with patch.object(shorts.subprocess,"run") as ffmpeg:
            directory,manifest=self.export(dry_run=True)
        ffmpeg.assert_not_called()
        self.assertFalse(self.output.exists())
        self.assertEqual(before,self.path.read_bytes())
        _,second=self.export(dry_run=True)
        self.assertEqual(manifest,second)
        self.assertEqual(manifest["clips"][0]["output_filename"],"clip_01_t00015.000.mp4")
        self.assertEqual(manifest["clips"][0]["ranking_score"],8)
        self.assertEqual(manifest["selection"]["mode"],"reused_persisted_selection")

    def test_export_manifest_and_accurate_encode_command(self):
        before=self.path.read_bytes()
        (directory,manifest),run=self.encoded()
        self.assertEqual(run.call_count,2)
        self.assertTrue(all(r["status"]=="exported" for r in manifest["clips"]))
        self.assertEqual(json.loads((directory/"shorts_manifest.json").read_text()),manifest)
        self.assertEqual(self.path.read_bytes(),before)
        cmd=run.call_args.args[0]
        self.assertIn("libx264",cmd)
        self.assertIn("aac",cmd)
        self.assertNotIn("copy",cmd)
        self.assertIn("candidate_evidence",manifest["clips"][0])

    def test_reuse_no_ffmpeg(self):
        self.encoded()
        with patch.object(shorts.subprocess,"run") as run,patch.object(shorts,"probe_clip",return_value=dict(duration_seconds=15,streams=[])):
            _,manifest=self.export()
        run.assert_not_called()
        self.assertTrue(all(r["status"]=="reused" for r in manifest["clips"]))

    def test_force_reencodes_owned_only(self):
        self.encoded()
        (_,manifest),run=self.encoded(force=True)
        self.assertEqual(run.call_count,2)
        self.assertTrue(all(r["status"]=="exported" for r in manifest["clips"]))

    def test_partial_ffmpeg_failure_and_cleanup(self):
        count=0
        def fail(cmd,**kwargs):
            nonlocal count
            count+=1
            if count==1:
                raise subprocess.CalledProcessError(1,cmd,stderr="encoding failure fixture")
            self.encoder(cmd)
        with patch.object(shorts.subprocess,"run",side_effect=fail),patch.object(shorts,"probe_clip",return_value=dict(duration_seconds=15,streams=[])):
            directory,manifest=self.export()
        self.assertEqual([r["status"] for r in manifest["clips"]],["failed","exported"])
        self.assertIn("encoding failure",manifest["clips"][0]["error"])
        self.assertEqual(list(directory.glob(".shorts_*")),[])

    def test_unrelated_clip_never_overwritten_even_force(self):
        directory,manifest=self.export(dry_run=True)
        directory.mkdir(parents=True)
        target=directory/manifest["clips"][0]["output_filename"]
        target.write_bytes(b"unrelated")
        with patch.object(shorts.subprocess,"run") as run,self.assertRaises(ValueError):
            self.export(force=True)
        run.assert_not_called()
        self.assertEqual(target.read_bytes(),b"unrelated")

    def test_user_edited_owned_clip_not_overwritten(self):
        (directory,manifest),_=self.encoded()
        target=directory/manifest["clips"][0]["output_filename"]
        target.write_bytes(b"user edited")
        with self.assertRaises(ValueError):
            self.export(force=True)
        self.assertEqual(target.read_bytes(),b"user edited")

    def test_unrelated_manifest(self):
        directory,_=self.export(dry_run=True)
        directory.mkdir(parents=True)
        (directory/"shorts_manifest.json").write_text('{"exporter":"someone else"}')
        with self.assertRaises(ValueError):
            self.export(force=True)

    def test_failed_force_preserves_owned_existing_output(self):
        (directory,first),_=self.encoded()
        original=(directory/first["clips"][0]["output_filename"]).read_bytes()
        with patch.object(shorts.subprocess,"run",side_effect=subprocess.CalledProcessError(1,["ffmpeg"],stderr="failure")):
            _,failed=self.export(force=True)
        self.assertEqual(failed["clips"][0]["status"],"failed")
        self.assertEqual((directory/first["clips"][0]["output_filename"]).read_bytes(),original)
        (_,retried),_=self.encoded(force=True)
        self.assertTrue(all(r["status"]=="exported" for r in retried["clips"]))

    def test_concurrent_unrelated_manifest_not_overwritten(self):
        def encode(cmd,**kwargs):
            self.encoder(cmd)
            target=Path(cmd[-1]).parent/"shorts_manifest.json"
            target.write_text('{"exporter":"unrelated concurrent writer"}')
        with patch.object(shorts.subprocess,"run",side_effect=encode),patch.object(shorts,"probe_clip",return_value=dict(duration_seconds=15,streams=[])),self.assertRaises(FileExistsError):
            self.export()
        directory=self.output/"game"/"shorts"
        self.assertEqual(json.loads((directory/"shorts_manifest.json").read_text())["exporter"],"unrelated concurrent writer")

    def test_wrong_export_duration_fails_before_publication(self):
        with patch.object(shorts.subprocess,"run",side_effect=self.encoder),patch.object(shorts,"probe_clip",return_value=dict(duration_seconds=3,streams=[])):
            directory,manifest=self.export()
        self.assertTrue(all(r["status"]=="failed" for r in manifest["clips"]))
        self.assertEqual(list(directory.glob("*.mp4")),[])

    def test_no_analysis_inference(self):
        with patch("transcription.load_model") as asr,patch("language_scoring.LocalTextModel") as language,patch("motion.analyze_motion") as motion:
            self.export(dry_run=True)
        asr.assert_not_called()
        language.assert_not_called()
        motion.assert_not_called()

if __name__=="__main__":
    unittest.main()
