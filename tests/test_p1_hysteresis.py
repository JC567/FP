# -*- coding: utf-8 -*-
"""P1-4 Hysteresis entry/exit 阈值表述测试。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from valresearch.signal.engine import hysteresis_bands, compute_signal, _hyst_less, _hyst_greater


def test_bands_no_contradiction():
    b = hysteresis_bands(30, 70, 70, 5.0)
    assert b['pe_entry'] == 30 and b['pe_exit'] == 35      # 退出在更不利一侧
    assert b['dy_entry'] == 70 and b['dy_exit'] == 65
    assert b['pr_entry'] == 70 and b['pr_exit'] == 75
    assert b['hysteresis'] == 5.0
    print('test_bands_no_contradiction OK: %s' % b)


def test_entry_exit_semantics_consistent():
    """进入=严格阈值；已在位时退出需越过更不利边界，杜绝来回翻转矛盾。"""
    # 条件A(越小越好)：未在位时 <30 才进入
    assert _hyst_less(29, 30, 5, False) is True
    assert _hyst_less(31, 30, 5, False) is False
    # 已在位时，直到 >=35 才退出
    assert _hyst_less(33, 30, 5, True) is True     # 仍在位
    assert _hyst_less(36, 30, 5, True) is False    # 退出
    # 条件B(越大越好)：未在位时 >70 才进入
    assert _hyst_greater(71, 70, 5, False) is True
    # 已在位时，直到 <=65 才退出
    assert _hyst_greater(67, 70, 5, True) is True
    assert _hyst_greater(64, 70, 5, True) is False
    print('test_entry_exit_semantics_consistent OK')


def test_compute_signal_exposes_bands():
    m = {'pe_pct': 10, 'dy_pct': 90, 'pr_pct': 40, 'spread': 0.03,
         'spread_threshold': 0.02, 'pe_fair_ratio': 0.9, 'gordon_status': 'VALID',
         'quality_score': 80, 'industry_score': 40}
    sig = compute_signal(m, {}, {'penalty': 0.0, 'level': 'LOW'}, {})
    assert 'hysteresis_bands' in sig
    assert sig['hysteresis_bands']['pe_exit'] > sig['hysteresis_bands']['pe_entry']
    print('test_compute_signal_exposes_bands OK')


if __name__ == '__main__':
    test_bands_no_contradiction()
    test_entry_exit_semantics_consistent()
    test_compute_signal_exposes_bands()
    print('== P1-4 Hysteresis 表述 全部通过 ==')