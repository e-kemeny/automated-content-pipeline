"""Shared persistence tests; synthetic data and file adapters, no inference."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from semantic_events import create_event
from shared_analysis import (create_analysis, from_existing_signals, from_saved_semantics,
    windows_from_results, validate_analysis, serialize_analysis, save_analysis, load_analysis)


SOURCE = dict(path="videos/example.mp4", duration_seconds=30.5, metadata={"title":"Fixture"})


class SharedAnalysisTests(unittest.TestCase):
    def test_missing_signals_explicit(self):
        result = create_analysis(SOURCE)
        signals = [*result["visual"].values(), *result["acoustic"].values(),
                   *result["language"].values(), result["transcript"],
                   result["semantic_events"], result["candidate_windows"]]
        self.assertTrue(all(s["status"] == "not_analyzed" and s["data"] == [] for s in signals))
        self.assertEqual(set(result["language"]), {"relevance","humor","reaction","narrative_context"})

    def test_empty_analyzed_is_distinct(self):
        result = from_existing_signals(SOURCE, semantic_events=[], scene_rows=[])
        self.assertEqual(result["semantic_events"]["status"],"analyzed")
        self.assertEqual(result["visual"]["scene_changes"]["status"],"analyzed")
        self.assertEqual(result["transcript"]["status"],"not_analyzed")

    def test_available_schemas_metadata_and_no_mutation(self):
        event = create_event(2,4,"combat",0.3,metadata={"original":{"note":"keep"}})
        window = dict(second=3,start=0,end=8,duration=8,highlight_score=0.7)
        audio = [dict(second=5,spike=-1,score=2,normalized_score=0.4)]
        original = deepcopy((audio,event,window,SOURCE))
        result = from_existing_signals(SOURCE,audio_rows=audio,scene_rows=[dict(time=3,score=15)],
            motion_rows=[dict(second=0,score=0)],semantic_events=[event],candidate_windows=[window],
            provenance={"audio_activity":{"source":"existing detector"}})
        self.assertEqual(result["acoustic"]["audio_activity"]["data"],audio)
        self.assertEqual(result["semantic_events"]["data"],[event])
        self.assertEqual(result["candidate_windows"]["data"],[window])
        result["semantic_events"]["data"][0]["metadata"]["original"]["note"]="changed"
        self.assertEqual((audio,event,window,SOURCE),original)

    def test_transcript_and_independent_language(self):
        segments=[dict(start=1.25,end=2.75,text="Synthetic transcript",speaker="player")]
        language={"humor":[dict(start=1,end=3,evidence="provided by future analyzer",score=0.2)]}
        result=from_existing_signals(SOURCE,transcript_segments=segments,language_signals=language)
        self.assertEqual(result["transcript"]["data"],segments)
        self.assertEqual(result["language"]["humor"]["data"],language["humor"])
        self.assertEqual(result["language"]["relevance"]["status"],"not_analyzed")
        with self.assertRaises(ValueError):
            from_existing_signals(SOURCE,language_signals={"other":[]})

    def test_json_roundtrip_deterministic_and_two_consumers(self):
        result=from_existing_signals(SOURCE,candidate_windows=[dict(second=3,start=0,end=8,duration=8)])
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"analysis.json"
            save_analysis(result,path)
            initial=path.read_bytes()
            shorts=load_analysis(path)
            long_form=load_analysis(path)
            self.assertEqual(shorts,long_form)
            self.assertEqual(shorts,result)
            shorts["candidate_windows"]["data"][0]["start"]=1
            self.assertEqual(load_analysis(path),long_form)
            save_analysis(long_form,path)
            self.assertEqual(path.read_bytes(),initial)
        self.assertEqual(serialize_analysis(result),serialize_analysis(result))

    def test_unsupported_version_on_load_and_save(self):
        for version in (0,2,"1",True):
            result=create_analysis(SOURCE)
            result["schema_version"]=version
            with self.assertRaises(ValueError):
                serialize_analysis(result)
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/"invalid.json"
                path.write_text(json.dumps(result))
                with self.assertRaises(ValueError):
                    load_analysis(path)

    def test_timestamp_bounds_and_finiteness(self):
        for second in (-1,31,float("nan"),float("inf"),"1",True):
            with self.assertRaises(ValueError):
                from_existing_signals(SOURCE,audio_rows=[dict(second=second,score=1)])
        for start,end in ((-1,2),(3,2),(0,31),(0,float("nan"))):
            with self.assertRaises(ValueError):
                from_existing_signals(SOURCE,transcript_segments=[dict(start=start,end=end,text="x")])

    def test_order_rejected_not_silently_sorted(self):
        for kwargs in (
            {"scene_rows":[dict(time=5),dict(time=3)]},
            {"semantic_events":[create_event(5,6,"kill",0.5),create_event(2,3,"kill",0.5)]},
            {"candidate_windows":[dict(start=5,end=6),dict(start=1,end=3)]},
            {"language_signals":{"reaction":[dict(start=2,end=4),dict(start=2,end=3)]}}):
            with self.assertRaises(ValueError):
                from_existing_signals(SOURCE,**kwargs)

    def test_window_and_event_schema_validation(self):
        for window in (dict(second=9,start=0,end=8),dict(start=0,end=8,duration=9)):
            with self.assertRaises(ValueError):
                from_existing_signals(SOURCE,candidate_windows=[window])
        with self.assertRaises(ValueError):
            from_existing_signals(SOURCE,semantic_events=[dict(start=0,end=1,event_type="other",confidence=0.5)])
        result=from_existing_signals(SOURCE,semantic_events=[create_event(30.5,30.5,"victory",1)])
        self.assertEqual(result["semantic_events"]["data"][0]["end"],30.5)

    def test_status_and_required_signal_validation(self):
        result=create_analysis(SOURCE)
        result["transcript"]["data"]=[dict(start=0,end=1,text="x")]
        with self.assertRaises(ValueError):
            validate_analysis(result)
        result=create_analysis(SOURCE)
        del result["language"]["humor"]
        with self.assertRaises(ValueError):
            validate_analysis(result)
        result=create_analysis(SOURCE)
        result["transcript"]["status"]="unknown"
        with self.assertRaises(ValueError):
            validate_analysis(result)

    def test_invalid_metadata_and_source(self):
        for metadata in ({1:"bad"},{"value":(1,2)},{"value":float("nan")}):
            with self.assertRaises(ValueError):
                create_analysis(dict(SOURCE,metadata=metadata))
        for source in (dict(SOURCE,duration_seconds=0),dict(SOURCE,path=""),dict(SOURCE,sha256="bad"),
                       dict(SOURCE,width=True),dict(SOURCE,fps=-1)):
            with self.assertRaises(ValueError):
                create_analysis(source)

    def test_failed_save_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"analysis.json"
            save_analysis(create_analysis(SOURCE),path)
            before=path.read_bytes()
            invalid=create_analysis(SOURCE)
            invalid["schema_version"]=2
            with self.assertRaises(ValueError):
                save_analysis(invalid,path)
            self.assertEqual(path.read_bytes(),before)

    def test_saved_clip_and_temporal_adapter_preserves_vectors(self):
        with tempfile.TemporaryDirectory() as directory:
            timeline=Path(directory)/"timeline.json"
            events=Path(directory)/"events.json"
            row=dict(timestamp=0,label="neutral",scores={"original":0.2},model_id="fixture")
            artifact=dict(duration=30.5,model_id="fixture",model_revision="fixture",rows=[row])
            timeline.write_text(json.dumps(artifact))
            events.write_text("[]")
            result=from_saved_semantics(SOURCE,timeline,events)
            self.assertEqual(result["visual"]["semantic_frames"]["data"],[row])
            self.assertEqual(result["visual"]["semantic_frames"]["provenance"]["model_revision"],"fixture")
            self.assertEqual(result["semantic_events"]["status"],"analyzed")
            self.assertEqual(result["acoustic"]["audio_activity"]["status"],"not_analyzed")

    def test_saved_multiframe_invalid_responses_remain_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            timeline=Path(directory)/"timeline.json"
            events=Path(directory)/"events.json"
            row=dict(start=0,end=5,frame_timestamps=[0,2.5,4.9],label=None,response="unrecognized")
            timeline.write_text(json.dumps(dict(duration=30.5,predictions=[row])))
            events.write_text("[]")
            result=from_saved_semantics(SOURCE,timeline,events)
            self.assertEqual(result["visual"]["semantic_frames"]["data"][0]["label"],None)
            row["frame_timestamps"]=[5]
            timeline.write_text(json.dumps(dict(duration=30.5,predictions=[row])))
            with self.assertRaises(ValueError):
                from_saved_semantics(SOURCE,timeline,events)

    def test_saved_source_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            timeline=Path(directory)/"timeline.json"
            events=Path(directory)/"events.json"
            events.write_text("[]")
            for artifact in (dict(duration=20,rows=[]),
                             dict(duration=30.5,video_sha256="b"*64,rows=[])):
                timeline.write_text(json.dumps(artifact))
                with self.assertRaises(ValueError):
                    from_saved_semantics(dict(SOURCE,sha256="a"*64),timeline,events)

    def test_saved_window_selection_is_copy_only(self):
        windows=[dict(second=3,start=0,end=8,duration=8)]
        results=[dict(fixed=dict(detector="Audio-only",k=5,windows=windows),
                      v2=dict(windows=windows))]
        output=windows_from_results(results,"Audio-only",5,"v2")
        self.assertEqual(output,windows)
        output[0]["start"]=1
        self.assertEqual(windows[0]["start"],0)
        with self.assertRaises(ValueError):
            windows_from_results(results,"Audio-only",10)
        with self.assertRaises(ValueError):
            windows_from_results(results,"Audio-only",5,"missing")


if __name__=="__main__":
    unittest.main()
