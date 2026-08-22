# -*- coding: utf-8 -*-
"""P1-3 价格区间统一与风险调整测试。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from valresearch.valuation.price_range import (price_methods, unify_price, risk_adjust_price,
                                               price_at_dy)


class _St:
    p50 = 15.0


def test_price_methods_gather():
    m = price_methods(2.0, _St(), 0.5, 30.0)          # ggm=30, pe_p50=30, div5%=10
    assert m.get('ggm') == 30.0
    assert m.get('pe_p50') == 30.0
    assert m.get('dividend_5pct') == price_at_dy(0.5, 0.05)   # 10.0
    # 单一方法失效：无 fair_price_base → 无 ggm
    m2 = price_methods(2.0, _St(), 0.5, None)
    assert 'ggm' not in m2 and 'pe_p50' in m2
    print('test_price_methods_gather OK: %s' % list(m.keys()))


def test_unify_median_and_uncertain():
    u = unify_price({'a': 20.0, 'b': 22.0, 'c': 21.0})
    assert u['fair_price'] == 21.0 and not u['uncertain'] and u['n_methods'] == 3
    # 差异过大 → uncertain
    u2 = unify_price({'a': 10.0, 'b': 40.0})
    assert u2['uncertain'] is True
    u3 = unify_price({})
    assert u3['fair_price'] is None and u3['n_methods'] == 0
    print('test_unify_median_and_uncertain OK')


def test_risk_adjust():
    assert risk_adjust_price(20.0, 0.0, False) == 18.0        # 仅基础10%折价
    assert risk_adjust_price(20.0, 0.5, False) == 17.0        # 陷阱惩罚0.5 → 折价15%
    assert risk_adjust_price(20.0, 1.0, False) == 16.0        # 惩罚1.0 → 折价20%
    assert risk_adjust_price(20.0, 0.0, True) == 16.0         # Gordon失效另加10%
    assert risk_adjust_price(None, 0.0, False) is None
    assert risk_adjust_price(20.0, 3.0, True) == 10.0         # 折价上限50%
    print('test_risk_adjust OK')


if __name__ == '__main__':
    test_price_methods_gather()
    test_unify_median_and_uncertain()
    test_risk_adjust()
    print('== P1-3 价格区间统一与风险调整 全部通过 ==')