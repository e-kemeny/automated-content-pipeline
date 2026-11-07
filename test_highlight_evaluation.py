"""Synthetic human-rating fixtures; no real ratings are assigned."""
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

import highlight_evaluation as evaluation
from shared_analysis import create_analysis,signal
from multimodal_timeline import build_timeline
from candidate_evidence import build_candidate_evidence


def fixture(scores=(30,20,10)):
    a=create_analysis(dict(path="fixture.mp4",duration_seconds=30,sha256="a"*64))
    a["candidate_windows"]=signal([dict(id=f"original-{i}",second=i*10+5,start=i*10,end=i*10+10,score=s)
                                  for i,s in enumerate(scores)],
                                 dict(detector="Audio-only",variant="fixed",k=len(scores)))
    return a


def rated(a,values):
    result=evaluation.create_template(a)
    for row,value in zip(result["candidates"],values):
        row["human_rating"]=value
    return result


class EvaluationTests(unittest.TestCase):
    def test_actual_schema_template_null_and_original_values(self):
        a=fixture()
        original=deepcopy(a)
        template=evaluation.create_template(a)
        self.assertEqual([r["original_candidate"] for r in template["candidates"]],a["candidate_windows"]["data"])
        self.assertEqual([r["original_score"] for r in template["candidates"]],[30,20,10])
        self.assertTrue(all(r["human_rating"] is None for r in template["candidates"]))
        self.assertEqual(len({r["candidate_id"] for r in template["candidates"]}),3)
        self.assertEqual(a,original)

    def test_pairwise_agreement_and_individual_disagreements(self):
        a=fixture()
        result=evaluation.evaluate_ratings(a,rated(a,[5,1,3]))
        metrics=result["metrics"]
        self.assertEqual(metrics["pairwise_agreement"],2/3)
        self.assertEqual(metrics["strict_pair_count"],3)
        self.assertEqual(metrics["mean_human_rating"],3)
        self.assertEqual(metrics["human_preferred_order"],[[0],[2],[1]])
        self.assertEqual(result["candidates"][1]["disagrees_with_candidate_indices"],[2])
        self.assertEqual(result["candidates"][2]["disagrees_with_candidate_indices"],[1])

    def test_null_is_missing(self):
        a=fixture()
        metrics=evaluation.evaluate_ratings(a,rated(a,[5,None,1]))["metrics"]
        self.assertEqual((metrics["rated"],metrics["unrated"],metrics["mean_human_rating"]),(2,1,3))
        self.assertEqual(metrics["pair_counts"]["unrated"],2)
        self.assertEqual(metrics["strict_pair_count"],1)

    def test_all_unrated_and_empty(self):
        for a in (fixture(),fixture(())):
            result=evaluation.evaluate_ratings(a,evaluation.create_template(a))
            self.assertIsNone(result["metrics"]["mean_human_rating"])
            self.assertIsNone(result["metrics"]["pairwise_agreement"])
            self.assertEqual(result["metrics"]["human_preferred_order"],[])

    def test_invalid_ratings(self):
        a=fixture()
        for value in (0,6,-1,True,3.0,"3",float("nan")):
            with self.subTest(value=value),self.assertRaises(ValueError):
                evaluation.evaluate_ratings(a,rated(a,[value,2,3]))

    def test_score_and_human_ties(self):
        a=fixture((30,30,10))
        metrics=evaluation.evaluate_ratings(a,rated(a,[5,4,4]))["metrics"]
        self.assertEqual(metrics["pair_counts"]["original_tie"],1)
        self.assertEqual(metrics["pair_counts"]["human_tie"],1)
        self.assertEqual(metrics["pairwise_agreement"],1)
        self.assertEqual(metrics["strict_pair_count"],1)
        self.assertEqual(metrics["original_score_order"],[[0,1],[2]])
        self.assertEqual(metrics["human_preferred_order"],[[0],[1,2]])

    def test_both_tied_no_denominator(self):
        a=fixture((10,10))
        metrics=evaluation.evaluate_ratings(a,rated(a,[3,3]))["metrics"]
        self.assertEqual(metrics["pair_counts"]["both_tied"],1)
        self.assertIsNone(metrics["pairwise_agreement"])

    def test_duplicate_windows_rejected(self):
        a=fixture()
        a["candidate_windows"]["data"][1]=deepcopy(a["candidate_windows"]["data"][0])
        with self.assertRaisesRegex(ValueError,"Duplicate"):
            evaluation.create_template(a)

    def test_order_not_assumed_ranking(self):
        a=fixture((1,3,2))
        metrics=evaluation.evaluate_ratings(a,rated(a,[1,3,2]))["metrics"]
        self.assertEqual(metrics["original_candidate_order"],[0,1,2])
        self.assertEqual(metrics["original_score_order"],[[1],[2],[0]])
        self.assertEqual(metrics["pairwise_agreement"],1)

    def test_unknown_provenance_prevents_ranking(self):
        a=fixture()
        a["candidate_windows"]["provenance"]={}
        result=evaluation.evaluate_ratings(a,rated(a,[1,5,3]))
        self.assertIsNone(result["metrics"]["pairwise_agreement"])
        self.assertEqual(result["metrics"]["pair_counts"]["incomparable"],3)
        self.assertEqual(result["metrics"]["original_score_order"],[])
        self.assertEqual(result["metrics"]["mean_human_rating"],3)

    def test_missing_or_mixed_scores_incomparable(self):
        for mode in ("missing","string","mixed"):
            a=fixture()
            row=a["candidate_windows"]["data"][0]
            if mode=="missing": del row["score"]
            elif mode=="string": row["score"]="unknown"
            else: row["detector"]="Audio + Scene"
            result=evaluation.evaluate_ratings(a,rated(a,[5,3,1]))
            self.assertEqual(result["metrics"]["pair_counts"]["incomparable"],2)
            self.assertEqual(result["metrics"]["strict_pair_count"],1)

    def test_nonfinite_scores_rejected(self):
        a=fixture()
        a["candidate_windows"]["data"][0]["score"]=float("inf")
        with self.assertRaises(ValueError):
            evaluation.create_template(a)

    def test_tampered_template_fields(self):
        a=fixture()
        for mode in ("id","index","start","score","count","order","version","duplicate_id","provenance"):
            t=evaluation.create_template(a)
            if mode=="id": t["candidates"][0]["candidate_id"]="changed"
            elif mode=="index": t["candidates"][0]["candidate_index"]=True
            elif mode=="start": t["candidates"][0]["start"]=1
            elif mode=="score": t["candidates"][0]["original_score"]=999
            elif mode=="count": t["candidates"].pop()
            elif mode=="order": t["candidates"].reverse()
            elif mode=="version": t["schema_version"]=True
            elif mode=="duplicate_id": t["candidates"][1]["candidate_id"]=t["candidates"][0]["candidate_id"]
            else: t["candidate_provenance"]["detector"]="Audio + Scene"
            with self.subTest(mode=mode),self.assertRaises(ValueError):
                evaluation.evaluate_ratings(a,t)

    def test_missing_identity_explicit(self):
        a=fixture()
        del a["source_video"]["sha256"]
        t=evaluation.create_template(a)
        self.assertEqual(t["source_identity_status"],"unverified_missing_source_digest")
        self.assertEqual(evaluation.evaluate_ratings(a,t)["source_identity_status"],t["source_identity_status"])

    def test_conflicting_identity_and_provenance(self):
        a=fixture()
        t=evaluation.create_template(a)
        t["source_video"]["sha256"]="b"*64
        with self.assertRaises(ValueError):
            evaluation.evaluate_ratings(a,t)
        a["candidate_windows"]["provenance"]["source_sha256"]="b"*64
        with self.assertRaises(ValueError):
            evaluation.create_template(a)

    def test_path_is_informational(self):
        a=fixture()
        t=evaluation.create_template(a)
        a["source_video"]["path"]="relocated/fixture.mp4"
        result=evaluation.evaluate_ratings(a,t)
        self.assertEqual(result["source_video"]["path"],"relocated/fixture.mp4")
        self.assertEqual(evaluation.create_template(a)["candidate_set_sha256"],t["candidate_set_sha256"])

    def test_deterministic_no_mutation(self):
        a=fixture()
        t=rated(a,[1,2,3])
        original=deepcopy((a,t))
        first=evaluation.evaluate_ratings(a,t)
        self.assertEqual(first,evaluation.evaluate_ratings(a,t))
        first["candidates"][0]["original_candidate"]["score"]=999
        self.assertEqual((a,t),original)

    def test_evidence_preserves_provenance_and_unknown_coverage(self):
        a=fixture()
        evidence=build_candidate_evidence(a,build_timeline(analysis=a))
        result=evaluation.evaluate_ratings(a,rated(a,[1,2,3]),evidence)
        self.assertEqual(result["evidence_context"]["inputs"],evidence["inputs"])
        self.assertEqual(result["evidence_context"]["candidates"][0]["evidence_coverage"],
                         evidence["candidates"][0]["evidence_coverage"])

    def test_evidence_mismatch_rejected(self):
        a=fixture()
        other=fixture((3,2,1))
        evidence=build_candidate_evidence(other,build_timeline(analysis=other))
        with self.assertRaises(ValueError):
            evaluation.evaluate_ratings(a,evaluation.create_template(a),evidence)


class CliTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.analysis=self.root/"analysis.json"
        self.ratings=self.root/"ratings.json"
        self.report=self.root/"report.json"
        self.analysis.write_text(json.dumps(fixture()),encoding="utf-8")

    def run_cli(self,command="template",*extra):
        args=[command,"--analysis",str(self.analysis),"--output",str(self.ratings if command=="template" else self.report)]
        if command=="evaluate": args+=["--ratings",str(self.ratings)]
        out,err=io.StringIO(),io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            code=evaluation.main(args+list(extra))
        return code,out.getvalue(),err.getvalue()

    def test_cli_roundtrip_inputs_unchanged(self):
        self.assertEqual(self.run_cli()[0],0)
        before={p:(p.read_bytes(),p.stat().st_mtime_ns) for p in (self.analysis,self.ratings)}
        self.assertEqual(self.run_cli("evaluate")[0],0)
        self.assertEqual(json.loads(self.report.read_text())["metrics"]["rated"],0)
        self.assertEqual(before,{p:(p.read_bytes(),p.stat().st_mtime_ns) for p in before})

    def test_atomic_and_overwrite(self):
        real_link=evaluation.save_query.__globals__["os"].link
        def publish(source,destination):
            self.assertFalse(Path(destination).exists())
            self.assertEqual(json.loads(Path(source).read_text())["artifact_type"],"highlight-ratings")
            real_link(source,destination)
        with patch("timeline_query.os.link",side_effect=publish):
            self.assertEqual(self.run_cli()[0],0)
        original=self.ratings.read_bytes()
        self.assertEqual(self.run_cli()[0],1)
        self.assertEqual(self.run_cli("template","--overwrite")[0],0)
        self.assertEqual(self.ratings.read_bytes(),original)

    def test_publication_failure_cleanup(self):
        with patch("timeline_query.os.link",side_effect=OSError("failure")):
            self.assertEqual(self.run_cli()[0],1)
        self.assertEqual(list(self.root.iterdir()),[self.analysis])

    def test_failed_replacement_preserves_existing(self):
        self.run_cli()
        original=self.ratings.read_bytes()
        with patch("timeline_query.os.replace",side_effect=OSError("failure")):
            self.assertEqual(self.run_cli("template","--overwrite")[0],1)
        self.assertEqual(self.ratings.read_bytes(),original)
        self.assertFalse(list(self.root.glob(".query-*")))

    def test_input_and_unrelated_output_protection(self):
        original=self.analysis.read_bytes()
        self.assertEqual(self.run_cli("template","--output",str(self.analysis),"--overwrite")[0],1)
        self.assertEqual(self.analysis.read_bytes(),original)
        self.ratings.write_text("{}")
        self.assertEqual(self.run_cli("template","--overwrite")[0],1)

    def test_missing_and_malformed_input(self):
        self.analysis.write_text("{}")
        self.assertEqual(self.run_cli()[0],1)
        self.assertFalse(self.ratings.exists())
        self.analysis.unlink()
        self.assertEqual(self.run_cli()[0],1)

    def test_isolated_import_safety(self):
        code="""import sys
def audit(event,args):
    if event in ('subprocess.Popen','os.mkdir','os.remove'):
        raise AssertionError(event)
    if event=='open' and ((isinstance(args[1],str) and any(c in args[1] for c in 'wax+')) or args[2] & 3):
        raise AssertionError('write')
sys.addaudithook(audit)
import highlight_evaluation
assert not any(name in sys.modules for name in ('torch','transformers','faster_whisper'))
"""
        result=subprocess.run([sys.executable,"-B","-c",code],capture_output=True,text=True,cwd=Path(evaluation.__file__).parent)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout+result.stderr,"")


if __name__=="__main__":
    unittest.main()
