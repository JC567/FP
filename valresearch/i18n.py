# -*- coding: utf-8 -*-
"""中文翻译：信号 / 规则 / 模式 / 陷阱等级 / 质量标记 / 指标等英文 → 中文。

cn(text) 将文本中出现的已知英文 token 替换为中文（先长后短，避免子串误替换）。
仅用于展示层（报告/CLI/GUI）；JSON 数据仍保留英文键以保证机器可读。
"""
from __future__ import annotations

# (英文原文, 中文) —— 按长度降序替换
TOKENS = [
    # 规则信号（长词在前）
    ('STRONG_UNDERVALUE', '三低共振·强烈低估'),
    ('POLICY_DRIVEN_HIGH_DIVIDEND', '政策驱动型高股息'),
    ('HIGH_YIELD_NOT_CHEAP_ENOUGH', '高股息但估值不低'),
    ('NEUTRAL', '中性'),
    # 最终/分数信号
    ('STRONG_BUY', '强烈买入'),
    ('ACCUMULATE', '逢低吸纳'),
    ('BUY', '买入'),
    ('HOLD', '持有'),
    ('WAIT', '观望'),
    ('REDUCE', '减仓'),
    ('SELL', '卖出'),
    # 模式
    ('conservative', '稳健型'),
    ('balanced', '均衡型'),
    ('aggressive', '进取型'),
    # 价值陷阱等级
    ('VERY_HIGH', '极高'),
    ('MEDIUM_LOW', '中低'),
    ('MEDIUM', '中等'),
    ('HIGH', '高'),
    ('LOW', '低'),
    # 数据/质量标记
    ('GGM_INVALID', '戈登模型失效'),
    ('GGM_THIN_SPREAD', '戈登置信度偏低'),
    ('THIN_SPREAD', '置信度偏低'),
    ('DATA_INSUFFICIENT', '数据不足'),
    ('DIVIDEND_UNSUSTAINABLE', '分红不可持续'),
    ('EARNINGS_WARNING', '盈利预警'),
    ('VALUE_TRAP_HINT', '价值陷阱提示'),
    ('OCF_WARNING', '现金流预警'),
    ('PE_TTM_PIT_APPROXIMATION', 'PE为近似值(公告日未精确对齐)'),
    ('DATA_QUALITY_WARNING', '数据质量警告'),
    ('DATA_CALIBER_RISK', '数据口径风险'),
    ('keyword-inference', '关键词推断'),
    ('baidu_pit_approx', '百度估值(近似)'),
]

_SORTED = sorted(TOKENS, key=lambda kv: len(kv[0]), reverse=True)


def cn(text) -> str:
    """把文本中的英文 token 替换为中文。"""
    if text is None:
        return ''
    s = str(text)
    for en, zh in _SORTED:
        s = s.replace(en, zh)
    return s


def cn_signal(sig: str) -> str:
    return cn(sig)


def cn_rule(rule: str) -> str:
    return cn(rule)


def cn_mode(mode: str) -> str:
    return cn(mode)


def cn_metrics(d: dict) -> dict:
    """把绩效指标 dict 的英文 key 翻译为中文 key。"""
    MAP = {'cagr': '年化复合收益率(CAGR)', 'annual_volatility': '年化波动率',
           'sharpe': '夏普比率', 'max_drawdown': '最大回撤', 'calmar': '卡尔玛比率',
           'benchmark_cagr': '基准年化', 'excess_return': '超额收益', 'alpha': '阿尔法',
           'final_value': '期末净值', 'total_return': '总收益率'}
    return {MAP.get(k, k): v for k, v in d.items()}