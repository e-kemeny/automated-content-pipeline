"""Synthetic windows and mocked generation; never download or run a model."""
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, MagicMock

from multiframe_semantics import (build_windows,parse_response,predictions_to_events,
                                   joint_response,MODEL_ID,MODEL_REVISION)
from semantic_events import validate_event,serialize_events,associate_events
from semantic_clip import classify_logits,timeline_to_events,PROMPTS
from evaluate_multiframe_semantics import project_to_grid,compare,format_report


def prediction(start,end,label):
    return dict(start=start,end=end,frame_timestamps=[start,(start+end)/2,end-0.1],
                label=label,response=label or "unrecognized",evidence="Synthetic",
                model_id=MODEL_ID,model_score=None)


class MultiframeTests(unittest.TestCase):
    def test_windows_and_three_positions(self):
        w=build_windows(12)
        self.assertEqual([(x["start"],x["end"]) for x in w],[(0,5),(5,10),(10,12)])
        self.assertEqual(w[0]["frame_timestamps"],[0,2.5,4.9])
        self.assertEqual(w[-1]["frame_timestamps"],[10,11,11.9])

    def test_exact_end_short_and_invalid_duration(self):
        self.assertEqual(len(build_windows(10)),2)
        w=build_windows(0.05)[0]
        self.assertTrue(all(0 <= t < 0.05 for t in w["frame_timestamps"]))
        for d in (-1,float("nan"),float("inf"),True):
            with self.assertRaises(ValueError):
                build_windows(d)

    def test_parser(self):
        self.assertEqual(parse_response(" \n Label: COMBAT\nPlayers fighting."),
                         dict(label="combat",evidence="Players fighting.",parse_status="valid"))

    def test_invalid_parser_no_label_guessing(self):
        for text in ("","combat or kill","combat.","I see victory","{\"label\":\"kill\"}","unknown\ncombat"):
            self.assertIsNone(parse_response(text)["label"])
        with self.assertRaises(ValueError):
            parse_response(None)

    def test_event_merge_metadata_and_confidence(self):
        p=[prediction(0,5,"combat"),prediction(5,10,"combat"),prediction(10,12,"kill")]
        events=predictions_to_events(p)
        self.assertEqual([(e["start"],e["end"]) for e in events],[(0,10),(10,12)])
        self.assertEqual(validate_event(events[0]),events[0])
        self.assertEqual(events[0]["metadata"]["predictions"],p[:2])
        self.assertEqual(events[0]["confidence"],0)
        self.assertIsNone(events[0]["metadata"]["model_confidence"])
        self.assertFalse(events[0]["metadata"]["confidence_available"])
        self.assertEqual(events[0]["metadata"]["model_revision"],MODEL_REVISION)
        self.assertEqual(serialize_events(events),serialize_events(predictions_to_events(p)))

    def test_invalid_neutral_and_gaps_break_runs(self):
        p=[prediction(0,5,"combat"),prediction(5,10,None),prediction(10,15,"combat"),
           prediction(15,20,"neutral"),prediction(21,22,"combat")]
        self.assertEqual(len(predictions_to_events(p)),3)
        for bad in ([prediction(5,4,"kill")],[prediction(0,5,"other")],
                    [prediction(0,5,"kill"),prediction(4,6,"kill")]):
            with self.assertRaises(ValueError):
                predictions_to_events(bad)

    def test_empty(self):
        self.assertEqual(build_windows(0),[])
        self.assertEqual(predictions_to_events([]),[])
        self.assertEqual(project_to_grid([],[]),[])

    def test_joint_generation_one_context(self):
        class Inputs(dict):
            def to(self,device):
                return self
        model=Mock(device="cpu")
        model.generate.return_value=MagicMock()
        processor=Mock()
        processor.return_value=Inputs(input_ids=SimpleNamespace(shape=(1,12)), pixel_values=SimpleNamespace(shape=(1,3,3,512,512)))
        processor.batch_decode.return_value=["combat\nTwo players fight."]
        images=[object(),object(),object()]
        response=joint_response(model,processor,images,build_windows(5)[0])
        self.assertEqual(parse_response(response)["label"],"combat")
        model.generate.assert_called_once()
        self.assertFalse(model.generate.call_args.kwargs["do_sample"])
        messages=processor.apply_chat_template.call_args.args[0]
        self.assertEqual(len(messages),1)
        self.assertEqual(sum(c["type"]=="image" for c in messages[0]["content"]),3)
        self.assertEqual(processor.call_args.kwargs["images"],images)
        with self.assertRaises(ValueError):
            joint_response(model,processor,[],build_windows(5)[0])

    def test_candidate_association(self):
        events=predictions_to_events([prediction(0,5,"kill"),prediction(5,10,"victory")])
        a=associate_events(events,{"second":5},radius=1)
        self.assertEqual(a["overlapping_events"][0]["event_type"],"victory")
        self.assertEqual(a["nearby_events"][0]["event_type"],"kill")

    def test_grid_keeps_invalid_distinct(self):
        p=[prediction(0,5,"kill"),prediction(5,10,None)]
        self.assertEqual([r["label"] for r in project_to_grid(p,[0,4,5,9])],["kill","kill",None,None])

    def test_comparison_and_report(self):
        rows=[classify_logits(float(i),[4 if label=="combat" else 0 for label in PROMPTS]) for i in range(5)]
        events=timeline_to_events(rows,5)
        multi=dict(predictions=[prediction(0,5,"victory")],device="cpu",hardware="fixture",
            torch_version="fixture",transformers_version="fixture",duration=5,video_sha256="fixture",
            setup_seconds=1,frame_seconds=1,inference_seconds=2,total_seconds=4,windows_per_second=0.5)
        data=compare(dict(rows=rows),dict(rows=rows),multi,events,events,
                     [dict(start=0,end=5,type="combat",description="Fixture")],{"fixture":[2]})
        self.assertEqual(data["Raw CLIP"]["diagnostics"]["same_type_coverage"]["combat"]["covered_duration"],5)
        self.assertEqual(data["Multiframe"]["diagnostics"]["same_type_coverage"]["combat"]["covered_duration"],0)
        report=format_report(multi,data)
        self.assertEqual(report,format_report(multi,json.loads(json.dumps(data,sort_keys=True))))
        self.assertIn("compatibility sentinel",report)
        self.assertIn("Original model responses",report)
        self.assertIn("no generalization claim",report)
        json.dumps(data,allow_nan=False)
        multi["predictions"][0]["label"] = None
        self.assertIn("not semantic stability", format_report(multi,data))


if __name__=="__main__":
    unittest.main()
