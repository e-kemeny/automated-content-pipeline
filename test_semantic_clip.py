"""Synthetic logits only: normal tests never download or run CLIP."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from semantic_clip import (MODEL_ID, PROMPTS, classify_logits, sample_timestamps,
    select_device, timeline_runs, timeline_to_events, write_json, validate_timeline)
from semantic_events import validate_event, serialize_events
from evaluate_semantic_clip import describe, frozen_candidates, report


def rows(labels):
    return [classify_logits(float(t), [5.0 if k == label else 0.0 for k in PROMPTS])
            for t, label in enumerate(labels)]


class ClipSemanticTests(unittest.TestCase):
    def test_sampling_grid_and_final_bin(self):
        self.assertEqual(sample_timestamps(2.4), [0, 1, 2])
        self.assertEqual(sample_timestamps(2), [0, 1])
        events = timeline_to_events(rows(["combat"]*3), 2.4)
        self.assertEqual((events[0]["start"], events[0]["end"]), (0, 2.4))

    def test_prompt_mapping_and_raw_evidence(self):
        for label in PROMPTS:
            row = rows([label])[0]
            self.assertEqual(row["label"], label)
            self.assertEqual(row["model_id"], MODEL_ID)
            self.assertEqual(row["scores"][label]["similarity"], 5)
            self.assertAlmostEqual(sum(s["zero_shot_score"] for s in row["scores"].values()), 1)

    def test_grouping_neutral_exclusion_and_schema(self):
        timeline = rows(["combat", "combat", "neutral", "kill", "kill", "combat"])
        before = deepcopy(timeline)
        events = timeline_to_events(timeline, 6)
        self.assertEqual([(e["start"], e["end"], e["event_type"]) for e in events],
                         [(0,2,"combat"), (3,5,"kill"), (5,6,"combat")])
        for e in events:
            self.assertEqual(validate_event(e), e)
            self.assertIn("uncalibrated", e["metadata"]["confidence_semantics"])
        self.assertEqual(events[0]["metadata"]["samples"], timeline[:2])
        self.assertEqual(timeline, before)

    def test_mean_relative_score(self):
        timeline = rows(["kill", "kill"])
        timeline[1] = classify_logits(1, [2.0 if k == "kill" else 0.0 for k in PROMPTS])
        event = timeline_to_events(timeline, 2)[0]
        self.assertAlmostEqual(event["confidence"], sum(r["winning_score"] for r in timeline)/2)

    def test_invalid_logits(self):
        for logits in ([], [0]*6, [0]*8, [float("nan")]*7, [float("inf")]*7, ["1"]*7, [True]*7):
            with self.assertRaises(ValueError):
                classify_logits(0, logits)
        for t in (-1, float("nan")):
            with self.assertRaises(ValueError):
                classify_logits(t, [0]*7)

    def test_invalid_timeline(self):
        for timeline in (rows(["kill"])*2, rows(["kill","combat"])[::-1]):
            with self.assertRaises(ValueError):
                validate_timeline(timeline, 2)
        row = rows(["kill"])[0]
        for field, value in (("label", "death"), ("winning_score", 0.1), ("model_id", "other")):
            with self.assertRaises(ValueError):
                validate_timeline([dict(row, **{field:value})], 1)
        for duration in (0, -1, float("inf")):
            with self.assertRaises(ValueError):
                sample_timestamps(duration)

    def test_empty_and_all_neutral(self):
        self.assertEqual(timeline_to_events([], 1), [])
        self.assertEqual(timeline_to_events(rows(["neutral"]), 1), [])
        self.assertEqual(timeline_runs([], 1), [])

    def test_deterministic_serialization_and_ties(self):
        row = classify_logits(0, [0]*7)
        self.assertEqual(row["label"], "combat")
        events = timeline_to_events([row], 1)
        self.assertEqual(serialize_events(events), serialize_events(events))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"timeline.json"
            write_json(path, [row])
            first = path.read_bytes()
            write_json(path, [row])
            self.assertEqual(path.read_bytes(), first)
            self.assertEqual(json.loads(path.read_text()), [row])

    def test_device_selection(self):
        torch = Mock()
        torch.cuda.is_available.return_value = True
        self.assertEqual(select_device(torch), "cuda")
        torch.cuda.is_available.return_value = False
        self.assertEqual(select_device(torch), "cpu")

    def test_temporal_comparison_and_candidate_association(self):
        events = timeline_to_events(rows(["combat","combat","neutral","victory"]), 4)
        gt = [dict(start=0,end=3,type="combat",description="fixture"),
              dict(start=3,end=4,type="victory",description="fixture")]
        data = describe(events, gt, {"fixture":[1]})
        self.assertEqual(data["event_counts"], {"combat":1,"victory":1})
        self.assertEqual(data["same_type_coverage"]["combat"]["covered_duration"], 2)
        self.assertEqual(data["overlap_seconds"]["combat"]["victory"], 0)
        self.assertEqual(data["associations"]["1"]["event_types"], ["combat","victory"])
        empty = describe([], gt, {})
        self.assertEqual(empty["same_type_coverage"]["combat"]["covered_duration"], 0)

    def test_frozen_candidate_parser_and_report(self):
        text = "\n".join(f"## {name} — Top {k}\nSelected timestamps (seconds): " +
                         ", ".join(str(i*15) for i in range(k))
                         for name in ("Audio-only","Audio + Scene","Audio + Motion") for k in (5,10))
        candidates = frozen_candidates(text)
        self.assertEqual(len(candidates), 6)
        with self.assertRaises(ValueError):
            frozen_candidates("")
        artifact = dict(model_revision="fixture", device="cpu",hardware="fixture",
                        torch_version="fixture",transformers_version="fixture",runtime_seconds=1,
                        duration=1,video_sha256="fixture",rows=rows(["neutral"]))
        output = report(artifact, [], [], candidates)
        self.assertIn("not calibrated", output)
        self.assertIn("neutral", output)
        self.assertIn("Frozen candidate diagnostics", output)


if __name__ == "__main__":
    unittest.main()
