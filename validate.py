# -*- coding: utf-8 -*-
"""验证 data/分红率排名.csv 是否满足全部规则。"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd, os

FP = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', '分红率排名.csv')
out = pd.read_csv(FP, encoding='utf-8-sig')
out['代码'] = out['代码'].astype(str).str.replace(r'\D', '', regex=True).str.zfill(6)
out['名称'] = out['名称'].astype(str)

issues = []

# --- 1. 沪深A股 & 非ST ---
bad_code = out[~out['代码'].str[:1].isin({'6', '0', '3'})]
if len(bad_code): issues.append(f'含非沪深股票 {len(bad_code)} 只')
st = out[out['名称'].str.contains('ST')]
if len(st): issues.append(f'含ST {len(st)} 只')

# --- 2. 最新分红率 > 3 ---
low = out[out['最新分红率'] <= 3.0]
if len(low): issues.append(f'最新分红率<=3% {len(low)} 只')

# --- 3. 内部一致性 ---
import numpy as np
ok_late = np.isclose(out['最新分红率'], out['每股分红合计'] / out['最新价'] * 100, rtol=1e-6, atol=1e-4)
ok_yes = np.isclose(out['昨日分红率'], out['每股分红合计'] / out['昨收'] * 100, rtol=1e-6, atol=1e-4)
ok_diff = np.isclose(out['分红率涨跌幅'], out['最新分红率'] - out['昨日分红率'], rtol=1e-6, atol=1e-4)
if not ok_late.all(): issues.append(f'最新分红率与收盘价不一致 {int((~ok_late).sum())} 行')
if not ok_yes.all(): issues.append(f'昨日分红率与昨收不一致 {int((~ok_yes).sum())} 行')
if not ok_diff.all(): issues.append(f'涨跌幅≠最新-昨日 {int((~ok_diff).sum())} 行')
if not (out['每股分红合计'] > 0).all(): issues.append('存在每股分红<=0')

# --- 4. 每股分红合计与2025分红源核对（缓存年报+中报）---
BASE = r'C:\Users\NINGMEI\AppData\Local\Temp\opencode\fhps'
def getcode(s): return s.astype(str).str.replace(r'\D', '', regex=True).str.zfill(6)
frames = []
for d in ['20240930', '20241231', '20250331', '20250630', '20250930']:
    df = pd.read_csv(BASE + f'\\{d}.csv', encoding='utf-8-sig')
    df['股权登记日'] = pd.to_datetime(df['股权登记日'], errors='coerce')
    df['cash'] = pd.to_numeric(df['现金分红-现金分红比例'], errors='coerce')
    df['代码'] = getcode(df['代码'])
    frames.append(df)
b = pd.concat(frames, ignore_index=True)
b = b.drop_duplicates(subset=['代码', '股权登记日'], keep='first')
okd = (b['股权登记日'] >= '2025-01-01') & (b['股权登记日'] <= '2025-12-31') & (b['cash'] > 0) & b['方案进度'].astype(str).str.contains('实施')
dm = b[okd].copy()
dm['每股分红'] = dm['cash'] / 10
per = dm.groupby('代码')['每股分红'].sum().rename('合计核对').reset_index()
chk = out.merge(per, on='代码', how='left')
mismatch = chk[~np.isclose(chk['每股分红合计'], chk['合计核对'], rtol=1e-6, atol=1e-6)]
if len(mismatch): issues.append(f'每股分红合计与源数据不一致 {len(mismatch)} 只')
if chk['合计核对'].isna().any(): issues.append('存在无法在2025分红源中对上的股票')

# --- 5. 近5年分红连续性（重拉2020-2024年报核对）---
import akshare as ak, time
CONT = [f'{y}1231' for y in range(2020, 2025)]
yearly = {}
for d in CONT:
    for i in range(4):
        try:
            df = ak.stock_fhps_em(date=d)
            df = df.rename(columns={c: str(c) for c in df.columns})
            df['cash'] = pd.to_numeric(df['现金分红-现金分红比例'], errors='coerce')
            yearly[d] = set(getcode(df[df['cash'] > 0]['代码']))
            break
        except Exception:
            time.sleep(5)
continuous = set.intersection(*yearly.values())
miss_con = set(out['代码']) - continuous
if miss_con: issues.append(f'存在近5年分红中断的股票 {len(miss_con)} 只: {list(miss_con)[:8]}')

# --- 汇总 ---
print('结果文件共', len(out), '行')
if issues:
    print('发现不合格项：')
    for i in issues:
        print(' -', i)
    sys.exit(1)
else:
    print('全部通过：满足 沪深A股、非ST、最新分红率>3%、每股分红正确、近5年分红连续')
    print('排名1~10：')
    print(out[['排名', '代码', '名称', '最新分红率']].head(10).to_string(index=False,
                                                                         float_format=lambda x: f'{x:.2f}'))