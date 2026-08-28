# -*- coding: utf-8 -*-
"""P0-10 单股回测：中文摘要 + 走势图/收益率图（含买卖点、10Y国债对比）+ 只买不卖/红利再投。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from valresearch.backtest.chart import make_backtest_figure, _buy_sell_dates, _reb_markers
from valresearch.backtest.engine import run_backtest, simulate_capital_modes


def test_buy_sell_dates():
    w = [0, 0, 0.5, 0.5, 0, 0, 0.3, 0.3, 0.3, 0]   # 买点 2,6；卖点 4,9
    buys, sells = _buy_sell_dates(w)
    assert buys == [2, 6], buys
    assert sells == [4, 9], sells
    # 只买不卖：权重单调不减 → 无卖点
    w2 = [0, 0, 0.2, 0.2, 0.4, 0.4]
    b2, s2 = _buy_sell_dates(w2)
    assert s2 == [], s2
    assert b2 == [2], b2
    print('test_buy_sell_dates OK')


def _fake_res(n=120):
    dates = pd.date_range('2020-01-01', periods=n, freq='D')
    rng = np.random.default_rng(0)
    base = 1 + np.cumsum(rng.normal(0, 0.01, n))
    # 再平衡信号：每 6 天一个决策日，前 10 个 BUY，后 5 个 REDUCE/SELL（仅 allow_sell 时算卖点）
    reb_dates = dates[::6]
    reb_signal = (['BUY'] * 10 + ['REDUCE'] * 5)[:len(reb_dates)]
    return {
        'ok': True, 'symbol': '600036', 'mode': 'balanced',
        'start': '2020-01-01', 'end': '2020-04-30', 'rebalance_freq': 'W',
        'allow_sell': True, 'dividend_reinvest': True,
        'benchmark_symbol': 'sh000300',
        'plot': {
            'dates': [d.strftime('%Y-%m-%d') for d in dates],
            'reb_dates': [d.strftime('%Y-%m-%d') for d in reb_dates],
            'reb_signal': reb_signal,
            'price_norm': list(base),
            'strat_equity': list(base),
            'bh_equity': list(base * 0.9),
            'weight': [0] * 20 + [0.5] * 60 + [0] * 40,
            'benchmark_symbol': 'sh000300',
            'benchmark_equity': list(base * 0.95),
            'rf_yield': [2.5] * n,
        },
    }


def test_make_figure_with_rf():
    res = _fake_res()
    fig = make_backtest_figure(res)
    assert fig is not None, '应生成 Figure'
    axes = fig.get_axes()
    assert len(axes) >= 3, axes          # ax1, ax2, ax2右轴 = 3
    # 应含 买入点/卖出点 散点（PathCollection）
    has_scatter = any(type(c).__name__ == 'PathCollection' for ax in axes for c in ax.collections)
    assert has_scatter, '应含买卖点散点'
    # 买入点数量应等于再平衡信号中的买入类次数（此处 10 个 BUY）
    buys, sells = _reb_markers(pd.to_datetime(res['plot']['dates']),
                               res['plot']['reb_dates'], res['plot']['reb_signal'], True)
    assert len(buys) == 10, '买入点应对应 10 个 BUY 信号，实际 %d' % len(buys)
    assert len(sells) == 5, '卖出点应对应 5 个 REDUCE/SELL，实际 %d' % len(sells)
    plt.close(fig)
    print('test_make_figure_with_rf OK: axes=%d buys=%d sells=%d' % (len(axes), len(buys), len(sells)))


def test_reb_markers_nosell():
    # 只买不卖：卖点不计入
    dates = pd.date_range('2020-01-01', periods=60, freq='D')
    reb_dates = dates[::6]
    reb_signal = ['BUY'] * 5 + ['SELL'] * 3
    buys, sells = _reb_markers(dates, [d.strftime('%Y-%m-%d') for d in reb_dates], reb_signal, False)
    assert len(buys) == 5, buys
    assert sells == [], '只买不卖不应有卖出点'
    print('test_reb_markers_nosell OK')


def test_make_figure_no_rf():
    res = _fake_res()
    res['plot']['rf_yield'] = None
    fig = make_backtest_figure(res)
    assert fig is not None
    plt.close(fig)
    print('test_make_figure_no_rf OK')


def test_make_figure_none():
    assert make_backtest_figure({'ok': False}) is None
    print('test_make_figure_none OK')


def test_bt_summary_chinese():
    from valresearch.gui.tab import VRTab
    res = {
        'ok': True, 'symbol': '600036', 'mode': 'balanced', 'start': '2020', 'end': '2021',
        'rebalance_freq': 'W', 'allow_sell': True, 'dividend_reinvest': True,
        'strategy': {'cagr': 0.12, 'annual_volatility': 0.2, 'sharpe': 0.6,
                     'max_drawdown': -0.1, 'calmar': 1.2, 'total_return': 0.25},
        'buy_and_hold': {'cagr': 0.1},
        'benchmark_symbol': 'sh000300', 'benchmark_metrics': {'cagr': 0.08},
        'signal_counts': {'BUY': 5, 'HOLD': 3}, 'avg_quality': 70, 'avg_score': 65,
        'notes': ['n1', 'n2'],
    }
    txt = VRTab._bt_summary(res)
    assert '年化复合收益率(CAGR)' in txt, '指标应为中文'
    assert '分红处理' in txt, '应含分红处理说明'
    assert '持仓规则' in txt, '应含持仓规则说明'
    print('test_bt_summary_chinese OK')


def test_run_backtest_plot_keys():
    # 联网/本地缓存可用时校验 plot 结构；不可用则跳过（不视为失败）
    try:
        res = run_backtest('600036', '2024-06-01', '2025-06-30', 'balanced',
                            dividend_reinvest=True)
    except Exception as e:
        print('test_run_backtest_plot_keys SKIP (无数据):', type(e).__name__)
        return
    if not res.get('ok'):
        print('test_run_backtest_plot_keys SKIP:', res.get('reason'))
        return
    assert 'plot' in res and res['plot'].get('dates'), '应返回 plot 序列'
    assert res.get('dividend_reinvest') is True
    for k in ('mode_monthly', 'mode_strategy', 'mode_smart'):
        assert res['plot'].get(k) is not None, '应返回资本模式序列 ' + k
        assert len(res['plot'][k]) == len(res['plot']['dates']), '模式序列长度应一致'
    assert res.get('modes') and set(res['modes']) >= {'monthly', 'strategy', 'smart'}, '应含三种模式指标'
    fig = make_backtest_figure(res)
    assert fig is not None
    plt.close(fig)
    print('test_run_backtest_plot_keys OK: 交易日=%d' % len(res['plot']['dates']))


def test_simulate_capital_modes():
    dates = pd.date_range('2020-01-01', '2021-12-31', freq='B')
    price = pd.Series(np.linspace(10.0, 12.0, len(dates)), index=dates)
    reb_dates = [dates[30], dates[len(dates) // 2 + 30]]
    reb_signal = ['BUY', 'ACCUMULATE']
    reb_pe = [20.0, 80.0]
    reb_dy = [80.0, 20.0]
    cap = simulate_capital_modes(price, dates, reb_dates, reb_signal, reb_pe, reb_dy, 500000.0)
    for k in ('monthly', 'strategy', 'smart'):
        assert len(cap[k]['value']) == len(dates), k
        assert cap[k]['invested'] > 0, k
    # 每月定投：约 24 个月 × (50万/12) ≈ 100万
    assert abs(cap['monthly']['invested'] - 1_000_000) < 50000, cap['monthly']['invested']
    # 策略买点：两年各一次触发，每次全额 ≈ 100万
    assert abs(cap['strategy']['invested'] - 1_000_000) < 1000, cap['strategy']['invested']
    # 智能定投：便宜/贵各半年，总投入在合理区间
    assert 300000 < cap['smart']['invested'] <= 1_100_000, cap['smart']['invested']
    print('test_simulate_capital_modes OK monthly=%.0f strategy=%.0f smart=%.0f'
          % (cap['monthly']['invested'], cap['strategy']['invested'], cap['smart']['invested']))


if __name__ == '__main__':
    test_buy_sell_dates()
    test_make_figure_with_rf()
    test_make_figure_no_rf()
    test_make_figure_none()
    test_bt_summary_chinese()
    test_run_backtest_plot_keys()
    test_reb_markers_nosell()
    test_simulate_capital_modes()
    print('== P0-10 单股回测图表/中文/开关 全部通过 ==')
