# -*- coding: utf-8 -*-
"""Gordon 增长模型（Phase 5）。

FairPE = Payout Ratio / (Ke - g)
  Ke = RiskFree + EquityRiskPremium
  g  = min(历史盈利增速, 可持续增速, 行业增速, 名义GDP增速)，且受 g <= Ke - min_g_ke_margin 约束。
若 g >= Ke → GGM_INVALID，绝不输出虚假合理PE。
输出 Bear/Base/Bull 情景矩阵合理PE。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from valresearch.config import get_config


def _cagr(first, last, n):
    if first is None or last is None or n <= 0 or first <= 0 or last <= 0:
        return None
    return (last / first) ** (1.0 / n) - 1.0


def historical_eps_cagr(fin, asof=None, years=5):
    """用年度 EPS 序列计算历史增速 CAGR。fin: DataFrame[report_period, eps_basic]。
    P0-A: asof 给定则只用 announcement_date<=asof 的财报（修订感知：每期取当时最新版本）。"""
    if fin is None or fin.empty:
        return None
    if asof is not None:
        from valresearch.data.pit import annual_versions_pit
        ann = annual_versions_pit(fin, asof)
    else:
        from valresearch.data.pit import annual_versions_pit
        ann = annual_versions_pit(fin, None)
    if ann is None:
        return None
    ann = ann[pd.to_numeric(ann['eps_basic'], errors='coerce').notna()]
    if len(ann) < 2:
        return None
    series = ann['eps_basic'].astype(float).tail(years + 1).tolist()
    if len(series) < 2:
        return None
    return _cagr(series[0], series[-1], len(series) - 1)


def roe_from_financials(fin, asof=None):
    """最近年报 ROE = 归母净利 / 股东权益(总资产-总负债)。缺任一或权益<=0 → None。
    P0-A: asof 给定则只用 announcement_date<=asof 的财报（修订感知）。"""
    if fin is None or fin.empty:
        return None
    if asof is not None:
        from valresearch.data.pit import annual_versions_pit
        ann = annual_versions_pit(fin, asof)
    else:
        from valresearch.data.pit import annual_versions_pit
        ann = annual_versions_pit(fin, None)
    if ann is None or ann.empty:
        return None
    row = ann.iloc[-1]
    np_, ta, tl = row.get('net_profit_attr'), row.get('total_assets'), row.get('total_liabilities')
    if np_ is None or ta is None or tl is None or pd.isna(np_) or pd.isna(ta) or pd.isna(tl):
        return None
    equity = float(ta) - float(tl)
    if equity <= 0:
        return None
    return float(np_) / equity


def sustainable_growth(roe, payout_ratio):
    """P0-6: 可持续增速 = ROE×(1-payout)。payout 为小数(0~1)。缺任一/非法→None；g<=0→None。"""
    if roe is None or payout_ratio is None or pd.isna(roe) or pd.isna(payout_ratio):
        return None
    if payout_ratio < 0 or payout_ratio > 1:
        return None
    g = float(roe) * (1.0 - float(payout_ratio))
    return g if g > 0 else None


def compute_growth(fin, payout_ratio, asof=None, cfg=None):
    """长期增长率 g：min(历史增速, 可持续增速, 行业增速, 名义GDP)。返回 (g, 各来源, 是否约束失效)。
    P0-A: asof 给定则增速/ROE 只用 announcement_date<=asof 的财报（修订感知，无未来函数）。"""
    cfg = cfg or get_config('balanced')
    gdp = cfg.get('gdp_growth', 0.05)
    industry = cfg.get('industry_growth', gdp)   # 无行业数据时用GDP近似，标记
    hist = historical_eps_cagr(fin, asof)
    # P0-6/P0-A: 可持续增速 = ROE×(1-payout)，ROE 取 asof 时点已公告最新年报（修订感知）
    roe = roe_from_financials(fin, asof)
    sustainable = sustainable_growth(roe, payout_ratio) if roe is not None else hist
    sources = {'hist': hist, 'sustainable': sustainable, 'roe': roe,
               'industry': industry, 'gdp': gdp}
    vals = [v for v in sources.values() if v is not None and v > 0]
    g = min(vals) if vals else None
    return g, sources


def gordon(payout_ratio, ke, g, min_margin=0.02):
    """GGM 合理PE。payout_ratio 为小数(0~1)。

    拒绝条件(返回 None):
      - 参数缺失 / g >= ke / 合理PE非正
    降级条件(返回 PE + 警告):
      - 0 < ke-g <= min_margin: 返回 PE 但标注 THIN_SPREAD（结果可用但置信度低）
    """
    if payout_ratio is None or ke is None or g is None:
        return None, 'GGM_INVALID: 参数缺失'
    if g >= ke:
        return None, 'GGM_INVALID: g>=Ke'
    spread = ke - g
    fair_pe = payout_ratio / spread
    if fair_pe <= 0 or not np.isfinite(fair_pe):
        return None, 'GGM_INVALID: 合理PE非正'
    if spread <= min_margin:
        return round(float(fair_pe), 2), 'GGM_THIN_SPREAD: Ke-g=%.2f%% 过小' % (spread * 100)
    return round(float(fair_pe), 2), None


def fair_price(eps_ttm, fair_pe):
    if eps_ttm is None or fair_pe is None:
        return None
    return round(float(eps_ttm) * float(fair_pe), 2)


def scenario_matrix(payout_ratio, eps_ttm, rf, erp, g, cfg=None):
    """Bear/Base/Bull 情景矩阵。返回 dict 含 fair_pe_low/base/high 与 fair_price_low/base/high 及状态。"""
    cfg = cfg or get_config('balanced')
    gd = cfg.get('gordon', {})
    # Ke 偏移：Bear 更高折现(+1%), Bull 更低折现(-1%)；g 情景：Bear 低增长, Bull 高增长
    ke_bear = rf + erp + gd.get('ke_bear', 0.01)
    ke_base = rf + erp + gd.get('ke_base', 0.0)
    ke_bull = rf + erp + gd.get('ke_bull', -0.01)
    g_bear = (g or 0) + gd.get('g_bear', -0.01)
    g_base = g
    g_bull = (g or 0) + gd.get('g_bull', 0.01)
    min_margin = gd.get('min_g_ke_margin', 0.02)

    def calc(ke_, g_):
        pe, err = gordon(payout_ratio, ke_, g_, min_margin)
        return pe, fair_price(eps_ttm, pe), err

    pl, pr_l, er_bear = calc(ke_bear, g_bear)
    pb, pr_b, er_base = calc(ke_base, g_base)
    ph, pr_h, er_bull = calc(ke_bull, g_bull)
    # invalid 仅反映 base 情况；bear/bull 失败是情景边界信息，不构成"模型失效"
    thin_spread = any(e and 'THIN_SPREAD' in e for e in (er_bear, er_base, er_bull))
    res = {
        'fair_pe_low': pl, 'fair_pe_base': pb, 'fair_pe_high': ph,
        'fair_price_low': pr_l, 'fair_price_base': pr_b, 'fair_price_high': pr_h,
        'ke_bear': round(ke_bear, 4), 'ke_base': round(ke_base, 4), 'ke_bull': round(ke_bull, 4),
        'g': round(g_base, 4) if g_base is not None else None,
        'g_bear': round(g_bear, 4), 'g_bull': round(g_bull, 4),
        'erp': round(erp, 4), 'rf': round(rf, 4),
        'invalid': er_base if er_base and 'THIN_SPREAD' not in er_base else '',
        'thin_spread': thin_spread,
        'scenario_errors': {'bear': er_bear, 'base': er_base, 'bull': er_bull},
    }
    return res


def pe_fair_ratio(current_pe, base_fair_pe):
    """当前PE / Base合理PE。"""
    if current_pe is None or base_fair_pe is None or base_fair_pe <= 0:
        return None
    return round(float(current_pe) / float(base_fair_pe), 3)


def pe_fair_band(ratio):
    if ratio is None:
        return 'NA'
    if ratio < 0.8:
        return '低估'
    if ratio < 1.0:
        return '偏低估'
    if ratio < 1.2:
        return '合理'
    if ratio < 1.5:
        return '偏高估'
    return '高估'