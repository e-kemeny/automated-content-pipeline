"""Synthetic persisted-schema fixtures; no media, models or subprocesses."""
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from shared_analysis import create_analysis, signal
from multimodal_timeline import build_timeline
import candidate_evidence as evidence


def fixture():
    analysis = create_analysis(dict(path="fixture.mp4", duration_seconds=20, sha256="a"*64))
    analysis["candidate_windows"] = signal([
        dict(id="first", rank=2, start=5, end=10, second=7, score=3),
        dict(id="second", rank=1, start=15, end=18, second=16, score=5)],
        dict(detector="Audio-only", variant="fixed"))
    analysis["acoustic"]["audio_activity"] = signal([dict(second=t, score=2) for t in (5,7,7,10)])
    analysis["transcript"] = signal([dict(start=1, end=5, text=" Touching "),
                                      dict(start=10, end=12, text="Other boundary")])
    return analysis, build_timeline(analysis=analysis)


class EvidenceTests(unittest.TestCase):
    def test_normal_extraction_order_and_metadata(self):
        analysis, timeline = fixture()
        original = deepcopy((analysis, timeline))
        result = evidence.build_candidate_evidence(analysis,timeline)
        self.assertEqual([r["candidate"] for r in result["candidates"]],analysis["candidate_windows"]["data"])
        self.assertEqual(result["inputs"]["candidates"]["source_video"],analysis["source_video"])
        self.assertEqual(result["inputs"]["candidates"]["provenance"],analysis["candidate_windows"]["provenance"])
        self.assertEqual(result["inputs"]["timeline"]["sources"],timeline["sources"])
        self.assertEqual(result["identity_comparison"],"consistent_reported_sha256")
        self.assertEqual((analysis,timeline),original)
        result["candidates"][0]["candidate"]["score"] = 999
        self.assertEqual((analysis,timeline),original)

    def test_boundaries_duplicates_event_order(self):
        analysis, timeline = fixture()
        result = evidence.build_candidate_evidence(analysis,timeline)["candidates"][0]
        self.assertEqual(result["matched_event_count"],6)
        self.assertEqual(result["counts_by_modality"],dict(audio=4,visual=0,transcript=2))
        self.assertEqual(result["events"],timeline["events"])

    def test_empty_window_is_not_negative_evidence(self):
        analysis, timeline = fixture()
        report = evidence.build_candidate_evidence(analysis,timeline)["candidates"][1]
        self.assertEqual(report["events"],[])
        self.assertEqual(report["evidence_coverage"]["audio"]["observation_status"],"no_events_in_window")
        self.assertEqual(report["evidence_coverage"]["audio"]["temporal_coverage"],"unknown")
        self.assertEqual(report["evidence_coverage"]["visual"]["observation_status"],"not_established")

    def test_absent_modality_distinguished(self):
        analysis, _ = fixture()
        timeline = build_timeline(transcript=dict(segments=[],provenance={}))
        report = evidence.build_candidate_evidence(analysis,timeline)
        coverage = report["candidates"][0]["evidence_coverage"]
        self.assertEqual(coverage["audio"]["observation_status"],"absent_from_timeline")
        self.assertEqual(coverage["transcript"]["observation_status"],"no_events_in_window")
        self.assertEqual(report["identity_comparison"],"unverified_missing_source_digest")
        self.assertEqual(report["inputs"]["timeline"]["identity_status"],"unverified_single_artifact")

    def test_analyzed_empty_candidates(self):
        analysis,timeline = fixture()
        analysis["candidate_windows"]["data"] = []
        self.assertEqual(evidence.build_candidate_evidence(analysis,timeline)["candidates"],[])

    def test_missing_candidates_and_wrong_format(self):
        analysis,timeline = fixture()
        analysis["candidate_windows"] = signal()
        for invalid in (analysis,{},[],{"clips":[]}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                evidence.build_candidate_evidence(invalid,timeline)

    def test_conflicting_identity_fields(self):
        for field,value in (("sha256","b"*64),("duration_seconds",21),("width",160),
                            ("height",90),("fps",30),("size_bytes",123)):
            analysis,_ = fixture()
            analysis["source_video"].update(width=100,height=100,fps=24,size_bytes=100)
            timeline = build_timeline(analysis=analysis)
            analysis["source_video"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                evidence.build_candidate_evidence(analysis,timeline)

    def test_conflicting_candidate_provenance(self):
        analysis,timeline = fixture()
        analysis["candidate_windows"]["provenance"]["source_sha256"] = "b"*64
        with self.assertRaises(ValueError):
            evidence.build_candidate_evidence(analysis,timeline)

    def test_conflicting_timeline_provenance_without_header_digest(self):
        analysis,_ = fixture()
        timeline = build_timeline(transcript=dict(segments=[],provenance={"source_sha256":"b"*64}))
        with self.assertRaises(ValueError):
            evidence.build_candidate_evidence(analysis,timeline)

    def test_path_is_not_identity(self):
        analysis,timeline = fixture()
        analysis["source_video"]["path"] = "different/location.mp4"
        self.assertEqual(evidence.build_candidate_evidence(analysis,timeline)["identity_comparison"],
                         "consistent_reported_sha256")

    def test_invalid_windows(self):
        for start,end in [(-1,10),(11,10),(0,21),(True,10),("5",10),(float("nan"),10),(5,float("inf"))]:
            analysis,timeline = fixture()
            analysis["candidate_windows"]["data"] = [dict(start=start,end=end)]
            with self.subTest(start=start,end=end),self.assertRaises(ValueError):
                evidence.build_candidate_evidence(analysis,timeline)

    def test_unordered_candidates_rejected_not_sorted(self):
        analysis,timeline = fixture()
        analysis["candidate_windows"]["data"].reverse()
        with self.assertRaises(ValueError):
            evidence.build_candidate_evidence(analysis,timeline)

    def test_versions_and_invalid_timeline(self):
        for target in ("analysis","timeline"):
            analysis,timeline = fixture()
            (analysis if target=="analysis" else timeline)["schema_version"] = 99
            with self.subTest(target=target),self.assertRaises(ValueError):
                evidence.build_candidate_evidence(analysis,timeline)
        analysis,timeline = fixture()
        del timeline["events"][0]["payload"]
        with self.assertRaises(ValueError):
            evidence.build_candidate_evidence(analysis,timeline)

    def test_zero_length_window_and_duplicate_candidates(self):
        analysis,timeline = fixture()
        analysis["candidate_windows"]["data"] = [dict(start=5,end=5)]*2
        result = evidence.build_candidate_evidence(analysis,timeline)
        self.assertEqual(len(result["candidates"]),2)
        self.assertEqual(result["candidates"][0]["matched_event_count"],2)

    def test_no_media_access_or_inference(self):
        analysis,timeline = fixture()
        with patch("subprocess.Popen",side_effect=AssertionError("subprocess")), patch(
                "source_identity.file_identity",side_effect=AssertionError("rehash")):
            self.assertEqual(evidence.build_candidate_evidence(analysis,timeline)["schema_version"],1)


class CliTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.candidates,self.timeline,self.output = [self.root/name for name in ("c.json","t.json","report.json")]
        analysis,timeline = fixture()
        self.candidates.write_text(json.dumps(analysis),encoding="utf-8")
        self.timeline.write_text(json.dumps(timeline),encoding="utf-8")
        self.args = ["--candidates",str(self.candidates),"--timeline",str(self.timeline)]

    def run_cli(self,*extra):
        out,err = io.StringIO(),io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            code = evidence.main(self.args+list(extra))
        return code,out.getvalue(),err.getvalue()

    def test_default_stdout_no_writes(self):
        before = {p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in self.root.iterdir()}
        code,out,err = self.run_cli()
        self.assertEqual(code,0)
        self.assertEqual(json.loads(out)["report_type"],"candidate-evidence")
        self.assertEqual(len(out.splitlines()),1)
        self.assertEqual(err,"")
        self.assertEqual(before,{p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in self.root.iterdir()})

    def test_overwrite_and_deterministic_serialization(self):
        args = ("--output",str(self.output))
        self.assertEqual(self.run_cli(*args)[0],0)
        original = self.output.read_bytes()
        self.assertEqual(self.run_cli(*args)[0],1)
        self.assertEqual(self.output.read_bytes(),original)
        self.assertEqual(self.run_cli(*args,"--overwrite")[0],0)
        self.assertEqual(self.output.read_bytes(),original)

    def test_input_and_unrelated_output_protection(self):
        for path in (self.candidates,self.timeline):
            original = path.read_bytes()
            self.assertEqual(self.run_cli("--output",str(path),"--overwrite")[0],1)
            self.assertEqual(path.read_bytes(),original)
        self.output.write_text("{}")
        self.assertEqual(self.run_cli("--output",str(self.output),"--overwrite")[0],1)
        self.assertEqual(self.output.read_text(),"{}")

    def test_atomic_publication_failure(self):
        with patch("timeline_query.os.link",side_effect=OSError("failed publication")):
            self.assertEqual(self.run_cli("--output",str(self.output))[0],1)
        self.assertEqual(set(self.root.iterdir()),{self.candidates,self.timeline})

    def test_failed_replace_preserves_existing(self):
        self.run_cli("--output",str(self.output))
        original = self.output.read_bytes()
        with patch("timeline_query.os.replace",side_effect=OSError("failure")):
            self.assertEqual(self.run_cli("--output",str(self.output),"--overwrite")[0],1)
        self.assertEqual(self.output.read_bytes(),original)
        self.assertFalse(list(self.root.glob(".query-*")))

    def test_malformed_input_and_missing_file(self):
        self.candidates.write_text("{}")
        self.assertEqual(self.run_cli("--output",str(self.output))[0],1)
        self.assertFalse(self.output.exists())
        self.candidates.unlink()
        self.assertEqual(self.run_cli()[0],1)

    def test_overwrite_requires_output(self):
        with self.assertRaises(SystemExit) as error:
            self.run_cli("--overwrite")
        self.assertEqual(error.exception.code,2)


if __name__ == "__main__":
    unittest.main()
