# -*- coding: utf-8 -*-
"""P0-6 Gordon 可持续增长率测试：g = ROE×(1-payout)。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

from valresearch.valuation import gordon as gg


def test_sustainable_growth_formula():
    assert abs(gg.sustainable_growth(0.15, 0.3) - 0.105) < 1e-9, 'ROE15%×(1-30%)=10.5%'
    assert gg.sustainable_growth(0.15, 1.0) is None, '全分红→无留存→g<=0→None'
    assert gg.sustainable_growth(None, 0.3) is None
    assert gg.sustainable_growth(0.15, None) is None
    assert gg.sustainable_growth(0.15, 1.2) is None, 'payout>1非法'
    print('test_sustainable_growth_formula OK')


def test_roe_from_financials():
    fin = pd.DataFrame({
        'report_period': ['2024-12-31', '2023-12-31'],
        'announcement_date': ['2025-04-30', '2024-04-30'],
        'eps_basic': [1.0, 0.9],
        'net_profit_attr': [10e8, 9e8],
        'total_assets': [100e8, 90e8],
        'total_liabilities': [40e8, 36e8],
        'revenue': [None, None], 'ocf': [None, None], 'int_bearing_debt': [None, None],
    })
    roe = gg.roe_from_financials(fin)
    assert roe is not None and abs(roe - (10e8 / (100e8 - 40e8))) < 1e-9, 'ROE=10/60=16.7%'
    fin_bad = fin.copy()
    fin_bad['total_liabilities'] = None
    assert gg.roe_from_financials(fin_bad) is None, '缺负债不可算ROE'
    print('test_roe_from_financials OK: roe=%.4f' % roe)


def test_compute_growth_uses_sustainable():
    fin = pd.DataFrame({
        'report_period': ['2024-12-31', '2023-12-31', '2022-12-31'],
        'announcement_date': ['2025-04-30', '2024-04-30', '2023-04-30'],
        'eps_basic': [1.0, 0.8, 0.64],
        'net_profit_attr': [10e8, 8e8, 6.4e8],
        'total_assets': [100e8, 90e8, 80e8],
        'total_liabilities': [40e8, 36e8, 32e8],
        'revenue': [None, None, None], 'ocf': [None, None, None],
        'int_bearing_debt': [None, None, None],
    })
    # payout=0.5 → sustainable = ROE×0.5；历史EPS CAGR=(1/0.64)^(1/2)-1=25%
    g, sources = gg.compute_growth(fin, 0.5, cfg={'gdp_growth': 0.05, 'industry_growth': 0.05})
    assert sources['roe'] is not None, '应有ROE'
    expected_sus = sources['roe'] * 0.5
    assert abs(sources['sustainable'] - expected_sus) < 1e-9, 'sustainable=ROE×(1-payout)'
    assert g is not None and g <= expected_sus + 1e-9, 'g应≤可持续增速'
    print('test_compute_growth_uses_sustainable OK: sustainable=%.4f g=%.4f' % (sources['sustainable'], g))


if __name__ == '__main__':
    test_sustainable_growth_formula()
    test_roe_from_financials()
    test_compute_growth_uses_sustainable()
    print('== P0-6 Gordon 可持续增长 全部通过 ==')