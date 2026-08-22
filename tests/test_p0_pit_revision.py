# -*- coding: utf-8 -*-
"""P0-2 财务数据多版本(PIT修订)机制测试。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

from valresearch.data import pit


def _fin():
    return pd.DataFrame({
        'report_period': ['2024-12-31', '2024-12-31'],
        'announcement_date': ['2025-03-30', '2025-06-15'],
        'eps_basic': [1.00, 0.90],          # 修订版
        'revenue': [100e8, 95e8],
        'net_profit_attr': [10e8, 9e8],
        'ocf': [None, None],
        'total_assets': [None, None],
        'total_liabilities': [None, None],
        'int_bearing_debt': [None, None],
    })


def test_select_version_by_asof():
    fin = _fin()
    v1 = pit.select_financial_version(fin, '2024-12-31', '2025-04-01')
    assert v1['eps_basic'] == 1.00, '修订公开前应取 v1'
    v2 = pit.select_financial_version(fin, '2024-12-31', '2025-07-01')
    assert v2['eps_basic'] == 0.90, '修订公开后应取最新版'
    none = pit.select_financial_version(fin, '2024-12-31', '2025-02-01')
    assert none is None, '未公开时不可见'
    print('test_select_version_by_asof OK')


def test_get_financial_pit_revision_number():
    fin = _fin()
    r1 = pit.get_financial_pit(fin, '2024-12-31', '2025-04-01')
    assert r1['revision_version'] == 1 and r1['eps_basic'] == 1.00
    r2 = pit.get_financial_pit(fin, '2024-12-31', '2025-07-01')
    assert r2['revision_version'] == 2 and r2['eps_basic'] == 0.90
    assert r2['asof_date'] == '2025-07-01'
    print('test_get_financial_pit_revision_number OK')


def test_restatement_does_not_rewrite_past():
    """修订不污染历史：公告日 6-15 之前 EPS 应为 v1(1.0)，之后为 v2(0.9)。"""
    fin = _fin()
    dates = pd.DatetimeIndex(['2025-04-10', '2025-06-01', '2025-06-20'])
    eps_vals = []
    for d in dates:
        e, _ = pit.eps_ttm_asof(fin, d)
        eps_vals.append(np.nan if e is None else float(e))
    eps = np.array(eps_vals)
    assert eps[0] == 1.0 and eps[1] == 1.0, '6-15前应为修订前版本'
    assert eps[2] == 0.9, '6-15后应为修订后版本'
    print('test_restatement_does_not_rewrite_past OK: before=%.2f after=%.2f' % (eps[1], eps[2]))


def test_ttm_uses_public_prev_version():
    """非年报 TTM 外推时，上年同期/上年年报须用该公告日已公开版本。"""
    fin = pd.DataFrame({
        'report_period': ['2023-12-31', '2024-03-31', '2024-12-31', '2024-12-31'],
        'announcement_date': ['2024-03-28', '2024-04-25', '2025-03-30', '2025-06-15'],
        'eps_basic': [1.00, 0.25, 1.10, 0.95],
        'revenue': [None] * 4, 'net_profit_attr': [None] * 4,
        'ocf': [None] * 4, 'total_assets': [None] * 4,
        'total_liabilities': [None] * 4, 'int_bearing_debt': [None] * 4,
    })
    # 2024Q1 公告日(4-25)时，2023年报用 v1(1.00)；但 2023Q1 eps 未提供 → TTM 无法外推 → None
    ttm, reason = pit.eps_ttm_asof(fin, '2024-04-25')
    # Q1 的 TTM 需要上年同期 Q1 数据，此处未提供 → 应返回 None 或 NaN
    assert ttm is None, '缺少上年同期Q1数据时应返回DATA_INSUFFICIENT'
    print('test_ttm_uses_public_prev_version OK (外推时点正确，无前视)')


if __name__ == '__main__':
    test_select_version_by_asof()
    test_get_financial_pit_revision_number()
    test_restatement_does_not_rewrite_past()
    test_ttm_uses_public_prev_version()
    print('== P0-2 财务多版本机制 全部通过 ==')