# -*- coding: utf-8 -*-
"""P0-5 分红率严格口径与交叉验证测试。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

from valresearch.data.payout import (payout_ratio_strict, crosscheck_payout,
                                     PAYOUT_SOURCE_STRICT, PAYOUT_SOURCE_PER_SHARE)
from valresearch.data import pit


def test_strict_total():
    assert payout_ratio_strict(5e8, 10e8)[0] == 50.0, '5亿/10亿=50%'
    assert payout_ratio_strict(0.0, 10e8)[0] == 0.0, '无分红=0%'
    assert np.isnan(payout_ratio_strict(5e8, -1e8)[0]), '亏损不可算'
    assert np.isnan(payout_ratio_strict(5e8, 0.0)[0]), '零净利不可算'
    assert np.isnan(payout_ratio_strict(None, 10e8)[0]), '缺总额不可算'
    print('test_strict_total OK')


def test_crosscheck_match_and_mismatch():
    ok, status, _, _, _ = crosscheck_payout(40.0, 41.0)      # 接近 → OK
    assert ok and status == 'PAYOUT_CROSSCHECK_OK'
    ok2, status2, _, _, msg = crosscheck_payout(20.0, 80.0)  # 悬殊 → MISMATCH
    assert not ok2 and status2 == 'PAYOUT_CROSSCHECK_MISMATCH'
    assert 'PAYOUT_CROSSCHECK_MISMATCH' in msg
    ok3, status3, _, _, _ = crosscheck_payout(np.nan, 50.0)  # 每股缺失 → 不判不一致
    assert ok3 and status3 == 'PAYOUT_CROSSCHECK_INSUFFICIENT'
    print('test_crosscheck_match_and_mismatch OK')


def test_layer_sets_source_and_crosscheck():
    div = pd.DataFrame({'report_period': ['2023-12-31'], 'implement_date': ['2024-06-30'],
                        'per_share_cash': [0.5]})
    fin = pd.DataFrame({
        'report_period': ['2024-12-31'], 'announcement_date': ['2025-04-30'],
        'eps_basic': [1.0], 'revenue': [100e8], 'net_profit_attr': [10e8],
        'ocf': [None], 'total_assets': [None], 'total_liabilities': [None],
        'int_bearing_debt': [None],
    })
    layer = pit.PitLayer('TEST', price=pd.DataFrame({'date': ['2025-05-02'], 'close': [10.0]}),
                         fin=fin, div=div)
    snap = layer.asof('2025-05-02')
    # P0-D: 正式 payout=现金分红总额/归母净利；每股口径仅交叉验证
    assert snap.payout_ratio_source == PAYOUT_SOURCE_STRICT
    assert abs(snap.payout_ratio - 50.0) < 1e-9       # 0.5*10e8/10e8*100
    assert snap.payout_crosscheck is not None
    assert snap.payout_crosscheck['status'] == 'PAYOUT_CROSSCHECK_OK'
    assert abs(snap.payout_crosscheck['per_share'] - 50.0) < 1e-9
    print('test_layer_sets_source_and_crosscheck OK')


if __name__ == '__main__':
    test_strict_total()
    test_crosscheck_match_and_mismatch()
    test_layer_sets_source_and_crosscheck()
    print('== P0-5 分红率严格口径 全部通过 ==')