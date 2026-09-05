import sys; sys.path.insert(0, '.')

from valresearch.data.providers import FinancialDataProvider
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import math


@dataclass
class DataComparison:
    metric_name: str
    pdf_value: float
    api_value: float
    api_source: str
    diff_percent: float
    status: str


@dataclass
class ValidationResult:
    comparisons: List[DataComparison]
    summary: str
    recommendations: Dict[str, str] = field(default_factory=dict)

    def get_status_counts(self) -> Dict[str, int]:
        counts = {'match': 0, 'warning': 0, 'error': 0}
        for comp in self.comparisons:
            counts[comp.status] = counts.get(comp.status, 0) + 1
        return counts


class DataValidator:
    CORE_METRICS = [
        '营业收入', '归母净利润', '基本每股收益', '总资产', '总负债', '归母权益',
        '经营活动现金流量净额', '净利息收入', '手续费及佣金收入'
    ]

    THRESHOLDS = {
        'match': 5.0,
        'warning': 20.0
    }

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.fp = FinancialDataProvider()

    def validate(self, parse_result) -> ValidationResult:
        if not parse_result.metrics:
            return ValidationResult(
                comparisons=[],
                summary='无PDF数据可验证',
                recommendations={}
            )

        comparisons = self._compare_with_api(parse_result)
        summary = self._generate_summary(comparisons)
        recommendations = self._generate_recommendations(comparisons)

        return ValidationResult(
            comparisons=comparisons,
            summary=summary,
            recommendations=recommendations
        )

    def _compare_with_api(self, parse_result) -> List[DataComparison]:
        comparisons = []
        api_financials = self.fp.get_financials(self.symbol)

        if api_financials is None or api_financials.empty:
            parse_result.parse_errors.append('无法获取API数据进行对比验证')
            return comparisons

        latest_annual = None
        for idx, row in api_financials.iterrows():
            if str(row.get('report_period', '')).endswith('-12-31'):
                latest_annual = row
                break

        if latest_annual is None and not api_financials.empty:
            latest_annual = api_financials.iloc[0]

        if latest_annual is None:
            parse_result.parse_errors.append('无法找到API年报数据进行对比验证')
            return comparisons

        api_data = self._extract_api_data(latest_annual)
        pdf_data = self._extract_pdf_data(parse_result)

        for metric in self.CORE_METRICS:
            pdf_val = pdf_data.get(metric)
            api_val = api_data.get(metric)

            if pdf_val is not None and api_val is not None and api_val > 0:
                diff_percent = abs(pdf_val - api_val) / api_val * 100
                status = self._determine_status(diff_percent)

                comparisons.append(DataComparison(
                    metric_name=metric,
                    pdf_value=pdf_val,
                    api_value=api_val,
                    api_source='akshare',
                    diff_percent=diff_percent,
                    status=status
                ))

        return comparisons

    def _extract_api_data(self, api_row) -> Dict[str, float]:
        return {
            '营业收入': api_row.get('revenue'),
            '归母净利润': api_row.get('net_profit_attr'),
            '基本每股收益': api_row.get('eps_basic'),
            '总资产': api_row.get('total_assets'),
            '总负债': api_row.get('total_liabilities'),
            '归母权益': api_row.get('total_assets', 0) - api_row.get('total_liabilities', 0),
            '经营活动现金流量净额': api_row.get('ocf'),
            '净利息收入': None,
            '手续费及佣金收入': None
        }

    def _extract_pdf_data(self, parse_result) -> Dict[str, float]:
        data = {}
        for metric in parse_result.metrics:
            data[metric.metric_name] = metric.value
        return data

    def _determine_status(self, diff_percent: float) -> str:
        if diff_percent < self.THRESHOLDS['match']:
            return 'match'
        elif diff_percent < self.THRESHOLDS['warning']:
            return 'warning'
        else:
            return 'error'

    def _generate_summary(self, comparisons: List[DataComparison]) -> str:
        if not comparisons:
            return '无数据可对比'

        counts = {'match': 0, 'warning': 0, 'error': 0}
        total_diff = 0

        for comp in comparisons:
            counts[comp.status] += 1
            total_diff += comp.diff_percent

        avg_diff = total_diff / len(comparisons) if comparisons else 0

        summary = f'共对比{len(comparisons)}个指标：'
        summary += f' 匹配{counts["match"]}个，'
        summary += f' 警告{counts["warning"]}个，'
        summary += f' 错误{counts["error"]}个。'
        summary += f' 平均差异{avg_diff:.2f}%。'

        if counts['error'] > 0:
            summary += ' 存在严重差异，建议人工审核。'
        elif counts['warning'] > 0:
            summary += ' 存在轻微差异，可接受。'
        else:
            summary += ' 数据一致性良好。'

        return summary

    def _generate_recommendations(self, comparisons: List[DataComparison]) -> Dict[str, str]:
        recommendations = {}

        for comp in comparisons:
            if comp.status == 'error':
                recommendations[comp.metric_name] = 'manual_review'
            elif comp.status == 'warning':
                recommendations[comp.metric_name] = 'use_pdf'
            else:
                recommendations[comp.metric_name] = 'use_pdf'

        return recommendations