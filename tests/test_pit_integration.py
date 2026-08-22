# -*- coding: utf-8 -*-
"""P0-G + 二十五：真正的 PIT 集成测试 / 未来数据注入攻击。

不是"公式单元测试"，而是端到端验证：
    在某历史时点 asof 用当前可得数据算出完整结果（PE/Gordon/ROE/Quality/Banking/Dividend/
    ValueTrap/FinalSignal/Score/Position），然后向数据库"疯狂注入"未来 N 年数据
    （EPS/净利/ROE/资产/负债/分红/修订财报 + 未来价格），
    重新在同一 asof 计算 —— 任何一项变化都判定为未来函数(BUG)。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

from valresearch.config import get_config
from valresearch.valuation import engine, gordon as gg
from valresearch.backtest.engine import _signal_at
from valresearch.fundamental.quality_score import quality_score
from valresearch.fundamental.banking import banking_quality
from valresearch.fundamental.dividend_sust import dividend_sustainability
from valresearch.risk.value_trap import value_trap_score
from valresearch.signal.position import position_plan


def _cfg():
    return get_config('balanced')


def _base_dataset(end='2025-12-31'):
    """基础数据集：2014~2019年报(2020年中前公告) + 分红 + 价格。银行行业路径。"""
    dates = pd.bdate_range('2014-01-01', end)
    price = pd.DataFrame({'date': dates, 'close': np.linspace(8.0, 14.0, len(dates)),
                          'adj_close': np.linspace(8.0, 14.0, len(dates))})
    yrs = list(range(2013, 2020))
    fin = pd.DataFrame({
        'report_period': [f'{y}-12-31' for y in yrs],
        'announcement_date': [f'{y+1}-04-30' for y in yrs],
        'announcement_date_source': ['ESTIMATED'] * len(yrs),
        'eps_basic': [0.5 + 0.1 * (i) for i in range(len(yrs))],     # 2013:0.5 → 2019:1.1
        'net_profit_attr': [50e8 + 10e8 * i for i in range(len(yrs))],
        'revenue': [800e8 + 100e8 * i for i in range(len(yrs))],
        'ocf': [None] * len(yrs),
        'total_assets': [3000e8 + 300e8 * i for i in range(len(yrs))],
        'total_liabilities': [2700e8 + 270e8 * i for i in range(len(yrs))],
        'int_bearing_debt': [None] * len(yrs),
        'data_source': ['ths'] * len(yrs),
    })
    div = pd.DataFrame({
        'report_period': [f'{y}年报' for y in yrs[:-1]],
        'implement_date': [f'{y+1}-07-01' for y in yrs[:-1]],
        'per_share_cash': [0.3] * (len(yrs) - 1),
    })
    bond = pd.DataFrame({'date': pd.bdate_range('2014-01-01', end), 'cn10y': 0.025})
    ind = {'industry': '银行', 'industry_type': '银行'}
    return price, fin, div, bond, ind


def _inject_future(price, fin, div):
    """二十五：疯狂注入未来5年数据（EPS/净利/资产/负债/分红/修订财报 + 未来价格）。"""
    price2 = pd.concat([price, pd.DataFrame({
        'date': pd.bdate_range('2026-01-01', '2030-12-31'),
        'close': np.linspace(100.0, 500.0, len(pd.bdate_range('2026-01-01', '2030-12-31'))),
        'adj_close': np.linspace(100.0, 500.0, len(pd.bdate_range('2026-01-01', '2030-12-31'))),
    })], ignore_index=True).sort_values('date').reset_index(drop=True)
    # 未来5年财报(2020~2024年报) + 未来修订(对过去报告期的 restated，公告日在未来)
    rows = []
    for y in range(2020, 2025):
        rows.append({'report_period': f'{y}-12-31', 'announcement_date': f'{y+1}-04-30',
                     'announcement_date_source': 'ESTIMATED', 'eps_basic': 99.0,
                     'net_profit_attr': 999e8, 'revenue': 9999e8, 'ocf': None,
                     'total_assets': 99999e8, 'total_liabilities': 50000e8,
                     'int_bearing_debt': None, 'data_source': 'ths'})
    # 修订财报：对 2017/2018/2019 报告期的 restated，公告日在 2022 之后（未来）
    for y in (2017, 2018, 2019):
        rows.append({'report_period': f'{y}-12-31', 'announcement_date': '2023-06-30',
                     'announcement_date_source': 'ESTIMATED', 'eps_basic': 77.0,
                     'net_profit_attr': 777e8, 'revenue': 7777e8, 'ocf': None,
                     'total_assets': 77777e8, 'total_liabilities': 30000e8,
                     'int_bearing_debt': None, 'data_source': 'ths'})
    fin2 = pd.concat([fin, pd.DataFrame(rows)], ignore_index=True)
    div2 = pd.concat([div, pd.DataFrame({
        'report_period': [f'{y}年报' for y in range(2020, 2025)],
        'implement_date': [f'{y+1}-07-01' for y in range(2020, 2025)],
        'per_share_cash': [9.9] * 5,
    })], ignore_index=True)
    return price2, fin2, div2


def _capture(t, price, fin, div, bond, ind, cfg):
    """同一 asof 的完整信号/仓位快照。"""
    t = pd.Timestamp(t)
    ser = engine.build_series(price, None, fin, div, window_years=11, end=t)
    assert ser is not None, 'asof 处应有数据'
    r = _signal_at(t, ser, price, fin, div, bond, ind, '银行', cfg)
    assert r is not None, 'asof 处应能算出信号'
    roe = gg.roe_from_financials(fin, t)
    payout_dec = (r['pr_pct'] / 100.0) if r['pr_pct'] is not None else None
    if payout_dec is None:
        payout_dec = 0.4
    g, sources = gg.compute_growth(fin, payout_dec, t, cfg)
    banking = banking_quality(fin, div, t, '银行', cfg)['score']
    div_consec = dividend_sustainability(div, fin, t)['consecutive_years']
    pos = position_plan(r['final_signal'], r['vt'], cfg)['target_weight']
    return {
        'score': r['score'], 'final_signal': r['final_signal'],
        'quality': r['quality'], 'vt_score': r['vt_score'],
        'pe_pct': r['pe_pct'], 'dy_pct': r['dy_pct'],
        'gordon_sustainable': sources.get('sustainable'),
        'roe': roe, 'banking': banking, 'dividend_consec': div_consec,
        'position': pos,
    }


def _assert_invariant(base, injected, label):
    for k in base:
        b, i = base[k], injected[k]
        if isinstance(b, float) and isinstance(i, float) and (np.isnan(b) or np.isnan(i)):
            assert np.isnan(b) and np.isnan(i), f'{label}.{k}: NaN漂移 {b} vs {i}'
            continue
        assert b == i, f'{label}.{k}: 未来函数! 基线={b} 注入后={i}'


def test_attack_asof_2020_future_5y():
    """二十五：asof=2020-06-30，注入未来5年全部数据 + 修订财报 → 信号/分/仓位必须完全不变。"""
    cfg = _cfg()
    price, fin, div, bond, ind = _base_dataset()
    base = _capture('2020-06-30', price, fin, div, bond, ind, cfg)
    price2, fin2, div2 = _inject_future(price, fin, div)
    injected = _capture('2020-06-30', price2, fin2, div2, bond, ind, cfg)
    _assert_invariant(base, injected, 'asof=2020-06-30')
    # 证明注入是"活的"：在未来的 asof(2026-06-30) 注入数据必须被看到并改变结果，
    # 否则上面的不变只是注入无效(自欺)。2026 年 ROE 应变为主观注入值(999e8/49999e8≈0.01998)
    later_base = _capture('2026-06-30', price2, fin2, div2, bond, ind, cfg)
    assert abs(later_base['roe'] - 0.01998) < 1e-4, '2026年应看到注入的ROE(证明注入有效)'
    assert later_base['pe_pct'] != base['pe_pct'], '2026年 PE 分位应与2020基线不同(证明注入生效)'
    print('test_attack_asof_2020_future_5y OK: score=%s sig=%s pos=%s | 2026注入后score=%s'
          % (base['score'], base['final_signal'], base['position'], later_base['score']))


def test_pit_asof_2022_add_future_financials():
    """P0-G：asof=2022-06-30，加入 2023/2024/2025 财报 → 2022 信号完全不能变化。"""
    cfg = _cfg()
    # 基础数据含 2020/2021 年报(在 2022 前已公告)
    price, fin, div, bond, ind = _base_dataset(end='2025-12-31')
    extra = pd.DataFrame({
        'report_period': ['2020-12-31', '2021-12-31'],
        'announcement_date': ['2021-04-30', '2022-04-30'],
        'announcement_date_source': ['ESTIMATED'] * 2,
        'eps_basic': [1.2, 1.3], 'net_profit_attr': [120e8, 130e8],
        'revenue': [1300e8, 1400e8], 'ocf': [None] * 2,
        'total_assets': [4000e8, 4300e8], 'total_liabilities': [3600e8, 3870e8],
        'int_bearing_debt': [None] * 2, 'data_source': ['ths'] * 2,
    })
    fin = pd.concat([fin, extra], ignore_index=True)
    div_extra = pd.DataFrame({
        'report_period': ['2020年报', '2021年报'],
        'implement_date': ['2021-07-01', '2022-07-01'],
        'per_share_cash': [0.35, 0.36],
    })
    div = pd.concat([div, div_extra], ignore_index=True)

    base = _capture('2022-06-30', price, fin, div, bond, ind, cfg)

    # 注入未来 2023/2024/2025 财报（公告日在 2023+，属未来）
    future_rows = pd.DataFrame({
        'report_period': ['2022-12-31', '2023-12-31', '2024-12-31'],
        'announcement_date': ['2023-04-30', '2024-04-30', '2025-04-30'],
        'announcement_date_source': ['ESTIMATED'] * 3,
        'eps_basic': [5.0, 6.0, 7.0], 'net_profit_attr': [500e8, 600e8, 700e8],
        'revenue': [5000e8, 6000e8, 7000e8], 'ocf': [None] * 3,
        'total_assets': [50000e8, 60000e8, 70000e8],
        'total_liabilities': [40000e8, 48000e8, 56000e8],
        'int_bearing_debt': [None] * 3, 'data_source': ['ths'] * 3,
    })
    fin_fut = pd.concat([fin, future_rows], ignore_index=True)
    div_fut = pd.concat([div, pd.DataFrame({
        'report_period': ['2022年报', '2023年报', '2024年报'],
        'implement_date': ['2023-07-01', '2024-07-01', '2025-07-01'],
        'per_share_cash': [8.0, 9.0, 10.0],
    })], ignore_index=True)

    injected = _capture('2022-06-30', price, fin_fut, div_fut, bond, ind, cfg)
    _assert_invariant(base, injected, 'asof=2022-06-30')
    print('test_pit_asof_2022_add_future_financials OK: score=%s sig=%s pos=%s'
          % (base['score'], base['final_signal'], base['position']))


if __name__ == '__main__':
    test_attack_asof_2020_future_5y()
    test_pit_asof_2022_add_future_financials()
    print('== P0-G + 二十五 未来函数攻击 全部通过 ==')