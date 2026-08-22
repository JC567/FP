# -*- coding: utf-8 -*-
"""数据质量检查（Phase 2）。正式计算前执行；不达标输出 DATA_QUALITY_WARNING 并拒出结论。"""
from __future__ import annotations

from typing import List

import pandas as pd


def check_price(price) -> List[str]:
    w = []
    if price is None or price.empty:
        return ['价格数据缺失(DATA_QUALITY_WARNING)']
    p = price.dropna(subset=['close'])
    if p['close'].le(0).any():
        w.append(f'存在 {int(p["close"].le(0).sum())} 个非正价格(DATA_QUALITY_WARNING)')
    if p['date'].duplicated().any():
        w.append(f'存在 {int(p["date"].duplicated().sum())} 个重复日期(DATA_QUALITY_WARNING)')
    if len(p) >= 2:
        d = pd.to_datetime(p['date']).sort_values().diff().dt.days
        gaps = (d > 10).sum()
        if gaps:
            w.append(f'存在 {int(gaps)} 处 >10日 断档(DATA_QUALITY_WARNING)')
    return w


def check_pe(pe) -> List[str]:
    """PE 为 PIT 自算(来自 EPS)时的参考检查：仅软提示，不再作为阻断项。
    P0-1：PE=Price/EPS_PIT，数据可得性由财报(fin)决定，外部历史 PE 不再必需。"""
    if pe is None or pe.empty:
        return ['外部历史PE未取到(PIT自算PE不受影响，见说明)']
    p = pe.dropna(subset=['pe_ttm'])
    neg = (p['pe_ttm'] <= 0).sum()
    if neg:
        w = [f'负/零PE样本 {int(neg)} 个（不参与分位，见说明）']
        return w
    return []


def check_financials(fin) -> List[str]:
    w = []
    if fin is None or fin.empty:
        return ['财报数据缺失(DATA_QUALITY_WARNING)']
    if fin['announcement_date'].isna().any():
        w.append('存在缺失公告日的财报(DATA_QUALITY_WARNING)')
    if not fin['eps_basic'].notna().any():
        w.append('财报缺少每股收益(EPS)，无法计算PIT PE(DATA_QUALITY_WARNING)')
    return w


def check_dividends(div) -> List[str]:
    w = []
    if div is None or div.empty:
        return ['分红数据缺失(DATA_QUALITY_WARNING)']
    if div['implement_date'].isna().any():
        w.append('存在缺失实施日的分红(DATA_QUALITY_WARNING)')
    return w


def run_all(price, pe, fin, div) -> List[str]:
    w = []
    w += check_price(price)
    w += check_pe(pe)
    w += check_financials(fin)
    w += check_dividends(div)
    return w


def hard_block(warnings: List[str]) -> bool:
    """是否存在阻断结论的严重质量问题（缺价格/缺财报/缺分红）。
    P0-1：PE 现由财报EPS自算，故不再把"外部PE缺失"作为阻断项。"""
    blocking = ('价格数据缺失', '财报数据缺失', '分红数据缺失',
                '价格数据缺失(DATA_QUALITY_WARNING)', '财报数据缺失(DATA_QUALITY_WARNING)',
                '分红数据缺失(DATA_QUALITY_WARNING)')
    return any(w.startswith(blocking) for w in warnings)