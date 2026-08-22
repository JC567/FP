# -*- coding: utf-8 -*-
"""行业风险评分(0-100)。基于行业类型+配置的主观打分，明示主观成分；数据驱动项(行业指数走势)可选。
不伪造——若无数据项则用配置默认并标注 subjective。"""
from __future__ import annotations

from valresearch.config import get_config


def industry_score(industry_type='制造业', industry='', cfg=None) -> dict:
    cfg = cfg or get_config('balanced')
    # 行业风险基准分（越低越安全）。银行为 60(受政策/息差影响)，消费制造 45。
    base = {
        '银行': 55, '保险': 55, '证券': 60, '地产': 80, '制造业': 50,
        '食品饮料': 40, '医药': 42, '公用事业': 35, '能源': 60,
    }.get(industry_type, 50)
    # 配置可覆盖（主观项）
    overrides = cfg.get('industry_risk', {}).get(industry_type)
    score = overrides if overrides is not None else base
    res = {
        'score': round(max(0, min(100, score))),
        'industry': industry,
        'industry_type': industry_type,
        'subjective': True,          # 主观配置项，明示
        'note': '行业风险评分为配置/启发式，未使用未来数据；数据驱动项(行业指数/毛利趋势)待扩充',
    }
    return res