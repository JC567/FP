# -*- coding: utf-8 -*-
"""基本面分析：盈利稳定性 / 现金流质量 / 分红持续性 / 负债水平 / 行业风险 / 质量评分。
各模块均基于时点数据(公告日<=t)，数据缺失返回 DATA_INSUFFICIENT 并给中间分，不伪造。
"""
from __future__ import annotations

from valresearch.fundamental.earnings import earnings_stability
from valresearch.fundamental.cashflow import cashflow_quality
from valresearch.fundamental.dividend_sust import dividend_sustainability
from valresearch.fundamental.leverage import leverage_score
from valresearch.fundamental.industry import industry_score
from valresearch.fundamental.quality_score import quality_score

__all__ = ['earnings_stability', 'cashflow_quality', 'dividend_sustainability',
           'leverage_score', 'industry_score', 'quality_score']