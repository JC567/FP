# -*- coding: utf-8 -*-
"""复核某只股票「近10年PE百分位」，用于检查 CSV 中的值是否正确。

用法:
    python check_pe.py 600887
    python check_pe.py 600887 000858
不带参数则随机抽查结果文件前5只。
"""
import sys, os, io, random
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import akshare as ak
import pandas as pd

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
RANK = os.path.join(DATA, '分红率排名（筛选后）.csv')


def norm(s):
    return s.astype(str).str.replace(r'\D', '', regex=True).str.zfill(6)


def compute(code):
    """从东财逐日接口重新计算 近10年PE-TTM 排名百分位（雪球口径）。"""
    df = ak.stock_value_em(symbol=code)
    v = pd.to_numeric(df['PE(TTM)'], errors='coerce').dropna()
    cur = v.iloc[-1]
    pct = float((v < cur).mean() * 100)
    return pct, cur, int(len(v))


def main():
    codes = [c for c in sys.argv[1:]]
    df = pd.read_csv(RANK, encoding='utf-8-sig')
    df['代码'] = norm(df['代码'])
    if not codes:
        codes = df['代码'].head(5).tolist()
    for code in codes:
        row = df[df['代码'] == code]
        if row.empty:
            print(f'{code}: 不在结果文件中')
            continue
        csv_val = row['近10年PE百分位'].iloc[0] if '近10年PE百分位' in df.columns else None
        try:
            pct, cur, n = compute(code)
            diff = ''
            if pd.notna(csv_val):
                diff = f'  差值={pct - float(csv_val):+.2f}'
            print(f'{code}: 当前PE-TTM={cur:.2f} | 重新计算百分位={pct:.2f}% '
                  f'(样本{n}个) | CSV值={csv_val}{diff}')
        except Exception as e:
            print(f'{code}: 复核失败 {e}')


if __name__ == '__main__':
    main()
