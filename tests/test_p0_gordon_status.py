# -*- coding: utf-8 -*-
"""P0-7 Gordon 失效/数据不足 ≠ 中性50：状态与置信度严格区分。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from valresearch.signal import engine as sig


def _base_cfg():
    return {'mode': 'balanced', 'signals': {'pe_percentile': 30, 'dividend_percentile': 70,
                                            'payout_percentile': 70, 'hysteresis': 0.0},
            'score': {'w_pe': 0.2, 'w_dy': 0.2, 'w_payout': 0.1, 'w_spread': 0.1,
                      'w_gordon': 0.15, 'w_quality': 0.2, 'w_industry': 0.05,
                      'neutral_default': 50.0}}


def _metrics(gordon_status, ratio):
    m = {'pe_pct': 50, 'dy_pct': 50, 'pr_pct': 50, 'spread': 0.02,
         'spread_threshold': 0.02, 'pe_fair_ratio': ratio, 'gordon_status': gordon_status,
         'quality_score': 50, 'industry_score': 50}
    return m


def test_gordon_valid_uses_score():
    comp = sig.score_components(_metrics('VALID', 1.0))
    assert comp['gordon'] == 50 and comp['gordon_status'] == 'VALID'
    print('test_gordon_valid_uses_score OK')


def test_gordon_invalid_not_neutral50():
    comp = sig.score_components(_metrics('INVALID', 0.8))
    assert comp['gordon'] is None, '失效必须为None，不得给50'
    assert comp['gordon_status'] == 'INVALID'
    # composite: gordon 计0 而非中性50 → 分数明显低于全50的情况
    score_invalid = sig.composite_score(_metrics('INVALID', 0.8), comp, _base_cfg())
    comp_ok = sig.score_components(_metrics('VALID', 1.0))
    score_ok = sig.composite_score(_metrics('VALID', 1.0), comp_ok, _base_cfg())
    assert score_invalid < score_ok, f'invalid({score_invalid}) 必须低于 valid({score_ok})'
    assert abs(score_invalid - 42.5) < 0.2, 'gordon计0 → 0.85×50=42.5'
    print('test_gordon_invalid_not_neutral50 OK: invalid=%s valid=%s' % (score_invalid, score_ok))


def test_gordon_insufficient_not_neutral50():
    comp = sig.score_components(_metrics('INSUFFICIENT', None))
    assert comp['gordon'] is None and comp['gordon_status'] == 'INSUFFICIENT'
    print('test_gordon_insufficient_not_neutral50 OK')


def test_compute_signal_sets_status_and_penalty():
    res = sig.compute_signal(_metrics('INVALID', 0.8), {}, {'penalty': 0.0, 'level': 'LOW'}, _base_cfg())
    assert res['gordon_status'] == 'INVALID'
    assert res['gordon_penalty'] == 0.05
    assert 'Gordon无结论' in res['note']
    res_ok = sig.compute_signal(_metrics('VALID', 1.0), {}, {'penalty': 0.0, 'level': 'LOW'}, _base_cfg())
    assert res_ok['gordon_status'] == 'VALID' and res_ok['gordon_penalty'] == 0.0
    assert res['score'] < res_ok['score']
    print('test_compute_signal_sets_status_and_penalty OK')


if __name__ == '__main__':
    test_gordon_valid_uses_score()
    test_gordon_invalid_not_neutral50()
    test_gordon_insufficient_not_neutral50()
    test_compute_signal_sets_status_and_penalty()
    print('== P0-7 Gordon 状态与置信度 全部通过 ==')