# -*- coding: utf-8 -*-
"""P0-3 公告日期来源模型测试：REAL/FALLBACK/ESTIMATED 优先级与诚实标注。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd

from valresearch.data.announce import (REAL, FALLBACK, ESTIMATED,
                                       resolve_announcement_source,
                                       annotate_announcement_source)


def test_priority_real_fallback_estimated():
    assert resolve_announcement_source('2025-04-20', None, '2025-04-30')[0] == REAL
    assert resolve_announcement_source(None, '2025-04-25', '2025-04-30')[0] == FALLBACK
    assert resolve_announcement_source(None, None, '2025-04-30')[0] == ESTIMATED
    assert resolve_announcement_source(None, None, None)[0] == ESTIMATED
    src, used = resolve_announcement_source('2025-04-20', '2025-04-25', '2025-04-30')
    assert src == REAL and used == '2025-04-20'
    print('test_priority_real_fallback_estimated OK')


def test_annotate_upgrades_and_keeps_date():
    fin = pd.DataFrame({
        'report_period': ['2024-12-31', '2024-09-30'],
        'announcement_date': ['2025-04-30', '2024-10-31'],
        'real_ann': ['2025-04-20', None],
        'fallback_ann': [None, '2024-10-25'],
    })
    out = annotate_announcement_source(fin, real_col='real_ann', fallback_col='fallback_ann')
    srcs = list(out['announcement_date_source'])
    assert srcs == [REAL, FALLBACK], srcs
    # REAL/FALLBACK 覆盖公告日
    assert out.loc[0, 'announcement_date'] == '2025-04-20'
    assert out.loc[1, 'announcement_date'] == '2024-10-25'
    print('test_annotate_upgrades_and_keeps_date OK')


def test_no_real_source_is_honest_estimated():
    fin = pd.DataFrame({'report_period': ['2024-12-31'],
                        'announcement_date': ['2025-04-30']})
    out = annotate_announcement_source(fin)
    assert out.loc[0, 'announcement_date_source'] == ESTIMATED
    assert out.loc[0, 'announcement_date'] == '2025-04-30'
    print('test_no_real_source_is_honest_estimated OK')


if __name__ == '__main__':
    test_priority_real_fallback_estimated()
    test_annotate_upgrades_and_keeps_date()
    test_no_real_source_is_honest_estimated()
    print('== P0-3 公告日期源 全部通过 ==')