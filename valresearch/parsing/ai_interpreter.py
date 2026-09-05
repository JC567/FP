import sys; sys.path.insert(0, '.')

from dataclasses import dataclass
from typing import Optional


@dataclass
class AIInterpretation:
    interpretation_summary: str
    risk_assessment: str
    investment_advice: str
    model_name: str = 'N/A'
    model_version: str = 'N/A'


class AIInterpreter:
    def __init__(self, parse_result, bank_interpretation):
        self.parse_result = parse_result
        self.bank_interpretation = bank_interpretation

    def interpret(self) -> AIInterpretation:
        return AIInterpretation(
            interpretation_summary='大模型解读功能待配置',
            risk_assessment='大模型解读功能待配置',
            investment_advice='大模型解读功能待配置',
            model_name='待配置',
            model_version='待配置'
        )