# -*- coding: utf-8 -*-
"""本地历史数据存储（SQLite，位于 D:\\stockdata\\hist.db）。

表结构：
- dividend(report_date, code, name, cash_ratio, reg_date, progress)  分红数据，按报告期缓存（历史稳定，永久缓存）
- spot(code, name, price, pre_close, fetch_date)                     最新行情快照（按日期新鲜度复用）
- pe_hist(code, trade_date, pe_ttm)                                  近10年 PE-TTM 序列（历史稳定，永久缓存）
- meta(key, value)                                                   元信息（如行情抓取日期）

若环境变量 STOCK_DB 指定了路径则优先使用，否则用默认 D 盘路径。
"""
import os
import sqlite3
import datetime

import pandas as pd

DB_PATH = os.environ.get('STOCK_DB', r'D:\stockdata\hist.db')


def connect():
    d = os.path.dirname(DB_PATH)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS dividend(
            report_date TEXT, code TEXT, name TEXT, cash_ratio REAL,
            reg_date TEXT, progress TEXT,
            PRIMARY KEY(report_date, code));
        CREATE TABLE IF NOT EXISTS spot(
            code TEXT PRIMARY KEY, name TEXT, price REAL, pre_close REAL,
            fetch_date TEXT);
        CREATE TABLE IF NOT EXISTS pe_hist(
            code TEXT, trade_date TEXT, pe_ttm REAL,
            PRIMARY KEY(code, trade_date));
        CREATE TABLE IF NOT EXISTS pb_hist(
            code TEXT, trade_date TEXT, pb REAL,
            PRIMARY KEY(code, trade_date));
        CREATE TABLE IF NOT EXISTS finance5(
            code TEXT, year INTEGER, revenue REAL, net_profit REAL,
            PRIMARY KEY(code, year));
        CREATE TABLE IF NOT EXISTS div_hist(
            code TEXT, report_date TEXT, per_share REAL, total_share REAL,
            ann_date TEXT, PRIMARY KEY(code, report_date));
        CREATE TABLE IF NOT EXISTS fin_np(
            code TEXT, year INTEGER, eps REAL,
            PRIMARY KEY(code, year));
        CREATE TABLE IF NOT EXISTS price_hist(
            code TEXT, trade_date TEXT, close REAL,
            PRIMARY KEY(code, trade_date));
        CREATE TABLE IF NOT EXISTS valuation_current(
            code TEXT PRIMARY KEY, pe_ttm REAL, pb REAL, fetch_date TEXT);
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS vr_stocks(
            symbol TEXT PRIMARY KEY, name TEXT, industry TEXT, industry_type TEXT,
            list_date TEXT, delist_date TEXT);
        CREATE TABLE IF NOT EXISTS vr_prices(
            symbol TEXT, date TEXT, close REAL, adj_close REAL, volume REAL,
            market_cap REAL, PRIMARY KEY(symbol, date));
        CREATE TABLE IF NOT EXISTS vr_valuation(
            symbol TEXT, date TEXT, pe_ttm REAL, pe_valid INTEGER, pe_outlier_flag INTEGER,
            source TEXT, PRIMARY KEY(symbol, date));
        CREATE TABLE IF NOT EXISTS vr_financials(
            symbol TEXT, report_period TEXT, announcement_date TEXT, revenue REAL,
            net_profit_attr REAL, eps_basic REAL, ocf REAL, total_assets REAL,
            total_liabilities REAL, int_bearing_debt REAL, industry_type TEXT,
            data_source TEXT, PRIMARY KEY(symbol, report_period, announcement_date));
        CREATE TABLE IF NOT EXISTS vr_dividends(
            symbol TEXT, report_period TEXT, dividend_type TEXT, per_share_cash REAL,
            announce_date TEXT, implement_date TEXT, reg_date TEXT,
            PRIMARY KEY(symbol, report_period, dividend_type));
        CREATE TABLE IF NOT EXISTS vr_macro(
            date TEXT PRIMARY KEY, cn10y REAL);
        CREATE TABLE IF NOT EXISTS vr_industry(
            industry_type TEXT PRIMARY KEY, score REAL, sub_scores TEXT, as_of TEXT);
        CREATE TABLE IF NOT EXISTS vr_analysis(
            symbol TEXT, analysis_date TEXT, mode TEXT, json_result TEXT,
            PRIMARY KEY(symbol, analysis_date, mode));
        CREATE TABLE IF NOT EXISTS vr_backtest(
            id INTEGER PRIMARY KEY AUTOINCREMENT, strategy TEXT, symbol TEXT,
            start TEXT, end TEXT, mode TEXT, metrics_json TEXT);
    ''')
    conn.commit()
    # 迁移：旧版 fin_np 用 net_profit 列，改为 eps 列
    cols = [r[1] for r in conn.execute('PRAGMA table_info(fin_np)').fetchall()]
    if cols and 'eps' not in cols:
        conn.execute('DROP TABLE fin_np')
        conn.execute('CREATE TABLE IF NOT EXISTS fin_np('
                     'code TEXT, year INTEGER, eps REAL, PRIMARY KEY(code, year));')
        conn.commit()
    # 迁移(P0-C)：vr_financials 需保留财务修订版本 → 主键须含 announcement_date。
    # 旧表主键仅 (symbol, report_period) 会覆盖修订，需重建。
    fin_cols = conn.execute('PRAGMA table_info(vr_financials)').fetchall()
    pk_cols = [c[1] for c in sorted(fin_cols, key=lambda c: c[5]) if c[5] > 0]
    if pk_cols and pk_cols != ['symbol', 'report_period', 'announcement_date']:
        conn.execute('ALTER TABLE vr_financials RENAME TO vr_financials_old')
        conn.execute('CREATE TABLE vr_financials('
                     'symbol TEXT, report_period TEXT, announcement_date TEXT, revenue REAL,'
                     'net_profit_attr REAL, eps_basic REAL, ocf REAL, total_assets REAL,'
                     'total_liabilities REAL, int_bearing_debt REAL, industry_type TEXT,'
                     'data_source TEXT, PRIMARY KEY(symbol, report_period, announcement_date))')
        conn.execute('INSERT INTO vr_financials(symbol, report_period, announcement_date, revenue,'
                     'net_profit_attr, eps_basic, ocf, total_assets, total_liabilities,'
                     'int_bearing_debt, industry_type, data_source) '
                     'SELECT symbol, report_period, announcement_date, revenue, net_profit_attr,'
                     'eps_basic, ocf, total_assets, total_liabilities, int_bearing_debt,'
                     'industry_type, data_source FROM vr_financials_old')
        conn.execute('DROP TABLE vr_financials_old')
        conn.commit()
    return conn


# ---------- 分红数据 ----------

def get_dividend(conn, report_date):
    df = pd.read_sql_query(
        'SELECT code, name, cash_ratio, reg_date, progress FROM dividend '
        'WHERE report_date=?', conn, params=(report_date,))
    if df.empty:
        return None
    return df.rename(columns={'code': '代码', 'name': '名称',
                              'cash_ratio': '现金分红比例',
                              'reg_date': '股权登记日',
                              'progress': '方案进度'})


def save_dividend(conn, report_date, df):
    rows = []
    for r in df.itertuples(index=False):
        cash = None if pd.isna(r.现金分红比例) else float(r.现金分红比例)
        rows.append((report_date, str(r.代码), str(r.名称), cash,
                     str(r.股权登记日), str(r.方案进度)))
    conn.executemany(
        'INSERT OR REPLACE INTO dividend VALUES (?,?,?,?,?,?)', rows)
    conn.commit()


# ---------- 行情快照 ----------

def get_spot(conn):
    df = pd.read_sql_query(
        'SELECT code, name, price, pre_close FROM spot', conn)
    if df.empty:
        return None
    return df.rename(columns={'code': '代码', 'name': '名称',
                              'price': '最新价', 'pre_close': '昨收'})


def save_spot(conn, df, fetch_date):
    rows = [(str(r.代码), str(r.名称), float(r.最新价), float(r.昨收), fetch_date)
            for r in df.itertuples(index=False)]
    conn.executemany('INSERT OR REPLACE INTO spot VALUES (?,?,?,?,?)', rows)
    set_meta(conn, 'spot_fetch_date', fetch_date)
    conn.commit()


# ---------- PE 历史 ----------

def get_pe(conn, code):
    df = pd.read_sql_query(
        'SELECT trade_date AS 日期, pe_ttm AS value FROM pe_hist WHERE code=?',
        conn, params=(code,)).sort_values('日期')
    return df if not df.empty else None


def save_pe(conn, code, df):
    rows = [(code, str(r.日期), float(r.value)) for r in df.itertuples(index=False)]
    conn.executemany('INSERT OR REPLACE INTO pe_hist VALUES (?,?,?)', rows)
    conn.commit()


def replace_pe(conn, code, df):
    """删除该代码原有全部 PE 后整段重写（用于从低密度切换为逐日数据）。"""
    conn.execute('DELETE FROM pe_hist WHERE code=?', (code,))
    save_pe(conn, code, df)


# ---------- 行业分类（vr_stocks，缓存） ----------

def save_vr_stocks(conn, rows):
    """rows: [(symbol, name, industry, industry_type, list_date, delist_date)]"""
    conn.executemany(
        'INSERT OR REPLACE INTO vr_stocks VALUES (?,?,?,?,?,?)',
        [(str(r[0]), str(r[1]) if r[1] is not None else '',
          str(r[2]) if r[2] is not None else '', str(r[3]) if r[3] is not None else '',
          str(r[4]) if r[4] is not None else '', str(r[5]) if r[5] is not None else '')
         for r in rows])
    conn.commit()


def get_industry_map(conn):
    """返回 {代码: 行业名称} 缓存（来自 vr_stocks.industry）。"""
    df = pd.read_sql_query('SELECT symbol, industry FROM vr_stocks', conn)
    return dict(zip(df['symbol'].astype(str), df['industry'].astype(str))) if not df.empty else {}


# ---------- PB 历史 ----------

def get_pb(conn, code):
    df = pd.read_sql_query(
        'SELECT trade_date AS 日期, pb AS value FROM pb_hist WHERE code=?',
        conn, params=(code,)).sort_values('日期')
    return df if not df.empty else None


def replace_pb(conn, code, df):
    conn.execute('DELETE FROM pb_hist WHERE code=?', (code,))
    rows = [(code, str(r.日期), float(r.value)) for r in df.itertuples(index=False)]
    conn.executemany('INSERT OR REPLACE INTO pb_hist VALUES (?,?,?)', rows)
    conn.commit()


# ---------- 逐日就绪标记 ----------

def get_pe_ready(conn):
    v = get_meta(conn, 'pe_daily_ready')
    return set(v.split(',')) if v else set()


def mark_pe_ready(conn, codes):
    ready = get_pe_ready(conn) | set(codes)
    set_meta(conn, 'pe_daily_ready', ','.join(sorted(ready)))


# ---------- 近5年营收/净利润 ----------

def get_finance5(conn, code):
    df = pd.read_sql_query(
        'SELECT year, revenue, net_profit FROM finance5 WHERE code=? ORDER BY year',
        conn, params=(code,))
    return df if not df.empty else None


def replace_finance5(conn, code, rows):
    """rows: [(year, revenue, net_profit)]，删除旧数据后整段重写。"""
    conn.execute('DELETE FROM finance5 WHERE code=?', (code,))
    conn.executemany('INSERT OR REPLACE INTO finance5 VALUES (?,?,?,?)',
                     [(code, int(y), float(r), float(n)) for y, r, n in rows])
    conn.commit()


def get_growth_ready(conn):
    v = get_meta(conn, 'growth_ready')
    return set(v.split(',')) if v else set()


def mark_growth_ready(conn, codes):
    ready = get_growth_ready(conn) | set(codes)
    set_meta(conn, 'growth_ready', ','.join(sorted(ready)))


# ---------- 历史分红明细（年度股息率/分红率用） ----------

def get_div_hist(conn, code):
    df = pd.read_sql_query(
        'SELECT report_date, per_share, total_share, ann_date FROM div_hist '
        'WHERE code=?', conn, params=(code,))
    return df if not df.empty else None


def replace_div_hist(conn, code, rows):
    """rows: [(report_date, per_share, ann_date)]"""
    conn.execute('DELETE FROM div_hist WHERE code=?', (code,))
    conn.executemany('INSERT OR REPLACE INTO div_hist VALUES (?,?,?,?,?)',
                     [(code, str(r[0]), float(r[1]), None, str(r[2])) for r in rows])
    conn.commit()


# ---------- 历史每股收益（分红率用） ----------

def get_fin_np(conn, code):
    df = pd.read_sql_query(
        'SELECT year, eps FROM fin_np WHERE code=? ORDER BY year',
        conn, params=(code,))
    return df if not df.empty else None


def replace_fin_np(conn, code, rows):
    """rows: [(year, eps)]"""
    conn.execute('DELETE FROM fin_np WHERE code=?', (code,))
    conn.executemany('INSERT OR REPLACE INTO fin_np VALUES (?,?,?)',
                     [(code, int(y), None if e is None else float(e)) for y, e in rows])
    conn.commit()


# ---------- 历史日线收盘（年度股息率用） ----------

def get_price_hist(conn, code):
    df = pd.read_sql_query(
        'SELECT trade_date AS 日期, close FROM price_hist WHERE code=?',
        conn, params=(code,)).sort_values('日期')
    return df if not df.empty else None


def replace_price_hist(conn, code, df):
    """df: DataFrame[日期, close]"""
    conn.execute('DELETE FROM price_hist WHERE code=?', (code,))
    conn.executemany('INSERT OR REPLACE INTO price_hist VALUES (?,?,?)',
                     [(code, str(r.日期), float(r.close)) for r in df.itertuples(index=False)])
    conn.commit()


# ---------- 当前估值（PE/PB） ----------

def get_valuation(conn, code):
    row = conn.execute(
        'SELECT pe_ttm, pb FROM valuation_current WHERE code=?', (code,)).fetchone()
    return (row[0], row[1]) if row else None


def save_valuation(conn, code, pe_ttm, pb):
    conn.execute('INSERT OR REPLACE INTO valuation_current VALUES (?,?,?,?)',
                 (code, pe_ttm, pb, today()))
    conn.commit()


# ---------- 元信息 ----------

def get_meta(conn, key):
    row = conn.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
    return row[0] if row else None


def set_meta(conn, key, value):
    conn.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (key, str(value)))
    conn.commit()


def today():
    return datetime.date.today().isoformat()


# ---------- valresearch 数据存取 ----------

def get_vr_prices(conn, symbol, start, end):
    df = pd.read_sql_query(
        'SELECT date, close, adj_close, volume FROM vr_prices WHERE symbol=? '
        'AND date>=? AND date<=? ORDER BY date',
        conn, params=(symbol, str(start), str(end)))
    if df.empty:
        return None
    df['date'] = pd.to_datetime(df['date'])
    return df


def save_vr_prices(conn, symbol, df):
    conn.execute('DELETE FROM vr_prices WHERE symbol=?', (symbol,))
    rows = [(symbol, str(r.date), float(r.close),
             None if pd.isna(r.adj_close) else float(r.adj_close),
             None if pd.isna(r.volume) else float(r.volume), None)
            for r in df.itertuples(index=False)]
    conn.executemany('INSERT OR REPLACE INTO vr_prices VALUES (?,?,?,?,?,?)', rows)
    conn.commit()


def get_vr_financials(conn, symbol):
    df = pd.read_sql_query(
        'SELECT report_period, announcement_date, revenue, net_profit_attr, eps_basic, '
        'ocf, total_assets, total_liabilities, int_bearing_debt, industry_type, data_source '
        'FROM vr_financials WHERE symbol=? ORDER BY report_period, announcement_date',
        conn, params=(symbol,))
    return df if not df.empty else None


def save_vr_financials(conn, symbol, df):
    conn.execute('DELETE FROM vr_financials WHERE symbol=?', (symbol,))
    rows = []
    for r in df.itertuples(index=False):
        rows.append((symbol, str(r.report_period), str(r.announcement_date),
                     _opt(r.revenue), _opt(r.net_profit_attr), _opt(r.eps_basic),
                     _opt(r.ocf), _opt(r.total_assets), _opt(r.total_liabilities),
                     _opt(r.int_bearing_debt), str(r.industry_type or ''), str(r.data_source or '')))
    conn.executemany('INSERT OR REPLACE INTO vr_financials VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', rows)
    conn.commit()


def get_vr_dividends(conn, symbol):
    df = pd.read_sql_query(
        'SELECT report_period, dividend_type, per_share_cash, announce_date, implement_date, reg_date '
        'FROM vr_dividends WHERE symbol=? ORDER BY implement_date',
        conn, params=(symbol,))
    return df if not df.empty else None


def save_vr_dividends(conn, symbol, df):
    conn.execute('DELETE FROM vr_dividends WHERE symbol=?', (symbol,))
    rows = []
    for r in df.itertuples(index=False):
        rows.append((symbol, str(r.report_period), str(r.dividend_type),
                     float(r.per_share_cash), str(r.announce_date or ''), str(r.implement_date or ''),
                     str(r.reg_date or '')))
    conn.executemany('INSERT OR REPLACE INTO vr_dividends VALUES (?,?,?,?,?,?,?)', rows)
    conn.commit()


def get_vr_valuation(conn, symbol):
    df = pd.read_sql_query(
        'SELECT date, pe_ttm, pe_valid, pe_outlier_flag, source FROM vr_valuation '
        'WHERE symbol=? ORDER BY date',
        conn, params=(symbol,))
    if df.empty:
        return None
    df['date'] = pd.to_datetime(df['date'])
    return df


def save_vr_valuation(conn, symbol, df):
    conn.execute('DELETE FROM vr_valuation WHERE symbol=?', (symbol,))
    rows = []
    for r in df.itertuples(index=False):
        rows.append((symbol, str(r.date),
                     None if pd.isna(r.pe_ttm) else float(r.pe_ttm),
                     int(r.pe_valid), int(r.pe_outlier_flag), str(r.source or '')))
    conn.executemany('INSERT OR REPLACE INTO vr_valuation VALUES (?,?,?,?,?,?)', rows)
    conn.commit()


def save_vr_analysis(conn, symbol, analysis_date, mode, json_result):
    conn.execute('INSERT OR REPLACE INTO vr_analysis VALUES (?,?,?,?)',
                 (symbol, analysis_date, mode, json_result))
    conn.commit()


def get_vr_analysis(conn, symbol, analysis_date, mode):
    row = conn.execute(
        'SELECT json_result FROM vr_analysis WHERE symbol=? AND analysis_date=? AND mode=?',
        (symbol, analysis_date, mode)).fetchone()
    return row[0] if row else None


def save_vr_backtest(conn, strategy, symbol, start, end, mode, metrics_json):
    conn.execute('INSERT INTO vr_backtest (strategy,symbol,start,end,mode,metrics_json) '
                 'VALUES (?,?,?,?,?,?)',
                 (strategy, symbol, str(start), str(end), mode, metrics_json))
    conn.commit()


def save_vr_macro(conn, df):
    conn.execute('DELETE FROM vr_macro')
    rows = [(str(r.date), float(r.cn10y)) for r in df.itertuples(index=False)]
    conn.executemany('INSERT OR REPLACE INTO vr_macro VALUES (?,?)', rows)
    conn.commit()


def get_vr_macro(conn):
    df = pd.read_sql_query('SELECT date, cn10y FROM vr_macro ORDER BY date', conn)
    return df if not df.empty else None


def _opt(v):
    import pandas as _pd
    if v is None or _pd.isna(v):
        return None
    try:
        return float(v)
    except Exception:
        return None