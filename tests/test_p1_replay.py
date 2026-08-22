# -*- coding: utf-8 -*-
"""P1-6 历史回放测试：对历史时点用当时数据重算，验证 PIT、可复现性、回测一致性。

- 可复现: 同一时点重复计算得分一致
- 无前视: 未来数据/未来公告不得改变历史时点信号
- 一致:   build_series 在 t 的末值 == 全序列在 t 的值（无泄漏）
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

from valresearch.valuation import engine
from valresearch.backtest.engine import _signal_at
from valresearch.config import get_config


def _price():
    dates = pd.bdate_range('2023-01-02', '2025-06-30')
    return pd.DataFrame({'date': dates, 'close': np.linspace(10.0, 12.0, len(dates)),
                         'adj_close': np.linspace(10.0, 12.0, len(dates))})


def _fin(extra=None):
    rows = pd.DataFrame({
        'report_period': ['2022-12-31', '2023-03-31', '2023-06-30', '2023-12-31',
                          '2024-03-31', '2024-06-30', '2024-12-31'],
        'announcement_date': ['2023-04-25', '2023-04-28', '2023-08-28', '2024-04-25',
                              '2024-04-28', '2024-08-28', '2025-04-25'],
        'eps_basic': [1.0, 0.25, 0.55, 1.2, 0.30, 0.62, 1.4],
        'revenue': [100e8, 25e8, 52e8, 115e8, 28e8, 58e8, 130e8],
        'net_profit_attr': [10e8, 2.5e8, 5.2e8, 11.5e8, 2.8e8, 5.8e8, 13e8],
        'ocf': [None] * 7, 'total_assets': [100e8] * 7, 'total_liabilities': [40e8] * 7,
        'int_bearing_debt': [None] * 7,
    })
    if extra is not None:
        rows = pd.concat([rows, extra], ignore_index=True)
    return rows


def _div():
    return pd.DataFrame({'report_period': ['2022', '2023'],
                         'implement_date': ['2023-06-30', '2024-06-30'],
                         'per_share_cash': [0.5, 0.6]})


def _bond():
    dates = pd.bdate_range('2023-01-02', '2025-06-30')
    return pd.DataFrame({'date': dates, 'cn10y': 0.025})


def test_replay_reproducible_and_no_lookahead():
    cfg = get_config('balanced')
    price = _price()
    div = _div()
    bond = _bond()
    ind = {'industry': '银行'}
    t = pd.Timestamp('2024-08-30')   # 历史时点（2024Q2 已公告，2024年报/未来未公告）

    base_fin = _fin()
    ser = engine.build_series(price, None, base_fin, div, window_years=11, end=pd.Timestamp('2025-06-30'))
    r1 = _signal_at(t, ser, price, base_fin, div, bond, ind, '银行', cfg)
    r2 = _signal_at(t, ser, price, base_fin, div, bond, ind, '银行', cfg)
    assert r1 is not None and r2 is not None
    assert r1['score'] == r2['score'], '同一点重复计算必须可复现'

    # 未来数据不得污染历史：追加一份"未来公告"的高盈利财报
    future = pd.DataFrame({
        'report_period': ['2025-06-30'], 'announcement_date': ['2025-08-28'],
        'eps_basic': [9.9], 'revenue': [900e8], 'net_profit_attr': [90e8],
        'ocf': [None], 'total_assets': [100e8], 'total_liabilities': [40e8],
        'int_bearing_debt': [None],
    })
    fin_with_future = _fin(future)
    ser2 = engine.build_series(price, None, fin_with_future, div, window_years=11,
                               end=pd.Timestamp('2025-06-30'))
    r3 = _signal_at(t, ser, price, fin_with_future, div, bond, ind, '银行', cfg)
    assert r3['score'] == r1['score'], '未来公告不得改变历史时点信号(无前视)'
    print('test_replay_reproducible_and_no_lookahead OK: score=%s' % r1['score'])


def test_replay_series_value_at_t_consistent():
    """历史回放一致性：截断到 t 的序列在 t 的 EPS/PE 与全序列在 t 相同。"""
    price = _price()
    div = _div()
    fin = _fin()
    t = pd.Timestamp('2024-06-28')   # 交易日
    ser_full = engine.build_series(price, None, fin, div, window_years=11,
                                   end=pd.Timestamp('2025-06-30'))
    ser_at = engine.build_series(price[price['date'] <= t], None, fin, div,
                                 window_years=11, end=t)
    full_last = ser_full[ser_full['date'] == t]
    at_last = ser_at[ser_at['date'] == t]
    assert not at_last.empty and not full_last.empty
    assert abs(float(at_last['eps_ttm'].iloc[0]) - float(full_last['eps_ttm'].iloc[0])) < 1e-9
    assert abs(float(at_last['pe'].iloc[0]) - float(full_last['pe'].iloc[0])) < 1e-9
    print('test_replay_series_value_at_t_consistent OK')


if __name__ == '__main__':
    test_replay_reproducible_and_no_lookahead()
    test_replay_series_value_at_t_consistent()
    print('== P1-6 历史回放测试 全部通过 ==')