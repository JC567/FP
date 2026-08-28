"""巴菲特模式 · 单股评估。

把"单股分析"的结果，用巴菲特式标准重判：
  适合买点 = 质量分高(护城河扎实, ≥60) 且 价格便宜(留安全边际) 且 非价值陷阱(陷阱分≤50)。
  其中"便宜"的判定必须**可靠**：
    · 若 Gordon 合理PE 可信(状态=VALID) 且 价≤合理价×0.8 → 用 Gordon 安全边际；
    · 否则（A股高股息股普遍为 THIN_SPREAD：股息利差过薄，Gordon分母极小、合理PE失真）
      退回**历史估值分位**判定便宜（PE分位≤30% 或 股息率分位≥70%，即均衡型买点口径）。
  适合时给"分批建仓、长期持有(forever)"建议；不适合时只说明原因、不给买入建议。
  关键：Gordon 不可信时绝不拿它充当"安全边际"，也不展示其失真的合理价。
"""
from valresearch.i18n import cn

_BUFFETT_QUALITY_MIN = 60.0
_BUFFETT_FAIR_RATIO_MAX = 0.8
_BUFFETT_VTSCORE_MAX = 50.0
_BUFFETT_PE_PCT_MAX = 30.0     # 历史 PE 分位 ≤ 30% 视为"低估"（均衡型买点口径）
_BUFFETT_DY_PCT_MIN = 70.0     # 历史股息率分位 ≥ 70% 视为"高股息"


def _pct(x):
    return '--' if x is None else '%.0f' % x


def buffett_assess(rep) -> dict:
    quality = rep.fundamental.get('quality_score')
    fair_ratio = rep.signal.get('pe_fair_ratio')
    gordon_status = rep.signal.get('gordon_status')
    vt_score = rep.value_trap.get('score')
    v = rep.valuation
    pe_pct = v.get('pe_pct_10y')
    dy_pct = v.get('dividend_yield_pct')

    reasons = []
    fails = []
    margin = None
    method = None

    # 1) 质量分（护城河）
    if quality is None or quality < _BUFFETT_QUALITY_MIN:
        fails.append('质量分 %s < %.0f：护城河不够扎实，不符合"优质"前提'
                     % ('--' if quality is None else round(quality, 1), _BUFFETT_QUALITY_MIN))
    else:
        reasons.append('质量分 %.1f ≥ %.0f：护城河扎实' % (quality, _BUFFETT_QUALITY_MIN))

    # 2) 便宜（鲁棒）：Gordon 可信则用它；否则退回历史估值分位
    gordon_credible = (gordon_status == 'VALID') and (fair_ratio is not None)
    gordon_cheap = gordon_credible and (fair_ratio <= _BUFFETT_FAIR_RATIO_MAX)
    pct_cheap = ((pe_pct is not None and pe_pct <= _BUFFETT_PE_PCT_MAX) or
                (dy_pct is not None and dy_pct >= _BUFFETT_DY_PCT_MIN))
    if gordon_cheap:
        cheap = True
        method = 'Gordon合理PE(价≤合理价×0.8)'
        margin = max(0.0, 1.0 - fair_ratio)
        reasons.append('Gordon: 当前价/合理PE=%.2f≤0.80，价低于合理价约 %.1f%%，安全边际充足'
                       % (fair_ratio, margin * 100))
    elif pct_cheap:
        cheap = True
        method = '历史估值分位(PE分位≤%d%% 或 股息率分位≥%d%%)' % (_BUFFETT_PE_PCT_MAX, _BUFFETT_DY_PCT_MIN)
        reasons.append('历史估值分位便宜：PE分位=%s%% 股息率分位=%s%%（Gordon不可信[%s]，改用分位判定）'
                       % (_pct(pe_pct), _pct(dy_pct), gordon_status or '无'))
    else:
        cheap = False
        fails.append('价格不够便宜：Gordon不可信(状态=%s) 且 历史估值分位未达低估'
                     '（PE分位=%s%% 股息率分位=%s%%）'
                     % (gordon_status or '无', _pct(pe_pct), _pct(dy_pct)))
    # 记录 Gordon 是否可信（供报告展示，不影响上面的便宜判定）
    gordon_reliable = gordon_credible

    # 3) 价值陷阱
    if vt_score is None or vt_score > _BUFFETT_VTSCORE_MAX:
        fails.append('价值陷阱分 %s > %.0f：存在价值陷阱风险'
                     % ('--' if vt_score is None else round(vt_score, 1), _BUFFETT_VTSCORE_MAX))
    else:
        reasons.append('价值陷阱分 %.1f ≤ %.0f：非陷阱' % (vt_score, _BUFFETT_VTSCORE_MAX))

    suitable = (len(fails) == 0) and (quality is not None) and (vt_score is not None) and cheap
    return {
        'suitable': bool(suitable),
        'reasons': reasons,
        'fails': fails,
        'method': method,
        'margin_of_safety': (round(margin, 4) if margin is not None else None),
        'quality_score': quality,
        'pe_fair_ratio': fair_ratio,
        'gordon_status': gordon_status,
        'gordon_reliable': bool(gordon_reliable),
        'vt_score': vt_score,
    }


def _num(x, nd=2):
    return '--' if x is None else f'{x:.{nd}f}'


def format_buffett_report(rep) -> str:
    a = buffett_assess(rep)
    v = rep.valuation
    d = rep.to_dict()
    L = []
    A = L.append
    A('=' * 64)
    A('巴菲特模式 · 单股评估')
    A('=' * 64)
    A('标的: %s(%s)  分析日 %s  Gordon状态=%s'
      % (d.get('name'), d.get('symbol'), d.get('analysis_date'), a['gordon_status']))
    A('-' * 64)
    A('【适用性判定：优质 + 便宜(留安全边际) + 非陷阱】')
    for r in a['reasons']:
        A('  ✓ %s' % r)
    for f in a['fails']:
        A('  ✗ %s' % f)
    A('-' * 64)
    if a['suitable']:
        A('结论：✔ 适合巴菲特模式（满足"优质+便宜+安全边际+非陷阱"）')
        A('  便宜判定方法：%s' % a['method'])
        A('')
        A('【建议】')
        A('  · 建仓：分批买入（如每月定额），切勿一次追高；低估区间持续累积。')
        A('  · 持有：长期持有(forever)，不轻易卖出；以"好生意+好价格"为前提陪伴企业成长。')
        if a['margin_of_safety'] is not None:
            A('  · Gordon 安全边际：当前价较合理价低约 %.1f%%，下行有缓冲。' % (a['margin_of_safety'] * 100))
        else:
            A('  · 注：本次"便宜"由历史估值分位判定（Gordon不可信），非精确内在价值安全边际；')
            A('    仍建议分批建仓以平滑买入成本。')
        fair = d.get('signal', {}).get('gordon_scenario', {}).get('fair_price_base')
        if a['gordon_reliable'] and fair is not None:
            A('  · Gordon 合理价基准 ≈ %.2f；当前价 %s。' % (fair, v.get('price')))
        else:
            A('  · Gordon 合理价不可信（%s），未采用；当前价 %s。' % (a['gordon_status'], v.get('price')))
        A('  · 切勿因短期波动卖出；仅在"质量恶化/落入价值陷阱"时重新评估。')
    else:
        A('结论：✘ 不适合巴菲特模式（无法给出买入建议）')
        A('')
        A('【说明】')
        A('  当前不满足"优质 + 便宜(留安全边际) + 非陷阱"的巴菲特式买点，')
        A('  故不给出建仓建议，建议观望并等待：价格进入低估区间、')
        A('  且质量分回升、价值陷阱解除后，再重新评估。')
    A('-' * 64)
    A('【关键数据】')
    A('  价格=%s  PE_TTM=%s  股息率=%s%%  质量分=%s  陷阱分=%s  '
      '价/合理PE=%s  Gordon状态=%s'
      % (_num(v.get('price')), _num(v.get('pe_ttm')), _num(v.get('dividend_yield')),
         a['quality_score'], a['vt_score'],
         ('--' if a['pe_fair_ratio'] is None else '%.2f' % a['pe_fair_ratio']),
         a['gordon_status']))
    A('  PE分位=%s%%  股息率分位=%s%%  当前估值区: %s'
      % (_pct(v.get('pe_pct_10y')), _pct(v.get('dividend_yield_pct')),
         d.get('price', {}).get('current_zone', '--')))
    A('=' * 64)
    A('风险提示：便宜≠一定上涨；高股息≠一定安全；历史低估≠未来不跌。')
    A('本报告仅供研究参考，不构成投资建议。')
    return '\n'.join(L)
