# -*- coding: utf-8 -*-
"""金融行业(银行/保险/券商)专用基本面质量(0-100)（P1-2）。

通用模型的杠杆/现金流分项对金融机构不适用：
- 银行天然高杠杆：通用 leverage_score 会误伤，故不计入；
- 银行 OCF 无意义：THS 摘要也无 OCF，通用 cashflow 恒 DATA_INSUFFICIENT，故不计入。

银行模型改用可用字段：
- ROE（归母净利/股东权益）水平与稳定性
- 权益比率(equity/total_assets) 作为资本充足代理（<6% 警示）
- 盈利稳定性（复用通用 earnings）
- 分红持续性（复用通用 dividend_sustainability）
缺失项一律不伪造；ROE/权益比率缺任一 → 该项取 0 并打 DATA_INSUFFICIENT 警告。
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from valresearch.config import get_config
from valresearch.fundamental.earnings import earnings_stability
from valresearch.fundamental.dividend_sust import dividend_sustainability

_BANKING = ('银行', '保险', '证券', '金融')

# 银行业资产负债表（新浪）缓存：A股财报接口(net_profit/total_assets)常缺余额表，
# 而巴菲特式银行分析必须有 ROE/资本充足/破净(PB)，故单独用新浪资产负债表补足（按 symbol 缓存）。
_BS_CACHE = {}


def is_financial(industry_type: Optional[str]) -> bool:
    return industry_type in _BANKING


def _num(x):
    try:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return None
        v = float(x)
        return v if pd.notna(v) else None
    except Exception:
        return None


def _ann_of(r):
    a = str(r.get('公告日期', '') or '')
    if len(a) >= 8 and a[:8].isdigit():
        return a[:8]
    return None


def _sina_balance_sheet(symbol: str):
    """新浪资产负债表（合并期末），解析出每期 资产总计/负债合计/归母权益 + 报告期/公告日。
    返回 DataFrame[rp, ann, ta, tl, eq] 或 None（不可得）。"""
    if symbol in _BS_CACHE:
        return _BS_CACHE[symbol]
    df = None
    try:
        import akshare as ak
        sina = ('sh' if symbol.startswith('6') else 'sz') + symbol
        raw = ak.stock_financial_report_sina(stock=sina, symbol='资产负债表')
        if raw is not None and not raw.empty:
            rp_cols = [c for c in raw.columns if '报告' in str(c)]
            rp_col = rp_cols[0] if rp_cols else None
            ann_col = next((c for c in raw.columns if '公告日期' in str(c)), None)
            ta_col = next((c for c in raw.columns if '资产总计' in str(c)), None)
            tl_col = next((c for c in raw.columns if '负债合计' in str(c)), None)
            eq_col = next((c for c in raw.columns if '归属于母公司股东的权益' in str(c)), None)
            rows = []
            for _, r in raw.iterrows():
                rp = str(r.get(rp_col, '') or '') if rp_col else ''
                if len(rp) >= 8 and rp[:8].isdigit():
                    rows.append({
                        'rp': rp[:8],
                        'ann': (str(r.get(ann_col, '') or '')[:8] if ann_col else None),
                        'ta': _num(r.get(ta_col)) if ta_col else None,
                        'tl': _num(r.get(tl_col)) if tl_col else None,
                        'eq': _num(r.get(eq_col)) if eq_col else None,
                    })
            if rows:
                df = pd.DataFrame(rows)
    except Exception:
        df = None
    _BS_CACHE[symbol] = df
    return df


def bank_equity_asof(symbol: str, t):
    """PIT 取截至 t 最新的 资产总计/负债合计/归母权益；不可得返回 (None,None,None)。"""
    df = _sina_balance_sheet(symbol)
    if df is None or df.empty:
        return (None, None, None)
    ts = pd.Timestamp(t).strftime('%Y%m%d')
    has_ann = df['ann'].notna().any()
    if has_ann:
        cand = df[df['ann'].notna() & (df['ann'] <= ts)]
    else:
        cand = df[df['rp'] <= ts]
    if cand.empty:
        cand = df
    cand = cand.sort_values('rp')          # 新浪资产负债表为"最新在前"，按报告期升序取最新一期
    row = cand.iloc[-1]
    return (row['ta'], row['tl'], row['eq'])


def bank_roe_asof(fin, symbol: str, t):
    """银行业 ROE = 归母净利(PIT,来自利润表 fin) / 归母权益(PIT,来自新浪资产负债表)。缺一则 None。"""
    np_ = None
    row = _last_annual(fin, t)
    if row is not None:
        np_ = _num(row.get('net_profit_attr'))
    eq = bank_equity_asof(symbol, t)[2]
    if np_ is None or eq is None or eq <= 0:
        return None
    return float(np_) / float(eq)


def bank_equity_ratio_asof(fin, symbol: str, t):
    """银行业权益比率 = 归母权益 / 资产总计(PIT,新浪资产负债表)。"""
    ta, tl, eq = bank_equity_asof(symbol, t)
    if eq is None or ta is None or ta <= 0:
        return None
    return float(eq) / float(ta)


def _get_db_path():
    from pathlib import Path
    return Path(__file__).resolve().parents[2] / 'data' / 'annual_reports.db'


def _get_standalone_equity_from_db(symbol: str, report_date: str) -> Optional[float]:
    """从本地年报数据库读取母公司单独口径股东权益合计。"""
    try:
        import sqlite3
        db_path = _get_db_path()
        if not db_path.exists():
            return None
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute('''
            SELECT metric_value FROM financial_data fd
            JOIN annual_reports ar ON fd.report_id = ar.id
            WHERE ar.symbol = ? AND fd.metric_name = '股东权益合计'
            AND fd.period = ? AND fd.is_consolidated = 0
        ''', (symbol, report_date))
        row = cursor.fetchone()
        conn.close()
        if row and row[0] is not None:
            return float(row[0])
    except Exception:
        pass
    return None


def _get_standalone_shares_from_db(symbol: str, report_date: str) -> Optional[float]:
    """从本地年报数据库读取母公司单独口径股本。"""
    try:
        import sqlite3
        db_path = _get_db_path()
        if not db_path.exists():
            return None
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute('''
            SELECT metric_value FROM financial_data fd
            JOIN annual_reports ar ON fd.report_id = ar.id
            WHERE ar.symbol = ? AND fd.metric_name = '股本'
            AND fd.period = ? AND fd.is_consolidated = 0
        ''', (symbol, report_date))
        row = cursor.fetchone()
        conn.close()
        if row and row[0] is not None:
            return float(row[0])
    except Exception:
        pass
    return None


def _get_latest_standalone_equity_from_db(symbol: str, asof_date: str) -> Optional[tuple]:
    """从本地年报数据库读取截至 asof_date 的最新单独口径权益和股本。"""
    try:
        import sqlite3
        db_path = _get_db_path()
        if not db_path.exists():
            return None
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        # 先查权益
        cursor.execute('''
            SELECT fd.metric_value, fd.period FROM financial_data fd
            JOIN annual_reports ar ON fd.report_id = ar.id
            WHERE ar.symbol = ? AND fd.metric_name = '股东权益合计'
            AND fd.period <= ? AND fd.is_consolidated = 0
            ORDER BY fd.period DESC LIMIT 1
        ''', (symbol, asof_date))
        eq_row = cursor.fetchone()
        if not eq_row:
            return None
        eq = float(eq_row[0])
        eq_period = eq_row[1]
        # 再查同期股本
        cursor.execute('''
            SELECT metric_value FROM financial_data fd
            JOIN annual_reports ar ON fd.report_id = ar.id
            WHERE ar.symbol = ? AND fd.metric_name = '股本'
            AND fd.period = ? AND fd.is_consolidated = 0
        ''', (symbol, eq_period))
        sh_row = cursor.fetchone()
        conn.close()
        if sh_row and sh_row[0] is not None:
            return eq, float(sh_row[0]), eq_period
        conn.close()
    except Exception:
        pass
    return None


def bank_book_asof(fin, symbol: str, t):
    """银行业每股净资产 = 归母权益 / 近似股本(归母净利/基本EPS)。

    关键：权益必须与净利/股本同属一份报告（同报告期），否则 BVPS/PB 失真。
    优先：本地年报/半年报数据库的单独口径权益与股本（最准确，单独口径）；
    次选：Sina 资产负债表按报告期匹配（合并口径，可能失真）；
    兜底：bank_equity_asof（最新 PIT，合并口径，可能失真）。"""
    row = _last_annual(fin, t)
    if row is None:
        return None
    np_ = _num(row.get('net_profit_attr'))
    eps = _num(row.get('eps_basic'))
    if np_ is None or eps is None or float(eps) <= 0 or float(np_) <= 0:
        return None
    shares = float(np_) / float(eps)
    if shares <= 0:
        return None

    # 1) 优先：本地年报/半年报数据库的单独口径权益与股本（最准确，单独口径）
    # 获取截至 t 的最新单独口径权益和股本（含年报、半年报）
    ts = pd.Timestamp(t).strftime('%Y-%m-%d')
    latest = _get_latest_standalone_equity_from_db(symbol, ts)
    if latest is not None:
        eq, db_shares, eq_period = latest
        if db_shares is not None and db_shares > 0:
            shares = db_shares
    else:
        eq = None

    # 2) 次选：Sina 资产负债表按年报期匹配（合并口径，可能失真）
    if eq is None:
        rptime = str(row.get('report_period', '') or '')[:10]
        df = _sina_balance_sheet(symbol)
        if df is not None and not df.empty and rptime:
            rp_short = rptime.replace('-', '')[:8]
            match = df[df['rp'] == rp_short]
            if not match.empty:
                eq = match.iloc[0]['eq']

    # 3) 兜底：最新 PIT（合并口径，可能失真）
    if eq is None:
        eq = bank_equity_asof(symbol, t)[2]
    if eq is None:
        return None
    return {'book_equity': float(eq), 'shares': shares, 'bvps': float(eq) / shares}


def _last_annual(fin, t=None) -> Optional[pd.Series]:
    """最近年报（P0-B：只取 announcement_date<=t 的财报，修订感知每期取当时最新版本）。
    t=None 表示全部可见（仍做修订去重）。"""
    from valresearch.data.pit import annual_versions_pit
    ann = annual_versions_pit(fin, t)
    if ann is None or ann.empty:
        return None
    return ann.iloc[-1]


def roe_latest(fin, t=None) -> Optional[float]:
    row = _last_annual(fin, t)
    if row is None:
        return None
    np_, ta, tl = row.get('net_profit_attr'), row.get('total_assets'), row.get('total_liabilities')
    if np_ is None or ta is None or tl is None or pd.isna(np_) or pd.isna(ta) or pd.isna(tl):
        return None
    eq = float(ta) - float(tl)
    if eq <= 0:
        return None
    return float(np_) / eq


def equity_ratio_latest(fin, t=None) -> Optional[float]:
    row = _last_annual(fin, t)
    if row is None:
        return None
    ta, tl = row.get('total_assets'), row.get('total_liabilities')
    if ta is None or tl is None or pd.isna(ta) or pd.isna(tl) or ta <= 0:
        return None
    return (float(ta) - float(tl)) / float(ta)


def book_value_latest(fin, t=None, symbol=None) -> Optional[dict]:
    """时点PIT 最近年报的账面权益与每股净资产(破净代理)。返回 {book_equity, shares, bvps} 或 None。

    优先用新浪资产负债表取归母权益(余额表更全)；近似股本 = 归母净利 / 基本EPS（加权股本代理）。
    字段缺失或不合理(权益<=0 / EPS<=0)→ None，绝不伪造。
    """
    if symbol is not None:
        bv = bank_book_asof(fin, symbol, t)
        if bv is not None:
            return bv
        # 回退到 fin 余额（可能为空）
    row = _last_annual(fin, t)
    if row is None:
        return None
    np_ = row.get('net_profit_attr')
    ta = row.get('total_assets')
    tl = row.get('total_liabilities')
    eps = row.get('eps_basic')
    if np_ is None or ta is None or tl is None or eps is None:
        return None
    if pd.isna(np_) or pd.isna(ta) or pd.isna(tl) or pd.isna(eps):
        return None
    eq = float(ta) - float(tl)
    if eq <= 0 or float(eps) <= 0 or float(np_) <= 0:
        return None
    shares = float(np_) / float(eps)          # 近似总股本
    if shares <= 0:
        return None
    bvps = eq / shares
    return {'book_equity': eq, 'shares': shares, 'bvps': float(bvps)}


def banking_quality(fin, div, t, industry_type='银行', cfg=None, symbol=None) -> dict:
    cfg = cfg or get_config('balanced')
    w = cfg.get('banking', {})
    warnings, flags = [], []
    # ROE/权益比率：优先用新浪资产负债表补足（利润表常缺余额），再回退 fin（可能为空）
    roe = bank_roe_asof(fin, symbol, t) if symbol else roe_latest(fin, t)
    eqr = bank_equity_ratio_asof(fin, symbol, t) if symbol else equity_ratio_latest(fin, t)
    earn = earnings_stability(fin, t)
    divs = dividend_sustainability(div, fin, t)

    if roe is None:
        warnings.append('银行模型：ROE 数据不足(DATA_INSUFFICIENT)')
    if eqr is None:
        warnings.append('银行模型：权益比率数据不足(DATA_INSUFFICIENT)')
    if eqr is not None and eqr < 0.06:
        flags.append('资本充足率偏低(权益/总资产<6%)')

    def _scale_roe(r):
        if r is None:
            return 0.0
        return round(100.0 * min(1.0, max(0.0, r / 0.15)), 1)   # ROE 15% 即满分

    def _scale_eqr(r):
        if r is None:
            return 0.0
        return round(100.0 * min(1.0, max(0.0, (r - 0.05) / 0.10)), 1)  # 5%→0, 15%→100

    s_roe = _scale_roe(roe)
    s_eqr = _scale_eqr(eqr)
    score = (w.get('w_roe', 0.30) * s_roe
             + w.get('w_equity', 0.25) * s_eqr
             + w.get('w_earnings', 0.20) * earn['score']
             + w.get('w_dividend', 0.25) * divs['score'])
    return {
        'score': round(score, 1),
        'roe': round(roe, 4) if roe is not None else None,
        'equity_ratio': round(eqr, 4) if eqr is not None else None,
        'warnings': warnings,
        'flags': flags,
        'detail': {'earnings': {k: earn[k] for k in ('cagr_revenue', 'cagr_np', 'cagr_eps',
                                                     'np_vol', 'np_max_drawdown', 'consecutive_declines')},
                    'dividend': {k: divs[k] for k in ('consecutive_years', 'dps_cagr_5y', 'dps_cagr_10y',
                                                      'avg_payout_5y', 'avg_payout_10y', 'unsustainable')}},
    }