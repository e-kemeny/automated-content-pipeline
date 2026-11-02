"""Timeline query tests use synthetic schema-valid observations only."""
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
import timeline_query as query


def fixture():
    analysis = create_analysis(dict(path="fixture.mp4", duration_seconds=20))
    analysis["acoustic"]["audio_activity"] = signal(
        [dict(second=t, score=1) for t in (2, 5, 7, 7, 10, 12)], {"detector":"fixture"})
    analysis["visual"]["scene_changes"] = signal([dict(time=7, score=3)])
    analysis["transcript"] = signal([dict(start=4, end=11, text=" Original text. ")])
    return build_timeline(analysis=analysis)


class QueryTests(unittest.TestCase):
    def test_points_and_boundaries(self):
        result = query.query_timeline(fixture(), 5, 10, "audio")
        self.assertEqual([e["start_seconds"] for e in result["events"]], [5, 7, 7, 10])

    def test_interval_overlap_cases(self):
        for start, end, expected in [(5,10,True), (3,5,True), (10,12,True),
                                     (0,20,True), (4,4,True), (11,11,True),
                                     (0,3,False), (12,20,False)]:
            with self.subTest(start=start, end=end):
                self.assertEqual(bool(query.query_timeline(fixture(), start, end, "transcript")["events"]), expected)

    def test_empty(self):
        self.assertEqual(query.query_timeline(fixture(), 15, 20)["matched_event_count"], 0)

    def test_modalities_and_counts(self):
        self.assertEqual(query.query_timeline(fixture(),5,10)["counts_by_modality"],
                         dict(audio=4, visual=1, transcript=1))
        for modality in query.MODALITIES:
            self.assertTrue(all(e["modality"] == modality for e in
                                query.query_timeline(fixture(),0,20,modality)["events"]))

    def test_bad_queries(self):
        for start, end in [(-1,2),(3,2),(0,21),(True,2),("1",2),
                           (float("nan"),2),(0,float("inf")),(0,None)]:
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                query.query_timeline(fixture(),start,end)
        with self.assertRaises(ValueError):
            query.query_timeline(fixture(),0,1,"other")

    def test_unknown_duration(self):
        timeline = build_timeline(transcript=dict(segments=[], provenance={}))
        self.assertEqual(query.query_timeline(timeline,100,200)["events"], [])

    def test_invalid_schema(self):
        timeline = fixture()
        timeline["schema_version"] = 99
        with self.assertRaises(ValueError):
            query.query_timeline(timeline,0,1)

    def test_malformed_unselected_event(self):
        timeline = fixture()
        del timeline["events"][-1]["start_seconds"]
        with self.assertRaises(ValueError):
            query.query_timeline(timeline,0,1)

    def test_order_duplicates_payload_provenance_and_identity(self):
        timeline = fixture()
        original = deepcopy(timeline)
        result = query.query_timeline(timeline,0,20)
        self.assertEqual(result["events"], original["events"])
        self.assertEqual(result["sources"], original["sources"])
        self.assertEqual(result["identity_status"], original["identity_status"])
        self.assertEqual(result["timeline_schema_version"], 1)
        self.assertEqual(len(result["events"]), 8)
        result["events"][0]["payload"]["score"] = 999
        self.assertEqual(timeline, original)

    def test_unsorted_events_rejected_not_repaired(self):
        timeline = fixture()
        timeline["events"].reverse()
        with self.assertRaises(ValueError):
            query.query_timeline(timeline,0,20)


class QueryCliTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.input = self.root/"timeline.json"
        self.input.write_text(json.dumps(fixture()), encoding="utf-8")
        self.output = self.root/"result.json"
        self.args = ["--timeline",str(self.input),"--start","5","--end","10"]

    def run_cli(self, *extra):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = query.main(self.args + list(extra))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_stdout_only(self):
        before = list(self.root.iterdir())
        code, stdout, stderr = self.run_cli()
        self.assertEqual(code,0)
        self.assertEqual(json.loads(stdout)["matched_event_count"],6)
        self.assertEqual(len(stdout.splitlines()),1)
        self.assertEqual(stderr,"")
        self.assertEqual(list(self.root.iterdir()),before)

    def test_output_and_overwrite(self):
        args = ("--output",str(self.output))
        self.assertEqual(self.run_cli(*args)[0],0)
        original = self.output.read_bytes()
        self.assertEqual(self.run_cli(*args)[0],1)
        self.assertEqual(self.output.read_bytes(),original)
        self.assertEqual(self.run_cli(*args,"--overwrite")[0],0)
        self.assertEqual(self.output.read_bytes(),original)

    def test_atomic_publication(self):
        real_link = query.os.link
        def check(source, destination):
            self.assertFalse(Path(destination).exists())
            self.assertEqual(json.loads(Path(source).read_text())["matched_event_count"],6)
            real_link(source,destination)
        with patch.object(query.os,"link",side_effect=check) as mocked:
            self.assertEqual(self.run_cli("--output",str(self.output))[0],0)
            mocked.assert_called_once()
        self.assertEqual(sorted(p.name for p in self.root.iterdir()),["result.json","timeline.json"])

    def test_failed_publication_cleanup(self):
        with patch.object(query.os,"link",side_effect=OSError("fixture failure")):
            self.assertEqual(self.run_cli("--output",str(self.output))[0],1)
        self.assertEqual(list(self.root.iterdir()),[self.input])

    def test_failed_replace_preserves_previous(self):
        self.output.write_text("original")
        with patch.object(query.os,"replace",side_effect=OSError("fixture failure")):
            self.assertEqual(self.run_cli("--output",str(self.output),"--overwrite")[0],1)
        self.assertEqual(self.output.read_text(),"original")
        self.assertFalse(list(self.root.glob(".query-*")))

    def test_input_protection(self):
        original = self.input.read_bytes()
        self.assertEqual(self.run_cli("--output",str(self.input),"--overwrite")[0],1)
        self.assertEqual(self.input.read_bytes(),original)

    def test_missing_and_malformed_input(self):
        self.input.write_text("{}")
        self.assertEqual(self.run_cli("--output",str(self.output))[0],1)
        self.assertFalse(self.output.exists())
        self.input.unlink()
        self.assertEqual(self.run_cli()[0],1)

    def test_invalid_cli_options(self):
        for extra in [("--modality","other"),("--overwrite",)]:
            with self.subTest(extra=extra), self.assertRaises(SystemExit) as error:
                self.run_cli(*extra)
            self.assertEqual(error.exception.code,2)

    def test_no_subprocess_or_heavy_imports(self):
        import builtins
        import importlib
        original_import = builtins.__import__
        def guarded(name, *args, **kwargs):
            if name.split(".")[0] in {"torch","numpy","transformers","faster_whisper","cv2"}:
                raise AssertionError("Heavy dependency imported")
            return original_import(name,*args,**kwargs)
        with patch("builtins.__import__",side_effect=guarded), patch("subprocess.Popen",side_effect=AssertionError("Subprocess")):
            importlib.reload(query)
            self.assertEqual(self.run_cli()[0],0)


if __name__ == "__main__":
    unittest.main()
