# -*- coding: utf-8 -*-
"""P0-11 缓存覆盖范围校验测试。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

from valresearch.data.cache_coverage import (price_cache_covers,
                                             financial_cache_covers,
                                             dividend_cache_covers)


def test_price_coverage():
    ok, r = price_cache_covers('2020-01-02', '2025-06-30', '2020-01-01', '2025-06-30')
    assert ok and r == 'COVERED'
    # 头部缺失：缓存从 2022 才开始，查询要 2020
    ok2, r2 = price_cache_covers('2022-01-04', '2025-06-30', '2020-01-01', '2025-06-30')
    assert not ok2 and r2 == 'HEAD_MISSING'
    # 尾部缺失：缓存只到 2024
    ok3, r3 = price_cache_covers('2020-01-02', '2024-06-30', '2020-01-01', '2025-06-30')
    assert not ok3 and r3 == 'TAIL_MISSING'
    # 空缓存
    ok4, r4 = price_cache_covers(None, None, '2020-01-01', '2025-06-30')
    assert not ok4 and r4 == 'EMPTY_CACHE'
    print('test_price_coverage OK')


def test_financial_and_dividend_coverage():
    ok, r = financial_cache_covers('2025-04-30', now='2025-06-01')
    assert ok and r == 'COVERED'
    ok2, r2 = financial_cache_covers('2020-04-30', now='2025-06-01')   # 5年前公告 → 缺近期
    assert not ok2 and r2 == 'STALE'
    ok3, r3 = dividend_cache_covers('2025-06-30', now='2025-09-01')
    assert ok3 and r3 == 'COVERED'
    ok4, r4 = dividend_cache_covers('2020-06-30', now='2025-09-01')
    assert not ok4 and r4 == 'STALE'
    print('test_financial_and_dividend_coverage OK')


if __name__ == '__main__':
    test_price_coverage()
    test_financial_and_dividend_coverage()
    print('== P0-11 缓存覆盖范围校验 全部通过 ==')