# -*- coding: utf-8 -*-
"""P1-5 四类反例测试：构造能暴露缺陷的对抗样例，防止修复回退。

A. 高股息但亏损(负盈利/无EPS) → 不得被判为低估(PE=NaN, 不伪造)
B. 高分红率(透支分红>100%/异常) → 判不可持续/剔除出分位
C. 数据不足(缺价格/缺财报/缺分红) → DATA_INSUFFICIENT，绝不伪装成50分
D. 未来数据污染历史 → PIT 失效检测(未来公告/未来EPS不得进入过去)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

from valresearch.data.pit_pe import compute_pe_ttm_pit
from valresearch.data.payout import payout_ratio_strict
from valresearch.valuation import percentile as pct
from valresearch.valuation import engine
from valresearch.data import pit
from valresearch.signal.engine import score_components, composite_score


def _cfg():
    return {'mode': 'balanced', 'signals': {'pe_percentile': 30, 'dividend_percentile': 70,
                                            'payout_percentile': 70, 'hysteresis': 0.0},
            'score': {'w_pe': 0.2, 'w_dy': 0.2, 'w_payout': 0.1, 'w_spread': 0.1,
                      'w_gordon': 0.15, 'w_quality': 0.2, 'w_industry': 0.05, 'neutral_default': 50.0}}


def test_a_lossmaking_high_dividend_not_cheap():
    """A. 亏损高股息：EPS<0 → PE 必须 NaN(不伪造低估)，不得因低价股息率判便宜。"""
    pe, valid, reason, _ = compute_pe_ttm_pit(5.0, -1.0)
    assert np.isnan(pe) and not valid and reason == 'EPS_NON_POSITIVE'
    comp = score_components({'pe_pct': None, 'dy_pct': 95, 'pr_pct': None, 'spread': 0.03,
                             'spread_threshold': 0.02, 'pe_fair_ratio': None,
                             'gordon_status': 'INSUFFICIENT', 'quality_score': 50,
                             'industry_score': 50})
    assert comp['pe'] is None and comp['gordon'] is None
    print('test_a_lossmaking_high_dividend_not_cheap OK')


def test_b_overpay_dividend_unsustainable():
    """B. 透支分红：分红率异常(>上限)剔除出分位；strict 口径对亏损判 NaN。"""
    s = pd.Series([30.0, 200.0, 50.0, 120.0])
    valid, n_excl, abnormal, _ = pct.filter_payout(s, 40.0, lower=0.0, upper=1.5)
    assert n_excl == 1 and bool(abnormal.iloc[1])       # 200% 被剔除
    assert 200.0 not in valid.values and float(valid.max()) < 150.0
    # 严格口径：亏损不可算分红率
    assert np.isnan(payout_ratio_strict(5e8, -1e8)[0])
    print('test_b_overpay_dividend_unsustainable OK')


def test_c_data_insufficient_no_fake_50():
    """C. 数据不足：无分红数据 → dy=NaN(非0)；无财报 → PE=NaN；Gordon INSUFFICIENT 计0非50。"""
    price = pd.DataFrame({'date': ['2025-05-02'], 'close': [10.0]})
    fin = pd.DataFrame({
        'report_period': ['2024-12-31'], 'announcement_date': ['2025-04-30'],
        'eps_basic': [1.0], 'revenue': [100e8], 'net_profit_attr': [10e8],
        'ocf': [None], 'total_assets': [None], 'total_liabilities': [None],
        'int_bearing_debt': [None],
    })
    ser = engine.build_series(price, None, fin, None, end='2025-05-02')   # div=None
    assert np.isnan(ser['dy'].iloc[0]), '无分红数据=NaN，不是0'
    assert ser['pe'].iloc[0] == 10.0                                      # PE 由EPS自算=10
    comp = score_components({'pe_pct': 30, 'dy_pct': None, 'pr_pct': None, 'spread': None,
                             'spread_threshold': 0.02, 'pe_fair_ratio': None,
                             'gordon_status': 'INSUFFICIENT', 'quality_score': 50,
                             'industry_score': 50})
    sc = composite_score({}, comp, _cfg())
    assert sc < 50, '数据不足时综合分应明显低于全50(非伪装中性)'
    print('test_c_data_insufficient_no_fake_50 OK: score=%s' % sc)


def test_d_future_data_does_not_pollute_past():
    """D. 未来数据污染：未来公告/未来EPS不得进入过去。"""
    fin = pd.DataFrame({
        'report_period': ['2024-12-31', '2024-12-31'],
        'announcement_date': ['2025-04-30', '2025-09-15'],   # 未来修订(9-15)
        'eps_basic': [1.0, 0.8],
        'revenue': [100e8, 95e8], 'net_profit_attr': [10e8, 9e8],
        'ocf': [None, None], 'total_assets': [None, None],
        'total_liabilities': [None, None], 'int_bearing_debt': [None, None],
    })
    dates = pd.DatetimeIndex(['2025-06-01', '2025-10-01'])
    eps_vals = []
    for d in dates:
        e, _ = pit.eps_ttm_asof(fin, d)
        eps_vals.append(np.nan if e is None else float(e))
    eps = np.array(eps_vals)
    assert eps[0] == 1.0, '未来修订(9-15)不得改写6-1的EPS'
    assert eps[1] == 0.8, '修订公开后(10-1)才用新值'
    # PIT 选择：asof 6-1 取 v1，asof 10-1 取 v2
    assert pit.select_financial_version(fin, '2024-12-31', '2025-06-01')['eps_basic'] == 1.0
    assert pit.select_financial_version(fin, '2024-12-31', '2025-10-01')['eps_basic'] == 0.8
    print('test_d_future_data_does_not_pollute_past OK')


if __name__ == '__main__':
    test_a_lossmaking_high_dividend_not_cheap()
    test_b_overpay_dividend_unsustainable()
    test_c_data_insufficient_no_fake_50()
    test_d_future_data_does_not_pollute_past()
    print('== P1-5 四类反例测试 全部通过 ==')