# -*- coding: utf-8 -*-
"""Phase 2 单元测试：Point-in-Time 机制 + 数据质量检查 + 严禁未来函数。

覆盖规格测试：Test3(未来财报不入历史)、Test7(除权除息不使股息率失真) 的 PIT 部分。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from valresearch.data.pit import eps_ttm_asof, dps_ttm_asof, price_asof, PitLayer
from valresearch.data import quality


def build_fin():
    # 报告期, 公告日, EPS
    return pd.DataFrame({
        'report_period': ['2023-03-31', '2023-06-30', '2023-09-30', '2023-12-31',
                          '2024-03-31', '2024-06-30', '2024-09-30', '2024-12-31',
                          '2025-03-31', '2025-06-30', '2025-09-30', '2025-12-31'],
        'announcement_date': ['2023-04-30', '2023-08-31', '2023-10-31', '2024-04-30',
                              '2024-04-30', '2024-08-31', '2024-10-31', '2025-04-30',
                              '2025-04-30', '2025-08-31', '2025-10-31', '2026-04-30'],
        'eps_basic': [0.3, 0.9, 1.5, 2.0, 0.4, 1.0, 1.5, 2.4, 0.5, 1.3, 2.0, 3.0],
    })


def test_eps_ttm_annual():
    fin = build_fin()
    # 2025-05-01: 2024年报(2025-04-30)与2025Q1(2025-04-30)均已公告 → 用最新Q1外推: 0.5+2.4-0.4=2.5
    v, w = eps_ttm_asof(fin, '2025-05-01')
    assert round(v,6)==2.5, v
    # 2025-04-25: 2024年报与2025Q1均未公告 → 用2024Q3外推: 1.5+2.0-1.5=2.0
    v, _ = eps_ttm_asof(fin, '2025-04-25')
    assert round(v,6)==2.0, v
    print('test_eps_ttm_annual OK')


def test_eps_ttm_sequential():
    fin = build_fin()
    # 2025-05-05: 2025Q1公告, EPS_TTM = 0.5 + 2.4 - 0.4 = 2.5
    v, w = eps_ttm_asof(fin, '2025-05-05')
    assert round(v,6)==2.5, v
    # 2025-11-05: 2025Q3公告, EPS_TTM = 2.0 + 2.4 - 1.5 = 2.9
    v, _ = eps_ttm_asof(fin, '2025-11-05')
    assert round(v,6)==2.9, v
    print('test_eps_ttm_sequential OK')


def test_no_future_function():
    # 未来财报(2026-04-30公告的2025年报)不得进入 2026-04-01 的分析
    fin = build_fin()
    v, _ = eps_ttm_asof(fin, '2026-04-01')
    # 应为 2025Q3外推: 2.0 + 2.4 - 1.5 = 2.9, 而非2025年报3.0
    assert round(v,6)==2.9, v
    print('test_no_future_function OK')


def test_dps_ttm():
    div = pd.DataFrame({
        'report_period': ['2023年报', '2024半年报', '2024年报', '2025半年报'],
        'implement_date': ['2024-06-20', '2024-09-10', '2025-07-01', '2026-01-05'],
        'per_share_cash': [1.0, 0.5, 1.2, 0.6],
    })
    # 2025-08-01: 近12月(2024-08-01~2025-08-01)已实施 = 2024半年报0.5 + 2024年报1.2 = 1.7
    v, _ = dps_ttm_asof(div, '2025-08-01')
    assert v == 1.7, v
    # 2024-10-01: 近12月 = 2023年报1.0 + 2024半年报0.5 = 1.5
    v, _ = dps_ttm_asof(div, '2024-10-01')
    assert v == 1.5, v
    print('test_dps_ttm OK')


def test_price_asof():
    price = pd.DataFrame({'date': ['2024-01-05', '2024-01-10', '2024-01-15'],
                          'close': [10.0, 10.5, 11.0]})
    assert price_asof(price, '2024-01-10') == 10.5
    assert price_asof(price, '2024-01-09') == 10.0
    print('test_price_asof OK')


def test_pit_layer_snapshot():
    price = pd.DataFrame({'date': ['2025-05-05', '2025-05-06'], 'close': [10.0, 10.2]})
    layer = PitLayer('X', price=price, fin=build_fin(), div=pd.DataFrame({
        'report_period': ['2024年报'], 'implement_date': ['2025-07-01'],
        'per_share_cash': [1.2]}))
    snap = layer.asof('2025-05-06')
    assert snap.price == 10.2
    assert snap.eps_ttm == 2.5   # 2025Q1外推
    # P0-4: 实施日在 t 之后的分红不得计入(无未来函数)；窗口内无分红 → DPS_TTM=0(真实0%)
    assert snap.dps_ttm == 0.0
    assert snap.dividend_yield == 0.0
    print('test_pit_layer_snapshot OK')


def test_quality():
    price = pd.DataFrame({'date': ['2024-01-05', '2024-01-05'], 'close': [10.0, 10.1]})
    w = quality.check_price(price)
    assert any('重复日期' in x for x in w), w
    pe = pd.DataFrame({'date': ['2024-01-05'], 'pe_ttm': [-5.0]})
    w = quality.check_pe(pe)
    assert any('负/零PE' in x for x in w), w
    assert quality.hard_block(['财报数据缺失(DATA_QUALITY_WARNING)']) is True
    assert quality.hard_block(['负/零PE样本 1 个']) is False
    print('test_quality OK')


if __name__ == '__main__':
    test_eps_ttm_annual()
    test_eps_ttm_sequential()
    test_no_future_function()
    test_dps_ttm()
    test_price_asof()
    test_pit_layer_snapshot()
    test_quality()
    print('== Phase 2 全部通过 ==')