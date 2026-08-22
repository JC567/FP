# -*- coding: utf-8 -*-
"""金融行业(银行/保险/券商)专用基本面质量(0-100)（P1-2）。

通用模型的杠杆/现金流分项对金融机构不适用：
- 银行天然高杠杆：通用 leverage_score 会误伤，故不计入；
- 银行 OCF 无意义：THS 摘要也无 OCF，通用 cashflow 恒 DATA_INSUFFICIENT，故不计入。

银行模型改用可用字段：
- ROE（归母净利/股东权益）水平与稳定性
- 权益比率(equity/total_assets) 作为资本充足代理（<6% 警示）
- 盈利稳定性（复用通用 earnings）
- 分红持续性（复用通用 dividend_sustainability）
缺失项一律不伪造；ROE/权益比率缺任一 → 该项取 0 并打 DATA_INSUFFICIENT 警告。
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from valresearch.config import get_config
from valresearch.fundamental.earnings import earnings_stability
from valresearch.fundamental.dividend_sust import dividend_sustainability

_BANKING = ('银行', '保险', '证券', '金融')


def is_financial(industry_type: Optional[str]) -> bool:
    return industry_type in _BANKING


def _last_annual(fin, t=None) -> Optional[pd.Series]:
    """最近年报（P0-B：只取 announcement_date<=t 的财报，修订感知每期取当时最新版本）。
    t=None 表示全部可见（仍做修订去重）。"""
    from valresearch.data.pit import annual_versions_pit
    ann = annual_versions_pit(fin, t)
    if ann is None or ann.empty:
        return None
    return ann.iloc[-1]


def roe_latest(fin, t=None) -> Optional[float]:
    row = _last_annual(fin, t)
    if row is None:
        return None
    np_, ta, tl = row.get('net_profit_attr'), row.get('total_assets'), row.get('total_liabilities')
    if np_ is None or ta is None or tl is None or pd.isna(np_) or pd.isna(ta) or pd.isna(tl):
        return None
    eq = float(ta) - float(tl)
    if eq <= 0:
        return None
    return float(np_) / eq


def equity_ratio_latest(fin, t=None) -> Optional[float]:
    row = _last_annual(fin, t)
    if row is None:
        return None
    ta, tl = row.get('total_assets'), row.get('total_liabilities')
    if ta is None or tl is None or pd.isna(ta) or pd.isna(tl) or ta <= 0:
        return None
    return (float(ta) - float(tl)) / float(ta)


def banking_quality(fin, div, t, industry_type='银行', cfg=None) -> dict:
    cfg = cfg or get_config('balanced')
    w = cfg.get('banking', {})
    warnings, flags = [], []
    roe = roe_latest(fin, t)             # P0-B: 时点PIT
    eqr = equity_ratio_latest(fin, t)    # P0-B: 时点PIT
    earn = earnings_stability(fin, t)
    divs = dividend_sustainability(div, fin, t)

    if roe is None:
        warnings.append('银行模型：ROE 数据不足(DATA_INSUFFICIENT)')
    if eqr is None:
        warnings.append('银行模型：权益比率数据不足(DATA_INSUFFICIENT)')
    if eqr is not None and eqr < 0.06:
        flags.append('资本充足率偏低(权益/总资产<6%)')

    def _scale_roe(r):
        if r is None:
            return 0.0
        return round(100.0 * min(1.0, max(0.0, r / 0.15)), 1)   # ROE 15% 即满分

    def _scale_eqr(r):
        if r is None:
            return 0.0
        return round(100.0 * min(1.0, max(0.0, (r - 0.05) / 0.10)), 1)  # 5%→0, 15%→100

    s_roe = _scale_roe(roe)
    s_eqr = _scale_eqr(eqr)
    score = (w.get('w_roe', 0.30) * s_roe
             + w.get('w_equity', 0.25) * s_eqr
             + w.get('w_earnings', 0.20) * earn['score']
             + w.get('w_dividend', 0.25) * divs['score'])
    return {
        'score': round(score, 1),
        'roe': round(roe, 4) if roe is not None else None,
        'equity_ratio': round(eqr, 4) if eqr is not None else None,
        'warnings': warnings,
        'flags': flags,
        'detail': {'earnings': {k: earn[k] for k in ('cagr_revenue', 'cagr_np', 'cagr_eps',
                                                     'np_vol', 'np_max_drawdown', 'consecutive_declines')},
                   'dividend': {k: divs[k] for k in ('consecutive_years', 'dps_cagr_5y', 'dps_cagr_10y',
                                                     'avg_payout_5y', 'avg_payout_10y', 'unsustainable')}},
    }