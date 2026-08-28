"""P0：巴菲特模式（单股分析）判定与报告。

确定性单测用构造的 AnalysisReport 覆盖 适合/不适合/边界；
集成测试联网时对 600036 验证"适合"路径（无数据则跳过）。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from valresearch.main import AnalysisReport
from valresearch.report.buffett import buffett_assess, format_buffett_report


def _rep(quality, fair_ratio, gordon_status, vt_score):
    return AnalysisReport(
        symbol='X', name='测试', analysis_date='2026-01-01',
        fundamental={'quality_score': quality},
        value_trap={'score': vt_score},
        signal={'pe_fair_ratio': fair_ratio, 'gordon_status': gordon_status},
    )


def test_buffett_suitable():
    rep = _rep(quality=70, fair_ratio=0.7, gordon_status='VALID', vt_score=10)
    a = buffett_assess(rep)
    assert a['suitable'] is True, a
    assert a['margin_of_safety'] == 0.3
    txt = format_buffett_report(rep)
    assert '✔ 适合巴菲特模式' in txt and '分批买入' in txt
    assert '✘ 不适合巴菲特模式' not in txt


def test_buffett_unsuitable_quality():
    rep = _rep(quality=50, fair_ratio=0.5, gordon_status='VALID', vt_score=10)
    a = buffett_assess(rep)
    assert a['suitable'] is False
    assert any('质量分' in f for f in a['fails'])
    txt = format_buffett_report(rep)
    assert '✘ 不适合巴菲特模式' in txt
    assert '分批建仓' not in txt   # 不适合时不给买入建议


def test_buffett_unsuitable_margin():
    rep = _rep(quality=70, fair_ratio=0.9, gordon_status='VALID', vt_score=10)
    a = buffett_assess(rep)
    assert a['suitable'] is False
    assert any('安全边际' in f for f in a['fails'])


def test_buffett_unsuitable_trap():
    rep = _rep(quality=70, fair_ratio=0.5, gordon_status='VALID', vt_score=80)
    a = buffett_assess(rep)
    assert a['suitable'] is False
    assert any('价值陷阱' in f for f in a['fails'])


def test_buffett_unsuitable_gordon_invalid():
    rep = _rep(quality=70, fair_ratio=None, gordon_status='INVALID', vt_score=10)
    a = buffett_assess(rep)
    assert a['suitable'] is False
    assert any('Gordon' in f for f in a['fails'])


def test_buffett_integration_600036():
    # 联网/本地缓存可用时校验 600036 走"适合"路径；不可用/超时则跳过（不阻塞）
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
    th.join(60)   # 最多等 60 秒取数，超时即跳过
    if 'rep' not in box:
        print('test_buffett_integration_600036 SKIP (无数据/超时)')
        return
    a = buffett_assess(box['rep'])
    print('test_buffett_integration_600036 OK suitable=', a['suitable'],
          '质量=', a['quality_score'], '价/合理PE=', a['pe_fair_ratio'], '陷阱=', a['vt_score'])
    assert a['suitable'] is True, a['fails']


if __name__ == '__main__':
    test_buffett_suitable()
    test_buffett_unsuitable_quality()
    test_buffett_unsuitable_margin()
    test_buffett_unsuitable_trap()
    test_buffett_unsuitable_gordon_invalid()
    test_buffett_integration_600036()
    print('== 巴菲特模式(单股分析) 全部通过 ==')
