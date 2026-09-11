# -*- coding: utf-8 -*-
"""银行价值投资模型（Bank Value Investment Model）。

仅适用于A股银行业。使用银行盈利能力+资产质量+资本稳健+分红能力+PB绝对估值+历史估值分位，
判断银行是否进入价值投资累积区，输出严格量化、可审计、不可妥协的数据结果。

核心原则：
1. 能力圈限定：仅银行业
2. 数据缺失绝不妥协：缺失→DATA_INSUFFICIENT
3. 禁止未来函数：严格PIT
4. 结果必须可追溯
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
import math

# ── 状态常量 ──
UNSUPPORTED_INDUSTRY = 'UNSUPPORTED_INDUSTRY'
DATA_INSUFFICIENT = 'DATA_INSUFFICIENT'
QUALITY_FAIL_ROE = 'QUALITY_FAIL_ROE'
QUALITY_FAIL_EARNINGS_DRAWDOWN = 'QUALITY_FAIL_EARNINGS_DRAWDOWN'
QUALITY_FAIL_EARNINGS_DECLINE = 'QUALITY_FAIL_EARNINGS_DECLINE'
QUALITY_FAIL_ASSET = 'QUALITY_FAIL_ASSET'
QUALITY_FAIL_CAPITAL = 'QUALITY_FAIL_CAPITAL'
QUALITY_FAIL_DIVIDEND = 'QUALITY_FAIL_DIVIDEND'
GORDON_INVALID = 'GORDON_INVALID'
STRONG_BUY = 'STRONG_BUY'
ACCUMULATE = 'ACCUMULATE'
HOLD_WAIT = 'HOLD_WAIT'
REASSESS = 'REASSESS'

# ── 硬门槛阈值 ──
ROE_MIN = 10.0                 # ROE(%) 下限
ROE_HIGH = 12.0                # ROE(%) 高质量线
MAX_DRAWDOWN_LIMIT = -40.0     # 净利最大回撤下限(%)
MAX_CONSECUTIVE_DECLINE = 2    # 连续下滑年数上限
NPL_RISING_YEARS_LIMIT = 3    # NPL连续上升年数上限
PROVISION_MIN = 150.0          # 拨备覆盖率下限(%)
CET1_MIN = 6.0                 # 核心一级资本充足率下限(%)
TIER1_MIN = 8.0                # 一级资本充足率下限(%)
CAR_MIN = 10.0                 # 资本充足率下限(%)
DIV_CONSEC_MIN = 5             # 连续分红年数下限
PAYOUT_MAX = 100.0             # 分红率上限(%)
PB_CHEAP = 1.0                 # PB累积区阈值
PB_STRONG = 0.80               # PB强买区阈值
PE_PCT_ACCUM = 30.0            # PE分位累积区阈值(%)
DY_PCT_ACCUM = 70.0            # 股息率分位累积区阈值(%)
PE_PCT_STRONG = 15.0           # PE分位强买区阈值(%)
DY_PCT_STRONG = 85.0           # 股息率分位强买区阈值(%)
PB_FAIR_MARGIN_ACCUM = 0.90    # 累积区：PB <= 合理PB × 此值
PB_FAIR_MARGIN_STRONG = 0.80   # 强买区：PB <= 合理PB × 此值
DEFAULT_KE = 10.0              # 默认股权要求回报率(%)
DEFAULT_RF = 5.0               # 默认无风险利率(%)
VALUE_TRAP_MAX = 50.0          # 价值陷阱分上限


@dataclass
class QualityResult:
    """质量评估结果。"""
    roe: Optional[float] = None
    roe_status: str = ''
    max_drawdown: Optional[float] = None
    max_drawdown_status: str = ''
    consecutive_decline_years: Optional[int] = None
    decline_status: str = ''
    npl_ratio: Optional[float] = None
    npl_trend: str = ''
    provision_coverage: Optional[float] = None
    provision_trend: str = ''
    concern_loan_ratio: Optional[float] = None
    concern_trend: str = ''
    credit_cost: Optional[float] = None
    asset_quality_status: str = ''
    cet1: Optional[float] = None
    tier1: Optional[float] = None
    car: Optional[float] = None
    capital_status: str = ''
    consecutive_div_years: Optional[int] = None
    avg_payout: Optional[float] = None
    latest_payout: Optional[float] = None
    dividend_status: str = ''
    quality_pass: bool = False
    quality_fail_reasons: List[str] = field(default_factory=list)


@dataclass
class ValuationResult:
    """估值结果。"""
    price: Optional[float] = None
    pb: Optional[float] = None
    pe_ttm: Optional[float] = None
    dividend_yield: Optional[float] = None
    bvps: Optional[float] = None
    pb_fair: Optional[float] = None
    pb_fair_method: str = ''
    pb_margin: Optional[float] = None
    pe_pct_10y: Optional[float] = None
    dy_pct_10y: Optional[float] = None
    pb_zone: str = ''  # CHEAP / STRONG / NONE


@dataclass
class BankValueResult:
    """银行价值投资模型最终结果。"""
    symbol: str = ''
    name: str = ''
    industry: str = ''
    industry_type: str = ''
    status: str = ''  # STRONG_BUY / ACCUMULATE / HOLD_WAIT / DATA_INSUFFICIENT / UNSUPPORTED_INDUSTRY
    asof_date: str = ''
    quality: QualityResult = field(default_factory=QualityResult)
    valuation: ValuationResult = field(default_factory=ValuationResult)
    signal_reasons: List[str] = field(default_factory=list)
    fail_reasons: List[str] = field(default_factory=list)
    reassess_conditions: List[str] = field(default_factory=list)
    monthly_multiplier: Optional[float] = None
    data_sources: Dict[str, str] = field(default_factory=dict)
    raw_data: Dict[str, Any] = field(default_factory=dict)


def check_industry(industry_type: str) -> bool:
    """检查是否为银行业。"""
    return industry_type == '银行'


def check_data_completeness(fin: dict, div, t) -> List[str]:
    """检查数据完整性，返回缺失指标列表。"""
    missing = []
    
    # A. 盈利数据
    if fin is None:
        missing.append('财务数据(fin)')
        return missing
    
    # B. 资产质量指标
    for key in ['npl_ratio', 'provision_coverage', 'concern_loan_ratio', 'credit_cost']:
        if key not in fin or fin[key] is None:
            missing.append(key)
    
    # C. 资本指标
    for key in ['cet1', 'tier1', 'car']:
        if key not in fin or fin[key] is None:
            missing.append(key)
    
    # D. 分红数据
    if div is None:
        missing.append('分红数据(div)')
    
    # E. 估值数据
    for key in ['price', 'pb', 'pe_ttm', 'dividend_yield', 'pe_pct', 'dy_pct']:
        if key not in fin or fin[key] is None:
            missing.append(key)
    
    return missing


def calculate_roe(net_profit: Optional[float], equity: Optional[float]) -> Optional[float]:
    """计算ROE(%)。ROE = 归母净利润 / 归母权益 × 100。"""
    if net_profit is None or equity is None or equity == 0:
        return None
    return round(net_profit / equity * 100, 2)


def assess_roe(roe: Optional[float]) -> str:
    """评估ROE状态。"""
    if roe is None:
        return 'DATA_INSUFFICIENT'
    if roe >= ROE_HIGH:
        return 'HIGH'
    elif roe >= ROE_MIN:
        return 'PASS'
    else:
        return 'FAIL'


def calculate_max_drawdown(profits: List[float]) -> Optional[float]:
    """计算净利润最大回撤(%)。"""
    if not profits or len(profits) < 2:
        return None
    max_val = profits[0]
    max_dd = 0.0
    for p in profits[1:]:
        if p > max_val:
            max_val = p
        dd = (p / max_val - 1) * 100 if max_val > 0 else 0
        if dd < max_dd:
            max_dd = dd
    return round(max_dd, 2)


def count_consecutive_declines(profits: List[float]) -> Optional[int]:
    """计算连续盈利下滑年数。"""
    if not profits or len(profits) < 2:
        return None
    max_consecutive = 0
    current = 0
    for i in range(1, len(profits)):
        if profits[i] < profits[i - 1]:
            current += 1
            max_consecutive = max(max_consecutive, current)
        else:
            current = 0
    return max_consecutive


def assess_asset_quality(fin: dict) -> tuple:
    """评估资产质量，返回(status, reasons)。"""
    reasons = []
    npl = fin.get('npl_ratio')
    provision = fin.get('provision_coverage')
    concern = fin.get('concern_loan_ratio')
    credit_cost = fin.get('credit_cost')
    
    if npl is None:
        reasons.append('NPL缺失')
        return DATA_INSUFFICIENT, reasons
    
    # NPL趋势
    npl_history = fin.get('npl_history', [])
    if len(npl_history) >= 3:
        rising_years = sum(1 for i in range(1, len(npl_history)) 
                          if npl_history[i] > npl_history[i-1])
        if rising_years >= NPL_RISING_YEARS_LIMIT:
            reasons.append(f'NPL连续上升{rising_years}年')
            return 'FAIL', reasons
    
    # 拨备覆盖率
    if provision is not None and provision < PROVISION_MIN:
        reasons.append(f'拨备覆盖率{provision}%<{PROVISION_MIN}%')
        return 'FAIL', reasons
    
    return 'PASS', reasons


def assess_capital(fin: dict) -> tuple:
    """评估资本稳健，返回(status, reasons)。"""
    reasons = []
    cet1 = fin.get('cet1')
    tier1 = fin.get('tier1')
    car = fin.get('car')
    
    if cet1 is None and tier1 is None and car is None:
        reasons.append('资本充足率数据全部缺失')
        return DATA_INSUFFICIENT, reasons
    
    if cet1 is not None and cet1 < CET1_MIN:
        reasons.append(f'CET1={cet1}%<{CET1_MIN}%')
    if tier1 is not None and tier1 < TIER1_MIN:
        reasons.append(f'Tier1={tier1}%<{TIER1_MIN}%')
    if car is not None and car < CAR_MIN:
        reasons.append(f'CAR={car}%<{CAR_MIN}%')
    
    if reasons:
        return 'FAIL', reasons
    return 'PASS', reasons


def assess_dividends(div, profits: List[float]) -> tuple:
    """评估分红能力，返回(status, reasons, consecutive_years, avg_payout, latest_payout)。"""
    reasons = []
    if div is None:
        reasons.append('分红数据缺失')
        return DATA_INSUFFICIENT, reasons, 0, None, None
    
    # 连续分红年数
    div_years = getattr(div, 'consecutive_years', None)
    if div_years is None or div_years < DIV_CONSEC_MIN:
        reasons.append(f'连续分红{div_years or 0}年<{DIV_CONSEC_MIN}年')
        return 'FAIL', reasons, div_years or 0, None, None
    
    # 分红率
    payout_ratios = getattr(div, 'payout_ratios', [])
    if payout_ratios:
        avg_payout = sum(payout_ratios) / len(payout_ratios)
        latest_payout = payout_ratios[-1] if payout_ratios else None
        
        # 检查异常分红率
        for i, p in enumerate(payout_ratios):
            if p > PAYOUT_MAX:
                reasons.append(f'第{i+1}年分红率{p:.1f}%>{PAYOUT_MAX}%')
        
        if any(p > PAYOUT_MAX for p in payout_ratios):
            return 'WARNING', reasons, div_years, avg_payout, latest_payout
    
    return 'PASS', reasons, div_years, sum(payout_ratios)/len(payout_ratios) if payout_ratios else None, payout_ratios[-1] if payout_ratios else None


def calculate_reasonable_pb(roe: float, g: float, ke: float) -> Optional[float]:
    """计算合理PB = (ROE - g) / (Ke - g)。"""
    if ke <= g:
        return None
    if roe <= g:
        return None
    return round((roe - g) / (ke - g), 2)


def assess_quality(fin: dict, div, profits: List[float]) -> QualityResult:
    """综合质量评估。"""
    result = QualityResult()
    
    # ROE
    net_profit = fin.get('net_profit')
    equity = fin.get('equity')
    result.roe = calculate_roe(net_profit, equity)
    result.roe_status = assess_roe(result.roe)
    
    # 盈利稳定性
    result.max_drawdown = calculate_max_drawdown(profits)
    if result.max_drawdown is not None:
        result.max_drawdown_status = 'PASS' if result.max_drawdown >= MAX_DRAWDOWN_LIMIT else 'FAIL'
    
    result.consecutive_decline_years = count_consecutive_declines(profits)
    if result.consecutive_decline_years is not None:
        result.decline_status = 'PASS' if result.consecutive_decline_years <= MAX_CONSECUTIVE_DECLINE else 'FAIL'
    
    # 资产质量
    asset_status, asset_reasons = assess_asset_quality(fin)
    result.asset_quality_status = asset_status
    result.npl_ratio = fin.get('npl_ratio')
    result.provision_coverage = fin.get('provision_coverage')
    result.concern_loan_ratio = fin.get('concern_loan_ratio')
    result.credit_cost = fin.get('credit_cost')
    
    # 资本
    cap_status, cap_reasons = assess_capital(fin)
    result.capital_status = cap_status
    result.cet1 = fin.get('cet1')
    result.tier1 = fin.get('tier1')
    result.car = fin.get('car')
    
    # 分红
    div_status, div_reasons, div_years, avg_payout, latest_payout = assess_dividends(div, profits)
    result.dividend_status = div_status
    result.consecutive_div_years = div_years
    result.avg_payout = avg_payout
    result.latest_payout = latest_payout
    
    # 综合判断
    fails = []
    if result.roe_status == 'FAIL':
        fails.append(QUALITY_FAIL_ROE)
    if result.max_drawdown_status == 'FAIL':
        fails.append(QUALITY_FAIL_EARNINGS_DRAWDOWN)
    if result.decline_status == 'FAIL':
        fails.append(QUALITY_FAIL_EARNINGS_DECLINE)
    if asset_status in ('FAIL', DATA_INSUFFICIENT):
        fails.append(QUALITY_FAIL_ASSET)
    if cap_status in ('FAIL', DATA_INSUFFICIENT):
        fails.append(QUALITY_FAIL_CAPITAL)
    if div_status in ('FAIL', DATA_INSUFFICIENT):
        fails.append(QUALITY_FAIL_DIVIDEND)
    
    result.quality_fail_reasons = fails
    result.quality_pass = len(fails) == 0
    
    return result


def assess_valuation(fin: dict) -> ValuationResult:
    """估值评估。"""
    result = ValuationResult()
    result.price = fin.get('price')
    result.pb = fin.get('pb')
    result.pe_ttm = fin.get('pe_ttm')
    result.dividend_yield = fin.get('dividend_yield')
    result.bvps = fin.get('bvps')
    result.pe_pct_10y = fin.get('pe_pct')
    result.dy_pct_10y = fin.get('dy_pct')
    
    # PB区域
    if result.pb is not None:
        if result.pb <= PB_STRONG:
            result.pb_zone = 'STRONG'
        elif result.pb <= PB_CHEAP:
            result.pb_zone = 'CHEAP'
        else:
            result.pb_zone = 'NONE'
    
    return result


def determine_signal(quality: QualityResult, valuation: ValuationResult) -> tuple:
    """确定最终信号，返回(status, reasons, monthly_multiplier)。"""
    reasons = []
    
    # 质量不通过
    if not quality.quality_pass:
        reasons.extend(quality.quality_fail_reasons)
        return HOLD_WAIT, reasons, 0.0
    
    # 估值检查
    pb = valuation.pb
    pe_pct = valuation.pe_pct_10y
    dy_pct = valuation.dy_pct_10y
    pb_fair = valuation.pb_fair
    
    # 强买区判断
    strong_buy = False
    if pb is not None and pb <= PB_STRONG:
        strong_buy = True
        reasons.append(f'PB={pb:.2f}<=0.80深度破净')
    elif pb is not None and pb_fair is not None and pb <= pb_fair * PB_FAIR_MARGIN_STRONG:
        strong_buy = True
        reasons.append(f'PB={pb:.2f}<=合理PB×0.80={pb_fair*0.8:.2f}')
    elif (pb is not None and pb <= PB_CHEAP and 
          pe_pct is not None and pe_pct <= PE_PCT_STRONG):
        strong_buy = True
        reasons.append(f'PB={pb:.2f}<=1.0且PE分位={pe_pct:.1f}%<=15%')
    elif (pb is not None and pb <= PB_CHEAP and 
          dy_pct is not None and dy_pct >= DY_PCT_STRONG):
        strong_buy = True
        reasons.append(f'PB={pb:.2f}<=1.0且股息率分位={dy_pct:.1f}%>=85%')
    
    if strong_buy:
        return STRONG_BUY, reasons, 2.0
    
    # 累积区判断
    if pb is not None and pb <= PB_CHEAP:
        reasons.append(f'PB={pb:.2f}<=1.0破净')
        
        # 辅助条件
        if pb_fair is not None and pb <= pb_fair * PB_FAIR_MARGIN_ACCUM:
            reasons.append(f'PB<=合理PB×0.90')
        elif pe_pct is not None and pe_pct <= PE_PCT_ACCUM:
            reasons.append(f'PE分位={pe_pct:.1f}%<=30%')
        elif dy_pct is not None and dy_pct >= DY_PCT_ACCUM:
            reasons.append(f'股息率分位={dy_pct:.1f}%>=70%')
        else:
            # PB<=1.0但不满足辅助条件
            reasons.append('PB破净但估值辅助条件不满足')
            return HOLD_WAIT, reasons, 0.0
        
        return ACCUMULATE, reasons, 1.0
    
    # 不满足累积区
    reasons.append(f'PB={pb:.2f if pb else "N/A"}>1.0，安全边际不足')
    return HOLD_WAIT, reasons, 0.0


def generate_reassess_conditions() -> List[str]:
    """生成重新评估条件。"""
    return [
        'ROE连续2年低于10%',
        'ROE显著下降（较上期下降>2个百分点）',
        'NPL持续恶化（连续3年上升）',
        '拨备覆盖率持续下降（连续3年下降）',
        'CET1显著下降（较上期下降>1个百分点）',
        '资本充足率显著下降',
        '连续降低现金分红',
        '分红长期超过盈利能力（分红率>100%连续2年）',
        '重大治理风险',
        '商业模式发生重大变化',
    ]


def bank_value_assess(symbol: str, name: str, industry_type: str,
                      fin: dict, div, profits: List[float],
                      asof_date: str = '', bond_yield: float = DEFAULT_RF,
                      ke: float = DEFAULT_KE) -> BankValueResult:
    """银行价值投资模型主函数。
    
    Args:
        symbol: 股票代码
        name: 股票名称
        industry_type: 行业类型
        fin: 财务数据字典
        div: 分红数据
        profits: 历史净利润列表
        asof_date: 评估基准日
        bond_yield: 无风险利率(%)
        ke: 股权要求回报率(%)
    
    Returns:
        BankValueResult
    """
    result = BankValueResult()
    result.symbol = symbol
    result.name = name
    result.industry = industry_type
    result.industry_type = industry_type
    result.asof_date = asof_date
    
    # 1. 行业确认
    if not check_industry(industry_type):
        result.status = UNSUPPORTED_INDUSTRY
        result.fail_reasons = [f'行业={industry_type or "未知"}，银行价值投资模型仅支持银行业']
        return result
    
    # 2. 数据完整性检查
    missing = check_data_completeness(fin, div, asof_date)
    if missing:
        result.status = DATA_INSUFFICIENT
        result.fail_reasons = [f'缺失指标: {", ".join(missing)}']
        return result
    
    # 3. 质量评估
    result.quality = assess_quality(fin, div, profits)
    
    # 4. 估值评估
    result.valuation = assess_valuation(fin)
    
    # 5. 计算合理PB
    if result.quality.roe is not None:
        # 计算增长率g
        g = None
        if profits and len(profits) >= 5:
            cagr = (profits[-1] / profits[0]) ** (1/len(profits)) - 1 if profits[0] > 0 else None
            if cagr is not None:
                g = min(cagr * 100, 5.0)  # 上限5%
        
        if g is None:
            g = 2.0  # 默认
        
        if ke > g:
            result.valuation.pb_fair = calculate_reasonable_pb(result.quality.roe, g, ke)
            result.valuation.pb_fair_method = f'ROE={result.quality.roe:.1f}%, g={g:.1f}%, Ke={ke:.1f}%'
            
            if result.valuation.pb is not None and result.valuation.pb_fair is not None:
                result.valuation.pb_margin = round(result.valuation.pb / result.valuation.pb_fair, 2)
    
    # 6. 确定信号
    result.status, result.signal_reasons, result.monthly_multiplier = determine_signal(
        result.quality, result.valuation)
    
    # 7. 重新评估条件
    result.reassess_conditions = generate_reassess_conditions()
    
    return result


def format_bank_value_report(res: BankValueResult) -> str:
    """格式化银行价值投资模型报告。"""
    lines = []
    lines.append('=' * 60)
    lines.append('银行价值投资模型')
    lines.append('=' * 60)
    lines.append(f'标的: {res.symbol}({res.name})  行业: {res.industry}')
    lines.append(f'分析日: {res.asof_date}')
    lines.append('-' * 60)
    
    # 数据状态
    lines.append(f'数据状态: {res.status}')
    if res.fail_reasons:
        for r in res.fail_reasons:
            lines.append(f'  ✗ {r}')
    lines.append('')
    
    # 一、盈利质量
    q = res.quality
    lines.append('【一、盈利质量】')
    lines.append(f'  ROE: {q.roe:.2f}% ({q.roe_status})' if q.roe else '  ROE: 缺失')
    lines.append(f'  5年净利润最大回撤: {q.max_drawdown:.2f}% ({q.max_drawdown_status})' if q.max_drawdown is not None else '  最大回撤: 缺失')
    lines.append(f'  连续盈利下降年数: {q.consecutive_decline_years} ({q.decline_status})' if q.consecutive_decline_years is not None else '  连续下降: 缺失')
    lines.append('')
    
    # 二、资产质量
    lines.append('【二、资产质量】')
    lines.append(f'  NPL: {q.npl_ratio:.2f}%' if q.npl_ratio else '  NPL: 缺失')
    lines.append(f'  拨备覆盖率: {q.provision_coverage:.2f}%' if q.provision_coverage else '  拨备覆盖率: 缺失')
    lines.append(f'  关注类贷款率: {q.concern_loan_ratio:.2f}%' if q.concern_loan_ratio else '  关注类贷款率: 缺失')
    lines.append(f'  信用成本: {q.credit_cost:.2f}%' if q.credit_cost else '  信用成本: 缺失')
    lines.append(f'  资产质量结论: {q.asset_quality_status}')
    lines.append('')
    
    # 三、资本稳健
    lines.append('【三、资本稳健】')
    lines.append(f'  CET1: {q.cet1:.2f}%' if q.cet1 else '  CET1: 缺失')
    lines.append(f'  Tier1: {q.tier1:.2f}%' if q.tier1 else '  Tier1: 缺失')
    lines.append(f'  资本充足率: {q.car:.2f}%' if q.car else '  CAR: 缺失')
    lines.append(f'  资本结论: {q.capital_status}')
    lines.append('')
    
    # 四、分红能力
    lines.append('【四、分红能力】')
    lines.append(f'  连续分红年数: {q.consecutive_div_years}' if q.consecutive_div_years else '  连续分红: 缺失')
    lines.append(f'  5年平均分红率: {q.avg_payout:.2f}%' if q.avg_payout else '  平均分红率: 缺失')
    lines.append(f'  最新分红率: {q.latest_payout:.2f}%' if q.latest_payout else '  最新分红率: 缺失')
    lines.append(f'  分红结论: {q.dividend_status}')
    lines.append('')
    
    # 五、估值
    v = res.valuation
    lines.append('【五、估值】')
    lines.append(f'  当前股价: {v.price}' if v.price else '  股价: 缺失')
    lines.append(f'  PB: {v.pb:.4f}' if v.pb else '  PB: 缺失')
    lines.append(f'  PE-TTM: {v.pe_ttm:.2f}' if v.pe_ttm else '  PE-TTM: 缺失')
    lines.append(f'  股息率: {v.dividend_yield:.2f}%' if v.dividend_yield else '  股息率: 缺失')
    lines.append(f'  PB合理估值: {v.pb_fair:.2f} ({v.pb_fair_method})' if v.pb_fair else '  合理PB: 缺失')
    lines.append(f'  PB/合理PB: {v.pb_margin:.2f}' if v.pb_margin else '  PB边际: 缺失')
    lines.append(f'  PE 10年分位: {v.pe_pct_10y:.1f}%' if v.pe_pct_10y else '  PE分位: 缺失')
    lines.append(f'  股息率10年分位: {v.dy_pct_10y:.1f}%' if v.dy_pct_10y else '  股息率分位: 缺失')
    lines.append('')
    
    # 六、安全边际
    lines.append('【六、安全边际】')
    lines.append(f'  质量门槛: {"通过" if q.quality_pass else "未通过"}')
    lines.append(f'  估值门槛: {v.pb_zone}')
    lines.append(f'  安全边际: {res.status}')
    lines.append('')
    
    # 七、最终信号
    lines.append('【七、最终信号】')
    signal_text = {
        STRONG_BUY: '强烈买入',
        ACCUMULATE: '累积区',
        HOLD_WAIT: '持有/等待',
        DATA_INSUFFICIENT: '数据不足',
    }.get(res.status, res.status)
    lines.append(f'  信号: {signal_text}')
    if res.signal_reasons:
        for r in res.signal_reasons:
            lines.append(f'  · {r}')
    lines.append('')
    
    # 八、操作建议
    lines.append('【八、操作建议】')
    if res.monthly_multiplier is not None:
        if res.monthly_multiplier >= 2.0:
            lines.append('  建议: 分批加速建仓')
        elif res.monthly_multiplier >= 1.0:
            lines.append('  建议: 月度定额分批建仓')
        else:
            lines.append('  建议: 持有/观察，等待安全边际')
    lines.append(f'  月度投入倍数: {res.monthly_multiplier}')
    lines.append('')
    
    # 九、重新评估条件
    lines.append('【九、重新评估条件】')
    for c in res.reassess_conditions:
        lines.append(f'  · {c}')
    lines.append('')
    
    lines.append('=' * 60)
    lines.append('风险提示: 便宜≠一定上涨；高股息≠一定安全；历史低估≠未来不跌。')
    lines.append('本报告仅供研究参考，不构成投资建议。')
    lines.append('=' * 60)
    
    return '\n'.join(lines)
