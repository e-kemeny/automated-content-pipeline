"""Focused fixed-window baseline checks; no media needed."""

from copy import deepcopy
import unittest

from evaluate_fixed_windows import evaluate_baselines, format_baseline


class FixedBaselineTests(unittest.TestCase):
    def test_selection_suppression_and_limits(self):
        candidates = [dict(second=t, score=100-t, highlight_score=t,
                           motion_highlight_score=100-t) for t in range(10, 200, 5)]
        before = deepcopy(candidates)
        results = evaluate_baselines(candidates, 200, [])
        self.assertEqual(len(results), 6)
        self.assertEqual([w['second'] for w in results[0]['windows']], [10, 25, 40, 55, 70])
        self.assertEqual([w['second'] for w in results[2]['windows']], [135, 150, 165, 180, 195])
        self.assertEqual([len(r['windows']) for r in results], [5, 10, 5, 10, 5, 10])
        for result in results:
            self.assertTrue(all(w['start'] == w['second'] - 10 and w['end'] == w['second'] + 5
                                for w in result['windows']))
        self.assertEqual(candidates, before)

    def test_mean_median_include_unmatched(self):
        candidates = [dict(second=t, score=1, highlight_score=1, motion_highlight_score=1)
                      for t in (10, 40)]
        gt = [dict(start=0, end=15, type='combat', description='Test only')]
        result = evaluate_baselines(candidates, 100, gt)[0]
        self.assertEqual(result['mean_iou'], 0.5)
        self.assertEqual(result['median_iou'], 0.5)
        self.assertEqual(result['evaluation']['threshold_summary']['at_or_above_threshold'], 1)
        self.assertEqual(result['evaluation']['overall_coverage']['covered_duration'], 15)

    def test_empty_predictions_report(self):
        results = evaluate_baselines([], 100, [])
        self.assertTrue(all(r['mean_iou'] is None and r['median_iou'] is None for r in results))
        report = format_baseline(results, 100, {})
        self.assertIn('N/A', report)
        self.assertIn('not a validated cutoff', report)

    def test_report_boundaries_and_gt_coverage(self):
        candidates = [dict(second=98, score=1, highlight_score=1, motion_highlight_score=1)]
        gt = [dict(start=90, end=100, type='victory', description='Test | metadata')]
        results = evaluate_baselines(candidates, 100, gt)
        self.assertEqual(results[0]['windows'][0]['end'], 100)
        report = format_baseline(results, 100, {'video': 'fixture-hash'})
        self.assertIn('| 98 | 88.000000 | 100.000000 | 90-100 | 0.833333 |', report)
        self.assertIn('Test \\| metadata', report)
        self.assertIn('10.000000 | 10.000000 | 100.00%', report)
        self.assertIn('fixture-hash', report)


if __name__ == '__main__':
    unittest.main()
