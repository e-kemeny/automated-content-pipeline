"""Run with python -m unittest -v test_windows."""

from copy import deepcopy
import unittest

from windows import build_candidate_windows, temporal_overlap, temporal_iou


class WindowTests(unittest.TestCase):
    def test_normal_window(self):
        self.assertEqual(build_candidate_windows([{"second": 30}], 100),
                         [{"second": 30, "start": 20, "end": 35, "duration": 15}])

    def test_near_beginning(self):
        window = build_candidate_windows([{"second": 3}], 100)[0]
        self.assertEqual((window["start"], window["end"], window["duration"]), (0, 8, 8))

    def test_near_end(self):
        window = build_candidate_windows([{"second": 98}], 100)[0]
        self.assertEqual((window["start"], window["end"], window["duration"]), (88, 100, 12))

    def test_exact_boundaries(self):
        windows = build_candidate_windows([{"second": 0}, {"second": 100}], 100)
        self.assertEqual([(w["start"], w["end"], w["duration"]) for w in windows],
                         [(0, 5, 5), (90, 100, 10)])

    def test_metadata_order_and_input_preservation(self):
        candidates = [{"second": 32.5, "normalized_score": 0.7, "scene_score": 0.2,
                       "highlight_score": 0.55, "extra": "keep"},
                      {"second": 30, "highlight_score": 0.9}]
        before = deepcopy(candidates)
        windows = build_candidate_windows(candidates, 100)
        self.assertEqual([w["second"] for w in windows], [32.5, 30])
        for candidate, window in zip(candidates, windows):
            self.assertEqual({key: window[key] for key in candidate}, candidate)
            self.assertIsNot(window, candidate)
        self.assertEqual(candidates, before)
        self.assertGreater(temporal_overlap(*windows), 0)  # No merging or suppression.

    def test_custom_padding_and_short_video(self):
        window = build_candidate_windows([{"second": 5.5}], 20, 2, 3)[0]
        self.assertEqual((window["start"], window["end"], window["duration"]), (3.5, 8.5, 5))
        window = build_candidate_windows([{"second": 1}], 2)[0]
        self.assertEqual((window["start"], window["end"], window["duration"]), (0, 2, 2))

    def test_zero_padding_and_empty_input(self):
        window = build_candidate_windows([{"second": 5}], 10, 0, 0)[0]
        self.assertEqual((window["start"], window["end"], window["duration"]), (5, 5, 0))
        self.assertEqual(build_candidate_windows([], 10), [])

    def test_invalid_input_rejected(self):
        for second in (-1, 101, float("nan"), float("inf")):
            with self.subTest(second=second), self.assertRaises(ValueError):
                build_candidate_windows([{"second": second}], 100)
        for duration in (0, -1, float("inf"), float("nan")):
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                build_candidate_windows([], duration)
        for padding in (-1, float("inf"), float("nan")):
            for name in ("seconds_before", "seconds_after"):
                with self.subTest(padding=padding, name=name), self.assertRaises(ValueError):
                    build_candidate_windows([], 100, **{name: padding})


class OverlapTests(unittest.TestCase):
    def test_overlap_and_partial_iou(self):
        first, second = dict(start=0, end=10), dict(start=5, end=15)
        self.assertEqual(temporal_overlap(first, second), 5)
        self.assertAlmostEqual(temporal_iou(first, second), 1 / 3)
        self.assertEqual(temporal_iou(first, second), temporal_iou(second, first))

    def test_nonoverlap_and_touching(self):
        for start in (10, 11):
            first, second = dict(start=0, end=10), dict(start=start, end=20)
            self.assertEqual(temporal_overlap(first, second), 0)
            self.assertEqual(temporal_iou(first, second), 0)

    def test_exact_match(self):
        interval = dict(start=2, end=12)
        self.assertEqual(temporal_overlap(interval, interval), 10)
        self.assertEqual(temporal_iou(interval, interval), 1)

    def test_containment(self):
        self.assertEqual(temporal_iou(dict(start=0, end=10), dict(start=2, end=4)), 0.2)

    def test_zero_length(self):
        point = dict(start=5, end=5)
        self.assertEqual(temporal_iou(point, point), 0)
        self.assertEqual(temporal_overlap(point, dict(start=0, end=10)), 0)
        self.assertEqual(temporal_iou(point, dict(start=0, end=10)), 0)

    def test_invalid_interval(self):
        for interval in (dict(start=5, end=4), dict(start=-1, end=2), dict(start=0, end=float("inf"))):
            for function in (temporal_overlap, temporal_iou):
                with self.subTest(interval=interval, function=function), self.assertRaises(ValueError):
                    function(interval, dict(start=0, end=10))


if __name__ == "__main__":
    unittest.main()
