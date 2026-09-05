# Project Agents Configuration

## 铁律：投资三原则（每次AI编码前必须理解）

本项目服务于一个明确的个人投资计划：**年投10万，10年目标1000万，只买不卖，红利复利**。以下三条铁律是所有代码设计、功能开发、分析逻辑的最高准则。任何修改都不得违背。

### 铁律一：安全边际是买入的唯一前提

> **没有足够安全边际的股票，永远不买。宁可错过，不可买贵。**

- 所有估值分析的核心目标是回答一个问题：**现在买，便宜吗？**
- PB ≤ 1.0（破净）是银行业的便宜底线；PB ≤ 0.80 是深度破净强买区
- 安全边际不是"估值偏低"，而是"即使我判断错了，也不会亏大钱"
- 任何功能如果削弱了对安全边际的严格判断，必须拒绝

### 铁律二：系统存在的唯一价值是精准定位买点

> **买点对了，10年持有才有意义。买点错了，持有10年就是灾难。**

- 用户买入后10年不做卖出动作，因此**卖出信号、减仓逻辑、止损机制**对本系统无意义
- 所有计算资源、分析维度、UI展示都应服务于一个问题：**这个价格，该不该买？**
- 买点判断必须同时满足：优质（能活10年）+ 便宜（有安全边际）+ 非陷阱（不是价值毁灭）
- 任何偏离"买点定位"的功能（如短线择时、技术分析、卖出建议）不应加入

### 铁律三：10年可持续性是质量评估的硬门槛

> **不是好公司不买，不是能活10年的公司不买。分红持续性 > 当前收益率。**

- 银行业看：ROE持续稳定 ≥ 10%、资本充足率达标、不良率可控、连续分红 ≥ 5年
- 质量评分的权重应反映"10年后这家公司还在不在、还能不能分红"
- 盈利连续下滑、资本充足率恶化、分红中断是最高优先级的一票否决信号
- 短期业绩波动（单季利润下降）不应过度惩罚，长期趋势才是关键

## Git Workflow

After every code modification session, the agent MUST:

1. Run `git add -A` to stage all changes
2. Run `git commit` with a concise commit message describing the changes
3. Run `git push` to push to the remote repository (`origin master`)

This applies to ALL code changes — bug fixes, feature additions, refactoring, test updates, etc. Never skip the push step.

Remote: `git@github.com:JC567/FP.git`

## Test Execution

Before committing, run the test suite to verify changes do not break existing functionality:

```powershell
$env:PYTHONIOENCODING='utf-8'; $env:PYTHONUTF8='1'; python -X utf8 tests/test_p0_pit_pe.py tests/test_p0_pit_revision.py tests/test_p0_pit_attacks.py tests/test_pit_integration.py
```

## Code Style

- Self-contained `if __name__` assertion scripts for tests (not pytest)
- No future functions, no fabricated data, no DATA_INSUFFICIENT disguised as 50
- PIT (Point-in-Time) integrity: `announcement_date <= t` only
