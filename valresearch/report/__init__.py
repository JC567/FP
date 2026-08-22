# -*- coding: utf-8 -*-
"""报告输出：九段式文本 + JSON。"""
from valresearch.report.generator import format_report
from valresearch.report.json_output import save_json, load_json, report_to_dict
__all__ = ['format_report', 'save_json', 'load_json', 'report_to_dict']