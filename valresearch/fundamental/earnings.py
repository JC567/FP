# -*- coding: utf-8 -*-
"""盈利稳定性评分(0-100)。基于公告日<=t 的年度财务数据。"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _annual(fin, t, col):
    from valresearch.data.pit import annual_versions_pit
    ann = annual_versions_pit(fin, t)   # 修订感知：每期取当时最新版本，announcement_date<=t
    if ann is None:
        return pd.DataFrame()
    a = ann[pd.to_numeric(ann[col], errors='coerce').notna()].sort_values('per_ts')
    return a


def _cagr(first, last, n):
    if first is None or last is None or n <= 0 or first <= 0 or last <= 0:
        return None
    return (last / first) ** (1.0 / n) - 1.0


def earnings_stability(fin, t, years=5) -> dict:
    res = {'score': 50, 'cagr_revenue': None, 'cagr_np': None, 'cagr_eps': None,
           'np_vol': None, 'np_max_drawdown': None, 'consecutive_declines': 0,
           'single_year_drop': False, 'flags': [], 'warnings': [], 'available': True}
    if fin is None or fin.empty:
        res['available'] = False
        res['warnings'].append('盈利稳定性: 无财报数据(DATA_INSUFFICIENT)')
        return res
    np_ann = _annual(fin, t, 'net_profit_attr')
    eps_ann = _annual(fin, t, 'eps_basic')
    rev_ann = _annual(fin, t, 'revenue')
    score = 60.0

    def add_cagr(ann, name):
        if len(ann) >= years + 1:
            v = _cagr(ann[col].iloc[0], ann[col].iloc[-1], len(ann) - 1)
            return v
        return None
    col = 'net_profit_attr'
    res['cagr_np'] = add_cagr(np_ann, 'cagr_np')
    if len(np_ann) >= years + 1:
        ser = np_ann[col].astype(float)
        if (ser > 0).all():
            yoy = ser.pct_change().dropna()
            res['np_vol'] = round(float(yoy.std()), 3)
            res['consecutive_declines'] = _consec_neg(yoy)
            res['single_year_drop'] = bool((yoy < -0.30).any())
            peak = ser.cummax()
            dd = (ser - peak) / peak
            res['np_max_drawdown'] = round(float(dd.min()) * 100, 1)
            # 评分调整
            score += max(-30, min(20, 100 * float(res['cagr_np'] if res['cagr_np'] is not None else 0)))
            score -= 10 * res['consecutive_declines']
            if res['single_year_drop']:
                score -= 15
                res['flags'].append('EARNINGS_WARNING: 单年净利YoY<-30%')
            if res['np_vol'] is not None and res['np_vol'] > 0.4:
                score -= 10
        else:
            res['flags'].append('EARNINGS_WARNING: 存在亏损年度(净利非正)')
            score -= 20
    eps_ann['col'] = eps_ann['eps_basic']
    res['cagr_eps'] = _cagr(eps_ann['eps_basic'].iloc[0], eps_ann['eps_basic'].iloc[-1],
                            len(eps_ann) - 1) if len(eps_ann) >= years + 1 else None
    if rev_ann is not None and len(rev_ann) >= years + 1:
        res['cagr_revenue'] = _cagr(rev_ann['revenue'].iloc[0], rev_ann['revenue'].iloc[-1],
                                    len(rev_ann) - 1)
    if res['consecutive_declines'] >= 2:
        res['flags'].append('VALUE_TRAP_HINT: 连续两年净利下滑')
    res['score'] = round(max(0, min(100, score)))
    return res


def _consec_neg(yoy):
    max_run = 0
    run = 0
    for v in yoy:
        if v < 0:
            run += 1
            max_run = max(max_run, run)
        else:
            run = 0
    return max_run