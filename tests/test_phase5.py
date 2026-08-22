# -*- coding: utf-8 -*-
"""Phase 5 测试：Gordon 增长模型 + 情景矩阵 + g>=Ke 防护。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from valresearch.valuation import gordon


def test_gordon_basic():
    # payout=0.4, Ke=0.10, g=0.04 -> 0.4/(0.10-0.04)=6.67
    pe, err = gordon.gordon(0.4, 0.10, 0.04)
    assert err is None
    assert pe == 6.67
    print('test_gordon_basic OK')


def test_gordon_invalid_g_ge_ke():
    # 规格 Test5: g>=Ke 时不得输出错误结果
    pe, err = gordon.gordon(0.5, 0.10, 0.12)
    assert pe is None and 'GGM_INVALID' in err
    pe, err = gordon.gordon(0.5, 0.10, 0.10)
    assert pe is None and 'GGM_INVALID' in err
    print('test_gordon_invalid_g_ge_ke OK')


def test_gordon_ke_g_margin():
    # g 太接近 Ke: 返回 PE 但标注 THIN_SPREAD（降级而非拒绝）
    pe, err = gordon.gordon(0.5, 0.10, 0.085)   # Ke-g=0.015 < 0.02
    assert pe is not None and 'THIN_SPREAD' in err
    print('test_gordon_ke_g_margin OK')


def test_hist_cagr():
    fin = pd.DataFrame({'report_period': ['2019-12-31', '2020-12-31', '2021-12-31',
                                          '2022-12-31', '2023-12-31', '2024-12-31'],
                        'announcement_date': ['2020-04-30', '2021-04-30', '2022-04-30',
                                              '2023-04-30', '2024-04-30', '2025-04-30'],
                        'eps_basic': [1.0, 1.1, 1.21, 1.33, 1.46, 1.61]})
    c = gordon.historical_eps_cagr(fin, years=5)
    assert c is not None and abs(c - 0.1) < 0.01   # ~10% CAGR
    # P0-A: asof 截断到 2023-06-01 → 只用公告日<=该日的年报(2019~2022 共4年=3区间)
    c2 = gordon.historical_eps_cagr(fin, asof='2023-06-01', years=5)
    assert c2 is not None and abs(c2 - ((1.33 / 1.0) ** (1 / 3) - 1)) < 1e-9, c2
    print('test_hist_cagr OK')


def test_scenario_matrix():
    res = gordon.scenario_matrix(0.4, 2.0, 0.02, 0.05, 0.04)
    # Bear Ke=0.08,g=0.03 -> 8；Base Ke=0.07,g=0.04 -> 13.33；Bull(g=0.05,Ke=0.06利差1%<2%) 判 GGM_INVALID
    assert res['fair_pe_base'] is not None
    assert res['fair_pe_low'] < res['fair_pe_base']
    assert res['fair_pe_low'] == 8.0
    assert res['fair_pe_base'] == round(0.4 / 0.03, 2)
    # Bull(g=0.05,Ke=0.06利差1%<2%) 返回 PE 但标注 THIN_SPREAD（降级可用）
    assert res['fair_pe_high'] is not None and res['thin_spread'] is True
    assert res['invalid'] == ''   # base 有效 → 模型不失效
    print('test_scenario_matrix OK: low=%s base=%s high=%s inv=%s'
          % (res['fair_pe_low'], res['fair_pe_base'], res['fair_pe_high'], res['invalid']))


def test_pe_fair_ratio():
    assert gordon.pe_fair_ratio(8.0, 10.0) == 0.8
    assert gordon.pe_fair_band(0.7) == '低估'
    assert gordon.pe_fair_band(1.6) == '高估'
    print('test_pe_fair_ratio OK')


if __name__ == '__main__':
    test_gordon_basic()
    test_gordon_invalid_g_ge_ke()
    test_gordon_ke_g_margin()
    test_hist_cagr()
    test_scenario_matrix()
    test_pe_fair_ratio()
    print('== Phase 5 全部通过 ==')