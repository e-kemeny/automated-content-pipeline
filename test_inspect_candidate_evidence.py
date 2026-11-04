"""Synthetic Candidate Evidence V1 inspection tests."""
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

from candidate_evidence import build_candidate_evidence
from multimodal_timeline import build_timeline
from shared_analysis import create_analysis, signal
import inspect_candidate_evidence as inspection
import test_multimodal_timeline as timeline_fixtures


def fixture(audio=True, transcript=True, scene=True, vision=False):
    analysis = create_analysis(dict(path="fixture.mp4",duration_seconds=10,sha256="a"*64))
    analysis["candidate_windows"] = signal([
        dict(id=f"candidate-{i}",rank=5-i,start=i*2,end=i*2+2,score=10-i) for i in range(5)],
        dict(detector="Audio-only",variant="fixed"))
    if audio:
        analysis["acoustic"]["audio_activity"] = signal([dict(second=1,score=3,spike=-1),dict(second=1,score=3,spike=-1)])
    if transcript:
        analysis["transcript"] = signal([dict(start=0.5,end=1.5,text="Original speech " * 30)])
    if scene:
        analysis["visual"]["scene_changes"] = signal([dict(time=1,score=12)])
    timeline = build_timeline(analysis=analysis,vision=timeline_fixtures.vision() if vision else None)
    return build_candidate_evidence(analysis,timeline)


class InspectionTests(unittest.TestCase):
    def test_five_candidates_summary_and_scores(self):
        result = inspection.inspect_evidence(fixture())
        self.assertEqual(result["candidate_count"],5)
        self.assertEqual(result["with_observations"],dict(transcript=1,audio=1,visual=1,scene_change=1))
        self.assertEqual(result["without_observations"],dict(transcript=4,audio=4,visual=4,scene_change=4))
        first = result["candidates"][0]
        self.assertEqual((first["start"],first["end"],first["duration"]),(0,2,2))
        self.assertEqual(first["original_scores"],{"score":10})
        self.assertEqual(first["matched_event_count"],4)

    def test_empty_candidates(self):
        evidence = fixture()
        evidence["candidates"] = []
        result = inspection.inspect_evidence(evidence)
        self.assertEqual(result["candidate_count"],0)
        self.assertFalse(any(result["with_observations"].values()))

    def test_no_observations_and_not_established(self):
        result = inspection.inspect_evidence(fixture(False,False,False))
        self.assertFalse(any(result["with_observations"].values()))
        self.assertEqual(result["candidates"][0]["evidence_coverage"]["audio"]["observation_status"],"not_established")

    def test_transcript_only(self):
        result = inspection.inspect_evidence(fixture(False,True,False))
        self.assertEqual(result["with_observations"],dict(transcript=1,audio=0,visual=0,scene_change=0))
        self.assertEqual(result["candidates"][0]["previews"]["transcript"]["items"][0]["start"],0.5)

    def test_visual_only_predictions_not_gameplay(self):
        result = inspection.inspect_evidence(fixture(False,False,False,True))
        self.assertEqual(result["with_observations"],dict(transcript=0,audio=0,visual=1,scene_change=0))
        item = result["candidates"][2]["previews"]["visual_predictions"]["items"][0]
        self.assertEqual(item["model_predictions"][0]["label"],"tench")
        self.assertEqual(item["model_predictions"][0]["confidence"],.6)
        self.assertIn("not verified gameplay",inspection.render_text(result))

    def test_audio_and_scene_summaries(self):
        result = inspection.inspect_evidence(fixture(True,False,True))
        previews = result["candidates"][0]["previews"]
        self.assertEqual(previews["audio"]["items"][0]["original_values"],dict(spike=-1,score=3))
        self.assertEqual(previews["scene_change"]["items"][0]["original_values"],dict(score=12))

    def test_absent_modality_vs_empty_channel(self):
        analysis = create_analysis(dict(path="fixture.mp4",duration_seconds=10))
        analysis["candidate_windows"] = signal([dict(start=1,end=2)])
        timeline = build_timeline(transcript=dict(segments=[],provenance={}))
        result = inspection.inspect_evidence(build_candidate_evidence(analysis,timeline))
        coverage = result["candidates"][0]["evidence_coverage"]
        self.assertEqual(coverage["audio"]["observation_status"],"absent_from_timeline")
        self.assertEqual(coverage["transcript"]["observation_status"],"no_events_in_window")
        self.assertEqual(result["identity_comparison"],"unverified_missing_source_digest")

    def test_unknown_coverage_preserved(self):
        evidence = fixture()
        result = inspection.inspect_evidence(evidence)
        for original,row in zip(evidence["candidates"],result["candidates"]):
            self.assertEqual(row["evidence_coverage"],original["evidence_coverage"])
            self.assertTrue(all(c["temporal_coverage"]=="unknown" for c in row["evidence_coverage"].values()))

    def test_preview_limits_do_not_change_counts(self):
        result = inspection.inspect_evidence(fixture(),preview_limit=1,preview_chars=12)
        first = result["candidates"][0]
        self.assertEqual(first["counts_by_modality"]["audio"],2)
        self.assertEqual(first["previews"]["audio"]["omitted_events"],1)
        excerpt = first["previews"]["transcript"]["items"][0]
        self.assertEqual(excerpt["text"],"Original spe")
        self.assertTrue(excerpt["text_truncated"])
        zero = inspection.inspect_evidence(fixture(),preview_limit=0)
        self.assertEqual(zero["candidates"][0]["previews"]["transcript"]["items"],[])

    def test_visual_label_truncation(self):
        evidence = fixture(False,False,False,True)
        prediction = evidence["candidates"][2]["events"][0]["payload"]["top3"][0]
        prediction["category"] = "very long label"
        result = inspection.inspect_evidence(evidence,preview_chars=4)
        label = result["candidates"][2]["previews"]["visual_predictions"]["items"][0]["model_predictions"][0]
        self.assertEqual(label["label"],"very")
        self.assertTrue(label["label_truncated"])

    def test_order_duplicates_no_mutation(self):
        evidence = fixture()
        original = deepcopy(evidence)
        result = inspection.inspect_evidence(evidence)
        self.assertEqual([r["identifiers"]["rank"] for r in result["candidates"]],[5,4,3,2,1])
        audio = result["candidates"][0]["previews"]["audio"]["items"]
        self.assertEqual(len(audio),2)
        self.assertLess(audio[0]["source_order"],audio[1]["source_order"])
        result["candidates"][0]["evidence_coverage"]["audio"]["temporal_coverage"]="changed"
        self.assertEqual(evidence,original)

    def test_missing_score(self):
        evidence = fixture()
        del evidence["candidates"][0]["candidate"]["score"]
        self.assertEqual(inspection.inspect_evidence(evidence)["candidates"][0]["original_scores"],{})

    def test_bad_preview_arguments(self):
        for limit,chars in [(True,160),(-1,160),(21,160),(3,0),(3,501),(3,float("inf"))]:
            with self.subTest(limit=limit,chars=chars),self.assertRaises(ValueError):
                inspection.inspect_evidence(fixture(),limit,chars)

    def test_bad_schema_and_required_fields(self):
        for key in ("inputs","candidates","identity_comparison"):
            evidence=fixture()
            del evidence[key]
            with self.subTest(key=key),self.assertRaises(ValueError):
                inspection.inspect_evidence(evidence)
        for version in (2,True,"1"):
            evidence=fixture()
            evidence["schema_version"]=version
            with self.subTest(version=version),self.assertRaises(ValueError):
                inspection.inspect_evidence(evidence)

    def test_missing_candidate_fields(self):
        for key in ("candidate_index","candidate","window","events","matched_event_count","counts_by_modality","evidence_coverage"):
            evidence=fixture()
            del evidence["candidates"][0][key]
            with self.subTest(key=key),self.assertRaises(ValueError):
                inspection.inspect_evidence(evidence)

    def test_invalid_counts(self):
        for count in (-1,True,4.0,99):
            evidence=fixture()
            evidence["candidates"][0]["matched_event_count"]=count
            with self.subTest(count=count),self.assertRaises(ValueError):
                inspection.inspect_evidence(evidence)
        evidence=fixture()
        evidence["candidates"][0]["counts_by_modality"]["audio"]=2.0
        with self.assertRaises(ValueError):
            inspection.inspect_evidence(evidence)

    def test_invalid_times(self):
        for value in (-1,True,"0",float("nan"),11):
            evidence=fixture()
            evidence["candidates"][0]["candidate"]["start"]=value
            with self.subTest(value=value),self.assertRaises(ValueError):
                inspection.inspect_evidence(evidence)

    def test_missing_coverage_and_false_certainty(self):
        for mutation in ("missing","false"):
            evidence=fixture()
            coverage=evidence["candidates"][0]["evidence_coverage"]
            if mutation=="missing":
                del coverage["audio"]
            else:
                coverage["audio"]["temporal_coverage"]="complete"
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                inspection.inspect_evidence(evidence)

    def test_bad_event_structure_and_payload(self):
        for mutation in ("modality","payload","timestamp","type","text"):
            evidence=fixture()
            event=evidence["candidates"][0]["events"][0]
            if mutation=="payload":
                event["payload"]=[]
            elif mutation=="timestamp":
                event["start_seconds"]=float("inf")
            elif mutation=="type":
                event["event_type"]="unsupported"
            elif mutation=="text":
                event["payload"]["text"]=None
            else:
                event["modality"]="other"
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                inspection.inspect_evidence(evidence)

    def test_bad_visual_prediction(self):
        evidence=fixture(False,False,False,True)
        evidence["candidates"][2]["events"][0]["payload"]["top3"][0]["confidence"]=2
        with self.assertRaises(ValueError):
            inspection.inspect_evidence(evidence)

    def test_identity_claim_not_upgraded(self):
        evidence=fixture()
        result=inspection.inspect_evidence(evidence)
        self.assertEqual(result["identity_comparison"],evidence["identity_comparison"])
        evidence["identity_comparison"]="verified"
        with self.assertRaises(ValueError):
            inspection.inspect_evidence(evidence)


class CliTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.path=self.root/"evidence.json"
        self.path.write_text(json.dumps(fixture()),encoding="utf-8")

    def run_cli(self,*extra):
        out,err=io.StringIO(),io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            code=inspection.main(["--evidence",str(self.path),*extra])
        return code,out.getvalue(),err.getvalue()

    def test_terminal_output_no_writes(self):
        before=(self.path.read_bytes(),self.path.stat().st_mtime_ns)
        code,out,err=self.run_cli()
        self.assertEqual(code,0)
        self.assertIn("Candidates: 5",out)
        self.assertIn("Original scores:",out)
        self.assertIn("temporal coverage: unknown",out)
        self.assertEqual(err,"")
        self.assertEqual(before,(self.path.read_bytes(),self.path.stat().st_mtime_ns))
        self.assertEqual(list(self.root.iterdir()),[self.path])

    def test_json_output_and_preview_flags(self):
        code,out,err=self.run_cli("--format","json","--preview-limit","1","--preview-chars","5")
        self.assertEqual(code,0)
        result=json.loads(out)
        self.assertEqual(result["candidate_count"],5)
        self.assertEqual(len(result["candidates"][0]["previews"]["transcript"]["items"][0]["text"]),5)
        self.assertEqual(err,"")

    def test_missing_and_malformed_file(self):
        self.path.write_text("{}")
        code,out,err=self.run_cli()
        self.assertEqual(code,1)
        self.assertEqual(out,"")
        self.assertIn("FAIL:",err)
        self.path.unlink()
        self.assertEqual(self.run_cli()[0],1)

    def test_import_safety_isolated(self):
        code = """
import builtins, sys
def audit(event, args):
    if event == 'open' and (isinstance(args[1],str) and any(c in args[1] for c in 'wax+') or isinstance(args[2],int) and args[2] & 3):
        raise AssertionError('write')
    if event in ('os.mkdir','subprocess.Popen','os.system'):
        raise AssertionError(event)
sys.addaudithook(audit)
original = builtins.__import__
def guarded(name,*args,**kwargs):
    if name.split('.')[0] in ('torch','transformers','numpy','faster_whisper'):
        raise AssertionError('heavy import')
    return original(name,*args,**kwargs)
builtins.__import__ = guarded
import inspect_candidate_evidence
"""
        result=subprocess.run([sys.executable,"-B","-c",code],cwd=Path(inspection.__file__).parent,
                              capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout,"")
        self.assertEqual(result.stderr,"")


if __name__ == "__main__":
    unittest.main()
