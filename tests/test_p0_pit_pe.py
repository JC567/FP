# -*- coding: utf-8 -*-
"""P0-1 PIT PE 修复测试：PE_TTM = Price / EPS_TTM_PIT，不再依赖外部历史PE。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

from valresearch.data.pit_pe import (compute_pe_ttm_pit, PE_SOURCE_PIT,
                                     R_EPS_INSUFFICIENT, R_EPS_NON_POSITIVE,
                                     R_PRICE_NON_POSITIVE, R_PRICE_MISSING)
from valresearch.data import pit
from valresearch.valuation import engine


def test_price10_eps08():
    pe, valid, reason, src = compute_pe_ttm_pit(10.0, 0.8)
    assert pe == 12.5
    assert valid is True
    assert reason is None
    assert src == PE_SOURCE_PIT
    print('test_price10_eps08 OK: PE=%.2f source=%s' % (pe, src))


def test_eps_negative_zero():
    pe, valid, reason, _ = compute_pe_ttm_pit(10.0, -0.5)
    assert np.isnan(pe) and valid is False and reason == R_EPS_NON_POSITIVE
    pe, valid, reason, _ = compute_pe_ttm_pit(10.0, 0.0)
    assert np.isnan(pe) and valid is False and reason == R_EPS_NON_POSITIVE
    pe, valid, reason, _ = compute_pe_ttm_pit(10.0, np.nan)
    assert np.isnan(pe) and valid is False and reason == R_EPS_INSUFFICIENT
    pe, valid, reason, _ = compute_pe_ttm_pit(None, 0.8)
    assert np.isnan(pe) and valid is False and reason == R_PRICE_MISSING
    pe, valid, reason, _ = compute_pe_ttm_pit(0.0, 0.8)
    assert np.isnan(pe) and valid is False and reason == R_PRICE_NON_POSITIVE
    print('test_eps_negative_zero OK')


def test_no_future_eps_in_past():
    """未来EPS不能进入过去PE：公告日前 PE 必须为 NaN。"""
    fin = pd.DataFrame({
        'report_period': ['2024-12-31'],
        'announcement_date': ['2025-04-30'],
        'eps_basic': [1.0],
        'revenue': [100e8], 'net_profit_attr': [10e8],
        'ocf': [None], 'total_assets': [None], 'total_liabilities': [None],
        'int_bearing_debt': [None],
    })
    dates = pd.DatetimeIndex(['2025-03-01', '2025-05-02', '2025-06-01'])
    eps_vals = []
    for d in dates:
        e, _ = pit.eps_ttm_asof(fin, d)
        eps_vals.append(e)
    eps = np.array([np.nan if v is None else float(v) for v in eps_vals])
    # 公告日(4-30)前无EPS
    assert np.isnan(eps[0]), '公告日前不应有EPS'
    assert eps[1] == 1.0 and eps[2] == 1.0
    print('test_no_future_eps_in_past OK: eps_before=NaN, eps_after=%.1f' % eps[1])


def test_series_pit_pe_no_external():
    """build_series 用 PIT EPS 自算 PE，公告日前 PE=NaN；价格10/EPS1 → PE10。"""
    price = pd.DataFrame({'date': ['2025-03-01', '2025-05-02', '2025-06-02'],
                          'close': [10.0, 10.0, 10.0]})
    fin = pd.DataFrame({
        'report_period': ['2024-12-31'],
        'announcement_date': ['2025-04-30'],
        'eps_basic': [1.0],
        'revenue': [100e8], 'net_profit_attr': [10e8],
        'ocf': [None], 'total_assets': [None], 'total_liabilities': [None],
        'int_bearing_debt': [None],
    })
    div = pd.DataFrame(columns=['report_period', 'implement_date', 'per_share_cash'])
    ser = engine.build_series(price, None, fin, div, end='2025-06-02')
    pe_before = ser[ser['date'] < pd.Timestamp('2025-04-30')]['pe']
    pe_after = ser[ser['date'] >= pd.Timestamp('2025-04-30')]['pe']
    assert pe_before.isna().all(), '公告日前PE必须为NaN（外部PE不可入内）'
    assert (pe_after == 10.0).all(), '公告日后 PE=Price/EPS=10'
    assert (ser['pe_source'] == 'PIT_CALCULATED').all()
    print('test_series_pit_pe_no_external OK: pe_after=%.1f' % float(pe_after.iloc[0]))


if __name__ == '__main__':
    test_price10_eps08()
    test_eps_negative_zero()
    test_no_future_eps_in_past()
    test_series_pit_pe_no_external()
    print('== P0-1 PIT PE 全部通过 ==')