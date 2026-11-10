"""Synthetic phrase and persisted-timeline tests; no media, GPU or models."""
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

from shared_analysis import create_analysis, signal
from multimodal_timeline import build_timeline
import transcript_event_recognition as recognition


def fixture(texts=("I broke his bed.",), digest="a"*64):
    source = dict(path="synthetic.mp4",duration_seconds=100)
    if digest is not None:
        source["sha256"] = digest
    analysis = create_analysis(source)
    analysis["transcript"] = signal([dict(start=i*3,end=i*3+2,text=text) for i,text in enumerate(texts)],
                                    dict(backend="synthetic"))
    return build_timeline(analysis=analysis)


def categories(text):
    return [(r["event_type"],r["linguistic_classification"]) for r in recognition.classify_text(text)]


class PhraseTests(unittest.TestCase):
    def test_completed_vocabulary(self):
        for text,kind in (("I broke his bed","bed_destroyed"),("Their bed is gone","bed_destroyed"),
                ("We won the game","game_victory"),("I died","player_death"),
                ("I eliminated him","player_elimination"),("I respawned","respawn"),("Next game","game_transition"),
                ("We started the next game","game_transition")):
            with self.subTest(text=text):
                self.assertEqual(categories(text),[(kind,"asserted_completed")])

    def test_negation(self):
        for text in ("I didn't break his bed","We haven't won yet","I have not died","Their bed is not gone",
                     "I never respawned","I didn\u2019t kill him"):
            with self.subTest(text=text):
                self.assertTrue(categories(text))
                self.assertTrue(all(category=="negated" for _,category in categories(text)))

    def test_future(self):
        for text in ("I'm going to break their bed","I will eliminate him","I'm about to respawn","Next game I will win"):
            with self.subTest(text=text):
                self.assertTrue(categories(text))
                self.assertTrue(all(category=="hypothetical_future" for _,category in categories(text)))

    def test_hypotheticals(self):
        for text in ("If I win this game","If I died","Unless I respawn","When I break their bed"):
            with self.subTest(text=text):
                self.assertTrue(all(c=="hypothetical_future" for _,c in categories(text)))
                self.assertTrue(categories(text))

    def test_questions(self):
        for text in ("Did I kill him?","I died?","Did I break their bed","Have we won the game?"):
            with self.subTest(text=text):
                self.assertTrue(categories(text))
                self.assertTrue(all(c=="question" for _,c in categories(text)))

    def test_uncertainty(self):
        for text in ("I almost died","I think his bed is gone","Maybe we won the game","I nearly died","I respawned I guess"):
            with self.subTest(text=text):
                self.assertTrue(categories(text))
                self.assertTrue(all(c=="uncertain" for _,c in categories(text)))

    def test_ambiguous_and_everyday_speech_abstention(self):
        for text in ("bed win dead kill","Kill time before bed","I died laughing","I broke his bed while moving furniture",
                     "We won the game of chess","I love the bed break","Nice got the bed",
                     'He said "I died."',"I killed him in my story","I need a new bed","My phone is dead","I died and went to heaven","I broke his bed and moved the furniture"):
            with self.subTest(text=text):
                self.assertFalse(any(c=="asserted_completed" for _,c in categories(text)))

    def test_multiple_events_and_text_order(self):
        text="I died and I respawned. We won the game!"
        self.assertEqual(categories(text),[("player_death","asserted_completed"),("respawn","asserted_completed"),
                                           ("game_victory","asserted_completed")])
        for row in recognition.classify_text(text):
            start,end=row["evidence_span"]
            self.assertEqual(text[start:end],row["matched_clause"])

    def test_conservative_sentence_guard(self):
        self.assertEqual(categories("I didn't break his bed but I died."),
                         [("bed_destroyed","negated"),("player_death","negated")])
        self.assertEqual(categories("I didn't break his bed. I died.")[-1],("player_death","asserted_completed"))

    def test_normalization_without_mutating_evidence(self):
        text="  OH, I just BROKE their bed!  "
        timeline=fixture((text,))
        before=deepcopy(timeline)
        row=recognition.recognize_events(timeline)["hypotheses"][0]
        self.assertEqual(row["evidence_text"],text)
        self.assertEqual(timeline,before)

    def test_unmatched_and_invalid_text(self):
        self.assertEqual(recognition.classify_text(""),[])
        self.assertEqual(recognition.classify_text("Texture packs look nice."),[])
        for value in (None,{},4):
            with self.assertRaises(ValueError):
                recognition.classify_text(value)


class TimelineTests(unittest.TestCase):
    def test_preserves_provenance_and_explicit_uncertainty(self):
        timeline=fixture()
        result=recognition.recognize_events(timeline)
        row=result["hypotheses"][0]
        self.assertEqual(row["original_observation"],timeline["events"][0])
        self.assertEqual(row["source_video_claim"],timeline["sources"][0]["source_video"])
        self.assertEqual(row["transcript_interval"],dict(start_seconds=0,end_seconds=2))
        self.assertIsNone(row["temporal_uncertainty"]["gameplay_event_start_seconds"])
        self.assertIsNone(row["temporal_uncertainty"]["gameplay_event_end_seconds"])
        self.assertNotIn("confidence",row)
        self.assertNotEqual(row["source"],"human")
        self.assertEqual(result["transcript_coverage"]["speaker_role"],"unverified")

    def test_duplicate_observations_preserved_with_distinct_ids(self):
        timeline=fixture()
        duplicate=deepcopy(timeline["events"][0])
        duplicate["source_order"]=1
        duplicate["source"]["row_index"]=1
        timeline["events"].append(duplicate)
        rows=recognition.recognize_events(timeline)["hypotheses"]
        self.assertEqual(len(rows),2)
        self.assertNotEqual(rows[0]["hypothesis_id"],rows[1]["hypothesis_id"])
        self.assertEqual(rows[0]["evidence_text"],rows[1]["evidence_text"])

    def test_interval_boundaries_and_point_utterance(self):
        timeline=fixture()
        for start,end in ((0,0),(98,100),(100,100)):
            timeline["events"][0].update(start_seconds=start,end_seconds=end)
            timeline["events"][0]["payload"].update(start=start,end=end)
            with self.subTest(start=start,end=end):
                row=recognition.recognize_events(timeline)["hypotheses"][0]
                self.assertEqual(row["transcript_interval"],dict(start_seconds=start,end_seconds=end))

    def test_source_identity_conflict(self):
        timeline=fixture()
        timeline["sources"][0]["channels"]["transcript"]["provenance"]["source_sha256"]="b"*64
        with self.assertRaises(ValueError):
            recognition.recognize_events(timeline)

    def test_missing_identity_and_unknown_duration(self):
        timeline=fixture(digest=None)
        result=recognition.recognize_events(timeline)
        self.assertEqual(result["source_identity_status"],"unverified_single_artifact")
        self.assertIsNone(result["source_identity"])
        timeline=build_timeline(transcript=dict(segments=[dict(start=0,end=1,text="I died")],provenance={}))
        self.assertEqual(len(recognition.recognize_events(timeline)["hypotheses"]),1)

    def test_absent_unanalyzed_empty_and_blank_transcripts(self):
        analysis=create_analysis(dict(path="fixture.mp4",duration_seconds=10))
        result=recognition.recognize_events(build_timeline(analysis=analysis))
        self.assertEqual(result["status"],"not_analyzed")
        analysis["transcript"]=signal([])
        self.assertEqual(recognition.recognize_events(build_timeline(analysis=analysis))["status"],"analyzed_empty")
        self.assertEqual(recognition.recognize_events(fixture(("   ",)))["status"],"analyzed_empty")
        self.assertEqual(result["hypotheses"],[])
        self.assertEqual(result["transcript_coverage"]["temporal_coverage"],"unknown")

    def test_diagnostic_counts_do_not_claim_coverage(self):
        result=recognition.recognize_events(fixture(("I died","I almost died","Hello")))
        self.assertEqual(len(result["hypotheses"]),1)
        self.assertEqual(len(result["excluded_matches"]),1)
        self.assertEqual(result["transcript_coverage"]["segments_with_rule_cues"],2)
        self.assertEqual(result["transcript_coverage"]["segments_without_rule_cues"],1)

    def test_malformed_payload_or_timestamp(self):
        for field,value in (("text",None),("start",True),("start",3),("end",float("nan")),("metadata",[])):
            timeline=fixture()
            timeline["events"][0]["payload"][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):
                recognition.recognize_events(timeline)
        timeline=fixture()
        del timeline["events"][0]["payload"]["text"]
        with self.assertRaises(ValueError):
            recognition.recognize_events(timeline)

    def test_incompatible_channel_kind_and_version(self):
        for field,value in (("observation_kind","point"),("event_type","invented")):
            timeline=fixture()
            timeline["events"][0][field]=value
            with self.assertRaises(ValueError):
                recognition.recognize_events(timeline)
        timeline=fixture()
        timeline["schema_version"]=2
        with self.assertRaises(ValueError):
            recognition.recognize_events(timeline)
        timeline=fixture()
        timeline["sources"][0]["channels"]["transcript"]["status"]="not_analyzed"
        with self.assertRaises(ValueError):
            recognition.recognize_events(timeline)

    def test_determinism_and_no_mutation(self):
        timeline=fixture(("I died","I respawned","Next game"))
        before=deepcopy(timeline)
        first=recognition.recognize_events(timeline)
        self.assertEqual(first,recognition.recognize_events(json.loads(json.dumps(timeline))))
        first["hypotheses"][0]["original_observation"]["payload"]["text"]="changed copy"
        self.assertEqual(timeline,before)


class CLITests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.input=self.root/"timeline.json"
        self.output=self.root/"events.json"
        self.input.write_text(json.dumps(fixture()),encoding="utf-8")
        self.args=["--timeline",str(self.input),"--output",str(self.output)]

    def run_cli(self,args):
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            return recognition.main(args)

    def test_cli_deterministic_safe_publication(self):
        before=self.input.read_bytes()
        self.assertEqual(self.run_cli(self.args),0)
        saved=self.output.read_bytes()
        self.assertEqual(self.run_cli(self.args),1)
        self.assertEqual(self.run_cli(self.args+["--overwrite"]),0)
        self.assertEqual(saved,self.output.read_bytes())
        self.assertEqual(before,self.input.read_bytes())
        self.assertEqual(json.loads(saved)["detector"]["version"],1)

    def test_atomic_failure_cleanup(self):
        with patch("timeline_query.os.link",side_effect=OSError("publication failure")):
            self.assertEqual(self.run_cli(self.args),1)
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob(".query-*")))

    def test_input_and_unrelated_output_protection(self):
        before=self.input.read_bytes()
        self.assertEqual(self.run_cli(["--timeline",str(self.input),"--output",str(self.input),"--overwrite"]),1)
        self.assertEqual(before,self.input.read_bytes())
        self.output.write_text('{"unrelated":true}')
        self.assertEqual(self.run_cli(self.args+["--overwrite"]),1)
        self.assertEqual(self.output.read_text(),'{"unrelated":true}')

    def test_missing_and_malformed_input(self):
        for text in ("{","[]",'{"a":1,"a":2}','{"a":Infinity}'):
            self.input.write_text(text)
            self.assertEqual(self.run_cli(self.args),1)
            self.assertFalse(self.output.exists())
        self.input.unlink()
        self.assertEqual(self.run_cli(self.args),1)

    def test_import_safety_and_recognition_no_subprocess(self):
        script="""import sys
def audit(event,args):
    if event in ('subprocess.Popen','os.mkdir','os.remove'):
        raise AssertionError(event)
    if event=='open' and ((isinstance(args[1],str) and any(c in args[1] for c in 'wax+')) or args[2] & 3):
        raise AssertionError('write')
sys.addaudithook(audit)
import transcript_event_recognition
assert not any(n in sys.modules for n in ('torch','transformers','faster_whisper'))
"""
        result=subprocess.run([sys.executable,"-B","-c",script],cwd=Path(recognition.__file__).parent,
                              capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout+result.stderr,"")
        with patch("subprocess.run",side_effect=AssertionError("No media or inference")):
            self.assertEqual(len(recognition.recognize_events(fixture())["hypotheses"]),1)


if __name__=="__main__":
    unittest.main()
