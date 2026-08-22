# -*- coding: utf-8 -*-
"""负债水平评分(0-100)。普通行业用资产负债率/有息负债；银行/保险/证券走行业适配指标。
数据缺失返回中间分并标 DATA_INSUFFICIENT。"""
from __future__ import annotations

import pandas as pd


def leverage_score(fin, t, industry_type='制造业') -> dict:
    res = {'score': 50, 'asset_liability_ratio': None, 'int_bearing_debt': None,
           'flags': [], 'warnings': [], 'available': True, 'industry_type': industry_type}
    if fin is None or fin.empty:
        res['available'] = False
        res['warnings'].append('负债水平: 无财报数据(DATA_INSUFFICIENT)')
        return res
    f = fin.copy()
    f['ann_ts'] = pd.to_datetime(f['announcement_date'])
    a = f[f['ann_ts'] <= pd.to_datetime(t)]
    if a.empty:
        res['available'] = False
        res['warnings'].append('负债水平: 无已公告财报(DATA_INSUFFICIENT)')
        return res
    # 行业适配：金融类不适用普通资产负债率
    if industry_type in ('银行', '保险', '证券'):
        res['warnings'].append(f'负债水平: 金融行业({industry_type})需专门指标(资本充足/偿付能力/杠杆)，'
                               f'当前数据不足，采用中间分(DATA_INSUFFICIENT)')
        res['available'] = False
        res['score'] = 55
        return res
    # 普通行业：最近年报资产负债率
    a = a.sort_values('ann_ts')
    if 'total_assets' in a.columns and 'total_liabilities' in a.columns:
        valid = a[pd.to_numeric(a['total_assets'], errors='coerce').notna()
                  & pd.to_numeric(a['total_liabilities'], errors='coerce').notna()]
        if not valid.empty:
            last = valid.iloc[-1]
            ta, tl = float(last['total_assets']), float(last['total_liabilities'])
            if ta > 0:
                res['asset_liability_ratio'] = round(tl / ta, 4)
                al = res['asset_liability_ratio']
                score = 80 if al < 0.4 else 65 if al < 0.6 else 45 if al < 0.75 else 25 if al < 0.85 else 10
                res['score'] = score
                return res
    res['available'] = False
    res['warnings'].append('负债水平: 缺少总资产/总负债字段(DATA_INSUFFICIENT)')
    return res