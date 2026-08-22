# -*- coding: utf-8 -*-
"""严格 Point-in-Time 的 PE_TTM 计算（P0-1）。

历史 PE 不再依赖外部"后来重算的历史 PE"，而是由当时可获得的数据自算：

    PE_TTM(t) = Price(t) / EPS_TTM_PIT(t)

- Price(t)：t 时点原始收盘价。
- EPS_TTM_PIT(t)：截至 t 已公告财报外推的 TTM 每股收益（严格公告日 PIT）。
- 未来 EPS / 未来公告的财报一律不可见。

异常口径（不得把"负/零盈利"当作低估，也不得伪造）：
- price 缺失            -> PE=NaN, invalid, reason=PRICE_MISSING
- price <= 0            -> PE=NaN, invalid, reason=PRICE_NON_POSITIVE
- eps 缺失(None/NaN)    -> PE=NaN, invalid, reason=EPS_INSUFFICIENT
- eps <= 0              -> PE=NaN, invalid, reason=EPS_NON_POSITIVE
- 其余                  -> PE=price/eps, valid, reason=None

source 恒为 PIT_CALCULATED，区别于旧的外部历史 PE 源(EXTERNAL_HISTORICAL_PE)。
"""
from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
import pandas as pd

PE_SOURCE_PIT = 'PIT_CALCULATED'
PE_SOURCE_EXTERNAL = 'EXTERNAL_HISTORICAL_PE'  # 仅供对比/兼容，不再用于正式估值

# invalid_reason 常量
REASON_OK = None
R_PRICE_MISSING = 'PRICE_MISSING'
R_PRICE_NON_POSITIVE = 'PRICE_NON_POSITIVE'
R_EPS_INSUFFICIENT = 'EPS_INSUFFICIENT'
R_EPS_NON_POSITIVE = 'EPS_NON_POSITIVE'


def compute_pe_ttm_pit(price, eps_ttm, asof_date=None) -> Tuple[float, bool, Optional[str], str]:
    """单点时点 PIT 计算 PE_TTM。

    Args:
        price: t 时点原始收盘价。
        eps_ttm: 截至 t 已公告的 TTM 每股收益（调用方须保证已按公告日 PIT 过滤）。
        asof_date: 时点日期（用于可追溯，不参与计算）。

    Returns:
        (pe_ttm, valid, invalid_reason, source)
    """
    source = PE_SOURCE_PIT
    if price is None or pd.isna(price):
        return np.nan, False, R_PRICE_MISSING, source
    if price <= 0:
        return np.nan, False, R_PRICE_NON_POSITIVE, source
    if eps_ttm is None or pd.isna(eps_ttm):
        return np.nan, False, R_EPS_INSUFFICIENT, source
    if eps_ttm <= 0:
        return np.nan, False, R_EPS_NON_POSITIVE, source
    return float(price / eps_ttm), True, REASON_OK, source