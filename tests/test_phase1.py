# -*- coding: utf-8 -*-
"""Phase 1 冒烟测试：验证各数据源可实际取数（网络不稳，含重试）。"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from valresearch.data.providers import (DataProvider, FinancialDataProvider,
                                        DividendDataProvider, MacroDataProvider,
                                        IndustryDataProvider)

SYM = '600036'   # 招商银行
NAME = '招商银行'


def t(label, fn):
    t0 = time.time()
    for i in range(3):
        try:
            res = fn()
            n = len(res) if hasattr(res, '__len__') else res
            print(f'  [OK] {label}: {n}  ({time.time()-t0:.1f}s)')
            return res
        except Exception as e:
            if i == 2:
                print(f'  [FAIL] {label}: {type(e).__name__} {str(e)[:100]}')
            else:
                time.sleep(2)
    return None


if __name__ == '__main__':
    print('== Phase 1 Provider 冒烟 (symbol=600036) ==')
    price = t('price', lambda: DataProvider().get_price(SYM, '20150101'))
    if price is not None:
        print('     price rows sample:', price.tail(2).to_dict('records'))
        print('     has adj_close:', price['adj_close'].notna().sum(), '/', len(price))
    fin = t('financials', lambda: FinancialDataProvider().get_financials(SYM, 2013))
    if fin is not None:
        print('     fin cols:', list(fin.columns))
        print(fin.tail(3).to_string())
    div = t('dividends', lambda: DividendDataProvider().get_dividends(SYM))
    if div is not None:
        print('     div rows:', len(div), div.tail(3).to_string())
    macro = t('bond_yield', lambda: MacroDataProvider().get_bond_yield('20240101'))
    if macro is not None:
        print('     macro tail:', macro.tail(2).to_string())
    ind = t('industry', lambda: IndustryDataProvider().get_industry(SYM, NAME))
    print('     industry:', ind)