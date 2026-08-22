# -*- coding: utf-8 -*-
"""合并《分红率排名_排除.csv》的 J~M 列到《分红率排名.csv》，并生成筛选后文件。

J 列 = 是否保留（是 / 否 / 空）；K = 买入提醒pe；L = 买入提醒价格；M = 买入pb。
筛选规则：保留“是否保留”为“是”或为空(未标注)的股票，剔除为“否”的。
"""
import os
import pandas as pd

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
RANK = os.path.join(DATA, '分红率排名.csv')
EXCL = os.path.join(DATA, '分红率排名_排除.csv')
OUT_FULL = os.path.join(DATA, '分红率排名.csv')
OUT_FILT = os.path.join(DATA, '分红率排名（筛选后）.csv')


def norm_code(s):
    return s.astype(str).str.replace(r'\D', '', regex=True).str.zfill(6)


def main():
    rank = pd.read_csv(RANK, encoding='utf-8-sig')
    excl = pd.read_csv(EXCL, encoding='gbk')          # 排除文件为 GBK 编码
    excl = excl.rename(columns=lambda c: c.strip())    # 去除表头可能的空格

    # J~M：是否保留、买入提醒pe、买入提醒价格、买入pb
    excl_cols = ['代码', '是否保留', '买入提醒pe', '买入提醒价格', '买入pb']
    excl_map = excl.loc[:, excl_cols].copy()
    if '代码' in excl_map.columns:
        excl_map['代码'] = norm_code(excl_map['代码'])
    else:  # 兜底：若代码列名异常，按第2列
        excl_map = excl.iloc[:, [1, 9, 10, 11, 12]].copy()
        excl_map.columns = excl_cols
        excl_map['代码'] = norm_code(excl_map['代码'])
    excl_map = excl_map.drop_duplicates(subset='代码', keep='first')

    rank['代码'] = norm_code(rank['代码'])

    merged = rank.merge(excl_map, on='代码', how='left')

    print(f'《分红率排名.csv》: {len(rank)} 只；')
    print(f'《分红率排名_排除.csv》: {len(excl)} 只；')
    matched = merged['是否保留'].notna().sum()
    print(f'按代码匹配到 J~M 数据的股票数: {matched}')

    merged.to_csv(OUT_FULL, index=False, encoding='utf-8-sig')

    # 筛选：是否保留 = 是 或 空（NaN/空白）
    j = merged['是否保留'].astype('string')
    keep = merged[j.isna() | (j.str.strip() == '是')].copy()
    keep.to_csv(OUT_FILT, index=False, encoding='utf-8-sig')

    print(f'筛选后保留 {len(keep)} 只 -> {os.path.basename(OUT_FILT)}')
    print('  剔除(否)股票示例:',
          merged.loc[j.str.strip() == '否', '名称'].tolist()[:5])


if __name__ == '__main__':
    main()