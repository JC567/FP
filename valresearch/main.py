# -*- coding: utf-8 -*-
"""红利价值分位研究 - 主分析流程编排器。

analyze(symbol, analysis_date, mode) → AnalysisReport
全程 PIT（公告日<=t 才可用），质量不达标拒出结论；缺失字段标注 DATA_INSUFFICIENT，不伪造。
"""
from __future__ import annotations

import datetime
from typing import Optional

import pandas as pd

from valresearch import config as cfgmod
from valresearch.models import AnalysisReport
from valresearch.data import quality as qc
from valresearch.data.providers import (DataProvider, FinancialDataProvider,
                                        DividendDataProvider, MacroDataProvider,
                                        IndustryDataProvider)
from valresearch.valuation import engine, percentile as pct
import importlib
gg = importlib.import_module('valresearch.valuation.gordon')
qs = importlib.import_module('valresearch.fundamental.quality_score')
vt = importlib.import_module('valresearch.risk.value_trap')
bk = importlib.import_module('valresearch.fundamental.banking')   # 银行专用质量/市净率
from valresearch.valuation.price_range import (buy_range, current_zone, hist_price_map,
                                               price_methods, unify_price, risk_adjust_price)  # P1-3
from valresearch.signal import compute_signal
from valresearch.signal.position import position_plan
from valresearch.data.confidence import data_confidence_score  # P1-1


def _asof_bond(bond, t):
    if bond is None or bond.empty:
        return None
    b = bond.copy()
    b['d'] = pd.to_datetime(b['date'])
    sub = b[b['d'] <= pd.to_datetime(t)]
    if sub.empty:
        return None
    return float(sub.iloc[-1]['cn10y'])


def analyze(symbol: str, analysis_date: Optional[str] = None,
            mode: str = 'balanced', name: str = '', cfg=None,
            progress_cb=None) -> AnalysisReport:
    """progress_cb(percent: float, message: str) 可选，用于界面显示进度。"""
    def _prog(p, msg):
        if progress_cb is not None:
            try:
                progress_cb(max(0.0, min(1.0, p)), msg)
            except Exception:
                pass
    cfg = cfg or cfgmod.get_config(mode)
    if analysis_date is None:
        analysis_date = datetime.date.today().isoformat()
    rep = AnalysisReport(symbol=symbol, name=name or symbol,
                          analysis_date=analysis_date, mode=cfg.get('mode', mode))

    # 1. 取数
    _prog(0.05, '正在获取行情/PE/财报/分红/国债/行业数据…')
    dp, fp, dd, mp, ip = (DataProvider(), FinancialDataProvider(),
                          DividendDataProvider(), MacroDataProvider(), IndustryDataProvider())
    price = dp.get_price(symbol)
    pe = dp.get_pe_ttm(symbol)
    fin = fp.get_financials(symbol)
    div = dd.get_dividends(symbol)
    bond = mp.get_bond_yield()
    ind = ip.get_industry(symbol, name)
    industry_type = ind.get('industry_type', '制造业')
    rep.industry = ind.get('industry', '')
    rep.industry_type = industry_type
    rep.data_limitations.append('行业识别来源=' + ind.get('source', ''))
    if ind.get('source') == 'keyword-inference':
        rep.data_limitations.append('行业为关键词推断(启发式)，可配置覆盖')
    _prog(0.15, '数据获取完成')

    # 2. 质量检查
    _prog(0.20, '执行数据质量检查…')
    warnings = qc.run_all(price, pe, fin, div)
    hard = qc.hard_block(warnings)
    rep.quality_warnings = list(dict.fromkeys(warnings))
    rep.data_limitations.append('PE_TTM 为严格 PIT 自算：PE=Price/EPS_TTM_PIT（公告日PIT，eps<=0→NaN），'
                                '不再依赖外部历史PE')
    rep.data_limitations.append('财报公告日按法规截止日近似(DATA_CALIBER_RISK)，PIT精度受其影响')
    if hard:
        rep.notes.append('DATA_QUALITY_WARNING: 存在阻断性数据缺失，本报告不构成投资结论')
        rep.notes.append('请核对: ' + '; '.join(rep.quality_warnings))
        _prog(1.0, '数据质量不达标，已中止')
        return rep
    _prog(0.25, '质量检查通过')

    # 3. 估值序列 + 当前值
    _prog(0.30, '构建估值序列(PE/股息率/分红率)…')
    t = pd.Timestamp(analysis_date)
    series = engine.build_series(price, pe, fin, div, window_years=10, end=t)
    if series is None or series.empty:
        rep.notes.append('DATA_INSUFFICIENT: 无法构建估值序列(窗口内无交易数据)')
        _prog(1.0, '数据不足，已中止')
        return rep
    last = series.iloc[-1]
    cur_pe = last['pe'] if last['pe_valid'] else None
    cur_dy = last['dy']
    cur_payout = last['payout']
    cur_eps = last['eps_ttm']
    cur_dps = last['dps_ttm']
    cur_price = last['close']
    _prog(0.40, '估值序列构建完成')

    # 4. 分位数
    _prog(0.45, '计算 10年/5年 历史分位数…')
    pe_series = series.loc[series['pe_valid'] & series['pe'].notna(), 'pe']
    pe_hist, n_pe_excl, _ = pct.filter_pe(pe_series, cur_pe, cfg['valuation'].get('negative_pe', 'exclude'))
    pe_stats10 = pct.percentile_stats(pe_hist, cur_pe, n_excluded=n_pe_excl,
                                      start=series['date'].iloc[0].date(),
                                      end=series['date'].iloc[-1].date())
    cut5 = series['date'].iloc[-1] - pd.Timedelta(days=5 * 365.25)
    pe5 = series.loc[(series['pe_valid']) & (series['pe'].notna()) & (series['date'] >= cut5), 'pe']
    pe_hist5, n5, _ = pct.filter_pe(pe5, cur_pe, cfg['valuation'].get('negative_pe', 'exclude'))
    pe_stats5 = {'pct': pct.count_pct(pe_hist5, cur_pe),
                 'n_valid': int(len(pe_hist5)), 'n_excluded': n5,
                 'start': str(cut5.date()), 'end': str(series['date'].iloc[-1].date())}

    dy_series = series['dy'].dropna()
    cur_dy = float(dy_series.iloc[-1]) if not dy_series.empty else None
    dy_stats10 = pct.percentile_stats(dy_series, cur_dy, start=series['date'].iloc[0].date(),
                                      end=series['date'].iloc[-1].date())
    dy5 = series.loc[series['date'] >= cut5, 'dy'].dropna()
    dy_stats5 = {'pct': pct.count_pct(dy5, float(dy5.iloc[-1]) if not dy5.empty else None),
                 'n_valid': int(len(dy5)),
                 'start': str(cut5.date()), 'end': str(series['date'].iloc[-1].date())}

    pr_series = series['payout'].dropna()
    pr_valid, pr_excl, pr_abnormal, cur_pr = pct.filter_payout(
        pr_series, cur_payout, cfg['payout'].get('lower', 0.0),
        cfg['payout'].get('upper', 1.5), cfg['payout'].get('winsorize', True),
        cfg['payout'].get('winsor_percent', 0.01))
    pr_stats10 = pct.percentile_stats(pr_valid, cur_pr, n_excluded=pr_excl,
                                      start=series['date'].iloc[0].date(),
                                      end=series['date'].iloc[-1].date())
    pr5 = series.loc[series['date'] >= cut5, 'payout'].dropna()
    pr_valid5, pr_excl5, _, _ = pct.filter_payout(
        pr5, float(pr5.iloc[-1]) if not pr5.empty else None,
        cfg['payout'].get('lower', 0.0), cfg['payout'].get('upper', 1.5),
        cfg['payout'].get('winsorize', True), cfg['payout'].get('winsor_percent', 0.01))
    pr_stats5 = {'pct': pct.count_pct(pr_valid5, float(pr_valid5.iloc[-1]) if not pr_valid5.empty else None),
                 'n_valid': int(len(pr_valid5)), 'n_excluded': pr_excl5,
                 'start': str(cut5.date()), 'end': str(series['date'].iloc[-1].date())}

    # 5. 股息率-国债利差
    _prog(0.60, '计算股息率-国债利差…')
    rf = _asof_bond(bond, t)
    spread = None
    spread_signal = None
    spread_thr_pct = None
    if cur_dy is not None and rf is not None:
        spread = round(cur_dy - rf, 3)     # 百分点
        spread_thr_pct = cfg['macro'].get('treasury_spread', 0.02) * 100
        spread_signal = bool(spread > spread_thr_pct)

    # 6. Gordon (rf 转小数；erp/g 已是小数)  P0-A: compute_growth 传 asof=t（时点PIT）
    payout_dec = (cur_pr / 100.0) if cur_pr is not None else None
    g, g_sources = gg.compute_growth(fin, payout_dec, t, cfg)
    erp = cfg['gordon'].get('equity_risk_premium', 0.05)
    scen = gg.scenario_matrix(payout_dec, cur_eps, (rf / 100.0) if rf is not None else None,
                              erp, g, cfg) if rf is not None else None
    ratio = gg.pe_fair_ratio(cur_pe, scen['fair_pe_base'] if scen else None)
    ratio_band = gg.pe_fair_band(ratio)
    if scen and scen.get('invalid'):
        gordon_status = 'INVALID'
    elif scen and scen.get('thin_spread') and ratio is not None:
        gordon_status = 'THIN_SPREAD'   # Ke-g 过小，PE 可用但置信度低
    elif ratio is not None:
        gordon_status = 'VALID'
    else:
        gordon_status = 'INSUFFICIENT'

    # 7. 基本面质量 + 价值陷阱
    _prog(0.70, '计算基本面质量与价值陷阱…')
    quality = qs.quality_score(fin, div, t, industry_type, ind.get('industry', ''), cfg, symbol=symbol)
    vtres = vt.value_trap_score(quality, industry_type, cfg)
    _prog(0.80, '质量与陷阱评分完成')

    # 8. 信号
    _prog(0.85, '生成信号…')
    metrics = {'pe_pct': pe_stats10.pct_10y, 'dy_pct': dy_stats10.pct_10y,
               'pr_pct': pr_stats10.pct_10y, 'spread': spread,
               'spread_threshold': spread_thr_pct,
               'pe_fair_ratio': ratio, 'quality_score': quality['score'],
               'gordon_status': gordon_status,
               'industry_score': quality['sub'].get('industry', 50)}
    sig = compute_signal(metrics, quality, vtres, cfg)
    _prog(0.90, '信号生成完成')

    # P1-1: 数据置信度
    _comp = sig.get('components', {})
    n_valid_dims = sum(1 for k in ('pe', 'dy', 'payout', 'spread', 'gordon', 'quality', 'industry')
                       if _comp.get(k) is not None)
    ann_src = 'ESTIMATED'
    if fin is not None and not fin.empty and 'announcement_date_source' in fin.columns:
        valid_src = fin['announcement_date_source'].dropna()
        if len(valid_src):
            from valresearch.data.confidence import ann_source_score
            ann_src = min(valid_src, key=ann_source_score)   # 取最保守来源
    n_years = 0
    if fin is not None and not fin.empty:
        n_years = int(pd.to_datetime(fin['report_period']).dt.year.drop_duplicates().nunique())
    conf = data_confidence_score(n_valid_dims, ann_src, n_years)
    _conf = conf
    rep.data_limitations.append(f'数据置信度 {conf["level"]} ({conf["score"]}/100)：' + '；'.join(conf['reasons']))

    # P1-7: 模型解释链
    _explanation = None
    try:
        from valresearch.signal.explain import explain_signal
        _explanation = explain_signal(
            sig.get('metrics', {}), _comp, sig.get('thresholds', {}),
            sig.get('hysteresis_bands', {}), vtres.get('level', 'LOW'),
            sig.get('final_signal', 'HOLD'), sig.get('note', []), cfg)
    except Exception as e:  # 解释链失败不影响主流程
        rep.data_limitations.append(f'模型解释链生成失败(忽略)：{e}')

    # 9. 价格区间
    prange = buy_range(cur_eps, pe_stats10, cur_dps, scen['fair_price_base'] if scen else None,
                       quality_ok=quality['score'] >= 60)
    prange.update(hist_price_map(cur_eps, pe_stats10))
    prange['current_zone'] = current_zone(cur_pe, pe_stats10, dy_stats10.pct_10y, dy_stats10.p80)
    # P1-3: 价格区间统一 + 风险调整
    pm = price_methods(cur_eps, pe_stats10, cur_dps, scen['fair_price_base'] if scen else None)
    unified = unify_price(pm)
    risk_adj = risk_adjust_price(unified['fair_price'], vtres['penalty'],
                                 gordon_status != 'VALID')
    prange['unified'] = unified
    prange['risk_adjusted_fair'] = risk_adj
    if unified.get('uncertain'):
        rep.data_limitations.append('各估值法合理价格差异过大，统一合理价存在不确定(UNCERTAIN)')

    # 10. 仓位
    pos = position_plan(sig['final_signal'], vtres, cfg)

    # 11. 组装
    # 银行专用：市净率 PB（破净=便宜代理），仅金融业计算；字段缺失则 None
    pb = None
    if bk.is_financial(industry_type):
        try:
            _bv = bk.book_value_latest(fin, t, symbol=symbol)
            if _bv is not None and _bv.get('bvps') is not None and cur_price is not None:
                pb = round(float(cur_price) / float(_bv['bvps']), 3)
        except Exception:
            pb = None
    rep.valuation = {
        'date': str(series['date'].iloc[-1].date()),
        'price': round(float(cur_price), 2) if cur_price is not None else None,
        'pb': pb,
        'eps_ttm': round(float(cur_eps), 3) if cur_eps is not None else None,
        'dps_ttm': round(float(cur_dps), 3) if cur_dps is not None else None,
        'pe_ttm': round(float(cur_pe), 2) if cur_pe is not None else None,
        'pe_pct_10y': pe_stats10.pct_10y, 'pe_pct_5y': pe_stats5.get('pct'),
        'pe_min': pe_stats10.min, 'pe_max': pe_stats10.max, 'pe_median': pe_stats10.median,
        'pe_p10': pe_stats10.p10, 'pe_p25': pe_stats10.p25, 'pe_p50': pe_stats10.p50,
        'pe_p75': pe_stats10.p75, 'pe_p90': pe_stats10.p90,
        'pe_p20': pe_stats10.p20, 'pe_p30': pe_stats10.p30, 'pe_p70': pe_stats10.p70,
        'pe_n_valid': pe_stats10.n_valid, 'pe_n_excluded': pe_stats10.n_excluded,
        'dividend_yield': round(float(cur_dy), 2) if cur_dy is not None else None,
        'dividend_yield_pct': dy_stats10.pct_10y, 'dy_pct_5y': dy_stats5.get('pct'),
        'dy_min': dy_stats10.min, 'dy_max': dy_stats10.max, 'dy_median': dy_stats10.median,
        'dy_p10': dy_stats10.p10, 'dy_p90': dy_stats10.p90, 'dy_n_valid': dy_stats10.n_valid,
        'payout_ratio': round(float(cur_pr), 1) if cur_pr is not None else None,
        'payout_pct': pr_stats10.pct_10y, 'pr_pct_5y': pr_stats5.get('pct'),
        'pr_n_valid': pr_stats10.n_valid, 'pr_n_excluded': pr_stats10.n_excluded,
        'payout_abnormal': bool(pr_abnormal.any()) if len(pr_abnormal) else False,
        'rf_10y': round(float(rf), 3) if rf is not None else None,
        'dividend_spread': spread, 'spread_threshold': spread_thr_pct,
        'spread_signal': spread_signal,
    }
    rep.fundamental = {
        'quality_score': quality['score'], 'sub': quality['sub'],
        'detail': quality['detail'], 'flags': quality['flags'],
        'warnings': quality['warnings'],
    }
    rep.value_trap = {'score': vtres['score'], 'level': vtres['level'],
                      'flags': vtres['flags'], 'detail': vtres['detail'],
                      'penalty': vtres['penalty'], 'block_strong_buy': vtres['block_strong_buy']}
    # P0-F: rep.signal 必须包含全部关键字段，且不被后续覆盖丢失。
    rep.signal = {k: sig[k] for k in ('condition_a', 'condition_b', 'condition_c', 'rule_signal',
                                      'score', 'base_score', 'score_signal', 'value_trap_level',
                                      'final_signal', 'note', 'mode', 'thresholds', 'components',
                                      'gordon_status', 'gordon_penalty', 'hysteresis_bands', 'metrics')}
    # P1-1/P1-7: 数据置信度与解释链须最终进入 rep.signal（避免被上面赋值覆盖）
    rep.signal['data_confidence'] = _conf
    if _explanation is not None:
        rep.signal['explanation'] = _explanation
    rep.signal['gordon_g'] = round(g, 4) if g is not None else None
    rep.signal['g_growth_sources'] = {k: (round(v, 4) if v is not None else None)
                                      for k, v in g_sources.items()}
    rep.signal['pe_fair_ratio'] = ratio
    rep.signal['pe_fair_band'] = ratio_band
    if scen:
        rep.signal['gordon_scenario'] = {k: v for k, v in scen.items()}
    rep.price = prange
    rep.position = pos
    rep.trace = {
        'pe': {'source': 'pit_calculated', 'n_valid': pe_stats10.n_valid,
               'n_excluded': pe_stats10.n_excluded,
               'window': f"{pe_stats10.window_10y_start} ~ {pe_stats10.window_10y_end}",
               'formula': 'PE_TTM(t)=Price(t)/EPS_TTM_PIT(t), 公告日PIT, eps<=0→NaN'},
        'dy': {'source': 'cninfo分红+sina日线', 'n_valid': dy_stats10.n_valid,
               'formula': 'DPS_TTM(近12月已实施)/price×100, count(DY<cur)/n'},
        'payout': {'source': 'cninfo分红+ths财报', 'n_valid': pr_stats10.n_valid,
                   'n_excluded': pr_stats10.n_excluded,
                   'formula': '现金分红总额TTM/归母净利TTM×100(严格口径), DPS/EPS仅cross-check, 越界winsorize'},
        'gordon': {'source': 'ths财报+国债', 'formula': 'FairPE=Payout/(Ke-g), Ke=Rf+ERP'},
        'rf': {'source': 'bond_zh_us_rate(中国10Y)'},
    }
    rep.notes.append('便宜≠一定上涨；高股息≠一定安全；历史低估≠未来不会继续下跌。')
    for _key, _nv in (('PE', pe_stats10.n_valid), ('股息率', dy_stats10.n_valid),
                      ('分红率', pr_stats10.n_valid)):
        if _nv is not None and _nv < 260:   # 少于约1年交易日 → 分位样本偏少
            rep.data_limitations.append(
                f'{_key}样本量偏少({_nv}个，数据/上市期短)，历史分位可能系统性偏低，需谨慎解读')
    _prog(1.0, '分析完成')
    return rep