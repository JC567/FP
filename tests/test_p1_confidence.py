# -*- coding: utf-8 -*-
"""P1-1 数据置信度评分测试。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from valresearch.data.confidence import (data_confidence_score, ann_source_score,
                                         N_DIMS, REAL, FALLBACK, ESTIMATED)


def test_full_data_high_confidence():
    conf = data_confidence_score(N_DIMS, REAL, 12)
    assert conf['level'] == 'HIGH'
    assert conf['score'] >= 80
    assert conf['dim_coverage'] == 1.0 and conf['ann_caliber'] == 1.0
    print('test_full_data_high_confidence OK: score=%s' % conf['score'])


def test_estimates_and_short_history_low():
    conf = data_confidence_score(4, ESTIMATED, 2)
    assert conf['level'] == 'LOW'
    assert conf['score'] < 60
    assert any('公告日' in r for r in conf['reasons'])
    assert any('历史跨度' in r for r in conf['reasons'])
    print('test_estimates_and_short_history_low OK: score=%s' % conf['score'])


def test_mid_medium():
    # 5/7 维度 + 法规截止日 + 6年 → 约65分 MEDIUM
    conf = data_confidence_score(5, ESTIMATED, 6)
    assert conf['level'] == 'MEDIUM'
    assert 60 <= conf['score'] < 80
    print('test_mid_medium OK: score=%s' % conf['score'])


def test_no_data_lowest():
    conf = data_confidence_score(0, None, 0)
    assert conf['level'] == 'LOW'
    assert conf['score'] == 0.0
    assert ann_source_score(None) == 0.0
    assert ann_source_score(REAL) == 1.0
    assert ann_source_score(FALLBACK) == 0.8
    assert ann_source_score(ESTIMATED) == 0.6
    print('test_no_data_lowest OK')


if __name__ == '__main__':
    test_full_data_high_confidence()
    test_estimates_and_short_history_low()
    test_mid_medium()
    test_no_data_lowest()
    print('== P1-1 Data Confidence 全部通过 ==')