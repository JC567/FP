# -*- coding: utf-8 -*-
"""分红持续性评分(0-100)。连续分红年数、DPS CAGR、平均分红率、payout>100% 警示。

分红率口径（与 P0-D 严格 payout 同源）：
    ratio_Y = 现金分红总额_Y / 归母净利润_Y
    现金分红总额_Y = Σ DPS(报告期属Y, implement_date<=t) × sizing_shares
    sizing_shares = implied_shares_Y = NP_Y / EPS_Y（同一张年报内自洽的隐含股本）

股本跳变修正：THS 等供应商的历史 EPS 是按后续送转/转增**追溯稀释**的，
而历史每股分红按当时(未除权)股本支付。若直接 DPS/EPS 跨股本事件相除会产生
假阳性(如 600887 2014: 0.80/0.68=117.6%，真实约56%)。因此当相邻两年隐含股本
变动超过 20% 时，FY-Y 分红按事件前股本 min(implied_Y, implied_{Y-1}) 折算总额。
股本稳定年份该公式与 DPS/EPS 代数等价，行为不变。
"""
from __future__ import annotations

import pandas as pd

_SHARE_JUMP_TOL = 0.20   # 隐含股本相邻年变动超过 20% 视为送转/转增/回购事件


def dividend_sustainability(div, fin, t, payout_unsustainable=1.0) -> dict:
    res = {'score': 50, 'consecutive_years': 0, 'dps_cagr_5y': None, 'dps_cagr_10y': None,
           'avg_payout_5y': None, 'avg_payout_10y': None, 'unsustainable': False,
           'payout_method': 'STRICT_TOTAL_SHARE_ADJUSTED', 'share_jump_years': [],
           'flags': [], 'warnings': [], 'available': True}
    if div is None or div.empty:
        res['available'] = False
        res['warnings'].append('分红持续性: 无分红数据(DATA_INSUFFICIENT)')
        return res
    d = div.copy()
    d['imp_ts'] = pd.to_datetime(d['implement_date'])
    d['per_share'] = pd.to_numeric(d['per_share_cash'], errors='coerce')
    known = d[d['imp_ts'] <= pd.to_datetime(t)].copy()
    if known.empty:
        res['available'] = False
        res['warnings'].append('分红持续性: 截至该日无已实施分红(DATA_INSUFFICIENT)')
        return res
    # 按会计年度汇总年度每股分红(含中期)
    known['year'] = known['report_period'].astype(str).str.extract(r'(\d{4})')[0]
    annual = known.groupby('year')['per_share'].sum().sort_index()
    res['consecutive_years'] = _consecutive_series(annual)
    score = 50.0 + min(30, res['consecutive_years'] * 3)
    if res['consecutive_years'] >= 5:
        score += 10
    # DPS CAGR (用年度序列)
    vals = annual.values.astype(float)
    if len(vals) >= 6 and vals[0] > 0:
        res['dps_cagr_5y'] = round((vals[-1] / vals[0]) ** (1.0 / (len(vals) - 1)) - 1, 4)
    if len(vals) >= 11 and vals[0] > 0:
        res['dps_cagr_10y'] = round((vals[-1] / vals[0]) ** (1.0 / (len(vals) - 1)) - 1, 4)
    # 分红率: 总额口径 = 分红总额 / 归母净利（含股本跳变修正）
    annual_map = _annual_fin_map(fin, t)
    ratios = {}
    n_skipped = 0
    for y, dps in annual.items():
        m = annual_map.get(y)
        if m is None or not m.get('np') or not m.get('eps') or m['np'] <= 0 or m['eps'] <= 0:
            n_skipped += 1
            continue
        shares = m['np'] / m['eps']
        prev = annual_map.get(str(int(y) - 1))
        if prev and prev.get('np') and prev.get('eps') and prev['np'] > 0 and prev['eps'] > 0:
            shares_prev = prev['np'] / prev['eps']
            if abs(shares / shares_prev - 1.0) > _SHARE_JUMP_TOL:
                shares = min(shares, shares_prev)   # 送转/转增前股本
                res['share_jump_years'].append(str(y))
        ratios[y] = dps * shares / m['np']
    if ratios:
        rs = pd.Series(ratios).sort_index()
        res['avg_payout_5y'] = round(float(rs.tail(5).mean()), 3)
        res['avg_payout_10y'] = round(float(rs.mean()), 3)
        res['unsustainable'] = bool((rs > payout_unsustainable).any())
        if res['unsustainable']:
            score -= 20
            res['flags'].append('DIVIDEND_UNSUSTAINABLE: 年度分红率>100%')
    elif n_skipped:
        res['warnings'].append(
            f'分红持续性: {n_skipped} 个年度缺年报净利/EPS，分红率不可算(DATA_INSUFFICIENT)')
    res['score'] = round(max(0, min(100, score)))
    return res


def _annual_fin_map(fin, t):
    """各会计年度年报首公告版本(≤t)的 {year: {'np','eps'}}。

    取最早公告版本而非最新修订：历史分红的支付股本与当年首次披露口径同源；
    归母净利润绝对额不随送转/转增变化，仅会计重述才会改变。
    """
    out = {}
    if fin is None or fin.empty:
        return out
    f = fin.copy()
    f['per_ts'] = pd.to_datetime(f['report_period'])
    f['ann_ts'] = pd.to_datetime(f['announcement_date'])
    f = f[(f['ann_ts'] <= pd.to_datetime(t)) & (f['per_ts'].dt.month == 12)].copy()
    if f.empty:
        return out
    f['year'] = f['per_ts'].dt.year.astype(str)
    f['np'] = pd.to_numeric(f.get('net_profit_attr'), errors='coerce')
    f['eps'] = pd.to_numeric(f.get('eps_basic'), errors='coerce')
    f = f.sort_values('ann_ts')
    for y, g in f.groupby('year'):
        row = g.iloc[0]   # 首次披露版本
        if pd.notna(row['np']) or pd.notna(row['eps']):
            out[y] = {'np': float(row['np']) if pd.notna(row['np']) else None,
                      'eps': float(row['eps']) if pd.notna(row['eps']) else None}
    return out


def _consecutive_series(annual_series):
    """截至最新一年的连续分红年数（要求近N年每年都有分红，可含中期）。"""
    if annual_series.empty:
        return 0
    yrs = sorted(annual_series.index, key=int)
    # 从最新往前数连续
    n = 0
    expected = int(yrs[-1])
    s = set(yrs)
    while str(expected) in s or f'{expected}' in s:
        n += 1
        expected -= 1
    return n