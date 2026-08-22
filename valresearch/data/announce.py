# -*- coding: utf-8 -*-
"""公告日期来源模型（P0-3）。

同一财报报告期，其"公告日"可能来自不同可信度来源。为不夸大 PIT 精度，显式打标：
- REAL      : 交易所/信披平台披露的真实公告日（如东财业绩快报公告日）。
- FALLBACK  : 来自财报正文/二手数据源的可信披露日期。
- ESTIMATED : 法规截止日近似（一季报/年报4-30，半年报8-31，三季报10-31）。

解析优先级：REAL > FALLBACK > ESTIMATED。使用 ESTIMATED 时必须在报告中声明
DATA_CALIBER_RISK，不得假装为精确公告日。
"""
from __future__ import annotations

from typing import Any, Optional, Tuple

import pandas as pd

REAL = 'REAL'
FALLBACK = 'FALLBACK'
ESTIMATED = 'ESTIMATED'
_UNKNOWN = 'UNKNOWN'


def resolve_announcement_source(
    real_date: Any = None,
    fallback_date: Any = None,
    est_date: Any = None,
) -> Tuple[str, Any]:
    """按可信度优先级解析 (source, used_date)。

    Returns:
        (REAL, real_date)    若 real_date 有效
        (FALLBACK, fallback_date) 若 fallback_date 有效
        (ESTIMATED, est_date) 否则（est_date 可为 None）
    """
    if real_date is not None and not pd.isna(real_date):
        return REAL, real_date
    if fallback_date is not None and not pd.isna(fallback_date):
        return FALLBACK, fallback_date
    return ESTIMATED, est_date


def annotate_announcement_source(
    fin: pd.DataFrame,
    real_col: Optional[str] = None,
    fallback_col: Optional[str] = None,
    est_col: str = 'announcement_date',
) -> pd.DataFrame:
    """给财务 DataFrame 逐行补充 announcement_date_source 列。

    - 若 real_col 存在且该行有值 → REAL（并以此值覆盖公告日）
    - 否则若 fallback_col 存在且有值 → FALLBACK
    - 否则 → ESTIMATED
    不修改其它列；无则新增列。
    """
    f = fin.copy()
    if 'announcement_date_source' not in f.columns:
        f['announcement_date_source'] = None
    for i, r in f.iterrows():
        real = None if real_col is None or real_col not in r else r[real_col]
        fb = None if fallback_col is None or fallback_col not in r else r[fallback_col]
        est = r.get(est_col)
        src, used = resolve_announcement_source(real, fb, est)
        f.at[i, 'announcement_date_source'] = src
        if src in (REAL, FALLBACK) and used is not None:
            f.at[i, est_col] = used
    return f