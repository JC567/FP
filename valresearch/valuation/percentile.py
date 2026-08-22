# -*- coding: utf-8 -*-
"""历史分位数引擎（Phase 4）。

严格 count 口径：Pct = count(历史样本 < 当前值) / 有效样本数 × 100
（非 pandas 默认线性插值分位）。输出 Min/Max/Median/P10..P90 等统计量。
支持异常值处理：negative_pe exclude；payout winsorize 前后各1%并保留原始值。
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from valresearch.models import PercentileStats


def count_pct(series, cur):
    """严格 count 分位：低于当前值的样本占比×100。cur 不在样本时即其自身分位。"""
    s = pd.to_numeric(series, errors='coerce').dropna()
    if s.empty or pd.isna(cur):
        return None
    return round(float((s < float(cur)).mean()) * 100.0, 2)


def quantiles(series):
    s = pd.to_numeric(series, errors='coerce').dropna()
    if s.empty:
        return {}
    q = s.quantile([0.0, 0.10, 0.20, 0.25, 0.30, 0.50, 0.70, 0.75, 0.80, 0.90, 1.0])
    return {'min': round(float(q.iloc[0]), 2), 'p10': round(float(q.iloc[1]), 2),
            'p20': round(float(q.iloc[2]), 2), 'p25': round(float(q.iloc[3]), 2),
            'p30': round(float(q.iloc[4]), 2), 'p50': round(float(q.iloc[5]), 2),
            'p70': round(float(q.iloc[6]), 2), 'p75': round(float(q.iloc[7]), 2),
            'p80': round(float(q.iloc[8]), 2), 'p90': round(float(q.iloc[9]), 2),
            'max': round(float(q.iloc[10]), 2)}


def percentile_stats(series, cur, window_years=10, n_excluded=0,
                     start=None, end=None) -> PercentileStats:
    """主窗口分位统计。series 为窗口内有效值（已按口径过滤异常）。"""
    st = PercentileStats()
    s = pd.to_numeric(series, errors='coerce').dropna()
    if s.empty or pd.isna(cur):
        st.n_valid = int(len(s))
        st.n_excluded = int(n_excluded)
        if start: st.window_10y_start = str(start)
        if end: st.window_10y_end = str(end)
        return st
    st.pct_10y = count_pct(s, cur)
    st.n_valid = int(len(s))
    st.n_excluded = int(n_excluded)
    if start: st.window_10y_start = str(start)
    if end: st.window_10y_end = str(end)
    q = quantiles(s)
    st.min = q.get('min'); st.max = q.get('max'); st.median = q.get('p50')
    st.p10 = q.get('p10'); st.p25 = q.get('p25'); st.p50 = q.get('p50')
    st.p75 = q.get('p75'); st.p90 = q.get('p90')
    st.p20 = q.get('p20'); st.p30 = q.get('p30'); st.p70 = q.get('p70'); st.p80 = q.get('p80')
    return st


def percentile_5y(series, cur, start=None, end=None):
    """辅窗口(5Y)分位。返回 pct 及窗口起止。"""
    s = pd.to_numeric(series, errors='coerce').dropna()
    if s.empty or pd.isna(cur):
        return None
    return {
        'pct': count_pct(s, cur),
        'n_valid': int(len(s)),
        'start': str(start) if start else None,
        'end': str(end) if end else None,
    }


# ---------- 异常值处理 ----------

def filter_pe(series, cur, negative_pe='exclude', winsorize=False):
    """PE 分位输入。negative_pe=exclude: 剔除 PE<=0；winsorize 可选。返回 (valid_series, n_excluded, cur)。"""
    s = pd.to_numeric(series, errors='coerce')
    raw = s.copy()
    n_excluded = 0
    if negative_pe in ('exclude', 'winsorize'):
        n_excluded = int((s <= 0).sum())
        s = s[s > 0]
    if winsorize:
        lo, hi = s.quantile(0.01), s.quantile(0.99)
        s = s.clip(lo, hi)
    return s.dropna(), n_excluded, cur


def filter_payout(series, cur, lower=0.0, upper=1.5, winsorize=True, winsor_percent=0.01):
    """分红率分位输入。越界(<lower或>upper)打 abnormal 标记但默认剔除出分位样本；winsorize 可选。
    返回 (valid_series, n_excluded, abnormal_flags, cur)。"""
    s = pd.to_numeric(series, errors='coerce')
    abnormal = (s < lower * 100) | (s > upper * 100)
    n_excluded = int(abnormal.sum())
    valid = s[~abnormal]
    if winsorize and len(valid) > 1:
        lo = valid.quantile(winsor_percent)
        hi = valid.quantile(1 - winsor_percent)
        valid = valid.clip(lo, hi)
    return valid.dropna(), n_excluded, abnormal, cur


def evaluate_pe_outlier(pe_value, upper_bound=None):
    """PE 极端值标记：>1000 视为异常但保留（不删极端贵历史）。"""
    if pd.isna(pe_value):
        return False
    return bool(pe_value > 1000) or (upper_bound is not None and pe_value > upper_bound)