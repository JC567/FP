# -*- coding: utf-8 -*-
"""合并“排除”文件夹合集数据的 J~M 列到结果文件，并生成筛选后文件。

J=是否保留  K=买入提醒pe  L=买入提醒价格  M=买入pb

流程：
1. 读取《分红率排名.csv》（主程序已按主板生成）。
2. 读取 data/排除/ 下全部文件，取并集（按代码去重），提取 J~M 列。
3. 将其按代码合并到《分红率排名.csv》和《分红率排名（筛选后）.csv》两个结果文件。
4. 《分红率排名（筛选后）.csv》按 J 列 是否保留==否 进行排除（排除数据 = 排除文件夹并集中标记为否的代码）。
"""
import os
import glob

import pandas as pd
import highlight

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
EXCL_DIR = os.path.join(DATA, '排除')
RANK = os.path.join(DATA, '分红率排名.csv')
OUT_FULL = RANK
OUT_FILT = os.path.join(DATA, '分红率排名（筛选后）.csv')
OUT_XLSX = os.path.join(DATA, '分红率排名（筛选后）.xlsx')
MANUAL = os.path.join(EXCL_DIR, '手动配置.csv')


def norm_code(s):
    return s.astype(str).str.replace(r'\D', '', regex=True).str.zfill(6)


def read_any_encoding(path):
    for enc in ('utf-8-sig', 'gbk', 'gb18030'):
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception:
            continue
    raise ValueError(f'无法解析 {path}')


def union_exclude_data():
    """读取 data/排除/ 全部文件，按代码合并为一表（保留 J~M 列）。"""
    files = glob.glob(os.path.join(EXCL_DIR, '*.csv'))
    if not files:
        raise FileNotFoundError(f'排除文件夹为空: {EXCL_DIR}')
    frames = []
    for f in files:
        df = read_any_encoding(f)
        df['代码'] = norm_code(df['代码'])
        jcol = next((c for c in df.columns if '保留' in str(c) or '是否' in str(c)), None)
        out_cols = ['代码']
        if jcol:
            out_cols.append(jcol)  # 是否保留(J)
        for c in df.columns:
            cs = str(c)
            if cs in ('买入提醒pe', '买入提醒价格', '买入pb'):
                out_cols.append(c)
        frames.append(df[out_cols])
    uni = pd.concat(frames, ignore_index=True)
    # 按代码跨文件合并：每列取第一个非空值（coalesce），避免 keep_first 丢失有值文件的数据
    def first_nonnull(s):
        v = s.dropna()
        return v.iloc[0] if len(v) else pd.NA

    agg = uni.groupby('代码').agg({c: first_nonnull for c in uni.columns if c != '代码'})
    return agg.reset_index()


def collect_no_codes():
    """排除文件夹中任意文件 J 列==否 的代码并集（只要任一处标记为否即排除）。"""
    files = glob.glob(os.path.join(EXCL_DIR, '*.csv'))
    no = set()
    for f in files:
        df = read_any_encoding(f)
        jcol = next((c for c in df.columns if '保留' in str(c) or '是否' in str(c)), None)
        if jcol is None:
            continue
        df['代码'] = norm_code(df['代码'])
        j = df[jcol].astype(str)
        no |= set(df.loc[j.str.strip() == '否', '代码'])
    return no


EXCL_COLS = ['是否保留', '买入提醒pe', '买入提醒价格', '买入pb']


def clean_rank(rank):
    """若 rank 已含排除列（含 _x/_y 变体），先剔除，避免重复合并产生 _x/_y。"""
    drop = []
    for c in rank.columns:
        cs = str(c)
        if cs in EXCL_COLS:
            drop.append(c)
        elif cs.endswith('_x') or cs.endswith('_y'):
            if cs[:-2] in EXCL_COLS:
                drop.append(c)
    if drop:
        print(f'已剔除基础文件中的旧排除列: {drop}')
        rank = rank.drop(columns=drop)
    return rank


def _overlay_manual(excl, jcol):
    """《手动配置.csv》为权威：应用界面保存的 L~O 列覆盖其他排除文件，是否保留以它为准。
    同代码、同列只要存在于手动配置即无条件写入（空值=清空旧值）。"""
    if not os.path.exists(MANUAL):
        return excl, None
    m = read_any_encoding(MANUAL)
    m['代码'] = norm_code(m['代码'])
    for _, r in m.iterrows():
        code = r['代码']
        hit = excl.index[excl['代码'] == code]
        if hit.empty:
            continue
        i = hit[0]
        for c in m.columns:
            if c == '代码' or c not in excl.columns:
                continue
            excl.at[i, c] = r.get(c)   # NaN/空 = 清空旧值
    return excl, m['代码'].tolist()


def main():
    rank = pd.read_csv(RANK, encoding='utf-8-sig')
    rank = clean_rank(rank)
    rank['代码'] = norm_code(rank['代码'])

    excl = union_exclude_data()
    no_codes = collect_no_codes()
    jcol = next((c for c in excl.columns if '保留' in str(c) or '是否' in str(c)), None)
    manual_codes = None
    if os.path.exists(MANUAL):
        excl, manual_codes = _overlay_manual(excl, jcol)
        no_codes = set(excl.loc[excl[jcol].astype(str).str.strip() == '否', '代码']) if jcol else set()
        print(f'已应用《手动配置.csv》（权威覆盖），涉及 {len(manual_codes)} 只')
    if jcol is not None:
        # 让“否”在任一文件出现的代码，其展示 J 列统一为“否”
        excl.loc[excl['代码'].isin(no_codes), jcol] = '否'
    print(f'排除文件夹合集: {len(excl)} 只（列 {list(excl.columns)}）')
    print(f'任一处标记为“否”的排除代码数: {len(no_codes)}')

    # 合并 J~M 到《分红率排名.csv》
    full = rank.merge(excl, on='代码', how='left')
    full.to_csv(OUT_FULL, index=False, encoding='utf-8-sig')

    # 生成《分红率排名（筛选后）.csv》：排除 任一处==否 的代码
    keep = full[~full['代码'].isin(no_codes)]
    keep.to_csv(OUT_FILT, index=False, encoding='utf-8-sig')

    print(f'《分红率排名.csv》: {len(full)} 只')
    print(f'排除(否) {len(full) - len(keep)} 只 -> 《分红率排名（筛选后）.csv》: {len(keep)} 只')

    # 生成带高亮的彩色 Excel
    try:
        highlight.process(OUT_FILT, OUT_XLSX, '筛选后')
    except Exception as e:
        print(f'[警告] 导出彩色Excel失败: {e}')


if __name__ == '__main__':
    main()