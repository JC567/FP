# -*- coding: utf-8 -*-
"""Phase 11 报告生成测试（用已生成 JSON，无网络）。"""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from valresearch.models import AnalysisReport
from valresearch.report import format_report, save_json, load_json


def _rep():
    return AnalysisReport.from_dict({
        'symbol': '600036', 'name': '招商银行', 'analysis_date': '2025-07-01',
        'mode': 'balanced',
        'valuation': {'price': 46.45, 'pe_ttm': 8.18, 'pe_pct_10y': 50.02, 'pe_pct_5y': 62.08,
                      'dividend_yield': 4.25, 'dividend_yield_pct': 70.19, 'payout_ratio': 34.6,
                      'payout_pct': 88.84, 'rf_10y': 1.64, 'dividend_spread': 2.6,
                      'spread_threshold': 2.0, 'spread_signal': True,
                      'pe_min': 3.0, 'pe_p10': 4.0, 'pe_median': 8.0, 'pe_p90': 12.0, 'pe_max': 20.0,
                      'pe_n_valid': 100, 'pe_n_excluded': 3, 'dy_min': 1.0, 'dy_p10': 2.0,
                      'dy_median': 4.0, 'dy_p90': 6.0, 'dy_max': 8.0, 'dy_n_valid': 100,
                      'pr_n_valid': 90, 'pr_n_excluded': 2, 'payout_abnormal': False,
                      'eps_ttm': 5.68, 'dps_ttm': 1.97},
        'fundamental': {'quality_score': 64.2,
                        'sub': {'earnings': 68, 'cashflow': 50, 'dividend': 78,
                                'leverage': 65, 'industry': 50},
                        'flags': ['PE_TTM_PIT_APPROXIMATION']},
        'value_trap': {'score': 0, 'level': 'LOW', 'flags': [], 'penalty': 0.0,
                       'block_strong_buy': False},
        'signal': {'condition_a': False, 'condition_b': True, 'condition_c': True,
                   'rule_signal': 'HIGH_YIELD_NOT_CHEAP_ENOUGH', 'score': 59.1,
                   'score_signal': 'HOLD', 'final_signal': 'HOLD', 'note': '',
                   'gordon_g': 0.05, 'pe_fair_ratio': None, 'pe_fair_band': 'NA',
                   'thresholds': {'pe': 30, 'dy': 70, 'payout': 70},
                   'gordon_scenario': {'fair_pe_low': 9.5, 'fair_pe_base': None,
                                       'fair_pe_high': None, 'invalid': 'GGM_INVALID: Ke-g 过小'}},
        'price': {'fair_price_low': 54.15, 'fair_price_base': None, 'fair_price_high': None,
                  'price_at_4pct': 49.3, 'price_at_5pct': 39.44, 'price_at_6pct': 32.87,
                  'price_at_7pct': 28.17, 'pe_p20_price': 37.73, 'pe_p30_price': 41.5,
                  'pe_p50_price': 46.34, 'pe_p70_price': 56.66,
                  'deep_buy_low': 33.96, 'deep_buy_high': 37.73,
                  'standard_buy_low': 37.35, 'standard_buy_high': 41.5,
                  'current_zone': '持有区'},
        'position': {'signal': 'HOLD', 'init_weight': 0.0, 'target_weight': 0.0,
                     'max_weight': 0.0, 'rationale': '信号=HOLD 的基础仓位'},
        'trace': {'pe': {'source': 'baidu_pit_approx', 'n_valid': 100, 'n_excluded': 3,
                         'window': '2015-07 ~ 2025-07'}},
        'quality_warnings': [], 'data_limitations': ['PE_TTM_PIT_APPROXIMATION'],
        'notes': ['便宜≠一定上涨'],
    })


def test_format_report():
    rep = _rep()
    txt = format_report(rep)
    for sec in ('【1 摘要】', '【2 当前估值概况】', '【3 历史水平对比】', '【4 公司基本面质量】',
                '【5 价值陷阱风险】', '【6 投资信号分析】', '【7 合理价格与买入区间】',
                '【8 仓位建议】', '【9 注意事项与数据来源】'):
        assert sec in txt, sec
    assert '招商银行' in txt and '持有' in txt
    assert '均衡型' in txt and '高股息但估值不低' in txt
    assert 'STRONG_BUY' not in txt and 'HOLD' not in txt
    print('test_format_report OK, %d chars' % len(txt))


def test_json_roundtrip():
    rep = _rep()
    path = os.path.join(tempfile.gettempdir(), 'vr_rep_test.json')
    save_json(rep, path)
    d = load_json(path)
    assert d['symbol'] == '600036'
    assert d['signal']['final_signal'] == 'HOLD'
    os.remove(path)
    print('test_json_roundtrip OK')


if __name__ == '__main__':
    test_format_report()
    test_json_roundtrip()
    print('== Phase 11 全部通过 ==')
    print()
    print(format_report(_rep()))