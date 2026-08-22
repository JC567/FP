# -*- coding: utf-8 -*-
"""JSON 输出。"""
from __future__ import annotations

import json

from valresearch.models import AnalysisReport


def report_to_dict(rep: AnalysisReport) -> dict:
    return rep.to_dict()


def save_json(rep: AnalysisReport, path: str) -> str:
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(rep.to_dict(), f, ensure_ascii=False, indent=2, default=str)
    return path


def load_json(path: str) -> dict:
    with open(path, encoding='utf-8') as f:
        return json.load(f)