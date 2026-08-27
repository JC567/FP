# -*- coding: utf-8 -*-
"""行业分类映射（东方财富行业板块）。

来源：akshare 行业板块列表 + 各板块成分股，构成 代码→行业名称 的映射，
落库到 stock_db.vr_stocks(industry) 做永久缓存（首次抓取约需数十次网络请求，
之后直接读库，不触网）。
"""
import time
import stock_db as db


def build_industry_map():
    """抓取全部行业板块成分股，返回 {代码(6位): 行业名称}。网络失败返回 {}。"""
    import akshare as ak
    out = {}
    try:
        boards = ak.stock_board_industry_name_em()
    except Exception:
        return out
    if boards is None or boards.empty:
        return out
    board_col = next((c for c in boards.columns if '名称' in str(c)), None)
    if board_col is None:
        return out
    for b in boards[board_col].astype(str).tolist():
        try:
            cons = ak.stock_board_industry_cons_em(symbol=b)
        except Exception:
            cons = None
        if cons is None or cons.empty:
            time.sleep(0.05)
            continue
        code_col = next((c for c in cons.columns if str(c) == '代码'), None)
        if code_col is None:
            time.sleep(0.05)
            continue
        for code in cons[code_col].astype(str).tolist():
            out[str(code).zfill(6)] = b
        time.sleep(0.05)
    return out


def ensure_industry_map(conn=None, refresh=False):
    """返回 {代码: 行业名称}；优先读库缓存，缓存为空(或 refresh)时抓取并落库。"""
    own = conn is None
    if own:
        conn = db.connect()
    try:
        if not refresh:
            cached = db.get_industry_map(conn)
            if cached:
                return cached
        mp = build_industry_map()
        if mp:
            rows = [(code, '', ind, '', '', '') for code, ind in mp.items()]
            db.save_vr_stocks(conn, rows)
        return mp
    finally:
        if own:
            conn.close()


if __name__ == '__main__':
    m = ensure_industry_map()
    print(f'行业映射数量: {len(m)}')
    for c in ('600519', '605368', '600210'):
        print(c, '->', m.get(c))
