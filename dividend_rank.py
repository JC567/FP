# -*- coding: utf-8 -*-
"""A股分红率排名

计算规则：
- 分红率 = 上一个自然年（2025）内每股分红合计 / 当日收盘价
- 分红筛选：股权登记日在 2025-01-01 ~ 2025-12-31、方案已实施、现金分红比例 > 0
- 分红数据来源：东财分红送配，覆盖股权登记日在 2025 年内的多个报告期
  （20240930/20241231/20250331/20250630/20250930），同一笔按 代码+登记日 去重
  每股分红合计 = 各期现金分红比例(每10股派现金) / 10 之和
- 最新分红率：基于当日收盘价；昨日分红率：基于昨日收盘价（昨收）
- 分红率涨跌幅 = 最新分红率 - 昨日分红率

附加筛选：
1. 近5年每年都有分红：财政年度 2020~2024 年报均存在现金分红（分红连续性）
2. 排除 ST 股票；仅保留沪深主板（排除创业板、科创板、北交所）
3. 筛选条件：最新分红率 > 3.0%
"""
import sys
import io
import time
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    sys.stdout.reconfigure(encoding='utf-8')   # 幂等，避免子进程下二次包装产生乱码
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import akshare as ak
import pandas as pd
import stock_db as db
import div_hist

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
os.makedirs(OUT, exist_ok=True)

REPORT_DATES = ['20240930', '20241231', '20250331', '20250630', '20250930']
CONTINUITY_YEARS = [f'{y}1231' for y in range(2020, 2025)]  # 近5年(2020~2024)连续分红
RATE_DATE = ('2025-01-01', '2025-12-31')
SZSH_MAINBOARD_PREFIX = {'60', '00'}                  # 沪深主板：沪6(600/601/603/605)、深00(000/001/002/003)
THRESHOLD = 3.0                                         # 最新分红率筛选阈值(%)


def get_code(series):
    return series.astype(str).str.replace(r'\D', '', regex=True).str.zfill(6)


def fetch_fhps(date):
    df = ak.stock_fhps_em(date=date)
    df = df.rename(columns={c: str(c) for c in df.columns})
    return df[['代码', '名称', '现金分红-现金分红比例', '股权登记日', '方案进度']].copy()


def robust_fetch(date):
    for i in range(4):
        try:
            return fetch_fhps(date)
        except Exception as e:
            print(f'[重试] 报告期 {date} 第{i+1}次失败: {e}')
            time.sleep(4)
    raise RuntimeError(f'报告期 {date} 获取失败')


def get_report(conn, report_date):
    """读取某报告期的分红数据；本地无则远程抓取并永久缓存。"""
    df = db.get_dividend(conn, report_date)
    if df is not None:
        print(f'本地缓存报告期 {report_date}（{len(df)} 只）')
        return df
    raw = robust_fetch(report_date)
    df = raw.copy()
    df['现金分红比例'] = pd.to_numeric(df['现金分红-现金分红比例'], errors='coerce')
    df['股权登记日'] = df['股权登记日'].astype(str)
    keep = ['代码', '名称', '现金分红比例', '股权登记日', '方案进度']
    df = df[keep]
    db.save_dividend(conn, report_date, df)
    print(f'已抓取并缓存报告期 {report_date}（{len(df)} 只）')
    return df


def build_dividend():
    """2025 年内每股分红合计（年报+中报）。"""
    conn = db.connect()
    df = pd.concat([get_report(conn, d) for d in REPORT_DATES], ignore_index=True)
    conn.close()
    df['股权登记日'] = pd.to_datetime(df['股权登记日'], errors='coerce')

    # 同一笔分红可能在多个报告期重复出现，按 代码+股权登记日 去重
    df = df.drop_duplicates(subset=['代码', '股权登记日'], keep='first')

    ok = (
        df['股权登记日'].notna()
        & (df['股权登记日'] >= RATE_DATE[0])
        & (df['股权登记日'] <= RATE_DATE[1])
        & (df['现金分红比例'] > 0)
        & df['方案进度'].astype(str).str.contains('实施')
    )
    dm = df[ok].copy()
    dm['每股分红'] = dm['现金分红比例'] / 10.0

    per = (
        dm.groupby('代码')
        .agg(名称=('名称', 'first'), 每股分红合计=('每股分红', 'sum'))
        .reset_index()
    )
    per['代码'] = get_code(per['代码'])
    return per


def continuous_dividend_codes():
    """近5年（2020~2024 年报）每年都有现金分红的股票代码集合。"""
    conn = db.connect()
    yearly = {}
    for d in CONTINUITY_YEARS:
        df = get_report(conn, d)
        codes = set(get_code(df[df['现金分红比例'] > 0]['代码']))
        yearly[d] = codes
        print(f'近5年分红检查 {d}: {len(codes)} 只有现金分红')
    conn.close()
    common = set.intersection(*yearly.values())
    print(f'连续5年分红（{len(common)} 只）')
    return common


def fetch_spot():
    """全市场最新价/昨收，优先用本地今日快照；否则抓新浪/东财并存库。"""
    conn = db.connect()
    cached = db.get_spot(conn)
    if cached is not None and db.get_meta(conn, 'spot_fetch_date') == db.today():
        print('行情: 使用本地今日快照')
        conn.close()
        return cached[['代码', '最新价', '昨收']]

    s = None
    sources = [('新浪', ak.stock_zh_a_spot), ('东财', ak.stock_zh_a_spot_em)]
    for label, fn in sources:
        for i in range(6):
            try:
                s = fn()
                print(f'行情来源: {label}')
                break
            except Exception:
                time.sleep(5)
        if s is not None:
            break

    if s is None:
        if cached is not None:
            print('实时行情获取失败，使用本地最近一次快照')
            conn.close()
            return cached[['代码', '最新价', '昨收']]
        raise RuntimeError('实时行情获取失败且本地无快照')

    s['代码'] = get_code(s['代码'])
    keep = ['代码'] + [c for c in s.columns if str(c) in ('最新价', '昨收', '现价')]
    s = s[keep].copy()
    for c in s.columns[1:]:
        s[c] = pd.to_numeric(s[c], errors='coerce')
    s = s.rename(columns={'现价': '最新价'})
    s = s[s['最新价'] > 0]
    s = s[['代码', '最新价', '昨收']].copy()
    db.save_spot(conn, s.assign(名称=s['代码']), db.today())
    conn.close()
    return s


PE_CACHE = os.path.join(OUT, 'pe_percentile_cache.csv')


def fetch_daily(code):
    """东财逐日 PE(TTM)/市净率（约8.6年，2093个交易日）。返回 df(日期, value=PE, pb=PB)。"""
    for i in range(4):
        try:
            df = ak.stock_value_em(symbol=code)
            d = df.rename(columns={'数据日期': '日期'})[['日期', 'PE(TTM)', '市净率']].copy()
            d = d.rename(columns={'PE(TTM)': 'value', '市净率': 'pb'})
            d['日期'] = pd.to_datetime(d['日期']).astype(str)
            d['value'] = pd.to_numeric(d['value'], errors='coerce')
            d['pb'] = pd.to_numeric(d['pb'], errors='coerce')
            return d[['日期', 'value', 'pb']]
        except Exception:
            time.sleep(2)
    return None


def _current_pb(conn, code, raw):
    if raw is not None:
        pbv = raw['pb'].astype(float).dropna()
        if not pbv.empty:
            return float(pbv.iloc[-1])
    pbh = db.get_pb(conn, code)
    if pbh is not None:
        pbv = pbh['value'].astype(float).dropna()
        if not pbv.empty:
            return float(pbv.iloc[-1])
    return None


def add_pe_percentile(codes):
    """基于东财逐日 PE 序列计算当前 PE-TTM 排名百分位（雪球口径），并返回当前 PE/PB。

    百分位 = 历史样本中低于当前PE的天数 / 总样本天数 × 100。
    逐日序列（PE/PB）落库到 pe_hist / pb_hist，本地已有则直接复用，精度更高。
    返回 (pct列表, 当前PE列表, 当前PB列表)。
    """
    conn = db.connect()
    ready = db.get_pe_ready(conn)
    pct_out, pe_out, pb_out = [], [], []
    newly = []
    total = len(codes)
    for i, code in enumerate(codes, 1):
        raw = None
        h = db.get_pe(conn, code)
        if h is None or code not in ready:
            raw = fetch_daily(code)
            if raw is None or raw['value'].astype(float).dropna().empty:
                pct_out.append(pd.NA); pe_out.append(pd.NA); pb_out.append(pd.NA)
                time.sleep(0.1)
                continue
            db.replace_pe(conn, code, raw[['日期', 'value']].dropna())
            db.replace_pb(conn, code, raw[['日期', 'pb']].dropna().rename(columns={'pb': 'value'}))
            newly.append(code)
            h = raw
        vals = h['value'].astype(float).dropna()
        cur = vals.iloc[-1]
        pct_out.append(round(float((vals < cur).mean() * 100), 2))
        pe_out.append(cur)
        pb_out.append(_current_pb(conn, code, raw))
        time.sleep(0.1)
        if i % 25 == 0 or i == total:
            print(f'[PE进度] {i}/{total}')
    if newly:
        db.mark_pe_ready(conn, newly)
    conn.close()
    return pct_out, pe_out, pb_out


def fetch_growth5(code):
    """抓取最近5个完整会计年度的 (年份, 营业总收入, 净利润)。返回 [(year, rev, np)]。"""
    for i in range(4):
        try:
            df = ak.stock_financial_abstract(symbol=code)
            df = df.rename(columns={c: str(c).strip() for c in df.columns})
            df['指标'] = df['指标'].astype(str).str.strip()
            rev_row = df.loc[df['指标'] == '营业总收入']
            np_row = df.loc[df['指标'] == '净利润']
            periods = [c for c in df.columns if c not in ('选项', '指标') and str(c).endswith('1231')]
            periods = sorted(periods)[-5:]   # 最近5个完整年度
            if rev_row.empty or np_row.empty or len(periods) < 5:
                return None
            rev = pd.to_numeric(rev_row.iloc[0][periods], errors='coerce')
            np_ = pd.to_numeric(np_row.iloc[0][periods], errors='coerce')
            return [(int(c[:4]), float(r), float(n)) for c, r, n in zip(periods, rev, np_) if pd.notna(r) and pd.notna(n)]
        except Exception:
            time.sleep(2)
    return None


def growth_flag(years, rev, np_):
    """判断是否满足近5年增长。

    规则：
      1. 5年内任何一年的营收、净利润均 > 0（不允许为负）。
      2. 上一年(最新) 营收与净利润 均 > 5年前(最早) 相应值（整体趋势增长）。
      3. 中间年份中"下降年份" <= 2（下降年份 = 营收与净利润均较上一年下降）。
    满足 -> 是，否则 -> 否。
    """
    if len(years) < 5:
        return '否'
    r, n = list(rev), list(np_)
    last5 = list(zip(r[-5:], n[-5:]))
    if any(rr <= 0 or pp <= 0 for rr, pp in last5):
        return '否'
    latest, first = last5[-1], last5[0]
    if latest[0] <= first[0] or latest[1] <= first[1]:
        return '否'
    down = 0
    prev = last5[0]
    for y in last5[1:-1]:            # 中间年份
        if y[0] < prev[0] and y[1] < prev[1]:
            down += 1
        prev = y
    return '是' if down <= 2 else '否'


def add_growth_flag(codes):
    """计算"是否满足近5年增长"，缓存年度财务数据到 finance5，返回 是/否 列表。

    首次运行对缺数据的股票并发抓取（多线程），之后全部读本地缓存，显著提速。
    """
    conn = db.connect()
    need = []
    for c in codes:
        r = db.get_finance5(conn, c)
        if r is None or len(r) < 5:
            need.append(c)
    if need:
        print(f'需要抓取近5年财务数据的股票: {len(need)}/{len(codes)}（多线程并发）')
        results = {}
        with ThreadPoolExecutor(max_workers=8) as ex:
            fut = {ex.submit(fetch_growth5, c): c for c in need}
            for k, f in enumerate(as_completed(fut), 1):
                c = fut[f]
                try:
                    results[c] = f.result()
                except Exception:
                    results[c] = None
                if k % 25 == 0 or k == len(need):
                    print(f'[抓取进度] {k}/{len(need)}')
        for c in need:
            raw = results.get(c)
            if raw and len(raw) >= 5:
                db.replace_finance5(conn, c, raw)

    out = []
    total = len(codes)
    for i, code in enumerate(codes, 1):
        rows = db.get_finance5(conn, code)
        if rows is None or len(rows) < 5:
            out.append('否')
        else:
            data = [(int(r[0]), float(r[1]), float(r[2])) for r in rows.itertuples(index=False)]
            out.append(growth_flag([r[0] for r in data], [r[1] for r in data], [r[2] for r in data]))
        if i % 25 == 0 or i == total:
            print(f'[增长进度] {i}/{total}')
    conn.close()
    return out


def add_val_percentiles(codes):
    """计算 近10年股息率百分位(日频口径) + 近10年分红率百分位(现金分红总额/归母净利润)。

    首次运行对缺缓存股票并行抓取（多线程），再顺序落库+计算；之后全部读本地缓存，提速。
    返回 (股息率百分位列, 分红率百分位列)。
    """
    conn = db.connect()
    missing = []
    for c in codes:
        fhps = db.get_div_hist(conn, c)
        npd = db.get_fin_np(conn, c)
        price = db.get_price_hist(conn, c)
        if fhps is None or npd is None or price is None:
            missing.append(c)
    conn.close()
    fetched = {}
    if missing:
        print(f'需要抓取历史估值数据的股票: {len(missing)}/{len(codes)}（多线程并发）')
        fetched = {}
        with ThreadPoolExecutor(max_workers=5) as ex:
            fut = {ex.submit(div_hist.fetch_all, c): c for c in missing}
            for k, f in enumerate(as_completed(fut), 1):
                c = fut[f]
                try:
                    fetched[c] = f.result()
                except Exception:
                    fetched[c] = None
                if k % 25 == 0 or k == len(missing):
                    print(f'[抓取进度] {k}/{len(missing)}')

    conn = db.connect()
    dy_out, pp_out = [], []
    total = len(codes)
    for i, code in enumerate(codes, 1):
        if code in fetched and fetched[code]:
            fhps, npd, price = fetched[code]
            div_hist._store_cached(conn, code, fhps, npd, price)
        else:
            fhps, npd, price = div_hist._load_cached(conn, code)
        dy_pct, pp_pct = div_hist.compute_from_data(fhps, npd, price)
        dy_out.append(dy_pct)
        pp_out.append(pp_pct)
        if i % 25 == 0 or i == total:
            print(f'[估值百分位] {i}/{total}')
    conn.close()
    return dy_out, pp_out


def _compute_eps_payout_ratios(codes):
    """批量计算 EPS 口径分红率：每股年度分红合计 / 每股收益(基本EPS) × 100。"""
    import stock_db as _db
    conn = _db.connect()
    result = {}
    for code in codes:
        code = str(code).zfill(6)
        try:
            div_rows = pd.read_sql_query(
                'SELECT SUBSTR(report_date,1,4) AS year, SUM(per_share) AS ps '
                'FROM div_hist WHERE code=? GROUP BY year',
                conn, params=(code,))
            eps_rows = pd.read_sql_query(
                'SELECT year, eps FROM fin_np WHERE code=?',
                conn, params=(code,))
            if div_rows.empty or eps_rows.empty:
                continue
            m = div_rows.merge(eps_rows, on='year', how='inner')
            m = m[m['eps'] > 0]
            if m.empty:
                continue
            last = m.sort_values('year').iloc[-1]
            payout = float(last['ps']) / float(last['eps']) * 100.0
            result[code] = round(payout, 2)
        except Exception:
            continue
    conn.close()
    return result


def main():
    per = build_dividend()
    continuous = continuous_dividend_codes()
    spot = fetch_spot()

    merged = per.merge(spot, on='代码', how='inner')
    # 仅保留沪深主板，排除创业板 300/301、科创板 688/689、北交所
    merged = merged[merged['代码'].str[:2].isin(SZSH_MAINBOARD_PREFIX)]
    # 排除 ST
    merged = merged[~merged['名称'].astype(str).str.contains('ST')]
    # 近5年分红未中断
    merged = merged[merged['代码'].isin(continuous)]

    merged['最新分红率'] = merged['每股分红合计'] / merged['最新价'] * 100.0
    merged['昨日分红率'] = merged['每股分红合计'] / merged['昨收'] * 100.0

    res = merged[merged['最新分红率'] > THRESHOLD].copy()
    res = res.sort_values('最新分红率', ascending=False).reset_index(drop=True)
    res.insert(0, '排名', res.index + 1)

    print('正在计算近10年PE百分位（首次较慢，之后走缓存）...')
    pct, cur_pe, cur_pb = add_pe_percentile(res['代码'].tolist())
    print('正在计算近5年增长（营收/净利润）...')
    growth = add_growth_flag(res['代码'].tolist())
    print('正在计算近10年股息率/分红率百分位（首次较慢，之后走缓存）...')
    dy_pct, pp_pct = add_val_percentiles(res['代码'].tolist())
    # 在昨日分红率之后插入 当前PE、当前PB、是否满足近5年增长、近10年PE百分位、
    # 近10年股息率百分位、近10年分红率百分位
    base = res.columns.get_loc('昨日分红率')
    res.insert(base + 1, '当前PE', cur_pe)
    res.insert(base + 2, '当前PB', cur_pb)
    res.insert(base + 3, '是否满足近5年增长', growth)
    res.insert(base + 4, '近10年PE百分位', pct)
    res.insert(base + 5, '近10年股息率百分位', dy_pct)
    res.insert(base + 6, '近10年分红率百分位', pp_pct)
    ok_n = int(pd.Series(pct).notna().sum())
    print(f'近10年PE百分位计算完成: {ok_n}/{len(res)} 只')
    ok_dy = int(pd.Series(dy_pct).notna().sum())
    ok_pp = int(pd.Series(pp_pct).notna().sum())
    print(f'近10年股息率/分红率百分位计算完成: 股息率 {ok_dy}/{len(res)} 只, 分红率 {ok_pp}/{len(res)} 只')

    # 计算 EPS 口径分红率（= 每股年度分红合计 / 每股收益 × 100）
    print('正在计算 EPS 口径分红率...')
    eps_payout = _compute_eps_payout_ratios(res['代码'].tolist())
    res['EPS分红率'] = res['代码'].astype(str).str.zfill(6).map(lambda c: eps_payout.get(c, pd.NA))

    print(f'\n最新分红率 > {THRESHOLD}% 的股票共 {len(res)} 只\n')
    cols = ['排名', '代码', '名称', '最新分红率', '昨日分红率', 'EPS分红率', '当前PE', '当前PB',
            '是否满足近5年增长', '近10年PE百分位', '近10年股息率百分位', '近10年分红率百分位',
            '每股分红合计', '最新价']
    print(res[cols].head(12).to_string(index=False, float_format=lambda x: f'{x:.4f}'))

    # 输出时去掉"昨收"列（内部计算仍需要）
    out_res = res.drop(columns=['昨收'], errors='ignore')
    out_res.to_csv(os.path.join(OUT, '分红率排名.csv'), index=False, encoding='utf-8-sig')
    print(f'\n结果已保存 -> data/分红率排名.csv（共 {len(out_res)} 只）')


if __name__ == '__main__':
    main()