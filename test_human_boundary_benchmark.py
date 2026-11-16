"""Validate the preserved real human fixture; no media or inference required."""
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import human_boundary_benchmark as benchmark


class BenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=benchmark.DEFAULT
        cls.plan=json.loads((root/"evaluation_plan.json").read_text())
        cls.manifest=json.loads((root/"export_manifest.json").read_text())
        cls.rows=json.loads((root/"human_reviews.json").read_text())

    def test_all_reviews_and_pairs(self):
        r=benchmark.load_benchmark()
        self.assertEqual(r["coverage"],dict(reviewed_clips=20,valid_rated_pairs=15,incomplete_evaluations=[]))
        self.assertEqual(len(r["per_candidate_pairs"]),15)

    def test_exact_means_and_differences(self):
        r=benchmark.load_benchmark()
        for name,expected in dict(original=(3.8,4.8,3.8),earlier=(3.6,4.4,3.6),
                                  later=(4.0,4.4,4.2),both=(3.6,4.2,3.8)).items():
            self.assertEqual(tuple(r["means"][name][m] for m in benchmark.METRICS),expected)
        for name,expected in dict(earlier=(-.2,-.4,-.2),later=(.2,-.4,.4),both=(-.2,-.6,0)).items():
            self.assertEqual(tuple(r["paired_differences"][name][m] for m in benchmark.METRICS),expected)

    def test_preferences_separate(self):
        r=benchmark.load_benchmark()
        self.assertEqual([(p["start"],p["end"]) for p in r["human_preferences"]],
                         [(30,48),(56,77),(74,89),(136,151),(160,178)])
        self.assertTrue(r["human_preferences"][2]["provisional"])
        self.assertIn("NOT a perfect",r["human_preferences"][0]["notes"])

    def test_all_fields_and_mapping_preserved(self):
        reviews=benchmark.import_reviews(self.plan,self.manifest,self.rows)
        by_id={r["clip_id"]:r for r in reviews["clips"]}
        for row in self.rows:
            candidate=self.plan["candidates"][row["candidate_index"]]
            variant=next(v for v in candidate["variants"] if v["label"]==benchmark.LABELS[row["variant"]])
            imported=by_id[variant["clip_id"]]
            for k in ("ratings","starts","ends","notes"):
                self.assertEqual(imported[k],row[k])

    def test_missing_duplicate_or_unknown_variant(self):
        for mode in ("missing","duplicate","unknown"):
            rows=deepcopy(self.rows)
            if mode=="missing": rows.pop()
            elif mode=="duplicate": rows[-1]=deepcopy(rows[0])
            else: rows[0]["variant"]="narrative"
            with self.subTest(mode=mode),self.assertRaises(ValueError):
                benchmark.import_reviews(self.plan,self.manifest,rows)

    def test_malformed_and_incomplete(self):
        for value in (None,True,0,6,"5"):
            rows=deepcopy(self.rows)
            rows[0]["ratings"]["pacing"]=value
            with self.subTest(value=value),self.assertRaises(ValueError):
                benchmark.import_reviews(self.plan,self.manifest,rows)
        rows=deepcopy(self.rows); rows[0]["ends"]="wrong"
        with self.assertRaises(ValueError): benchmark.import_reviews(self.plan,self.manifest,rows)

    def test_source_conflict(self):
        plan=deepcopy(self.plan)
        plan["source_identity"]["digest"]="b"*64
        with self.assertRaises(ValueError): benchmark.import_reviews(plan,self.manifest,self.rows)

    def test_manifest_mismatch_duplicate_and_missing(self):
        for mode in ("identity","duplicate","missing","mapping"):
            m=deepcopy(self.manifest)
            if mode=="identity": m["plan_id"]="wrong"
            elif mode=="duplicate": m["clips"][-1]=deepcopy(m["clips"][0])
            elif mode=="missing": m["clips"].pop()
            else: m["clips"][0]["references"][0]["candidate_index"]=4
            with self.subTest(mode=mode),self.assertRaises(ValueError):
                benchmark.import_reviews(self.plan,m,self.rows)

    def test_deterministic_no_mutation(self):
        before=deepcopy((self.plan,self.manifest,self.rows))
        self.assertEqual(benchmark.load_benchmark(),benchmark.load_benchmark())
        self.assertEqual(before,(self.plan,self.manifest,self.rows))

    def test_readonly_cli(self):
        root=benchmark.DEFAULT
        before={p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in root.iterdir() if p.is_file()}
        with patch("subprocess.run",side_effect=AssertionError("No processing")),contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(benchmark.main([]),0)
        self.assertEqual(json.loads(out.getvalue())["coverage"]["valid_rated_pairs"],15)
        self.assertEqual(before,{p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in root.iterdir() if p.is_file()})

    def test_checksum_tamper_and_missing_file(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for p in benchmark.DEFAULT.iterdir():
                if p.is_file(): (root/p.name).write_bytes(p.read_bytes())
            (root/"human_reviews.json").write_text("[]")
            with self.assertRaises(ValueError): benchmark.load_benchmark(root)
            (root/"human_reviews.json").unlink()
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(benchmark.main(["--benchmark",str(root)]),1)


if __name__=="__main__":
    unittest.main()
