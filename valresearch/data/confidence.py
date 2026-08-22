# -*- coding: utf-8 -*-
"""Data Confidence Score（P1-1）。

聚合各数据口径的可信度，输出 0-100 分，用于诚实标注"本次结论建立在多少可信数据上"。
维度缺得越多、公告日越近似、历史越短，置信度越低；绝不因数据不足而虚报高分。

三大成分（权重合计 1.0）：
- dim_coverage : 7 个计算维度(PE/DY/Payout/Spread/Gordon/质量/行业)中实际可算的比例
- ann_caliber  : 财务公告日来源可信度 REAL=1.0 / FALLBACK=0.8 / ESTIMATED=0.6；无财报=0
- history_depth: 已公告历史跨度：min(1, 已公告年数/10)

score = 100 × (0.45×dim_coverage + 0.30×ann_caliber + 0.25×history_depth)
LEVEL: HIGH>=80, MEDIUM>=60, 否则 LOW
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

from valresearch.data.announce import REAL, FALLBACK, ESTIMATED

N_DIMS = 7


def ann_source_score(source: Optional[str]) -> float:
    if source is None:
        return 0.0
    if source == REAL:
        return 1.0
    if source == FALLBACK:
        return 0.8
    if source == ESTIMATED:
        return 0.6
    return 0.0


def _history_depth(n_announced_years: int) -> float:
    if n_announced_years is None or n_announced_years <= 0:
        return 0.0
    return min(1.0, n_announced_years / 10.0)


def data_confidence_score(n_valid_dims: int,
                          ann_source: Optional[str],
                          n_announced_years: int,
                          w_dim=0.45, w_ann=0.30, w_depth=0.25) -> Dict:
    """返回 dict: {score, level, dim_coverage, ann_caliber, history_depth, reasons}。"""
    reasons = []
    dim_cov = max(0.0, min(1.0, n_valid_dims / N_DIMS))
    ann_cal = ann_source_score(ann_source)
    depth = _history_depth(n_announced_years)
    if n_valid_dims < N_DIMS:
        reasons.append(f'仅 {n_valid_dims}/{N_DIMS} 个维度可算')
    if ann_source != REAL:
        reasons.append(f'财务公告日来源={ann_source or "无"}（非真实公告日，有口径风险）')
    if depth < 1.0:
        reasons.append(f'历史跨度 {n_announced_years or 0} 年（不足10年）')
    score = round(100.0 * (w_dim * dim_cov + w_ann * ann_cal + w_depth * depth), 1)
    if score >= 80:
        level = 'HIGH'
    elif score >= 60:
        level = 'MEDIUM'
    else:
        level = 'LOW'
    return {'score': score, 'level': level, 'dim_coverage': round(dim_cov, 3),
            'ann_caliber': round(ann_cal, 3), 'history_depth': round(depth, 3),
            'reasons': reasons}