# -*- coding: utf-8 -*-
"""基本面质量综合评分(0-100)，按权重合成。数据缺失的子模块用其中间分并计入质量分，附警告。"""
from __future__ import annotations

from valresearch.config import get_config
from valresearch.fundamental.earnings import earnings_stability
from valresearch.fundamental.cashflow import cashflow_quality
from valresearch.fundamental.dividend_sust import dividend_sustainability
from valresearch.fundamental.leverage import leverage_score
from valresearch.fundamental.industry import industry_score
from valresearch.fundamental.banking import is_financial, banking_quality  # P1-2


def quality_score(fin, div, t, industry_type='制造业', industry='', cfg=None, symbol=None) -> dict:
    cfg = cfg or get_config('balanced')
    if is_financial(industry_type):
        # P1-2: 金融行业用专用模型（ROE/权益比率/盈利稳定性/分红持续性）
        bk = banking_quality(fin, div, t, industry_type, cfg, symbol=symbol)
        ind = industry_score(industry_type, industry, cfg)
        score = round(0.85 * bk['score'] + 0.15 * ind['score'], 1)
        return {
            'score': score,
            'sub': {'banking': bk['score'], 'industry': ind['score'],
                    'earnings': bk['detail']['earnings'].get('cagr_np'),
                    'dividend': bk['detail']['dividend'].get('consecutive_years')},
            'detail': {
                'banking': {'roe': bk['roe'], 'equity_ratio': bk['equity_ratio'],
                            **bk['detail']},
                'industry': {'score': ind['score']},
                # 与通用模型保持一致，供 value_trap 读取；金融模型无OCF/负债杠杆口径 → 置空不误报
                'earnings': {k: bk['detail']['earnings'].get(k) for k in
                             ('cagr_revenue', 'cagr_np', 'cagr_eps', 'np_vol',
                              'np_max_drawdown', 'consecutive_declines')},
                'cashflow': {'ocf_np_3y': None, 'ocf_np_years': None},
                'dividend': {k: bk['detail']['dividend'].get(k) for k in
                             ('consecutive_years', 'dps_cagr_5y', 'dps_cagr_10y',
                              'avg_payout_5y', 'avg_payout_10y', 'unsustainable')},
                'leverage': {'asset_liability_ratio': None},
            },
            'flags': bk['flags'],
            'warnings': bk['warnings'],
            'industry_type': industry_type,
        }
    w = cfg.get('fundamental', {})
    earnings = earnings_stability(fin, t)
    cashflow = cashflow_quality(fin, t)
    div_sust = dividend_sustainability(div, fin, t)
    lev = leverage_score(fin, t, industry_type)
    ind = industry_score(industry_type, industry, cfg)

    score = (w.get('w_earnings', 0.25) * earnings['score']
             + w.get('w_cashflow', 0.25) * cashflow['score']
             + w.get('w_dividend', 0.20) * div_sust['score']
             + w.get('w_leverage', 0.15) * lev['score']
             + w.get('w_industry', 0.15) * ind['score'])
    warnings = (earnings.get('warnings', []) + cashflow.get('warnings', [])
                + div_sust.get('warnings', []) + lev.get('warnings', []))
    return {
        'score': round(score, 1),
        'sub': {'earnings': earnings['score'], 'cashflow': cashflow['score'],
                'dividend': div_sust['score'], 'leverage': lev['score'],
                'industry': ind['score']},
        'detail': {
            'earnings': {k: earnings[k] for k in ('cagr_revenue', 'cagr_np', 'cagr_eps',
                                                  'np_vol', 'np_max_drawdown', 'consecutive_declines')},
            'cashflow': {'ocf_np_3y': cashflow.get('ocf_np_3y'), 'ocf_np_years': cashflow.get('ocf_np_years')},
            'dividend': {k: div_sust[k] for k in ('consecutive_years', 'dps_cagr_5y', 'dps_cagr_10y',
                                                  'avg_payout_5y', 'avg_payout_10y', 'unsustainable')},
            'leverage': {'asset_liability_ratio': lev.get('asset_liability_ratio')},
        },
        'flags': (earnings.get('flags', []) + cashflow.get('flags', [])
                  + div_sust.get('flags', []) + lev.get('flags', [])),
        'warnings': warnings,
        'industry_type': industry_type,
    }