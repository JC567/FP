# -*- coding: utf-8 -*-
"""合理价格与买入区间（Phase 9）。

- GGM 情景合理价格反推：fair_price_low/base/high = EPS_TTM × FairPE
- 股息率目标价：Price@4/5/6/7% = DPS_TTM / target
- 历史分位价格映射：Price_Pxx = 当前EPS × 历史PE_Pxx（静态映射，非预测）
- 买入区间：深度/标准/观察/持有/高估
"""
from __future__ import annotations

from typing import Optional


def price_at_dy(dps_ttm, target_dy):
    """由目标股息率反推价格 = DPS / target_dy。target_dy 为小数(如0.04)。"""
    if dps_ttm is None or not dps_ttm > 0 or target_dy <= 0:
        return None
    return round(float(dps_ttm) / float(target_dy), 2)


def hist_price_map(eps_ttm, pe_stats):
    """历史分位价格静态映射：Price_Pxx = EPS × PE_Pxx。"""
    out = {}
    if eps_ttm is None or pe_stats is None:
        return out
    for key in ('p20', 'p30', 'p50', 'p70', 'p10', 'p90'):
        v = getattr(pe_stats, key, None)
        if v is not None:
            out[f'pe_{key}_price'] = round(float(eps_ttm) * float(v), 2)
    return out


def current_zone(current_pe, pe_stats, dy_pct, dy_p80=None):
    """当前所处区间。"""
    if pe_stats is None:
        return 'NA'
    p20, p30, p50, p70 = pe_stats.p20, pe_stats.p30, pe_stats.p50, pe_stats.p70
    if current_pe is None:
        return 'NA'
    # 高估区
    if (p70 is not None and current_pe > p70) or (dy_pct is not None and dy_pct < 30):
        return '高估区'
    if p50 is not None and current_pe > p50:
        return '持有区'
    if p30 is not None and current_pe > p30:
        return '观察区'
    return '标准/深度买入区'


def buy_range(eps_ttm, pe_stats, dps_ttm, fair_price_base, quality_ok=True):
    """综合价格区间。返回 dict。"""
    out = {}
    if pe_stats is not None:
        p20, p30 = pe_stats.p20, pe_stats.p30
        if p20 is not None and eps_ttm is not None:
            out['deep_buy_low'] = round(float(eps_ttm) * float(p20) * 0.9, 2)
            out['deep_buy_high'] = round(float(eps_ttm) * float(p20), 2)
        if p30 is not None and eps_ttm is not None:
            out['standard_buy_low'] = round(float(eps_ttm) * float(p30) * 0.9, 2)
            out['standard_buy_high'] = round(float(eps_ttm) * float(p30), 2)
    if fair_price_base is not None:
        out['fair_price_base'] = fair_price_base
    for tag, tgt in (('price_at_4pct', 0.04), ('price_at_5pct', 0.05),
                     ('price_at_6pct', 0.06), ('price_at_7pct', 0.07)):
        out[tag] = price_at_dy(dps_ttm, tgt)
    return out


# ---------- P1-3 价格区间统一与风险调整 ----------

def price_methods(eps_ttm, pe_stats, dps_ttm, fair_price_base) -> dict:
    """收集各估值法给出的合理价格（同一标尺，单位=元）。返回 {method: price, available:[...]}。"""
    m = {}
    if fair_price_base is not None and fair_price_base > 0:
        m['ggm'] = round(float(fair_price_base), 2)
    if pe_stats is not None and eps_ttm is not None and pe_stats.p50 is not None:
        m['pe_p50'] = round(float(eps_ttm) * float(pe_stats.p50), 2)   # 历史中位PE
    p_dy = price_at_dy(dps_ttm, 0.05)
    if p_dy is not None and p_dy > 0:
        m['dividend_5pct'] = p_dy
    return m


def unify_price(method_prices, max_spread_ratio=0.35) -> dict:
    """统一各法合理价格：取中位数。极差过大(>max_spread_ratio)标记 uncertain。
    单一方法失效时用剩余方法；无方法 → fair_price=None。"""
    vals = [v for v in method_prices.values() if v is not None and v > 0]
    if not vals:
        return {'fair_price': None, 'n_methods': 0, 'uncertain': False, 'spread_ratio': None}
    sv = sorted(vals)
    med = sv[len(sv) // 2]
    spread = (max(sv) - min(sv)) / med if med else 0.0
    return {'fair_price': round(med, 2), 'n_methods': len(sv),
            'uncertain': spread > max_spread_ratio, 'spread_ratio': round(spread, 3)}


def risk_adjust_price(fair_price, vt_penalty=0.0, gordon_invalid=False):
    """风险调整：价值陷阱/模型失效 → 收窄安全边际(下调合理价)。
    discount = 10% + 10%×陷阱惩罚 + (Gordon失效另加10%)，上限50%。"""
    if fair_price is None:
        return None
    discount = 0.10 + 0.10 * float(vt_penalty) + (0.10 if gordon_invalid else 0.0)
    return round(float(fair_price) * (1.0 - min(0.5, discount)), 2)