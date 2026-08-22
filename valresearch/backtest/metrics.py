# -*- coding: utf-8 -*-
"""回测绩效指标。返回 dict。"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _cagr(final, init, years):
    if init <= 0 or final <= 0 or years <= 0:
        return None
    return float((final / init) ** (1.0 / years) - 1.0)


def metrics(equity: pd.Series, benchmark: pd.Series = None, periods_per_year: int = 252):
    """equity/benchmark: 净值序列(以起始=1)。返回绩效指标 dict。"""
    eq = pd.to_numeric(equity, errors='coerce').dropna()
    if eq.empty or eq.iloc[0] == 0:
        return {}
    ret = eq / eq.shift(1) - 1
    ret = ret.dropna()
    res = {}
    years = len(eq) / periods_per_year
    res['cagr'] = round(_cagr(eq.iloc[-1], 1.0, years), 4) if years > 0 else None
    if len(ret) >= 2:
        ann_vol = float(ret.std(ddof=1) * np.sqrt(periods_per_year))
        res['annual_volatility'] = round(ann_vol, 4)
        sharpe = float(ret.mean() / ret.std(ddof=1) * np.sqrt(periods_per_year)) \
            if ret.std(ddof=1) > 0 else 0.0
        res['sharpe'] = round(sharpe, 3)
    else:
        res['annual_volatility'] = None
        res['sharpe'] = None
    # 最大回撤
    runmax = eq.cummax()
    dd = (eq / runmax - 1.0).min()
    res['max_drawdown'] = round(float(dd), 4)
    res['calmar'] = round(res['cagr'] / abs(dd), 3) if res['cagr'] is not None and dd < 0 else None
    # 超额 & 与基准对比
    if benchmark is not None and not pd.to_numeric(benchmark, errors='coerce').dropna().empty:
        bm = pd.to_numeric(benchmark, errors='coerce').dropna()
        bm = bm / bm.iloc[0]
        res['benchmark_cagr'] = round(_cagr(bm.iloc[-1], 1.0, len(bm) / periods_per_year), 4) \
            if len(bm) / periods_per_year > 0 else None
        res['excess_return'] = round(float((eq.iloc[-1] - 1.0) - (bm.iloc[-1] - 1.0)), 4)
        # 与基准对齐求 alpha 近似 = 策略CAGR - 基准CAGR
        if res.get('benchmark_cagr') is not None and res['cagr'] is not None:
            res['alpha'] = round(res['cagr'] - res['benchmark_cagr'], 4)
    res['final_value'] = round(float(eq.iloc[-1]), 4)
    res['total_return'] = round(float(eq.iloc[-1] - 1.0), 4)
    return res


def win_rate(signals: pd.Series, returns: pd.Series):
    """信号期 vs 非信号期收益胜率/平均。returns 为未来一期收益序列。"""
    if signals.empty or returns.empty:
        return {}
    active = signals.astype(bool)
    a = returns[active]
    n = returns[~active]
    return {
        'active_periods': int(a.shape[0]),
        'inactive_periods': int(n.shape[0]),
        'active_mean_ret': round(float(a.mean()), 5) if not a.empty else None,
        'inactive_mean_ret': round(float(n.mean()), 5) if not n.empty else None,
        'active_win_rate': round(float((a > 0).mean()), 4) if not a.empty else None,
    }