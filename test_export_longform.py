"""Chronological planning and mocked FFmpeg assembly tests."""
from copy import deepcopy
import json
import contextlib
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import export_shorts
import export_longform as longform
from shared_analysis import create_analysis,save_analysis
from windows import build_candidate_windows

class PlanningTests(unittest.TestCase):
    def plan(self,seconds,**kwargs):
        return longform.plan_segments([dict(second=s) for s in seconds],100,**kwargs)

    def test_single_anchor(self):
        expanded,segments=self.plan([50])
        self.assertEqual((segments[0]["start"],segments[0]["end"],segments[0]["duration"]),(35,65,30))
        self.assertEqual(expanded[0]["second"],50)

    def test_overlapping_no_duplicate_footage(self):
        _,segments=self.plan([50,60])
        self.assertEqual([(r["start"],r["end"]) for r in segments],[(35,75)])
        self.assertEqual(segments[0]["duration"],40)
        self.assertEqual(segments[0]["anchors"],[50,60])

    def test_adjacent_within_gap(self):
        _,segments=self.plan([20,55])
        self.assertEqual([(r["start"],r["end"]) for r in segments],[(5,70)])
        _,separate=self.plan([20,55],merge_gap=4.9)
        self.assertEqual(len(separate),2)

    def test_separated_ordering_and_arithmetic(self):
        _,segments=self.plan([85,20])
        self.assertEqual([(r["start"],r["end"]) for r in segments],[(5,35),(70,100)])
        self.assertEqual(sum(r["duration"] for r in segments),60)
        self.assertLess(segments[0]["end"],segments[1]["start"])

    def test_clamping(self):
        _,segments=self.plan([0,100])
        self.assertEqual([(r["start"],r["end"]) for r in segments],[(0,15),(85,100)])

    def test_invalid_and_empty(self):
        with self.assertRaises(ValueError):
            self.plan([])
        for value in [-1,float("nan"),float("inf"),True]:
            with self.assertRaises(ValueError):
                self.plan([50],merge_gap=value)
        with self.assertRaises(ValueError):
            self.plan([50],seconds_before=0,seconds_after=0)

    def test_metadata_and_no_mutation(self):
        original=[dict(second=50,score=0.7,note="supplied")]
        expanded,_=longform.plan_segments(original,100)
        self.assertEqual(expanded[0]["note"],"supplied")
        self.assertEqual(original,[dict(second=50,score=0.7,note="supplied")])

class AssemblyTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.video=self.root/"game.mp4"
        self.video.write_bytes(b"source fixture")
        self.path=self.root/"analysis.json"
        self.output=self.root/"output"
        self.source=dict(path=str(self.video),duration_seconds=100,sha256=longform.media_sha256(self.video),width=160,height=90,fps=60)
        self.analysis=create_analysis(self.source)
        self.analysis["candidate_windows"]=dict(status="analyzed",
            data=build_candidate_windows([dict(second=s,score=s) for s in [20,40,85]],100),
            provenance=dict(detector="Audio-only",variant="fixed",k=3,artifact="fixture"))
        save_analysis(self.analysis,self.path)
        self.addCleanup(patch.stopall)
        patch.object(export_shorts,"probe_media",return_value=self.source).start()
        self.durations={}
        self.calls=[]
        self.cached_duration=80

    def export(self,**kwargs):
        return longform.export_longform(self.video,self.path,output_root=self.output,**kwargs)

    def encode(self,command,**kwargs):
        self.calls.append(command)
        path=Path(command[-1])
        if "-t" in command:
            duration=float(command[command.index("-t")+1])
        else:
            listing=Path(command[command.index("-i")+1])
            duration=sum(self.durations[listing.parent/line.split("'")[1]] for line in listing.read_text().splitlines())
        self.durations[path]=duration
        path.write_bytes(f"encoded {duration} fixture".encode())

    def probe(self,path):
        return dict(duration_seconds=self.durations.get(Path(path),self.cached_duration),
                    streams=[dict(codec_type="video",avg_frame_rate="60/1",start_time="0"),
                             dict(codec_type="audio",start_time="0")])

    def encoded(self,**kwargs):
        with patch.object(longform.subprocess,"run",side_effect=self.encode) as run,patch.object(longform,"probe_clip",side_effect=self.probe):
            result=self.export(**kwargs)
        return result,run

    def test_missing_source_and_schema(self):
        with self.assertRaises(FileNotFoundError):
            longform.prepare_plan(self.root/"missing",self.path)
        bad=deepcopy(self.analysis)
        bad["schema_version"]=2
        self.path.write_text(json.dumps(bad))
        with self.assertRaises(ValueError):
            self.export(dry_run=True)

    def test_source_mismatch(self):
        for change in [dict(sha256="0"*64),dict(duration_seconds=101)]:
            with patch.object(export_shorts,"probe_media",return_value=dict(self.source,**change)),self.assertRaises(ValueError):
                self.export(dry_run=True)

    def test_missing_empty_or_pool_candidates(self):
        for mode in ["missing","empty","pool"]:
            a=deepcopy(self.analysis)
            if mode=="missing":
                a["candidate_windows"]["status"]="not_analyzed"
                a["candidate_windows"]["data"]=[]
            elif mode=="empty":
                a["candidate_windows"]["data"]=[]
            else:
                a["candidate_windows"]["provenance"]["representation"]="candidate_pool"
            save_analysis(a,self.path)
            with self.assertRaises(ValueError):
                self.export(dry_run=True)

    def test_dry_run_deterministic_no_writes(self):
        before=self.path.read_bytes()
        with patch.object(longform.subprocess,"run") as ffmpeg:
            directory,first=self.export(dry_run=True)
            _,second=self.export(dry_run=True)
        ffmpeg.assert_not_called()
        self.assertEqual(first,second)
        self.assertFalse(directory.exists())
        self.assertEqual(before,self.path.read_bytes())
        self.assertEqual(first["planning"]["estimated_duration_seconds"],80)
        self.assertEqual(first["planning"]["candidate_anchors"],[20,40,85])

    def test_manifest_assembly_and_preservation(self):
        before=self.path.read_bytes()
        (directory,manifest),run=self.encoded()
        self.assertEqual(run.call_count,3)
        self.assertEqual(manifest["assembly"]["status"],"complete")
        self.assertEqual(manifest["assembly"]["actual_duration_seconds"],80)
        self.assertEqual(json.loads((directory/"longform_manifest.json").read_text()),manifest)
        self.assertTrue((directory/"longform_v1.mp4").exists())
        self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(list(directory.glob(".longform_*")),[])
        self.assertIn("pcm_s16le",self.calls[0])
        self.assertIn("aac",self.calls[-1])

    def test_reuse_no_encoding_preserves_output(self):
        (directory,_),_=self.encoded()
        output=directory/"longform_v1.mp4"
        before=(output.stat().st_mtime_ns,output.read_bytes())
        with patch.object(longform.subprocess,"run") as run,patch.object(longform,"probe_clip",side_effect=self.probe):
            _,manifest=self.export()
        run.assert_not_called()
        self.assertEqual(manifest["assembly"]["status"],"reused")
        self.assertTrue(all(r["status"]=="reused_from_final" for r in manifest["segments"]))
        self.assertEqual(before,(output.stat().st_mtime_ns,output.read_bytes()))

    def test_config_invalidation_requires_force(self):
        self.encoded()
        with self.assertRaisesRegex(ValueError,"--force"):
            self.export(seconds_before=10)
        (_,result),run=self.encoded(seconds_before=10,force=True)
        self.assertEqual(run.call_count,3)
        self.assertEqual(result["assembly"]["actual_duration_seconds"],70)

    def test_corrupt_or_unrelated_output_never_overwritten(self):
        directory,_=self.export(dry_run=True)
        directory.mkdir(parents=True)
        path=directory/"longform_v1.mp4"
        path.write_bytes(b"unrelated")
        with self.assertRaises(ValueError):
            self.export(force=True)
        self.assertEqual(path.read_bytes(),b"unrelated")

    def test_cache_integrity_check(self):
        (directory,_),_=self.encoded()
        path=directory/"longform_v1.mp4"
        path.write_bytes(b"edited")
        with self.assertRaises(ValueError):
            self.export()
        with self.assertRaises(ValueError):
            self.export(force=True)

    def test_partial_segment_failure_skips_concat(self):
        with patch.object(longform.subprocess,"run",side_effect=subprocess.CalledProcessError(1,["ffmpeg"],stderr="segment failure")) as run:
            directory,manifest=self.export()
        self.assertEqual(run.call_count,1)
        self.assertEqual([r["status"] for r in manifest["segments"]],["failed","skipped"])
        self.assertEqual(manifest["assembly"]["status"],"failed")
        self.assertIsNone(manifest["assembly"]["actual_duration_seconds"])
        self.assertFalse((directory/"longform_v1.mp4").exists())
        self.assertEqual(list(directory.glob(".longform_*")),[])

    def test_concat_failure_no_success_output(self):
        def fail(command,**kwargs):
            if "-f" in command:
                raise subprocess.CalledProcessError(1,command,stderr="concat failure")
            self.encode(command)
        with patch.object(longform.subprocess,"run",side_effect=fail),patch.object(longform,"probe_clip",side_effect=self.probe):
            directory,manifest=self.export()
        self.assertEqual(manifest["assembly"]["status"],"failed")
        self.assertIn("concat failure",manifest["assembly"]["error"])
        self.assertFalse((directory/"longform_v1.mp4").exists())

    def test_failed_force_retains_previous_and_can_retry(self):
        (directory,first),_=self.encoded()
        path=directory/"longform_v1.mp4"
        before=path.read_bytes()
        with patch.object(longform.subprocess,"run",side_effect=subprocess.CalledProcessError(1,["ffmpeg"],stderr="failed refresh")):
            _,failed=self.export(force=True)
        self.assertEqual(path.read_bytes(),before)
        self.assertEqual(failed["assembly"]["status"],"failed")
        self.assertIn("retained_previous_output",failed["assembly"])
        (_,retried),_=self.encoded(force=True)
        self.assertEqual(retried["assembly"]["status"],"complete")

    def test_unrelated_manifest(self):
        directory,_=self.export(dry_run=True)
        directory.mkdir(parents=True)
        path=directory/"longform_manifest.json"
        path.write_text('{"exporter":"someone else"}')
        with self.assertRaises(ValueError):
            self.export(force=True)

    def test_candidate_change_invalidates_cache(self):
        self.encoded()
        self.analysis["candidate_windows"]["data"]=build_candidate_windows([dict(second=s,score=s) for s in [20,45,85]],100)
        save_analysis(self.analysis,self.path)
        with self.assertRaisesRegex(ValueError,"--force"):
            self.export()

    def test_unrelated_language_change_does_not_invalidate_cache(self):
        self.encoded()
        from shared_analysis import signal
        self.analysis["language"]["humor"]=signal([dict(start=0,end=1,score=0.5)])
        save_analysis(self.analysis,self.path)
        with patch.object(longform.subprocess,"run") as run,patch.object(longform,"probe_clip",side_effect=self.probe):
            _,manifest=self.export()
        run.assert_not_called()
        self.assertEqual(manifest["assembly"]["status"],"reused")

    def test_later_segment_failure_preserves_honest_partial_status(self):
        def fail(command,**kwargs):
            if len(self.calls)==1:
                raise subprocess.CalledProcessError(1,command,stderr="second segment failed")
            self.encode(command)
        with patch.object(longform.subprocess,"run",side_effect=fail),patch.object(longform,"probe_clip",side_effect=self.probe):
            directory,manifest=self.export()
        self.assertEqual(manifest["assembly"]["status"],"failed")
        self.assertEqual(manifest["assembly"]["assembled_segment_count"],0)
        self.assertEqual([r["status"] for r in manifest["segments"]],["encoded_temporary","failed"])
        self.assertTrue(manifest["segments"][0]["temporary_removed"])
        self.assertFalse((directory/"longform_v1.mp4").exists())

    def test_cli_config_and_dry_run(self):
        directory,manifest=self.export(dry_run=True)
        with patch.object(longform,"export_longform",return_value=(directory,manifest)) as export,contextlib.redirect_stdout(io.StringIO()) as text:
            status=longform.main([str(self.video),"--analysis",str(self.path),"--seconds-before","10","--seconds-after","20","--merge-gap","3","--dry-run"])
        self.assertEqual(status,0)
        self.assertEqual(export.call_args.kwargs["seconds_before"],10)
        self.assertEqual(export.call_args.kwargs["seconds_after"],20)
        self.assertTrue(export.call_args.kwargs["dry_run"])
        self.assertIn("not assembled",text.getvalue())

    def test_no_inference(self):
        with patch("transcription.load_model") as asr,patch("language_scoring.LocalTextModel") as language,patch("motion.analyze_motion") as motion:
            self.export(dry_run=True)
        asr.assert_not_called()
        language.assert_not_called()
        motion.assert_not_called()

if __name__=="__main__":
    unittest.main()
