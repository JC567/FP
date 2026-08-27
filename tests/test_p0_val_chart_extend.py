# -*- coding: utf-8 -*-
"""P0-8 估值走势图各序列延展到最新日期(今天)回归测试。

分红率为年度序列，止步于较早的公告日(如 2026-07-14)，会使图表最新时间不是今天。
_extend_series_to 按最后值前移(Carry-forward)到 target_end。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import run_task as rt


def _ser(dates, vals):
    return pd.DataFrame({'日期': pd.to_datetime(dates), 'value': vals})


def test_extends_to_target_with_last_value():
    w = _ser(['2025-01-01', '2026-07-14'], [30.0, 40.0])
    out = rt.TaskApp._extend_series_to(w, pd.Timestamp('2026-08-27'))
    assert len(out) == 3, '应追加一行'
    assert out['日期'].iloc[-1] == pd.Timestamp('2026-08-27'), '末日应为今天'
    assert out['value'].iloc[-1] == 40.0, '末值应前移(等于最后真实值)'
    print('test_extends_to_target_with_last_value OK')


def test_no_extension_when_already_at_or_past_target():
    w = _ser(['2025-01-01', '2026-08-27'], [30.0, 40.0])
    out = rt.TaskApp._extend_series_to(w, pd.Timestamp('2026-08-27'))
    assert len(out) == 2, '已到 target 不应追加'
    w2 = _ser(['2025-01-01', '2026-09-01'], [30.0, 40.0])
    out2 = rt.TaskApp._extend_series_to(w2, pd.Timestamp('2026-08-27'))
    assert len(out2) == 2, '超过 target 不应追加'
    print('test_no_extension_when_already_at_or_past_target OK')


def test_none_and_empty_passthrough():
    assert rt.TaskApp._extend_series_to(None, pd.Timestamp('2026-08-27')) is None
    empty = pd.DataFrame({'日期': [], 'value': []})
    out = rt.TaskApp._extend_series_to(empty, pd.Timestamp('2026-08-27'))
    assert out.empty
    print('test_none_and_empty_passthrough OK')


if __name__ == '__main__':
    test_extends_to_target_with_last_value()
    test_no_extension_when_already_at_or_past_target()
    test_none_and_empty_passthrough()
    print('== P0-8 估值图序列延展到今天 全部通过 ==')
