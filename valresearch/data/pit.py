# -*- coding: utf-8 -*-
"""Point-in-Time 机制（Phase 2 核心）。

核心原则：asof(t) 只使用 公告/实施日 <= t 的数据，严禁未来函数。
- 财务：announcement_date <= t 才可用；EPS_TTM 用"最新已公告报告期 + 上年同期 + 上年年报"滚动外推。
- 分红：implement_date(实施方案公告日) <= t 的近12个月现金分红 = DPS_TTM。
- PE：取 t 当时已公布的 PE_TTM（百度源为 as-reported，打 PIT 近似标记）。
- 分红率 payout = DPS_TTM / EPS_TTM（每股口径，等价 现金分红总额/归母净利润，无需股本）。
"""
from __future__ import annotations

import datetime
from typing import Optional

import numpy as np
import pandas as pd

from valresearch.models import PitSnapshot
from valresearch.data.payout import (PAYOUT_SOURCE_STRICT, PAYOUT_SOURCE_PER_SHARE,
                                     payout_ratio_strict, crosscheck_payout)
from valresearch.data.pit_pe import compute_pe_ttm_pit, PE_SOURCE_PIT

_TTM_DAYS = 365


def _as_ts(x):
    return pd.to_datetime(x)


def _asof(df, date_col, t, cols):
    """返回 df 中 date_col<=t 的最后一行（cols 子集），无则 None。"""
    if df is None or df.empty:
        return None
    sub = df[_as_ts(df[date_col]) <= _as_ts(t)]
    if sub.empty:
        return None
    row = sub.iloc[-1]
    return {c: row[c] for c in cols}


def eps_ttm_asof(fin, t):
    """EPS_TTM(时点)：以 t 前已公告的最新报告期为锚点滚动外推。"""
    if fin is None or fin.empty:
        return None, 'EPS_TTM: 无财报数据(DATA_INSUFFICIENT)'
    f = fin.copy()
    f['ann_ts'] = _as_ts(f['announcement_date'])
    f['per_ts'] = _as_ts(f['report_period'])
    avail = f[f['ann_ts'] <= _as_ts(t)].sort_values('per_ts')
    if avail.empty:
        return None, 'EPS_TTM: 截至该日无已公告财报(DATA_INSUFFICIENT)'
    anchor = avail.iloc[-1]
    eps = anchor['eps_basic']
    month = anchor['per_ts'].month
    year = anchor['per_ts'].year
    # 找到上年年报 与 上年同期
    def get_period(y, m, d):
        per = pd.Timestamp(year=y, month=m, day=d)
        rows = avail[avail['per_ts'] == per]
        return rows.iloc[0]['eps_basic'] if not rows.empty else None
    if month == 12:                       # 年报：直接为TTM
        return (float(eps), None) if pd.notna(eps) else (None, 'EPS_TTM: 年报EPS缺失')
    prev_annual = get_period(year - 1, 12, 31)
    prev_same = get_period(year - 1, month, {3: 31, 6: 30, 9: 30}[month])
    if prev_annual is None or prev_same is None or pd.isna(eps):
        return None, 'EPS_TTM: 缺少上年同期/年报外推项(DATA_INSUFFICIENT)'
    ttm = float(eps) + float(prev_annual) - float(prev_same)
    return ttm, None


def dps_ttm_asof(div, t):
    """DPS_TTM(时点)：implement_date<=t 的近12个月每股现金分红合计。"""
    if div is None or div.empty:
        return None, 'DPS_TTM: 无分红数据(DATA_INSUFFICIENT)'
    d = div.copy()
    d['imp_ts'] = _as_ts(d['implement_date'])
    d['per_share'] = pd.to_numeric(d['per_share_cash'], errors='coerce')
    t_ts = _as_ts(t)
    window = d[(d['imp_ts'] <= t_ts) & (d['imp_ts'] >= t_ts - pd.Timedelta(days=_TTM_DAYS))]
    if window.empty:
        # P0-4: 该公司存在分红记录但近12个月未实施 → DPS_TTM=0（真实0%，非数据缺失）
        return 0.0, None
    return float(window['per_share'].sum()), None


def price_asof(price, t):
    if price is None or price.empty:
        return None
    p = price.copy()
    p['d_ts'] = _as_ts(p['date'])
    sub = p[p['d_ts'] <= _as_ts(t)]
    if sub.empty:
        return None
    return float(sub.iloc[-1]['close'])


def pe_asof(pe, t):
    if pe is None or pe.empty:
        return None, None
    p = pe.copy()
    p['d_ts'] = _as_ts(p['date'])
    sub = p[p['d_ts'] <= _as_ts(t)]
    if sub.empty:
        return None, None
    row = sub.iloc[-1]
    return row['pe_ttm'], row.get('pe_valid', True)


# ---------- P0-2 财务多版本(修订)机制 ----------

def _fin_indexed(fin):
    f = fin.copy()
    f['ann_ts'] = pd.to_datetime(f['announcement_date'])
    f['rp'] = f['report_period'].astype(str)
    return f


def _revision_number(fin, report_period, ann_ts):
    """某 report_period 下，ann_ts 这个公告对应的版本号(1,2,3...，按公告日升序)。"""
    f = _fin_indexed(fin)
    f = f[f['rp'] == str(report_period)].sort_values('ann_ts')
    if f.empty:
        return None
    mask = f['ann_ts'] <= pd.Timestamp(ann_ts)
    return int(mask.sum())


def select_financial_version(fin, report_period, asof_date):
    """同一 symbol+report_period 可存在多个版本。返回 asof 当时已公开的最新版本行(dict)。

    - 只考虑 announcement_date <= asof_date 的版本；
    - 多个版本时选 announcement_date 最大者（即当时已公开的最新修订）；
    - asof 前无任何版本公开 → 返回 None。
    """
    if fin is None or fin.empty:
        return None
    f = _fin_indexed(fin)
    f = f[f['rp'] == str(report_period)]
    if f.empty:
        return None
    a = _as_ts(asof_date)
    avail = f[f['ann_ts'] <= a]
    if avail.empty:
        return None
    row = avail.loc[avail['ann_ts'].idxmax()].to_dict()
    return row


def get_financial_pit(fin, report_period, asof_date) -> Optional[dict]:
    """P0-2 核心：返回 (symbol=fin, report_period, asof_date) 时点已公开的最新财务版本。

    只返回 announcement_date <= asof_date 的数据；多版本返回当时最新版。
    未来版本 / 未来公告 一律不可见。
    """
    row = select_financial_version(fin, report_period, asof_date)
    if row is None:
        return None
    rev = _revision_number(fin, report_period, row['ann_ts'])
    out = {k: row.get(k) for k in ('report_period', 'announcement_date', 'revenue',
                                   'net_profit_attr', 'eps_basic', 'ocf',
                                   'total_assets', 'total_liabilities',
                                   'int_bearing_debt', 'announcement_date_source')}
    out['asof_date'] = str(_as_ts(asof_date).date())
    out['revision_version'] = rev
    out['source'] = row.get('data_source', '')
    return out


# ---------- P0-A/P0-B: 年度财报 PIT 视图（公告日<=t + 修订感知） ----------

def annual_versions_pit(fin, t=None) -> Optional[pd.DataFrame]:
    """年度(12-31)财报 PIT 视图：只保留 announcement_date<=t 的行，且每个 report_period
    只取当时已公开的最新版本（修订感知）。t=None 表示不设公告截止（全部可见，仍做修订去重）。
    """
    if fin is None or fin.empty:
        return None
    f = fin.copy()
    f['ann_ts'] = pd.to_datetime(f['announcement_date'])
    f['per_ts'] = pd.to_datetime(f['report_period'])
    if t is not None:
        f = f[f['ann_ts'] <= _as_ts(t)]
    if f.empty:
        return None
    ann = f[f['per_ts'].dt.month == 12]
    if ann.empty:
        return None
    ann = ann.sort_values(['ann_ts', 'per_ts'])
    # P0-2 修订感知：同一报告期保留公告日最大的版本（禁止 groupby().last() 跨列拼接）
    ann = ann.loc[ann.groupby('report_period')['ann_ts'].idxmax()]
    return ann.sort_values('per_ts').reset_index(drop=True)


def net_profit_ttm_asof(fin, t):
    """归母净利润 TTM(时点)：口径同 eps_ttm_asof，但作用于 net_profit_attr。
    返回 (np_ttm, reason)。"""
    if fin is None or fin.empty:
        return None, 'NET_PROFIT_TTM: 无财报数据(DATA_INSUFFICIENT)'
    if 'net_profit_attr' not in fin.columns:
        return None, 'NET_PROFIT_TTM: 缺归母净利润字段(DATA_INSUFFICIENT)'
    f = fin.copy()
    f['ann_ts'] = _as_ts(f['announcement_date'])
    f['per_ts'] = _as_ts(f['report_period'])
    avail = f[f['ann_ts'] <= _as_ts(t)].sort_values('per_ts')
    if avail.empty:
        return None, 'NET_PROFIT_TTM: 截至该日无已公告财报(DATA_INSUFFICIENT)'
    # P0-2 修订感知：同一报告期取当时最新版本（禁止 groupby().last() 跨列拼接）
    avail = avail.loc[avail.groupby('report_period')['ann_ts'].idxmax()]
    avail = avail.sort_values('per_ts')
    anchor = avail.iloc[-1]
    np_ = anchor['net_profit_attr']
    month = anchor['per_ts'].month
    year = anchor['per_ts'].year

    def get_period(y, m, d):
        per = pd.Timestamp(year=y, month=m, day=d)
        rows = avail[avail['per_ts'] == per]
        return rows.iloc[0]['net_profit_attr'] if not rows.empty else None

    if month == 12:
        return (float(np_), None) if pd.notna(np_) else (None, 'NET_PROFIT_TTM: 年报净利缺失')
    prev_annual = get_period(year - 1, 12, 31)
    prev_same = get_period(year - 1, month, {3: 31, 6: 30, 9: 30}[month])
    if prev_annual is None or prev_same is None or pd.isna(np_):
        return None, 'NET_PROFIT_TTM: 缺少上年同期/年报外推项(DATA_INSUFFICIENT)'
    ttm = float(np_) + float(prev_annual) - float(prev_same)
    return ttm, None


class PitLayer:
    """持有单个标的的全部 PIT 数据集，提供 asof(t) 时点快照。"""

    def __init__(self, symbol, price=None, pe=None, fin=None, div=None,
                 warnings=None):
        self.symbol = symbol
        self.price = price
        self.pe = pe
        self.fin = fin
        self.div = div
        self.warnings = warnings if warnings is not None else []

    def asof(self, t) -> PitSnapshot:
        t_ts = _as_ts(t)
        snap = PitSnapshot(date=t_ts)
        snap.price = price_asof(self.price, t_ts)
        eps, we = eps_ttm_asof(self.fin, t_ts)
        snap.eps_ttm = eps
        if we:
            self.warnings.append(we)
        # P0-1: PE 严格自算（不再使用外部历史 PE）
        pe_val, pe_valid, _pe_reason, pe_src = compute_pe_ttm_pit(snap.price, snap.eps_ttm)
        snap.pe_ttm = pe_val
        snap.pe_valid = pe_valid
        snap.pe_source = pe_src
        dps, wd = dps_ttm_asof(self.div, t_ts)
        snap.dps_ttm = dps
        if wd:
            self.warnings.append(wd)
        if snap.price and snap.dps_ttm is not None:
            snap.dividend_yield = snap.dps_ttm / snap.price * 100.0
        # P0-D: 正式 payout = 现金分红总额TTM / 归母净利TTM（每股仅作交叉验证）
        np_ttm, wnp = net_profit_ttm_asof(self.fin, t_ts)
        snap.net_profit_ttm = np_ttm
        if wnp:
            self.warnings.append(wnp)
        # 股本 = 归母净利TTM / EPS_TTM（两口径一致时每股/总额数学等价；此处仍以总额口径为正式）
        shares = None
        if np_ttm is not None and snap.eps_ttm is not None and np_ttm > 0 and snap.eps_ttm > 0:
            shares = np_ttm / snap.eps_ttm
        if snap.dps_ttm is not None and shares is not None:
            snap.cash_dividend_total_ttm = snap.dps_ttm * shares
        strict_v, strict_reason = payout_ratio_strict(snap.cash_dividend_total_ttm, np_ttm)
        per_v = None
        if snap.dps_ttm is not None and snap.eps_ttm and snap.eps_ttm > 0:
            per_v = snap.dps_ttm / snap.eps_ttm * 100.0
        snap.payout_ratio = strict_v
        snap.payout_ratio_source = PAYOUT_SOURCE_STRICT
        _ok, _status, _per, _strict, _msg = crosscheck_payout(per_v, strict_v)
        snap.payout_crosscheck = {'ok': _ok, 'status': _status, 'per_share': _per,
                                  'strict_total': _strict, 'message': _msg}
        if _status == 'PAYOUT_CROSSCHECK_MISMATCH':
            self.warnings.append(_msg)
        if strict_reason and not pd.isna(strict_v):
            self.warnings.append(strict_reason)
        # P0-7: 可追溯性字段（锚点报告期、公告日、修订版本号）
        if self.fin is not None and not self.fin.empty:
            f_idx = _fin_indexed(self.fin)
            f_idx['per_ts'] = pd.to_datetime(f_idx['report_period'])
            avail_f = f_idx[f_idx['ann_ts'] <= t_ts].sort_values('per_ts')
            if not avail_f.empty:
                _anchor = avail_f.iloc[-1]
                snap.report_period = str(_anchor['report_period'])
                snap.announcement_date = str(_anchor['announcement_date'])
                snap.revision_version = _revision_number(
                    self.fin, _anchor['report_period'], _anchor['announcement_date'])
        return snap

    def price_series(self):
        return self.price


def build_pit_warnings(layer, t):
    """汇总截至 t 的数据可得性警告（缺失字段→DATA_INSUFFICIENT，不伪造）。"""
    w = []
    if layer.price is None or layer.price.empty:
        w.append('价格数据缺失(DATA_INSUFFICIENT)')
    if layer.fin is None or layer.fin.empty:
        w.append('财报数据缺失：无法计算EPS_TTM/分红率(DATA_INSUFFICIENT)')
    if layer.div is None or layer.div.empty:
        w.append('分红数据缺失：无法计算股息率(DATA_INSUFFICIENT)')
    if layer.pe is None or layer.pe.empty:
        w.append('PE历史缺失：无法计算PE分位(DATA_INSUFFICIENT)')
    return w