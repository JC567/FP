# AI Development Context — A股红利/价值投资量化研究系统

> **本文档是给接手此项目的 AI 的完整上下文。** 读完本文档后，你应能理解项目全貌、设计约束、历史决策和开发规范，无需额外探索即可继续研发。

---

## 一、项目身份

- **项目名**: first-project（A股分红率排名 & 红利价值分位研究）
- **仓库**: `git@github.com:JC567/FP.git`
- **当前版本**: V1.6.1
- **语言**: Python 3.8+
- **包管理**: 无 pip install，直接运行；依赖见 `requirements.txt`
- **入口**:
  - `run_task.py` — 桌面程序（tkinter，4个页签）
  - `main_valresearch.py` — CLI 单股分析
  - `python -m valresearch` — 包级 CLI

---

## 二、项目目标

1. **1号任务 · 分红率排名**: 全市场扫描，输出分红率排名 CSV
2. **红利价值分位研究**: 单股深度分析——历史分位 + Gordon估值 + 基本面质量 + 价值陷阱 + 综合信号 + 价格区间 + 历史回测，生成九段式报告

**核心设计哲学**: 所有计算严格遵循 **Point-in-Time（PIT，无未来函数）**；数据缺失标注 `DATA_INSUFFICIENT`，**绝不伪造数据**。

---

## 三、25条铁律（不可违反）

| # | 铁律 | 具体要求 |
|---|------|---------|
| 1 | **无未来函数** | 所有计算只能用 `announcement_date <= t` 的数据 |
| 2 | **无 groupby().last()** | 财务版本选择必须用 `groupby('report_period')['ann_ts'].idxmax()` 整行选择，禁止跨列拼接 |
| 3 | **无伪造数据** | DATA_INSUFFICIENT 就是 DATA_INSUFFICIENT，不伪装成50分中性 |
| 4 | **无功能删除** | 每次修复只增不删（除非明确标记 DEPRECATED/LEGACY） |
| 5 | **GUI/CLI/API 兼容** | 修改必须同时兼容三种入口 |
| 6 | **每个模型修复必须有测试** | 修 bug 必须附带回归测试 |
| 7 | **README 公式=代码=测试** | 三者必须一致 |
| 8 | **PE 严格自算** | `PE = Price / EPS_TTM_PIT`，EPS<=0 → NaN，不使用外部历史PE |
| 9 | **分红率严格口径** | `现金分红总额TTM / 归母净利润TTM`，DPS/EPS 仅作交叉验证 |
| 10 | **零分红 = 真实0%** | 无分红是真实0%（参与分位计算），不是NaN |
| 11 | **TTM 唯一实现** | 全项目只有一套 TTM 算法，在 `pit.py` 中 |
| 12 | **report_period 标准化** | 所有日期比较使用 `normalize_report_period()` 统一格式 |
| 13 | **修订感知** | 同一报告期多版本时，按 `announcement_date` 选择当时最新版本 |
| 14 | **Gordon PIT** | `historical_eps_cagr()`、`roe_from_financials()`、`compute_growth()` 均带 asof 参数 |
| 15 | **银行 PIT** | `_last_annual(fin, t)` 只取 `announcement_date<=t` 的年报 |
| 16 | **分红持续性 PIT** | 分红数据按 `implement_date` 做 PIT |
| 17 | **显式排序** | 使用 `iloc[-1]`/`tail()` 前必须有显式 `sort_values()` |
| 18 | **缓存覆盖校验** | 缓存区间不足时自动重抓 |
| 19 | **公告日三级标注** | `REAL`/`FALLBACK`/`ESTIMATED`，诚实标注数据源精度 |
| 20 | **不伪造低估** | EPS<=0 → PE=NaN，不因低价高股息判"便宜" |
| 21 | **Gordon 不可结论计0分** | `g >= Ke` 时 score=0，不伪装中性 |
| 22 | **三条件 + 滞回** | 入场/出场使用不同阈值，避免频繁切换 |
| 23 | **仓位不超过30%** | 强制上限，高估/价值陷阱逐步降至0% |
| 24 | **回测T+1执行** | 信号日T产生，T+1开盘执行 |
| 25 | **价格区间多方法** | GGM反推、股息率反推、历史分位映射，取交集 |

---

## 四、架构与模块依赖

```
run_task.py / main_valresearch.py
    │
    ▼
valresearch/main.py  ← 分析编排器（11步流水线）
    │
    ├── data/providers.py    ← akshare 封装（带锁+重试+缓存）
    ├── data/pit.py          ← PIT 核心（唯一 TTM 实现）
    ├── data/pit_pe.py       ← PIT PE 计算
    ├── data/payout.py       ← 严格分红率
    ├── data/quality.py      ← 数据质量检查
    ├── data/confidence.py   ← 数据置信度
    ├── data/cache_coverage.py ← 缓存覆盖校验
    │
    ├── valuation/engine.py  ← 估值序列（调用 pit.py 做 TTM）
    ├── valuation/percentile.py ← 历史分位
    ├── valuation/gordon.py  ← Gordon 增长模型
    ├── valuation/price_range.py ← 合理价/买入区间
    │
    ├── fundamental/earnings.py   ← 盈利稳定性
    ├── fundamental/cashflow.py   ← 现金流质量
    ├── fundamental/dividend_sust.py ← 分红持续性
    ├── fundamental/leverage.py   ← 负债水平
    ├── fundamental/banking.py    ← 银行专用模型
    ├── fundamental/industry.py   ← 行业风险
    ├── fundamental/quality_score.py ← 加权质量分
    │
    ├── risk/value_trap.py    ← 价值陷阱
    ├── signal/engine.py      ← 三条件规则 + 综合评分
    ├── signal/explain.py     ← 模型解释链
    ├── signal/position.py    ← 仓位建议
    │
    ├── backtest/engine.py    ← 回测引擎
    ├── backtest/metrics.py   ← 绩效指标
    │
    └── report/generator.py   ← 九段式报告（中文）
```

---

## 五、数据源与局限性

| 数据 | 来源 (akshare) | 用途 | 局限 |
|------|---------------|------|------|
| 日线行情 | `stock_zh_a_daily` (Sina) | 估值用 close；回测用 adj_close | - |
| 历史PE-TTM | `stock_zh_valuation_baidu` (百度) | PE分位（已标记为 PIT 近似） | 仅为兼容保留，核心估值已不使用 |
| 财务报表 | 同花顺 (THS) | EPS_TTM、净利润、现金流、负债 | **announcement_date 全部为 ESTIMATED**（法规截止日近似） |
| 分红明细 | CNINFO/东方财富 | DPS_TTM | - |
| 国债利率 | `bond_zh_us_rate` | 无风险利率 Rf | - |
| 基准指数 | `stock_zh_index_daily` (Sina) | 回测基准 | - |

**关键局限**: 当前生产数据源（同花顺 THS）的 `announcement_date` 全部为 `ESTIMATED`（法规截止日近似，非真实公告日期），因此历史回测的 PIT 严谨性受数据源覆盖限制。系统输出 `DATA_LIMITATION` 而非伪造数据。

---

## 六、核心公式与实现位置

### 6.1 PIT TTM（唯一实现：`valresearch/data/pit.py`）

```
EPS_TTM(t):
  anchor = latest report where announcement_date <= t (revision-aware)
  if anchor is annual (month=12):
      TTM = anchor.eps_basic
  else (quarterly):
      prev_annual = same-period FY data at t (revision-aware)
      prev_same   = same-quarter prior-year data at t (revision-aware)
      TTM = anchor.eps_basic + prev_annual - prev_same
  if any component missing → return None (DATA_INSUFFICIENT)
```

**关键函数**:
- `pit.eps_ttm_asof(fin, t)` → `(float|None, reason|None)`
- `pit.net_profit_ttm_asof(fin, t)` → `(float|None, reason|None)`
- `pit.dps_ttm_asof(div, t)` → `(float, reason|None)` (0.0 when no dividends in 12 months)
- `pit.select_financial_version(fin, report_period, asof_date)` → dict|None
- `pit.annual_versions_pit(fin, t)` → DataFrame|None (revision-aware annual view)

### 6.2 PIT PE（`valresearch/data/pit_pe.py`）

```
PE_TTM(t) = Price(t) / EPS_TTM_PIT(t)
valid only when Price > 0 AND EPS > 0
otherwise PE = NaN (never fake low valuation)
```

### 6.3 估值序列（`valresearch/valuation/engine.py`）

```
build_series(price, pe, fin, div):
    for each trading day d in window:
        eps[d] = pit.eps_ttm_asof(fin, d)        # PIT TTM
        np_ttm[d] = pit.net_profit_ttm_asof(fin, d)
        dps[d] = dps_ttm_rolling(div, d)          # rolling 12-month cash dividends
        pe[d] = close[d] / eps[d]                 # PIT PE
        dy[d] = dps[d] / close[d] * 100           # dividend yield
        payout[d] = (dps * shares) / np_ttm * 100 # strict total caliber
```

### 6.4 分红率（严格口径，`valresearch/data/payout.py`）

```
payout = 现金分红总额TTM / 归母净利润TTM × 100
shares = 归母净利TTM / EPS_TTM
cash_dividend_totalTTM = DPS_TTM × shares
crosscheck = DPS_TTM / EPS_TTM × 100 (per-share, for validation only)
```

### 6.5 Gordon 增长模型（`valresearch/valuation/gordon.py`）

```
FairPE = Payout / (Ke - g)
Ke = Rf + ERP (default 5%)
g = ROE × (1 - Payout) (sustainable growth)
if g >= Ke → INVALID (score 0, confidence -5%)
if 0 < Ke-g <= 2% → THIN_SPREAD (degraded, confidence -3%)
```

### 6.6 综合评分（`valresearch/signal/engine.py`）

```
7 dimensions, denominator always 1.0:
  PE: 0.20, DY: 0.20, Payout: 0.10, Spread: 0.10,
  Gordon: 0.15, Quality: 0.20, Industry: 0.05
Missing dimensions → neutral score 50
Final = composite × (1 - value_trap_penalty - gordon_invalid_penalty_0.05)

Signals: ≥90 strong_buy, ≥80 buy, ≥65 accumulate, ≥50 hold,
         ≥35 wait, ≥20 reduce, else sell
```

### 6.7 三条件 + 滞回（`valresearch/signal/engine.py`）

```
A = PE_Pct < threshold (低估)
B = DY_Pct > threshold (高股息)
C = PR_Pct < threshold (低分红率)
Entry: strict threshold
Exit: crossing the adverse side (hysteresis 5 percentile points)
```

### 6.8 历史分位（`valresearch/valuation/percentile.py`）

```
pct = count(samples < current) / valid_samples × 100
current value excluded from denominator
```

---

## 七、版本历史

### V1.0 → V1.5（基础建设）
- 11个 Phase：数据层 → PIT → 估值 → Gordon → 基本面 → 信号 → 回测 → 报告
- P0-1~P0-11 + P1-1~P1-7 + P2 修复

### V1.6 P0（PIT 引擎统一）
- 修复 `groupby().last()` → `idxmax()` 整行选择
- PE 严格自算，消除外部 PE 依赖
- PitLayer.asof() 改用 `compute_pe_ttm_pit()`
- PitSnapshot 新增可追溯性字段
- 新增 11 项攻击测试

### V1.6.1 P0（消除第二套TTM）
- **P0-1**: 删除 engine.py 第二套 TTM 算法（`_ttm_values/_ttm_step/eps_ttm_step/np_ttm_step`），`build_series()` 直接调用 `pit.eps_ttm_asof()`
- **P0-2**: 新增 `pit.normalize_report_period()`，统一 `'YYYY-MM-DD'` 零填充格式
- **P0-3**: 修复 cashflow.py `.tail(3)` 隐式排序（增加 `.sort_index()`）
- **P0-4**: 新增 Golden Case 测试（1000次随机打乱验证确定性）
- **P0-5**: 新增 PIT 不变量测试（7项：asof单调性、修订隔离、无未来数据、字段一致性、TTM公式、PE有效性、行序不变性）

---

## 八、测试规范

### 测试风格
- **自包含断言脚本**（非 pytest）：每个 `test_*.py` 可独立运行
- 文件末尾 `if __name__ == '__main__':` 调用所有测试函数
- 断言失败抛 `AssertionError`，通过打印 `== 全部通过 ==`
- 不使用 fixture、mock、parametrize

### 运行方式
```powershell
$env:PYTHONIOENCODING='utf-8'; $env:PYTHONUTF8='1'; python -X utf8 tests/test_xxx.py
```

### 测试命名
- `test_p0_*` — P0 核心修复测试
- `test_p1_*` — P1 增强测试
- `test_phase*` — Phase 功能测试
- `test_pit_*` — PIT 机制测试

### 测试数据
- 使用合成数据（非真实股票）
- 数据足够小以快速运行
- 覆盖边界情况：空数据、缺失字段、修订版本、未来数据注入

---

## 九、代码规范

1. **不写 future 函数**: 不使用 `from __future__`（除 `annotations`）
2. **不伪造数据**: `DATA_INSUFFICIENT` 就是 `DATA_INSUFFICIENT`
3. **不删除功能**: 标记 DEPRECATED/LEGACY 但保留
4. **显式排序**: 使用 `iloc[-1]`/`tail()` 前必须有 `sort_values()`
5. **PIT 一致性**: 同一计算在 pit.py 和 engine.py 中必须产生相同结果
6. **中文注释**: 关键逻辑用中文注释
7. **无外部 PE 依赖**: 核心估值不使用外部历史 PE

---

## 十、已知遗留问题

1. **THS announcement_date 为 ESTIMATED**: 真实公告日不可用，PIT 精度受限
2. **`pe_asof()` 和 `pe_step()` 仍存在**: 标记 LEGACY/DEPRECATED，不被核心流程调用，可安全删除
3. **cashflow.py 仍需验证排序修复**: `.sort_index()` 修复已添加，但需真实数据验证
4. **`main.py` 和 `backtest/engine.py` 中的 `iloc[-1]`**: 依赖上游数据已排序（低风险，但可显式排序加固）

---

## 十一、开发工作流

1. **修改代码** → 运行相关测试
2. **运行全量测试** → 确保不破坏现有功能
3. **git add -A** → **git commit** → **git push**（自动执行，见 AGENTS.md）
4. **更新 README**（如涉及公式/架构变更）

---

## 十二、配置文件

- `valresearch/settings.yaml` — 全部可调参数（阈值/权重/模式覆盖）
- `valresearch/config.py` — 配置加载 + 模式深层合并
- `opencode.json` — opencode 配置（加载 AGENTS.md）
- `AGENTS.md` — AI 开发规范（自动 git push 规则）
- `requirements.txt` — Python 依赖

---

## 十三、给下一个 AI 的建议

1. **先读本文档**，再读 `README.md`，再读 `valresearch/main.py`
2. **运行测试**: `python -X utf8 tests/test_p0_pit_pe.py tests/test_p0_pit_revision.py tests/test_p0_pit_attacks.py tests/test_pit_integration.py tests/test_p0_golden_case.py tests/test_p0_pit_invariants.py`
3. **核心修改点**: `pit.py`（PIT核心）、`engine.py`（估值序列）、`main.py`（编排器）
4. **修改后必须**: 跑测试 → git push
5. **铁律不可违反**: 特别是第1条（无未来函数）和第2条（无 groupby().last()）

---

*文档生成时间: V1.6.1 | 最后更新: 2026-08-22*
