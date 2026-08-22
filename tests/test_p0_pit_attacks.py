# -*- coding: utf-8 -*-
"""P0 PIT Attack tests: boundary / order-invariance / multi-revision / traceability."""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

from valresearch.data.pit import (
    eps_ttm_asof, net_profit_ttm_asof, annual_versions_pit,
    select_financial_version, price_asof, PitLayer,
)
from valresearch.data.pit_pe import compute_pe_ttm_pit
from valresearch.models import PitSnapshot

STD_COLS = ['report_period', 'announcement_date', 'eps_basic', 'net_profit_attr',
            'revenue', 'ocf', 'total_assets', 'total_liabilities', 'int_bearing_debt']


def _r(report_period, announcement_date, eps_basic, net_profit_attr=None, **kw):
    row = {c: kw.get(c) for c in STD_COLS[3:]}
    row.update({'report_period': report_period, 'announcement_date': announcement_date,
                'eps_basic': eps_basic, 'net_profit_attr': net_profit_attr
                if net_profit_attr is not None else eps_basic * 10e8})
    return row


def _fin(*rows):
    return pd.DataFrame(list(rows))


def _mk_price(dates, closes):
    return pd.DataFrame({'date': dates, 'close': closes})


# ── 1. test_same_announcement_date_multiple_periods ──
def test_same_announcement_date_multiple_periods():
    name = 'test_same_announcement_date_multiple_periods'
    fin = _fin(
        _r('2023-12-31', '2024-04-28', 0.80, 8e8),
        _r('2024-12-31', '2025-04-30', 1.00, 10e8),
        _r('2025-03-31', '2025-04-30', 0.30, 3e8),
    )
    v_fy_before = select_financial_version(fin, '2024-12-31', '2025-04-29')
    assert v_fy_before is None, '2024-12-31 ann=04-30, asof=04-29 invisible'
    v_fy_after = select_financial_version(fin, '2024-12-31', '2025-05-01')
    assert v_fy_after is not None and v_fy_after['eps_basic'] == 1.00
    v_q1 = select_financial_version(fin, '2025-03-31', '2025-05-01')
    assert v_q1 is not None and v_q1['eps_basic'] == 0.30
    eps2, _ = eps_ttm_asof(fin, '2025-05-01')
    for seed in range(10):
        shuffled = fin.sample(frac=1, random_state=seed).reset_index(drop=True)
        e, _ = eps_ttm_asof(shuffled, '2025-05-01')
        assert e == eps2, f'seed={seed}: {e} != {eps2}'
    print(f'{name} PASS')


# ── 2. test_pit_is_order_invariant ──
def test_pit_is_order_invariant():
    name = 'test_pit_is_order_invariant'
    fin = _fin(
        _r('2022-09-30', '2022-10-28', 0.20),
        _r('2022-12-31', '2023-03-28', 0.80),
        _r('2023-03-31', '2023-04-25', 0.20),
        _r('2023-06-30', '2023-08-25', 0.25),
        _r('2023-09-30', '2023-10-28', 0.30),
    )
    asof = '2023-11-01'
    base, _ = eps_ttm_asof(fin, asof)
    assert base is not None
    for seed in range(5):
        shuffled = fin.sample(frac=1, random_state=seed).reset_index(drop=True)
        e, _ = eps_ttm_asof(shuffled, asof)
        assert e == base, f'seed={seed}: {e} != {base}'
    print(f'{name} PASS')


# ── 3. test_same_period_multiple_revisions ──
def test_same_period_multiple_revisions():
    name = 'test_same_period_multiple_revisions'
    fin = _fin(
        _r('2024-12-31', '2025-03-01', 1.0, 10e8),
        _r('2024-12-31', '2025-05-01', 1.1, 11e8),
    )
    v1 = select_financial_version(fin, '2024-12-31', '2025-04-01')
    assert v1 is not None and v1['eps_basic'] == 1.0
    v2 = select_financial_version(fin, '2024-12-31', '2025-06-01')
    assert v2 is not None and v2['eps_basic'] == 1.1
    print(f'{name} PASS')


# ── 4. test_missing_field_revision ──
def test_missing_field_revision():
    name = 'test_missing_field_revision'
    fin = _fin(
        _r('2024-12-31', '2025-03-01', 1.0, 100.0),
        _r('2024-12-31', '2025-05-01', 1.1, np.nan),
    )
    v = select_financial_version(fin, '2024-12-31', '2025-06-01')
    assert v is not None
    assert v['eps_basic'] == 1.1
    assert pd.isna(v['net_profit_attr']), f'Expected NaN, got {v["net_profit_attr"]}'
    print(f'{name} PASS')


# ── 5. test_future_revision_excluded ──
def test_future_revision_excluded():
    name = 'test_future_revision_excluded'
    fin = _fin(
        _r('2020-12-31', '2021-03-01', 1.0, 10e8),
        _r('2020-12-31', '2022-05-01', 1.2, 12e8),
    )
    eps1, _ = eps_ttm_asof(fin, '2021-12-31')
    assert eps1 == 1.0, f'Expected 1.0, got {eps1}'
    eps2, _ = eps_ttm_asof(fin, '2022-12-31')
    assert eps2 == 1.2, f'Expected 1.2, got {eps2}'
    print(f'{name} PASS')


# ── 6. test_future_period_excluded ──
def test_future_period_excluded():
    name = 'test_future_period_excluded'
    fin = _fin(
        _r('2021-12-31', '2022-02-28', 0.90),
        _r('2022-12-31', '2023-03-28', 1.0),
        _r('2023-09-30', '2023-10-28', 0.90),
        _r('2023-12-31', '2024-04-30', 1.20),
    )
    eps_old, _ = eps_ttm_asof(fin, '2022-04-01')
    assert eps_old == 0.90, f'asof before 2022FY ann: expected 0.90, got {eps_old}'
    eps_mid, _ = eps_ttm_asof(fin, '2023-06-30')
    assert eps_mid == 1.0, f'asof mid-2023 (Q3 unseen): expected 1.0, got {eps_mid}'
    eps_late, _ = eps_ttm_asof(fin, '2024-05-01')
    assert eps_late == 1.20, f'asof after 2023FY ann: expected 1.20, got {eps_late}'
    print(f'{name} PASS')


# ── 7. test_same_day_multi_report_revision ──
def test_same_day_multi_report_revision():
    name = 'test_same_day_multi_report_revision'
    fin = _fin(
        _r('2023-12-31', '2024-03-28', 0.80),
        _r('2024-12-31', '2025-04-30', 1.0, 10e8),
        _r('2025-03-31', '2025-04-30', 0.25, 2.5e8),
        _r('2024-12-31', '2025-05-01', 1.1, 11e8),
    )
    results = {}
    for asof in ['2025-04-29', '2025-04-30', '2025-05-02']:
        e, _ = eps_ttm_asof(fin, asof)
        results[asof] = e
    for seed in range(100):
        shuffled = fin.sample(frac=1, random_state=seed).reset_index(drop=True)
        for asof in ['2025-04-29', '2025-04-30', '2025-05-02']:
            e, _ = eps_ttm_asof(shuffled, asof)
            assert e == results[asof], f'seed={seed} asof={asof}: {e} != {results[asof]}'
    print(f'{name} PASS (100 shuffles x 3 dates)')


# ── 8. test_pit_ttm_correctness ──
def test_pit_ttm_correctness():
    name = 'test_pit_ttm_correctness'
    fin = _fin(
        _r('2023-03-31', '2023-04-25', 0.25),
        _r('2023-06-30', '2023-08-25', 0.30),
        _r('2023-09-30', '2023-10-28', 0.35),
        _r('2023-12-31', '2024-03-28', 1.20),
        _r('2024-03-31', '2024-04-25', 0.30),
    )
    eps_annual, _ = eps_ttm_asof(fin, '2024-04-01')
    assert eps_annual == 1.20, f'Annual EPS_TTM should be 1.20, got {eps_annual}'
    eps_q1_next, _ = eps_ttm_asof(fin, '2024-05-01')
    expected = 0.30 + 1.20 - 0.25
    assert eps_q1_next == expected, f'Q1 TTM should be {expected}, got {eps_q1_next}'
    print(f'{name} PASS')


# ── 9. test_pe_is_price_divided_by_pit_eps ──
def test_pe_is_price_divided_by_pit_eps():
    name = 'test_pe_is_price_divided_by_pit_eps'
    pe, valid, reason, src = compute_pe_ttm_pit(39.0, 6.0)
    assert pe == 6.5 and valid is True
    pe, valid, _, _ = compute_pe_ttm_pit(10, 1)
    assert pe == 10.0 and valid is True
    pe, valid, reason, _ = compute_pe_ttm_pit(10, -1)
    assert np.isnan(pe) and valid is False and reason == 'EPS_NON_POSITIVE'
    pe, valid, reason, _ = compute_pe_ttm_pit(10, 0)
    assert np.isnan(pe) and valid is False and reason == 'EPS_NON_POSITIVE'
    print(f'{name} PASS')


# ── 10. test_external_pe_not_used ──
def test_external_pe_not_used():
    name = 'test_external_pe_not_used'
    fin = _fin(_r('2024-12-31', '2025-03-01', 1.0, 10e8))
    price = _mk_price(['2025-04-01'], [10.0])
    pe_ext = pd.DataFrame({'date': ['2025-04-01'], 'pe_ttm': [100.0]})
    layer = PitLayer('TEST', price=price, pe=pe_ext, fin=fin, div=None)
    snap = layer.asof('2025-04-01')
    assert snap.pe_ttm == 10.0, f'PE should be 10 (price/eps), got {snap.pe_ttm}'
    assert snap.pe_source == 'PIT_CALCULATED'
    print(f'{name} PASS')


# ── 11. test_pit_snapshot_traceability ──
def test_pit_snapshot_traceability():
    name = 'test_pit_snapshot_traceability'
    fin = _fin(
        _r('2024-12-31', '2025-03-01', 1.0, 10e8),
        _r('2024-12-31', '2025-06-01', 1.1, 11e8),
    )
    price = _mk_price(['2025-04-01', '2025-07-01'], [39.0, 40.0])
    layer = PitLayer('TEST', price=price, pe=None, fin=fin, div=None)
    snap = layer.asof('2025-05-01')
    assert snap.report_period is not None, 'report_period must be populated'
    assert snap.announcement_date is not None, 'announcement_date must be populated'
    assert snap.revision_version is not None, 'revision_version must be populated'
    assert snap.revision_version == 1
    snap2 = layer.asof('2025-07-01')
    assert snap2.revision_version == 2
    print(f'{name} PASS')


if __name__ == '__main__':
    all_tests = [
        test_same_announcement_date_multiple_periods,
        test_pit_is_order_invariant,
        test_same_period_multiple_revisions,
        test_missing_field_revision,
        test_future_revision_excluded,
        test_future_period_excluded,
        test_same_day_multi_report_revision,
        test_pit_ttm_correctness,
        test_pe_is_price_divided_by_pit_eps,
        test_external_pe_not_used,
        test_pit_snapshot_traceability,
    ]
    passed = failed = 0
    for t in all_tests:
        try:
            t()
            passed += 1
        except Exception as e:
            failed += 1
            print(f'{t.__name__} FAIL: {e}')
    print(f'\n=== Summary: {passed} passed, {failed} failed, {len(all_tests)} total ===')
    if failed:
        sys.exit(1)
