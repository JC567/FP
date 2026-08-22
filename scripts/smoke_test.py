# -*- coding: utf-8 -*-
"""Smoke test: verify core imports and minimal offline computations."""
import os
import sys
import traceback

# Ensure the project root is on sys.path so valresearch is importable
# regardless of where this script is invoked from.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import numpy as np
import pandas as pd


def _banner(msg):
    print(f"\n{'='*60}\n  {msg}\n{'='*60}")


def _ok(msg):
    print(f"  [OK] {msg}")


def _fail(msg):
    print(f"  [FAIL] {msg}")


# ---------- 1. Import core modules ----------
_banner("Step 1: Import core modules")
try:
    import valresearch.data.pit as pit
    import valresearch.data.pit_pe as pit_pe
    import valresearch.valuation.engine as engine
    import valresearch.config as config
    import valresearch.models as models
    _ok("All core modules imported successfully")
except Exception as e:
    _fail(f"Import error: {e}")
    traceback.print_exc()
    sys.exit(1)

# ---------- 2. Load config ----------
_banner("Step 2: Load config (balanced)")
try:
    cfg = config.get_config('balanced')
    _ok(f"Config loaded, mode={cfg.get('mode')}")
except Exception as e:
    _fail(f"Config error: {e}")
    traceback.print_exc()
    sys.exit(1)

# ---------- 3. Minimal synthetic financial DataFrame ----------
_banner("Step 3: Create synthetic financial DataFrame")
try:
    fin = pd.DataFrame([
        # 2022Q3: used as prev_same for 2023Q3
        {'announcement_date': '2022-10-28', 'report_period': '2022-09-30',
         'eps_basic': 0.20, 'net_profit_attr': 20_000_000},
        # 2022 annual: used as prev_annual for 2023 quarters
        {'announcement_date': '2023-03-30', 'report_period': '2022-12-31',
         'eps_basic': 0.90, 'net_profit_attr': 90_000_000},
        # 2023Q1
        {'announcement_date': '2023-04-28', 'report_period': '2023-03-31',
         'eps_basic': 0.25, 'net_profit_attr': 25_000_000},
        # 2023Q2
        {'announcement_date': '2023-08-28', 'report_period': '2023-06-30',
         'eps_basic': 0.55, 'net_profit_attr': 55_000_000},
        # 2023Q3
        {'announcement_date': '2023-10-28', 'report_period': '2023-09-30',
         'eps_basic': 0.30, 'net_profit_attr': 30_000_000},
        # 2023 annual
        {'announcement_date': '2024-03-28', 'report_period': '2023-12-31',
         'eps_basic': 1.20, 'net_profit_attr': 120_000_000},
    ])
    _ok(f"Financial DataFrame: {len(fin)} rows")
except Exception as e:
    _fail(f"DataFrame creation error: {e}")
    traceback.print_exc()
    sys.exit(1)

# ---------- 4. Minimal price DataFrame ----------
_banner("Step 4: Create synthetic price DataFrame")
try:
    dates = pd.bdate_range('2023-10-23', periods=10)
    price = pd.DataFrame({
        'date': dates.strftime('%Y-%m-%d'),
        'close': [9.8, 9.9, 10.0, 10.1, 10.0, 10.2, 10.3, 10.1, 10.0, 9.9],
    })
    _ok(f"Price DataFrame: {len(price)} rows, date range {price['date'].iloc[0]}..{price['date'].iloc[-1]}")
except Exception as e:
    _fail(f"Price DataFrame error: {e}")
    traceback.print_exc()
    sys.exit(1)

# ---------- 5. Minimal dividend DataFrame ----------
_banner("Step 5: Create synthetic dividend DataFrame")
try:
    div = pd.DataFrame([
        {'implement_date': '2023-07-10', 'per_share_cash': 0.15, 'report_period': '2022-12-31'},
        {'implement_date': '2024-01-15', 'per_share_cash': 0.10, 'report_period': '2023-06-30'},
    ])
    _ok(f"Dividend DataFrame: {len(div)} records")
except Exception as e:
    _fail(f"Dividend DataFrame error: {e}")
    traceback.print_exc()
    sys.exit(1)

# ---------- 6. Compute EPS_TTM ----------
_banner("Step 6: Compute EPS_TTM via pit.eps_ttm_asof()")
try:
    # As of 2023-10-30, the latest available report is 2023Q3 (announced 2023-10-28)
    # EPS_TTM = 0.30 + 0.90 (2022 annual) - 0.20 (2022Q3) = 1.00
    ttm_val, reason = pit.eps_ttm_asof(fin, '2023-10-30')
    assert ttm_val is not None, f"EPS_TTM should not be None, reason={reason}"
    assert abs(ttm_val - 1.0) < 1e-9, f"EPS_TTM expected ~1.0, got {ttm_val}"
    _ok(f"EPS_TTM = {ttm_val:.4f} (expected 1.0000)")
except Exception as e:
    _fail(f"EPS_TTM error: {e}")
    traceback.print_exc()
    sys.exit(1)

# ---------- 7. Compute PE ----------
_banner("Step 7: Compute PE via pit_pe.compute_pe_ttm_pit()")
try:
    # Price ~10.0 at 2023-10-30, EPS_TTM ~1.0 => PE ~10.0
    pe_val, valid, reason, source = pit_pe.compute_pe_ttm_pit(10.0, ttm_val, '2023-10-30')
    assert valid, f"PE should be valid, reason={reason}"
    assert abs(pe_val - 10.0) < 1e-9, f"PE expected ~10.0, got {pe_val}"
    _ok(f"PE_TTM = {pe_val:.4f} (expected 10.0000), source={source}")
except Exception as e:
    _fail(f"PE compute error: {e}")
    traceback.print_exc()
    sys.exit(1)

# ---------- 8. Compute PitSnapshot ----------
_banner("Step 8: Compute PitSnapshot via PitLayer.asof()")
try:
    layer = pit.PitLayer(symbol='TEST', price=price, pe=None, fin=fin, div=div)
    snap = layer.asof('2023-10-30')
    _ok(f"PitSnapshot: price={snap.price}, eps_ttm={snap.eps_ttm}, pe_ttm={snap.pe_ttm}, "
        f"dps_ttm={snap.dps_ttm}, dividend_yield={snap.dividend_yield}, "
        f"payout_ratio={snap.payout_ratio}, report_period={snap.report_period}")
except Exception as e:
    _fail(f"PitSnapshot error: {e}")
    traceback.print_exc()
    sys.exit(1)

# ---------- 9. Build valuation series ----------
_banner("Step 9: Build valuation series via engine.build_series()")
try:
    series = engine.build_series(price=price, pe=None, fin=fin, div=div,
                                 window_years=1, end='2023-10-30')
    assert series is not None, "build_series returned None"
    assert len(series) > 0, "build_series returned empty DataFrame"
    _ok(f"Valuation series: {len(series)} rows, "
        f"columns={list(series.columns)}")
    print(f"\n  Sample (last 3 rows):\n{series.tail(3).to_string(index=False)}")
except Exception as e:
    _fail(f"Build series error: {e}")
    traceback.print_exc()
    sys.exit(1)

# ---------- 10. Summary ----------
_banner("ALL STEPS PASSED")
print("  Smoke test completed successfully.")
sys.exit(0)
