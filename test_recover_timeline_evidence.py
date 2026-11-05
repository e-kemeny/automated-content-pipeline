"""Synthetic fixtures mirror evaluate_dynamic_windows_v2's persisted list."""
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import recover_timeline_evidence as recovery
from multimodal_timeline import build_timeline, validate_timeline
from candidate_evidence import build_candidate_evidence
from inspect_candidate_evidence import inspect_evidence
from shared_analysis import create_analysis, signal
from timeline_query import query_timeline


def fixture():
    audio=dict(second=5,spike=-2,score=4,normalized_score=.4,start=0,end=10,duration=10)
    diagnostic=dict(boundary=6,inward_mean=.2,outward_mean=.1,scene_time=5.5,
                    scene_score=.7,audio_ok=True,scene_ok=True)
    window=dict(start=0,end=10,boundary_diagnostics={
        "backward":{"evidence":[diagnostic,deepcopy(diagnostic)]},
        "forward":{"evidence":[dict(diagnostic,scene_time=None,scene_score=None,scene_ok=False)]}})
    return [dict(fixed=dict(detector="Audio-only",k=5,windows=[audio,deepcopy(audio)]),
                 v1=dict(windows=[]),v2=dict(windows=[window]))]


class RecoveryTests(unittest.TestCase):
    def test_audio_values_and_provenance(self):
        data=fixture()
        timeline=recovery.recover_dynamic_v2(data,"fixture.json")
        rows=[e for e in timeline["events"] if e["modality"]=="audio"]
        self.assertEqual(rows[0]["payload"],data[0]["fixed"]["windows"][0])
        self.assertEqual(rows[0]["event_type"],"audio_spike_score")
        self.assertEqual(rows[0]["source"]["artifact_pointer"],"/0/fixed/windows/0")
        self.assertEqual(rows[0]["source"]["provenance"]["original_artifact"],"fixture.json")

    def test_scene_values_are_normalized_only(self):
        timeline=recovery.recover_dynamic_v2(fixture())
        rows=[e for e in timeline["events"] if e["modality"]=="visual"]
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]["payload"]["time"],5.5)
        self.assertEqual(rows[0]["payload"]["normalized_score"],.7)
        self.assertNotIn("score",rows[0]["payload"])
        self.assertEqual(rows[0]["payload"]["recovery_diagnostic"],
                         fixture()[0]["v2"]["windows"][0]["boundary_diagnostics"]["backward"]["evidence"][0])

    def test_duplicates_order_no_mutation(self):
        data=fixture()
        original=deepcopy(data)
        timeline=recovery.recover_dynamic_v2(data)
        self.assertEqual(len(timeline["events"]),4)
        self.assertEqual([e["source_order"] for e in timeline["events"]],[0,1,2,3])
        timeline["events"][0]["payload"]["score"]=99
        self.assertEqual(data,original)

    def test_chronological_order_preserves_source_order(self):
        data=fixture()
        data[0]["fixed"]["windows"][0]["second"]=8
        timeline=recovery.recover_dynamic_v2(data)
        self.assertEqual([e["start_seconds"] for e in timeline["events"]],[5,5.5,5.5,8])
        self.assertEqual([e["source_order"] for e in timeline["events"]],[1,2,3,0])

    def test_boundary_queries_and_downstream_inspection(self):
        timeline=recovery.recover_dynamic_v2(fixture())
        self.assertEqual(len(query_timeline(timeline,5,5.5)["events"]),4)
        analysis=create_analysis(dict(path="fixture.mp4",duration_seconds=10,sha256="a"*64))
        analysis["candidate_windows"]=signal([dict(start=5,end=5.5)])
        report=inspect_evidence(build_candidate_evidence(analysis,timeline))
        self.assertEqual(report["candidates"][0]["counts_by_modality"],dict(audio=2,visual=2,transcript=0))
        self.assertEqual(report["identity_comparison"],"unverified_missing_source_digest")

    def test_missing_transcript_unknown_identity_coverage(self):
        timeline=recovery.recover_dynamic_v2(fixture())
        self.assertEqual(timeline["identity_status"],"unverified_single_artifact")
        self.assertIsNone(timeline["duration_seconds"])
        self.assertIsNone(timeline["source_identity"])
        analysis=create_analysis(dict(path="fixture.mp4",duration_seconds=10))
        analysis["candidate_windows"]=signal([dict(start=0,end=1)])
        row=build_candidate_evidence(analysis,timeline)["candidates"][0]
        self.assertEqual(row["evidence_coverage"]["transcript"]["observation_status"],"absent_from_timeline")
        self.assertEqual(row["evidence_coverage"]["audio"]["observation_status"],"no_events_in_window")
        self.assertTrue(all(c["temporal_coverage"]=="unknown" for c in row["evidence_coverage"].values()))

    def test_empty_analyzed_channels(self):
        data=fixture()
        data[0]["fixed"]["windows"]=[]
        data[0]["v2"]["windows"]=[]
        timeline=recovery.recover_dynamic_v2(data)
        self.assertEqual(timeline["events"],[])
        self.assertTrue(all(c["status"]=="analyzed" for c in timeline["sources"][0]["channels"].values()))

    def test_existing_shared_analysis_combined_support(self):
        a=create_analysis(dict(path="fixture.mp4",duration_seconds=10))
        a["acoustic"]["audio_activity"]=signal([dict(second=2,spike=1,score=2)])
        a["visual"]["scene_changes"]=signal([dict(time=3,score=5)])
        a["transcript"]=signal([dict(start=1,end=4,text="Existing text")])
        timeline=build_timeline(analysis=a)
        self.assertEqual({e["modality"] for e in timeline["events"]},{"audio","visual","transcript"})

    def test_conflicting_identity_rejected_by_existing_contract(self):
        a=create_analysis(dict(path="fixture.mp4",duration_seconds=10,sha256="a"*64))
        a["acoustic"]["audio_activity"]=signal([],dict(source_sha256="b"*64))
        with self.assertRaises(ValueError):
            build_timeline(analysis=a)

    def test_missing_digest_cannot_merge_other_artifact(self):
        timeline=recovery.recover_dynamic_v2(fixture())
        other=build_timeline(analysis=create_analysis(dict(path="fixture.mp4",duration_seconds=10,sha256="a"*64)))
        timeline["sources"]+=other["sources"]
        with self.assertRaisesRegex(ValueError,"every source SHA-256"):
            validate_timeline(timeline)

    def test_unsupported_artifacts_and_injected_identity(self):
        for data in ({},[],[{}],dict(schema_version=99)):
            with self.subTest(data=data),self.assertRaises(ValueError):
                recovery.recover_dynamic_v2(data)
        data=fixture()
        data[0]["source_video"]={"sha256":"a"*64}
        with self.assertRaises(ValueError):
            recovery.recover_dynamic_v2(data)

    def test_invalid_audio_timestamps_and_numbers(self):
        for key,value in (("second",-1),("second",True),("second",11),("score",float("nan")),("spike","2")):
            data=fixture()
            data[0]["fixed"]["windows"][0][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                recovery.recover_dynamic_v2(data)

    def test_invalid_scene_diagnostics(self):
        for key,value in (("scene_time",-1),("scene_time",None),("scene_score",2),("scene_score",float("inf")),
                          ("boundary",True),("inward_mean","0.2"),("audio_ok",1)):
            data=fixture()
            data[0]["v2"]["windows"][0]["boundary_diagnostics"]["backward"]["evidence"][0][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                recovery.recover_dynamic_v2(data)


class CliTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.input=self.root/"dynamic.json"
        self.output=self.root/"timeline.json"
        self.input.write_text(json.dumps(fixture()),encoding="utf-8")

    def run_cli(self,*extra):
        out,err=io.StringIO(),io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            code=recovery.main(["--dynamic-v2",str(self.input),*extra])
        return code,out.getvalue(),err.getvalue()

    def test_stdout_and_no_writes(self):
        before=self.input.stat().st_mtime_ns
        code,out,err=self.run_cli()
        self.assertEqual(code,0)
        validate_timeline(json.loads(out))
        self.assertEqual(err,"")
        self.assertEqual(list(self.root.iterdir()),[self.input])
        self.assertEqual(before,self.input.stat().st_mtime_ns)

    def test_atomic_output_and_overwrite_protection(self):
        real_link=recovery.save_timeline.__globals__["os"].link
        def publish(source,destination):
            self.assertFalse(Path(destination).exists())
            validate_timeline(json.loads(Path(source).read_text()))
            real_link(source,destination)
        with patch("multimodal_timeline.os.link",side_effect=publish):
            self.assertEqual(self.run_cli("--output",str(self.output))[0],0)
        first=self.output.read_bytes()
        self.assertEqual(self.run_cli("--output",str(self.output))[0],1)
        self.assertEqual(self.run_cli("--output",str(self.output),"--overwrite")[0],0)
        self.assertEqual(first,self.output.read_bytes())

    def test_failure_cleanup_and_input_protection(self):
        with patch("multimodal_timeline.os.link",side_effect=OSError("failure")):
            self.assertEqual(self.run_cli("--output",str(self.output))[0],1)
        self.assertEqual(list(self.root.iterdir()),[self.input])
        original=self.input.read_bytes()
        self.assertEqual(self.run_cli("--output",str(self.input),"--overwrite")[0],1)
        self.assertEqual(original,self.input.read_bytes())

    def test_missing_input_and_invalid_json(self):
        self.input.write_text("{}")
        self.assertEqual(self.run_cli()[0],1)
        self.input.unlink()
        self.assertEqual(self.run_cli()[0],1)

    def test_import_safety(self):
        import importlib
        out,err=io.StringIO(),io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err),patch(
                "subprocess.Popen",side_effect=AssertionError("process")),patch(
                "pathlib.Path.write_text",side_effect=AssertionError("write")),patch(
                "pathlib.Path.mkdir",side_effect=AssertionError("mkdir")):
            importlib.reload(recovery)
        self.assertEqual(out.getvalue()+err.getvalue(),"")


if __name__=="__main__":
    unittest.main()
