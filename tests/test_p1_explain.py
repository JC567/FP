# -*- coding: utf-8 -*-
"""P1-7 模型解释链测试：每个分数都能追溯回原始输入与阈值。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from valresearch.signal.explain import explain_signal
from valresearch.signal.engine import compute_signal, hysteresis_bands


def test_explain_chain_complete():
    m = {'pe_pct': 10.0, 'dy_pct': 85.0, 'pr_pct': 40.0, 'spread': 0.03,
         'spread_threshold': 0.02, 'pe_fair_ratio': 0.9, 'gordon_status': 'VALID',
         'quality_score': 80, 'industry_score': 40}
    sig = compute_signal(m, {}, {'penalty': 0.0, 'level': 'LOW'}, {})
    chain = explain_signal(m, sig['components'], sig['thresholds'],
                           sig['hysteresis_bands'], sig['value_trap_level'],
                           sig['final_signal'], sig['note'], {})
    assert len(chain) == 8, '解释链应有8步'
    steps = [c['step'] for c in chain]
    assert all(s in steps for s in ('1. PE分位(低估维度)', '4. Gordon可持续增速',
                                    '8. 最终信号'))
    # 每步可读且含阈值/结果
    for c in chain:
        assert c['threshold'] and c['result']
    print('test_explain_chain_complete OK, %d 步' % len(chain))


def test_explain_data_insufficient_text():
    m = {'pe_pct': None, 'dy_pct': None, 'pr_pct': None, 'spread': None,
         'spread_threshold': 0.02, 'pe_fair_ratio': None, 'gordon_status': 'INSUFFICIENT',
         'quality_score': 50, 'industry_score': 50}
    sig = compute_signal(m, {}, {'penalty': 0.0, 'level': 'LOW'}, {})
    chain = explain_signal(m, sig['components'], sig['thresholds'],
                           sig['hysteresis_bands'], sig['value_trap_level'],
                           sig['final_signal'], sig['note'], {})
    # 数据不足应在解释链中体现为"数据不足"
    assert any('数据不足' in c['value'] for c in chain[:3])
    print('test_explain_data_insufficient_text OK')


if __name__ == '__main__':
    test_explain_chain_complete()
    test_explain_data_insufficient_text()
    print('== P1-7 模型解释链 全部通过 ==')