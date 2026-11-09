"""Synthetic human annotation fixtures; no video access or inference."""
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

import gameplay_events as events
from shared_analysis import create_analysis, signal
from multimodal_timeline import build_timeline


def analysis_fixture():
    analysis = create_analysis(dict(path="synthetic.mp4", duration_seconds=20, sha256="a"*64))
    analysis["candidate_windows"] = signal([
        dict(start=2, end=10, second=5, duration=8, score=7, highlight_score=0.6),
        dict(start=2, end=10, second=5, duration=8, score=7, highlight_score=0.6)],
        dict(detector="Audio-only", variant="fixed", k=2))
    analysis["acoustic"]["audio_activity"] = signal([dict(second=t,score=2) for t in (2,5,5,10)])
    analysis["visual"]["scene_changes"] = signal([dict(time=10,score=3)])
    analysis["transcript"] = signal([dict(start=10,end=12,text="synthetic words")])
    return analysis


def add_event(document, event_id="review-1", start=2, end=10, precision="clip_level", candidate=0):
    item = dict(event_id=event_id, event_type="fight", start_seconds=start, end_seconds=end,
        temporal_precision=precision, description="Synthetic test annotation", source="human",
        source_video_identity=deepcopy(document["source_video_identity"]),
        provenance=dict(annotator="fixture reviewer", method="manual_review"))
    document["candidates"][candidate]["events"].append(item)
    return item


def fixture():
    document = events.create_template(analysis_fixture())
    add_event(document)
    return document


class AnnotationTests(unittest.TestCase):
    def test_empty_template_preserves_actual_candidate_schema(self):
        analysis = analysis_fixture()
        before = deepcopy(analysis)
        result = events.create_template(analysis)
        self.assertEqual([r["original_candidate"] for r in result["candidates"]], analysis["candidate_windows"]["data"])
        self.assertEqual([r["events"] for r in result["candidates"]], [[],[]])
        self.assertEqual(result["candidate_provenance"], analysis["candidate_windows"]["provenance"])
        self.assertEqual(result["source_video_identity"]["claims"], analysis["source_video"])
        self.assertEqual(analysis, before)
        self.assertEqual(events.validate_annotations(result), result)

    def test_duplicate_candidates_preserve_indices_and_distinct_events(self):
        document = fixture()
        add_event(document,event_id="review-2",candidate=1)
        result = events.query_events(document,2,10)
        self.assertEqual([r["candidate_index"] for r in result["events"]],[0,1])
        self.assertEqual(result["matched_event_count"],2)
        self.assertEqual(result["event_types"],["fight"])

    def test_exact_point_interval_and_uncertainty(self):
        for precision,start,end in (("exact_point",5,5),("exact_interval",5,6),("clip_level",2,10)):
            document = events.create_template(analysis_fixture())
            add_event(document,start=start,end=end,precision=precision)
            with self.subTest(precision=precision):
                self.assertEqual(events.validate_annotations(document),document)

    def test_event_vocabulary(self):
        for kind in events.EVENT_TYPES:
            document = fixture()
            document["candidates"][0]["events"][0]["event_type"] = kind
            self.assertEqual(events.validate_annotations(document),document)
        for invalid in ("kill","bed_break",None,7):
            document = fixture()
            document["candidates"][0]["events"][0]["event_type"] = invalid
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                events.validate_annotations(document)

    def test_invalid_timestamps_and_precision(self):
        for start,end,precision in ((-1,2,"clip_level"),(3,2,"clip_level"),(0,21,"clip_level"),
                (True,3,"clip_level"),(float("nan"),3,"clip_level"),(0,float("inf"),"clip_level"),
                ("0",3,"clip_level"),(2,2,"clip_level"),(2,3,"exact_point"),(2,2,"exact_interval"),(2,3,"approximate")):
            document = events.create_template(analysis_fixture())
            add_event(document,start=start,end=end,precision=precision)
            with self.subTest(values=(start,end,precision)),self.assertRaises(ValueError):
                events.validate_annotations(document)

    def test_global_unique_event_ids(self):
        document = fixture()
        add_event(document,candidate=1)
        with self.assertRaisesRegex(ValueError,"Duplicate event_id"):
            events.validate_annotations(document)

    def test_required_human_provenance(self):
        for key,value in (("source","model"),("event_id"," "),("description",3),
                ("provenance",{}),("provenance",dict(annotator="x",method="inference")),
                ("provenance",dict(annotator=" ",method="manual_review"))):
            document = fixture()
            document["candidates"][0]["events"][0][key] = value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                events.validate_annotations(document)

    def test_optional_metadata_and_certainty(self):
        document = fixture()
        item = document["candidates"][0]["events"][0]
        item.update(player={"perspective":"unclear"},team={"color":"aqua"},notes="human notes",certainty="uncertain")
        result = events.query_events(document,0,20)
        self.assertEqual(result["events"][0]["event"],item)
        for key,value in (("certainty",0.8),("player",[]),("team","aqua"),("notes",None),("confidence",0.8)):
            bad = deepcopy(document)
            bad["candidates"][0]["events"][0][key] = value
            with self.subTest(key=key),self.assertRaises(ValueError):
                events.validate_annotations(bad)

    def test_event_identity_conflicts_or_missing_claim(self):
        for mode in ("sha","status","missing","duration"):
            document = fixture()
            identity = document["candidates"][0]["events"][0]["source_video_identity"]
            if mode == "sha": identity["claims"]["sha256"] = "b"*64
            elif mode == "status": identity["status"] = "verified"
            elif mode == "duration": identity["claims"]["duration_seconds"] = 21
            else: identity["claims"].pop("sha256")
            with self.subTest(mode=mode),self.assertRaises(ValueError):
                events.validate_annotations(document)

    def test_unknown_identity_is_explicit_and_queryable(self):
        analysis = analysis_fixture()
        del analysis["source_video"]["sha256"]
        document = events.create_template(analysis)
        add_event(document)
        result = events.query_events(document,2,10)
        self.assertEqual(result["source_video_identity"]["status"],"unverified_missing_source_digest")
        self.assertEqual(result["matched_event_count"],1)
        with self.assertRaises(ValueError):
            events.validate_annotations(document,verified_source=analysis_fixture()["source_video"])

    def test_independently_verified_duration_and_content(self):
        document = fixture()
        source = analysis_fixture()["source_video"]
        self.assertEqual(events.validate_annotations(document,verified_source=source),document)
        for key,value in (("duration_seconds",9),("sha256","b"*64),("duration_seconds",float("nan"))):
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                events.validate_annotations(document,verified_source=dict(source,**{key:value}))
        with self.assertRaises(ValueError):
            events.validate_annotations(document,verified_source={"sha256":"a"*64})
        self.assertEqual(document["source_video_identity"]["status"],"reported_sha256_unverified")

    def test_invalid_or_unknown_duration(self):
        for value in (None,0,-1,float("inf"),True):
            analysis = analysis_fixture()
            analysis["source_video"]["duration_seconds"] = value
            with self.subTest(value=value),self.assertRaises(ValueError):
                events.create_template(analysis)
        analysis = analysis_fixture()
        del analysis["source_video"]["duration_seconds"]
        with self.assertRaises(ValueError):
            events.create_template(analysis)

    def test_template_binding_and_versions(self):
        for mode in ("schema","identity","candidate","order","provenance","events","extra"):
            document = fixture()
            if mode == "schema": document["schema_version"] = 2
            elif mode == "identity": document["source_video_identity"]["status"] = "verified"
            elif mode == "candidate": document["candidates"][0]["original_candidate"]["score"] = 9
            elif mode == "order": document["candidates"].reverse()
            elif mode == "provenance": document["candidate_provenance"]["detector"] = "Other"
            elif mode == "events": document["candidates"][1]["events"] = {}
            else: document["extra"] = 1
            with self.subTest(mode=mode),self.assertRaises(ValueError):
                events.validate_annotations(document)

    def test_explicit_provenance_identity_conflict(self):
        analysis = analysis_fixture()
        analysis["candidate_windows"]["provenance"]["source_sha256"] = "b"*64
        with self.assertRaises(ValueError):
            events.create_template(analysis)
        document = fixture()
        document["candidates"][0]["events"][0]["provenance"]["source_duration_seconds"] = 21
        with self.assertRaises(ValueError):
            events.validate_annotations(document)

    def test_provenance_conflicts_with_unknown_header_digest(self):
        analysis = analysis_fixture()
        del analysis["source_video"]["sha256"]
        document = events.create_template(analysis)
        first = add_event(document)
        second = add_event(document,event_id="second")
        first["provenance"]["source_sha256"] = "a"*64
        second["provenance"]["source_sha256"] = "b"*64
        with self.assertRaisesRegex(ValueError,"Conflicting annotation provenance"):
            events.validate_annotations(document)

    def test_closed_overlap_and_point_queries(self):
        document = fixture()
        for start,end,count in ((0,1,0),(0,2,1),(3,5,1),(10,10,1),(10,12,1),(11,20,0)):
            with self.subTest(start=start,end=end):
                self.assertEqual(events.query_events(document,start,end)["matched_event_count"],count)
        document = events.create_template(analysis_fixture())
        add_event(document,start=20,end=20,precision="exact_point")
        self.assertEqual(events.query_events(document,20,20)["matched_event_count"],1)

    def test_invalid_query(self):
        for start,end in ((-1,2),(3,2),(0,21),(True,3),(0,float("inf"))):
            with self.subTest(start=start,end=end),self.assertRaises(ValueError):
                events.query_events(fixture(),start,end)

    def test_query_order_copy_and_empty_annotations(self):
        document = fixture()
        add_event(document,event_id="late",start=15,end=16,precision="exact_interval")
        add_event(document,event_id="early",start=1,end=1,precision="exact_point")
        before = deepcopy(document)
        result = events.query_events(document,0,20)
        self.assertEqual([r["event"]["event_id"] for r in result["events"]],["review-1","late","early"])
        result["events"][0]["event"]["description"] = "changed copy"
        self.assertEqual(document,before)
        self.assertEqual(events.query_events(events.create_template(analysis_fixture()),0,20)["events"],[])

    def test_deterministic_round_trip(self):
        document = fixture()
        restored = json.loads(json.dumps(document,sort_keys=True))
        self.assertEqual(events.query_events(restored,2,10),events.query_events(document,2,10))
        self.assertEqual(events.create_template(analysis_fixture()),events.create_template(analysis_fixture()))


class AlignmentTests(unittest.TestCase):
    def test_alignment_preserves_duplicates_provenance_and_coverage(self):
        document = fixture()
        timeline = build_timeline(analysis=analysis_fixture())
        before = deepcopy((document,timeline))
        result = events.align_timeline(document,timeline)
        row = result["events"][0]
        self.assertEqual(row["observations"],timeline["events"])
        self.assertEqual(row["counts_by_modality"],dict(audio=4,visual=1,transcript=1))
        self.assertTrue(all(c["temporal_coverage"]=="unknown" for c in row["evidence_coverage"].values()))
        self.assertEqual((document,timeline),before)
        self.assertEqual(result["identity_comparison"],"consistent_reported_sha256")

    def test_alignment_rejects_conflicts_and_unknown_identity(self):
        for digest in (None,"b"*64):
            analysis = analysis_fixture()
            if digest is None: del analysis["source_video"]["sha256"]
            else: analysis["source_video"]["sha256"] = digest
            with self.subTest(digest=digest),self.assertRaises(ValueError):
                events.align_timeline(fixture(),build_timeline(analysis=analysis))

    def test_alignment_empty_match_is_not_negative_label(self):
        document = events.create_template(analysis_fixture())
        add_event(document,start=15,end=16,precision="clip_level")
        row = events.align_timeline(document,build_timeline(analysis=analysis_fixture()))["events"][0]
        self.assertEqual(row["observations"],[])
        self.assertEqual(row["evidence_coverage"]["audio"]["observation_status"],"no_events_in_window")
        self.assertEqual(row["evidence_coverage"]["audio"]["temporal_coverage"],"unknown")

    def test_alignment_vision_predictions_not_relabelled(self):
        vision = dict(schema_version=1,experiment="vision-inference-v1",video=analysis_fixture()["source_video"],
            model=dict(name="resnet18"),sampling={},runtime={},
            frames=[dict(timestamp_seconds=5,top3=[dict(category=name,confidence=0.2) for name in ("a","b","c")])])
        row = events.align_timeline(fixture(),build_timeline(vision=vision))["events"][0]
        self.assertEqual(row["observations"][0]["event_type"],"imagenet_frame_prediction")
        self.assertEqual(row["observations"][0]["payload"],vision["frames"][0])


class CLITests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.analysis = self.root/"analysis.json"
        self.analysis.write_text(json.dumps(analysis_fixture()),encoding="utf-8")
        self.output = self.root/"annotations.json"

    def run_cli(self,args):
        out,err = io.StringIO(),io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            code = events.main(args)
        return code,out.getvalue(),err.getvalue()

    def template_args(self):
        return ["template","--analysis",str(self.analysis),"--output",str(self.output)]

    def test_cli_template_query_and_alignment(self):
        self.assertEqual(self.run_cli(self.template_args())[0],0)
        document = events.read_json(self.output)
        self.assertEqual(document["candidates"][0]["events"],[])
        add_event(document)
        self.output.write_text(json.dumps(document),encoding="utf-8")
        before = self.output.read_bytes()
        code,stdout,_ = self.run_cli(["query","--annotations",str(self.output),"--start","2","--end","10"])
        self.assertEqual(code,0)
        self.assertEqual(json.loads(stdout)["matched_event_count"],1)
        timeline = self.root/"timeline.json"
        timeline.write_text(json.dumps(build_timeline(analysis=analysis_fixture())),encoding="utf-8")
        report = self.root/"alignment.json"
        self.assertEqual(self.run_cli(["align","--annotations",str(self.output),"--timeline",str(timeline),"--output",str(report)])[0],0)
        self.assertEqual(before,self.output.read_bytes())

    def test_atomic_failure_cleans_temporary(self):
        with patch("timeline_query.os.link",side_effect=OSError("publication failure")):
            self.assertEqual(self.run_cli(self.template_args())[0],1)
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob(".query-*")))

    def test_overwrite_and_input_protection(self):
        self.assertEqual(self.run_cli(self.template_args())[0],0)
        before = self.output.read_bytes()
        self.assertEqual(self.run_cli(self.template_args())[0],1)
        self.assertEqual(before,self.output.read_bytes())
        self.assertEqual(self.run_cli(self.template_args()+["--overwrite"])[0],0)
        self.assertEqual(before,self.output.read_bytes())
        self.assertEqual(self.run_cli(["template","--analysis",str(self.analysis),"--output",str(self.analysis),"--overwrite"])[0],1)
        self.output.write_text('{"unrelated":true}')
        self.assertEqual(self.run_cli(self.template_args()+["--overwrite"])[0],1)
        self.assertEqual(self.output.read_text(),'{"unrelated":true}')

    def test_malformed_json_missing_files_and_validation_failures(self):
        for text in ('{', '{"a":1,"a":2}', '{"a":NaN}', '[]'):
            self.output.write_text(text)
            code,_,err = self.run_cli(["query","--annotations",str(self.output),"--start","2","--end","10"])
            self.assertEqual(code,1)
            self.assertIn("FAIL:",err)
        self.output.unlink()
        self.assertEqual(self.run_cli(["query","--annotations",str(self.output),"--start","2","--end","10"])[0],1)

    def test_import_safety(self):
        script = """import sys
sys.dont_write_bytecode=True
def audit(event,args):
    if event in ('subprocess.Popen','os.mkdir','os.remove'):
        raise AssertionError(event)
    if event=='open' and ((isinstance(args[1],str) and any(c in args[1] for c in 'wax+')) or args[2] & 3):
        raise AssertionError('write')
sys.addaudithook(audit)
import gameplay_events
assert not any(name in sys.modules for name in ('torch','transformers','faster_whisper'))
"""
        result = subprocess.run([sys.executable,"-B","-c",script],cwd=Path(events.__file__).parent,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout+result.stderr,"")


if __name__ == "__main__":
    unittest.main()
