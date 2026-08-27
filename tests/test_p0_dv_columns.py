# -*- coding: utf-8 -*-
"""P0-6 数据查看页字段调整回归测试。

要求：
1) 去掉 EPS分红率、昨日分红率 列
2) 最新分红率 改名为 最新价格去年分红率
3) 最新分红率_raw 紧随 最新价格去年分红率 之后
4) 最新分红率_raw = 近12月(TTM)现金股息总和 ÷ 当前股价 × 100
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import run_task as rt


def _sample_df():
    return pd.DataFrame({
        '排名': [1, 2],
        '代码': ['605368', '600519'],
        '名称': ['X', 'Y'],
        '最新分红率': [5.0, 2.0],
        '昨日分红率': [4.8, 1.9],
        'EPS分红率': [102.56, 50.0],
        '当前PE': [10.0, 30.0],
        '每股分红合计': [0.85, 1.0],
        '最新价': [7.13, 1700.0],
    })


def test_columns_dropped_and_renamed_and_ordered():
    df = _sample_df()
    ttm_map = {'605368': 0.40, '600519': 30.0}   # 近12月现金股息总和
    out = rt.TaskApp._prepare_data_view(df, ttm_map)
    cols = list(out.columns)
    # 1) EPS分红率、昨日分红率 必须消失
    assert 'EPS分红率' not in cols, 'EPS分红率 应被去掉'
    assert '昨日分红率' not in cols, '昨日分红率 应被去掉'
    # 2) 最新分红率 改名为 最新价格去年分红率
    assert '最新分红率' not in cols, '最新分红率 应改名'
    assert '最新价格去年分红率' in cols, '应有 最新价格去年分红率'
    # 3) 最新分红率_raw 紧随其后
    assert '最新分红率_raw' in cols
    assert cols.index('最新分红率_raw') == cols.index('最新价格去年分红率') + 1, \
        '最新分红率_raw 应紧随 最新价格去年分红率 之后'
    print('test_columns_dropped_and_renamed_and_ordered OK')


def test_ttm_yield_calculation():
    df = _sample_df()
    # 605368: TTM股息 0.40 / 最新价 7.13 * 100 = 5.61%
    # 600519: TTM股息 30.0 / 最新价 1700 * 100 = 1.76%
    ttm_map = {'605368': 0.40, '600519': 30.0}
    out = rt.TaskApp._prepare_data_view(df, ttm_map)
    val_605368 = out.loc[out['代码'] == '605368', '最新分红率_raw'].iloc[0]
    val_600519 = out.loc[out['代码'] == '600519', '最新分红率_raw'].iloc[0]
    assert abs(val_605368 - 0.40 / 7.13 * 100) < 0.01, f'605368 TTM股息率应为 5.61, 实际 {val_605368}'
    assert abs(val_600519 - 30.0 / 1700.0 * 100) < 0.01, f'600519 TTM股息率应为 1.76, 实际 {val_600519}'
    # 最新价格去年分红率 保留原 最新分红率 值
    assert abs(out.loc[out['代码'] == '605368', '最新价格去年分红率'].iloc[0] - 5.0) < 1e-9
    print('test_ttm_yield_calculation OK')


def test_missing_ttm_yields_na():
    df = _sample_df()
    out = rt.TaskApp._prepare_data_view(df, {})   # 无 TTM 数据
    assert out['最新分红率_raw'].isna().all(), '缺失 TTM 数据时应全为 NA（非 0）'
    print('test_missing_ttm_yields_na OK')


if __name__ == '__main__':
    test_columns_dropped_and_renamed_and_ordered()
    test_ttm_yield_calculation()
    test_missing_ttm_yields_na()
    print('== P0-6 数据查看页字段调整 全部通过 ==')
