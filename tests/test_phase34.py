# -*- coding: utf-8 -*-
"""Phase 3+4 测试：PE/DY/PR 计算 + 分位引擎（严格 count 口径 + 异常值处理）。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd
from valresearch.valuation import percentile as pct
from valresearch.valuation import engine


def test_count_pct_spec():
    # 规格 Test1: [1,2,3,4,5] 当前=3 -> 40%
    s = pd.Series([1, 2, 3, 4, 5])
    assert pct.count_pct(s, 3) == 40.0
    print('test_count_pct_spec OK')


def test_negative_pe_excluded():
    # 规格 Test2: 负PE不进入正常分位
    series = pd.Series([-5.0, -1.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0])
    valid, n_excl, cur = pct.filter_pe(series, 15.0, negative_pe='exclude')
    assert n_excl == 2
    assert (valid > 0).all()
    # 有效 [10,15,20,25,30,35,40], 当前15 -> 低于15的=10 共1个 -> 1/7≈14.29
    assert pct.count_pct(valid, 15.0) == round(1 / 7 * 100, 2)
    print('test_negative_pe_excluded OK')


def test_payout_abnormal():
    # 规格 Test4: 分红率>100% 识别
    series = pd.Series([30.0, 40.0, 50.0, 160.0, 200.0])   # % 单位
    valid, n_excl, abnormal, cur = pct.filter_payout(series, 50.0, lower=0.0, upper=1.5,
                                                      winsorize=False)
    assert n_excl == 2            # 160,200 被剔除
    assert abnormal.sum() == 2
    assert list(valid) == [30.0, 40.0, 50.0]
    # winsorize 模式不报错且保留异常标记
    v2, n2, ab2, _ = pct.filter_payout(series, 50.0, lower=0.0, upper=1.5, winsorize=True)
    assert ab2.sum() == 2 and n2 == 2
    print('test_payout_abnormal OK')


def test_percentile_stats():
    s = pd.Series(np.arange(1, 101, dtype=float))
    st = pct.percentile_stats(s, 50.0, window_years=10, n_excluded=0)
    assert st.pct_10y == 49.0        # 49 个 < 50
    assert st.median == 50.5
    assert st.min == 1.0 and st.max == 100.0
    print('test_percentile_stats OK')


def test_build_series_pit():
    dates = pd.date_range('2023-06-01', '2025-12-31', freq='D')
    price = pd.DataFrame({'date': dates, 'close': np.linspace(10, 12, len(dates))})
    fin = pd.DataFrame({
        'report_period': ['2022-12-31', '2023-12-31'],
        'announcement_date': ['2023-04-30', '2024-04-30'],
        'eps_basic': [1.0, 1.2],
        'net_profit_attr': [10e8, 12e8],   # P0-D: 严格分红率=现金分红总额/归母净利
    })
    div = pd.DataFrame({
        'report_period': ['2022年报'],
        'implement_date': ['2023-07-01'],
        'per_share_cash': [0.4],
    })
    pe = pd.DataFrame({'date': dates, 'pe_ttm': 10.0, 'pe_valid': True})
    ser = engine.build_series(price, pe, fin, div, window_years=10, end='2024-01-01')
    # 2024-01-01 之前 2023年报(2024-04-30)未公告 -> eps_ttm=1.0(2022年报)
    last = ser.iloc[-1]
    assert last['eps_ttm'] == 1.0
    # dps_ttm: 2023-07-01实施0.4 在近12月窗口内
    assert last['dps_ttm'] == 0.4
    assert abs(last['dy'] - (0.4 / last['close'] * 100)) < 1e-6
    # P0-D: 正式 payout = 现金分红总额TTM/归母净利TTM = (0.4*10e8)/(10e8)*100 = 40%（严格口径）
    assert abs(last['payout'] - 40.0) < 1e-6, 'payout 应为严格口径(总额/归母)'
    assert abs(last['payout_crosscheck'] - 40.0) < 1e-6, '每股口径应为交叉验证'
    assert last['payout_method'] == 'STRICT_TOTAL'
    # 未来函数检查：2024-01-01 无 2024 数据
    assert (ser['date'] <= pd.Timestamp('2024-01-01')).all()
    print('test_build_series_pit OK')


if __name__ == '__main__':
    test_count_pct_spec()
    test_negative_pe_excluded()
    test_payout_abnormal()
    test_percentile_stats()
    test_build_series_pit()
    print('== Phase 3+4 全部通过 ==')