# -*- coding: utf-8 -*-
"""P0-4 股息率0值处理：无分红 = 真实 0%（参与分位），数据缺失才为 NaN。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

from valresearch.valuation import engine
from valresearch.data import pit


def _fin():
    return pd.DataFrame({
        'report_period': ['2024-12-31'],
        'announcement_date': ['2025-04-30'],
        'eps_basic': [1.0],
        'revenue': [100e8], 'net_profit_attr': [10e8],
        'ocf': [None], 'total_assets': [None], 'total_liabilities': [None],
        'int_bearing_debt': [None],
    })


def test_no_dividend_is_zero_yield():
    price = pd.DataFrame({'date': ['2025-05-02'], 'close': [10.0]})
    fin = _fin()
    # 有历史分红但不在10年窗口内 → 窗口内 DPS_TTM=0 → 股息率 0%（真实0%，非NaN）
    div = pd.DataFrame({'report_period': ['2005-12-31'], 'implement_date': ['2006-06-30'],
                        'per_share_cash': [0.5]})
    ser = engine.build_series(price, None, fin, div, end='2025-05-02')
    assert ser['dy'].iloc[0] == 0.0, '窗口内无分红股息率应为0'
    assert ser['payout'].iloc[0] == 0.0, '窗口内无分红分红率应为0'
    print('test_no_dividend_is_zero_yield OK: dy=0, payout=0')


def test_missing_dividend_data_is_nan():
    price = pd.DataFrame({'date': ['2025-05-02'], 'close': [10.0]})
    fin = _fin()
    ser = engine.build_series(price, None, fin, None, end='2025-05-02')  # div=None → 数据缺失
    assert np.isnan(ser['dy'].iloc[0]), '无分红数据应NaN，不可伪装为0'
    assert np.isnan(ser['payout'].iloc[0])
    print('test_missing_dividend_data_is_nan OK')


def test_dps_ttm_asof_zero_window():
    div = pd.DataFrame({'report_period': ['2023-12-31'], 'implement_date': ['2024-06-30'],
                        'per_share_cash': [0.5]})
    dps, warn = pit.dps_ttm_asof(div, '2025-09-01')  # 近12个月无分红
    assert dps == 0.0 and warn is None, '公司有记录但近12个月未分红 → DPS_TTM=0'
    dps_none, warn_none = pit.dps_ttm_asof(None, '2025-06-01')
    assert dps_none is None and warn_none is not None, '无分红数据 → 缺失'
    print('test_dps_ttm_asof_zero_window OK')


def test_snapshot_dividend_yield_zero():
    div = pd.DataFrame({'report_period': ['2023-12-31'], 'implement_date': ['2024-06-30'],
                        'per_share_cash': [0.5]})
    layer = pit.PitLayer('TEST', price=pd.DataFrame({'date': ['2025-09-01'], 'close': [10.0]}),
                         fin=_fin(), div=div)
    snap = layer.asof('2025-09-01')
    assert snap.dps_ttm == 0.0
    assert snap.dividend_yield == 0.0, 'dps=0 时股息率应为0而非None'
    print('test_snapshot_dividend_yield_zero OK: dividend_yield=%.2f' % snap.dividend_yield)


if __name__ == '__main__':
    test_no_dividend_is_zero_yield()
    test_missing_dividend_data_is_nan()
    test_dps_ttm_asof_zero_window()
    test_snapshot_dividend_yield_zero()
    print('== P0-4 股息率0值处理 全部通过 ==')