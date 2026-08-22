# -*- coding: utf-8 -*-
"""配置加载与模式(mode)合并。默认 balanced；conservative/aggressive 覆盖关键阈值。"""
from __future__ import annotations

import copy
import os
from typing import Any, Dict

import yaml

_CFG = None


def _load() -> Dict[str, Any]:
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, 'settings.yaml')
    with open(path, encoding='utf-8') as f:
        return yaml.safe_load(f)


def get_config(mode: str = 'balanced') -> Dict[str, Any]:
    """返回合并 mode 后的配置字典（深层合并）。"""
    global _CFG
    if _CFG is None:
        _CFG = _load()
    cfg = copy.deepcopy(_CFG)
    mode_key = (mode or 'balanced').lower()
    if mode_key not in ('conservative', 'balanced', 'aggressive'):
        mode_key = 'balanced'
    overrides = _CFG.get('modes', {}).get(mode_key, {})
    _deep_set(cfg, overrides)
    cfg['mode'] = mode_key
    return cfg


def _deep_set(cfg: Dict, overrides: Dict) -> None:
    """用 dotted-key 覆盖，如 'signals.pe_percentile'。"""
    for k, v in overrides.items():
        parts = k.split('.')
        node = cfg
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = v


def get_mode_params(cfg: Dict[str, Any]) -> Dict[str, float]:
    """取信号阈值（按模式已合并）。"""
    s = cfg.get('signals', {})
    return {
        'pe_percentile': s.get('pe_percentile', 30),
        'dividend_percentile': s.get('dividend_percentile', 70),
        'payout_percentile': s.get('payout_percentile', 70),
    }


def check() -> Dict[str, Any]:
    for m in ('conservative', 'balanced', 'aggressive'):
        cfg = get_config(m)
        sp = get_mode_params(cfg)
        assert sp['pe_percentile'] >= 0
        assert sp['dividend_percentile'] <= 100
    return get_config('balanced')


if __name__ == '__main__':
    c = check()
    print('config OK')
    print('balanced signals:', get_mode_params(c))
    print('conservative signals:', get_mode_params(get_config('conservative')))
    print('aggressive signals:', get_mode_params(get_config('aggressive')))