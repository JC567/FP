import sqlite3
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class BankInterpretation:
    interpretation_type: str
    metric_name: str
    metric_value: float
    rating: str
    analysis: str


@dataclass
class BankAnalysisResult:
    capital_adequacy: List[BankInterpretation]
    asset_quality: List[BankInterpretation]
    profitability: List[BankInterpretation]
    liquidity: List[BankInterpretation]
    overall_assessment: Dict


class BankInterpreter:
    REGULATORY_REQUIREMENTS = {
        'core_tier1_capital_ratio': 7.5,
        'capital_adequacy_ratio': 10.5,
        'leverage_ratio': 4.0,
        'npl_ratio_warning': 3.0,
        'provision_coverage_safe': 150.0,
        'liquidity_coverage': 100.0,
        'net_stable_funding': 100.0
    }

    RATING_THRESHOLDS = {
        'excellent': 1.0,
        'good': 0.8,
        'average': 0.6,
        'poor': 0.4,
        'warning': 0.0
    }

    def __init__(self, parse_result):
        self.parse_result = parse_result
        self.data = self._extract_bank_data()

    def _extract_bank_data(self) -> Dict:
        data = {}
        for metric in ['核心一级资本充足率', '资本充足率', '杠杆率', '不良贷款率',
                      '拨备覆盖率', '净息差', '流动性覆盖率', '净稳定资金比率']:
            value = self.parse_result.get_metric(metric)
            if value is not None:
                data[metric] = value
        return data

    def _rate(self, value: float, threshold: float, higher_better: bool = True) -> str:
        if higher_better:
            ratio = value / threshold
        else:
            ratio = threshold / value if value > 0 else 0

        if ratio >= 1.2:
            return 'excellent'
        elif ratio >= 1.0:
            return 'good'
        elif ratio >= 0.9:
            return 'average'
        elif ratio >= 0.8:
            return 'poor'
        else:
            return 'warning'

    def interpret(self) -> BankAnalysisResult:
        return BankAnalysisResult(
            capital_adequacy=self._analyze_capital(),
            asset_quality=self._analyze_asset_quality(),
            profitability=self._analyze_profitability(),
            liquidity=self._analyze_liquidity(),
            overall_assessment=self._overall_assessment()
        )

    def _analyze_capital(self) -> List[BankInterpretation]:
        results = []
        data = self.data

        if '核心一级资本充足率' in data:
            value = data['核心一级资本充足率']
            rating = self._rate(value, self.REGULATORY_REQUIREMENTS['core_tier1_capital_ratio'])
            analysis = f'核心一级资本充足率为{value:.2f}%，监管要求为{self.REGULATORY_REQUIREMENTS["core_tier1_capital_ratio"]}%。'
            if rating in ['excellent', 'good']:
                analysis += '资本充足性良好，抗风险能力强。'
            elif rating == 'warning':
                analysis += '资本充足性不足，需关注资本补充。'
            results.append(BankInterpretation('capital_adequacy', '核心一级资本充足率', value, rating, analysis))

        if '资本充足率' in data:
            value = data['资本充足率']
            rating = self._rate(value, self.REGULATORY_REQUIREMENTS['capital_adequacy_ratio'])
            analysis = f'资本充足率为{value:.2f}%，监管要求为{self.REGULATORY_REQUIREMENTS["capital_adequacy_ratio"]}%。'
            if rating in ['excellent', 'good']:
                analysis += '整体资本充足性良好。'
            elif rating == 'warning':
                analysis += '整体资本充足性不足，需补充资本。'
            results.append(BankInterpretation('capital_adequacy', '资本充足率', value, rating, analysis))

        if '杠杆率' in data:
            value = data['杠杆率']
            rating = self._rate(value, self.REGULATORY_REQUIREMENTS['leverage_ratio'])
            analysis = f'杠杆率为{value:.2f}%，监管要求为{self.REGULATORY_REQUIREMENTS["leverage_ratio"]}%。'
            if rating in ['excellent', 'good']:
                analysis += '杠杆水平合理。'
            elif rating == 'warning':
                analysis += '杠杆水平过高，需注意风险。'
            results.append(BankInterpretation('capital_adequacy', '杠杆率', value, rating, analysis))

        return results

    def _analyze_asset_quality(self) -> List[BankInterpretation]:
        results = []
        data = self.data

        if '不良贷款率' in data:
            value = data['不良贷款率']
            rating = self._rate(value, self.REGULATORY_REQUIREMENTS['npl_ratio_warning'], higher_better=False)
            analysis = f'不良贷款率为{value:.2f}%。'
            if rating in ['excellent', 'good']:
                analysis += '资产质量优秀。'
            elif rating == 'warning':
                analysis += '资产质量较差，需关注信用风险。'
            results.append(BankInterpretation('asset_quality', '不良贷款率', value, rating, analysis))

        if '拨备覆盖率' in data:
            value = data['拨备覆盖率']
            rating = self._rate(value, self.REGULATORY_REQUIREMENTS['provision_coverage_safe'])
            analysis = f'拨备覆盖率为{value:.2f}%，监管安全线为{self.REGULATORY_REQUIREMENTS["provision_coverage_safe"]}%。'
            if rating in ['excellent', 'good']:
                analysis += '风险缓冲充足。'
            elif rating == 'warning':
                analysis += '风险缓冲不足，需提高拨备。'
            results.append(BankInterpretation('asset_quality', '拨备覆盖率', value, rating, analysis))

        return results

    def _analyze_profitability(self) -> List[BankInterpretation]:
        results = []
        data = self.data

        if '净息差' in data:
            value = data['净息差']
            rating = self._rate(value, 2.0, higher_better=True)
            analysis = f'净息差为{value:.2f}%。'
            if rating in ['excellent', 'good']:
                analysis += '盈利能力较强。'
            elif rating == 'warning':
                analysis += '盈利能力较弱，需关注息差收窄风险。'
            results.append(BankInterpretation('profitability', '净息差', value, rating, analysis))

        return results

    def _analyze_liquidity(self) -> List[BankInterpretation]:
        results = []
        data = self.data

        if '流动性覆盖率' in data:
            value = data['流动性覆盖率']
            rating = self._rate(value, self.REGULATORY_REQUIREMENTS['liquidity_coverage'])
            analysis = f'流动性覆盖率为{value:.2f}%，监管要求为{self.REGULATORY_REQUIREMENTS["liquidity_coverage"]}%。'
            if rating in ['excellent', 'good']:
                analysis += '短期流动性充足。'
            elif rating == 'warning':
                analysis += '短期流动性不足，需关注流动性风险。'
            results.append(BankInterpretation('liquidity', '流动性覆盖率', value, rating, analysis))

        if '净稳定资金比率' in data:
            value = data['净稳定资金比率']
            rating = self._rate(value, self.REGULATORY_REQUIREMENTS['net_stable_funding'])
            analysis = f'净稳定资金比率为{value:.2f}%，监管要求为{self.REGULATORY_REQUIREMENTS["net_stable_funding"]}%。'
            if rating in ['excellent', 'good']:
                analysis += '长期流动性充足。'
            elif rating == 'warning':
                analysis += '长期流动性不足，需关注长期资金来源。'
            results.append(BankInterpretation('liquidity', '净稳定资金比率', value, rating, analysis))

        return results

    def _overall_assessment(self) -> Dict:
        capital = self._analyze_capital()
        asset = self._analyze_asset_quality()
        profit = self._analyze_profitability()
        liquidity = self._analyze_liquidity()

        all_interpretations = capital + asset + profit + liquidity
        rating_counts = {r: 0 for r in ['excellent', 'good', 'average', 'poor', 'warning']}
        for interp in all_interpretations:
            rating_counts[interp.rating] += 1

        total = len(all_interpretations)
        if total == 0:
            return {
                'overall_score': 0,
                'overall_rating': 'insufficient_data',
                'summary': '数据不足，无法评估',
                'investment_advice': 'N/A',
                'risk_alerts': []
            }

        weighted_score = (
            rating_counts['excellent'] * 1.0 +
            rating_counts['good'] * 0.8 +
            rating_counts['average'] * 0.6 +
            rating_counts['poor'] * 0.4 +
            rating_counts['warning'] * 0.0
        ) / total

        if weighted_score >= 0.9:
            overall_rating = 'excellent'
            investment_advice = '强烈推荐'
        elif weighted_score >= 0.7:
            overall_rating = 'good'
            investment_advice = '推荐'
        elif weighted_score >= 0.5:
            overall_rating = 'average'
            investment_advice = '中性'
        elif weighted_score >= 0.3:
            overall_rating = 'poor'
            investment_advice = '不推荐'
        else:
            overall_rating = 'warning'
            investment_advice = '强烈不推荐'

        risk_alerts = []
        if rating_counts['warning'] > 0:
            risk_alerts.append(f'存在{rating_counts["warning"]}项高风险指标')
        if rating_counts['poor'] > 2:
            risk_alerts.append(f'存在{rating_counts["poor"]}项中风险指标')

        summary = f'综合评分{weighted_score:.2f}，评级{overall_rating}。'
        if risk_alerts:
            summary += f' 风险提示：{"；".join(risk_alerts)}。'

        return {
            'overall_score': weighted_score,
            'overall_rating': overall_rating,
            'summary': summary,
            'investment_advice': investment_advice,
            'risk_alerts': risk_alerts,
            'rating_distribution': rating_counts
        }