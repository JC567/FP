# -*- coding: utf-8 -*-
"""缓存覆盖范围校验（P0-11）。

缓存命中必须满足"与当前查询完全匹配"，禁止用不完整/过期数据冒充完整数据：
- 价格缓存：头部须覆盖查询起点，尾部须覆盖查询终点（允许轻微滞后）。
- 财报/分红缓存：最新报告期/实施日不得过旧（否则说明缺了近期公告，需刷新）。
判断全部为纯函数，便于测试；调用方根据结果决定命中缓存或重新抓取。
"""
from __future__ import annotations

from typing import Optional, Tuple

import pandas as pd


def price_cache_covers(min_date, max_date, start, end,
                       recency_days=10, lead_days=5) -> Tuple[bool, str]:
    """价格缓存是否覆盖 [start, end]。

    - EMPTY_CACHE : 无数据
    - HEAD_MISSING: 头部缺 (min_date 晚于 start+lead_days)
    - TAIL_MISSING: 尾部缺 (max_date 早于 end-recency_days)
    - COVERED     : 覆盖
    """
    if min_date is None or max_date is None or pd.isna(min_date) or pd.isna(max_date):
        return False, 'EMPTY_CACHE'
    s, e = pd.to_datetime(start), pd.to_datetime(end)
    mn, mx = pd.to_datetime(min_date), pd.to_datetime(max_date)
    if mn > s + pd.Timedelta(days=lead_days):
        return False, 'HEAD_MISSING'
    if mx < e - pd.Timedelta(days=recency_days):
        return False, 'TAIL_MISSING'
    return True, 'COVERED'


def financial_cache_covers(latest_announcement_date, now=None, max_age_days=400) -> Tuple[bool, str]:
    """财报缓存须包含足够新的公告。

    - EMPTY_CACHE : 无财报
    - STALE       : 最近公告日距今超过 max_age_days（缺近期公告，如 400天≈13个月，
                    正常公司每年至少披露一次年报）
    - COVERED     : 覆盖
    """
    if latest_announcement_date is None or pd.isna(latest_announcement_date):
        return False, 'EMPTY_CACHE'
    now = pd.Timestamp.today() if now is None else pd.to_datetime(now)
    age = (now - pd.to_datetime(latest_announcement_date)).days
    if age > max_age_days:
        return False, 'STALE'
    return True, 'COVERED'


def dividend_cache_covers(latest_implement_date, now=None, max_age_days=550) -> Tuple[bool, str]:
    """分红缓存：最近实施日不能过旧（≥18个月无分红记录视为可能缺数）。
    注：长期不分红的公司会正常触发 STALE，属保守刷新，不伪造。
    """
    if latest_implement_date is None or pd.isna(latest_implement_date):
        return False, 'EMPTY_CACHE'
    now = pd.Timestamp.today() if now is None else pd.to_datetime(now)
    age = (now - pd.to_datetime(latest_implement_date)).days
    if age > max_age_days:
        return False, 'STALE'
    return True, 'COVERED'