import pytest
from city_benchmark.selection import select_sections


def record(block, score, section='History', target='b'):
    return dict(source='a', target=target, block=str(block), score=score,
                section=section, start=0, end=5, anchor='Name')


def test_repeat_policy_explains_every_decision_and_preserves_order():
    rows = [record(0, .95), record(5, .9), record(6, .85, 'Transport'),
            record(10, .7, 'Culture'), record(15, .4, 'Sports', 'c')]
    decisions = []
    selected = select_sections(rows, repeat_threshold=.8, decisions=decisions)
    assert [r['block'] for r in selected] == ['0', '6']
    assert len(decisions) == len(rows)
    assert [d['reason'] for d in decisions] == ['selected', 'same_or_missing_section',
                                              'selected', 'target_limit', 'below_threshold']
    assert select_sections(list(reversed(rows)), repeat_threshold=.8) == selected


@pytest.mark.parametrize('score', [float('nan'), float('inf'), -1, 80])
def test_probability_scale_is_enforced(score):
    with pytest.raises(ValueError):
        select_sections([record(0, score)])


def test_section_comparison_never_mixes_sources_or_targets():
    import numpy as np
    from city_benchmark.repeat_ranking import section_relative_features
    rows = [record(0, .8), record(1, .7), record(2, .6), record(3, .5, target='c')]
    sections = {('a', str(i)): ('A' if i < 2 else 'B') for i in range(4)}
    features = section_relative_features(np.array([[1.], [3.], [9.], [100.]]), rows, sections)
    np.testing.assert_allclose(features[:, -2:], [[-2, -1], [0, 1], [0, 0], [0, 0]])
