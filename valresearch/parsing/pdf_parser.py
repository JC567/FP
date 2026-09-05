# -*- coding: utf-8 -*-
"""PDF财报解析器 - 基于文本提取的银行财报解析。"""
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from pathlib import Path

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False


@dataclass
class MetricValue:
    metric_name: str
    value: float
    unit: str
    period: str
    is_consolidated: bool
    page_number: Optional[int] = None
    confidence: float = 1.0


@dataclass
class TextSection:
    content_type: str
    section_title: str
    content: str
    page_number: int


@dataclass
class ParseResult:
    symbol: str
    report_date: str
    report_type: str
    metrics: List[MetricValue] = field(default_factory=list)
    text_sections: List[TextSection] = field(default_factory=list)
    parse_warnings: List[str] = field(default_factory=list)
    parse_errors: List[str] = field(default_factory=list)

    def get_metric(self, metric_name: str) -> Optional[float]:
        for m in self.metrics:
            if m.metric_name == metric_name:
                return m.value
        return None


class PDFParser:
    BANK_METRICS = {
        '营业收入': {'name': '营业收入', 'unit': '百万元', 'category': 'income'},
        '归属于本行股东的净利润': {'name': '归母净利润', 'unit': '百万元', 'category': 'income'},
        '净利润': {'name': '净利润', 'unit': '百万元', 'category': 'income'},
        '归属于本行普通股股东的基本每股收益': {'name': '基本每股收益', 'unit': '元', 'category': 'income'},
        '经营活动产生的现金流量净额': {'name': '经营活动现金流量净额', 'unit': '百万元', 'category': 'cashflow'},
        '总资产': {'name': '总资产', 'unit': '百万元', 'category': 'balance'},
        '总负债': {'name': '总负债', 'unit': '百万元', 'category': 'balance'},
        '归属于本行股东权益': {'name': '归母权益', 'unit': '百万元', 'category': 'balance'},
        '贷款和垫款总额': {'name': '贷款总额', 'unit': '百万元', 'category': 'balance'},
        '不良贷款': {'name': '不良贷款', 'unit': '百万元', 'category': 'balance'},
        '贷款损失准备': {'name': '贷款损失准备', 'unit': '百万元', 'category': 'balance'},
        '客户存款总额': {'name': '存款总额', 'unit': '百万元', 'category': 'balance'},
        '核心一级资本净额': {'name': '核心一级资本净额', 'unit': '百万元', 'category': 'capital'},
        '一级资本净额': {'name': '一级资本净额', 'unit': '百万元', 'category': 'capital'},
        '资本净额': {'name': '资本净额', 'unit': '百万元', 'category': 'capital'},
        '风险加权资产': {'name': '风险加权资产', 'unit': '百万元', 'category': 'capital'},
    }

    BANK_RATIOS = {
        '归属于本行普通股股东的每股净资产': {'name': '每股净资产', 'unit': '元', 'category': 'balance'},
        '核心一级资本充足率': {'name': '核心一级资本充足率', 'unit': '%', 'category': 'capital_adequacy'},
        '一级资本充足率': {'name': '一级资本充足率', 'unit': '%', 'category': 'capital_adequacy'},
        '资本充足率': {'name': '资本充足率', 'unit': '%', 'category': 'capital_adequacy'},
        '不良贷款率': {'name': '不良贷款率', 'unit': '%', 'category': 'asset_quality'},
        '拨备覆盖率': {'name': '拨备覆盖率', 'unit': '%', 'category': 'asset_quality'},
        '贷款拨备率': {'name': '贷款拨备率', 'unit': '%', 'category': 'asset_quality'},
        '净利息收益率': {'name': '净息差', 'unit': '%', 'category': 'profitability'},
        '净利差': {'name': '净利差', 'unit': '%', 'category': 'profitability'},
        '成本收入比': {'name': '成本收入比', 'unit': '%', 'category': 'profitability'},
        '流动性覆盖率': {'name': '流动性覆盖率', 'unit': '%', 'category': 'liquidity'},
        '流动性比例': {'name': '流动性比例', 'unit': '%', 'category': 'liquidity'},
        '归属于本行普通股股东的平均净资产收益率': {'name': 'ROE', 'unit': '%', 'category': 'profitability'},
        '归属于本行股东的平均总资产收益率': {'name': 'ROA', 'unit': '%', 'category': 'profitability'},
    }

    TEXT_SECTION_KEYWORDS = {
        'management_discussion': ['管理层讨论', '经营情况', '讨论与分析', '业务回顾', '经营回顾'],
        'risk_factors': ['风险因素', '风险管理', '面临的风险'],
        'business_description': ['公司业务', '业务概况', '主营业务', '公司简介'],
    }

    def __init__(self, pdf_path: str, symbol: str):
        self.pdf_path = Path(pdf_path)
        self.symbol = symbol
        if not PDFPLUMBER_AVAILABLE:
            raise ImportError('pdfplumber未安装，请运行: pip install pdfplumber')

    def parse(self) -> ParseResult:
        result = ParseResult(
            symbol=self.symbol,
            report_date='',
            report_type=''
        )

        try:
            with pdfplumber.open(self.pdf_path) as pdf:
                result.parse_warnings.append('开始解析PDF，共{}页'.format(len(pdf.pages)))

                all_text = []
                for i, page in enumerate(pdf.pages, 1):
                    text = page.extract_text()
                    if text:
                        all_text.append((i, text))

                self._extract_report_info(all_text, result)
                self._extract_metrics_from_text(all_text, result)
                self._extract_text_sections(all_text, result)

                if not result.metrics:
                    result.parse_errors.append('未提取到任何财务数据')
                else:
                    result.parse_warnings.append('成功提取{}个指标'.format(len(result.metrics)))

        except Exception as e:
            result.parse_errors.append('PDF解析失败: {}'.format(str(e)))

        return result

    def _extract_report_info(self, all_text: List[Tuple[int, str]], result: ParseResult):
        for page_num, text in all_text[:15]:
            date_match = re.search(r'(\d{4})年.*?半年度报告', text)
            if date_match:
                year = date_match.group(1)
                result.report_date = '{}-06-30'.format(year)
                result.report_type = 'half_year'
                return

            date_match = re.search(r'(\d{4})年.*?年度报告', text)
            if date_match:
                year = date_match.group(1)
                result.report_date = '{}-12-31'.format(year)
                result.report_type = 'annual'
                return

    def _extract_metrics_from_text(self, all_text: List[Tuple[int, str]], result: ParseResult):
        for page_num, text in all_text:
            lines = text.split('\n')
            for i, line in enumerate(lines):
                self._parse_metric_line(line, page_num, result)
                # 处理跨行：关键词在当前行，数值在下一行
                if i + 1 < len(lines):
                    merged = line.strip() + ' ' + lines[i + 1].strip()
                    self._parse_metric_line(merged, page_num, result)

    def _parse_metric_line(self, line: str, page_num: int, result: ParseResult):
        line = line.strip()
        if not line:
            return

        all_keywords = []
        for keyword, info in self.BANK_METRICS.items():
            all_keywords.append((keyword, info, 'metric'))
        for keyword, info in self.BANK_RATIOS.items():
            all_keywords.append((keyword, info, 'ratio'))

        all_keywords.sort(key=lambda x: len(x[0]), reverse=True)

        matched_keywords = set()
        for keyword, info, kind in all_keywords:
            if keyword in line and keyword not in matched_keywords:
                skip = False
                for matched_kw in matched_keywords:
                    if keyword in matched_kw:
                        skip = True
                        break
                if skip:
                    continue

                if kind == 'metric':
                    existing = [m for m in result.metrics if m.metric_name == info['name']]
                    if existing:
                        continue
                    value = self._extract_number_after_keyword(line, keyword)
                    if value is not None:
                        result.metrics.append(MetricValue(
                            metric_name=info['name'],
                            value=value,
                            unit=info['unit'],
                            period=result.report_date,
                            is_consolidated=True,
                            page_number=page_num,
                            confidence=0.95
                        ))
                        matched_keywords.add(keyword)
                else:
                    existing = [m for m in result.metrics if m.metric_name == info['name']]
                    if existing:
                        continue
                    value = self._extract_ratio_after_keyword(line, keyword)
                    if value is not None:
                        result.metrics.append(MetricValue(
                            metric_name=info['name'],
                            value=value,
                            unit=info['unit'],
                            period=result.report_date,
                            is_consolidated=True,
                            page_number=page_num,
                            confidence=0.95
                        ))
                        matched_keywords.add(keyword)

    def _extract_number_after_keyword(self, line: str, keyword: str) -> Optional[float]:
        pattern = re.escape(keyword) + r'\s*([\d,\.]+)'
        match = re.search(pattern, line)
        if match:
            num_str = match.group(1).replace(',', '')
            try:
                return float(num_str)
            except ValueError:
                return None
        return None

    def _extract_ratio_after_keyword(self, line: str, keyword: str) -> Optional[float]:
        # 跳过括号内的数字（如脚注标记(1)），找到第一个真正的数值
        pattern = re.escape(keyword) + r'.*?[\)\）]\s*([\d,\.]+)'
        match = re.search(pattern, line)
        if match:
            num_str = match.group(1).replace(',', '')
            try:
                return float(num_str)
            except ValueError:
                return None
        return None

    def _extract_text_sections(self, all_text: List[Tuple[int, str]], result: ParseResult):
        for page_num, text in all_text:
            for section_type, keywords in self.TEXT_SECTION_KEYWORDS.items():
                for keyword in keywords:
                    if keyword in text:
                        lines = text.split('\n')
                        section_lines = []
                        capturing = False
                        for line in lines:
                            if keyword in line:
                                capturing = True
                            if capturing:
                                section_lines.append(line)
                        if section_lines:
                            result.text_sections.append(TextSection(
                                content_type=section_type,
                                section_title=keyword,
                                content='\n'.join(section_lines[:50]),
                                page_number=page_num
                            ))
                        break

    def get_metric(self, metric_name: str) -> Optional[float]:
        return None
