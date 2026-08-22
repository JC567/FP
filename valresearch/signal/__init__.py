# -*- coding: utf-8 -*-
"""信号系统：三指标 + 综合评分 + 价值陷阱仲裁 + 仓位。"""
from valresearch.signal.engine import compute_signal, rule_signal, score_signal
from valresearch.signal.position import position_plan
__all__ = ['compute_signal', 'rule_signal', 'score_signal', 'position_plan']