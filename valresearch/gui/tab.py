# -*- coding: utf-8 -*-
"""红利价值分位研究 · 桌面页签（Phase 12）。

自包含 Tk 页签：输入代码/名称/日期/模式 → 单股分析(九段式报告) / 生成JSON / 单股历史重估回测。
- 模式用中文名（稳健型/均衡型/进取型），并提供「模式说明」弹框解释三者差异。
- 「帮助说明」弹框解释 单股分析/单股回测 的详细规则与 九段式报告各段含义。
- 运行时有进度条 + 状态文字。
- 输出内容英文 token 一律翻译为中文。
"""
from __future__ import annotations

import queue
import threading

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

from valresearch.config import get_config
from valresearch.main import analyze
from valresearch.report import format_report, save_json
from valresearch.backtest import run_backtest
from valresearch.i18n import cn, cn_metrics

ACCENT = '#3b82f6'
BG = '#f4f6fb'
CARD = '#ffffff'
TEXT = '#1f2937'
MUTED = '#6b7280'

# 中文模式名 -> 内部 key
MODE_CN2KEY = {'稳健型 (保守)': 'conservative',
               '均衡型 (默认)': 'balanced',
               '进取型 (激进)': 'aggressive'}

HELP_GLOSSARY = (
    '【新手必读 · 术语速查】看不懂报告？先看这一页\n'
    '\n'
    '■ 什么是"分红"？\n'
    '  公司赚钱后，把一部分利润按股份发给股东，就叫分红。\n'
    '  红利投资的核心逻辑：买"肯分红、分得起、分得久"的公司，靠分红赚钱。\n'
    '\n'
    '■ 四个基础数字（报告中反复出现）\n'
    '  · 股价：现在买一股要花多少钱。\n'
    '  · 每股收益 EPS：公司平均在每股上赚多少利润（元/股）。\n'
    '     例：EPS=2元，即每股一年赚2元。EPS≤0（亏损）时系统不硬算PE。\n'
    '  · 每股分红 DPS：平均每股分到多少现金（元/股）。\n'
    '     例：DPS=1元，即每股一年分1元现金；不分红就是0。\n'
    '  · 总股本：公司总共发行了多少股（用于把"每股"换算成"总额"）。\n'
    '\n'
    '■ 三个核心"率"（判断贵不贵、值不值的关键）\n'
    '  1) 市盈率 PE = 股价 ÷ EPS\n'
    '     通俗理解："按现在的赚钱速度，大约多少年回本"。\n'
    '     例：股价20元、EPS=2元 → PE=10倍，即大约10年回本。\n'
    '     PE越低越便宜、PE越高越贵，是最常用的估值尺子。\n'
    '\n'
    '  2) 股息率 DY = DPS ÷ 股价 × 100%\n'
    '     通俗理解："花100元买它，每年能拿回多少现金分红"。\n'
    '     例：股价20元、DPS=1元 → 股息率5%，比存银行利息高。\n'
    '     股息率越高、吃息越划算，是红利投资者的第一指标。\n'
    '\n'
    '  3) 分红率 payout = 分红总额 ÷ 净利润 × 100%\n'
    '     通俗理解："赚的100块钱里，拿出多少发给股东"。\n'
    '     例：分红率50% = 赚100元发50元、留50元发展。\n'
    '     分红率过高（>100%）＝分的是老本，不可持续，要警惕。\n'
    '\n'
    '■ 历史分位（回答"现在到底是贵还是便宜"）\n'
    '  分位 = 过去十年里，比"当前值"更极端的日子占比 × 100。\n'
    '  例：当前PE分位=20%，意思是"过去10年只有20%的日子比现在便宜"。\n'
    '  记忆口诀：\n'
    '    PE分位   越低越便宜（10%≈历史最便宜的区间）\n'
    '    股息率分位 越高越划算（90%≈历史分红最丰厚的区间）\n'
    '    分红率分位 过高反而有隐患\n'
    '\n'
    '■ Gordon增长模型（算"理论上值多少钱"）\n'
    '  思路：股票的价值 ≈ 未来每年分红折算回今天的总和。\n'
    '  核心公式：合理PE = 分红率 ÷ (折现率Ke − 增长率g)\n'
    '    Ke = 10年国债利率 + 风险溢价(默认5%)：投资人要求的最低回报。\n'
    '    g = 用 ROE×(1−分红率) 等推算的可持续增长率。\n'
    '  Ke−g 越大 → 合理PE越低 → 同样的分红，理论价越便宜。\n'
    '  若 g≥Ke（增长高到不合理）→ 公式失效，系统明说"模型失效"，不硬编数字。\n'
    '\n'
    '■ 价值陷阱（"便宜"可能是坑）\n'
    '  估值很低、但背后藏着隐患：盈利连年下滑、现金流恶化、\n'
    '  分红率>100%靠发老本、负债过高、行业衰退……\n'
    '  陷阱分越高越危险；>60分禁止"强烈买入"，并按系数打折扣。\n'
    '\n'
    '■ 其他常用词\n'
    '  · TTM：滚动12个月（最近12个月的合计，比自然年更实时）。\n'
    '  · 利差 = 股息率 − 10年国债利率；股息比国债高2%以上算"达标"。\n'
    '  · 滞回：买入用严格标准、卖出要等明显变差才走，防止来回折腾。\n'
    '  · PIT无未来函数：算某天数值时，只用当天之前已公布的公告，绝不掺未来信息。\n'
)

HELP_MODE = (
    '【三种模式怎么选】只调"买入门槛"，计算口径完全一致\n'
    '\n'
    '为什么分模式？因为每个人风险偏好不同：\n'
    '有人只买"极其便宜"的，有人愿意在"比较便宜"时就下手。\n'
    '模式只改变三个"买入门槛"的高低，不影响任何计算方法。\n'
    '\n'
    '三个门槛：\n'
    '  ① PE分位门槛：PE分位低于多少，才算"估值低估"\n'
    '  ② 股息率分位门槛：股息率分位高于多少，才算"高股息"\n'
    '  ③ Gordon折现率偏移：对"合理价"额外要求多少安全边际\n'
    '\n'
    '────────────────────────────\n'
    '■ 稳健型（保守 conservative）——最挑剔，宁缺毋滥\n'
    '   · PE分位 < 20% 才算低估（要便宜到历史最低的20%区间才动心）\n'
    '   · 股息率分位 > 80% 才算高股息（要丰厚到历史最高的20%区间）\n'
    '   · Ke +1%：要求回报更高 → 合理价更低 → 更不容易喊"买入"\n'
    '   · 适合：追求绝对安全边际、怕回撤、准备长拿的投资者。\n'
    '   · 代价：可能长时间等不到买点，容易错过。\n'
    '\n'
    '■ 均衡型（默认 balanced）——攻守平衡\n'
    '   · PE分位 < 30% · 股息率分位 > 70% · Ke不偏移\n'
    '   · 适合：大多数普通投资者，适合定投、逐步建仓。\n'
    '\n'
    '■ 进取型（激进 aggressive）——更积极，机会更多\n'
    '   · PE分位 < 40% 就算低估（股价"中等偏便宜"就开始考虑）\n'
    '   · 股息率分位 > 60% 就算高股息\n'
    '   · Ke −1%：要求回报略低 → 合理价更高 → 更容易触发"买入"\n'
    '   · 适合：风险承受力强、想抓住更多机会的投资者。\n'
    '   · 代价：买贵一点的可能性更大，需要扛得住回撤。\n'
    '\n'
    '一句话总结：稳健=耐心等好价，进取=积极抓机会，均衡=两头兼顾。\n'
    '\n'
    '选择方式：页面上方「模式」下拉框切换，或点「模式说明」查看本说明。'
)

HELP_ANALYZE = (
    '【单股分析在做什么】——给一只股票做"全面体检"\n'
    '\n'
    '最重要的一条原则：\n'
    '系统只用"分析日之前已经公开"的信息（财报、分红公告、价格），\n'
    '绝不用未来数据，所以结论真实可复现，不骗你。\n'
    '\n'
    '分析共10步（对应报告的各个段落）：\n'
    '\n'
    '① 取数\n'
    '   下载股价、财报(利润)、分红记录、国债利率、行业信息。\n'
    '   首次运行较慢，之后全部走本地缓存，很快。\n'
    '\n'
    '② 数据质量检查\n'
    '   检查数据是否完整可靠。关键数据缺失会直接中止并写明"数据不足"，\n'
    '   绝不硬凑结论。每个数字都带"来源+统计范围+样本数"，可复核。\n'
    '\n'
    '③ 当前估值（滚动12个月 TTM 口径）\n'
    '   算出：PE(贵不贵)、EPS(每股赚多少)、DPS(每股分多少)、\n'
    '         股息率、分红率。→ 对应报告【2 当前估值概况】。\n'
    '\n'
    '④ 历史分位（回答"现在算贵还是便宜"）\n'
    '   把当前 PE/股息率/分红率 放进过去10年(另附5年)的历史中排名。\n'
    '   例：当前PE分位=15%，表示"过去10年只有15%的日子比现在更便宜"。\n'
    '   → 对应报告【3 历史水平对比】。\n'
    '   异常处理：PE≤0剔除；分红率<0或>150%剔除并打异常标记；\n'
    '           前后各1%的极端值winsorize但保留原始值。\n'
    '\n'
    '⑤ 股息率 vs 国债利差\n'
    '   股息率 − 10年国债利率 > 2%，说明"分红利息比买国债还高2个点"，\n'
    '   对靠吃息赚钱的人是加分项。\n'
    '\n'
    '⑥ Gordon合理估值\n'
    '   用Gordon模型算"理论上值多少钱"，给出熊市/基准/牛市三档合理价。\n'
    '   若模型失效（增长率过高导致公式无意义），会如实说明，不硬编数字。\n'
    '\n'
    '⑦ 基本面质量分（0~100）\n'
    '   给公司"底子"打分：盈利稳定性 + 现金流 + 分红持续性 +\n'
    '   负债水平 + 行业前景，五项加权。分越高，公司越扎实。\n'
    '\n'
    '⑧ 价值陷阱分（0~100）\n'
    '   专挑"看似便宜但暗藏风险"的信号：盈利连年下滑、现金流恶化、\n'
    '   分红率>100%靠发老本、负债过高、行业衰退。分数越高越要警惕。\n'
    '\n'
    '⑨ 综合信号（最终结论）\n'
    '   把前面的信息合成一个"信号"，像体检报告的总结论：\n'
    '   强烈买入 → 买入 → 逢低吸纳 → 持有 → 观望 → 减仓 → 卖出\n'
    '   信号由三条件规则 + 综合评分 + 陷阱仲裁共同决定，互相制约。\n'
    '   → 对应报告【6 投资信号分析】。\n'
    '\n'
    '⑩ 价格区间 + 仓位建议\n'
    '   给出"多少钱算便宜"（深度买入区/标准买入区），\n'
    '   以及按信号该配置多少仓位（单只上限10%）。\n'
    '   → 对应报告【7】【8】。\n'
    '\n'
    '最后输出一份九段式报告（详见"九段式报告说明"页签），\n'
    '并附数据来源与统计窗口，方便复核与复盘。'
)

HELP_BACKTEST = (
    '【单股回测在做什么】——用历史数据"模拟演练"这套信号好不好用\n'
    '\n'
    '一句话：把"单股分析"的规则，在过去几年里每周跑一遍，\n'
    '比较"按信号买卖"、"一直拿着不动"、和"沪深300指数"三种结果。\n'
    '\n'
    '① 时间范围：默认 2019-01-01 ~ 2025-12-31，每周再平衡一次。\n'
    '② 每次评估都只用"当时已公开"的数据重算完整信号\n'
    '   （PE/股息率/分红率分位、Gordon、质量、陷阱、最终信号），\n'
    '   没有未来函数，历史结论可信。\n'
    '③ 交易规则：信号为"强烈买入/买入/逢低吸纳"就持有，否则空仓；\n'
    '   信号当天产生、下一个交易日才执行（T+1），贴近真实交易。\n'
    '④ 收益用后复权价计算（近似包含分红再投资）。\n'
    '\n'
    '⑤ 三组对比：\n'
    '   · 策略：按这套信号进出场\n'
    '   · 买入并持有：从头到尾满仓拿着\n'
    '   · 基准指数：沪深300（大盘参照物）\n'
    '\n'
    '⑥ 看哪些指标：\n'
    '   · 年化复合收益率(CAGR)：平均每年赚多少（越高越好）\n'
    '   · 年化波动率：涨跌剧烈程度（越低越稳）\n'
    '   · 夏普比率：每担一分风险换多少收益（越高越好）\n'
    '   · 最大回撤：过程中最多从高点跌多少（越低越好）\n'
    '   · 卡尔玛比率 = 年化收益 ÷ 最大回撤（越高越好）\n'
    '   · 总收益率：全程总账\n'
    '   · 信号分布：这几年里每个信号各出现多少次\n'
    '\n'
    '⑦ 两个可选开关（页签工具条）：\n'
    '   · 只买不卖：勾选后模型只用于"判断买点"，卖出信号不再减仓，\n'
    '     仓位只增不减（适合把本系统当"建仓触发器"的用法）。\n'
    '   · 红利再投：默认勾选，用"后复权价"算收益，已内含"分红次日自动再投"的复利；\n'
    '     取消勾选则只用收盘价（不含分红再投），便于对比"纯价"表现。\n'
    '\n'
    '⑧ 回测结果图：\n'
    '   · 上图"走势图"：股价走势 + 各策略净值曲线，并标出策略的买入点(▲绿)/卖出点(▼红)。\n'
    '   · 下图"收益率走势图"：各策略累计净值，并叠加 10 年期国债无风险收益率(%) 做对比基准。\n'
    '\n'
    '务必冷静看待：\n'
    '· 过去赚钱≠未来赚钱，回测只是检验信号逻辑是否合理。\n'
    '· 存在幸存者偏差（只有活到现在的公司才有数据）与过拟合风险。\n'
    '· 结果仅供参考，不构成投资建议。'
)

HELP_REPORT = (
    '【九段式报告怎么读】——每一段的含义与怎么看\n'
    '\n'
    '【1 摘要】全篇结论速览\n'
    '   最终结论(强烈买入…卖出)、综合评分(0-100)、规则判断。\n'
    '   想快速知道结论，只看这一段。\n'
    '\n'
    '【2 当前估值概况】现在贵不贵\n'
    '   股价、EPS(每股赚多少)、DPS(每股分多少)、\n'
    '   市盈率(几倍≈多少年回本)、股息率(买100元每年拿回多少)、\n'
    '   分红率(赚100元发多少)、10年国债、股息超过国债多少。\n'
    '\n'
    '【3 历史水平对比】现在处于历史哪个位置\n'
    '   每个指标给出：当前值 + 分位 + 历史最低/中位/最高。\n'
    '   · PE分位越低越便宜；股息率分位越高越划算；\n'
    '   · 分红率分位过高可能是隐患。\n'
    '\n'
    '【4 公司基本面质量】公司底子好不好（0-100）\n'
    '   综合质量分 + 五项分项：盈利/现金流/分红持续/负债/行业。\n'
    '   分越高公司越扎实；低于60说明基本面偏弱，谨慎对待。\n'
    '\n'
    '【5 价值陷阱风险】有没有"看着便宜其实是坑"\n'
    '   风险分 + 等级(低/中低/中/高/极高) + 具体触发项。\n'
    '   惩罚：陷阱分越高，综合分打折越多（最高惩罚85%）。\n'
    '   等级"高/极高"会禁止"强烈买入"。\n'
    '\n'
    '【6 投资信号分析】最终怎么下结论\n'
    '   买入三条件(PE低估/高股息/分红率合理)各是否达标 →\n'
    '   规则判断 + 评分判断 + 最终结论(仲裁结果)。\n'
    '   附：Gordon理论合理PE、当前PE是合理价的几倍、\n'
    '   熊/基准/牛三档情景、当前模式的门槛数值。\n'
    '\n'
    '【7 合理价格与买入区间】多少钱算便宜\n'
    '   · Gordon合理价：低/基准/高三档；\n'
    '   · 股息率反推价：股息率4%/5%/6%/7%分别对应的价格；\n'
    '   · 历史分位价：按历史PE的20%/30%/50%/70%分位反推的价格；\n'
    '   · 深度买入区/标准买入区：两个"便宜"价格带；\n'
    '   · 当前所处：现在在买入区上方、区间内，还是下方。\n'
    '\n'
    '【8 仓位建议】该买多少\n'
    '   建议仓位 + 上限仓位(单只不超10%) + 依据。\n'
    '   信号越强仓位越高；陷阱分高会压缩仓位。\n'
    '\n'
    '【9 注意事项与数据来源】可信度与出处\n'
    '   数据质量警告、局限标注(如公告日按法规截止日近似、样本偏少)、\n'
    '   每个指标的数据来源与统计窗口，便于复核。\n'
    '\n'
    '最后提醒：\n'
    '便宜≠一定上涨；高股息≠一定安全；历史低估≠未来不会继续跌。\n'
    '本报告仅供研究参考，不构成投资建议。'
)


class VRTab:
    def __init__(self, nb: ttk.Notebook):
        self.nb = nb
        self.q = queue.Queue()
        self.busy = False
        self.tab = ttk.Frame(nb, style='Card.TFrame', padding=12)
        nb.add(self.tab, text='  红利价值分位研究  ')
        self.tab.columnconfigure(0, weight=1)
        self.tab.rowconfigure(4, weight=1)
        self._build()
        self.root = self.tab.winfo_toplevel()
        self.root.after(40, self._poll)

    def _build(self):
        # 输入工具条
        bar = ttk.Frame(self.tab, style='Card.TFrame')
        bar.grid(row=0, column=0, sticky='ew', pady=(0, 6))
        ttk.Label(bar, text='代码:', style='Muted.TLabel').pack(side='left')
        self.e_code = ttk.Entry(bar, width=8)
        self.e_code.pack(side='left', padx=(2, 8))
        self.e_code.insert(0, '600036')
        ttk.Label(bar, text='名称:', style='Muted.TLabel').pack(side='left')
        self.e_name = ttk.Entry(bar, width=10)
        self.e_name.pack(side='left', padx=(2, 8))
        ttk.Label(bar, text='分析日:', style='Muted.TLabel').pack(side='left')
        self.e_date = ttk.Entry(bar, width=12)
        self.e_date.pack(side='left', padx=(2, 8))
        self.e_date.insert(0, '')
        ttk.Label(bar, text='模式:', style='Muted.TLabel').pack(side='left')
        self.cb_mode = ttk.Combobox(bar, values=list(MODE_CN2KEY.keys()),
                                    state='readonly', width=12)
        self.cb_mode.current(list(MODE_CN2KEY.keys()).index('均衡型 (默认)'))
        self.cb_mode.pack(side='left', padx=(2, 8))
        ttk.Button(bar, text='模式说明', style='Small.TButton',
                   command=lambda: self._show_help('模式区别', HELP_MODE)).pack(side='left', padx=(2, 4))

        # 操作按钮
        self.btn_analyze = ttk.Button(bar, text='单股分析', style='Accent.TButton', command=self._analyze)
        self.btn_analyze.pack(side='left', padx=(8, 0))
        self.btn_json = ttk.Button(bar, text='生成JSON', style='Ghost.TButton', command=self._to_json)
        self.btn_json.pack(side='left', padx=(4, 0))
        self.btn_bt = ttk.Button(bar, text='单股回测', style='Accent.TButton', command=self._backtest)
        self.btn_bt.pack(side='left', padx=(4, 0))

        # 回测开关
        self.var_nosell = tk.BooleanVar(value=False)
        self.var_dr = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text='只买不卖', variable=self.var_nosell).pack(side='left', padx=(6, 0))
        ttk.Checkbutton(bar, text='红利再投', variable=self.var_dr).pack(side='left', padx=(4, 0))

        # 帮助按钮
        ttk.Button(bar, text='? 帮助说明', style='Small.TButton',
                   command=self._show_help_menu).pack(side='right')

        # 进度条 + 状态
        progbar = ttk.Frame(self.tab, style='Card.TFrame')
        progbar.grid(row=1, column=0, sticky='ew', pady=(2, 2))
        progbar.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(progbar, mode='determinate', maximum=100, value=0)
        self.progress.grid(row=0, column=0, sticky='ew')
        self.status = ttk.Label(progbar, text='就绪', style='Muted.TLabel')
        self.status.grid(row=1, column=0, sticky='w', pady=(2, 0))

        tip = tk.Label(self.tab, text='PE/股息率/分红率历史分位 + Gordon + 质量 + 价值陷阱 + 信号 + 价格区间 + 仓位。'
                                      '分析日留空=今天；数据本地缓存，首次取数较慢。',
                       bg=CARD, fg=MUTED, font=('Microsoft YaHei', 9), anchor='w', justify='left')
        tip.grid(row=2, column=0, sticky='ew', pady=(4, 4))

        # 输出区
        wrap = tk.Frame(self.tab, bg=BG)
        wrap.grid(row=4, column=0, sticky='nsew')
        wrap.rowconfigure(1, weight=1); wrap.columnconfigure(0, weight=1)
        tk.Label(wrap, text='输出', bg=BG, fg=TEXT, font=('Microsoft YaHei', 11, 'bold')).grid(
            row=0, column=0, sticky='w', pady=(0, 6))
        box = tk.Frame(wrap, bg='#111827', bd=0)
        box.grid(row=1, column=0, sticky='nsew')
        box.rowconfigure(0, weight=1); box.columnconfigure(0, weight=1)
        self.out = scrolledtext.ScrolledText(box, state='disabled', wrap='word',
                                             font=('Consolas', 9), bg='#111827',
                                             fg='#e5e7eb', insertbackground='white')
        self.out.grid(row=0, column=0, sticky='nsew')
        self.out.tag_config('err', foreground='#f87171')

        # 回测图区（走势图 + 收益率走势图）
        self.chart_host = tk.Frame(self.tab, bg=BG)
        self.chart_host.grid(row=5, column=0, sticky='nsew', pady=(6, 0))
        self.chart_host.rowconfigure(0, weight=1); self.chart_host.columnconfigure(0, weight=1)
        self._chart_canvas = None
        self.tab.rowconfigure(5, weight=3)

    # ---------- 帮助弹框 ----------
    def _show_help_menu(self):
        win = tk.Toplevel(self.root)
        win.title('帮助说明')
        win.geometry('720x600')
        win.configure(bg=BG)
        nb = ttk.Notebook(win)
        nb.pack(fill='both', expand=True, padx=10, pady=10)
        for title, content in (('新手术语速查', HELP_GLOSSARY),
                               ('模式区别', HELP_MODE),
                               ('单股分析规则', HELP_ANALYZE),
                               ('单股回测规则', HELP_BACKTEST),
                               ('九段式报告说明', HELP_REPORT)):
            tab = ttk.Frame(nb, style='Card.TFrame')
            nb.add(tab, text='  ' + title + '  ')
            txt = scrolledtext.ScrolledText(tab, wrap='word', font=('Microsoft YaHei', 10),
                                            bg=CARD, fg=TEXT, padx=12, pady=10)
            txt.pack(fill='both', expand=True)
            txt.insert('1.0', content)
            txt.configure(state='disabled')

    def _show_help(self, title, content):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry('640x520')
        win.configure(bg=BG)
        txt = scrolledtext.ScrolledText(win, wrap='word', font=('Microsoft YaHei', 10),
                                        bg=CARD, fg=TEXT, padx=12, pady=10)
        txt.pack(fill='both', expand=True, padx=10, pady=10)
        txt.insert('1.0', content)
        txt.configure(state='disabled')

    # ---------- 后台线程 ----------
    def _args(self):
        code = self.e_code.get().strip().replace(r'\D', '')
        if not code:
            raise ValueError('请输入6位股票代码')
        mode = MODE_CN2KEY.get(self.cb_mode.get(), 'balanced')
        return (code.zfill(6), self.e_name.get().strip(), self.e_date.get().strip() or None, mode)

    def _prog_cb(self):
        def cb(p, msg):
            self.q.put(('prog', int(p * 100), msg))
        return cb

    def _analyze(self):
        if self.busy:
            return
        try:
            code, name, date, mode = self._args()
        except ValueError as e:
            messagebox.showwarning('提示', str(e))
            return
        self._set_busy(True, '准备分析…')
        threading.Thread(target=self._work_analyze, args=(code, name, date, mode),
                         daemon=True).start()

    def _work_analyze(self, code, name, date, mode):
        try:
            cfg = get_config(mode)
            rep = analyze(code, date, mode, name, cfg, progress_cb=self._prog_cb())
            txt = format_report(rep)
            self.q.put(('report', txt))
        except Exception as e:
            self.q.put(('err', f'分析失败: {type(e).__name__} {e}'))

    def _to_json(self):
        if self.busy:
            return
        try:
            code, name, date, mode = self._args()
        except ValueError as e:
            messagebox.showwarning('提示', str(e))
            return
        self._set_busy(True, '生成JSON中…')
        threading.Thread(target=self._work_json, args=(code, name, date, mode),
                         daemon=True).start()

    def _work_json(self, code, name, date, mode):
        try:
            cfg = get_config(mode)
            rep = analyze(code, date, mode, name, cfg, progress_cb=self._prog_cb())
            import os
            outdir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                  'data', 'vr_reports')
            os.makedirs(outdir, exist_ok=True)
            path = save_json(rep, os.path.join(outdir, f'{code}_{(date or "latest")}.json'))
            self.q.put(('report', f'JSON 已写出:\n{path}\n'))
        except Exception as e:
            self.q.put(('err', f'生成JSON失败: {type(e).__name__} {e}'))

    def _backtest(self):
        if self.busy:
            return
        try:
            code, name, date, mode = self._args()
        except ValueError as e:
            messagebox.showwarning('提示', str(e))
            return
        self._set_busy(True, '准备回测…')
        allow_sell = not self.var_nosell.get()
        dividend_reinvest = self.var_dr.get()
        threading.Thread(target=self._work_bt, args=(code, mode, allow_sell, dividend_reinvest),
                         daemon=True).start()

    def _work_bt(self, code, mode, allow_sell, dividend_reinvest):
        try:
            cfg = get_config(mode)
            res = run_backtest(code, '2019-01-01', '2025-12-31', mode, cfg,
                               progress_cb=self._prog_cb(),
                               allow_sell=allow_sell, dividend_reinvest=dividend_reinvest)
            self.q.put(('report', self._bt_summary(res)))
            if res.get('ok'):
                try:
                    from valresearch.backtest import make_backtest_figure
                    fig = make_backtest_figure(res)
                    if fig is not None:
                        self.q.put(('chart', fig))
                except Exception as e:
                    self.q.put(('err', f'绘图失败(不影响文本): {type(e).__name__} {e}'))
        except Exception as e:
            self.q.put(('err', f'回测失败: {type(e).__name__} {e}'))

    @staticmethod
    def _bt_summary(res) -> str:
        if not res.get('ok'):
            return f"回测无结果: {res.get('reason')}"
        L = []
        A = L.append
        A('=' * 64)
        A(f"单股历史重估回测 · {res['symbol']} · {res['start']}~{res['end']} · 模式={cn(res['mode'])} · 再平衡={res['rebalance_freq']}")
        A('=' * 64)
        A(f"持仓规则：{'只买不卖（模型仅判断买点）' if not res.get('allow_sell') else '按信号买卖（含卖出）'}")
        A(f"分红处理：{'红利再投（后复权，分红次日自动再投）' if res.get('dividend_reinvest') else '不复投（仅收盘价）'}")

        def row_cn(m):
            if not m:
                return '  --'
            parts = [f'{k}={v}' for k, v in cn_metrics(m).items() if v is not None]
            return '  ' + ' | '.join(parts) if parts else '  --'

        A('【策略（按信号进出场）】')
        A(row_cn(res['strategy']))
        A('【买入并持有（全程满仓）】')
        A(row_cn(res['buy_and_hold']))
        if res.get('benchmark_metrics'):
            A(f"【基准指数（{res.get('benchmark_symbol')}）】")
            A(row_cn(res['benchmark_metrics']))
        A('信号分布：' + '，'.join(f'{cn(k)}={v}' for k, v in res.get('signal_counts', {}).items()))
        A('平均质量分 %s ｜ 平均综合分 %s' % (res.get('avg_quality'), res.get('avg_score')))
        for note in res.get('notes', []):
            A('· ' + note)
        A('=' * 64)
        A('说明：净值起点=1；策略按单股上限归一化仓位、已计交易成本。下方为走势与收益率曲线（含买卖点）。')
        return '\n'.join(L)

    # ---------- 队列轮询 ----------
    def _poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                kind = item[0]
                if kind == 'prog':
                    self.progress['value'] = item[1]
                    self.status.config(text=item[2])
                elif kind == 'report':
                    self.progress['value'] = 100
                    self._append(item[1])
                    self._set_busy(False, '完成')
                elif kind == 'chart':
                    self._show_chart(item[1])
                elif kind == 'err':
                    self._append(item[1] + '\n', 'err')
                    self._set_busy(False, '失败')
        except queue.Empty:
            pass
        self.root.after(40, self._poll)

    def _append(self, text, tag=None):
        self.out.config(state='normal')
        self.out.delete('1.0', 'end')
        self.out.insert('end', text, tag)
        self.out.see('end')
        self.out.config(state='disabled')

    def _show_chart(self, fig):
        """在主线程把回测 Figure 嵌入 Tk（FigureCanvasTkAgg）。"""
        try:
            import matplotlib
            matplotlib.use('Agg')
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            for w in list(self.chart_host.winfo_children()):
                w.destroy()
            canvas = FigureCanvasTkAgg(fig, master=self.chart_host)
            canvas.draw()
            widget = canvas.get_tk_widget()
            widget.grid(row=0, column=0, sticky='nsew')
            self._chart_canvas = canvas
        except Exception as e:
            self._append(f'图表显示失败: {e}\n', 'err')

    def _set_busy(self, busy, text):
        self.busy = busy
        state = 'disabled' if busy else 'normal'
        for b in (self.btn_analyze, self.btn_json, self.btn_bt):
            b.config(state=state)
        if not busy:
            self.status.config(text=text)


def build_vr_tab(nb: ttk.Notebook) -> VRTab:
    return VRTab(nb)