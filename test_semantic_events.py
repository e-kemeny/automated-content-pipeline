"""Synthetic interface tests; no annotations used as semantic predictions."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from semantic_events import (EVENT_TYPES, create_event, validate_event, sort_events,
    serialize_events, save_events, load_events, events_overlapping,
    events_near_timestamp, group_events_by_type, associate_events, summarize_sequence)


class SemanticEventTests(unittest.TestCase):
    def event(self, start=10, end=12, kind="combat", confidence=0.7, **kwargs):
        return create_event(start, end, kind, confidence, **kwargs)

    def test_valid_creation_and_vocabulary(self):
        for kind in EVENT_TYPES:
            self.assertEqual(self.event(kind=kind)["event_type"], kind)
        self.assertEqual(self.event(0, 0, confidence=0)["end"], 0)
        self.assertEqual(self.event(confidence=1)["confidence"], 1)

    def test_invalid_timestamps(self):
        for start, end in [(-1, 1), (2, 1), (float("nan"), 2),
                           (0, float("inf")), ("1", 2), (True, 2)]:
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                self.event(start, end)

    def test_invalid_confidence(self):
        for value in (-0.1, 1.1, float("nan"), float("inf"), "0.5", True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.event(confidence=value)

    def test_invalid_type_and_schema(self):
        for kind in ("bed_break", "", None, []):
            with self.assertRaises(ValueError):
                self.event(kind=kind)
        for event in ({}, [], dict(self.event(), unknown=3)):
            with self.assertRaises(ValueError):
                validate_event(event)
        with self.assertRaises(ValueError):
            self.event(source=42)

    def test_metadata_preserved_and_independent(self):
        metadata = {"subtype": "bed_break", "details": [1, None, True, {"text": "hello"}]}
        event = self.event(kind="objective", source="future-detector", metadata=metadata)
        self.assertEqual(event["metadata"], metadata)
        metadata["details"].append(5)
        self.assertNotEqual(event["metadata"], metadata)
        copy = sort_events([event])[0]
        copy["metadata"]["details"].append(9)
        self.assertNotEqual(copy, event)

    def test_invalid_metadata(self):
        for metadata in ([], {1: "coerced"}, {"x": (1, 2)}, {"x": float("nan")}, {"x": object()}):
            with self.assertRaises(ValueError):
                self.event(metadata=metadata)

    def test_json_roundtrip_and_determinism(self):
        events = [self.event(20, 21), self.event(metadata={"z": [1], "a": "text"}, source="test")]
        before = deepcopy(events)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.json"
            save_events(events, path)
            self.assertEqual(load_events(path), sort_events(events))
            self.assertEqual(path.read_text(), serialize_events(events))
            old = path.read_bytes()
            with self.assertRaises(ValueError):
                save_events([dict(events[0], confidence=2)], path)
            self.assertEqual(path.read_bytes(), old)
            path.write_text("{}")
            with self.assertRaises(ValueError):
                load_events(path)
        self.assertEqual(events, before)
        self.assertEqual(serialize_events(events), serialize_events(events))

    def test_chronological_sort_and_stable_ties(self):
        a, b = self.event(source="a"), self.event(source="b")
        events = [self.event(20, 21), a, b, self.event(10, 11)]
        ordered = sort_events(events)
        self.assertEqual([e["end"] for e in ordered], [11, 12, 12, 21])
        self.assertEqual([e["source"] for e in ordered[1:3]], ["a", "b"])

    def test_interval_overlap_and_points(self):
        events = [self.event(0, 10), self.event(10, 20),
                  self.event(10, 10, "kill"), self.event(20, 20, "death")]
        self.assertEqual(events_overlapping(events, 10, 20), sort_events(events[1:3]))
        self.assertEqual(events_overlapping(events, 10, 10), sort_events(events[1:3]))
        self.assertEqual(events_overlapping(events, 20, 21), [events[3]])

    def test_nearby_distance_to_extent_inclusive(self):
        events = [self.event(0, 8), self.event(12, 14), self.event(15, 15, "kill")]
        self.assertEqual(events_near_timestamp(events, 10, 2), events[:2])
        self.assertEqual(events_near_timestamp(events, 8, 0), [events[0]])

    def test_grouping(self):
        events = [self.event(20, 21, "kill"), self.event(), self.event(5, 5, "kill")]
        groups = group_events_by_type(events)
        self.assertEqual(list(groups), ["combat", "kill"])
        self.assertEqual([e["start"] for e in groups["kill"]], [5, 20])

    def test_window_association_max_confidence_and_nonmutation(self):
        events = [self.event(11, 12, "kill", 0.4), self.event(18, 18, "kill", 0.9),
                  self.event(23, 25, "objective", 0.6), self.event(30, 31, "death")]
        candidate = dict(second=15, start=10, end=20, highlight_score=0.5)
        before = deepcopy((events, candidate))
        result = associate_events(events, candidate, radius=3)
        self.assertEqual(result["overlapping_events"], events[:2])
        self.assertEqual(result["nearby_events"], [events[2]])
        self.assertEqual(result["event_types"], ["kill", "objective"])
        self.assertEqual(result["max_confidence_by_type"], {"kill": 0.9, "objective": 0.6})
        self.assertEqual((events, candidate), before)

    def test_point_association(self):
        events = [self.event(5, 10), self.event(10, 10, "kill")]
        result = associate_events(events, {"second": 10}, radius=0)
        self.assertEqual(result["overlapping_events"], [events[1]])
        self.assertEqual(result["nearby_events"], [events[0]])

    def test_sequence_preserves_repeated_types(self):
        types = ["combat", "kill", "objective", "combat", "kill"]
        events = [self.event(i, i+0.5, kind) for i, kind in enumerate(types)]
        summary = summarize_sequence(events[::-1], 0, 5)
        self.assertEqual(summary["events"], events)
        self.assertEqual(summary["event_types"], types)

    def test_empty_lists(self):
        self.assertEqual(sort_events([]), [])
        self.assertEqual(serialize_events([]), "[]\n")
        self.assertEqual(events_overlapping([], 0, 1), [])
        self.assertEqual(events_near_timestamp([], 0, 1), [])
        self.assertEqual(group_events_by_type([]), {})
        self.assertEqual(associate_events([], {"second": 1}),
                         dict(overlapping_events=[], nearby_events=[], event_types=[], max_confidence_by_type={}))
        self.assertEqual(summarize_sequence([], 0, 1), dict(events=[], event_types=[]))

    def test_invalid_queries_even_without_events(self):
        for start, end in ((-1, 2), (3, 2), (0, float("nan"))):
            with self.assertRaises(ValueError):
                events_overlapping([], start, end)
        for radius in (-1, float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                events_near_timestamp([], 1, radius)
            with self.assertRaises(ValueError):
                associate_events([], {"second": 1}, radius)
        with self.assertRaises(ValueError):
            associate_events([], {"start": 1})


if __name__ == "__main__":
    unittest.main()
