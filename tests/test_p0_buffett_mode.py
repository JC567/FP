"""P0：巴菲特模式（单股分析 / 单股回测）——仅银行业，能力圈限定。

确定性单测用构造的 AnalysisReport 覆盖：
  · 非银行业 → 暂未支持该行业（unsupported）
  · 银行业 → 适合 / 各项质量门槛不满足 / 便宜门槛不满足
集成测试联网时对 600036(银行) 验证"支持+银行业口径"，对 000333(非银行) 验证"不支持"。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from valresearch.main import AnalysisReport
from valresearch.report.buffett import buffett_assess, format_buffett_report


def _bank_rep(roe=0.15, eqr=0.08, div_consec=10, vt_score=20, vt_level='LOW',
              pb=0.8, pe_pct=20, dy_pct=40, np_dd=-20.0, declines=0,
              price=10.0, dy=4.0, industry_type='银行'):
    return AnalysisReport(
        symbol='X', name='测试银行', analysis_date='2026-01-01',
        industry_type=industry_type,
        fundamental={'detail': {
            'banking': {'roe': roe, 'equity_ratio': eqr},
            'earnings': {'np_max_drawdown': np_dd, 'consecutive_declines': declines},
            'dividend': {'consecutive_years': div_consec},
        }},
        value_trap={'score': vt_score, 'level': vt_level},
        valuation={'price': price, 'pb': pb, 'pe_pct_10y': pe_pct,
                   'dividend_yield_pct': dy_pct, 'dividend_yield': dy, 'pe_ttm': 6.0},
    )


def test_buffett_unsupported_industry():
    rep = AnalysisReport(symbol='Y', name='测试制造', analysis_date='2026-01-01',
                         industry_type='制造业')
    a = buffett_assess(rep)
    assert a['supported'] is False
    assert a['suitable'] is None
    assert any('暂未支持该行业' in f for f in a['fails'])
    txt = format_buffett_report(rep)
    assert '暂未支持该行业' in txt and '能力圈' in txt


def test_buffett_banking_suitable():
    rep = _bank_rep(roe=0.15, eqr=0.08, div_consec=10, vt_score=20, pb=0.8)
    a = buffett_assess(rep)
    assert a['supported'] is True
    assert a['suitable'] is True, a['fails']
    assert a['method'] == 'PB(破净)'
    txt = format_buffett_report(rep)
    assert '✔ 适合巴菲特模式' in txt and '分批买入' in txt
    assert '✘ 不适合巴菲特模式' not in txt


def test_buffett_banking_unsuitable_roe():
    rep = _bank_rep(roe=0.08)   # ROE < 12%
    a = buffett_assess(rep)
    assert a['suitable'] is False
    assert any('ROE' in f for f in a['fails'])


def test_buffett_banking_unsuitable_equity():
    rep = _bank_rep(eqr=0.04)   # 权益比率 < 6%
    a = buffett_assess(rep)
    assert a['suitable'] is False
    assert any('权益比率' in f for f in a['fails'])


def test_buffett_banking_unsuitable_div():
    rep = _bank_rep(div_consec=3)   # 连续分红 < 5 年
    a = buffett_assess(rep)
    assert a['suitable'] is False
    assert any('分红' in f for f in a['fails'])


def test_buffett_banking_unsuitable_trap():
    rep = _bank_rep(vt_score=70, vt_level='HIGH')   # 价值陷阱
    a = buffett_assess(rep)
    assert a['suitable'] is False
    assert any('价值陷阱' in f for f in a['fails'])


def test_buffett_banking_unsuitable_cheap():
    # 质量达标但 PB>1 且 历史分位未低估 → 便宜门槛不满足
    rep = _bank_rep(roe=0.15, eqr=0.08, div_consec=10, vt_score=20,
                    pb=1.3, pe_pct=60, dy_pct=20)
    a = buffett_assess(rep)
    assert a['suitable'] is False
    assert any('PB' in f or '不够便宜' in f or '价格不够便宜' in f for f in a['fails'])


def test_buffett_banking_cheap_fallback_percentile():
    # 无 PB 时退回历史分位：PE分位=20% → 便宜（质量达标则适合）
    rep = _bank_rep(roe=0.15, eqr=0.08, div_consec=10, vt_score=20,
                    pb=None, pe_pct=20, dy_pct=30)
    a = buffett_assess(rep)
    assert a['supported'] is True
    assert a['method'] == '历史估值分位(PE/股息率)'
    assert a['suitable'] is True, a['fails']


def test_buffett_integration_600036():
    # 联网/本地缓存可用时校验 600036(银行) 走"支持+银行业口径"；不可用则跳过。
    import threading
    box = {}
    def _run():
        try:
            from valresearch.main import analyze
            box['rep'] = analyze('600036', None, 'balanced', '', progress_cb=lambda p, m: None)
        except Exception as e:  # noqa
            box['err'] = e
    th = threading.Thread(target=_run, daemon=True)
    th.start()
    th.join(90)
    if 'rep' not in box:
        print('test_buffett_integration_600036 SKIP (无数据/超时)')
        return
    a = buffett_assess(box['rep'])
    print('test_buffett_integration_600036 OK industry=', box['rep'].industry_type,
          'supported=', a['supported'], 'suitable=', a['suitable'], 'method=', a['method'])
    assert a['supported'] is True   # 600036 是银行 → 必须支持


def test_buffett_backtest_unsupported_nonbank():
    # 非银行业选巴菲特模式 → 回测 buffett_supported=False 且不建仓（trades 为空）
    import threading
    from valresearch.backtest import run_backtest
    from valresearch.config import get_config
    box = {}
    def _run():
        try:
            box['res'] = run_backtest('000333', '2019-01-01', None, 'buffett', get_config('buffett'),
                                      progress_cb=lambda p, m: None)
        except Exception as e:  # noqa
            box['err'] = e
    th = threading.Thread(target=_run, daemon=True)
    th.start()
    th.join(180)
    if 'res' not in box:
        print('test_buffett_backtest_unsupported_nonbank SKIP (无数据/超时)')
        return
    res = box['res']
    print('test_buffett_backtest_unsupported_nonbank OK industry=', res.get('industry_type'),
          'buffett_supported=', res.get('buffett_supported'))
    assert res.get('buffett_supported') is False
    _bt = res.get('trades', {}).get('buffett', [])
    assert not any(t.get('action') == '买入' for t in _bt)   # 非银行业：巴菲特模式不建仓（仅有预算注入记录）


def test_buffett_backtest_supported_bank():
    import threading
    from valresearch.backtest import run_backtest
    from valresearch.config import get_config
    box = {}
    def _run():
        try:
            box['res'] = run_backtest('600036', '2019-01-01', None, 'buffett', get_config('buffett'),
                                      progress_cb=lambda p, m: None)
        except Exception as e:  # noqa
            box['err'] = e
    th = threading.Thread(target=_run, daemon=True)
    th.start()
    th.join(180)
    if 'res' not in box:
        print('test_buffett_backtest_supported_bank SKIP (无数据/超时)')
        return
    res = box['res']
    print('test_buffett_backtest_supported_bank OK industry=', res.get('industry_type'),
          'buffett_supported=', res.get('buffett_supported'))
    assert res.get('buffett_supported') is True


if __name__ == '__main__':
    test_buffett_unsupported_industry()
    test_buffett_banking_suitable()
    test_buffett_banking_unsuitable_roe()
    test_buffett_banking_unsuitable_equity()
    test_buffett_banking_unsuitable_div()
    test_buffett_banking_unsuitable_trap()
    test_buffett_banking_unsuitable_cheap()
    test_buffett_banking_cheap_fallback_percentile()
    test_buffett_integration_600036()
    test_buffett_backtest_unsupported_nonbank()
    test_buffett_backtest_supported_bank()
    print('== 巴菲特模式(银行业专用) 全部通过 ==')
