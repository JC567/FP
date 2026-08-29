# -*- coding: utf-8 -*-
"""核心数据结构（dataclass）。统一 Data Model，支持 to_dict / from_dict 以序列化 JSON。"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


def _asdict(obj):
    return asdict(obj)


@dataclass
class MarketData:
    """市场数据：date=日期, close=原始收盘价, adj_close=后复权价, volume=成交量, market_cap=总市值。
    估值一律用 close（原始价）；adj_close 仅用于收益/回测分析。"""
    date: Any                # Timestamp/str
    close: Optional[float] = None
    adj_close: Optional[float] = None
    volume: Optional[float] = None
    market_cap: Optional[float] = None


@dataclass
class ValuationPoint:
    """时点估值：PE_TTM 及有效性/异常标记。EPS<=0 时 pe_valid=False。"""
    date: Any
    pe_ttm: Optional[float] = None
    pe_valid: bool = True
    pe_outlier_flag: bool = False
    source: str = ''


@dataclass
class FinancialSnapshot:
    """财报快照（含 PIT 公告日）。report_period=报告期(如 2025-12-31)。"""
    report_period: str
    announcement_date: Any = None
    announcement_date_source: str = 'ESTIMATED'  # P0-3: REAL/FALLBACK/ESTIMATED
    revenue: Optional[float] = None
    net_profit_attr: Optional[float] = None   # 归母净利润
    eps_basic: Optional[float] = None          # 基本每股收益
    ocf: Optional[float] = None                # 经营现金流净额
    total_assets: Optional[float] = None
    total_liabilities: Optional[float] = None
    int_bearing_debt: Optional[float] = None
    industry_type: Optional[str] = None
    data_source: str = ''


@dataclass
class DividendRecord:
    """分红记录。announce_date=公告日, implement_date=实施方案公告日, reg_date=股权登记日。"""
    report_period: str
    dividend_type: str = ''                    # 年度分红/中期分红
    per_share_cash: Optional[float] = None     # 每股现金(元)
    announce_date: Any = None
    implement_date: Any = None
    reg_date: Any = None


@dataclass
class PitSnapshot:
    """asof(t) 时点可用快照：用于所有后续计算，天然只含 t 前已公告数据。"""
    date: Any
    price: Optional[float] = None
    eps_ttm: Optional[float] = None            # PIT TTM EPS
    pe_ttm: Optional[float] = None
    pe_valid: bool = False                     # P0-10: PE 是否有效
    pe_source: str = ''                        # P0-10: PE 来源 (PIT_CALCULATED / EXTERNAL_HISTORICAL_PE)
    dps_ttm: Optional[float] = None            # PIT TTM 每股现金分红
    dividend_yield: Optional[float] = None     # %
    payout_ratio: Optional[float] = None       # % (TTM 现金分红/归母净利)
    payout_ratio_source: str = 'PER_SHARE'     # P0-5: STRICT_TOTAL / PER_SHARE
    payout_crosscheck: Optional[dict] = None   # P0-5: 每股 vs 总额 交叉验证
    net_profit_ttm: Optional[float] = None
    ocf_ttm: Optional[float] = None
    net_profit_attr_latest: Optional[float] = None
    total_assets: Optional[float] = None
    total_liabilities: Optional[float] = None
    int_bearing_debt: Optional[float] = None
    cash_dividend_total_ttm: Optional[float] = None
    # P0-7: 可追溯性字段
    report_period: Optional[str] = None        # 锚点报告期
    announcement_date: Optional[str] = None    # 锚点公告日
    revision_version: Optional[int] = None     # 锚点修订版本号


@dataclass
class PercentileStats:
    """分位统计：pct 为严格 count 口径（低于当前值占比）。"""
    pct_10y: Optional[float] = None
    pct_5y: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    median: Optional[float] = None
    p10: Optional[float] = None
    p20: Optional[float] = None
    p25: Optional[float] = None
    p30: Optional[float] = None
    p50: Optional[float] = None
    p70: Optional[float] = None
    p75: Optional[float] = None
    p80: Optional[float] = None
    p90: Optional[float] = None
    n_valid: int = 0
    n_excluded: int = 0
    window_10y_start: Optional[str] = None
    window_10y_end: Optional[str] = None
    window_5y_start: Optional[str] = None
    window_5y_end: Optional[str] = None


@dataclass
class QualityResult:
    """基本面质量评分(0-100)。sub 含各模块分数。"""
    score: float = 0.0
    sub: Dict[str, float] = field(default_factory=dict)
    detail: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValueTrapResult:
    """价值陷阱评分(0-100) + 等级 + 触发项。"""
    score: float = 0.0
    level: str = 'LOW'
    flags: List[str] = field(default_factory=list)
    penalty: float = 0.0


@dataclass
class SignalResult:
    """信号：三条件 + 规则信号 + 分数信号 + 陷阱信号 + 最终信号。"""
    condition_a: bool = False   # PE 低估
    condition_b: bool = False   # 股息率高
    condition_c: bool = False   # 分红率合理
    rule_signal: str = 'NEUTRAL'
    score: float = 0.0
    score_signal: str = 'WAIT'
    value_trap_level: str = 'LOW'
    final_signal: str = 'WAIT'
    note: str = ''


@dataclass
class PriceRange:
    """价格区间：GGM 合理PE反推 + 股息率反推 + 历史分位映射 + 分档。"""
    fair_pe_low: Optional[float] = None
    fair_pe_base: Optional[float] = None
    fair_pe_high: Optional[float] = None
    fair_price_low: Optional[float] = None
    fair_price_base: Optional[float] = None
    fair_price_high: Optional[float] = None
    price_at_4pct: Optional[float] = None
    price_at_5pct: Optional[float] = None
    price_at_6pct: Optional[float] = None
    price_at_7pct: Optional[float] = None
    pe_p20_price: Optional[float] = None
    pe_p30_price: Optional[float] = None
    pe_p50_price: Optional[float] = None
    deep_buy_low: Optional[float] = None
    deep_buy_high: Optional[float] = None
    standard_buy_low: Optional[float] = None
    standard_buy_high: Optional[float] = None
    current_zone: str = ''


@dataclass
class PositionPlan:
    """目标仓位建议。"""
    signal: str = ''
    init_weight: float = 0.0
    max_weight: float = 0.0
    target_weight: float = 0.0
    rationale: str = ''


@dataclass
class Traceability:
    """指标可追溯信息。"""
    key: str = ''
    data_source: str = ''
    data_date: str = ''
    formula: str = ''
    sample_start: str = ''
    sample_end: str = ''
    n_valid: int = 0
    n_excluded: int = 0
    outlier_handling: str = ''
    warnings: List[str] = field(default_factory=list)


@dataclass
class AnalysisReport:
    """完整分析结果：估值 + 质量 + 陷阱 + 信号 + 价格 + 仓位 + 可追溯 + 局限。"""
    symbol: str = ''
    name: str = ''
    analysis_date: str = ''
    mode: str = 'balanced'
    industry: str = ''          # 行业名称（如 '银行'）
    industry_type: str = ''     # 行业大类（如 '银行'/'制造业'），巴菲特模式据此限定能力圈
    valuation: Dict[str, Any] = field(default_factory=dict)
    fundamental: Dict[str, Any] = field(default_factory=dict)
    value_trap: Dict[str, Any] = field(default_factory=dict)
    signal: Dict[str, Any] = field(default_factory=dict)
    price: Dict[str, Any] = field(default_factory=dict)
    position: Dict[str, Any] = field(default_factory=dict)
    trace: Dict[str, Any] = field(default_factory=dict)
    quality_warnings: List[str] = field(default_factory=list)
    data_limitations: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return _asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'AnalysisReport':
        return cls(**d)