# -*- coding: utf-8 -*-
"""分红率严格口径与交叉验证（P0-5）。

严格口径：
    分红率(payout) = 现金分红总额 / 归母净利润 × 100

每股口径 DPS/EPS 在"股本口径一致"前提下数学等价于总额/归母净利。为防止
派息比例、每股现金、每股收益口径漂移造成静默误差，必须做交叉验证：
- 若每股口径(DPS/EPS) 与 总额口径(现金分红总额/归母净利) 均可算且偏差超过容忍度，
  记 PAYOUT_CROSSCHECK_MISMATCH 警告，绝不静默用错口径。

缺失/异常：
- net_profit<=0 或 dividend_total<0 → payout=NaN（不能算，也不伪装为0）
- dividend_total=0 且 net_profit>0 → payout=0（无分红是真实0）
"""
from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
import pandas as pd

PAYOUT_SOURCE_STRICT = 'STRICT_TOTAL'    # 现金分红总额/归母净利润
PAYOUT_SOURCE_PER_SHARE = 'PER_SHARE'    # DPS_TTM/EPS_TTM（股本口径一致时等价）


def payout_ratio_strict(dividend_total, net_profit_attr):
    """严格口径：payout = 现金分红总额/归母净利润 ×100。

    Returns (payout, invalid_reason)：
    - net_profit 缺失/<=0 或 dividend_total 缺失/<0 → (NaN, reason)
    - dividend_total=0 且 net_profit>0 → (0.0, None)
    - 正常 → (总额/归母×100, None)
    """
    if dividend_total is None or pd.isna(dividend_total) or dividend_total < 0:
        return np.nan, 'CASH_DIVIDEND_INSUFFICIENT'
    if net_profit_attr is None or pd.isna(net_profit_attr) or net_profit_attr <= 0:
        return np.nan, 'NET_PROFIT_NON_POSITIVE'
    if dividend_total == 0:
        return 0.0, None
    return float(dividend_total / net_profit_attr * 100.0), None


def crosscheck_payout(per_share_ratio, strict_ratio, relative_tol=0.20, abs_tol=10.0):
    """交叉验证每股口径 vs 总额口径。

    - 两者任一不可算(NaN) → 返回 (True, 'INSUFFICIENT', ...) 不视为不一致。
    - 相对偏差 > relative_tol 或绝对偏差 > abs_tol(百分点) → (False, 'PAYOUT_CROSSCHECK_MISMATCH')
    - 否则 → (True, 'PAYOUT_CROSSCHECK_OK')

    Returns (ok, status, per_share_ratio, strict_ratio, message)
    """
    if pd.isna(per_share_ratio) or pd.isna(strict_ratio):
        return True, 'PAYOUT_CROSSCHECK_INSUFFICIENT', per_share_ratio, strict_ratio, '任一口径缺失，未交叉验证'
    rel = abs(per_share_ratio - strict_ratio) / max(abs(strict_ratio), 1e-9)
    abs_diff = abs(per_share_ratio - strict_ratio)
    if rel > relative_tol and abs_diff > abs_tol:
        msg = (f'每股口径{per_share_ratio:.1f}% 与总额口径{strict_ratio:.1f}% 偏差过大，'
               f'疑口径漂移(PAYOUT_CROSSCHECK_MISMATCH)')
        return False, 'PAYOUT_CROSSCHECK_MISMATCH', per_share_ratio, strict_ratio, msg
    msg = f'每股口径{per_share_ratio:.1f}% 与总额口径{strict_ratio:.1f}% 一致'
    return True, 'PAYOUT_CROSSCHECK_OK', per_share_ratio, strict_ratio, msg