# -*- coding: utf-8 -*-
"""价值陷阱评分(0-100) + 惩罚系数。>block阈值 禁止 STRONG BUY。"""
from __future__ import annotations

from valresearch.config import get_config


def _penalty(score, steps):
    score = max(0, min(100, score))
    pen = 0.0
    for lo, p in sorted(steps):
        if score >= lo:
            pen = p
    return pen


def value_trap_score(quality, industry_type='制造业', cfg=None) -> dict:
    """基于基本面质量子结果汇总价值陷阱分。"""
    cfg = cfg or get_config('balanced')
    vt_cfg = cfg.get('value_trap', {})
    flags = list(quality.get('flags', []))
    score = 0.0
    detail = {}

    # 盈利连续下降 +20
    if quality['detail']['earnings'].get('consecutive_declines', 0) >= 2:
        score += 20
        detail['盈利连续下降'] = 20
        if 'VALUE_TRAP_HINT' not in ''.join(flags):
            flags.append('盈利连续下降(+20)')

    # OCF 恶化 +20
    if quality['detail']['cashflow'].get('ocf_np_3y') is not None and \
            quality['detail']['cashflow']['ocf_np_3y'] < 0.8:
        score += 20
        detail['OCF恶化'] = 20
        flags.append('OCF恶化(+20)')

    # 分红率长期>100% +20
    if quality['detail']['dividend'].get('unsustainable'):
        score += 20
        detail['分红率长期>100%'] = 20
        flags.append('分红率长期>100%(+20)')

    # 负债快速上升/高负债 +15
    alr = quality['detail']['leverage'].get('asset_liability_ratio')
    if alr is not None and alr > 0.75:
        score += 15
        detail['高负债'] = 15
        flags.append('高负债(+15)')

    # 行业衰退(行业风险分高) +15
    ind = quality['sub'].get('industry', 50)
    if ind > 60:
        score += 15
        detail['行业衰退风险'] = 15
        flags.append('行业衰退风险(+15)')

    # 政策重大风险 +10
    if industry_type in ('地产', '能源'):
        score += 10
        detail['政策重大风险'] = 10
        flags.append('政策重大风险(+10)')

    score = round(max(0, min(100, score)))
    level = 'LOW'
    if score > 80:
        level = 'VERY_HIGH'
    elif score > 60:
        level = 'HIGH'
    elif score > 40:
        level = 'MEDIUM'
    elif score > 20:
        level = 'MEDIUM_LOW'
    penalty = round(_penalty(score, vt_cfg.get('penalty_steps', [])), 4)
    return {
        'score': score, 'level': level, 'flags': flags, 'detail': detail,
        'penalty': penalty,
        'block_strong_buy': score > vt_cfg.get('block_strong_buy_above', 60),
    }