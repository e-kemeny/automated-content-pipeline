"""Mocked contextual language tests; no model imports or inference."""
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from shared_analysis import create_analysis, load_analysis, save_analysis, signal, validate_analysis
from language_scoring import LANGUAGE_SIGNALS, apply_results, context_prompt, contract, parse_scores, score_segments, smoke_test
import score_language as cli

SCORES=dict(relevance=0.8,humor=0.2,reaction=0.6,narrative_context=0.4)
RAW=json.dumps(SCORES)
SEGMENTS=[dict(start=0.0,end=2.0,text=" Intro unchanged. "),dict(start=2.0,end=4.0,text="Oh wow!"),dict(start=5.0,end=7.0,text="Next pack.")]

class LanguageTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.path=self.root/"analysis.json"
        self.analysis=create_analysis(dict(path="videos/fixture.mp4",duration_seconds=10))
        self.analysis["transcript"]=signal(SEGMENTS,dict(model="fixture"))
        self.analysis["visual"]["scene_changes"]=signal([dict(time=3,score=12)])
        self.analysis["candidate_windows"]=signal([dict(start=0,end=10,second=5,duration=10)])
        save_analysis(self.analysis,self.path)
        self.backend=Mock(return_value=RAW)
        self.backend.provenance=dict(model_id=contract()["model_id"],model_revision=contract()["model_revision"],device="cpu",library_version="fixture",model_setup_seconds=1)
        self.factory=Mock(return_value=self.backend)

    def update(self,**kwargs):
        return cli.update_language(self.path,factory=self.factory,require_smoke=False,**kwargs)

    def test_four_independent_scores(self):
        self.assertEqual(parse_scores(RAW),SCORES)
        updated,_=self.update()
        for name in LANGUAGE_SIGNALS:
            self.assertEqual(updated["language"][name]["data"][0]["score"],SCORES[name])

    def test_context(self):
        p=json.loads(context_prompt(SEGMENTS,1))
        self.assertEqual(p["previous"],SEGMENTS[0]["text"])
        self.assertEqual(p["target"],SEGMENTS[1]["text"])
        self.assertEqual(p["next"],SEGMENTS[2]["text"])
        self.assertEqual(set(p),{"topic","previous","target","next"})
        self.assertIsNone(json.loads(context_prompt(SEGMENTS,0))["previous"])
        self.assertIsNone(json.loads(context_prompt(SEGMENTS,2))["next"])

    def test_strict_parsing(self):
        cases=["","[]","null","text "+RAW,chr(96)*3+RAW+chr(96)*3,json.dumps(dict(SCORES,extra=1)),json.dumps({"relevance":0.5}),'{"relevance":0.2,"relevance":0.3,"humor":0,"reaction":0,"narrative_context":0}']
        for raw in cases:
            with self.subTest(raw=raw),self.assertRaises(ValueError):
                parse_scores(raw)

    def test_numeric_validation(self):
        for value in [True,False,None,"0.5",-0.1,1.1,float("nan"),float("inf"),float("-inf"),10**500]:
            with self.subTest(value=value),self.assertRaises(ValueError):
                parse_scores(json.dumps(dict(SCORES,humor=value)))
        for value in [0,1,0.5]:
            self.assertEqual(parse_scores(json.dumps(dict(SCORES,humor=value)))["humor"],value)
        with self.assertRaises(ValueError):
            parse_scores(RAW.replace("0.8","1e999"))

    def test_invalid_output(self):
        r=score_segments(SEGMENTS,Mock(return_value="broken"))[0]
        self.assertEqual(r["status"],"invalid_output")
        self.assertEqual(r["raw_output"],"broken")
        self.assertIsNone(r["scores"])
        self.assertTrue(r["failure_reason"])

    def test_inference_exception(self):
        r=score_segments(SEGMENTS,Mock(side_effect=RuntimeError("OOM")))[0]
        self.assertEqual(r["status"],"inference_error")
        self.assertIsNone(r["raw_output"])
        self.assertIsNone(r["scores"])
        self.assertIn("OOM",r["failure_reason"])

    def test_partial_failure(self):
        self.backend.side_effect=[RAW,"broken",RuntimeError("error")]
        result,_=self.update()
        for s in result["language"].values():
            self.assertEqual(s["status"],"partial")
            self.assertEqual(s["provenance"]["counts"],dict(scored=1,invalid_output=1,inference_error=1))
            self.assertIsNone(s["data"][1]["score"])

    def test_all_failed(self):
        self.backend.return_value="broken"
        result,_=self.update()
        self.assertTrue(all(s["status"]=="failed" for s in result["language"].values()))

    def test_setup_failure(self):
        self.factory.side_effect=RuntimeError("unavailable")
        result,_=self.update()
        self.assertEqual(result["language"]["humor"]["status"],"failed")
        self.assertIn("unavailable",result["language"]["humor"]["provenance"]["setup_error"])
        self.backend.assert_not_called()

    def test_silence_analyzed_empty(self):
        self.analysis["transcript"]=signal([])
        save_analysis(self.analysis,self.path)
        result,_=self.update()
        self.factory.assert_not_called()
        for s in result["language"].values():
            self.assertEqual(s["status"],"analyzed")
            self.assertEqual(s["data"],[])
            self.assertEqual(s["provenance"]["completion"],"empty")

    def test_missing_transcript(self):
        self.analysis["transcript"]=signal()
        save_analysis(self.analysis,self.path)
        with self.assertRaises(ValueError):
            self.update()
        self.factory.assert_not_called()

    def test_cache_no_inference_write(self):
        self.update()
        self.factory.reset_mock()
        before=self.path.read_bytes()
        _,reused=self.update()
        self.assertTrue(reused)
        self.factory.assert_not_called()
        self.assertEqual(before,self.path.read_bytes())

    def test_partial_cache_no_retry(self):
        self.backend.side_effect=[RAW,"broken",RAW]
        first,_=self.update()
        self.factory.reset_mock()
        second,reused=self.update()
        self.assertTrue(reused)
        self.factory.assert_not_called()
        self.assertEqual(first,second)

    def test_force_only_language(self):
        self.update()
        before=load_analysis(self.path)
        self.factory.reset_mock()
        self.backend.return_value=json.dumps(dict(SCORES,humor=0.9))
        result,reused=self.update(force=True)
        self.assertFalse(reused)
        self.factory.assert_called_once()
        self.assertEqual(result["language"]["humor"]["data"][0]["score"],0.9)
        for key in before:
            if key!="language":
                self.assertEqual(before[key],result[key])

    def test_changed_transcript_requires_force(self):
        self.update()
        result=load_analysis(self.path)
        result["transcript"]["data"][0]["text"]="changed"
        save_analysis(result,self.path)
        self.factory.reset_mock()
        with self.assertRaisesRegex(ValueError,"--force"):
            self.update()
        self.factory.assert_not_called()

    def test_preservation(self):
        result,_=self.update()
        for key in self.analysis:
            if key!="language":
                self.assertEqual(result[key],self.analysis[key])
        for s in result["language"].values():
            for original,row in zip(SEGMENTS,s["data"]):
                for key in ("start","end","text"):
                    self.assertEqual(original[key],row[key])

    def test_provenance(self):
        result,_=self.update()
        p=result["language"]["relevance"]["provenance"]
        for key in ("model_id","model_revision","device","library_version","model_setup_seconds","system_prompt","generation","input_signature","inference_seconds","processing_seconds"):
            self.assertIn(key,p)

    def test_legacy_and_version(self):
        legacy=deepcopy(self.analysis)
        legacy["language"]["humor"]=signal([dict(start=0,end=2,score=0.3,note="legacy",status="human_reviewed")])
        self.assertEqual(validate_analysis(legacy),legacy)
        legacy["schema_version"]=2
        self.path.write_text(json.dumps(legacy))
        with self.assertRaises(ValueError):
            self.update()
        self.factory.assert_not_called()

    def test_schema_completion_and_score_validation(self):
        result,_=self.update()
        bad=deepcopy(result)
        bad["language"]["humor"]["status"]="failed"
        with self.assertRaises(ValueError):
            validate_analysis(bad)
        for value in [-1,True,None,1.01]:
            bad=deepcopy(result)
            bad["language"]["humor"]["data"][0]["score"]=value
            with self.assertRaises(ValueError):
                validate_analysis(bad)
        bad=deepcopy(self.analysis)
        bad["visual"]["motion"]["status"]="partial"
        with self.assertRaises(ValueError):
            validate_analysis(bad)

    def test_deterministic_roundtrip(self):
        result,_=self.update()
        before=self.path.read_bytes()
        save_analysis(load_analysis(self.path),self.path)
        self.assertEqual(before,self.path.read_bytes())
        self.assertEqual(result,load_analysis(self.path))
        self.assertEqual(list(self.root.glob(".language_*")),[])

    def test_smoke_gate(self):
        with self.assertRaises(FileNotFoundError):
            cli.update_language(self.path,factory=self.factory)
        self.factory.assert_not_called()
        report=smoke_test(self.backend)
        self.assertTrue(report["passed"])
        (self.root/"language_smoke_v1.json").write_text(json.dumps(report))
        cli.update_language(self.path,factory=self.factory)
        self.factory.assert_called_once()

    def test_invalid_smoke_gate(self):
        report=smoke_test(Mock(return_value="broken"))
        self.assertFalse(report["passed"])
        (self.root/"language_smoke_v1.json").write_text(json.dumps(report))
        with self.assertRaises(ValueError):
            cli.update_language(self.path,factory=self.factory)
        self.factory.assert_not_called()

    def test_cli_force_single_pass(self):
        result,_=self.update()
        with patch.object(cli,"update_language",return_value=(result,False)) as update,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["--analysis",str(self.path),"--force"]),0)
        update.assert_called_once_with(self.path,force=True)

    def test_concurrent_analysis_change_not_overwritten(self):
        changed=deepcopy(self.analysis)
        changed["visual"]["scene_changes"]=signal([])
        def inference(prompt):
            save_analysis(changed,self.path)
            return RAW
        self.backend.side_effect=inference
        with self.assertRaisesRegex(RuntimeError,"Analysis changed"):
            self.update()
        self.assertEqual(load_analysis(self.path),changed)

    def test_atomic_failure(self):
        before=self.path.read_bytes()
        with patch.object(cli,"save_analysis",side_effect=OSError("write")),self.assertRaises(OSError):
            self.update()
        self.assertEqual(before,self.path.read_bytes())
        self.assertEqual(list(self.root.glob(".language_*")),[])

if __name__=="__main__":
    unittest.main()
