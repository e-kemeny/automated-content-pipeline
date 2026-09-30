"""Run with python -m unittest -v test_evaluation_v2."""

from copy import deepcopy
import unittest

from evaluation_v2 import evaluate_windows
from windows import build_candidate_windows


def interval(start, end):
    return {"start": start, "end": end, "type": "combat", "description": "Test interval"}


class IntervalEvaluationTests(unittest.TestCase):
    def test_exact_match_and_metadata(self):
        gt = interval(10, 25)
        prediction = build_candidate_windows([{"second": 20, "highlight_score": 0.8}], 100)[0]
        before = deepcopy((prediction, gt))
        result = evaluate_windows([prediction], [gt])
        self.assertEqual(result['matches'][0], dict(prediction=prediction, ground_truth=gt,
                                                 overlap_duration=15, iou=1))
        self.assertEqual(result['coverage'][0], dict(annotation=gt, duration=15,
                                                  covered_duration=15, coverage_fraction=1))
        self.assertEqual((prediction, gt), before)
        self.assertIsNot(result['matches'][0]['prediction'], prediction)
        self.assertIsNot(result['coverage'][0]['annotation'], gt)

    def test_partial_overlap(self):
        match = evaluate_windows([interval(5, 15)], [interval(0, 10)])['matches'][0]
        self.assertEqual(match['overlap_duration'], 5)
        self.assertAlmostEqual(match['iou'], 1 / 3)

    def test_no_overlap_and_touching(self):
        result = evaluate_windows([interval(10, 20), interval(30, 40)], [interval(0, 10)])
        for match in result['matches']:
            self.assertIsNone(match['ground_truth'])
            self.assertEqual(match['iou'], 0)
            self.assertEqual(match['overlap_duration'], 0)

    def test_best_iou_not_largest_overlap(self):
        large, exact = interval(0, 100), interval(5, 15)
        result = evaluate_windows([interval(5, 15)], [large, exact])
        self.assertEqual(result['matches'][0]['ground_truth'], exact)

    def test_tie_uses_gt_input_order(self):
        first, second = interval(5, 15), interval(0, 10)
        result = evaluate_windows([interval(5, 10)], [first, second])
        self.assertEqual(result['matches'][0]['ground_truth'], first)

    def test_coverage_clipped_and_no_double_count(self):
        predictions = [interval(0, 12), interval(10, 18), interval(25, 30)]
        result = evaluate_windows(predictions, [interval(5, 20)])
        self.assertEqual(result['coverage'][0]['covered_duration'], 13)
        self.assertAlmostEqual(result['coverage'][0]['coverage_fraction'], 13 / 15)
        self.assertEqual(result['overall_coverage']['covered_duration'], 13)

    def test_disjoint_coverage_preserves_gaps(self):
        result = evaluate_windows([interval(0, 2), interval(8, 10)], [interval(0, 10)])
        self.assertEqual(result['coverage'][0]['covered_duration'], 4)
        self.assertEqual(result['overall_coverage']['coverage_fraction'], 0.4)

    def test_overall_union_of_overlapping_gt(self):
        result = evaluate_windows([interval(0, 12)], [interval(0, 10), interval(5, 15)])
        self.assertEqual([c['covered_duration'] for c in result['coverage']], [10, 7])
        self.assertEqual(result['overall_coverage'], dict(duration=15, covered_duration=12, coverage_fraction=0.8))

    def test_multiple_predictions_share_gt(self):
        gt = interval(0, 20)
        result = evaluate_windows([interval(0, 10), interval(10, 20)], [gt])
        self.assertEqual([m['ground_truth'] for m in result['matches']], [gt, gt])
        self.assertEqual(result['threshold_summary']['at_or_above_threshold'], 2)

    def test_threshold_separate_and_inclusive(self):
        predictions, gt = [interval(0, 5), interval(20, 25)], [interval(0, 10)]
        base = evaluate_windows(predictions, gt)
        strict = evaluate_windows(predictions, gt, 0.51)
        self.assertEqual(base['threshold_summary']['at_or_above_threshold'], 1)
        self.assertEqual(strict['threshold_summary']['at_or_above_threshold'], 0)
        self.assertEqual(base['matches'], strict['matches'])
        self.assertEqual(base['coverage'], strict['coverage'])
        self.assertEqual(evaluate_windows(predictions, gt, 0)['threshold_summary']['at_or_above_threshold'], 1)
        self.assertIsNone(evaluate_windows(predictions, gt, None)['threshold_summary'])

    def test_empty_predictions(self):
        result = evaluate_windows([], [interval(0, 10)])
        self.assertEqual(result['matches'], [])
        self.assertEqual(result['coverage'][0]['covered_duration'], 0)
        self.assertEqual(result['overall_coverage']['coverage_fraction'], 0)
        self.assertEqual(result['threshold_summary']['prediction_count'], 0)

    def test_empty_ground_truth(self):
        result = evaluate_windows([interval(0, 10)], [])
        self.assertIsNone(result['matches'][0]['ground_truth'])
        self.assertEqual(result['coverage'], [])
        self.assertEqual(result['overall_coverage'], dict(duration=0, covered_duration=0, coverage_fraction=0))
        self.assertEqual(evaluate_windows([], [])['matches'], [])

    def test_zero_duration(self):
        result = evaluate_windows([interval(5, 5)], [interval(5, 5)])
        self.assertIsNone(result['matches'][0]['ground_truth'])
        self.assertEqual(result['coverage'][0]['coverage_fraction'], 0)

    def test_invalid_threshold(self):
        for threshold in (-0.1, 1.1, float('nan'), float('inf')):
            with self.subTest(threshold=threshold), self.assertRaises(ValueError):
                evaluate_windows([], [], threshold)


if __name__ == '__main__':
    unittest.main()
