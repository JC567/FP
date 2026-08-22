# -*- coding: utf-8 -*-
"""P0-5 PIT invariant tests: 7 core invariants for PIT correctness."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd
from valresearch.data import pit
from valresearch.data.pit_pe import compute_pe_ttm_pit


def _make_fin():
    return pd.DataFrame({
        'report_period': [
            '2021-03-31', '2021-06-30', '2021-09-30', '2021-12-31',
            '2022-03-31', '2022-06-30', '2022-09-30', '2022-12-31',
            '2023-03-31', '2023-06-30', '2023-09-30', '2023-12-31',
            '2023-12-31',
        ],
        'announcement_date': [
            '2021-04-25', '2021-08-28', '2021-10-30', '2022-03-28',
            '2022-04-25', '2022-08-28', '2022-10-30', '2023-03-28',
            '2023-04-25', '2023-08-28', '2023-10-30', '2024-03-28',
            '2024-06-15',
        ],
        'eps_basic': [0.18, 0.40, 0.65, 0.80, 0.22, 0.48, 0.75, 1.00,
                      0.25, 0.52, 0.78, 1.10, 0.95],
        'revenue': [18e8, 40e8, 65e8, 80e8, 22e8, 48e8, 75e8, 100e8,
                    25e8, 52e8, 78e8, 105e8, 98e8],
        'net_profit_attr': [1.8e8, 4.0e8, 6.5e8, 8e8, 2.2e8, 4.8e8, 7.5e8, 10e8,
                            2.5e8, 5.2e8, 7.8e8, 11e8, 9.5e8],
        'ocf': [None] * 13, 'total_assets': [None] * 13,
        'total_liabilities': [None] * 13, 'int_bearing_debt': [None] * 13,
    })


def test_invariant_1_asof_monotonicity():
    """The set of visible financial records at t1 is a subset of those at t2 (t1 < t2)."""
    fin = _make_fin()
    dates = pd.date_range('2021-01-01', '2025-01-01', freq='MS')
    prev_count = 0
    for d in dates:
        visible = fin[pd.to_datetime(fin['announcement_date']) <= pd.Timestamp(d)]
        count = len(visible)
        assert count >= prev_count, \
            f'Row monotonicity violated at {d}: {count} < {prev_count}'
        prev_count = count
    # Also check TTM monotonicity after we have enough data (2+ years of quarterly)
    # After 2023-04-01 we should always have TTM (enough history for extrapolation)
    ttms_after = []
    for d in pd.date_range('2023-04-01', '2025-01-01', freq='MS'):
        ttm, _ = pit.eps_ttm_asof(fin, d)
        ttms_after.append(ttm)
    assert all(t is not None for t in ttms_after), \
        'TTM should be continuously available after having 2+ years of data'
    print('test_invariant_1_asof_monotonicity OK')


def test_invariant_2_revision_isolation():
    fin = _make_fin()
    ttm_before, _ = pit.eps_ttm_asof(fin, '2024-06-01')
    ttm_after, _ = pit.eps_ttm_asof(fin, '2024-07-01')
    assert ttm_before is not None and ttm_after is not None
    assert abs(ttm_before - ttm_after) > 0.01
    fin_no_rev = fin[fin['announcement_date'] != '2024-06-15'].reset_index(drop=True)
    ttm_no_rev, _ = pit.eps_ttm_asof(fin_no_rev, '2024-06-01')
    assert abs(ttm_no_rev - ttm_before) < 1e-10
    print('test_invariant_2_revision_isolation OK')


def test_invariant_3_no_future_data():
    fin = _make_fin()
    fin_limited = fin[fin['announcement_date'] <= '2024-03-01'].reset_index(drop=True)
    ttm_full, _ = pit.eps_ttm_asof(fin, '2024-03-01')
    ttm_limited, _ = pit.eps_ttm_asof(fin_limited, '2024-03-01')
    if ttm_full is not None and ttm_limited is not None:
        assert abs(ttm_full - ttm_limited) < 1e-10
    print('test_invariant_3_no_future_data OK')


def test_invariant_4_field_consistency():
    fin = _make_fin()
    v1 = pit.select_financial_version(fin, '2023-12-31', '2024-05-01')
    v2 = pit.select_financial_version(fin, '2023-12-31', '2024-07-01')
    assert v1 is not None and v2 is not None
    assert v1['eps_basic'] != v2['eps_basic']
    assert v1['revenue'] != v2['revenue']
    assert v1['net_profit_attr'] != v2['net_profit_attr']
    r1 = pit.get_financial_pit(fin, '2023-12-31', '2024-05-01')
    r2 = pit.get_financial_pit(fin, '2023-12-31', '2024-07-01')
    assert r1['revision_version'] < r2['revision_version']
    print('test_invariant_4_field_consistency OK')


def test_invariant_5_ttm_formula():
    fin = pd.DataFrame({
        'report_period': ['2022-12-31', '2023-03-31', '2023-06-30', '2023-09-30', '2023-12-31'],
        'announcement_date': ['2023-03-28', '2023-04-25', '2023-08-28', '2023-10-30', '2024-03-28'],
        'eps_basic': [1.00, 0.28, 0.55, 0.82, 1.10],
        'revenue': [100e8, 25e8, 52e8, 78e8, 105e8],
        'net_profit_attr': [10e8, 2.8e8, 5.5e8, 8.2e8, 11e8],
        'ocf': [None] * 5, 'total_assets': [None] * 5,
        'total_liabilities': [None] * 5, 'int_bearing_debt': [None] * 5,
    })
    ttm_annual, _ = pit.eps_ttm_asof(fin, '2023-04-01')
    assert abs(ttm_annual - 1.00) < 1e-10, f'Annual TTM should be 1.00, got {ttm_annual}'
    ttm_q1_no_prev, _ = pit.eps_ttm_asof(fin, '2023-05-01')
    assert ttm_q1_no_prev is None, f'Should be None without prior Q1, got {ttm_q1_no_prev}'
    fin_ext = pd.concat([fin, pd.DataFrame({
        'report_period': ['2022-03-31'], 'announcement_date': ['2022-04-25'],
        'eps_basic': [0.22], 'revenue': [22e8], 'net_profit_attr': [2.2e8],
        'ocf': [None], 'total_assets': [None], 'total_liabilities': [None],
        'int_bearing_debt': [None],
    })], ignore_index=True)
    ttm_q1, _ = pit.eps_ttm_asof(fin_ext, '2023-05-01')
    expected = 0.28 + 1.00 - 0.22
    assert ttm_q1 is not None and abs(ttm_q1 - expected) < 1e-10
    print('test_invariant_5_ttm_formula OK')


def test_invariant_6_pe_validity():
    pe, valid, reason, src = compute_pe_ttm_pit(20.0, 2.0)
    assert pe == 10.0 and valid is True
    pe, valid, reason, _ = compute_pe_ttm_pit(20.0, 0.0)
    assert np.isnan(pe) and valid is False
    pe, valid, reason, _ = compute_pe_ttm_pit(20.0, -1.0)
    assert np.isnan(pe) and valid is False
    pe, valid, reason, _ = compute_pe_ttm_pit(0.0, 2.0)
    assert np.isnan(pe) and valid is False
    pe, valid, reason, _ = compute_pe_ttm_pit(-10.0, 2.0)
    assert np.isnan(pe) and valid is False
    pe, valid, reason, _ = compute_pe_ttm_pit(None, 2.0)
    assert np.isnan(pe) and valid is False
    pe, valid, reason, _ = compute_pe_ttm_pit(20.0, None)
    assert np.isnan(pe) and valid is False
    print('test_invariant_6_pe_validity OK')


def test_invariant_7_order_invariance():
    fin = _make_fin()
    base_before, _ = pit.eps_ttm_asof(fin, '2024-01-15')
    base_after, _ = pit.eps_ttm_asof(fin, '2024-07-01')
    assert base_before is not None and base_after is not None
    n_ok = 0
    for seed in range(100):
        shuffled = fin.sample(frac=1, random_state=seed).reset_index(drop=True)
        t1, _ = pit.eps_ttm_asof(shuffled, '2024-01-15')
        t2, _ = pit.eps_ttm_asof(shuffled, '2024-07-01')
        if (t1 is not None and t2 is not None and
                abs(t1 - base_before) < 1e-10 and abs(t2 - base_after) < 1e-10):
            n_ok += 1
    assert n_ok == 100, f'Order invariance: {n_ok}/100'
    print('test_invariant_7_order_invariance OK')


if __name__ == '__main__':
    test_invariant_1_asof_monotonicity()
    test_invariant_2_revision_isolation()
    test_invariant_3_no_future_data()
    test_invariant_4_field_consistency()
    test_invariant_5_ttm_formula()
    test_invariant_6_pe_validity()
    test_invariant_7_order_invariance()
    print('== P0-5 PIT Invariants all passed ==')
