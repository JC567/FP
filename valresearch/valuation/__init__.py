# -*- coding: utf-8 -*-
"""估值计算包：序列构建 / 分位引擎 / Gordon / 价格区间。
注：`gordon` 导出为子模块（可用 gordon.gordon()），避免与内部函数名遮蔽。"""
from valresearch.valuation import engine, percentile, gordon, price_range
from valresearch.valuation.percentile import (count_pct, percentile_stats, filter_pe,
                                              filter_payout, percentile_5y)
from valresearch.valuation.gordon import (scenario_matrix, compute_growth,
                                          pe_fair_ratio, pe_fair_band, fair_price)
from valresearch.valuation.price_range import (buy_range, current_zone, price_at_dy,
                                               hist_price_map)
from valresearch.valuation.engine import build_series

__all__ = ['engine', 'percentile', 'gordon', 'price_range',
           'count_pct', 'percentile_stats', 'filter_pe', 'filter_payout', 'percentile_5y',
           'scenario_matrix', 'compute_growth', 'pe_fair_ratio', 'pe_fair_band',
           'fair_price', 'buy_range', 'current_zone', 'price_at_dy', 'hist_price_map',
           'build_series']