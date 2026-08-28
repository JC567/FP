# -*- coding: utf-8 -*-
"""单股历史重估回测（Phase 10）。

对每个再平衡时点 t，用截至 t 已公开的数据（PIT）重算完整分析信号，模拟“按信号进出场”的持仓收益，
并与 Buy&Hold 及基准指数对比。绝不使用未来数据。
"""
from __future__ import annotations

import datetime
import importlib
from typing import Optional

import numpy as np
import pandas as pd

from valresearch import config as cfgmod
from valresearch.data.providers import (DataProvider, FinancialDataProvider,
                                        DividendDataProvider, MacroDataProvider,
                                        IndustryDataProvider)
from valresearch.valuation import engine, percentile as pct
from valresearch.backtest.metrics import metrics as perf_metrics, win_rate

gg = importlib.import_module('valresearch.valuation.gordon')
qs = importlib.import_module('valresearch.fundamental.quality_score')
vt = importlib.import_module('valresearch.risk.value_trap')
signal_mod = importlib.import_module('valresearch.signal.engine')
position_mod = importlib.import_module('valresearch.signal.position')

_INVEST = ('BUY', 'STRONG_BUY', 'ACCUMULATE')


def _invest_daily(final_signals, return_index, invest=_INVEST) -> pd.Series:
    """把(再平衡日索引)的进出场布尔序列映射到日频收益索引，并强制 T+1 执行。

    - 决策 basis 日 = 该再平衡日之前(含)最后一个交易日（其收盘数据用于生成信号）。
    - 持仓自 basis 日的下一个交易日(严格 >basis)起生效 → 绝不实现"信号生成当天"的收益，
      杜绝同日收盘价成交的前视。
    - 再平衡日通常为周末(非交易日)：basis=上周五，持仓自次周一生效（T+1）。
    """
    inv = final_signals.isin(invest)          # indexed by decision date D（升序）
    idx = np.asarray(pd.to_datetime(return_index)).astype('datetime64[D]')
    out = np.zeros(len(idx), dtype=bool)
    dd = np.asarray(pd.to_datetime(final_signals.index)).astype('datetime64[D]')
    n = len(final_signals)
    for k, D in enumerate(dd):
        basis_mask = idx <= D
        if not basis_mask.any():
            continue
        basis = idx[np.where(basis_mask)[0][-1]]
        eff = int(np.searchsorted(idx, basis, side='right'))   # 第一个 >basis 的交易日
        if eff >= len(idx):
            continue
        end_eff = len(idx)
        if k + 1 < n:
            nb = idx[idx <= dd[k + 1]]
            if nb.size:
                end_eff = int(np.searchsorted(idx, nb[-1], side='right'))
        out[eff:end_eff] = bool(inv.iloc[k])
    return pd.Series(out, index=return_index)


def _equity_with_cost(rets, weights, unit_cost):
    """P0-10: 按日权重与调仓摩擦成本累计净值。rets/weights 为等长数组。"""
    rets = np.asarray(rets, dtype=float)
    weights = np.asarray(weights, dtype=float)
    eq = 1.0
    prev_w = 0.0
    out = np.empty(len(rets))
    for i in range(len(rets)):
        w = weights[i]
        cost = abs(w - prev_w) * unit_cost
        eq *= 1.0 + rets[i] * w - cost
        out[i] = eq
        prev_w = w
    return out


_BUY_SET = {'BUY', 'STRONG_BUY', 'ACCUMULATE'}

# 巴菲特模式触发阈值：质量分高(护城河扎实) + Gordon合理PE留安全边际 + 非价值陷阱
_BUFFETT_QUALITY_MIN = 60.0     # 质量分(0-100)下限，越高护城河越扎实
_BUFFETT_VTSCORE_MAX = 50.0     # 价值陷阱分上限，越低越不是陷阱
_BUFFETT_FAIR_RATIO_MAX = 0.8   # cur_pe/Gordon合理PE <= 0.8 => 价≤合理价×0.8，留 20% 安全边际


def simulate_capital_modes(px_price, dates, reb_dates, reb_signal, reb_pe, reb_dy,
                           annual_budget=500000.0, rf_yield=None, reb_buffett=None):
    """资本预算回测：每年注入 annual_budget，比较四种建仓模式（价格用 px_price，含分红再投则用后复权）。

    返回 {mode: {'value': Series(每日资产=持股*价+现金), 'invested': 累计投入}}。
      · monthly   每月定投：每月首个交易日投入 annual_budget/12（现金不足则投入剩余）。
      · strategy  策略买点：出现买入类信号(买入/强烈买入/逢低吸纳)时，把当时全部可用现金一次买完；
                          当年无买点则现金自然留存到下一年（预算每年照常注入）。
      · smart     智能定投：每月定投基数 annual_budget/12，按估值分位动态调节当月金额
                          (便宜多买、贵了少买)：cheap=(股息率分位-PE分位)/100，倍数=clamp(1+cheap,0.5,2.0)。
      · buffett   巴菲特模式：仅在" quality高(护城河扎实) + Gordon合理PE留安全边际(价≤合理价×0.8)
                  + 非价值陷阱 "同时成立时建仓，且低估区分批（每月额度）买入、永不卖出(持有 forever)；
                  不满足条件则现金留存（吃国债利息）到下个机会。
    现金每年初注入 annual_budget；分红已含于后复权价，不再单独处理。
    闲置现金每日按 10Y 国债收益率(rf_yield, 年化%、与 dates 对齐) 复利计息（自动"买国债"），
    买点/定投触发时连本带息一并换入股；rf_yield 为 None 则不计息（现金闲置）。
    """
    price = pd.to_numeric(px_price, errors='coerce').reindex(dates)
    reb_df = pd.DataFrame({'signal': list(reb_signal), 'pe': list(reb_pe), 'dy': list(reb_dy)},
                          index=pd.to_datetime(list(reb_dates)))
    if reb_buffett is not None:
        reb_df['buffett'] = list(reb_buffett)
    reb_df = reb_df.reindex(dates, method='pad')
    n = len(dates)
    monthly = annual_budget / 12.0
    is_buy = reb_df['signal'].isin(_BUY_SET).fillna(False).to_numpy()
    is_buffett = reb_df['buffett'].fillna(False).to_numpy().astype(bool) if 'buffett' in reb_df else None
    pe = reb_df['pe'].to_numpy()
    dy = reb_df['dy'].to_numpy()
    rf = np.asarray(rf_yield, dtype=float) if rf_yield is not None else None

    def _sim(kind):
        shares = 0.0
        cash = 0.0
        invested = 0.0
        cur_year = None
        last_month = None
        vals = np.empty(n)
        for i in range(n):
            d = dates[i]
            yr = d.year
            if cur_year != yr:
                cash += annual_budget
                cur_year = yr
            # 闲置现金按 10Y 国债每日复利计息（自动买国债）
            if rf is not None:
                r = rf[i]
                if r == r and r > 0:   # 非 NaN 且为正
                    cash *= (1.0 + r / 100.0) ** (1.0 / 252.0)
            p = price.iloc[i]
            if kind == 'monthly':
                if last_month != d.month:
                    amt = min(monthly, cash)
                    if p and p > 0 and amt > 0:
                        shares += amt / p
                        cash -= amt
                        invested += amt
                    last_month = d.month
            elif kind == 'strategy':
                if is_buy[i] and cash > 0 and p and p > 0:
                    shares += cash / p
                    invested += cash
                    cash = 0.0
            elif kind == 'smart':
                if last_month != d.month:
                    pev = 50.0 if pd.isna(pe[i]) else pe[i]
                    dyv = 50.0 if pd.isna(dy[i]) else dy[i]
                    cheap = (dyv / 100.0) - (pev / 100.0)
                    mult = max(0.5, min(2.0, 1.0 + 1.0 * cheap))
                    amt = min(monthly * mult, cash)
                    if p and p > 0 and amt > 0:
                        shares += amt / p
                        cash -= amt
                        invested += amt
                    last_month = d.month
            elif kind == 'buffett':
                if last_month != d.month and is_buffett is not None and is_buffett[i] \
                        and cash > 0 and p and p > 0:
                    amt = min(monthly, cash)   # 低估区分批：每月额度，连续低估则逐月买
                    shares += amt / p
                    cash -= amt
                    invested += amt
                    last_month = d.month
            vals[i] = (shares * p if p == p else shares * 0.0) + cash
        return vals, invested

    out = {}
    for k in ('monthly', 'strategy', 'smart', 'buffett'):
        v, inv = _sim(k)
        s = pd.Series(v, index=dates)
        out[k] = {'value': s, 'invested': float(inv)}
    return out


def _weight_daily(final_signals, vt_objs, return_index, cfg) -> pd.Series:
    """P0-9/P1-8: 真正用仓位系统(信号→target_weight)，按 T+1 映射到日频，产出 0~1 权重序列。

    与 _invest_daily 相同的基础日/T+1 逻辑。但 position.table 的 target_weight 是**组合级**绝对配比
    (STRONG_BUY≤5%)，直接用于单股回测会常年空仓、波动近 0。因此按**单股上限归一化**：
        invest_weight = min(1.0, target_weight / backtest.max_position)
    使 STRONG_BUY 达到单股满仓、BUY/ACCUMULATE 按梯度缩仓，HOLD/WAIT/REDUCE/SELL → 0。
    单股回测为纯多头：组合减仓的负权重(REDUCE/SELL)一律归 0，禁止变做空。
    P0-E: vt_objs 为**完整 value_trap 结果 dict 序列**（含 score/level/flags/penalty），
    直接传给 position_plan 做陷阱修正，不再用 vt_score 重构 LOW/penalty=0。
    allow_sell=False（只买不卖模式）：权重只增不减 w=max(w, prev_w)——本模型定位是判断买点，
    卖出信号(HOLD/WAIT/REDUCE/SELL→0、陷阱强制清仓)不再减仓，仅阻止新增买入；首次买入前仍为 0。
    """
    bt_cfg = cfg.get('backtest', {})
    cap = float(bt_cfg.get('max_position', 0.10)) or 0.10
    allow_sell = bool(bt_cfg.get('allow_sell', True))
    idx = np.asarray(pd.to_datetime(return_index)).astype('datetime64[D]')
    out = np.zeros(len(idx), dtype=float)
    dd = np.asarray(pd.to_datetime(final_signals.index)).astype('datetime64[D]')
    n = len(final_signals)
    prev_w = 0.0
    for k, D in enumerate(dd):
        basis_mask = idx <= D
        if not basis_mask.any():
            continue
        basis = idx[np.where(basis_mask)[0][-1]]
        eff = int(np.searchsorted(idx, basis, side='right'))
        if eff >= len(idx):
            continue
        end_eff = len(idx)
        if k + 1 < n:
            nb = idx[idx <= dd[k + 1]]
            if nb.size:
                end_eff = int(np.searchsorted(idx, nb[-1], side='right'))
        vt = {}
        if vt_objs is not None and k < len(vt_objs):
            obj = vt_objs.iloc[k] if hasattr(vt_objs, 'iloc') else vt_objs[k]
            if isinstance(obj, dict):
                vt = obj
            else:
                vt = {'score': float(obj), 'level': 'LOW', 'penalty': 0.0}
        tw = position_mod.position_plan(final_signals.iloc[k], vt, cfg)['target_weight']
        # 单股回测为纯多头：负权重(组合减仓语义)归一化后禁止变做空，一律归 0
        w = max(0.0, min(1.0, tw / cap)) if cap > 0 else tw
        if not allow_sell:
            w = max(w, prev_w)   # 只买不卖：权重单调不减
        prev_w = w
        out[eff:end_eff] = w
    return pd.Series(out, index=return_index)


def _percentiles_at(ser10, cur_pe, cur_dy, cur_pr, cfg):
    pe_series = ser10.loc[ser10['pe_valid'] & ser10['pe'].notna(), 'pe']
    pe_valid, n_pe, _ = pct.filter_pe(pe_series, cur_pe, cfg['valuation'].get('negative_pe', 'exclude'))
    st_pe = pct.percentile_stats(pe_valid, cur_pe, n_excluded=n_pe)
    dy_series = ser10['dy'].dropna()
    st_dy = pct.percentile_stats(dy_series, cur_dy)
    pr_series = ser10['payout'].dropna()
    pr_valid, n_pr, abnormal, cur_pr2 = pct.filter_payout(
        pr_series, cur_pr, cfg['payout'].get('lower', 0.0), cfg['payout'].get('upper', 1.5),
        cfg['payout'].get('winsorize', True), cfg['payout'].get('winsor_percent', 0.01))
    st_pr = pct.percentile_stats(pr_valid, cur_pr2, n_excluded=n_pr)
    return st_pe, st_dy, st_pr


def _signal_at(t, ser, price, fin, div, bond, ind, industry_type, cfg, prev=None):
    ser_at = ser[ser['date'] <= t]
    if ser_at.empty:
        return None
    ser10 = ser_at[ser_at['date'] >= (t - pd.Timedelta(days=10 * 365.25))]
    last = ser_at.iloc[-1]
    cur_pe = last['pe'] if last['pe_valid'] else None
    cur_dy = last['dy']
    cur_pr = last['payout']
    cur_eps = last['eps_ttm']
    cur_dps = last['dps_ttm']
    st_pe, st_dy, st_pr = _percentiles_at(ser10, cur_pe, cur_dy, cur_pr, cfg)
    # 国债
    rf = None
    if bond is not None and not bond.empty:
        sub = bond[bond['date'] <= t]
        if not sub.empty:
            rf = float(sub.iloc[-1]['cn10y'])
    spread = None
    thr_pct = cfg['macro'].get('treasury_spread', 0.02) * 100
    if cur_dy is not None and rf is not None:
        spread = round(cur_dy - rf, 3)
    # Gordon
    payout_dec = (cur_pr / 100.0) if cur_pr is not None else None
    g, g_src = gg.compute_growth(fin, payout_dec, t, cfg)   # P0-A: 时点PIT
    erp = cfg['gordon'].get('equity_risk_premium', 0.05)
    scen = gg.scenario_matrix(payout_dec, cur_eps, (rf / 100.0) if rf is not None else None,
                              erp, g, cfg) if rf is not None else None
    ratio = gg.pe_fair_ratio(cur_pe, scen['fair_pe_base'] if scen else None)
    if scen and scen.get('invalid'):
        gordon_status = 'INVALID'
    elif scen and scen.get('thin_spread') and ratio is not None:
        gordon_status = 'THIN_SPREAD'
    elif ratio is not None:
        gordon_status = 'VALID'
    else:
        gordon_status = 'INSUFFICIENT'
    # 质量/陷阱
    quality = qs.quality_score(fin, div, t, industry_type, ind.get('industry', ''), cfg)
    vtres = vt.value_trap_score(quality, industry_type, cfg)
    metrics = {'pe_pct': st_pe.pct_10y, 'dy_pct': st_dy.pct_10y, 'pr_pct': st_pr.pct_10y,
               'spread': spread, 'spread_threshold': thr_pct, 'pe_fair_ratio': ratio,
               'gordon_status': gordon_status,
               'quality_score': quality['score'], 'industry_score': quality['sub'].get('industry', 50)}
    sig = signal_mod.compute_signal(metrics, quality, vtres, cfg, prev=prev)
    return {
        'price': float(last['close']),
        'pe_pct': st_pe.pct_10y, 'dy_pct': st_dy.pct_10y, 'pr_pct': st_pr.pct_10y,
        'spread': spread, 'rf': rf, 'quality': quality['score'],
        'vt_score': vtres['score'],
        'vt': vtres,               # P0-E: 完整 value_trap 对象(score/level/flags/penalty)
        'pe_fair_ratio': ratio,    # cur_pe / Gordon 合理PE（<=1 表示低于合理价）
        'gordon_status': gordon_status,
        'score': sig['score'],
        'rule_signal': sig['rule_signal'], 'final_signal': sig['final_signal'],
        'a': sig['condition_a'], 'b': sig['condition_b'], 'c': sig['condition_c'],
    }


def fetch_benchmark(symbol: str, start: str, end: str) -> Optional[pd.DataFrame]:
    """基准指数日线(新浪为主，东财兜底)。返回 DataFrame[date, close]。symbol 如 'sh000300'。"""
    import akshare as ak
    from valresearch.data.providers import _AK_LOCK, _retry
    df = None
    with _AK_LOCK:
        try:
            df = _retry(ak.stock_zh_index_daily, symbol=symbol)   # 新浪
        except Exception:
            df = None
    if df is None or df.empty:
        with _AK_LOCK:
            try:
                df = _retry(ak.stock_zh_index_daily_em, symbol=symbol,
                            start_date=start, end_date=end)
            except Exception:
                df = None
    if df is None or df.empty:
        return None
    date_col = next((c for c in df.columns if 'date' in str(c).lower() or '日期' in str(c)), None)
    close_col = next((c for c in df.columns if c == 'close' or '收盘' in str(c)), None)
    if not date_col or not close_col:
        return None
    out = pd.DataFrame({'date': pd.to_datetime(df[date_col]), 'close': pd.to_numeric(df[close_col], errors='coerce')})
    out = out.dropna(subset=['close']).sort_values('date')
    return out[(out['date'] >= pd.to_datetime(start)) & (out['date'] <= pd.to_datetime(end))]


def re_evaluate(symbol: str, start: str, end: str, mode: str = 'balanced',
                cfg=None, freq: str = 'W', progress_cb=None) -> pd.DataFrame:
    """返回 DataFrame[t, price, pe_pct, dy_pct, pr_pct, spread, rf, quality, vt_score, score, rule_signal, final_signal]。"""
    def _prog(p, msg):
        if progress_cb is not None:
            try:
                progress_cb(max(0.0, min(1.0, p)), msg)
            except Exception:
                pass
    cfg = cfg or cfgmod.get_config(mode)
    _prog(0.05, '正在获取历史数据…')
    dp, fp, dd, mp, ip = (DataProvider(), FinancialDataProvider(),
                          DividendDataProvider(), MacroDataProvider(), IndustryDataProvider())
    price = dp.get_price(symbol, start=(pd.to_datetime(start) - pd.Timedelta(days=11 * 365)).strftime('%Y%m%d'),
                         end=(pd.to_datetime(end)).strftime('%Y%m%d'))
    pe = dp.get_pe_ttm(symbol)
    fin = fp.get_financials(symbol)
    div = dd.get_dividends(symbol)
    bond = mp.get_bond_yield()
    ind = ip.get_industry(symbol)
    industry_type = ind.get('industry_type', '制造业')
    if fin is None or div is None or price is None:
        return pd.DataFrame()
    _prog(0.20, '构建历史估值序列…')
    t_end = pd.to_datetime(end)
    ser = engine.build_series(price, pe, fin, div, window_years=11, end=t_end)
    if ser is None or ser.empty:
        return pd.DataFrame()
    grid = pd.date_range(pd.to_datetime(start), t_end, freq=freq)
    _prog(0.25, f'逐周重估（共 {len(grid)} 期）…')
    rows = []
    n = max(1, len(grid))
    prev_cond = None
    for i, t in enumerate(grid, 1):
        r = _signal_at(t, ser, price, fin, div, bond, ind, industry_type, cfg, prev=prev_cond)
        if r is None:
            continue
        prev_cond = {'a': r['a'], 'b': r['b'], 'c': r['c']}
        r['t'] = t
        rows.append(r)
        _prog(0.25 + 0.6 * (i / n), f'重估第 {i}/{len(grid)} 期（{t.date()}）')
    _prog(0.85, '信号序列生成完成')
    return pd.DataFrame(rows).set_index('t')


def run_backtest(symbol: str, start: str, end: str = None, mode: str = 'balanced',
                 cfg=None, benchmark_symbols=('sh000300', 'sh000922', 'sh000923'),
                 freq: str = 'W', progress_cb=None, allow_sell=None,
                 dividend_reinvest: bool = True, annual_budget: float = 500000.0) -> dict:
    """单股回测：按信号进出场 vs Buy&Hold vs 基准。返回 dict。

    allow_sell: None=用 cfg['backtest']['allow_sell'](默认 true 按模型买卖)；
                 False=只买不卖(权重只增不减，适合"模型只用于判断买点"的用法)。
    dividend_reinvest: True(默认)=用后复权价(adj_close)，内含"分红次日自动再投"的复利效果；
                 False=仅用收盘价(不含分红再投)。
    """
    def _prog(p, msg):
        if progress_cb is not None:
            try:
                progress_cb(max(0.0, min(1.0, p)), msg)
            except Exception:
                pass
    cfg = cfg or cfgmod.get_config(mode)
    if not end:
        end = pd.Timestamp.today().strftime('%Y-%m-%d')   # 未指定结束日 => 取到今天
    if allow_sell is not None:
        import copy
        cfg = copy.deepcopy(cfg)
        cfg.setdefault('backtest', {})['allow_sell'] = bool(allow_sell)
    df = re_evaluate(symbol, start, end, mode, cfg, freq, progress_cb)
    if df.empty:
        return {'ok': False, 'reason': '无足够数据'}
    _prog(0.88, '模拟策略收益并对比基准…')
    dp = DataProvider()
    price = dp.get_price(symbol, start=(pd.to_datetime(start) - pd.Timedelta(days=400)).strftime('%Y%m%d'),
                         end=(pd.to_datetime(end)).strftime('%Y%m%d'))
    px = price.copy()
    px['date'] = pd.to_datetime(px['date'])
    actual_end = str(px['date'].max())[:10]   # 最近一个交易日（数据可得的最后交易日）
    # 红利再投(默认): 用后复权价(adj_close)，其已内含"分红次日自动再投"的复利效果；
    # 关闭则只用收盘价(不含分红再投)。
    if dividend_reinvest and 'adj_close' in px.columns and px['adj_close'].notna().any():
        ret_col = 'adj_close'
    else:
        ret_col = 'close'
    px = px.set_index('date')
    full_ret = px[ret_col].pct_change().dropna()
    full_ret.index = pd.to_datetime(full_ret.index)
    lo, hi = pd.to_datetime(start), pd.to_datetime(actual_end)
    full_ret = full_ret[(full_ret.index >= lo) & (full_ret.index <= hi)]

    # 持仓权重序列（日频，真正用仓位系统 target_weight + 完整 value_trap 对象）：再平衡日之间 forward-fill，T+1 执行
    wt = df['vt'] if 'vt' in df.columns else (df['vt_score'] if 'vt_score' in df.columns else None)
    weight_daily = _weight_daily(df['final_signal'], wt, full_ret.index, cfg)
    # P0-10: 交易成本+滑点。权重变动(|Δw|)即交易额，按单边成本扣除。
    bt_cfg = cfg.get('backtest', {})
    tc = float(bt_cfg.get('trading_cost', 0.001))
    slip = float(bt_cfg.get('slippage', 0.002))
    unit_cost = tc + slip
    weights = weight_daily.to_numpy(dtype=float)
    rets = full_ret.to_numpy(dtype=float)
    strat_equity = pd.Series(_equity_with_cost(rets, weights, unit_cost), index=full_ret.index)
    bh_equity = (1 + full_ret).cumprod()   # Buy&Hold 全程满仓

    bench = None
    bench_used = None
    bench_equity = None
    for bsym in benchmark_symbols:
        b = fetch_benchmark(bsym, start, end)
        if b is not None and len(b) > 20:
            bench = b
            bench_used = bsym
            break

    # 10年期国债无风险收益率曲线（用于收益率走势图对比）
    rf_series = None
    try:
        from valresearch.data.providers import MacroDataProvider
        bond_full = MacroDataProvider().get_bond_yield(start=start, end=end)
        if bond_full is not None and not bond_full.empty:
            bf = bond_full.copy()
            bf['date'] = pd.to_datetime(bf['date'])
            bf = bf.set_index('date').sort_index()
            rf_series = bf['cn10y'].reindex(full_ret.index, method='ffill').bfill()
    except Exception:
        rf_series = None

    _prog(0.92, '模拟资本预算模式(每年50万)…')
    # 资本预算回测：每年注入 annual_budget，比较 每月定投/策略买点/智能定投 三种模式
    price_daily = px[ret_col]
    dates_cap = price_daily.index
    reb_dates = [t.strftime('%Y-%m-%d') for t in df.index]
    reb_signal = df['final_signal'].astype(str).tolist()
    reb_pe = df['pe_pct'].astype(float).tolist() if 'pe_pct' in df.columns else [np.nan] * len(df)
    reb_dy = df['dy_pct'].astype(float).tolist() if 'dy_pct' in df.columns else [np.nan] * len(df)
    # 巴菲特模式触发：质量高 + Gordon合理PE留安全边际 + 非价值陷阱
    q = pd.to_numeric(df.get('quality'), errors='coerce') if 'quality' in df.columns else pd.Series([np.nan] * len(df))
    vt = pd.to_numeric(df.get('vt_score'), errors='coerce') if 'vt_score' in df.columns else pd.Series([np.nan] * len(df))
    fr = pd.to_numeric(df.get('pe_fair_ratio'), errors='coerce') if 'pe_fair_ratio' in df.columns else pd.Series([np.nan] * len(df))
    gs = df.get('gordon_status') if 'gordon_status' in df.columns else pd.Series([''] * len(df))
    reb_buffett = (
        (q >= _BUFFETT_QUALITY_MIN) &
        (vt <= _BUFFETT_VTSCORE_MAX) &
        (fr.notna()) & (fr <= _BUFFETT_FAIR_RATIO_MAX)
    ).fillna(False).astype(bool).tolist()
    cap = simulate_capital_modes(price_daily, dates_cap, reb_dates, reb_signal,
                                 reb_pe, reb_dy, annual_budget,
                                 rf_yield=(rf_series.reindex(dates_cap, method='ffill').bfill()
                                           if rf_series is not None else None),
                                 reb_buffett=reb_buffett)

    def _mode_metrics(m):
        s = m['value']
        final = float(s.iloc[-1])
        inv = m['invested']
        total_ret = round(final / inv - 1.0, 4) if inv > 0 else None
        runmax = s.cummax()
        mdd = round(float((s / runmax - 1.0).min()), 4) if (runmax > 0).any() else None
        return {'期末资产': round(final, 2), '累计投入': round(inv, 2),
                '总收益率': total_ret, '最大回撤': mdd}

    modes_metrics = {k: _mode_metrics(v) for k, v in cap.items()}
    # 对齐到 full_ret.index（与图中其它曲线同一 x 轴）
    cap_plot = {k: [round(float(x), 2) for x in v['value'].reindex(full_ret.index).tolist()]
                for k, v in cap.items()}

    res = {
        'ok': True,
        'symbol': symbol, 'mode': mode, 'start': start, 'end': actual_end,
        'rebalance_freq': freq,
        'allow_sell': bool(bt_cfg.get('allow_sell', True)),
        'dividend_reinvest': bool(dividend_reinvest),
        'budget': float(annual_budget),
        'strategy': perf_metrics(strat_equity, bench['close'] if bench is not None else None),
        'buy_and_hold': perf_metrics(bh_equity),
        'benchmark_symbol': bench_used,
        'signal_counts': df['final_signal'].value_counts().to_dict(),
        'avg_quality': round(float(df['quality'].mean()), 1) if 'quality' in df else None,
        'avg_score': round(float(df['score'].mean()), 1) if 'score' in df else None,
        'modes': modes_metrics,
        'notes': [
            ('只买不卖模式(allow_sell=false)：模型仅用于判断买点，权重只增不减，卖出信号仅阻止新增买入。'
             if not bt_cfg.get('allow_sell', True) else
             '策略按真实仓位系统(target_weight)持仓并归一化到单股上限(max_position)做单股择时仓位，未满仓；已按单边成本(交易费率+滑点)计调仓摩擦。'),
            ('红利再投(默认开启)：使用"后复权价"计算收益，已内含"分红次日自动再投"的复利效果；'
             if dividend_reinvest else
             '红利再投已关闭：仅用收盘价计算收益，不含分红再投。'),
            ('资本预算：每年 %.0f 元，比较四种建仓模式——每月定投 / 策略买点(信号触发一次买完) / 智能定投(按估值分位动态调节每月金额) / 巴菲特模式(质量高+Gordon安全边际+非陷阱才买，低估区分批、持有 forever)。'
             % annual_budget),
            ('闲置现金自动买入10Y国债按日复利计息（买点/定投触发时连本带息换股）；等待期间不再白白闲置。'),
            ('基准窗口提示: 中证红利(sh000922/923)等指数约2019年起，与个股10年分位窗口不一致，收益对比口径不同。'
             if bench_used and bench_used != 'sh000300' else
             '沪深300基准窗口与个股基本一致。'),
        ],
        'plot': {
            'dates': [d.strftime('%Y-%m-%d') for d in full_ret.index],
            'reb_dates': reb_dates,
            'reb_signal': reb_signal,
            'price_norm': [round(float(x), 4) for x in
                           (px[ret_col].reindex(full_ret.index).ffill()
                            / px[ret_col].reindex(full_ret.index).ffill().iloc[0]).tolist()],
            'strat_equity': [round(float(x), 4) for x in strat_equity.tolist()],
            'bh_equity': [round(float(x), 4) for x in bh_equity.tolist()],
            'weight': [round(float(x), 4) for x in weights.tolist()],
            'benchmark_symbol': bench_used,
            'benchmark_equity': ([round(float(x), 4) for x in bench_equity.tolist()]
                                 if bench_equity is not None else None),
            'rf_yield': ([None if pd.isna(x) else round(float(x), 3) for x in rf_series.tolist()]
                         if rf_series is not None else None),
            'mode_monthly': cap_plot['monthly'],
            'mode_strategy': cap_plot['strategy'],
            'mode_smart': cap_plot['smart'],
            'mode_buffett': cap_plot['buffett'],
        },
    }
    if bench is not None:
        bm = bench.copy()
        bm['date'] = pd.to_datetime(bm['date'])
        bm = bm.set_index('date').sort_index()
        bench_ret = bm['close'].pct_change().dropna()
        bm_ret = bench_ret.reindex(full_ret.index).ffill().fillna(0.0)
        bench_equity = (1 + bm_ret).cumprod()
        res['benchmark_metrics'] = perf_metrics(bench_equity)
    _prog(1.0, '回测完成')
    return res