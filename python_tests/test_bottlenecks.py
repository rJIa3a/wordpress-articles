from city_benchmark.bottlenecks import diagnose


def test_coverage_separates_retrieval_from_selection_and_deduplicates_gold():
    def r(block, target='b'):
        return dict(source='a', block=block, target=target)
    gold = [r('1'), r('1'), r('2'), r('3', 'c'), r('4', 'd'), r('5', 'a'), r('6', 'outside')]
    result = diagnose([r('1'), r('2'), r('4', 'd')], [r('1'), r('8', 'c')], gold, {'a', 'b', 'c', 'd'})
    assert result['gold_blocks'] == 4
    assert result['candidate_recall'] == .75
    assert result['one_per_target_recall_ceiling'] == .5
    assert result['outcomes'] == dict(recovered=1, different_block_selected=1, candidate_missing=1, not_selected=1)
    assert result['unmatched_predictions'] == 1


def test_empty_gold_is_finite():
    result = diagnose([], [], [], set())
    assert result['candidate_recall'] == result['one_per_target_recall_ceiling'] == 0
