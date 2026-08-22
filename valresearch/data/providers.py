# -*- coding: utf-8 -*-
"""数据源抽象 + AkShare 实现。

统一接口（未来可替换 Tushare/Wind/自建库）：
- MarketDataProvider.get_price(symbol, start, end)
- FinancialDataProvider.get_financials(symbol, ...)
- DividendDataProvider.get_dividends(symbol, ...)
- MacroDataProvider.get_bond_yield(start, end)
- IndustryDataProvider.get_industry(symbol)

实现会写入本地 SQLite（vr_* 表）作缓存；无法取得的数据返回 None 并在 warnings 标注，
绝不伪造数据。价格：估值一律用 close(原始价)，adj_close(后复权) 仅用于收益分析。
"""
from __future__ import annotations

import datetime
import threading
import time
from typing import Dict, List, Optional

import pandas as pd
import akshare as ak

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import stock_db as db

# 巨潮/同花顺接口内部使用 py_mini_racer(V8)，多线程并发会段错误，须串行化。
_MINI_LOCK = threading.Lock()
_AK_LOCK = threading.Lock()   # 全局抓取串行，避免东财/百度限流与 V8 崩溃


def _retry(fn, *args, tries=3, sleep=1.0, **kwargs):
    last = None
    for i in range(tries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last = e
            time.sleep(sleep * (i + 1))
    raise last


def _today():
    return datetime.date.today().strftime('%Y%m%d')


class DataError(RuntimeError):
    """数据不可得/缺失。"""
    pass


class DataProvider:
    """市场数据：日线原始价 + 后复权价。新浪为主（东财已限流）。"""
    def get_price(self, symbol: str, start: str = '20050101',
                  end: str = None) -> Optional[pd.DataFrame]:
        if end is None:
            end = _today()
        conn = db.connect()
        try:
            cached = db.get_vr_prices(conn, symbol, start, end)
            if cached is not None and not cached.empty:
                # P0-11: 缓存必须覆盖查询窗口，否则视为不完整 → 重新抓取
                from valresearch.data.cache_coverage import price_cache_covers
                _ok, _reason = price_cache_covers(cached['date'].min(), cached['date'].max(),
                                                  start, end)
                if _ok:
                    return cached
        finally:
            conn.close()
        raw = None
        hfq = None
        sina = ('sh' if symbol.startswith('6') else 'sz') + symbol
        try:
            with _AK_LOCK:
                r = _retry(ak.stock_zh_a_daily, symbol=sina, start_date=start,
                           end_date=end, adjust='')
            if r is not None and not r.empty:
                raw = r[['date', 'close', 'volume']].copy()
        except Exception:
            raw = None
        try:
            with _AK_LOCK:
                h = _retry(ak.stock_zh_a_daily, symbol=sina, start_date=start,
                           end_date=end, adjust='hfq')
            if h is not None and not h.empty:
                hfq = h[['date', 'close']].copy()
        except Exception:
            hfq = None
        if raw is None:
            return None
        raw['date'] = pd.to_datetime(raw['date'])
        out = raw.rename(columns={'date': 'date', 'close': 'close', 'volume': 'volume'}).copy()
        if hfq is not None:
            hfq['date'] = pd.to_datetime(hfq['date'])
            hfq = hfq.rename(columns={'close': 'adj_close'})
            out = out.merge(hfq, on='date', how='left')
        else:
            out['adj_close'] = None
        out = out.dropna(subset=['close']).sort_values('date')
        conn = db.connect()
        try:
            db.save_vr_prices(conn, symbol, out)
        finally:
            conn.close()
        return out[['date', 'close', 'adj_close', 'volume']].copy()

    def get_pe_ttm(self, symbol: str) -> Optional[pd.DataFrame]:
        """PE_TTM 日频序列：百度估值(period='全部' 自上市日)。返回 DataFrame[date, pe_ttm, pe_valid, source]。
        标注：百度历史 PE 为 as-reported，存在轻微前视，打 PIT 近似标记。"""
        conn = db.connect()
        try:
            cached = db.get_vr_valuation(conn, symbol)
            if cached is not None and not cached.empty:
                return cached
        finally:
            conn.close()
        df = None
        with _AK_LOCK:
            try:
                df = _retry(ak.stock_zh_valuation_baidu, symbol=symbol,
                            indicator='市盈率(TTM)', period='全部')
            except Exception:
                df = None
        if df is None or df.empty:
            return None
        df = df.rename(columns={c: str(c).strip() for c in df.columns})
        date_col = next((c for c in df.columns if '日期' in c or c.lower() == 'date'), None)
        val_col = next((c for c in df.columns if '值' in c or '市盈率' in c or c.lower() == 'value'), None)
        if date_col is None or val_col is None:
            return None
        out = pd.DataFrame({
            'date': pd.to_datetime(df[date_col]),
            'pe_ttm': pd.to_numeric(df[val_col], errors='coerce'),
        })
        out['pe_valid'] = (out['pe_ttm'] > 0).astype(int)
        out['pe_outlier_flag'] = 0
        out['source'] = 'baidu_pit_approx'
        out = out.dropna(subset=['date']).sort_values('date')
        conn = db.connect()
        try:
            db.save_vr_valuation(conn, symbol, out)
        finally:
            conn.close()
        return out[['date', 'pe_ttm', 'pe_valid', 'pe_outlier_flag', 'source']].copy()


class FinancialDataProvider:
    """财务数据：同花顺 stock_financial_abstract_ths（营收/净利/每股收益/OCF/资产/负债）。
    公告日：东财业绩快报公告日(如可得)，否则按法规截止日近似并打 DATA_CALIBER_RISK。"""
    # 报表类型→公告截止日（法规）近似
    _DEADLINE = {  # 报告期末月最后一天 -> 最晚披露日(月,日)
        '3-31': (4, 30), '6-30': (8, 31), '9-30': (10, 31), '12-31': (4, 30)}

    def get_financials(self, symbol: str, start_year: int = 2013) -> Optional[pd.DataFrame]:
        conn = db.connect()
        try:
            cached = db.get_vr_financials(conn, symbol)
            if cached is not None and not cached.empty:
                # P0-11: 缓存须含足够新的公告，否则视为缺近期数据 → 重新抓取
                from valresearch.data.cache_coverage import financial_cache_covers
                _ok, _reason = financial_cache_covers(cached['announcement_date'].max())
                if _ok:
                    return cached
        finally:
            conn.close()
        df = None
        with _MINI_LOCK:
            try:
                df = _retry(ak.stock_financial_abstract_ths, symbol=symbol)
            except Exception:
                df = None
        if df is None or df.empty:
            return None
        df = df.rename(columns={c: str(c).strip() for c in df.columns})
        if '报告期' not in df.columns:
            return None
        df['报告期'] = df['报告期'].astype(str).str.strip()
        ann_est = {}
        rows = []
        for _, r in df.iterrows():
            rp = r['报告期']
            try:
                dt = pd.to_datetime(rp)
            except Exception:
                continue
            if dt.year < start_year:
                continue
            if dt.month == 3 or dt.month == 6 or dt.month == 9 or dt.month == 12:
                ann = self._estimate_announce(dt, ann_est)
                rows.append({
                    'report_period': rp,
                    'announcement_date': ann,
                    'announcement_date_source': 'ESTIMATED',  # P0-3: 当前无真实公告日源，诚实标注
                    'revenue': _num(r.get('营业总收入')),
                    'net_profit_attr': _num(r.get('净利润')),
                    'eps_basic': _num(r.get('基本每股收益')),
                    'ocf': None,  # ths 仅给每股经营现金流，缺总股本无法换算总量 → DATA_INSUFFICIENT，不伪造
                    'total_assets': _num(r.get('总资产')),
                    'total_liabilities': _num(r.get('总负债')) if '总负债' in df.columns else None,
                    'int_bearing_debt': None,
                    'industry_type': None,
                    'data_source': 'ths',
                })
        if not rows:
            return None
        # P0-C: 保留所有版本（同一报告期可能有多份修订，announcement_date 不同），
        # 不做 drop_duplicates('report_period')，避免删除修订版本。
        out = pd.DataFrame(rows).sort_values(['report_period', 'announcement_date'])
        conn = db.connect()
        try:
            db.save_vr_financials(conn, symbol, out)
        finally:
            conn.close()
        return out

    def _estimate_announce(self, period: datetime.datetime, memo: Dict) -> str:
        # 一季报/年报 4-30；半年报 8-31；三季报 10-31；年报(12-31) 次年的 4-30
        if period.month == 12:
            est = datetime.datetime(period.year + 1, 4, 30)
        elif period.month == 9:
            est = datetime.datetime(period.year, 10, 31)
        elif period.month == 6:
            est = datetime.datetime(period.year, 8, 31)
        else:
            est = datetime.datetime(period.year, 4, 30)
        memo[period.strftime('%Y-%m-%d')] = est.strftime('%Y-%m-%d')
        return est.strftime('%Y-%m-%d')


def _num(v) -> Optional[float]:
    try:
        s = str(v).strip()
    except Exception:
        return None
    if s in ('', 'None', 'nan', 'NaN', '--'):
        return None
    mult = 1.0
    if s.endswith('亿'):
        mult, s = 1e8, s[:-1]
    elif s.endswith('万'):
        mult, s = 1e4, s[:-1]
    try:
        return float(s) * mult
    except Exception:
        return None


class DividendDataProvider:
    """分红数据：巨潮 stock_dividend_cninfo（含实施方案公告日 = implement_date）。
    公告日(announce_date)用实施方案公告日近似（已实施分红在实施日即公开，无前视）。"""
    def get_dividends(self, symbol: str) -> Optional[pd.DataFrame]:
        conn = db.connect()
        try:
            cached = db.get_vr_dividends(conn, symbol)
            if cached is not None and not cached.empty:
                # P0-11: 缓存须含足够新的实施日，否则视为缺近期分红 → 重新抓取
                from valresearch.data.cache_coverage import dividend_cache_covers
                _ok, _reason = dividend_cache_covers(cached['implement_date'].max())
                if _ok:
                    return cached
        finally:
            conn.close()
        df = None
        with _MINI_LOCK:
            try:
                df = _retry(ak.stock_dividend_cninfo, symbol=symbol)
            except Exception:
                df = None
        if df is None or df.empty:
            return None
        df = df.rename(columns={c: str(c).strip() for c in df.columns})
        out = []
        for _, r in df.iterrows():
            dps = _num(r.get('派息比例'))
            if dps is None or dps <= 0:
                continue
            impl = _as_date(r.get('实施方案公告日期'))
            if impl is None:
                continue
            out.append({
                'report_period': str(r.get('报告时间', '')).strip(),
                'dividend_type': str(r.get('分红类型', '')).strip(),
                'per_share_cash': dps / 10.0,
                'announce_date': impl,
                'implement_date': impl,
                'reg_date': _as_date(r.get('股权登记日')),
            })
        if not out:
            return None
        res = pd.DataFrame(out)
        conn = db.connect()
        try:
            db.save_vr_dividends(conn, symbol, res)
        finally:
            conn.close()
        return res


def _as_date(v):
    try:
        return pd.to_datetime(v).strftime('%Y-%m-%d')
    except Exception:
        return None


class MacroDataProvider:
    """10Y 国债收益率：bond_zh_us_rate（中国国债收益率10年）。"""
    _cache = None

    def get_bond_yield(self, start: str = '20050101', end: str = None) -> Optional[pd.DataFrame]:
        if self._cache is None:
            df = None
            with _AK_LOCK:
                try:
                    df = _retry(ak.bond_zh_us_rate)
                except Exception:
                    df = None
            if df is None or df.empty:
                return None
            df = df.rename(columns={c: str(c).strip() for c in df.columns})
            col = next((c for c in df.columns if '国债收益率10年' in str(c) and '中国' in str(c)), None)
            if col is None:
                return None
            self._cache = df[['日期', col]].rename(columns={'日期': 'date', col: 'cn10y'}).copy()
            self._cache['date'] = pd.to_datetime(self._cache['date'])
            self._cache['cn10y'] = pd.to_numeric(self._cache['cn10y'], errors='coerce')
            self._cache = self._cache.dropna(subset=['cn10y'])
        out = self._cache.copy()
        if start:
            out = out[out['date'] >= pd.to_datetime(start)]
        if end:
            out = out[out['date'] <= pd.to_datetime(end)]
        return out.sort_values('date')


class IndustryDataProvider:
    """行业/行业类型：优先东财 stock_individual_info_em(可得时)，否则按名称关键词推断，可配置覆盖。
    行业风险评分(0-100)为主观配置，不在此伪造。"""
    _BANK = ('银行', '招商银行', '工商银行', '建设银行', '农业银行', '中国银行', '交通银行', '邮储', '兴业', '浦发', '民生', '中信银行', '光大银行', '华夏银行', '平安银行')
    _INSUR = ('保险', '中国人寿', '中国平安', '新华保险', '中国太保', '中国人保', '天茂')
    _SEC = ('证券', '券商', '中信证券', '国泰', '海通', '华泰', '招商证券', '广发', '东方证券', '申万', '银河', '中金')
    _REAL = ('地产', '万科', '保利', '招商蛇口', '金地', '华侨城', '新城', '华夏幸福')

    def get_industry(self, symbol: str, name: str = '') -> Dict:
        info = {'industry': '', 'industry_type': '制造业', 'source': 'keyword-inference'}
        try:
            with _AK_LOCK:
                d = _retry(ak.stock_individual_info_em, symbol=symbol)
            if d is not None and not d.empty:
                m = dict(zip(d['item'].astype(str), d['value'].astype(str)))
                ind = m.get('行业')
                if ind:
                    info['industry'] = ind
                    info['source'] = 'east'
        except Exception:
            pass
        probe = (info.get('industry', '') + name)
        if any(k in probe for k in self._BANK):
            info['industry_type'] = '银行'
        elif any(k in probe for k in self._INSUR):
            info['industry_type'] = '保险'
        elif any(k in probe for k in self._SEC):
            info['industry_type'] = '证券'
        elif any(k in probe for k in self._REAL):
            info['industry_type'] = '地产'
        else:
            info['industry_type'] = '制造业'
        return info


def _providers_check():
    """Phase 1 冒烟：确认各 Provider 可实例化。"""
    return {
        'market': DataProvider(),
        'financial': FinancialDataProvider(),
        'dividend': DividendDataProvider(),
        'macro': MacroDataProvider(),
        'industry': IndustryDataProvider(),
    }