# -*- coding: utf-8 -*-
"""P0-4 Golden Case 测试：1000次随机打乱验证 PIT TTM 计算确定性。

核心保证：无论财务数据行顺序如何，只要 PIT 信息相同，最终 EPS_TTM 必须相同。
这是 V1.6.1 的关键质量门禁。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import random
import numpy as np
import pandas as pd

from valresearch.data import pit
from valresearch.valuation import engine


def _make_fin_with_revision():
    """构造含修订的财务数据：同一报告期有两个版本。包含完整的历史季度数据以支持TTM外推。"""
    return pd.DataFrame({
        'report_period': [
            '2022-03-31', '2022-06-30', '2022-09-30', '2022-12-31',
            '2023-03-31', '2023-06-30', '2023-09-30', '2023-12-31',
            '2023-12-31',  # 修订版
        ],
        'announcement_date': [
            '2022-04-25', '2022-08-28', '2022-10-30', '2023-03-28',
            '2023-04-25', '2023-08-28', '2023-10-30', '2024-03-28',
            '2024-06-15',  # 修订公告日
        ],
        'eps_basic': [
            0.22,  # 2022Q1
            0.48,  # 2022Q2
            0.75,  # 2022Q3
            1.00,  # 2022年报
            0.28,  # 2023Q1
            0.55,  # 2023Q2
            0.82,  # 2023Q3
            1.10,  # 2023年报 v1
            0.95,  # 2023年报 v2 (修订)
        ],
        'revenue': [22e8, 48e8, 75e8, 100e8, 25e8, 52e8, 78e8, 105e8, 98e8],
        'net_profit_attr': [2.2e8, 4.8e8, 7.5e8, 10e8, 2.8e8, 5.5e8, 8.2e8, 11e8, 9.5e8],
        'ocf': [None] * 9,
        'total_assets': [None] * 9,
        'total_liabilities': [None] * 9,
        'int_bearing_debt': [None] * 9,
    })


def test_eps_ttm_determinism_1000_shuffles():
    """1000次随机打乱：同一财务数据不同行顺序 → EPS_TTM 必须完全相同。"""
    fin = _make_fin_with_revision()
    asof_date = '2024-01-15'  # 在修订公告前

    # 基准：原始顺序
    base_ttm, _ = pit.eps_ttm_asof(fin, asof_date)
    assert base_ttm is not None, '基准TTM不应为None'

    n_matches = 0
    n_shuffles = 1000
    for seed in range(n_shuffles):
        shuffled = fin.sample(frac=1, random_state=seed).reset_index(drop=True)
        ttm, _ = pit.eps_ttm_asof(shuffled, asof_date)
        if ttm is not None and abs(ttm - base_ttm) < 1e-10:
            n_matches += 1

    assert n_matches == n_shuffles, \
        f'Golden Case 失败: {n_matches}/{n_shuffles} 次匹配 (期望 100%)'
    print(f'test_eps_ttm_determinism_1000_shuffles OK: {n_matches}/{n_shuffles} 次全部匹配')


def test_eps_ttm_determinism_with_revision_1000_shuffles():
    """1000次随机打乱 + 修订场景：修订公告后取v2，修订公告前取v1。"""
    fin = _make_fin_with_revision()
    base_before, _ = pit.eps_ttm_asof(fin, '2024-01-15')
    base_after, _ = pit.eps_ttm_asof(fin, '2024-07-01')
    assert base_before is not None and base_after is not None
    assert abs(base_before - base_after) > 0.01, '修订前后TTM应不同'

    n_ok = 0
    for seed in range(1000):
        shuffled = fin.sample(frac=1, random_state=seed).reset_index(drop=True)
        t1, _ = pit.eps_ttm_asof(shuffled, '2024-01-15')
        t2, _ = pit.eps_ttm_asof(shuffled, '2024-07-01')
        if (t1 is not None and t2 is not None and
                abs(t1 - base_before) < 1e-10 and abs(t2 - base_after) < 1e-10):
            n_ok += 1

    assert n_ok == 1000, f'修订场景 Golden Case 失败: {n_ok}/1000'
    print(f'test_eps_ttm_determinism_with_revision_1000_shuffles OK: {n_ok}/1000')


def test_net_profit_ttm_determinism_1000_shuffles():
    """1000次随机打乱：归母净利润 TTM 也必须确定性一致。"""
    fin = _make_fin_with_revision()
    base_ttm, _ = pit.net_profit_ttm_asof(fin, '2024-01-15')
    assert base_ttm is not None

    n_ok = 0
    for seed in range(1000):
        shuffled = fin.sample(frac=1, random_state=seed).reset_index(drop=True)
        ttm, _ = pit.net_profit_ttm_asof(shuffled, '2024-01-15')
        if ttm is not None and abs(ttm - base_ttm) < 1e-6:
            n_ok += 1

    assert n_ok == 1000, f'NP_TTM Golden Case 失败: {n_ok}/1000'
    print(f'test_net_profit_ttm_determinism_1000_shuffles OK: {n_ok}/1000')


def test_build_series_determinism_100_shuffles():
    """100次随机打乱：build_series 产出的估值序列必须确定性一致。"""
    fin = _make_fin_with_revision()
    price = pd.DataFrame({
        'date': pd.date_range('2023-01-03', periods=50, freq='B'),
        'close': 10.0 + np.random.RandomState(42).randn(50).cumsum() * 0.1,
    })
    div = pd.DataFrame(columns=['report_period', 'implement_date', 'per_share_cash'])

    base_ser = engine.build_series(price, None, fin, div, window_years=2, end='2024-06-01')
    assert base_ser is not None and not base_ser.empty

    n_ok = 0
    for seed in range(100):
        shuffled = fin.sample(frac=1, random_state=seed).reset_index(drop=True)
        ser = engine.build_series(price, None, shuffled, div, window_years=2, end='2024-06-01')
        if ser is not None and not ser.empty:
            eps_match = np.allclose(
                ser['eps_ttm'].values, base_ser['eps_ttm'].values,
                equal_nan=True, atol=1e-10)
            pe_match = np.allclose(
                ser['pe'].values, base_ser['pe'].values,
                equal_nan=True, atol=1e-10)
            if eps_match and pe_match:
                n_ok += 1

    assert n_ok == 100, f'build_series Golden Case 失败: {n_ok}/100'
    print(f'test_build_series_determinism_100_shuffles OK: {n_ok}/100')


if __name__ == '__main__':
    test_eps_ttm_determinism_1000_shuffles()
    test_eps_ttm_determinism_with_revision_1000_shuffles()
    test_net_profit_ttm_determinism_1000_shuffles()
    test_build_series_determinism_100_shuffles()
    print('== P0-4 Golden Case 全部通过 ==')
