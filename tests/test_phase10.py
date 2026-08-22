# -*- coding: utf-8 -*-
"""Phase 10 回测测试。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd
from valresearch.backtest.metrics import metrics as perf, win_rate
from valresearch.backtest import re_evaluate, run_backtest
from valresearch.backtest.engine import _invest_daily, _weight_daily, _equity_with_cost
from valresearch.config import get_config


def test_invest_daily_forward_fill():
    """再平衡日为周末(非交易日)，须映射到最近交易日，否则策略收益恒为0。"""
    sundays = pd.date_range('2024-01-07', periods=4, freq='W')   # 每周日
    sig = pd.Series(['HOLD', 'BUY', 'HOLD', 'ACCUMULATE'], index=sundays)
    # 构造每个周日后的下一个交易日（周一）
    mondays = sundays + pd.Timedelta(days=1)
    daily = pd.DatetimeIndex(sorted(mondays.tolist() + (sundays + pd.Timedelta(days=2)).tolist()))
    inv = _invest_daily(sig, daily)
    # 周一应继承上周日信号：BUY/ACCUMULATE=True
    assert bool(inv.loc[mondays[1]]) is True
    assert bool(inv.loc[mondays[2]]) is False     # HOLD
    assert bool(inv.loc[mondays[3]]) is True      # ACCUMULATE
    assert inv.dtype == bool
    print('test_invest_daily_forward_fill OK:', dict(zip(daily.strftime('%m-%d'), inv.astype(int))))


def test_invest_daily_t_plus_1_no_same_day():
    """P0-8: 信号决策日当天不得实现其自身收益(T+1 执行，无同日收盘价前视)。"""
    # 场景1：决策日恰为交易日(周三)，不得实现当天收益，次日起生效
    daily = pd.bdate_range('2024-01-08', '2024-01-12')          # 周一至周五
    sig = pd.Series(['BUY'], index=[pd.Timestamp('2024-01-10')]) # 周三决策
    inv = _invest_daily(sig, daily)
    assert bool(inv.loc['2024-01-10']) is False, '决策日当天不持仓(无同日收益)'
    assert bool(inv.loc['2024-01-11']) is True,  '次日(T+1)起生效'
    assert bool(inv.loc['2024-01-12']) is True
    # 场景2：决策日为周日(非交易日)，basis=上周五，持仓自下周一(T+1)生效
    daily2 = pd.bdate_range('2024-01-08', '2024-01-16')         # 覆盖到下周一
    sunday_sig = pd.Series(['ACCUMULATE'], index=[pd.Timestamp('2024-01-14')])  # 周日
    inv2 = _invest_daily(sunday_sig, daily2)
    assert bool(inv2.loc['2024-01-12']) is False, '上周五(决策依据日)不持仓'
    assert bool(inv2.loc['2024-01-15']) is True,  '下周一(T+1)起生效'
    print('test_invest_daily_t_plus_1_no_same_day OK')


def test_weight_daily_uses_position_system():
    """P0-9/P1-8/P0-E: 回测用 target_weight 归一化到单股上限，并传完整 value_trap 对象做陷阱修正。"""
    cfg = get_config('balanced')
    cap = float(cfg['backtest'].get('max_position', 0.10)) or 0.10
    daily = pd.bdate_range('2024-01-08', '2024-01-16')
    sig = pd.Series(['BUY', 'ACCUMULATE'], index=[pd.Timestamp('2024-01-10'),
                                                  pd.Timestamp('2024-01-14')])
    # P0-E: 传完整 value_trap 对象
    vt = pd.Series([{'score': 0.0, 'level': 'LOW', 'penalty': 0.0},
                    {'score': 0.0, 'level': 'LOW', 'penalty': 0.0}], index=sig.index)
    w = _weight_daily(sig, vt, daily, cfg)
    table = cfg['position']['table']
    buy_w = min(1.0, table['BUY'][1] / cap)
    acc_w = min(1.0, table['ACCUMULATE'][1] / cap)
    # 1-10 决策 BUY：T+1 自 1-11 起权重=buy_w（已归一化，远大于组合target_weight 4%）
    assert w.loc['2024-01-10'] == 0.0, '决策日当天0仓位'
    assert w.loc['2024-01-11'] == buy_w, f'BUY 归一化权重={buy_w}'
    # 1-14 决策 ACCUMULATE：T+1 自 1-15 起权重=acc_w
    assert w.loc['2024-01-15'] == acc_w, f'ACCUMULATE 归一化权重={acc_w}'
    assert buy_w > acc_w and acc_w > 0, '不同信号应给不同且递减的部分仓位'
    # 关键：归一化后 BUY 权重应显著高于组合级 target_weight(0.04)
    assert buy_w > table['BUY'][1], '归一化应放大单股仓位(避免常年空仓)'
    assert 0 < buy_w <= 1.0, '权重应在(0,1]内'
    # 纯多头：REDUCE/SELL 的负组合权重归一化后必须归 0，禁止做空
    sig2 = pd.Series(['REDUCE', 'SELL', 'HOLD'], index=[pd.Timestamp('2024-01-10'),
                                                       pd.Timestamp('2024-01-14'),
                                                       pd.Timestamp('2024-01-15')])
    vt2 = pd.Series([{'score': 0.0, 'level': 'LOW', 'penalty': 0.0}] * 3, index=sig2.index)
    w2 = _weight_daily(sig2, vt2, daily, cfg)
    assert (w2 >= 0).all() and w2.max() == 0.0, 'REDUCE/SELL/HOLD 不得产生任何(做空)仓位'
    # P0-E: 高价值陷阱(score>=60)会压降仓位，>=80 归0 —— 证明传的是完整对象而非重造LOW/penalty=0
    sig3 = pd.Series(['BUY', 'BUY'], index=[pd.Timestamp('2024-01-08'), pd.Timestamp('2024-01-12')])
    vt3 = pd.Series([{'score': 0.0, 'level': 'LOW', 'penalty': 0.0},
                     {'score': 85.0, 'level': 'VERY_HIGH', 'penalty': 0.6}], index=sig3.index)
    w3 = _weight_daily(sig3, vt3, daily, cfg)
    assert w3.loc['2024-01-11'] == buy_w, '陷阱低时正常仓位'
    assert w3.loc['2024-01-15'] == 0.0, '陷阱极高(>=80)应强制归0仓位(完整vt对象生效)'
    print('test_weight_daily_uses_position_system OK: buy=%s acc=%s' % (buy_w, acc_w))


def test_equity_with_cost_reduces_returns():
    """P0-10: 调仓摩擦成本(交易费率+滑点)须按 |Δ权重| 扣除，带成本净值<=无成本净值。"""
    rets = np.array([0.01, 0.01, 0.01, 0.01])
    weights = np.array([0.0, 0.5, 0.5, 0.0])     # 入场与离场各一次调仓
    unit = 0.003                                  # 千一+千二
    eq_cost = _equity_with_cost(rets, weights, unit)
    eq_no = np.cumprod(1 + rets * weights)
    # 名义成本= |0-0.5|*unit + |0.5-0|*unit = 0.003；因成本随净值复利，实际扣减略高于此
    diff = eq_no[-1] - eq_cost[-1]
    assert eq_cost[-1] < eq_no[-1], '带成本净值应更低'
    assert (0.5 + 0.5) * unit <= diff < (0.5 + 0.5) * unit * 1.05, '成本≈Σ|Δw|×unit'
    print('test_equity_with_cost_reduces_returns OK: cost_equity=%.5f no_cost=%.5f diff=%.5f'
          % (eq_cost[-1], eq_no[-1], diff))


def test_metrics_synthetic():
    eq = pd.Series(1.0 + np.linspace(0, 1.0, 253))  # 简单上升
    m = perf(eq, periods_per_year=252)
    assert m['cagr'] is not None and m['cagr'] > 0
    assert m['final_value'] > 1.0
    assert m['max_drawdown'] <= 0
    # 有回撤的情况
    eq2 = pd.Series([1.0, 1.2, 0.9, 1.1, 1.3])
    m2 = perf(eq2, periods_per_year=252)
    assert m2['max_drawdown'] < 0
    print('test_metrics_synthetic OK', m['cagr'], m['max_drawdown'])


def test_win_rate():
    sig = pd.Series([1, 0, 1, 0, 1])
    ret = pd.Series([0.02, -0.01, 0.03, -0.02, 0.01])
    w = win_rate(sig, ret)
    assert w['active_periods'] == 3 and w['inactive_periods'] == 2
    assert w['active_mean_ret'] == 0.02
    print('test_win_rate OK', w)


def test_re_evaluate_smoke():
    cfg = get_config('balanced')
    df = re_evaluate('600036', '2024-06-01', '2025-06-30', 'balanced', cfg)
    assert not df.empty
    for col in ('price', 'pe_pct', 'dy_pct', 'pr_pct', 'final_signal', 'score'):
        assert col in df.columns
    assert df['final_signal'].isin(['STRONG_BUY', 'BUY', 'ACCUMULATE', 'HOLD',
                                    'WAIT', 'REDUCE', 'SELL']).all()
    print('test_re_evaluate_smoke OK rows=%d' % len(df))


def test_run_backtest_smoke():
    cfg = get_config('balanced')
    res = run_backtest('600036', '2024-06-01', '2025-06-30', 'balanced', cfg,
                       benchmark_symbols=('sh000300',))
    assert res['ok']
    assert 'strategy' in res and 'cagr' in res['strategy']
    assert 'benchmark_metrics' in res
    assert res['signal_counts']
    print('test_run_backtest_smoke OK: strat_cagr=%s bh=%s bench=%s'
          % (res['strategy'].get('cagr'), res['buy_and_hold'].get('cagr'),
             res.get('benchmark_metrics', {}).get('cagr')))


if __name__ == '__main__':
    test_metrics_synthetic()
    test_win_rate()
    test_invest_daily_forward_fill()
    test_invest_daily_t_plus_1_no_same_day()
    test_weight_daily_uses_position_system()
    test_equity_with_cost_reduces_returns()
    test_re_evaluate_smoke()
    test_run_backtest_smoke()
    print('== Phase 10 全部通过 ==')