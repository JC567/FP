"""巴菲特模式 · 单股评估。

把"单股分析"的结果，用巴菲特式标准重判：
  适合买点 = 质量分高(护城河扎实, ≥60) 且 Gordon合理PE留安全边际(价≤合理价×0.8)
            且 非价值陷阱(陷阱分≤50)。
适合时给"分批建仓、长期持有(forever)"建议；不适合时只说明原因、不给买入建议。
阈值与回测中的巴菲特模式(资本预算)保持一致。
"""
from valresearch.i18n import cn

_BUFFETT_QUALITY_MIN = 60.0
_BUFFETT_FAIR_RATIO_MAX = 0.8
_BUFFETT_VTSCORE_MAX = 50.0


def buffett_assess(rep) -> dict:
    """根据 AnalysisReport 判定是否适合巴菲特模式，返回判定明细。"""
    quality = rep.fundamental.get('quality_score')
    fair_ratio = rep.signal.get('pe_fair_ratio')
    gordon_status = rep.signal.get('gordon_status')
    vt_score = rep.value_trap.get('score')

    reasons = []
    fails = []
    margin = None

    # 1) 质量分（护城河）
    if quality is None or quality < _BUFFETT_QUALITY_MIN:
        fails.append('质量分 %s < %.0f：护城河不够扎实，不符合"优质"前提'
                     % ('--' if quality is None else round(quality, 1), _BUFFETT_QUALITY_MIN))
    else:
        reasons.append('质量分 %.1f ≥ %.0f：护城河扎实' % (quality, _BUFFETT_QUALITY_MIN))

    # 2) Gordon 合理PE 安全边际
    if fair_ratio is None or gordon_status in ('INVALID', 'INSUFFICIENT'):
        fails.append('Gordon 合理PE无法计算(%s)：缺乏内在价值锚，无法判断安全边际'
                     % (gordon_status or '无数据'))
    elif fair_ratio > _BUFFETT_FAIR_RATIO_MAX:
        fails.append('当前价/合理PE = %.2f > %.2f：价格未低于合理价×0.8，安全边际不足'
                     % (fair_ratio, _BUFFETT_FAIR_RATIO_MAX))
    else:
        margin = 1.0 - fair_ratio
        reasons.append('当前价/合理PE = %.2f ≤ %.2f：价低于合理价约 %.1f%%，安全边际充足'
                       % (fair_ratio, _BUFFETT_FAIR_RATIO_MAX, margin * 100))

    # 3) 价值陷阱
    if vt_score is None or vt_score > _BUFFETT_VTSCORE_MAX:
        fails.append('价值陷阱分 %s > %.0f：存在价值陷阱风险'
                     % ('--' if vt_score is None else round(vt_score, 1), _BUFFETT_VTSCORE_MAX))
    else:
        reasons.append('价值陷阱分 %.1f ≤ %.0f：非陷阱' % (vt_score, _BUFFETT_VTSCORE_MAX))

    suitable = (len(fails) == 0) and (quality is not None) and (fair_ratio is not None)
    return {
        'suitable': bool(suitable),
        'reasons': reasons,
        'fails': fails,
        'margin_of_safety': (round(margin, 4) if margin is not None else None),
        'quality_score': quality,
        'pe_fair_ratio': fair_ratio,
        'gordon_status': gordon_status,
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
        A('')
        A('【建议】')
        A('  · 建仓：分批买入（如每月定额），切勿一次追高；低估区间持续累积。')
        A('  · 持有：长期持有(forever)，不轻易卖出；以"好生意+好价格"为前提陪伴企业成长。')
        A('  · 安全边际：当前价较合理价低约 %.1f%%，下行有缓冲。' % (a['margin_of_safety'] * 100))
        fair = d.get('signal', {}).get('gordon_scenario', {}).get('fair_price_base')
        if fair is not None:
            A('  · Gordon 合理价基准 ≈ %.2f；当前价 %.2f。' % (fair, v.get('price')))
        A('  · 切勿因短期波动卖出；仅在"质量恶化/落入价值陷阱"时重新评估。')
    else:
        A('结论：✘ 不适合巴菲特模式（无法给出买入建议）')
        A('')
        A('【说明】')
        A('  当前不满足"优质 + 便宜(留安全边际) + 非陷阱"的巴菲特式买点，')
        A('  故不给出建仓建议，建议观望并等待：价格进入合理价×0.8以下、')
        A('  且质量分回升、价值陷阱解除后，再重新评估。')
    A('-' * 64)
    A('【关键数据】')
    A('  价格=%s  PE_TTM=%s  股息率=%s%%  质量分=%s  陷阱分=%s  '
      '价/合理PE=%s'
      % (_num(v.get('price')), _num(v.get('pe_ttm')), _num(v.get('dividend_yield')),
         a['quality_score'], a['vt_score'],
         ('--' if a['pe_fair_ratio'] is None else '%.2f' % a['pe_fair_ratio'])))
    A('  当前估值区: %s' % d.get('price', {}).get('current_zone', '--'))
    A('=' * 64)
    A('风险提示：便宜≠一定上涨；高股息≠一定安全；历史低估≠未来不跌。')
    A('本报告仅供研究参考，不构成投资建议。')
    return '\n'.join(L)
