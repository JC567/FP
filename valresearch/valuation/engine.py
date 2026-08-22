# -*- coding: utf-8 -*-
"""估值序列构建（Phase 3）。

在交易日网格上逐日计算 PIT 可得的：
- PE_TTM = Price / EPS_TTM_PIT（严格 PIT 自算，不使用外部历史 PE）
- 股息率 DY = DPS_TTM / price（DPS_TTM 用 implement_date 近12个月滚动现金分红）
- 分红率 payout = 现金分红总额TTM / 归母净利润TTM（严格总额口径）

V1.6.1: TTM 计算统一委托 pit.py（唯一实现），engine.py 不再包含独立 TTM 算法。
全部基于 PitLayer.asof 语义的向量化实现（无未来函数）。
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from valresearch.data import pit


def dps_ttm_rolling(div, dates):
    """日期网格上的 DPS_TTM（近12个月已实施现金分红，滚动求和）。"""
    if div is None or div.empty:
        return np.full(len(dates), np.nan)
    d = div.copy()
    d['imp_ts'] = pd.to_datetime(d['implement_date'])
    d['ps'] = pd.to_numeric(d['per_share_cash'], errors='coerce')
    d = d.dropna(subset=['imp_ts', 'ps']).sort_values('imp_ts')
    if d.empty:
        return np.full(len(dates), np.nan)
    imp = d['imp_ts'].values.astype('datetime64[D]')
    ps = d['ps'].values.astype(float)
    csum = np.concatenate([[0.0], np.cumsum(ps)])
    dt = np.asarray(pd.to_datetime(dates)).astype('datetime64[D]')
    lo = np.searchsorted(imp, dt - np.timedelta64(365, 'D'), side='left')
    hi = np.searchsorted(imp, dt, side='right')
    return csum[hi] - csum[lo]


def pe_pit_series(dates, close, eps):
    """严格 PIT 自算 PE_TTM 序列（P0-1）：PE=close/eps，eps<=0 或 close<=0 → NaN 且 invalid。
    不再使用外部历史 PE。返回 (values, valid_ndarray)。"""
    close = np.asarray(close, dtype=float)
    eps = np.asarray(eps, dtype=float)
    valid = np.isfinite(close) & (close > 0) & np.isfinite(eps) & (eps > 0)
    pe = np.full(len(dates), np.nan)
    pe[valid] = close[valid] / eps[valid]
    return pe, valid


def pe_step(pe, dates):
    """[DEPRECATED P0-1] PE_TTM 阶梯函数（外部历史PE），不再用于正式估值，仅保留兼容。"""
    if pe is None or pe.empty:
        return np.full(len(dates), np.nan), np.zeros(len(dates), dtype=bool)
    p = pe.copy()
    p['d_ts'] = pd.to_datetime(p['date'])
    p['pe'] = pd.to_numeric(p['pe_ttm'], errors='coerce')
    p = p.sort_values('d_ts')
    dts = p['d_ts'].values.astype('datetime64[D]')
    vals = p['pe'].values.astype(float)
    dt = np.asarray(pd.to_datetime(dates)).astype('datetime64[D]')
    idx = np.searchsorted(dts, dt, side='right') - 1
    has = idx >= 0
    v = np.where(has, vals[np.maximum(idx, 0)], np.nan)
    return v, has



def build_series(price, pe, fin, div, window_years=10, end=None):
    """返回 DataFrame[date, pe, pe_valid, pe_source, dy, payout, eps_ttm, dps_ttm, ...]。
    price: DataFrame[date, close, ...]；其余同上。窗口=[end-10y, end]。

    V1.6.1: TTM 计算统一委托 pit.py，engine.py 不再包含独立 TTM 算法。
    """
    if price is None or price.empty:
        return None
    p = price.copy()
    p['date'] = pd.to_datetime(p['date'])
    p = p.sort_values('date')
    if end is None:
        end = p['date'].iloc[-1]
    end = pd.to_datetime(end)
    start = end - pd.Timedelta(days=int(window_years * 365.25))
    grid = p[(p['date'] >= start) & (p['date'] <= end)][['date', 'close']].copy()
    if grid.empty:
        return None
    dates = grid['date']
    close = grid['close'].astype(float).values

    # V1.6.1: TTM 统一委托 pit.py —— 唯一 TTM 实现
    eps = np.full(len(dates), np.nan)
    np_ttm = np.full(len(dates), np.nan)
    for i, d in enumerate(dates):
        e, _ = pit.eps_ttm_asof(fin, d)
        if e is not None:
            eps[i] = float(e)
        n, _ = pit.net_profit_ttm_asof(fin, d)
        if n is not None:
            np_ttm[i] = float(n)

    dps = dps_ttm_rolling(div, dates)
    pe_v, pe_has = pe_pit_series(dates, close, eps)

    # P0-4: 无分红(dps==0)是真实 0%（参与分位），只有数据缺失(dps=NaN)才为 NaN
    dps_arr = np.asarray(dps, dtype=float)
    valid_dps = np.isfinite(dps_arr) & (dps_arr >= 0)
    valid_price = close > 0
    valid_eps = np.isfinite(eps) & (eps > 0)
    dy = np.full(len(dates), np.nan)
    dy[valid_dps & valid_price] = np.where(
        dps_arr[valid_dps & valid_price] > 0,
        dps_arr[valid_dps & valid_price] / close[valid_dps & valid_price] * 100.0,
        0.0)

    # P0-D: 正式 payout = 现金分红总额TTM / 归母净利TTM。
    # 股本(shares)=归母净利TTM/EPS_TTM；现金分红总额TTM=DPS_TTM×股本。
    valid_np = np.isfinite(np_ttm) & (np_ttm > 0)
    shares = np.where(valid_np & valid_eps, np_ttm / eps, np.nan)
    total_div_ttm = np.where(np.isfinite(shares) & (shares > 0) & valid_dps,
                             dps_arr * shares, np.nan)
    valid_total = np.isfinite(total_div_ttm) & (total_div_ttm >= 0)
    payout = np.full(len(dates), np.nan)
    payout[valid_total & valid_np] = np.where(
        total_div_ttm[valid_total & valid_np] > 0,
        total_div_ttm[valid_total & valid_np] / np_ttm[valid_total & valid_np] * 100.0,
        0.0)
    # 交叉验证（每股口径，仅供校验）
    payout_crosscheck = np.full(len(dates), np.nan)
    payout_crosscheck[valid_dps & valid_eps] = np.where(
        dps_arr[valid_dps & valid_eps] > 0,
        dps_arr[valid_dps & valid_eps] / eps[valid_dps & valid_eps] * 100.0,
        0.0)
    out = pd.DataFrame({
        'date': dates.values,
        'close': close,
        'pe': pe_v,
        'pe_valid': pe_has,
        'pe_source': 'PIT_CALCULATED',
        'dy': dy,
        'payout': payout,                       # 正式：现金分红总额TTM/归母净利TTM
        'payout_crosscheck': payout_crosscheck, # 仅交叉验证：DPS_TTM/EPS_TTM
        'payout_method': 'STRICT_TOTAL',
        'np_ttm': np_ttm,
        'shares_ttm': shares,
        'total_div_ttm': total_div_ttm,
        'eps_ttm': eps,
        'dps_ttm': dps,
    })
    return out
