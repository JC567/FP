# -*- coding: utf-8 -*-
"""现金流质量评分(0-100)。OCF/NP 三年平均；数据缺失返回中间分并标 DATA_INSUFFICIENT。"""
from __future__ import annotations

import pandas as pd


def cashflow_quality(fin, t, ocf_np_floor=0.8) -> dict:
    res = {'score': 50, 'ocf_np_3y': None, 'ocf_np_years': {}, 'flags': [],
           'warnings': [], 'available': True}
    if fin is None or fin.empty:
        res['available'] = False
        res['warnings'].append('现金流质量: 无财报数据(DATA_INSUFFICIENT)')
        return res
    f = fin.copy()
    f['ann_ts'] = pd.to_datetime(f['announcement_date'])
    a = f[f['ann_ts'] <= pd.to_datetime(t)]
    if 'ocf' not in a.columns or a['ocf'].isna().all():
        res['available'] = False
        res['warnings'].append('现金流质量: 缺少经营现金流总量(OCF)(DATA_INSUFFICIENT)')
        return res
    a = a[pd.to_numeric(a['ocf'], errors='coerce').notna()]
    a = a[pd.to_numeric(a['net_profit_attr'], errors='coerce').notna()]
    if a.empty:
        res['available'] = False
        res['warnings'].append('现金流质量: 缺少净利匹配数据(DATA_INSUFFICIENT)')
        return res
    a = a.copy()
    a['ratio'] = a['ocf'] / a['net_profit_attr']
    ratios = a[a['net_profit_attr'] != 0]['ratio'].dropna()
    if ratios.empty:
        res['available'] = False
        res['warnings'].append('现金流质量: 无可比年份(DATA_INSUFFICIENT)')
        return res
    ratios = ratios.sort_index()  # P0-3: 显式排序，避免隐式行顺序依赖
    recent = ratios.tail(3)
    res['ocf_np_3y'] = round(float(recent.mean()), 3)
    res['ocf_np_years'] = dict(zip(a['report_period'].astype(str).tail(3), ratios.tail(3).round(3)))
    below = int((ratios.tail(3) < ocf_np_floor).sum())
    score = 60.0
    if res['ocf_np_3y'] >= 1.0:
        score = 85
    elif res['ocf_np_3y'] >= 0.8:
        score = 65
    elif res['ocf_np_3y'] >= 0:
        score = 45
    else:
        score = 25
    if below >= 2:
        score -= 15
        res['flags'].append('CASHFLOW_WARNING: 连续2年以上OCF/NP<0.8')
    if (a['net_profit_attr'] > 0).any() and (a['ocf'] < 0).any():
        score -= 20
        res['flags'].append('CASHFLOW_WARNING: 净利>0但OCF<0')
    res['score'] = round(max(0, min(100, score)))
    return res