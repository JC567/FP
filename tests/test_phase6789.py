# -*- coding: utf-8 -*-
"""Phase 6/7/8/9 测试：基本面、价值陷阱、信号、价格区间。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from valresearch.fundamental import quality_score
from valresearch.risk import value_trap_score
from valresearch.signal import compute_signal
from valresearch.signal.engine import rule_signal, final_signal, composite_score, score_components
from valresearch.valuation import percentile as pct


def make_fin():
    return pd.DataFrame({
        'report_period': ['2019-12-31', '2020-12-31', '2021-12-31', '2022-12-31',
                          '2023-12-31', '2024-12-31'],
        'announcement_date': ['2020-04-30', '2021-04-30', '2022-04-30', '2023-04-30',
                              '2024-04-30', '2025-04-30'],
        'revenue': [100e8, 110e8, 121e8, 133e8, 146e8, 161e8],
        'net_profit_attr': [10e8, 11e8, 12e8, 13e8, 14e8, 15e8],
        'eps_basic': [1.0, 1.1, 1.2, 1.3, 1.4, 1.5],
        'ocf': [None, None, None, None, None, None],
        'total_assets': [200e8] * 6, 'total_liabilities': [80e8] * 6,
        'int_bearing_debt': None,
    })


def make_div():
    return pd.DataFrame({
        'report_period': ['2019年报', '2020年报', '2021年报', '2022年报',
                          '2023年报', '2024年报'],
        'implement_date': ['2020-06-20', '2021-06-20', '2022-06-20', '2023-06-20',
                           '2024-06-20', '2025-06-20'],
        'per_share_cash': [0.3, 0.33, 0.36, 0.4, 0.44, 0.48],
    })


def test_quality_score():
    fin = make_fin()
    div = make_div()
    q = quality_score(fin, div, '2025-07-01', '制造业', '汽车玻璃', {})
    assert q['score'] >= 0 and q['score'] <= 100
    # 现金流缺失 → 现金流模块警告(DATA_INSUFFICIENT)但总分仍可算
    assert any('DATA_INSUFFICIENT' in w for w in q['warnings'])
    assert q['detail']['earnings']['cagr_np'] is not None
    assert q['detail']['dividend']['consecutive_years'] == 6
    print('test_quality_score OK:', q['score'], q['sub'])


def test_value_trap():
    fin = make_fin()
    div = make_div()
    q = quality_score(fin, div, '2025-07-01', '地产', 'x', {})
    vt = value_trap_score(q, '地产', {})
    assert vt['score'] >= 0 and vt['score'] <= 100
    assert 'LOW' in vt['level'] or 'MEDIUM' in vt['level'] or 'HIGH' in vt['level']
    print('test_value_trap OK:', vt['score'], vt['level'], 'block=', vt['block_strong_buy'])


def test_rule_signals():
    assert rule_signal(True, True, True) == 'STRONG_UNDERVALUE'
    assert rule_signal(True, True, False) == 'POLICY_DRIVEN_HIGH_DIVIDEND'
    assert rule_signal(False, True, True) == 'HIGH_YIELD_NOT_CHEAP_ENOUGH'
    assert rule_signal(False, False, False) == 'NEUTRAL'
    print('test_rule_signals OK')


def test_signal_trap_block():
    metrics = {'pe_pct': 10, 'dy_pct': 90, 'pr_pct': 40, 'spread': 0.03,
               'spread_threshold': 0.02, 'pe_fair_ratio': 0.7,
               'quality_score': 80, 'industry_score': 40}
    vt_low = {'score': 15, 'level': 'LOW', 'block_strong_buy': False, 'penalty': 0.0}
    sig = compute_signal(metrics, {}, vt_low, {})
    assert sig['condition_a'] and sig['condition_b'] and sig['condition_c']
    assert sig['rule_signal'] == 'STRONG_UNDERVALUE'
    assert sig['final_signal'] in ('BUY', 'STRONG_BUY')
    # 陷阱高：禁止 STRONG_BUY
    vt_hi = {'score': 70, 'level': 'HIGH', 'block_strong_buy': True, 'penalty': 0.35}
    sig2 = compute_signal(metrics, {}, vt_hi, {})
    assert sig2['final_signal'] != 'STRONG_BUY'
    print('test_signal_trap_block OK:', sig['final_signal'], '->', sig2['final_signal'])


def test_price_and_zones():
    pe_stats = pct.percentile_stats(pd.Series(range(1, 101)), 15.0)
    assert pe_stats.p20 is not None
    assert pe_stats.pct_10y == 14.0    # 14 个 < 15
    from valresearch.valuation import price_range as pr
    eps = 2.0
    hist = pr.hist_price_map(eps, pe_stats)
    assert 'pe_p20_price' in hist
    assert abs(hist['pe_p20_price'] - 2.0 * pe_stats.p20) < 1e-6
    z = pr.current_zone(15.0, pe_stats, None)
    assert z in ('标准/深度买入区', '观察区', '持有区', '高估区', 'NA')
    at = pr.price_at_dy(0.5, 0.05)
    assert at == 10.0
    print('test_price_and_zones OK: zone=%s p20_price=%s' % (z, hist['pe_p20_price']))


def test_composite_neutral_default():
    """P0-7: 非Gordon缺失维度按中性分计、分母恒为全部权重；Gordon无结论必须计0而非50。"""
    comp = {'pe': 80.0, 'dy': 70.0, 'payout': 60.0, 'spread': 90.0,
            'gordon': None, 'quality': 64.2, 'industry': 45.0}
    sc = composite_score({}, comp, {})
    # 全权重加权，gordon 无结论计 0（不伪装中性50）：分母=1.0
    expect = (80*0.2 + 70*0.2 + 60*0.1 + 90*0.1 + 0*0.15 + 64.2*0.2 + 45*0.05) / 1.0
    assert abs(sc - round(expect, 1)) < 1e-9
    # 全维度有值时与旧口径一致(无None，不触发中性分)
    comp2 = dict(comp, gordon=100.0)
    sc2 = composite_score({}, comp2, {})
    assert sc2 == round((80*0.2 + 70*0.2 + 60*0.1 + 90*0.1 + 100*0.15 + 64.2*0.2 + 45*0.05) / 1.0, 1)
    # Gordon 无结论 → 明确标注，绝不显示为中性50
    metrics = {'pe_pct': 10, 'dy_pct': 90, 'pr_pct': 40, 'spread': 0.03,
               'spread_threshold': 0.02, 'pe_fair_ratio': None, 'gordon_status': 'INSUFFICIENT',
               'quality_score': 80, 'industry_score': 40}
    vt = {'score': 15, 'level': 'LOW', 'block_strong_buy': False, 'penalty': 0.0}
    sig = compute_signal(metrics, {}, vt, {})
    assert 'gordon' in sig['components'] and sig['components']['gordon'] is None
    assert sig['gordon_status'] == 'INSUFFICIENT'
    assert 'Gordon无结论' in sig['note'], '必须标注Gordon无结论，而非中性分'
    assert sig['base_score'] is not None
    print('test_composite_neutral_default OK: base=%s' % sig['base_score'])


if __name__ == '__main__':
    test_quality_score()
    test_value_trap()
    test_rule_signals()
    test_signal_trap_block()
    test_price_and_zones()
    test_composite_neutral_default()
    print('== Phase 6/7/8/9 全部通过 ==')