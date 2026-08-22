# -*- coding: utf-8 -*-
"""P1-7 模型解释链：对每个分数给出可解释的分解/原因，供审计回溯。

把每个维度从"原始输入 → 处理 → 分位 → 阈值判定 → 对综合分贡献"串成人类可读的链条。
"""
from __future__ import annotations

from typing import Optional


def _pct_text(v):
    if v is None:
        return '数据不足'
    return f'{round(v, 1)}%'


def explain_signal(metrics: dict, comp: dict, thresholds: dict,
                   hysteresis: dict, vt_level: str, final_signal: str,
                   note: list, cfg: Optional[dict] = None) -> list:
    """生成解释链(有序步骤列表)。metrics/comp 来自 compute_signal 的输入与分量。"""
    chain = []
    hs = hysteresis or {}
    th = thresholds or {}

    # 1. 三指标(原始输入 → 分位)
    pe_pct = metrics.get('pe_pct')
    chain.append({
        'step': '1. PE分位(低估维度)', 'input': '当前PE历史分位',
        'value': _pct_text(pe_pct),
        'threshold': f'进入<{hs.get("pe_entry", th.get("pe"))}%，退出>{hs.get("pe_exit", th.get("pe"))}%',
        'result': '达标' if (pe_pct is not None and pe_pct < th.get('pe', 30)) else '未达标/无数据',
        'score': comp.get('pe'),
    })
    dy_pct = metrics.get('dy_pct')
    chain.append({
        'step': '2. 股息率分位(分红维度)', 'input': '当前股息率历史分位',
        'value': _pct_text(dy_pct),
        'threshold': f'进入>{hs.get("dy_entry", th.get("dy"))}%，退出<{hs.get("dy_exit", th.get("dy"))}%',
        'result': '达标' if (dy_pct is not None and dy_pct > th.get('dy', 70)) else '未达标/无数据',
        'score': comp.get('dy'),
    })
    pr_pct = metrics.get('pr_pct')
    chain.append({
        'step': '3. 分红率分位(分红持续性)', 'input': '当前分红率历史分位',
        'value': _pct_text(pr_pct),
        'threshold': f'进入<{hs.get("pr_entry", th.get("payout"))}%，退出>{hs.get("pr_exit", th.get("payout"))}%',
        'result': '达标' if (pr_pct is not None and pr_pct < th.get('payout', 70)) else '未达标/无数据',
        'score': comp.get('payout'),
    })

    # 4. Gordon 可持续增速
    gs = comp.get('gordon_status')
    chain.append({
        'step': '4. Gordon可持续增速', 'input': 'ROE×(1-分红率) 与 Ke 的差',
        'value': ('失效/数据不足' if gs is None else gs),
        'threshold': 'Ke-g<=2% 判失效(计0分)',
        'result': '计分' if gs == 'VALID' else '不计分并降置信度',
        'score': comp.get('gordon'),
    })

    # 5. 质量/行业
    chain.append({
        'step': '5. 基本面质量', 'input': '财务质量子模型',
        'value': 'N/A', 'threshold': '权重内合成',
        'result': '含于综合分', 'score': comp.get('quality'),
    })
    chain.append({
        'step': '6. 行业景气', 'input': '行业评分',
        'value': 'N/A', 'threshold': '权重内合成',
        'result': '含于综合分', 'score': comp.get('industry'),
    })

    # 7. 价值陷阱调整 + 最终信号
    chain.append({
        'step': '7. 价值陷阱惩罚', 'input': '陷阱评分',
        'value': vt_level, 'threshold': '高风险禁STRONG_BUY',
        'result': '下调最终信号', 'score': None,
    })
    chain.append({
        'step': '8. 最终信号', 'input': '综合分×风险调整',
        'value': final_signal,
        'threshold': '分档映射',
        'result': '；'.join(note) if note else '无额外说明',
        'score': comp.get('_final', None),
    })
    return chain