"""Synthetic-signal tests; no GT-driven parameter selection."""

from copy import deepcopy
import unittest

from dynamic_windows import build_dynamic_windows
from evaluate_dynamic_windows import compare_boundaries, verify_frozen_results, format_report
from evaluate_fixed_windows import evaluate_baselines, format_baseline


def signal(values):
    return [{"second": i, "normalized_score": value} for i, value in enumerate(values)]


class DynamicWindowTests(unittest.TestCase):
    def test_start_boundary_and_minimum(self):
        w = build_dynamic_windows([{"second": 0}], signal([0]*40), 40)[0]
        self.assertEqual((w['start'], w['end'], w['duration']), (0, 8, 8))
        self.assertEqual(w['boundary_diagnostics']['left_stop'], 'video_boundary')
        self.assertTrue(w['boundary_diagnostics']['minimum_enforced'])

    def test_end_boundary(self):
        w = build_dynamic_windows([{"second": 40}], signal([0]*40), 40)[0]
        self.assertEqual((w['start'], w['end'], w['duration']), (32, 40, 8))
        self.assertEqual(w['boundary_diagnostics']['right_stop'], 'video_boundary')

    def test_minimum_and_short_video(self):
        w = build_dynamic_windows([{"second": 20}], signal([0]*40), 40)[0]
        self.assertEqual((w['start'], w['end']), (16, 24))
        w = build_dynamic_windows([{"second": 1}], signal([0]*3), 2.5)[0]
        self.assertEqual((w['start'], w['end']), (0, 2.5))

    def test_quiet_region_and_sustained_activity(self):
        values = [0]*100
        values[45:56] = [1]*11
        w = build_dynamic_windows([{"second": 50}], signal(values), 100)[0]
        self.assertEqual((w['start'], w['end'], w['duration']), (45, 55, 10))
        d = w['boundary_diagnostics']
        self.assertEqual((d['baseline'], d['quiet_threshold']), (0, 0.25))
        self.assertEqual((d['left_stop'], d['right_stop']), ('quiet_region', 'quiet_region'))
        self.assertFalse(d['minimum_enforced'])

    def test_maximum_and_single_quiet_sample_bridging(self):
        values = [1 if i % 2 == 0 else 0 for i in range(100)]
        w = build_dynamic_windows([{"second": 50}], signal(values), 100)[0]
        self.assertEqual((w['start'], w['end'], w['duration']), (35, 65, 30))
        self.assertEqual(w['boundary_diagnostics']['left_stop'], 'maximum_duration')
        self.assertEqual(w['boundary_diagnostics']['right_stop'], 'maximum_duration')

    def test_metadata_order_determinism_and_containment(self):
        candidates = [{"second": t, "highlight_score": 0.7, "extra": "keep"}
                      for t in (99.9, 0, 50, 4.2, 100)]
        activity = signal([0.4]*100)
        before = deepcopy((candidates, activity))
        windows = build_dynamic_windows(candidates, activity, 100)
        self.assertEqual(windows, build_dynamic_windows(candidates, list(reversed(activity)), 100))
        self.assertEqual((candidates, activity), before)
        for c, w in zip(candidates, windows):
            self.assertEqual({key: w[key] for key in c}, c)
            self.assertTrue(0 <= w['start'] <= c['second'] <= w['end'] <= 100)
            self.assertTrue(8 <= w['duration'] <= 30)

    def test_missing_signal(self):
        w = build_dynamic_windows([{"second": 20}], [], 100)[0]
        self.assertEqual(w['duration'], 8)
        self.assertEqual(w['boundary_diagnostics']['left_stop'], 'missing_signal')

    def test_invalid_input(self):
        for duration in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                build_dynamic_windows([], [], duration)
        for t in (-1, 101, float('nan')):
            with self.assertRaises(ValueError):
                build_dynamic_windows([{'second': t}], [], 100)
        for rows in ([{'second': 0.5, 'normalized_score': 1}],
                     [{'second': 0, 'normalized_score': float('inf')}],
                     signal([1]) * 2):
            with self.assertRaises(ValueError):
                build_dynamic_windows([], rows, 100)

    def test_runner_preserves_candidates_and_frozen_check(self):
        candidates = [dict(second=t, score=1, normalized_score=0.5,
                           highlight_score=1, motion_highlight_score=1) for t in (10, 40)]
        annotations = [dict(start=0, end=60, type='combat', description='Test only')]
        fixed = evaluate_baselines(candidates, 60, annotations)
        frozen = format_baseline(fixed, 60, {})
        verify_frozen_results(fixed, frozen)
        verify_frozen_results(fixed, frozen.replace("\n", "\r\n"))
        with self.assertRaises(ValueError):
            verify_frozen_results(fixed, frozen.replace('10, 40', '11, 40'))
        before = deepcopy(fixed)
        pairs = compare_boundaries(fixed, candidates, 60, annotations)
        self.assertEqual(fixed, before)
        for pair in pairs:
            self.assertEqual([w['second'] for w in pair['dynamic']['windows']], [10, 40])
        report = format_report(pairs, 60, 'fixture-hash', {})
        self.assertIn('Delta', report)
        self.assertIn('not a validated cutoff', report)
        self.assertIn('fixture-hash', report)


if __name__ == '__main__':
    unittest.main()
