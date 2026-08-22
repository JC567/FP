# A股分红率排名 & 红利价值分位研究

> 一个面向 A 股沪深主板的**红利/估值研究工具集**，包含两大子系统：
>
> 1. **1号任务 · 分红率排名**：一键生成全市场分红率排名与筛选结果（桌面程序）。
> 2. **红利价值分位研究**：对单只股票做「历史分位 + Gordon 估值 + 基本面质量 + 价值陷阱 + 综合信号 + 价格区间 + 历史回测」的九段式深度分析（第 4 个页签 + CLI）。

所有历史计算严格遵循 **Point-in-Time（PIT，无未来函数）** 原则；数据缺失时标注 `DATA_INSUFFICIENT`，**绝不伪造数据**。

> **V1.6 P0**: 统一 PIT TTM 引擎、修复 groupby().last() 跨版本拼接、PE 严格自算、消除外部 PE 依赖、新增 11 项攻击测试。
>
> **V1.6.1 P0**: 消除 engine.py 第二套 TTM 算法（统一委托 pit.py）、新增 `normalize_report_period()` 统一日期格式、修复 cashflow.py 隐式排序、新增 Golden Case（1000次随机打乱）+ PIT 不变量（7项）测试。

---

## 一、项目概览

| 子系统 | 入口 | 输出 | 技术栈 |
|--------|------|------|--------|
| 分红率排名（1号任务） | `run_task.py` 页签 1/2/3 | `data/分红率排名.csv`、`data/分红率排名（筛选后）.csv` | akshare / pandas / tkinter / sqlite |
| 红利价值分位研究 | `run_task.py` 页签 4 或 `main_valresearch.py` | 终端摘要 / JSON / 九段式报告 / 回测绩效 | akshare / pandas / numpy / tkinter / matplotlib |

核心设计目标：**可追溯、可复现、不撒谎**。每个指标都带来源、口径、样本数、异常处理说明；每个"便宜/高股息"结论都要求同时满足多个独立条件，而非单一指标。

---

## 二、目录结构

```
first-project/
├── run_task.py                  # 桌面程序入口（4 个页签）
├── main_valresearch.py          # 红利价值分位研究 CLI（命令行入口）
├── dividend_rank.py             # 1号任务：分红率排名主脚本（第一步）
├── apply_exclusion.py           # 1号任务：合并排除 J~M 列并筛选（第二步）
├── div_hist.py                  # 历史股息率/分红率序列（共享模块，含缓存）
├── highlight.py                 # 结果高亮标记（PE百分位<30、满足提醒）
├── stock_db.py                  # 本地 SQLite 读写（D:\stockdata\hist.db）
├── check_pe.py / merge_keep.py / validate.py / div_hist.py  # 校验/合并/验证辅助
│
├── valresearch/                 # 红利价值分位研究 主包（可独立使用）
│   ├── main.py                  # 分析编排器 analyze()：取数→PIT→分位→Gordon→信号→区间→仓位→报告
│   ├── config.py                # 配置加载 + 模式(mode)深层合并
│   ├── settings.yaml            # 全部可调参数（阈值/权重/模式覆盖）
│   ├── models.py                # dataclass 数据模型（AnalysisReport 等）
│   ├── i18n.py                  # 英文→中文 展示层翻译（cn()）
│   ├── data/                    # 数据层
│   │   ├── providers.py         # akshare 各数据源封装（行情/PE/财报/分红/国债/行业，带锁+重试+缓存覆盖校验）
│   │   ├── pit.py               # PIT 机制：asof(t) 只取 t 前已公告数据；财务多版本(修订)选择
│   │   ├── pit_pe.py            # PIT 自算 PE-TTM（price/EPS，EPS非正→NaN，不伪造低估）
│   │   ├── payout.py            # 严格分红率口径(总额/归母净利) + 交叉验证
│   │   ├── announce.py          # 公告日来源 REAL/FALLBACK/ESTIMATED 诚实标注
│   │   ├── cache_coverage.py    # 缓存覆盖校验（覆盖不足则重抓）
│   │   ├── confidence.py        # Data Confidence Score（维度覆盖/公告口径/历史深度）
│   │   └── quality.py           # 数据质量检查（硬阻断/软警告）
│   ├── valuation/               # 估值层
│   │   ├── engine.py            # 估值序列构建（PE/股息率/分红率 逐日 PIT 序列）
│   │   ├── percentile.py        # 历史分位统计（count 口径，10y/5y，P10~P90）
│   │   ├── gordon.py            # Gordon 增长模型（Ke=Rf+ERP，情景矩阵，合理性校验）
│   │   └── price_range.py       # 合理价/买入区间（GGM反推、股息率反推、历史分位映射）
│   ├── fundamental/             # 基本面质量
│   │   ├── earnings.py          # 盈利稳定性（增速、波动、CAGR）
│   │   ├── cashflow.py          # 现金流质量（OCF/净利润）
│   │   ├── dividend_sust.py     # 分红持续性（连续年数、分红率水平）
│   │   ├── leverage.py          # 负债水平
│   │   ├── banking.py           # 金融行业(银行/保险/证券)专用模型（ROE/权益比率/盈利稳定/分红持续）
│   │   ├── industry.py          # 行业风险（主观配置表，标注主观）
│   │   └── quality_score.py     # 加权合成质量分（0-100；金融行业自动走专用分支）
│   ├── risk/                    # 风险层
│   │   └── value_trap.py        # 价值陷阱评分（盈利下滑/OCF恶化/高分红率/高负债/行业衰退）
│   ├── signal/                  # 信号层
│   │   ├── engine.py            # 三条件规则 + 综合评分（7维度加权）+ 陷阱仲裁 + 滞回(显式entry/exit)
│   │   ├── explain.py           # 模型解释链（每分可追溯回原始输入与阈值，供审计）
│   │   └── position.py          # 仓位建议表（按信号查表 + 陷阱修正）
│   ├── backtest/                # 回测层
│   │   ├── engine.py            # 逐周 PIT 重估(T+1执行) + 仓位权重 + 交易成本/滑点 + 策略/Buy&Hold/基准对比
│   │   └── metrics.py           # 绩效指标（CAGR/波动/Sharpe/回撤/Calmar/超额）
│   ├── report/                  # 输出层
│   │   ├── generator.py         # 九段式中文报告文本
│   │   └── json_output.py       # JSON 序列化/反序列化（英文键，机器可读）
│   └── gui/
│       └── tab.py               # 第 4 个页签（中文模式/帮助弹框/进度条/中文输出）
│
├── data/                        # 运行产物
│   ├── 分红率排名.csv            # 全量排名（UTF-8 BOM）
│   ├── 分红率排名（筛选后）.csv  # 排除后的最终结果
│   ├── 排除/                     # 排除与手动配置（手动配置.csv 为 L~O 列编辑源）
│   ├── vr_reports/              # 单股分析 JSON 报告
│   └── error.log                # 运行日志
│
├── tests/                       # 分阶段单元测试（test_phase1 ~ test_phase11）
├── 1号任务_分红率排名.md          # 1号任务完整规则文档（含第 10 节：红利价值分位研究）
└── 计算规则说明.md               # 分红率排名计算公式与口径
```

---

## 三、快速开始

### 环境要求
- Python 3.8+，Windows（路径含中文，所有脚本已设置 UTF-8 输出）
- 依赖：`akshare pandas numpy matplotlib pyyaml`（见各文件 import）
- 本地数据库 `D:\stockdata\hist.db`（sqlite，历史行情缓存，优先本地读取）

### 启动桌面程序
```bash
python run_task.py
```
页签：`运行` / `数据查看` / `手动配置` / `红利价值分位研究`。

### 单股深度分析（CLI）
```bash
python main_valresearch.py 600036 --name 招商银行 --date 2025-07-01 --mode balanced
python main_valresearch.py 600036 --json data/vr_reports/600036.json   # 输出 JSON
```

### 运行全部测试
```bash
python tests/test_phase1.py
python tests/test_phase2.py
python tests/test_phase34.py
python tests/test_phase5.py
python tests/test_phase6789.py
python tests/test_phase10.py
python tests/test_phase11.py
python tests/test_p0_*.py
python tests/test_p1_*.py
```

---

## 四、数据源与依赖

| 数据 | 来源（akshare） | 用途 |
|------|----------------|------|
| 日线行情 | `stock_zh_a_daily`（新浪） | 估值用 **close（原始价）**，回测收益用 **adj_close（后复权）** |
| 全市场快照 | `stock_zh_a_spot`（新浪，优先）→ 东财 → 本地缓存 | 1号任务最新价/昨收 |
| 历史 PE-TTM | `stock_zh_valuation_baidu`（百度，周频，自上市起） | PE 分位（as-reported，打 PIT 近似标记） |
| 财报 | 同花顺财报接口 | EPS_TTM、净利润、现金流、负债 |
| 分红明细 | 巨潮/东财分红 | DPS_TTM（近12个月已实施现金分红） |
| 中国10年国债 | `bond_zh_us_rate` | 无风险利率 Rf → Ke=Rf+ERP |
| 基准指数 | `stock_zh_index_daily`（新浪，sh000300 优先） | 回测基准（东财指数接口曾被墙，已做兜底） |

**并发控制**：akshare 接口全局串行化（`_AK_LOCK`），关键请求带重试（`_retry`），避免限流。

---

## 五、核心概念与口径（务必先读）

### 1. Point-in-Time（PIT）—— 无未来函数
- 财务数据：仅当 `announcement_date <= t` 才可用；EPS_TTM 用"最新已公告报告期 + 上年同期 + 上年年报"滚动外推，**并对财务多版本(修订)做时点选择**：上年同期/上年年报取该公告日已公开的版本，杜绝用未来修订污染历史。
- **V1.6 P0 统一 PIT 引擎**：`pit.py` 中 `eps_ttm_asof()` 和 `net_profit_ttm_asof()` 均使用 `groupby('report_period')['ann_ts'].idxmax()` 做**整行版本选择**（禁止 `groupby().last()` 跨列拼接），确保同一报告期的所有字段来自同一 revision。
- **V1.6 P0 修订感知对称**：`eps_ttm_asof()` 与 `net_profit_ttm_asof()` 均有相同的修订去重逻辑，不再不对称。
- **P0-A Gordon 完全 PIT**：`historical_eps_cagr(fin, asof)`、`roe_from_financials(fin, asof)`、`compute_growth(fin, payout, asof, cfg)` 均只用 `announcement_date<=asof` 的财报（修订感知），无未来函数。
- **P0-B 银行模型完全 PIT**：`_last_annual(fin, t)` 只取 `announcement_date<=t` 的年报并支持修订；`roe_latest/equity_ratio_latest` 均带时点参数。
- **P0-C 财务修订版本不被删除**：`vr_financials` 主键改为 `(symbol, report_period, announcement_date)` 以保留全部修订；Provider 不再 `drop_duplicates('report_period')`。
- 分红：仅当 `implement_date（实施方案公告日）<= t` 的近 12 个月现金分红计入 DPS_TTM。
- **PE 由 EPS_TTM 与当日收盘价自算（`compute_pe_ttm_pit`）**，EPS 非正 → PE=NaN（不伪造低估）；`PitLayer.asof()` 已改为使用 PIT 自算 PE，不再调用外部 `pe_asof()`。外部 Baidu PE 仅保留用于向后兼容和诊断对比，不进入核心估值流程。
- 公告日来源分三级诚实标注：`REAL`（真实公告日）/ `FALLBACK`（法规截止日近似）/ `ESTIMATED`（缺失估算），并在置信度中体现。
- 缓存带覆盖校验（`cache_coverage`）：缓存区间不足以覆盖目标时自动重抓，防止用过时数据。
- **数据源局限性声明（V1.6 P0）**：PIT Engine 具备完整的修订版本选择能力，但当前生产数据源（同花顺 THS）的 `announcement_date` 全部为 `ESTIMATED`（法规截止日近似，非真实公告日期），因此历史回测的 PIT 严谨性受数据源覆盖限制。当真实数据源无法提供完整历史财务修订版本时，系统输出 `DATA_LIMITATION` 而非伪造数据。
- **V1.6.1 TTM 唯一实现**：`engine.py` 不再包含独立 TTM 算法，`build_series()` 直接调用 `pit.eps_ttm_asof()` / `pit.net_profit_ttm_asof()`，确保全项目只有一套 TTM 公式。
- **V1.6.1 report_period 标准化**：新增 `pit.normalize_report_period()` 函数，统一将任意格式的报告期转换为 `'YYYY-MM-DD'`（零填充），避免字符串比较不一致。

### 2. 关键指标定义
- **分红率 payout（正式口径，P0-D）= 现金分红总额TTM / 归母净利润TTM × 100**；股本=归母净利TTM/EPS_TTM，现金分红总额TTM=DPS_TTM×股本。**DPS/EPS 仅作交叉验证**（`payout_crosscheck`，偏差过大记 `PAYOUT_CROSSCHECK_MISMATCH`）。
  - 严格口径（`payout_ratio_strict`）：总额 / 归母净利润，并做每股口径交叉验证；EPS 非正 → NaN。
  - 分红率 < 0 或 > 150% 判为 abnormal，剔除并 winsorize ±1%；负 PE 剔除。
- **分红持续性分红率**（`dividend_sustainability`）= 现金分红总额_Y / 归母净利润_Y，总额=DPS×实施日PIT隐含股本；股本跳变修正：相邻年隐含股本变动>20%时按旧基数折算，消除历史EPS追溯稀释造成的假阳性（如 600887 2014: 旧口径117.6%，修正后55.9%）。
- **股息率 DY = DPS_TTM / 不复权收盘价 × 100**（%）。**分子用实际每股分红（不复权，真实金额），分母用不复权价格**；后复权价仅用于回测收益（含分红再投资）。**不分红股票 → 0%（非 NaN）**；仅当数据缺失时为 NaN。
- **历史分位 = count(历史样本 < 当前值) / 有效样本数 × 100**（雪球排名式口径，当前值不计入分母）。
- **PE 分位**用 10 年主窗口 + 5 年辅窗口；股息率/分红率同样计算 10y/5y 分位。

### 3. Gordon 增长模型
- `FairPE = Payout / (Ke − g)`，其中 `Ke = Rf + ERP(5%)`，`g` 优先用**可持续增速 = ROE × (1 − Payout)**（多源估计：历史增速/可持续/行业/GDP）。
- 有效性校验：`g ≥ Ke` → 判 `GGM_INVALID`（**完全拒绝**，计0分降置信度5%）；`0 < Ke−g ≤ 2%` → 判 `GGM_THIN_SPREAD`（**降级可用**：返回合理PE但标注置信度偏低，降置信度3%）。
- 情景矩阵：熊市(Ke+1%, g−1%) / 基准 / 牛市(Ke−1%, g+1%)；**仅 base 失效判 INVALID**，bear/bull 失败是情景边界信息。
- **Gordon 无结论（失效/数据不足）→ 该维度计 0 分（非中性 50），并降置信度 5%**；THIN_SPREAD 降 3%。绝不伪装成 50。

### 4. 三种模式（模式间仅调阈值，口径一致）
| 模式 | PE 分位阈值(A) | 股息率分位阈值(B) | Ke 偏移 |
|------|---------------|-------------------|---------|
| 稳健型（保守） | <20% | >80% | +1% |
| 均衡型（默认） | <30% | >70% | 0 |
| 进取型（激进） | <40% | >60% | −1% |

### 5. 综合评分（0-100，越高越好）
7 维度全权重加权（**分母恒为 1.0**，缺失维度取中性分 50，保证模式间可比）：

| 维度 | 权重 | 映射（消除封顶饱和失真） |
|------|------|--------------------------|
| PE | 0.20 | `100 − PE分位` |
| 股息率 | 0.20 | `股息率分位` |
| 分红率 | 0.10 | `100 − 分红率分位` |
| 利差 | 0.10 | `50 × (利差/阈值)`（阈值处=50，2×阈值=100） |
| Gordon | 0.15 | `100 − 50 × (当前PE/合理PE)`；**失效/数据不足计 0（非 50）并降置信度 5%** |
| 质量 | 0.20 | 基本面质量分（金融行业走专用模型） |
| 行业 | 0.05 | `100 − 行业风险分` |

最终得分 = 综合分 × (1 − 价值陷阱惩罚系数 − Gordon无结论惩罚0.05)。分数信号：≥90 强烈买入 / ≥80 买入 / ≥65 逢低吸纳 / ≥50 持有 / ≥35 观望 / ≥20 减仓 / 其余卖出。

### 5b. Data Confidence Score（P1-1）
`置信度 = 100 × (0.45×维度覆盖 + 0.30×公告口径 + 0.25×历史深度)`；级别 HIGH≥80 / MEDIUM≥60 / LOW。数据不足时降级并如实写入报告局限，**不伪装高分**。

### 6. 三条件规则 + 滞回
- `A = PE分位 < 阈值`、`B = 股息率分位 > 阈值`、`C = 分红率分位 < 阈值`。
- 规则信号：`A∧B∧C`→三低共振·强烈低估；`A∧B∧¬C`→政策驱动型高股息；`¬A∧B∧C`→高股息但估值不低；其余→中性。
- **滞回（hysteresis，带宽 5 分位点，显式 entry/exit 阈值）**：进入用严格阈值，已在位的条件需越过**更不利一侧**的边界才退出（如 A：进入<30、退出≥35），杜绝边界噪声来回翻转与矛盾信号；回测时序生效，单次分析用严格阈值。
- 最终信号 = 分数信号，再由规则信号强化/下调、价值陷阱仲裁（>60 禁 STRONG_BUY，极高强制 WAIT）。

### 7. 价值陷阱
逐项加分（盈利连续下滑 / OCF 恶化 / 分红率长期>100% / 高负债 / 行业衰退 / 政策风险），分档 LOW/MEDIUM_LOW/MEDIUM/HIGH/VERY_HIGH，惩罚系数阶梯折减综合分。

### 8. 价格区间
- GGM 情景合理价（低/基准/高）× EPS → 合理价格区间。
- 股息率反推价：`Price = DPS_TTM / 目标股息率`（@4/5/6/7%）。
- 历史分位价：`当前 EPS × 历史 PE_P20/P30/P50/P70`。
- 买入区：深度（P30 附近）/ 标准（P50 附近），并输出当前所处区间。
- **统一合理价 + 风险调整（P1-3）**：把各法（GGM/历史中位PE/股息率5%）合理价取中位数成统一合理价；各法极差>35% 标 `UNCERTAIN`；再按价值陷阱惩罚与 Gordon 失效**收窄安全边际**（`折价 = 10% + 10%×惩罚 + Gordon失效另10%，上限50%`）输出风险调整价。

### 9. 模型解释链（P1-7）
每个分数（PE/股息率/分红率/Gordon/质量/行业/陷阱/最终信号）都可沿"原始输入 → 处理 → 分位 → 阈值 → 贡献"展开成 8 步可读链条，供审计回溯。

### 10. 已知局限（报告「局限」段如实列出，不隐藏）
- 财报公告日缺失时按法规截止日近似（`FALLBACK`/`ESTIMATED`），并在置信度与局限中标注。
- 同花顺无 OCF 总量/总资产/总负债 → 现金流与负债模块部分 `DATA_INSUFFICIENT`；金融行业用专用模型规避误导。
- 行业识别为关键词推断（启发式），可配置覆盖。
- 分位样本 < 1 年交易日时提示"分位可能系统性偏低"。
- 质量分与陷阱分共用盈利/现金流/分红持续性等指标，同一基本面问题可能被双重扣分（保守倾向，已在报告注明）。
- 回测策略收益**已计交易成本 0.1% 与滑点 0.2%**（按 |Δ权重|×单边成本扣减）；中证红利基准指数约 2019 年起，与个股 10 年分位窗口不一致。
- 回测为 **T+1 执行 + 仓位系统 target_weight 归一化到单股上限(max_position)**（非简单满仓/当日生效，也避免直接把组合级配比当单股仓位导致的常年空仓）。
- **P0-E 回测传递完整 value_trap 对象**（score/level/flags/penalty）给 `position_plan`，而非用 `vt_score` 重构 LOW/penalty=0。
- **P0-F `rep.signal` 字段不覆盖**：`data_confidence`、`explanation`、`gordon_status`、`gordon_penalty`、`hysteresis_bands` 全部进入最终 `rep.signal`。
- **allow_sell 参数**（settings.yaml `backtest.allow_sell` 或 `run_backtest(allow_sell=False)`）：默认 true（按模型买卖）；设为 false 后权重单调不减（只买不卖），卖出信号仅阻止新增买入，不减仓。适用于"模型只用于判断买点"的用法。

---

## 六、数据流（一次单股分析）

```
用户输入(symbol, date, mode)
  → ① 取数(行情/PE/财报/分红/国债/行业)            data/providers.py
  → ② 数据质量检查(硬阻断/软警告)                  data/quality.py
  → ③ 估值序列构建(逐日 PE/DY/PR，PIT 无未来函数)  valuation/engine.py + pit_pe.py
  → ④ 分位数(10y/5y, count 口径, 异常剔除)         valuation/percentile.py
  → ⑤ Gordon 合理PE(可持续增速 + 失效/无结论处理)   valuation/gordon.py
  → ⑥ 基本面质量分(5 模块加权；金融走专用模型)      fundamental/*
  → ⑦ 价值陷阱评分 + 惩罚系数                       risk/value_trap.py
  → ⑧ 信号(三条件+评分+仲裁+滞回 entry/exit) + 解释链 signal/*
  → ⑨ 价格区间(统一合理价 + 风险调整)               valuation/price_range.py
  → ⑩ 数据置信度(Data Confidence Score)            data/confidence.py
  → ⑩ 组装 AnalysisReport                           models.py
  → ⑪ 输出(九段式报告 / JSON / 终端中文摘要)        report/* + i18n.py
```

---

## 七、模块职责速查

| 文件 | 职责 |
|------|------|
| `valresearch/main.py` | `analyze()` 编排上述 ①~⑪，带 `progress_cb(percent, message)` 进度回调 |
| `valresearch/config.py` | `get_config(mode)` 返回合并模式的配置；`check()` 校验 |
| `valresearch/settings.yaml` | 全部阈值/权重/模式覆盖/仓位表，改参数不写死 |
| `valresearch/data/providers.py` | 五类数据提供器（行情/财报/分红/国债/行业），全局锁+重试 |
| `valresearch/data/pit.py` | `PitLayer.asof(t)` 时点快照 + 财务多版本(修订)选择，PIT 语义的唯一入口 |
| `valresearch/data/pit_pe.py` | `compute_pe_ttm_pit` PIT 自算 PE（price/EPS，EPS非正→NaN） |
| `valresearch/data/payout.py` | `payout_ratio_strict` 严格分红率 + 每股口径交叉验证 |
| `valresearch/data/announce.py` | 公告日来源 REAL/FALLBACK/ESTIMATED 标注 |
| `valresearch/data/cache_coverage.py` | 缓存覆盖校验（不足则重抓） |
| `valresearch/data/confidence.py` | `data_confidence_score` 置信度 |
| `valresearch/valuation/engine.py` | 向量化构建估值序列（searchsorted 阶梯 + 滚动求和） |
| `valresearch/valuation/percentile.py` | `percentile_stats` 分位统计 + `filter_pe/filter_payout` 异常处理 |
| `valresearch/valuation/gordon.py` | 增长估计(可持续增速)、Ke、情景矩阵、合理PE、失效/无结论判断 |
| `valresearch/valuation/price_range.py` | `buy_range/current_zone/hist_price_map/price_at_dy` + `price_methods/unify_price/risk_adjust_price` |
| `valresearch/fundamental/*` | 5 个基本面子模块 + `banking`(金融专用) + `quality_score` 加权合成 |
| `valresearch/risk/value_trap.py` | `value_trap_score` 陷阱评分与惩罚 |
| `valresearch/signal/engine.py` | `compute_signal`（三条件+评分+仲裁+滞回 entry/exit + Gordon无结论计0） |
| `valresearch/signal/explain.py` | `explain_signal` 模型解释链 |
| `valresearch/signal/position.py` | `position_plan` 仓位表 |
| `valresearch/backtest/engine.py` | `re_evaluate`（逐周重估）+ `run_backtest`（T+1 + target_weight 归一化到单股上限 + 成本/滑点）+ `fetch_benchmark` |
| `valresearch/backtest/metrics.py` | 绩效指标计算 |
| `valresearch/report/generator.py` | `format_report` 九段式中文报告 |
| `valresearch/report/json_output.py` | `save_json/load_json`（英文键 JSON） |
| `valresearch/gui/tab.py` | `build_vr_tab` 页签（中文模式/帮助弹框/进度条） |
| `valresearch/i18n.py` | `cn()` 展示层中文翻译（信号/规则/模式/等级/指标） |

---

## 八、给其他 AI / 协作者的约定

- **严禁未来函数**：任何历史计算只使用 `asof(t)` 时刻已公开数据；判断数据可得性一律走 `data/pit.py`。
- **数据源锁定**：不要引入新的数据源替代现有接口；akshare 接口需通过 `providers.py` 的锁与重试。
- **不伪造数据**：字段缺失打 `DATA_INSUFFICIENT`，评分/报告明确标注，绝不插值填充后当作真实值。
- **展示层翻译**：中文输出一律经 `i18n.cn()`（英文 token→中文）；JSON 数据保留英文键（机器可读）。
- **进度回调**：长任务（分析/回测）必须接受 `progress_cb(percent, message)`，供界面显示。
- **数值口径**：股息率/利差为百分数（如 4.25 / 2.6），PE 为倍数（如 8.18）；Gordon 计算内部转小数（`/100`），注意单位换算。
- **模式可比较**：三个模式只允许调整阈值与 Ke 偏移，评分分母恒为全部权重；缺失维度取中性分 50 并在报告中注明。
- **测试先行**：新增/修改逻辑必须补充 `tests/` 对应阶段的用例并跑通全部测试。
- **文档同步**：修改口径/参数后同步更新 `1号任务_分红率排名.md` 与本文档。

---

## 九、常见工作流

### 执行 1 号任务（分红率排名）
```
python run_task.py → 页签1「运行」→ 点击「▶ 运行1号任务」
```
或在命令行：`python dividend_rank.py && python apply_exclusion.py`。
结果：`data/分红率排名.csv`（全量）+ `data/分红率排名（筛选后）.csv`（合并排除 J~M 列后的最终结果）。

### 查看数据
页签2「数据查看」：表头单击排序、双击筛选列、组合筛选(AND)、选中行查看近 10 年估值走势（PE/股息率/分红率叠加，30%/70% 线）。

### 手动配置
页签3「手动配置」：双击单元格编辑 L~O 列（是否保留/买入提醒pe/买入提醒价格/买入pb），保存到 `data/排除/手动配置.csv`，下次运行按新值计算。

### 单股深度研究
页签4「红利价值分位研究」：输入代码/名称/日期，选择中文模式（稳健型/均衡型/进取型），点「单股分析」（九段式报告）或「单股回测」（历史重估绩效对比），输出全部为中文。

---

## 十、测试体系

| 测试文件 | 覆盖阶段 |
|----------|----------|
| `test_phase1.py` | 数据接入与质量检查 |
| `test_phase2.py` | PIT 机制（asof、EPS/DPS 外推） |
| `test_phase34.py` | 估值序列构建 + 分位统计 |
| `test_phase5.py` | Gordon 模型 + 价格区间 |
| `test_phase6789.py` | 基本面质量 + 价值陷阱 + 信号引擎 + 中性分/滞回 + 买入区 |
| `test_phase10.py` | 回测引擎（T+1/仓位权重/成本滑点）+ 绩效指标 |
| `test_phase11.py` | 九段式报告 + JSON 往返 + 中文输出 |
| `test_p0_pit_pe.py` | P0-1 PIT 自算 PE |
| `test_p0_pit_revision.py` | P0-2 财务多版本修订选择 |
| `test_p0_announce_source.py` | P0-3 公告日来源 REAL/FALLBACK/ESTIMATED |
| `test_p0_zero_dividend.py` | P0-4 不分红=0% |
| `test_p0_payout_ratio.py` | P0-5 严格分红率口径 |
| `test_p0_gordon_growth.py` | P0-6 可持续增速 |
| `test_p0_gordon_status.py` | P0-7 Gordon 无结论计 0 |
| `test_p0_cache_coverage.py` | P0-11 缓存覆盖校验 |
| `test_p1_confidence.py` | P1-1 数据置信度 |
| `test_p1_banking.py` | P1-2 金融行业专用模型 |
| `test_p1_price_range.py` | P1-3 统一价格 + 风险调整 |
| `test_p1_hysteresis.py` | P1-4 entry/exit 阈值表述 |
| `test_p1_counterexamples.py` | P1-5 四类反例 |
| `test_p1_replay.py` | P1-6 历史回放（可复现/无前视） |
| `test_p1_explain.py` | P1-7 模型解释链 |
| `test_pit_integration.py` | P0-G 真实 PIT 集成 + 二十五 未来数据注入攻击（asof 注入未来5年全部数据/修订财报 → 信号/分/仓位必须不变） |
| `test_share_jump_payout.py` | 股本跳变修正（600887假阳性修复）+ allow_sell 只买不卖权重单调性 |
| `test_p0_pit_attacks.py` | **V1.6 P0 攻击测试**（11项）：同公告日多报告期、随机行顺序不变性、同报告期多版本、字段缺失版本、未来修订排除、未来报告期排除、同日多报告+revision组合、TTM正确性、PE自算、外部PE不使用、PIT Snapshot可追溯 |
| `test_p0_golden_case.py` | **V1.6.1 Golden Case**（1000次随机打乱）：EPS_TTM/净利TTM/build_series 确定性验证 |
| `test_p0_pit_invariants.py` | **V1.6.1 PIT 不变量**（7项）：asof单调性、修订隔离、无未来数据、字段一致性、TTM公式、PE有效性、行序不变性 |

运行：`python tests/test_*.py`（每个文件独立可跑，末尾打印 `== 全部通过 ==`）。