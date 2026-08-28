# -*- coding: utf-8 -*-
"""单股回测图表（Phase 12 增强）。

生成两张并排(上下)子图：
  · 上：走势图 —— 股价走势(归一化) + 各策略净值曲线 + 策略的买卖点(▲买入 / ▼卖出)
  · 下：收益率走势图 —— 各策略累计净值 + 10年期国债无风险收益率(%)曲线(右轴)对比
返回 matplotlib Figure（Agg 后端，纯数据、不弹窗），由 GUI 主线程嵌到 Tk。
"""
from __future__ import annotations

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'Arial Unicode MS',
                                   'Source Han Sans CN', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


def _buy_sell_dates(weight):
    """由日频权重序列识别买卖点：0→正=买入；正→0=卖出。返回 (buy_idx, sell_idx) 列表。"""
    w = np.asarray(weight, dtype=float)
    n = len(w)
    buys, sells = [], []
    for i in range(n):
        if w[i] > 0 and (i == 0 or w[i - 1] == 0):
            buys.append(i)
        elif w[i] == 0 and i > 0 and w[i - 1] > 0:
            sells.append(i)
    return buys, sells


_BUY_SET = {'BUY', 'STRONG_BUY', 'ACCUMULATE'}
_SELL_SET = {'REDUCE', 'SELL'}


def _reb_markers(dates, reb_dates, reb_signal, allow_sell):
    """按再平衡日信号序列标买卖点：每个买入类/卖出类信号均标一点（对应日志信号分布）。
    再平衡日可能落在非交易日，用 pad 映射到最近的前一个交易日序号。返回 (buy_idx, sell_idx)。"""
    di = pd.DatetimeIndex(dates)
    rd = pd.to_datetime(reb_dates)
    pos = di.get_indexer(rd, method='pad')
    buys, sells = [], []
    for p, sig in zip(pos, reb_signal):
        if p < 0:
            continue
        if sig in _BUY_SET:
            buys.append(int(p))
        elif sig in _SELL_SET and allow_sell:
            sells.append(int(p))
    return sorted(set(buys)), sorted(set(sells))


def make_backtest_figure(res: dict):
    """根据 run_backtest 返回的 dict（含 res['plot']）绘制 Figure。无 plot 数据时返回 None。"""
    plot = res.get('plot')
    if not plot or not plot.get('dates'):
        return None
    dates = pd.to_datetime(plot['dates'])
    strat = np.asarray(plot.get('strat_equity') or [], dtype=float)
    bh = np.asarray(plot.get('bh_equity') or [], dtype=float)
    price = np.asarray(plot.get('price_norm') or [], dtype=float)
    bench = np.asarray(plot.get('benchmark_equity') or [], dtype=float) if plot.get('benchmark_equity') else None
    rf = np.asarray(plot.get('rf_yield') or [], dtype=float) if plot.get('rf_yield') else None
    weight = plot.get('weight') or []

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 9), sharex=True)
    fig.subplots_adjust(hspace=0.08, left=0.08, right=0.92, top=0.93, bottom=0.10)

    sym = res.get('symbol', '')
    mode_cn = res.get('mode', '')
    budget = res.get('budget')
    title = (f"单股历史重估回测 · {sym} · {res.get('start')}~{res.get('end')} · "
             f"模式={mode_cn} · 再平衡={res.get('rebalance_freq')}\n"
             f"{'只买不卖' if not res.get('allow_sell') else '按信号买卖'} · "
             f"{'红利再投' if res.get('dividend_reinvest') else '不复投'}"
             + (f" · 每年预算{budget:.0f}元" if budget else ""))

    # ---- 上：走势图 ----
    if price.size:
        ax1.plot(dates, price, color='#9ca3af', lw=1.2, label='股价走势(归一化)')
    ax1.plot(dates, strat, color='#2563eb', lw=1.6, label='信号策略')
    ax1.plot(dates, bh, color='#f59e0b', lw=1.4, ls='--', label='买入持有')
    if bench is not None and bench.size:
        ax1.plot(dates, bench, color='#16a34a', lw=1.3, ls=':',
                 label=f"基准({plot.get('benchmark_symbol')})")

    # 买卖点：优先按再平衡日信号序列（每个买入类/卖出类信号标一点，对应日志信号分布）；
    # 缺失时回退到权重 0->正/正->0 的持仓切换检测。
    reb_dates = plot.get('reb_dates')
    reb_signal = plot.get('reb_signal')
    if reb_dates and reb_signal:
        buys, sells = _reb_markers(dates, reb_dates, reb_signal, bool(res.get('allow_sell')))
    else:
        buys, sells = _buy_sell_dates(weight)
    if buys:
        ax1.scatter(dates[buys], strat[buys], marker='^', color='#22c55e', s=70,
                    zorder=5, label='买入点')
    if sells:
        ax1.scatter(dates[sells], strat[sells], marker='v', color='#ef4444', s=70,
                    zorder=5, label='卖出点')

    ax1.set_title(title, fontsize=11)
    ax1.set_ylabel('净值(起点=1)', fontsize=9)
    ax1.legend(loc='upper left', fontsize=8, ncol=2)
    ax1.grid(True, ls=':', alpha=0.5)

    # ---- 下：收益率走势图（资本预算各模式对比）----
    mode_monthly = (np.asarray(plot.get('mode_monthly'), dtype=float)
                    if plot.get('mode_monthly') else None)
    mode_strategy = (np.asarray(plot.get('mode_strategy'), dtype=float)
                     if plot.get('mode_strategy') else None)
    mode_smart = (np.asarray(plot.get('mode_smart'), dtype=float)
                  if plot.get('mode_smart') else None)
    mode_buffett = (np.asarray(plot.get('mode_buffett'), dtype=float)
                    if plot.get('mode_buffett') else None)
    budget = res.get('budget')
    if mode_monthly is not None and mode_monthly.size:
        ax2.plot(dates, mode_monthly, color='#2563eb', lw=1.6, label='每月定投')
        if mode_strategy is not None and mode_strategy.size:
            ax2.plot(dates, mode_strategy, color='#f59e0b', lw=1.5, label='策略买点')
        if mode_smart is not None and mode_smart.size:
            ax2.plot(dates, mode_smart, color='#8b5cf6', lw=1.5, label='智能定投')
        if mode_buffett is not None and mode_buffett.size:
            ax2.plot(dates, mode_buffett, color='#0ea5e9', lw=1.7, label='巴菲特模式')
        ylabel = '资产(元)' + (f' · 每年预算{budget:.0f}' if budget else '')
        ax2.set_ylabel(ylabel, fontsize=9)
    else:
        # 回退：原净值曲线
        ax2.plot(dates, strat, color='#2563eb', lw=1.6, label='信号策略')
        ax2.plot(dates, bh, color='#f59e0b', lw=1.4, ls='--', label='买入持有')
        if bench is not None and bench.size:
            ax2.plot(dates, bench, color='#16a34a', lw=1.3, ls=':',
                     label=f"基准({plot.get('benchmark_symbol')})")
        ax2.set_ylabel('累计净值(收益率)', fontsize=9)
    ax2.grid(True, ls=':', alpha=0.5)

    if rf is not None and rf.size and not np.all(np.isnan(rf)):
        axr = ax2.twinx()
        axr.plot(dates, rf, color='#dc2626', lw=1.1, alpha=0.8,
                 label='10Y国债无风险收益率(%)')
        axr.set_ylabel('10Y国债收益率(%)', fontsize=9, color='#dc2626')
        axr.tick_params(axis='y', colors='#dc2626')
        # 合并右轴图例
        h1, l1 = ax2.get_legend_handles_labels()
        h2, l2 = axr.get_legend_handles_labels()
        ax2.legend(h1 + h2, l1 + l2, loc='upper left', fontsize=8, ncol=2)
    else:
        ax2.legend(loc='upper left', fontsize=8, ncol=2)

    ax2.set_xlabel('日期', fontsize=9)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    for lbl in ax2.get_xticklabels():
        lbl.set_rotation(30)
        lbl.set_ha('right')

    return fig
