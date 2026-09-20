"""Focused checks; run with python test_motion.py (no media required)."""

from math import isclose

from motion import frame_change, score_motion_frames, add_motion_scores


def test_frame_arithmetic():
    assert frame_change(bytes([0, 255]), bytes([255, 0])) == 1.0
    assert frame_change(bytes([255]), bytes([0])) == 1.0
    assert isclose(frame_change(bytes([10, 100]), bytes([30, 90])), 15 / 255)
    assert frame_change(bytes([77]), bytes([77])) == 0.0


def test_zero_normalization():
    for frames in ([], [bytes([42])], [bytes([42])] * 12):
        scores = score_motion_frames(frames)
        assert all(item['score'] == item['normalized_score'] == 0 for item in scores)


def test_second_aggregation():
    # First second has four differences; the 0.8 -> 1.0 transition goes to second 1.
    frames = [bytes([value]) for value in [0, 0, 0, 0, 255, 255, 255, 255, 255, 255, 0]]
    scores = score_motion_frames(frames)
    assert [item['second'] for item in scores] == [0, 1, 2]
    assert [item['score'] for item in scores] == [0.25, 0, 1]
    assert [item['normalized_score'] for item in scores] == [0.25, 0, 1]
    scores = score_motion_frames([bytes([0])] * 5 + [bytes([255])] * 5)
    assert scores[0]['score'] == 0
    assert isclose(scores[1]['score'], 0.2)
    assert scores[1]['normalized_score'] == 1


def test_motion_association():
    original = {'second': 20, 'score': 12, 'normalized_score': 0.5,
                'scene_score': 0.4, 'highlight_score': 0.47}
    for second in (15, 25):
        audio = [original.copy()]
        add_motion_scores(audio, [{'second': second, 'normalized_score': 0.8}])
        assert audio[0]['motion_score'] == 0.8
        assert isclose(audio[0]['motion_highlight_score'], 0.59)
        assert all(audio[0][key] == value for key, value in original.items())
    audio = [original.copy()]
    add_motion_scores(audio, [{'second': 14, 'normalized_score': 1},
                             {'second': 26, 'normalized_score': 1},
                             {'second': 20, 'normalized_score': 0.2},
                             {'second': 23, 'normalized_score': 0.6}])
    assert audio[0]['motion_score'] == 0.6
    add_motion_scores(audio, [])
    assert audio[0]['motion_score'] == 0
    assert isclose(audio[0]['motion_highlight_score'], 0.35)


if __name__ == '__main__':
    test_frame_arithmetic()
    test_zero_normalization()
    test_second_aggregation()
    test_motion_association()
    print('PASS: frame arithmetic, zero normalization, per-second aggregation, and +/-5s association')
