# -*- coding: utf-8 -*-
"""巴菲特模式 · 单股评估（仅银行业，能力圈限定）。

核心前提：巴菲特的前提是"能力圈"——先有行业，才有具体的分析模型与策略；不存在一个策略横跨多个行业。
因此本模块只实现"银行业"的巴菲特式评估，输入其它行业直接返回"暂未支持该行业"。

银行业专用评估模型（与通用质量+Gordon 估值彻底分离）：
  · 质量(护城河/稳健)——银行业口径：
      - ROE ≥ 12%（盈利能力与护城河代理；巴菲特偏好耐久高 ROE 银行）
      - 权益比率(资本充足代理) ≥ 6%（不脆弱）
      - 分红连续 ≥ 5 年（股东友好、盈利稳定）
      - 盈利未显著恶化（连续下滑年数少、净利最大回撤不过度）
      - 非价值陷阱（陷阱分 ≤ 50 且非 HIGH）
  · 便宜(安全边际)——银行业估值核心看 PB（市净率），而非 PE：
      - 有 PB 时：PB ≤ 1.0（破净）= 明确便宜（价格不高于账面值，留安全边际）
      - 无 PB 时：退回 PE分位≤30% 或 股息率分位≥70%（历史估值分位口径）
  · 不满足任一质量门槛 → 不适合（只说明原因，不给出买入建议）。
Gordon/PE合理性 等通用口径不再作为银行业便宜判定（银行高杠杆下 PE 易失真）。
"""
from __future__ import annotations

from typing import Optional

# 仅覆盖银行业（能力圈）。新增行业需另起一套行业专用模型。
SUPPORTED_INDUSTRIES = ('银行',)

# 银行业质量门槛
_BANK_ROE_MIN = 10.0        # 银行 ROE(%) 下限（简单口径=归母净利/归母权益；优质银行≥10% 即扎实）
_BANK_EQUITY_MIN = 0.06     # 权益比率(权益/总资产)下限，资本充足代理
_BANK_DIV_CONSEC_MIN = 5    # 连续分红年数下限
_BANK_VT_MAX = 50.0         # 价值陷阱分上限（<=50 视为非陷阱）
_BANK_MAX_DECLINES = 2      # 盈利连续下滑年数上限
_BANK_MIN_DD = -40.0        # 净利最大回撤下限(%)（不低于 -40%）

# 银行业便宜判定
_BANK_PB_CHEAP = 1.0        # PB ≤ 1.0（破净）视为便宜
_BANK_PB_FAIR = 1.5         # PB 合理中枢（仅用于提示安全边际，非精确内在价值）
_BUFFETT_PE_PCT_MAX = 30.0  # 无 PB 时：PE 分位 ≤ 30% 视为低估
_BUFFETT_DY_PCT_MIN = 70.0  # 无 PB 时：股息率分位 ≥ 70% 视为高股息


def _g(d, *keys, default=None):
    for k in keys:
        if isinstance(d, dict) and k in d and d[k] is not None:
            return d[k]
    return default


def buffett_assess(rep) -> dict:
    """返回 dict：supported / suitable / reasons / fails / method / margin_of_safety 等。"""
    industry_type = getattr(rep, 'industry_type', '') or ''
    if industry_type not in SUPPORTED_INDUSTRIES:
        return {
            'supported': False,
            'industry_type': industry_type,
            'suitable': None,
            'reasons': [],
            'fails': [f'暂未支持该行业（行业={industry_type or "未知"}）；巴菲特模式当前仅覆盖银行业（能力圈限定，不做跨行业通用策略）'],
            'method': None,
            'margin_of_safety': None,
        }

    fun = rep.fundamental or {}
    detail = fun.get('detail', {}) or {}
    bank = detail.get('banking', {}) or {}
    earn = detail.get('earnings', {}) or {}
    divd = detail.get('dividend', {}) or {}
    vt = rep.value_trap or {}
    val = rep.valuation or {}

    roe = _g(bank, 'roe')
    eqr = _g(bank, 'equity_ratio')
    div_consec = _g(divd, 'consecutive_years')
    np_dd = _g(earn, 'np_max_drawdown')
    declines = _g(earn, 'consecutive_declines')
    vt_score = _g(vt, 'score')
    vt_level = _g(vt, 'level')
    pb = _g(val, 'pb')
    pe_pct = _g(val, 'pe_pct_10y')
    dy_pct = _g(val, 'dividend_yield_pct')
    price = _g(val, 'price')
    dy = _g(val, 'dividend_yield')

    reasons, fails = [], []

    # —— 质量门槛（银行业口径）——
    if roe is None:
        fails.append('ROE 数据不足(DATA_INSUFFICIENT)：无法判定银行业盈利能力')
    elif roe * 100.0 >= _BANK_ROE_MIN:
        reasons.append(f'ROE={roe*100:.1f}% ≥ {_BANK_ROE_MIN:.0f}%：盈利能力扎实(护城河代理)')
    else:
        fails.append(f'ROE={roe*100:.1f}% < {_BANK_ROE_MIN:.0f}%：盈利能力不足，非优质银行')

    if eqr is None:
        fails.append('权益比率 数据不足(DATA_INSUFFICIENT)：无法判定资本充足')
    elif eqr >= _BANK_EQUITY_MIN:
        reasons.append(f'权益比率={eqr*100:.1f}% ≥ {_BANK_EQUITY_MIN*100:.0f}%：资本充足、不脆弱')
    else:
        fails.append(f'权益比率={eqr*100:.1f}% < {_BANK_EQUITY_MIN*100:.0f}%：资本偏薄，抗风险弱')

    if div_consec is None:
        fails.append('连续分红年数 数据不足(DATA_INSUFFICIENT)')
    elif div_consec >= _BANK_DIV_CONSEC_MIN:
        reasons.append(f'连续分红 {div_consec} 年 ≥ {_BANK_DIV_CONSEC_MIN} 年：股东友好、盈利稳定')
    else:
        fails.append(f'连续分红仅 {div_consec} 年 < {_BANK_DIV_CONSEC_MIN} 年：分红稳定性不足')

    if declines is not None and declines > _BANK_MAX_DECLINES:
        fails.append(f'盈利连续下滑 {declines} 年 > {_BANK_MAX_DECLINES} 年：盈利稳定性差')
    if np_dd is not None and np_dd < _BANK_MIN_DD:
        fails.append(f'净利最大回撤 {np_dd:.0f}% < {_BANK_MIN_DD:.0f}%：盈利波动过大')

    if vt_score is None:
        fails.append('价值陷阱评分 数据不足(DATA_INSUFFICIENT)')
    elif vt_score <= _BANK_VT_MAX and vt_level != 'HIGH':
        reasons.append(f'价值陷阱分 {vt_score:.0f} ≤ {_BANK_VT_MAX:.0f} 且非 HIGH：非价值陷阱')
    else:
        fails.append(f'价值陷阱分 {vt_score:.0f} > {_BANK_VT_MAX:.0f} 或等级 HIGH：疑似价值陷阱')

    # —— 便宜判定（银行业看 PB，无 PB 退回历史分位）——
    if pb is not None and pb > 0:
        cheap = pb <= _BANK_PB_CHEAP
        method = 'PB(破净)'
        if cheap:
            reasons.append(f'PB={pb:.2f} ≤ {_BANK_PB_CHEAP:.1f}（破净）：价格不高于账面值，留安全边际')
        else:
            fails.append(f'PB={pb:.2f} > {_BANK_PB_CHEAP:.1f}：未破净，银行业视角下便宜度不足')
        margin_of_safety = max(0.0, (_BANK_PB_FAIR - pb) / _BANK_PB_FAIR) if pb < _BANK_PB_FAIR else None
    else:
        cheap = ((pe_pct is not None and pe_pct <= _BUFFETT_PE_PCT_MAX) or
                 (dy_pct is not None and dy_pct >= _BUFFETT_DY_PCT_MIN))
        method = '历史估值分位(PE/股息率)'
        if cheap:
            bits = []
            if pe_pct is not None and pe_pct <= _BUFFETT_PE_PCT_MAX:
                bits.append(f'PE分位={pe_pct:.0f}%≤{_BUFFETT_PE_PCT_MAX:.0f}%')
            if dy_pct is not None and dy_pct >= _BUFFETT_DY_PCT_MIN:
                bits.append(f'股息率分位={dy_pct:.0f}%≥{_BUFFETT_DY_PCT_MIN:.0f}%')
            reasons.append('PB 不可得，退回历史估值分位判定便宜：' + ' 且 '.join(bits))
        else:
            bits = []
            if pe_pct is not None:
                bits.append(f'PE分位={pe_pct:.0f}%')
            if dy_pct is not None:
                bits.append(f'股息率分位={dy_pct:.0f}%')
            fails.append('PB 不可得且历史估值分位未达低估（' + '，'.join(bits) + '）：价格不够便宜')
        margin_of_safety = None

    suitable = (len(fails) == 0)
    return {
        'supported': True,
        'industry_type': industry_type,
        'suitable': suitable,
        'reasons': reasons,
        'fails': fails,
        'method': method,
        'margin_of_safety': (round(margin_of_safety, 3) if margin_of_safety is not None else None),
        # 透传关键数据供展示
        'roe': roe, 'equity_ratio': eqr, 'div_consec': div_consec,
        'pb': pb, 'pe_pct': pe_pct, 'dy_pct': dy_pct, 'price': price, 'dividend_yield': dy,
        'vt_score': vt_score, 'vt_level': vt_level,
    }


def format_buffett_report(rep) -> str:
    a = buffett_assess(rep)
    L = []
    L.append('=' * 64)
    L.append('巴菲特模式 · 单股评估（能力圈限定）')
    L.append('=' * 64)
    ind = getattr(rep, 'industry_type', '') or '未知'
    name = getattr(rep, 'name', '') or getattr(rep, 'symbol', '')
    L.append(f'标的: {getattr(rep, "symbol", "")}({name})  行业: {ind}  '
             f'分析日: {getattr(rep, "analysis_date", "")}')
    L.append('-' * 64)

    if not a['supported']:
        L.append('')
        L.append('【暂未支持该行业】')
        L.append('  ' + a['fails'][0])
        L.append('  说明：巴菲特模式以"行业(能力圈)"为前提，不做跨行业通用策略；')
        L.append('        当前仅实现银行业评估模型，输入其它行业直接不支持。')
        L.append('-' * 64)
        L.append('风险提示：本报告仅供研究参考，不构成投资建议。')
        return '\n'.join(L)

    L.append('【适用性判定：银行业专用 = 优质(护城河/稳健) + 便宜(留安全边际) + 非陷阱】')
    if a['reasons']:
        for r in a['reasons']:
            L.append('  ✔ ' + r)
    if a['fails']:
        for f in a['fails']:
            L.append('  ✘ ' + f)
    L.append('-' * 64)

    if a['suitable']:
        L.append(f'结论：✔ 适合巴菲特模式（满足"优质+便宜+安全边际+非陷阱"）')
        L.append(f'  便宜判定方法：{a["method"]}'
                 + (f'；安全边际≈{a["margin_of_safety"]*100:.0f}%' if a['margin_of_safety'] is not None else ''))
        L.append('')
        L.append('【建议】')
        L.append('  · 建仓：分批买入（如每月定额），切勿一次追高；低估区间持续累积。')
        L.append('  · 持有：长期持有(forever)，不轻易卖出；以"好生意+好价格"为前提陪伴企业成长。')
        L.append('  · 注：本结论由"银行业专用模型"得出（ROE/资本充足/分红连续性/PB破净），非通用质量分。')
        L.append('  · 仅在"质量恶化(ROE下滑/资本转薄)/落入价值陷阱"时重新评估，不因短期波动卖出。')
    else:
        L.append('结论：✘ 不适合巴菲特模式（未满足银行业质量/便宜门槛）')
        L.append('  · 仅说明原因，不给出买入建议；可等待基本面改善或价格进入便宜区后再评估。')
    L.append('-' * 64)

    L.append('【关键数据】')
    roe = a['roe']; eqr = a['equity_ratio']; pb = a['pb']
    L.append(f"  价格={a['price']}  PE_TTM={_g(rep.valuation,'pe_ttm')}  PB={pb}  "
             f"股息率={a['dividend_yield']}%")
    L.append(f"  ROE={ (roe*100) if roe is not None else None }%  权益比率={ (eqr*100) if eqr is not None else None }%  "
             f"连续分红={a['div_consec']}年")
    L.append(f"  PE分位={a['pe_pct']}  股息率分位={a['dy_pct']}  价值陷阱分={a['vt_score']}({a['vt_level']})")
    L.append('-' * 64)
    L.append('风险提示：便宜≠一定上涨；高股息≠一定安全；历史低估≠未来不跌。')
    L.append('本报告仅供研究参考，不构成投资建议。')
    return '\n'.join(L)
