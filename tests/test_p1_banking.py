# -*- coding: utf-8 -*-
"""P1-2 金融行业专用基本面模型测试。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd

from valresearch.fundamental.banking import (is_financial, banking_quality,
                                             roe_latest, equity_ratio_latest)
from valresearch.fundamental.quality_score import quality_score


def _bank_fin():
    return pd.DataFrame({
        'report_period': ['2024-12-31', '2023-12-31'],
        'announcement_date': ['2025-04-30', '2024-04-30'],
        'eps_basic': [1.5, 1.4],
        'net_profit_attr': [300e8, 280e8],
        'total_assets': [40000e8, 38000e8],
        'total_liabilities': [37000e8, 35200e8],
        'revenue': [6000e8, 5800e8], 'ocf': [None, None],
        'int_bearing_debt': [None, None],
    })


def test_is_financial():
    assert is_financial('银行') and is_financial('保险') and is_financial('证券')
    assert not is_financial('制造业') and not is_financial(None)
    print('test_is_financial OK')


def test_bank_metrics():
    fin = _bank_fin()
    roe = roe_latest(fin)                      # 300/(40000-37000)=0.10
    eqr = equity_ratio_latest(fin)             # 3000/40000=0.075
    assert roe is not None and abs(roe - 0.10) < 1e-9
    assert eqr is not None and abs(eqr - 0.075) < 1e-9
    bk = banking_quality(fin, None, '2025-06-01', '银行')
    assert bk['score'] >= 0 and bk['roe'] == 0.1
    assert bk['equity_ratio'] == 0.075
    print('test_bank_metrics OK: roe=%.3f eqr=%.3f score=%.1f' % (roe, eqr, bk['score']))


def test_quality_score_branches_for_bank():
    fin = _bank_fin()
    q = quality_score(fin, None, '2025-06-01', '银行')
    assert 'banking' in q['sub'], '银行行业应走专用模型'
    assert q['sub']['banking'] >= 0
    qm = quality_score(fin, None, '2025-06-01', '制造业')
    assert 'banking' not in qm['sub'], '非金融行业走通用模型'
    print('test_quality_score_branches_for_bank OK: bank_score=%s mfg_score=%s'
          % (q['sub']['banking'], qm['score']))


if __name__ == '__main__':
    test_is_financial()
    test_bank_metrics()
    test_quality_score_branches_for_bank()
    print('== P1-2 金融行业模型 全部通过 ==')