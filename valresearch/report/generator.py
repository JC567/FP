# -*- coding: utf-8 -*-
"""九段式分析报告文本生成（中文优化版）。"""
from __future__ import annotations

from valresearch.models import AnalysisReport
from valresearch.i18n import cn


def _fmt(v, unit=''):
    if v is None:
        return '--'
    return f'{v}{unit}'


def _pct_rank_desc(pct):
    """分位数通俗描述。"""
    if pct is None:
        return '--'
    if pct <= 10:
        return '极低(历史最低10%区间)'
    if pct <= 20:
        return '很低'
    if pct <= 30:
        return '较低'
    if pct <= 50:
        return '中等偏低'
    if pct <= 70:
        return '中等偏高'
    if pct <= 80:
        return '较高'
    if pct <= 90:
        return '很高'
    return '极高(历史最高10%区间)'


def _signal_cn(sig):
    """信号中文映射。"""
    m = {
        'STRONG_BUY': '强烈买入(三低共振+估值极低)',
        'BUY': '买入(估值偏低)',
        'ACCUMULATE': '逐步建仓(估值合理偏低)',
        'HOLD': '持有(估值合理)',
        'WAIT': '观望(估值偏高)',
        'REDUCE': '减仓(估值偏高)',
        'SELL': '卖出(估值过高)',
    }
    return m.get(sig, sig)


def _rule_cn(rule):
    """规则信号中文映射。"""
    m = {
        'THREE_LOW_RESONANCE': '三低共振(PE低估+高股息+分红率合理)',
        'POLICY_DRIVEN_HIGH_DIVIDEND': '政策驱动高股息(需谨慎)',
        'HIGH_YIELD_NOT_CHEAP_ENOUGH': '高股息但估值不低',
        'DEEP_VALUE': '深度低估',
        'NEUTRAL': '中性',
        'OVERVALUED': '估值偏高',
    }
    return m.get(rule, rule)


def format_report(rep: AnalysisReport) -> str:
    d = rep.to_dict()
    v, q, t, s = d['valuation'], d['fundamental'], d['value_trap'], d['signal']
    L = []
    A = L.append

    A('=' * 64)
    A('红利价值分位研究 · 九段式报告')
    A('=' * 64)
    # 1 摘要
    A(f'【1 摘要】 {d["name"]}({d["symbol"]}) 分析日 {d["analysis_date"]} 模式={cn(d["mode"])}')
    A(f'  最终结论: {_signal_cn(s.get("final_signal"))}')
    A(f'  综合评分: {_fmt(s.get("score"))}分(满分100)')
    A(f'  规则判断: {_rule_cn(s.get("rule_signal"))}')
    if s.get('note'):
        A(f'  说明: {cn(s.get("note"))}')

    # 2 估值快照
    A('【2 当前估值概况】')
    A(f'  股价 {_fmt(v.get("price"))}元 | 每股收益(年化) {_fmt(v.get("eps_ttm"))}元 | 每股分红(年化) {_fmt(v.get("dps_ttm"))}元')
    A(f'  市盈率 {_fmt(v.get("pe_ttm"))}倍 | 股息率 {_fmt(v.get("dividend_yield"), "%")} | 分红率 {_fmt(v.get("payout_ratio"), "%")}')
    A(f'  10年期国债 {_fmt(v.get("rf_10y"), "%")} | 股息超过国债 {_fmt(v.get("dividend_spread"), "%")}'
      f' (超过{_fmt(v.get("spread_threshold"), "%")}为达标)'
      f' -> {"达标 股息收益高于国债" if v.get("spread_signal") else "未达标"}')

    # 3 历史分位
    pe_pct = v.get("pe_pct_10y")
    dy_pct = v.get("dividend_yield_pct")
    pr_pct = v.get("payout_pct")
    A('【3 历史水平对比】(近10年数据)')
    A(f'  市盈率: 当前 {_fmt(v.get("pe_ttm"))}倍, {_pct_rank_desc(pe_pct)}(分位={_fmt(pe_pct, "%")})')
    A(f'    历史范围: 最低{_fmt(v.get("pe_min"))} ~ 中位数{_fmt(v.get("pe_median"))} ~ 最高{_fmt(v.get("pe_max"))}'
      f' (共{v.get("pe_n_valid")}个交易日)')
    A(f'  股息率: 当前 {_fmt(v.get("dividend_yield"), "%")}, {_pct_rank_desc(dy_pct)}(分位={_fmt(dy_pct, "%")})')
    A(f'    历史范围: 最低{_fmt(v.get("dy_min"), "%")} ~ 中位数{_fmt(v.get("dy_median"), "%")} ~ 最高{_fmt(v.get("dy_max"), "%")}')
    A(f'  分红率: 当前 {_fmt(v.get("payout_ratio"), "%")}, {_pct_rank_desc(pr_pct)}(分位={_fmt(pr_pct, "%")})'
      + (' [历史存在异常分红]' if v.get('payout_abnormal') else ''))

    # 4 质量评分
    A(f'【4 公司基本面质量】 综合评分 {_fmt(q.get("quality_score"))}分')
    sub = q.get("sub", {})
    A(f'  五项评估: 盈利能力{_fmt(sub.get("earnings"))}分 | 现金流{_fmt(sub.get("cashflow"))}分 | '
      f'分红持续{_fmt(sub.get("dividend"))}分 | 负债安全{_fmt(sub.get("leverage"))}分 | 行业地位{_fmt(sub.get("industry"))}分')
    for f in q.get('flags', []):
        A(f'  提示: {cn(f)}')

    # 5 价值陷阱
    trap_level_cn = {'HIGH': '高风险', 'MEDIUM': '中等风险', 'LOW': '低风险'}
    A(f'【5 价值陷阱风险】 风险分 {t.get("score")} 等级 {trap_level_cn.get(t.get("level"), t.get("level"))}')
    if t.get('penalty', 0) > 0:
        A(f'  惩罚: 综合分 x {1 - t["penalty"]:.0%} (因发现价值陷阱风险)')
    else:
        A(f'  惩罚: 无 (未发现明显价值陷阱)')
    for f in t.get('flags', []):
        A(f'  - {cn(f)}')
    A('  说明: 基本面质量分与价值陷阱分可能共用部分指标(如盈利/分红)，同一问题可能被两处分别扣分，属保守设计。')

    # 6 信号
    cond_a = s.get("condition_a")
    cond_b = s.get("condition_b")
    cond_c = s.get("condition_c")
    a_txt = '达标' if cond_a else '未达标'
    b_txt = '达标' if cond_b else '未达标'
    c_txt = '达标' if cond_c else '未达标'
    A(f'【6 投资信号分析】')
    A(f'  买入三条件: PE估值偏低={a_txt} | 股息率足够高={b_txt} | 分红率合理={c_txt}')
    A(f'  规则判断: {_rule_cn(s.get("rule_signal"))}')
    A(f'  评分判断: {_signal_cn(s.get("score_signal"))}({s.get("score")}分)')
    A(f'  最终结论: {_signal_cn(s.get("final_signal"))}')

    g = s.get("gordon_g")
    ratio = s.get("pe_fair_ratio")
    band = s.get("pe_fair_band")
    if ratio is not None:
        A(f'  估值参考(Gordon模型): 理论增长g={_fmt(g)} | 当前PE是合理PE的{_fmt(ratio)}倍 ({cn(band)})')
    else:
        A(f'  估值参考(Gordon模型): 理论增长g={_fmt(g)} | 合理PE无法计算(数据不足)')

    sc = s.get('gordon_scenario') or {}
    gordon_note = ''
    if sc.get('invalid'):
        gordon_note = f' [Gordon模型失效: {cn(sc.get("invalid"))}]'
    elif sc.get('thin_spread'):
        gordon_note = ' [Gordon置信度偏低: 增长率与折现率差距过小]'
    A(f'  三种情景: 熊市合理PE {_fmt(sc.get("fair_pe_low"))} | 基准 {_fmt(sc.get("fair_pe_base"))} | 牛市 {_fmt(sc.get("fair_pe_high"))}'
      + gordon_note)

    th = s.get("thresholds", {})
    A(f'  判断标准(模式{cn(rep.mode)}): PE分位<{th.get("pe")}% | 股息率分位>{th.get("dy")}% | 分红率分位<{th.get("payout")}%')

    # 7 价格区间
    p = d['price']
    A('【7 合理价格与买入区间】')
    A(f'  Gordon合理价: 低 {_fmt(p.get("fair_price_low"))} | 基准 {_fmt(p.get("fair_price_base"))} | 高 {_fmt(p.get("fair_price_high"))}')
    A(f'  股息率反推价: 股息率4%对应{_fmt(p.get("price_at_4pct"))}元 | 5%对应{_fmt(p.get("price_at_5pct"))}元 | 6%对应{_fmt(p.get("price_at_6pct"))}元 | 7%对应{_fmt(p.get("price_at_7pct"))}元')
    A(f'  历史分位价(当前EPS x 历史PE): 20%分位{_fmt(p.get("pe_p20_price"))}元 | 30%分位{_fmt(p.get("pe_p30_price"))}元 | 50%分位{_fmt(p.get("pe_p50_price"))}元 | 70%分位{_fmt(p.get("pe_p70_price"))}元')
    deep_lo = _fmt(p.get("deep_buy_low"))
    deep_hi = _fmt(p.get("deep_buy_high"))
    std_lo = _fmt(p.get("standard_buy_low"))
    std_hi = _fmt(p.get("standard_buy_high"))
    A(f'  深度买入区(历史极低估): {deep_lo}~{deep_hi}元')
    A(f'  标准买入区(历史偏低估): {std_lo}~{std_hi}元')
    A(f'  当前所处: {p.get("current_zone")}')

    # 8 仓位
    pos = d['position']
    A('【8 仓位建议】')
    A(f'  建议仓位: {_fmt(pos.get("target_weight"), "%")} (上限{_fmt(pos.get("max_weight"), "%")})')
    A(f'  依据: {cn(pos.get("rationale"))}')

    # 9 局限与可追溯
    A('【9 注意事项与数据来源】')
    for w in d.get('quality_warnings', []):
        A(f'  [数据质量] {cn(w)}')
    for x in d.get('data_limitations', []):
        A(f'  [局限] {cn(x)}')
    for n_item in d.get('notes', []):
        A(f'  [提示] {cn(n_item)}')
    tr = d.get('trace', {})
    for k, info in tr.items():
        A(f'  [{k}] 数据来源={cn(info.get("source"))} 时间范围={info.get("window")} 有效天数={info.get("n_valid")} 剔除={info.get("n_excluded")}')
    A('=' * 64)
    A('本报告由模型自动生成，仅供研究参考，不构成投资建议。')
    return '\n'.join(L)
