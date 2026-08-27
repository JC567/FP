# -*- coding: utf-8 -*-
"""P0-9 数据查看页「行业」列回归测试。

来源：东方财富行业板块（industry_map.build_industry_map，缓存于 vr_stocks）。
位置：紧贴 名称 之后。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from unittest import mock
import run_task as rt
import industry_map as indmap


def test_build_industry_map_logic():
    name_df = pd.DataFrame({'板块名称': ['白酒', '银行']})
    cons_baijiu = pd.DataFrame({'代码': ['600519', '000858'], '名称': ['贵州茅台', '五粮液']})
    cons_bank = pd.DataFrame({'代码': ['601398'], '名称': ['工商银行']})

    def fake_board_name_em():
        return name_df

    def fake_board_cons_em(symbol):
        return cons_baijiu if symbol == '白酒' else cons_bank

    with mock.patch('akshare.stock_board_industry_name_em',
                    side_effect=fake_board_name_em), \
         mock.patch('akshare.stock_board_industry_cons_em',
                    side_effect=fake_board_cons_em):
        mp = indmap.build_industry_map()
    assert mp.get('600519') == '白酒', mp
    assert mp.get('000858') == '白酒', mp
    assert mp.get('601398') == '银行', mp
    print('test_build_industry_map_logic OK')


def test_prepare_places_industry_after_name():
    df = pd.DataFrame({
        '排名': [1], '代码': ['600519'], '名称': ['贵州茅台'],
        '最新分红率': [2.0], 'EPS分红率': [50.0], '昨日分红率': [1.9],
        '当前PE': [30.0], '每股分红合计': [1.0], '最新价': [1700.0],
        '行业': ['白酒'],
    })
    out = rt.TaskApp._prepare_data_view(df, {})
    cols = list(out.columns)
    assert cols.index('行业') == cols.index('名称') + 1, cols
    assert 'EPS分红率' not in cols and '昨日分红率' not in cols
    assert '最新价格去年分红率' in cols
    print('test_prepare_places_industry_after_name OK')


def test_prepare_fills_industry_from_cache():
    df = pd.DataFrame({
        '排名': [1], '代码': ['600519'], '名称': ['贵州茅台'],
        '最新分红率': [2.0], '当前PE': [30.0], '每股分红合计': [1.0], '最新价': [1700.0],
    })
    with mock.patch.object(rt.stock_db, 'connect') as mconn, \
         mock.patch.object(rt.stock_db, 'get_industry_map',
                           return_value={'600519': '白酒'}) as mg:
        fake_conn = mock.MagicMock()
        mconn.return_value = fake_conn
        out = rt.TaskApp._prepare_data_view(df, {})
    cols = list(out.columns)
    assert out['行业'].iloc[0] == '白酒', '应从缓存补行业'
    assert cols.index('行业') == cols.index('名称') + 1, cols
    print('test_prepare_fills_industry_from_cache OK')


if __name__ == '__main__':
    test_build_industry_map_logic()
    test_prepare_places_industry_after_name()
    test_prepare_fills_industry_from_cache()
    print('== P0-9 数据查看页行业列 全部通过 ==')
