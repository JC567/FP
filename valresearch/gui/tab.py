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

HELP_MODE = (
    '三种模式的区别（对应信号阈值不同，越稳健要求越苛刻）：\n'
    '\n'
    '① 稳健型（保守 conservative）\n'
    '   · PE 分位 < 20% 才算低估（更便宜才买）\n'
    '   · 股息率分位 > 80% 才算高股息（更高才买）\n'
    '   · Gordon 折现率 Ke +1%（合理估值更保守）\n'
    '   · 适合：追求安全边际、对回撤容忍低、想长期持有的投资者\n'
    '\n'
    '② 均衡型（默认 balanced）\n'
    '   · PE 分位 < 30% · 股息率分位 > 70% · Ke 不做偏移\n'
    '   · 攻守平衡，适合大多数投资者\n'
    '\n'
    '③ 进取型（激进 aggressive）\n'
    '   · PE 分位 < 40% 就算低估（更愿意在估值略高时买入）\n'
    '   · 股息率分位 > 60% 就算高股息\n'
    '   · Gordon 折现率 Ke −1%（合理估值更高、更易触发买入）\n'
    '   · 适合：风险承受能力较高、希望捕捉更多机会的投资者\n'
    '\n'
    '选择方式：页面上方「模式」下拉框切换，或点「模式说明」查看本说明。'
)

HELP_ANALYZE = (
    '「单股分析」做什么（严格使用分析日之前已公开的公告，杜绝未来函数）：\n'
    '\n'
    '1. 估值快照：当前价、PE_TTM、EPS_TTM、DPS_TTM、股息率、分红率。\n'
    '2. 三指标历史分位（10年主窗口 + 5年辅窗口，严格“低于当前值的样本占比”口径）：\n'
    '   · PE 分位 —— 越低越便宜\n'
    '   · 股息率分位 —— 越高分红越丰厚\n'
    '   · 分红率分位 —— 过高可能不可持续\n'
    '   · 异常处理：PE≤0 剔除；分红率<0 或 >150% 剔除并打异常标记；winsorize 前后各1%但保留原始值\n'
    '3. 股息率 − 10年国债利差：>2% 视为显著（达标计入信号）。\n'
    '4. Gordon 合理估值：FairPE = 分红率/(折现率−增长率)。若 增长率≥折现率 或 差值≤2% → 模型失效，不强行给合理价。\n'
    '5. 基本面质量评分(0-100)：盈利稳定性+现金流+分红持续性+负债+行业 加权。\n'
    '6. 价值陷阱评分(0-100)：>60 禁止“强烈买入”，并按惩罚系数折减综合分。\n'
    '7. 信号仲裁：规则信号(三条件) + 分数信号 + 陷阱信号 → 最终信号\n'
    '   （强烈买入/买入/逢低吸纳/持有/观望/减仓/卖出）。\n'
    '8. 价格区间：GGM情景合理价、股息率反推价(@4/5/6/7%)、历史分位价(P20/30/50/70)、当前所处区间。\n'
    '9. 仓位建议：按最终信号查表，价值陷阱高分自动压降。\n'
    '10. 输出九段式报告 + 可追溯的数据来源与窗口。'
)

HELP_BACKTEST = (
    '「单股回测」做什么（单股历史重估，严格无未来函数）：\n'
    '\n'
    '1. 范围：默认 2019-01-01 ~ 2025-12-31，每周再平衡。\n'
    '2. 对每个再平衡日：只用截至该日已公开的数据重算完整信号（PE/股息率/分红率分位、'
    'Gordon、质量、价值陷阱、最终信号）。\n'
    '3. 交易规则：信号为 强烈买入/买入/逢低吸纳 时持有，否则空仓。\n'
    '4. 收益用后复权价计算（近似含分红）。\n'
    '5. 三组对比：\n'
    '   · 策略（按信号进出场）\n'
    '   · 买入并持有（全程满仓）\n'
    '   · 基准指数（沪深300 等）\n'
    '6. 指标：年化复合收益率(CAGR)、年化波动率、夏普比率、最大回撤、卡尔玛比率、总收益率、'
    '信号分布、平均质量分/综合分。\n'
    '\n'
    '注意：历史低估≠未来一定上涨；回测存在幸存者偏差与过拟合风险，结果仅供参考。'
)

HELP_REPORT = (
    '九段式报告各段含义：\n'
    '\n'
    '【1 摘要】结论速览：最终信号、综合分、规则信号。\n'
    '【2 估值快照】当前价、PE_TTM、EPS_TTM、DPS_TTM、股息率、分红率、10年国债、股息-国债利差。\n'
    '【3 历史分位分析】PE/股息率/分红率的 10年与5年分位，Min/P10/中位数/P90/Max，有效与剔除样本数，异常标记。\n'
    '【4 基本面质量】综合质量分 + 分项（盈利/现金流/分红/负债/行业）+ 提示标记。\n'
    '【5 价值陷阱】分数、等级、触发项、惩罚系数、是否禁止强烈买入。\n'
    '【6 信号分析】三条件(PE低估/高股息/分红率合理)、规则信号、分数信号、最终信号、'
    'Gordon 参数与情景矩阵、当前模式阈值。\n'
    '【7 合理价格与买入区间】GGM情景合理价、股息率反推价、历史分位价、深度/标准买入区、当前所处区间。\n'
    '【8 仓位建议】初始/建议/上限仓位及依据。\n'
    '【9 局限与可追溯】数据质量警告、局限标注、每项指标的数据来源与统计窗口。\n'
    '\n'
    '「便宜≠一定上涨」「高股息≠一定安全」，报告仅供研究参考，不构成投资建议。'
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

    # ---------- 帮助弹框 ----------
    def _show_help_menu(self):
        win = tk.Toplevel(self.root)
        win.title('帮助说明')
        win.geometry('720x600')
        win.configure(bg=BG)
        nb = ttk.Notebook(win)
        nb.pack(fill='both', expand=True, padx=10, pady=10)
        for title, content in (('模式区别', HELP_MODE),
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
        threading.Thread(target=self._work_bt, args=(code, mode), daemon=True).start()

    def _work_bt(self, code, mode):
        try:
            cfg = get_config(mode)
            res = run_backtest(code, '2019-01-01', '2025-12-31', mode, cfg,
                               progress_cb=self._prog_cb())
            self.q.put(('report', self._bt_summary(res)))
        except Exception as e:
            self.q.put(('err', f'回测失败: {type(e).__name__} {e}'))

    @staticmethod
    def _bt_summary(res) -> str:
        if not res.get('ok'):
            return f"回测无结果: {res.get('reason')}"
        L = []
        A = L.append
        A('=' * 64)
        A(f'单股历史重估回测 · {res["symbol"]} · {res["start"]}~{res["end"]} · 模式={cn(res["mode"])} · 再平衡={res["rebalance_freq"]}')
        A('=' * 64)

        def row(m):
            if not m:
                return '  --'
            parts = []
            for k in ('cagr', 'annual_volatility', 'sharpe', 'max_drawdown', 'calmar', 'total_return'):
                if m.get(k) is not None:
                    parts.append(f'{k}={m[k]}')
            return '  ' + ' | '.join(parts) if parts else '  --'

        def titled(label, m):
            A(label + ':')
            A(row(m))

        A('策略(按信号进出场):')
        A(row(res['strategy']))
        A('买入并持有(全程满仓):')
        A(row(res['buy_and_hold']))
        if res.get('benchmark_metrics'):
            A(f'基准指数({res.get("benchmark_symbol")}):')
            A(row(res['benchmark_metrics']))
        A('信号分布: ' + ', '.join(f'{cn(k)}={v}' for k, v in res.get('signal_counts', {}).items()))
        A('平均质量分 %s | 平均综合分 %s' % (res.get('avg_quality'), res.get('avg_score')))
        A('=' * 64)
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

    def _set_busy(self, busy, text):
        self.busy = busy
        state = 'disabled' if busy else 'normal'
        for b in (self.btn_analyze, self.btn_json, self.btn_bt):
            b.config(state=state)
        if not busy:
            self.status.config(text=text)


def build_vr_tab(nb: ttk.Notebook) -> VRTab:
    return VRTab(nb)