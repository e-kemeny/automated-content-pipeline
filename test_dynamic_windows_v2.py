"""Synthetic checks only; no real-video parameter selection."""
from copy import deepcopy
import unittest

from dynamic_windows_v2 import build_dynamic_windows_v2
from evaluate_dynamic_windows import compare_boundaries
from evaluate_fixed_windows import evaluate_baselines
from evaluate_dynamic_windows_v2 import evaluate_v2_pairs, fallback_counts, format_report


def audio(values):
    return [dict(second=i, normalized_score=v) for i, v in enumerate(values)]


def scenes(*times, score=1):
    return [dict(time=t, normalized_score=score) for t in times]


def window(values, scene_rows=(), center=50, duration=100):
    return build_dynamic_windows_v2([dict(second=center)], audio(values), scene_rows, duration)[0]


class DynamicV2Tests(unittest.TestCase):
    def test_brief_lull_even_with_scene_does_not_stop(self):
        values = [1]*100
        values[54] = 0
        w = window(values, scenes(54))
        self.assertEqual((w["start"], w["end"]), (40, 55))
        self.assertEqual(w["boundary_diagnostics"]["forward"]["reason"], "fallback_no_joint_boundary")

    def test_audio_quiet_without_scene(self):
        values = [0]*100
        values[45:55] = [1]*10
        w = window(values)
        self.assertEqual((w["start"], w["end"]), (40, 55))
        self.assertTrue(all(w["boundary_diagnostics"][s]["fallback"] for s in ("backward", "forward")))

    def test_combined_boundary_both_directions(self):
        values = [0]*100
        values[40:60] = [1]*20
        w = window(values, scenes(40, 60))
        self.assertEqual((w["start"], w["end"]), (41, 59))
        for side in ("backward", "forward"):
            d = w["boundary_diagnostics"][side]
            self.assertFalse(d["fallback"])
            e = d["evidence"][-1]
            self.assertTrue(e["audio_ok"] and e["scene_ok"])
            self.assertEqual(e["inward_mean"], 1)
            self.assertEqual(e["outward_mean"], 0.2)

    def test_scene_only_is_not_boundary(self):
        w = window([1]*100, scenes(40, 60))
        self.assertEqual((w["start"], w["end"]), (40, 55))

    def test_weak_scene_is_not_boundary(self):
        values = [0]*100
        values[40:60] = [1]*20
        w = window(values, scenes(40, 60, score=0.49))
        self.assertEqual((w["start"], w["end"]), (40, 55))

    def test_maximum_duration(self):
        values = [0]*100
        values[30:70] = [1]*40
        w = window(values, scenes(29, 71))
        self.assertEqual((w["start"], w["end"], w["duration"]), (30, 70, 40))

    def test_minimum_duration(self):
        values = [0]*100
        values[46:54] = [1]*8
        w = window(values, scenes(45, 55))
        self.assertEqual((w["start"], w["end"], w["duration"]), (46, 54, 8))

    def test_video_clamping_and_short_video(self):
        for center in (0, 0.2, 4.2, 99.9, 100):
            w = window([0]*100, center=center)
            self.assertTrue(0 <= w["start"] <= center <= w["end"] <= 100)
            self.assertTrue(8 <= w["duration"] <= 40)
        w = window([0]*3, center=1, duration=2.5)
        self.assertEqual((w["start"], w["end"]), (0, 2.5))

    def test_missing_audio_fallback(self):
        w = build_dynamic_windows_v2([dict(second=50)], [], scenes(40), 100)[0]
        self.assertEqual((w["start"], w["end"]), (40, 55))
        self.assertEqual(w["boundary_diagnostics"]["backward"]["reason"], "fallback_insufficient_audio_context")

    def test_metadata_order_determinism_no_mutation(self):
        candidates = [dict(second=t, score=0.5, label="keep") for t in (70, 30)]
        rows, visual = audio([1]*100), scenes(20, 40, 80)
        before = deepcopy((candidates, rows, visual))
        first = build_dynamic_windows_v2(candidates, rows, visual, 100)
        second = build_dynamic_windows_v2(candidates, rows[::-1], visual[::-1], 100)
        self.assertEqual(first, second)
        self.assertEqual((candidates, rows, visual), before)
        for c, w in zip(candidates, first):
            self.assertEqual({k: w[k] for k in c}, c)
            self.assertLessEqual(w["start"], c["second"])
            self.assertGreaterEqual(w["end"], c["second"])

    def test_invalid_input(self):
        for duration in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                build_dynamic_windows_v2([], [], [], duration)
        for t in (-1, 101, float("nan")):
            with self.assertRaises(ValueError):
                build_dynamic_windows_v2([dict(second=t)], [], [], 100)
        for rows in ([dict(second=0.5, normalized_score=1)], audio([1])*2,
                     [dict(second=0, normalized_score=float("nan"))]):
            with self.assertRaises(ValueError):
                build_dynamic_windows_v2([], rows, [], 100)
        for visual in (scenes(-1), scenes(101), scenes(20, score=float("nan")), scenes(20, score=1.1)):
            with self.assertRaises(ValueError):
                build_dynamic_windows_v2([], [], visual, 100)

    def test_comparison_report_and_counts(self):
        candidates = [dict(second=t, score=1, normalized_score=1,
                           highlight_score=1, motion_highlight_score=1) for t in (30, 70)]
        annotations = [dict(start=0, end=100, type="combat", description="Synthetic")]
        fixed = evaluate_baselines(candidates, 100, annotations)
        pairs = compare_boundaries(fixed, candidates, 100, annotations)
        before = deepcopy(pairs)
        results = evaluate_v2_pairs(pairs, audio([1]*100), [], 100, annotations)
        self.assertEqual(pairs, before)
        self.assertEqual(len(results), 6)
        for result in results:
            self.assertEqual([w["second"] for w in result["v2"]["windows"]], [30, 70])
            self.assertEqual(result["v2"]["mean_iou"], result["fixed"]["mean_iou"])
            self.assertEqual(fallback_counts(result["v2"]["windows"]), {"fallback_no_strong_scene": 4})
        report = format_report(results, 100, {})
        self.assertIn("V2-Fixed", report)
        self.assertIn("V2-V1", report)
        self.assertIn("2 unique candidates (4 sides)", report)
        self.assertIn("not a validated cutoff", report)


if __name__ == "__main__":
    unittest.main()
