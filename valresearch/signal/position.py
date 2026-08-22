# -*- coding: utf-8 -*-
"""仓位管理。按最终信号给初始/建议/最大仓位，并按价值陷阱与行业集中度修正。"""
from __future__ import annotations

from valresearch.config import get_config


def position_plan(final_signal, value_trap, cfg=None) -> dict:
    cfg = cfg or get_config('balanced')
    table = cfg.get('position', {}).get('table', {})
    init, target, mx = table.get(final_signal, [0.0, 0.0, 0.0])
    rationale = f'信号={final_signal} 的基础仓位'
    # 价值陷阱修正：陷阱分高时降低建议仓位
    vt = value_trap.get('score', 0)
    if vt >= 60:
        target = min(target, 0.03)
        rationale += '；价值陷阱高，仓位压降'
    if vt >= 80:
        target = 0.0
        rationale += '；价值陷阱极高，不建仓'
    return {
        'signal': final_signal,
        'init_weight': round(init, 4),
        'target_weight': round(target, 4),
        'max_weight': round(mx, 4),
        'value_trap_score': vt,
        'rationale': rationale,
    }