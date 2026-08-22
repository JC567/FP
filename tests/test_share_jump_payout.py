# -*- coding: utf-8 -*-
"""测试分红持续性的股本跳变修正（dividend_sust.py P1-9 增强）+ allow_sell 回测参数。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import numpy as np
from valresearch.fundamental.dividend_sust import dividend_sustainability


def _fin(eps_list, np_list, yrs):
    """构造 fin 年报数据：所有公告日都设为当年+1年4-30（t取次年6月即可全部可见）。"""
    return pd.DataFrame({
        'report_period': [f'{y}-12-31' for y in yrs],
        'announcement_date': [f'{y+1}-04-30' for y in yrs],
        'announcement_date_source': ['ESTIMATED'] * len(yrs),
        'eps_basic': eps_list, 'net_profit_attr': np_list,
        'revenue': [None]*len(yrs), 'ocf': [None]*len(yrs),
        'total_assets': [None]*len(yrs), 'total_liabilities': [None]*len(yrs),
        'int_bearing_debt': [None]*len(yrs), 'data_source': ['ths']*len(yrs),
    })


def _div(dps_list, yrs, imp_yrs):
    """构造分红数据：report_period=年报，implement_date 在指定年份。"""
    return pd.DataFrame({
        'report_period': [f'{y}年报' for y in yrs],
        'implement_date': [f'{im}-07-01' for im in imp_yrs],
        'per_share_cash': dps_list,
    })


def test_share_jump_false_positive_fixed():
    """600887 式场景：EPS 被追溯稀释（隐含股本翻倍），DPS 按旧股本支付，
    旧方法 ratio=117.6% 假阳性，新方法修正为 ~56%。"""
    # NP 恒定 100亿；2014 年 EPS 从 1.0 被追溯为 0.5（隐含股本翻倍：100亿/0.5=200亿 vs 100亿/1.0=100亿）
    fin = _fin(
        eps_list=[1.0, 0.5, 0.5, 0.5],
        np_list=[100e8, 100e8, 100e8, 100e8],
        yrs=[2013, 2014, 2015, 2016],
    )
    div = _div([0.80, 0.45, 0.50, 0.55], [2014, 2015, 2016, 2017],
               [2015, 2016, 2017, 2018])
    t = '2018-06-30'
    r = dividend_sustainability(div, fin, t)
    # 旧方法 2014: 0.80/0.5=160% 假阳性
    # 新方法 2014: DPS=0.80, implied_2014=200亿, implied_2013=100亿, 跳变>20%→取min=100亿
    #   ratio=0.80*100亿/100亿=80% (<100%, 正确)
    assert r['unsustainable'] is False, f'股本跳变假阳性未修正: unsustainable={r["unsustainable"]}'
    assert '2014' in r['share_jump_years'], '应检测到 2014 股本跳变'
    print('test_share_jump_false_positive_fixed OK')


def test_genuine_overpay_still_detected():
    """真实分红率 >100% 仍应触发。"""
    fin = _fin(
        eps_list=[1.0, 1.0, 1.0, 1.0],
        np_list=[100e8, 100e8, 100e8, 100e8],
        yrs=[2013, 2014, 2015, 2016],
    )
    # 2016 年度分红 1.50/股 → 1.50/1.0 = 150% 真实超额
    div = _div([0.80, 0.90, 1.00, 1.50], [2013, 2014, 2015, 2016],
               [2014, 2015, 2016, 2017])
    t = '2018-06-30'
    r = dividend_sustainability(div, fin, t)
    assert r['unsustainable'] is True, f'真实超额分红率未检出: unsustainable={r["unsustainable"]}'
    assert any('分红率' in f or 'payout' in f.lower() for f in r['flags'])
    print('test_genuine_overpay_still_detected OK')


def test_stable_shares_unchanged():
    """股本稳定时，新旧方法代数等价：ratio = DPS/EPS（无修正）。"""
    fin = _fin(
        eps_list=[1.2, 1.3, 1.4, 1.5],
        np_list=[120e8, 130e8, 140e8, 150e8],
        yrs=[2013, 2014, 2015, 2016],
    )
    div = _div([0.60, 0.65, 0.70, 0.75], [2013, 2014, 2015, 2016],
               [2014, 2015, 2016, 2017])
    t = '2018-06-30'
    r = dividend_sustainability(div, fin, t)
    # 所有年份无跳变，ratio = DPS/EPS: 0.5, 0.5, 0.5, 0.5
    assert r['share_jump_years'] == [], f'不应检测到股本跳变: {r["share_jump_years"]}'
    assert r['avg_payout_5y'] is not None
    assert abs(r['avg_payout_5y'] - 0.50) < 0.01, f'avg_payout_5y 不符: {r["avg_payout_5y"]}'
    assert r['unsustainable'] is False
    print('test_stable_shares_unchanged OK')


if __name__ == '__main__':
    test_share_jump_false_positive_fixed()
    test_genuine_overpay_still_detected()
    test_stable_shares_unchanged()
    print('== 股本跳变修正 + 分红率检测 全部通过 ==')
