# -*- coding: utf-8 -*-
"""红利价值分位研究 - 命令行入口。用法:
    python main_valresearch.py 600036 --name 招商银行 --date 2025-07-01 --mode balanced [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import sys

from valresearch.main import analyze
from valresearch.config import get_config
from valresearch.i18n import cn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('symbol')
    ap.add_argument('--name', default='')
    ap.add_argument('--date', default=None)
    ap.add_argument('--mode', default='balanced',
                    choices=['conservative', 'balanced', 'aggressive'])
    ap.add_argument('--json', default=None, help='输出 JSON 文件路径')
    ap.add_argument('--quiet', action='store_true', help='不打印进度')
    args = ap.parse_args()
    cfg = get_config(args.mode)

    def _cb(p, msg):
        if not args.quiet:
            sys.stdout.write(f'[{int(p*100):3d}%] {msg}\n')
            sys.stdout.flush()

    rep = analyze(args.symbol, args.date, args.mode, args.name, cfg, progress_cb=_cb)
    d = rep.to_dict()
    if args.json:
        import os
        ddir = os.path.dirname(os.path.abspath(args.json))
        if ddir:
            os.makedirs(ddir, exist_ok=True)
        with open(args.json, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=2, default=str)
        print('JSON 已写出:', args.json)
    # 终端摘要（中文）
    v = d.get('valuation', {})
    s = d.get('signal', {})
    print('=== %s(%s) %s 模式=%s ===' % (d['name'], d['symbol'], d['analysis_date'], cn(d['mode'])))
    print('价格 %.2f | PE %.2f(10年分位 %s%% | 5年 %s%%) | 股息率 %.2f%%(%s%%分位) | 分红率 %.1f%%(%s%%分位)'
          % (v.get('price', 0), v.get('pe_ttm', 0), v.get('pe_pct_10y'),
             v.get('pe_pct_5y'), v.get('dividend_yield', 0), v.get('dividend_yield_pct'),
             v.get('payout_ratio', 0), v.get('payout_pct')))
    print('10年国债 %.2f%% | 股息-国债利差 %s%%(阈值%s%%)' % (v.get('rf_10y'), v.get('dividend_spread'),
                                              v.get('spread_threshold')))
    print('Gordon: 基准合理PE %s | 当前/合理 %.2f | %s | 增长率 g=%.4f'
          % (s.get('gordon_scenario', {}).get('fair_pe_base'), s.get('pe_fair_ratio'),
             cn(s.get('pe_fair_band')), s.get('gordon_g')))
    print('质量分 %.1f | 价值陷阱 %s(%s) 惩罚%.2f' % (d.get('fundamental', {}).get('quality_score'),
                                              cn(d.get('value_trap', {}).get('level')),
                                              d.get('value_trap', {}).get('score'),
                                              d.get('value_trap', {}).get('penalty')))
    print('信号: %s | 规则=%s | 综合分=%.1f(%s) | %s' % (cn(s.get('final_signal')), cn(s.get('rule_signal')),
                                                s.get('score'), cn(s.get('score_signal')),
                                                cn(s.get('note'))))
    p = d.get('price', {})
    print('买入区间: 深度 %.2f~%.2f | 标准 %.2f~%.2f | Gordon合理 %.2f | @5%%股息率 %.2f | 当前区:%s'
          % (p.get('deep_buy_low'), p.get('deep_buy_high'), p.get('standard_buy_low'),
             p.get('standard_buy_high'), p.get('fair_price_base'), p.get('price_at_5pct'),
             p.get('current_zone')))
    pos = d.get('position', {})
    print('仓位: 初始%.1f%% 建议%.1f%% 上限%.1f%% (%s)' % (pos.get('init_weight', 0) * 100,
                                                   pos.get('target_weight', 0) * 100,
                                                   pos.get('max_weight', 0) * 100,
                                                   cn(pos.get('rationale'))))
    for w in d.get('data_limitations', []):
        print('  局限:', cn(w))


if __name__ == '__main__':
    main()