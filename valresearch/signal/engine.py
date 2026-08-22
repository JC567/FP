# -*- coding: utf-8 -*-
"""信号引擎：三指标 + 综合评分 + 价值陷阱仲裁。

三轨输出：Rule Signal / Score Signal / Value Trap Signal，最终信号为仲裁结果。
分数不能取代规则；陷阱分高时禁止 STRONG BUY。
"""
from __future__ import annotations

from valresearch.config import get_config


def rule_signal(a: bool, b: bool, c: bool) -> str:
    if a and b and c:
        return 'STRONG_UNDERVALUE'
    if a and b and not c:
        return 'POLICY_DRIVEN_HIGH_DIVIDEND'
    if not a and b and c:
        return 'HIGH_YIELD_NOT_CHEAP_ENOUGH'
    return 'NEUTRAL'


def score_components(metrics, cfg=None) -> dict:
    """各维度 0-100(越高越好)，供加权合成。metrics 需含 pe_pct, dy_pct, pr_pct, spread, spread_threshold,
    pe_fair_ratio, quality_score, industry_score。"""
    cfg = cfg or get_config('balanced')
    pe = metrics.get('pe_pct')
    dy = metrics.get('dy_pct')
    pr = metrics.get('pr_pct')
    comp = {}
    comp['pe'] = round(100 - min(100, pe), 1) if pe is not None else None
    comp['dy'] = round(dy, 1) if dy is not None else None
    comp['payout'] = round(100 - min(100, pr), 1) if pr is not None else None
    spread = metrics.get('spread')
    thr = metrics.get('spread_threshold', 0.02)
    if spread is None:
        comp['spread'] = None
    else:
        # 阈值处=50(中性)，2×阈值=100：线性、不封顶，能区分不同利差
        comp['spread'] = round(max(0, min(100, 50 * (spread / thr))), 1)
    ratio = metrics.get('pe_fair_ratio')
    gstatus = metrics.get('gordon_status')
    if ratio is None:
        comp['gordon'] = None
        comp['gordon_status'] = gstatus or 'INSUFFICIENT'   # 数据不足
    else:
        if gstatus is not None and gstatus not in ('VALID', 'THIN_SPREAD'):
            comp['gordon'] = None
            comp['gordon_status'] = gstatus                  # INVALID: GGM失效
        else:
            # 合理价(ratio=1)=50(中性)，对称线性：折价加分、溢价减分，无封顶饱和
            comp['gordon'] = round(max(0, min(100, 100 - 50 * ratio)), 1)
            comp['gordon_status'] = gstatus or 'VALID'
    comp['quality'] = metrics.get('quality_score')
    comp['industry'] = round(max(0, min(100, 100 - metrics.get('industry_score', 50))), 1)
    return comp


def composite_score(metrics, comp, cfg=None) -> float:
    cfg = cfg or get_config('balanced')
    w = cfg.get('score', {})
    neutral = w.get('neutral_default', 50.0)   # 缺失维度给中性分，分母恒为全部权重
    items = [('pe', w.get('w_pe', 0.2)), ('dy', w.get('w_dy', 0.2)),
             ('payout', w.get('w_payout', 0.1)), ('spread', w.get('w_spread', 0.1)),
             ('gordon', w.get('w_gordon', 0.15)), ('quality', w.get('w_quality', 0.2)),
             ('industry', w.get('w_industry', 0.05))]
    total_w = sum(wgt for _, wgt in items)
    s = 0.0
    for key, wgt in items:
        v = comp.get(key)
        if v is None:
            if key == 'gordon':
                v = 0.0    # P0-7: Gordon 无结论(失效/数据不足) 计 0，绝不伪装成中性50
            else:
                v = neutral
        s += wgt * v
    if total_w == 0:
        return 0.0
    return round(s / total_w, 1)   # 全权重加权；Gordon 无结论计0


def score_signal(score: float) -> str:
    if score >= 90:
        return 'STRONG_BUY'
    if score >= 80:
        return 'BUY'
    if score >= 65:
        return 'ACCUMULATE'
    if score >= 50:
        return 'HOLD'
    if score >= 35:
        return 'WAIT'
    if score >= 20:
        return 'REDUCE'
    return 'SELL'


def final_signal(rule, score_sig, value_trap, cfg=None) -> tuple:
    """三轨仲裁 → (final_signal, note)。"""
    cfg = cfg or get_config('balanced')
    block = value_trap.get('block_strong_buy', False)
    level = value_trap.get('level', 'LOW')
    order = ['SELL', 'REDUCE', 'WAIT', 'HOLD', 'ACCUMULATE', 'BUY', 'STRONG_BUY']
    note = []
    final = score_sig
    # 规则信号强化买入
    if rule == 'STRONG_UNDERVALUE':
        if order.index('BUY') > order.index(final):
            final = 'BUY'
            note.append('规则信号(强烈低估)上调至BUY')
    elif rule == 'POLICY_DRIVEN_HIGH_DIVIDEND':
        note.append('高股息可能由分红政策推动，谨慎')
        if final in ('BUY', 'STRONG_BUY'):
            final = 'ACCUMULATE'
            note.append('下调至ACCUMULATE')
    elif rule == 'HIGH_YIELD_NOT_CHEAP_ENOUGH':
        if final in ('BUY', 'STRONG_BUY'):
            final = 'ACCUMULATE'
            note.append('高股息但估值不够便宜，下调')
    # 价值陷阱限制
    if block:
        if level == 'VERY_HIGH':
            final = 'WAIT'
            note.append('价值陷阱极高，强制WAIT')
        elif final in ('BUY', 'STRONG_BUY'):
            final = 'ACCUMULATE'
            note.append('价值陷阱高，禁止STRONG_BUY，下调至ACCUMULATE')
    return final, '；'.join(note)


def _hyst_less(value, thr, hyst, prev):
    """'越小越好'条件(<阈值)：带滞回，避免边界噪声引起信号来回翻转。"""
    if value is None:
        return False
    if prev is True:
        return value < thr + hyst   # 已在位，需明显超过阈值才退出
    return value < thr              # 未在位，需明显低于阈值才进入


def _hyst_greater(value, thr, hyst, prev):
    """'越大越好'条件(>阈值)：带滞回。"""
    if value is None:
        return False
    if prev is True:
        return value > thr - hyst   # 已在位，需明显跌破阈值才退出
    return value > thr              # 未在位，需明显高于阈值才进入


def hysteresis_bands(pe_thr, dy_thr, pr_thr, hyst):
    """P1-4: 显式给出每个条件的进入/退出阈值(可表述、无矛盾)。

    - 条件A(PE<，越小越好): 进入=pe_thr, 退出=pe_thr+hyst（越过上界才退出）
    - 条件B(DY>，越大越好): 进入=dy_thr, 退出=dy_thr-hyst（跌破下界才退出）
    - 条件C(PR<，越小越好): 进入=pr_thr, 退出=pr_thr+hyst
    hysteresis 带宽(单位=百分位点)。退出阈值永远在"更不满足"一侧，杜绝来回翻转矛盾。
    """
    return {
        'hysteresis': hyst,
        'pe_entry': round(pe_thr, 2), 'pe_exit': round(pe_thr + hyst, 2),
        'dy_entry': round(dy_thr, 2), 'dy_exit': round(dy_thr - hyst, 2),
        'pr_entry': round(pr_thr, 2), 'pr_exit': round(pr_thr + hyst, 2),
    }


def compute_signal(metrics, quality, value_trap, cfg=None, prev=None) -> dict:
    cfg = cfg or get_config('balanced')
    sp = cfg.get('signals', {})
    mode = cfg.get('mode', 'balanced')
    pe_thr = sp.get('pe_percentile', 30)
    dy_thr = sp.get('dividend_percentile', 70)
    pr_thr = sp.get('payout_percentile', 70)
    hyst = sp.get('hysteresis', 5.0)   # 滞回带宽(%分位)，prev 为 None(单次分析)时严格阈值
    prev = prev or {}
    a = _hyst_less(metrics.get('pe_pct'), pe_thr, hyst, prev.get('a'))
    b = _hyst_greater(metrics.get('dy_pct'), dy_thr, hyst, prev.get('b'))
    c = _hyst_less(metrics.get('pr_pct'), pr_thr, hyst, prev.get('c'))
    rule = rule_signal(a, b, c)
    comp = score_components(metrics, cfg)
    missing = [k for k, v in comp.items() if v is None and k != 'gordon']
    base_score = composite_score(metrics, comp, cfg)
    penalty = value_trap.get('penalty', 0.0)
    # P0-7: Gordon 无结论(失效/数据不足) → 降置信度，绝不伪装成50
    gordon_status = comp.get('gordon_status')
    if gordon_status == 'INVALID':
        gordon_pen = 0.05
    elif gordon_status == 'THIN_SPREAD':
        gordon_pen = 0.03   # Ke-g 过小，PE 可用但置信度稍低
    elif gordon_status is not None and gordon_status != 'VALID':
        gordon_pen = 0.05
    else:
        gordon_pen = 0.0
    final_score = round(base_score * (1 - (penalty + gordon_pen)), 1)
    score_sig = score_signal(final_score)
    final, note = final_signal(rule, score_sig, value_trap, cfg)
    if gordon_pen > 0:
        if gordon_status == 'THIN_SPREAD':
            gnote = f'Gordon置信度偏低(Ke-g过小,THIN_SPREAD)，降置信度3%'
        else:
            gnote = f'Gordon无结论({gordon_status})，计0分(非中性50)并降置信度5%'
        note = (note + '；' + gnote) if note else gnote
    if missing:
        miss_note = '缺失维度按中性分(50)计: ' + ','.join(missing)
        note = (note + '；' + miss_note) if note else miss_note
    return {
        'metrics': metrics,   # P1-7 供解释链引用
        'condition_a': a, 'condition_b': b, 'condition_c': c,
        'rule_signal': rule, 'score': final_score, 'base_score': base_score,
        'gordon_status': gordon_status, 'gordon_penalty': gordon_pen,
        'score_signal': score_sig, 'value_trap_level': value_trap.get('level', 'LOW'),
        'final_signal': final, 'note': note, 'mode': mode,
        'thresholds': {'pe': pe_thr, 'dy': dy_thr, 'payout': pr_thr},
        'hysteresis_bands': hysteresis_bands(pe_thr, dy_thr, pr_thr, hyst),  # P1-4
        'components': comp,
    }