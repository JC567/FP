# -*- coding: utf-8 -*-
"""P0-5b EPS口径分红率(dividend_rank._compute_eps_payout_ratios)回归测试。

修复点：div_hist.report_date 形如 '2025年报'，SUBSTR(...,1,4) 得到字符串 '2025'，
而 fin_np.year 是整数 2025；两者直接 merge 会因类型不匹配抛 ValueError，
被 try/except 吞掉导致整列返回空。修复用 CAST(... AS INTEGER)。

本测试固定锁定该回归：对 605368 必须返回非空且为 102.56%（0.40/0.39*100）。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import dividend_rank as dr


def test_eps_payout_year_type_merge():
    """year 列类型不一致曾导致 merge 失败、整列返回空。"""
    res = dr._compute_eps_payout_ratios(['605368'])
    assert '605368' in res, '605368 必须返回非空 EPS 分红率'
    val = res['605368']
    assert pd.notna(val), 'EPS 分红率不应为 NA'
    # 2025: 每股分红合计 0.40, EPS 0.39 → 102.56%
    assert abs(val - 102.56) < 0.01, f'605368 EPS 分红率应为 102.56，实际 {val}'
    print(f'test_eps_payout_year_type_merge OK: 605368={val}%')


def test_eps_payout_returns_dict_for_many():
    """批量调用应返回 dict，且对存在的股票给出数值。"""
    codes = ['605368', '600519', '000001']
    res = dr._compute_eps_payout_ratios(codes)
    assert isinstance(res, dict)
    for c in codes:
        if c in res:
            assert pd.notna(res[c]) and res[c] > 0, f'{c} 的 EPS 分红率应 > 0'
    print('test_eps_payout_returns_dict_for_many OK')


if __name__ == '__main__':
    test_eps_payout_year_type_merge()
    test_eps_payout_returns_dict_for_many()
    print('== P0-5b EPS口径分红率 全部通过 ==')
