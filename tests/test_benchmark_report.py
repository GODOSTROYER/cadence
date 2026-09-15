"""Reporting regressions: pairing and missing evaluation data must never inflate evidence."""

import pytest
from analysis_tools.reproduce_benchmark import judge_summary, summarize


def ratings():
    return [
        {'id': ident, 'system': system, 'order_id': order, 'rank': rank,
         'scores': {'overall': score}, 'verdict': 'ship', 'flags': {'wrong_issue': False},
         'position': position if order == 0 else 3-position}
        for ident in ('a', 'b')
        for order in (0, 1)
        for system, rank, score, position in [('agent', 1, 5, 1), ('simple_keyword', 2, 3, 2)]
    ]


def test_both_orders_are_required_for_complete_judge_evidence():
    rows = ratings()
    assert judge_summary(rows[:-1], ['a', 'b'])['status'] == 'incomplete'
    result = judge_summary(rows, ['a', 'b'])
    assert result['mean_overall_delta'] == 2
    assert result['ci95'] == [2, 2]
    assert result['preference_order_consistency'] == 1
    assert result['human_agreement'] is None


def test_judge_rejects_duplicate_or_unexpected_samples():
    rows = ratings()
    with pytest.raises(ValueError, match='Duplicate'):
        judge_summary(rows + [rows[0]], ['a', 'b'])
    with pytest.raises(ValueError, match='Unexpected'):
        judge_summary(rows, ['a'])


def test_always_escalate_does_not_claim_zero_auto_handle_risk():
    gold = [{'id': 'a', 'gold': {'intent': 'other', 'should_escalate': True}},
            {'id': 'b', 'gold': {'intent': 'other', 'should_escalate': False}}]
    rows = [{'id': i, 'intent': 'other', 'decision': 'escalate', 'cached': False,
             'model': 'baseline', 'latency_ms': 0} for i in ('b', 'a')]
    result = summarize(gold, rows, n_boot=20)
    assert result['metrics']['escalation_recall']['estimate'] == 1
    assert result['metrics']['auto_handle_rate']['estimate'] == 0
    assert result['metrics']['unsafe_auto_rate'] == {'estimate': None, 'ci95': None}
    with pytest.raises(ValueError, match='exactly once'):
        summarize(gold, [rows[0], rows[0]], n_boot=20)
