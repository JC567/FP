# -*- coding: utf-8 -*-
"""历史估值数据（年度股息率 / 分红率）共享计算模块。

口径（专业定义）：
- 股息率 (Dividend Yield) = 每股年度派息金额 ÷ 每股股价 × 100%
  采用"年度切换"：分子 = 最近一个已宣告会计年度的每股分红合计（含中期分红），
  在年报预案公告日切换；分母 = 当日收盘价。由此得到逐日股息率序列（平滑、无滚动窗口突刺）。
- 分红率 (Dividend Payout Ratio) = 现金分红总额 ÷ 归母净利润 × 100%
  等价每股口径 = 每股年度分红合计 ÷ 每股收益(基本EPS) × 100%（两者数学相等）。
- 百分位 = 当前值在近10年历史样本中低于当前值的比例 × 100（雪球/乐咕口径）。

数据来源（均为当前稳定可靠的接口）：
- 分红送配明细：ak.stock_dividend_cninfo（巨潮资讯，含派息比例/实施方案公告日期，自上市日）
- 每股收益：ak.stock_financial_abstract_ths（同花顺，基本每股收益，年报口径）
- 日线收盘：新浪 ak.stock_zh_a_daily（东财已限流，弃用）

以上均缓存到 SQLite（div_hist / fin_np / price_hist），历史稳定、永久复用。
"""
import datetime
import threading
import time

import numpy as np
import pandas as pd
import akshare as ak

import stock_db as db

_DAYS_10Y = 3650

# 巨潮/同花顺接口内部使用 py_mini_racer(V8)，多线程并发会段错误崩溃，须串行化。
_MINI_LOCK = threading.Lock()


def _retry(fn, *args, tries=3, sleep=1.0, **kwargs):
    """带重试的抓取：临时网络失败自动重试。"""
    last = None
    for i in range(tries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last = e
            time.sleep(sleep * (i + 1))
    raise last


def today_c():
    return datetime.date.today()


# ---------- 抓取 ----------

def _locked_cninfo(code):
    with _MINI_LOCK:
        return ak.stock_dividend_cninfo(symbol=code)


def _locked_ths(code):
    with _MINI_LOCK:
        return ak.stock_financial_abstract_ths(symbol=code)


def _locked_abstract(code):
    with _MINI_LOCK:
        return ak.stock_financial_abstract(symbol=code)


def fetch_fhps(code):
    """抓取单只股票全部已实施分红明细，返回 DataFrame[报告期, 每股分红, 预案公告日, 会计年度]。
    来源：巨潮资讯 stock_dividend_cninfo（派息比例=每10股派现）。"""
    df = _retry(lambda: _locked_cninfo(code))
    if df is None or df.empty:
        return None
    df = df.copy()
    df['每股分红'] = pd.to_numeric(df['派息比例'], errors='coerce') / 10.0
    df['预案公告日'] = pd.to_datetime(df['实施方案公告日期'], errors='coerce')
    df['报告期'] = df['报告时间'].astype(str).str.strip()
    df['会计年度'] = df['报告期'].str[:4]
    df = df[df['每股分红'] > 0]
    df = df[df['预案公告日'].notna()]
    if df.empty:
        return None
    return df[['报告期', '每股分红', '预案公告日', '会计年度']].copy()


def fetch_price(code):
    """抓取长历史日线（自2005或上市日），返回 DataFrame[日期, close]。新浪为主（东财已被限流）。"""
    sina = ('sh' if code.startswith('6') else 'sz') + code
    hist = None
    try:
        hd = _retry(ak.stock_zh_a_daily, symbol=sina, start_date='20050101',
                    end_date=today_c().strftime('%Y%m%d'), adjust='')
        if hd is not None and not hd.empty:
            hist = hd[['date', 'close']].copy()
    except Exception:
        hist = None
    if hist is None or hist.empty:
        return None
    hist = hist.rename(columns={'日期': '日期', 'date': '日期',
                                '收盘': 'close', 'close': 'close'})[['日期', 'close']].copy()
    hist['日期'] = pd.to_datetime(hist['日期'])
    hist['close'] = pd.to_numeric(hist['close'])
    hist = hist.dropna(subset=['日期', 'close']).sort_values('日期')
    return hist


def fetch_fin_np(code):
    """抓取历年每股收益（基本EPS，年报），返回 [(year, eps)]。来源：同花顺（退新浪 abstract）。"""
    try:
        df = _retry(lambda: _locked_ths(code))
    except Exception:
        df = None
    if df is None or df.empty:
        df = _retry(lambda: _locked_abstract(code))
        if df is None or df.empty:
            return None
        df = df.rename(columns={c: str(c).strip() for c in df.columns})
        df['指标'] = df['指标'].astype(str).str.strip()
        row = df.loc[df['指标'] == '每股收益']
        if row.empty:
            return None
        periods = [c for c in df.columns if c not in ('选项', '指标') and str(c).endswith('1231')]
        out = []
        for c in periods:
            v = pd.to_numeric(row.iloc[0][c], errors='coerce')
            if pd.notna(v):
                out.append((int(c[:4]), float(v)))
        return out or None
    df = df.rename(columns={c: str(c).strip() for c in df.columns})
    if '报告期' not in df.columns or '基本每股收益' not in df.columns:
        return None
    df['报告期'] = df['报告期'].astype(str).str.strip()
    ann = df[df['报告期'].str.endswith('12-31')].copy()
    ann = ann[pd.to_numeric(ann['基本每股收益'], errors='coerce').notna()]
    if ann.empty:
        return None
    out = []
    for _, r in ann.iterrows():
        out.append((int(r['报告期'][:4]), float(r['基本每股收益'])))
    return sorted(set(out)) or None


# ---------- 缓存读写 ----------

def fetch_all(code):
    """纯网络抓取（不落库），返回 (fhps, npd, price)，格式与 _load_cached 一致。"""
    fhps = fetch_fhps(code)
    eps_raw = fetch_fin_np(code)
    npd = None
    if eps_raw:
        npd = pd.DataFrame(eps_raw, columns=['year', 'eps'])
        npd = npd.rename(columns={'eps': '每股收益'}).copy()
        npd['会计年度'] = npd['year'].astype(str)
    price = fetch_price(code)
    return fhps, npd, price


def _load_cached(conn, code):
    fhps = db.get_div_hist(conn, code)
    if fhps is not None:
        fhps = fhps.rename(columns={'report_date': '报告期', 'per_share': '每股分红',
                                    'ann_date': '预案公告日'})
        fhps['预案公告日'] = pd.to_datetime(fhps['预案公告日'], errors='coerce')
        fhps['会计年度'] = fhps['报告期'].astype(str).str[:4]
    npd = db.get_fin_np(conn, code)
    if npd is not None:
        npd = npd.rename(columns={'eps': '每股收益'}).copy()
        npd['会计年度'] = npd['year'].astype(str)
    price = db.get_price_hist(conn, code)
    return fhps, npd, price


def _store_cached(conn, code, fhps, npd, price):
    if fhps is not None:
        db.replace_div_hist(conn, code, [(r.报告期, r.每股分红, r.预案公告日)
                                         for r in fhps.itertuples(index=False)])
    if npd is not None:
        db.replace_fin_np(conn, code, [(r.year, r.每股收益) for r in npd.itertuples(index=False)])
    if price is not None:
        db.replace_price_hist(conn, code, price[['日期', 'close']])


def ensure_data(conn, code):
    """确保 fhps / 归母净利润 / 日线 已缓存，返回 (fhps, npd, price)。"""
    fhps, npd, price = _load_cached(conn, code)
    if fhps is None or npd is None or price is None:
        raw_fhps, raw_npd, raw_price = fetch_all(code)
        fhps = raw_fhps if fhps is None else fhps
        npd = raw_npd if npd is None else npd
        price = raw_price if price is None else price
        _store_cached(conn, code, raw_fhps, raw_npd, raw_price)
    return fhps, npd, price


# ---------- 计算 ----------

def annual_switch(fhps):
    """按会计年度汇总每股分红合计，切换日=该年度最晚预案公告日。返回 DataFrame[会计年度, 每股分红, 切换日]。"""
    g = fhps[fhps['预案公告日'].notna()].copy()
    if g.empty:
        return None
    ann = (g.groupby('会计年度', as_index=False)
            .agg(每股分红=('每股分红', 'sum'), 切换日=('预案公告日', 'max')))
    return ann.sort_values('切换日')


def daily_yield_series(fhps, price):
    """逐日股息率（%）= 年度切换每股分红 / 当日收盘价 * 100。返回 DataFrame[日期, value]。"""
    ann = annual_switch(fhps)
    if ann is None or price is None or price.empty:
        return None
    sw = ann['切换日'].values.astype('datetime64[D]')
    amp = ann['每股分红'].values.astype(float)
    d = price['日期'].values.astype('datetime64[D]')
    idx = np.searchsorted(sw, d, side='right') - 1
    has = idx >= 0
    price = price.copy()
    price['value'] = np.where(has, amp[np.maximum(idx, 0)] / price['close'] * 100.0, np.nan)
    out = price[['日期', 'value']].dropna(subset=['value'])
    out = out[out['value'] > 0].sort_values('日期')
    out['日期'] = pd.to_datetime(out['日期'])
    return out


def payout_series(fhps, npd):
    """分红率（%）= 每股年度分红合计 / 每股收益(基本EPS) * 100（等价总额/归母净利润），按会计年度。
    返回 DataFrame[会计年度, 分红率, 切换日]。"""
    if fhps is None or npd is None or npd.empty:
        return None
    fy = (fhps.groupby('会计年度', as_index=False)
          .agg(每股分红=('每股分红', 'sum'), 切换日=('预案公告日', 'max')))
    m = fy.merge(npd[['会计年度', '每股收益']], on='会计年度', how='inner')
    m['分红率'] = m['每股分红'] / m['每股收益'] * 100.0
    m = m.dropna(subset=['分红率']).sort_values('切换日')
    return m if not m.empty else None


def percentile_10y(values, cur):
    """当前值在样本中的百分位（%）：低于当前值的比例 * 100。"""
    if values is None or len(values) == 0 or pd.isna(cur):
        return pd.NA
    vals = pd.to_numeric(values, errors='coerce').dropna()
    if vals.empty:
        return pd.NA
    return round(float((vals < float(cur)).mean() * 100), 2)


def compute_from_data(fhps, npd, price):
    """由 (fhps, npd, price) 计算 (近10年股息率百分位, 近10年分红率百分位)。"""
    dy_pct = payout_pct = pd.NA
    if fhps is not None and price is not None:
        dy = daily_yield_series(fhps, price)
        if dy is not None and not dy.empty:
            end = dy['日期'].iloc[-1]
            start = end - pd.Timedelta(days=_DAYS_10Y)
            w = dy[(dy['日期'] >= start) & (dy['日期'] <= end)]
            if w.empty:
                w = dy
            dy_pct = percentile_10y(w['value'], w['value'].iloc[-1])
    if fhps is not None and npd is not None:
        ps = payout_series(fhps, npd)
        if ps is not None and not ps.empty:
            last10 = ps.tail(10)
            payout_pct = percentile_10y(last10['分红率'], last10['分红率'].iloc[-1])
    return dy_pct, payout_pct


def compute_percentiles(code):
    """计算 (近10年股息率百分位, 近10年分红率百分位)。股息率=日频口径，分红率=总额/归母净利润。"""
    conn = db.connect()
    try:
        fhps, npd, price = ensure_data(conn, code)
        return compute_from_data(fhps, npd, price)
    finally:
        conn.close()


def get_daily_yield(code):
    """供图表使用：返回 DataFrame[日期, value]（逐日股息率 %）。"""
    conn = db.connect()
    try:
        fhps, npd, price = ensure_data(conn, code)
        if fhps is None or price is None:
            return None
        return daily_yield_series(fhps, price)
    finally:
        conn.close()


def get_payout_history(code):
    """供图表使用：返回 DataFrame[日期, value]（年度分红率 %，按切换日对齐到日期轴）。"""
    conn = db.connect()
    try:
        fhps, npd, price = ensure_data(conn, code)
        ps = payout_series(fhps, npd)
        if ps is None:
            return None
        out = ps[['切换日', '分红率']].rename(columns={'切换日': '日期', '分红率': 'value'})
        out = out.dropna(subset=['日期'])
        out['日期'] = pd.to_datetime(out['日期'])
        return out
    finally:
        conn.close()