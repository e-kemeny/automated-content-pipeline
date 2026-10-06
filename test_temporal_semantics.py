"""Synthetic full score vectors; never run a model or use real labels."""
from copy import deepcopy
from statistics import mean
import unittest

from semantic_clip import PROMPTS, classify_logits, timeline_to_events
from semantic_events import validate_event
from temporal_semantics import aggregate_timeline, temporal_to_events, stability_metrics
from evaluate_semantic_clip import describe
from evaluate_temporal_semantics import format_report


def rows(labels):
    return [classify_logits(float(i), [4.0 if label == k else 0.0 for k in PROMPTS])
            for i,label in enumerate(labels)]


class TemporalSemanticTests(unittest.TestCase):
    def test_centered_mean_every_label(self):
        raw = rows(["combat","kill","death","objective","victory","neutral","combat"])
        aggregated = aggregate_timeline(raw, 7)
        for label in PROMPTS:
            self.assertEqual(aggregated[3]["mean_zero_shot_scores"][label],
                             mean(r["scores"][label]["zero_shot_score"] for r in raw[1:6]))
        self.assertEqual([r["timestamp"] for r in aggregated[3]["neighborhood"]], [1,2,3,4,5])

    def test_beginning_partial_window(self):
        raw = rows(["combat","kill","death","objective","victory"])
        result = aggregate_timeline(raw, 5)
        self.assertEqual(len(result[0]["neighborhood"]), 3)
        self.assertEqual(len(result[1]["neighborhood"]), 4)
        for k in PROMPTS:
            self.assertEqual(result[0]["mean_zero_shot_scores"][k],
                             mean(r["scores"][k]["zero_shot_score"] for r in raw[:3]))

    def test_end_partial_window(self):
        raw = rows(["combat","kill","death","objective","victory"])
        result = aggregate_timeline(raw, 4.5)
        self.assertEqual(len(result[-1]["neighborhood"]), 3)
        self.assertEqual(len(result[-2]["neighborhood"]), 4)
        for k in PROMPTS:
            self.assertEqual(result[-1]["mean_zero_shot_scores"][k],
                             mean(r["scores"][k]["zero_shot_score"] for r in raw[-3:]))

    def test_full_vectors_not_majority_vote(self):
        raw = [classify_logits(float(i), [0.01 if k == "kill" else 0 for k in PROMPTS]) for i in range(5)]
        raw[2] = classify_logits(2, [10.0 if k == "combat" else 0 for k in PROMPTS])
        self.assertEqual([r["label"] for r in raw].count("kill"), 4)
        self.assertEqual(aggregate_timeline(raw, 5)[2]["label"], "combat")

    def test_tie_uses_original_prompt_order(self):
        raw = [classify_logits(float(i), [0.0]*7) for i in range(5)]
        self.assertEqual([r["label"] for r in aggregate_timeline(raw,5)], ["combat"]*5)

    def test_grouping_neutral_exclusion_and_metadata(self):
        raw = rows(["combat"]*5 + ["neutral"]*5 + ["kill"]*5)
        aggregated = aggregate_timeline(raw, 14.5)
        events = temporal_to_events(aggregated, 14.5)
        self.assertEqual([(e["start"],e["end"],e["event_type"]) for e in events],
                         [(0,5,"combat"),(10,14.5,"kill")])
        for event in events:
            self.assertEqual(validate_event(event), event)
            self.assertIn("uncalibrated",event["metadata"]["confidence_semantics"])
        self.assertEqual(events[0]["metadata"]["samples"][0]["neighborhood"],raw[:3])

    def test_timestamp_preservation_nonmutation_and_determinism(self):
        raw = rows(["kill","combat","neutral","victory"])
        original = deepcopy(raw)
        result = aggregate_timeline(raw,4)
        self.assertEqual([r["timestamp"] for r in result], [r["timestamp"] for r in raw])
        self.assertEqual(result,aggregate_timeline(raw,4))
        self.assertEqual(raw,original)
        result[0]["neighborhood"][0]["label"] = "death"
        self.assertEqual(raw,original)

    def test_missing_duplicate_nonuniform_out_of_order(self):
        raw = rows(["combat"]*5)
        cases = [raw[:2]+raw[3:], raw[::-1], raw+[raw[-1]]]
        changed = deepcopy(raw)
        changed[1]["timestamp"] = 1.5
        cases.append(changed)
        for case in cases:
            with self.assertRaises(ValueError):
                aggregate_timeline(case,5)

    def test_invalid_vectors(self):
        raw = rows(["combat"])
        for value in (float("nan"),float("inf"),-0.1,1.1,"bad"):
            changed = deepcopy(raw)
            changed[0]["scores"]["combat"]["zero_shot_score"] = value
            with self.assertRaises(ValueError):
                aggregate_timeline(changed,1)
        changed = deepcopy(raw)
        del changed[0]["scores"]["kill"]
        with self.assertRaises(ValueError):
            aggregate_timeline(changed,1)
        aggregated = aggregate_timeline(raw,1)
        aggregated[0]["mean_zero_shot_scores"]["combat"] = float("nan")
        with self.assertRaises(ValueError):
            temporal_to_events(aggregated,1)

    def test_empty_and_single(self):
        self.assertEqual(aggregate_timeline([],1), [])
        self.assertEqual(temporal_to_events([],1), [])
        metrics = stability_metrics([],[])
        self.assertEqual(metrics["event_count"],0)
        self.assertEqual(metrics["label_transitions"],0)
        self.assertIsNone(metrics["mean_event_duration"])
        self.assertIsNone(metrics["adjacent_same_label_fraction"])
        raw = rows(["kill"])
        self.assertEqual(aggregate_timeline(raw,0.5)[0]["label"],"kill")
        self.assertIsNone(stability_metrics(raw,timeline_to_events(raw,0.5))["adjacent_same_label_fraction"])

    def test_stability_metrics_include_neutral_transitions(self):
        raw = rows(["combat","combat","neutral","kill","kill","kill"])
        metrics = stability_metrics(raw,timeline_to_events(raw,6))
        self.assertEqual(metrics,dict(event_count=2,label_transitions=2,
            mean_event_duration=2.5,median_event_duration=2.5,longest_event_duration=3,
            adjacent_same_label_fraction=0.6))

    def test_descriptive_report_and_candidate_reuse(self):
        raw = rows(["combat","kill","combat","combat","combat"])
        aggregate = aggregate_timeline(raw,5)
        old, new = timeline_to_events(raw,5), temporal_to_events(aggregate,5)
        gt = [dict(start=0,end=5,type="combat",description="Synthetic only")]
        candidates = {"fixture":[2]}
        a,b = describe(old,gt,candidates),describe(new,gt,candidates)
        stability = dict(raw=stability_metrics(raw,old),temporal=stability_metrics(aggregate,new))
        report = format_report(dict(rows=raw),new,a,b,stability,"fixture-hash")
        self.assertIn("fixture-hash",report)
        self.assertIn("Fragmentation and semantic evidence",report)
        self.assertIn("Raw overlap",report)
        self.assertEqual(a["candidates"],b["candidates"])


if __name__ == "__main__":
    unittest.main()
