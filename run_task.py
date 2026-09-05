# -*- coding: utf-8 -*-
"""1号任务 · A股分红率排名（桌面程序）

三个页签：
  1. 运行        —— 一键执行 dividend_rank.py + apply_exclusion.py，实时日志。
  2. 数据查看    —— 直接在应用内查看《分红率排名.csv》/《分红率排名（筛选后）.csv》
                    （含高亮），无需另开本地文件；实际文件仍会生成到 data/。
  3. 手动配置    —— 直接在应用内编辑 L~O 列（是否保留/买入提醒pe/买入提醒价格/买入pb），
                    保存到 data/排除/手动配置.csv，下次运行按新值计算、判断、展示。
"""
import os
import sys
import io
import re
import json
import queue
import subprocess
import threading
import time
import traceback

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

import pandas as pd
import numpy as np
import akshare as ak
import stock_db
import div_hist
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib

matplotlib.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, 'data')
EXCL_DIR = os.path.join(DATA, '排除')
OUT_FULL = os.path.join(DATA, '分红率排名.csv')
OUT_FILT = os.path.join(DATA, '分红率排名（筛选后）.csv')
MANUAL = os.path.join(EXCL_DIR, '手动配置.csv')
LOG_FILE = os.path.join(DATA, 'error.log')
ANALYSIS_CACHE = os.path.join(DATA, 'analysis_cache.json')

# 主题色
ACCENT = '#3b82f6'
ACCENT_DARK = '#2563eb'
BG = '#f4f6fb'
CARD = '#ffffff'
TEXT = '#1f2937'
MUTED = '#6b7280'
GREEN = '#16a34a'
RED = '#dc2626'

STEPS = [
    ('dividend_rank.py',    '第一步 · 生成沪深主板全量排名'),
    ('apply_exclusion.py',  '第二步 · 合并排除J~M列并筛选'),
]

# 手动配置树：可编辑的列（字段名）
CFG_EDITABLE = {'是否保留': '是否保留', '买入提醒pe': '买入提醒pe',
                '买入提醒价格': '买入提醒价格', '买入pb': '买入pb'}
CONFIG_COLS = ['代码', '名称', '是否保留', '买入提醒pe', '买入提醒价格', '买入pb']


def norm_code(x):
    return str(x).replace(r'\D', '').zfill(6) if x is not None else ''


class TaskApp:
    def __init__(self, root):
        self.root = root
        root.title('1号任务 · A股分红率排名')
        root.geometry('1120x720')
        root.minsize(900, 620)
        root.configure(bg=BG)
        self.running = False
        self.q = queue.Queue()          # worker -> UI 事件队列
        self.cfg_rows = []              # 手动配置行（列表[dict]），与树行一一对应
        self._style()
        self._build()
        self._load_config()
        self._load_data_view('筛选后')
        self._poll_loop()               # 启动主线程轮询

    # ---------- 主题 ----------
    def _style(self):
        s = ttk.Style(self.root)
        s.theme_use('clam')
        s.configure('.', font=('Microsoft YaHei', 10), background=BG, foreground=TEXT)
        s.configure('Card.TFrame', background=CARD)
        s.configure('Card.TLabel', background=CARD, foreground=TEXT)
        s.configure('Muted.TLabel', background=CARD, foreground=MUTED)
        s.configure('H2.TLabel', background=CARD, foreground=TEXT, font=('Microsoft YaHei', 11, 'bold'))
        s.configure('Accent.TButton',
                    background=ACCENT, foreground='white', borderwidth=0,
                    font=('Microsoft YaHei', 11, 'bold'), padding=(20, 8))
        s.map('Accent.TButton',
              background=[('active', ACCENT_DARK), ('disabled', '#a5b4fc')],
              foreground=[('disabled', 'white')])
        s.configure('Ghost.TButton', background=CARD, foreground=ACCENT,
                    borderwidth=1, padding=(14, 6))
        s.map('Ghost.TButton', background=[('active', '#eff6ff')])
        s.configure('Small.TButton', background=CARD, foreground=ACCENT,
                    borderwidth=1, padding=(10, 4), font=('Microsoft YaHei', 9))
        s.map('Small.TButton', background=[('active', '#eff6ff')])
        s.configure('Horizontal.TProgressbar', troughcolor='#e5e7eb', background=ACCENT, borderwidth=0)
        s.configure('Treeview', rowheight=24, font=('Microsoft YaHei', 9))
        s.configure('Treeview.Heading', font=('Microsoft YaHei', 9, 'bold'))
        s.configure('TCombobox', padding=2)

    # ---------- 布局 ----------
    def _build(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        self._header()
        self.nb = ttk.Notebook(self.root)
        self.nb.grid(row=1, column=0, sticky='nsew', padx=14, pady=(8, 14))
        self.nb.columnconfigure(0, weight=1); self.nb.rowconfigure(0, weight=1)

        self._build_run_tab(self.nb)
        self._build_data_tab(self.nb)
        self._build_config_tab(self.nb)
        self._build_vr_tab(self.nb)
        self._build_report_import_tab(self.nb)

    def _header(self):
        h = tk.Frame(self.root, bg=ACCENT, height=58)
        h.grid(row=0, column=0, sticky='ew')
        h.grid_propagate(False)
        tk.Label(h, text='1号任务', bg=ACCENT, fg='white',
                 font=('Microsoft YaHei', 15, 'bold')).pack(side='left', padx=16)
        tk.Label(h, text='A股分红率排名 · 排除创业板/科创板 · 应用内查看与手动配置 L~O 列',
                 bg=ACCENT, fg='#dbeafe', font=('Microsoft YaHei', 10)).pack(side='left', pady=(4, 0))

    # ---------- 页签4：红利价值分位研究 ----------
    def _build_vr_tab(self, nb):
        try:
            from valresearch.gui.tab import build_vr_tab
            build_vr_tab(nb)
        except Exception as e:
            tab = ttk.Frame(nb, style='Card.TFrame', padding=14)
            nb.add(tab, text='  红利价值分位研究  ')
            ttk.Label(tab, text=f'页签初始化失败：{e}\n请确认 valresearch 包可导入。',
                      style='Muted.TLabel').pack(anchor='w')

    # ---------- 页签5：财报导入分析 ----------
    def _build_report_import_tab(self, nb):
        try:
            from valresearch.gui.report_import_tab import build_report_import_tab
            tab = build_report_import_tab(nb)
            nb.add(tab.tab, text='  财报导入分析  ')
        except Exception as e:
            tab = ttk.Frame(nb, style='Card.TFrame', padding=14)
            nb.add(tab, text='  财报导入分析  ')
            ttk.Label(tab, text=f'页签初始化失败：{e}\n请确认 valresearch.parsing 包可导入。',
                      style='Muted.TLabel').pack(anchor='w')

    # ---------- 页签1：运行 ----------
    def _build_run_tab(self, nb):
        tab = ttk.Frame(nb, style='Card.TFrame', padding=14)
        nb.add(tab, text='  运行  ')
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(3, weight=1)

        # 控制
        c = ttk.Frame(tab, style='Card.TFrame')
        c.grid(row=0, column=0, sticky='ew')
        c.columnconfigure(1, weight=1)
        self.btn_run = ttk.Button(c, text='▶  运行1号任务', style='Accent.TButton', command=self.run_task)
        self.btn_run.grid(row=0, column=0, sticky='w')
        self.btn_open = ttk.Button(c, text='打开结果文件夹', style='Ghost.TButton',
                                   command=self.open_folder, state='disabled')
        self.btn_open.grid(row=0, column=1, sticky='w', padx=(12, 0))
        self.status = ttk.Label(c, text='就绪，等待运行', style='Muted.TLabel')
        self.status.grid(row=1, column=0, columnspan=2, sticky='w', pady=(10, 0))
        self.progress = ttk.Progressbar(c, mode='determinate', length=280, maximum=100, value=0)
        self.progress.grid(row=1, column=1, sticky='e')

        # 步骤 + 结果
        rc = ttk.Frame(tab, style='Card.TFrame')
        rc.grid(row=1, column=0, sticky='ew', pady=(12, 0))
        rc.columnconfigure(1, weight=1)
        ttk.Label(rc, text='运行步骤', style='H2.TLabel').grid(row=0, column=0, sticky='w', pady=(0, 6))
        self.step_labels = {}
        for i, (_, desc) in enumerate(STEPS):
            dot = ttk.Label(rc, text='○', style='Muted.TLabel', width=2)
            dot.grid(row=i + 1, column=0, sticky='w')
            lab = ttk.Label(rc, text=desc, style='Muted.TLabel')
            lab.grid(row=i + 1, column=1, sticky='w', pady=1)
            self.step_labels[desc] = (dot, lab)
        ttk.Label(rc, text='结果文件', style='H2.TLabel').grid(row=0, column=2, sticky='w', padx=(40, 0))
        self.res_full = ttk.Label(rc, text='— 尚未运行 —', style='Muted.TLabel')
        self.res_full.grid(row=1, column=2, columnspan=2, sticky='w')
        self.res_filt = ttk.Label(rc, text='', style='Muted.TLabel')
        self.res_filt.grid(row=2, column=2, columnspan=2, sticky='w')
        ttk.Label(rc, text='完成后可在「数据查看」页签查看数据、在「手动配置」页签编辑 L~O 列。',
                  style='Muted.TLabel').grid(row=3, column=2, columnspan=2, sticky='w', pady=(8, 0))

        # 日志
        lf = tk.Frame(tab, bg=BG)
        lf.grid(row=3, column=0, sticky='nsew', pady=(12, 0))
        lf.rowconfigure(1, weight=1); lf.columnconfigure(0, weight=1)
        tk.Label(lf, text='运行日志', bg=BG, fg=TEXT,
                 font=('Microsoft YaHei', 11, 'bold')).grid(row=0, column=0, sticky='w', pady=(0, 6))
        box = tk.Frame(lf, bg='#111827', bd=0)
        box.grid(row=1, column=0, sticky='nsew')
        box.rowconfigure(0, weight=1); box.columnconfigure(0, weight=1)
        self.log = scrolledtext.ScrolledText(box, state='disabled', wrap='word',
                                             font=('Consolas', 9), bg='#111827',
                                             fg='#e5e7eb', insertbackground='white')
        self.log.grid(row=0, column=0, sticky='nsew')
        self.log.tag_config('ok', foreground='#4ade80')
        self.log.tag_config('err', foreground='#f87171')
        self.log.tag_config('run', foreground='#93c5fd')

    # ---------- 页签2：数据查看 ----------
    def _build_data_tab(self, nb):
        tab = ttk.Frame(nb, style='Card.TFrame', padding=10)
        nb.add(tab, text='  数据查看  ')
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(3, weight=1)

        bar = ttk.Frame(tab, style='Card.TFrame')
        bar.grid(row=0, column=0, sticky='ew', pady=(0, 8))
        ttk.Label(bar, text='查看文件：', style='Muted.TLabel').pack(side='left')
        self.dv_choice = ttk.Combobox(bar, state='readonly', width=18,
                                      values=['筛选后', '全量'], font=('Microsoft YaHei', 9))
        self.dv_choice.current(0)
        self.dv_choice.pack(side='left', padx=(4, 8))
        self.dv_choice.bind('<<ComboboxSelected>>', lambda e: self._load_data_view(self.dv_choice.get()))
        self.btn_dv_refresh = ttk.Button(bar, text='刷新', style='Small.TButton',
                                         command=lambda: self._load_data_view(self.dv_choice.get()))
        self.btn_dv_refresh.pack(side='left')
        self.btn_jump = ttk.Button(bar, text='配置选中股票 →', style='Small.TButton',
                                   command=self._jump_selected_to_config, state='disabled')
        self.btn_jump.pack(side='left', padx=(10, 0))
        self.btn_dv_select_all = ttk.Button(bar, text='全选', style='Small.TButton',
                                            command=lambda: self.dv.selection_set(self.dv.get_children()))
        self.btn_dv_select_all.pack(side='left', padx=(10, 0))
        self.btn_dv_deselect = ttk.Button(bar, text='取消选择', style='Small.TButton',
                                          command=lambda: self.dv.selection_remove(self.dv.get_children()))
        self.btn_dv_deselect.pack(side='left', padx=(6, 0))
        self.btn_batch_analysis = ttk.Button(bar, text='稳健型批量分析', style='Accent.TButton',
                                             command=self._batch_conservative_analysis)
        self.btn_batch_analysis.pack(side='left', padx=(10, 0))
        self.btn_batch_pause = ttk.Button(bar, text='暂停', style='Small.TButton',
                                          command=self._toggle_batch_pause, state='disabled')
        self.btn_batch_pause.pack(side='left', padx=(6, 0))
        self.btn_clear_analysis = ttk.Button(bar, text='清理分析缓存', style='Small.TButton',
                                             command=self._clear_analysis_cache)
        self.btn_clear_analysis.pack(side='left', padx=(6, 0))
        ttk.Label(bar, text='（实际文件仍生成于 data/ 目录）黄=PE百分位<30，绿=满足提醒 / 深绿=分析看多',
                  style='Muted.TLabel').pack(side='left', padx=(14, 0))
        self.dv_count = ttk.Label(bar, text='', style='Muted.TLabel')
        self.dv_count.pack(side='right')

        # 筛选信息条（组合筛选）
        fbar = ttk.Frame(tab, style='Card.TFrame')
        fbar.grid(row=1, column=0, sticky='ew', pady=(0, 6))
        ttk.Label(fbar, text='活动筛选：', style='Muted.TLabel').pack(side='left')
        self.dv_filter_lbl = ttk.Label(fbar, text='（无）', style='Muted.TLabel')
        self.dv_filter_lbl.pack(side='left', padx=(4, 8))
        ttk.Button(fbar, text='清除全部筛选', style='Small.TButton',
                   command=self._clear_all_dv_filters).pack(side='left')
        ttk.Label(fbar, text='   双击表头 = 筛选该列 · 单击表头 = 排序（再次单击切换升/降序）· 多列筛选自动组合(AND) · 数值列支持区间如 3-5',
                  style='Muted.TLabel').pack(side='left', padx=(14, 0))

        # 估值走势工具条
        pbar = ttk.Frame(tab, style='Card.TFrame')
        pbar.grid(row=2, column=0, sticky='ew', pady=(0, 6))
        ttk.Label(pbar, text='选中股票后：', style='Muted.TLabel').pack(side='left')
        self.btn_val_chart = ttk.Button(pbar, text='查看近10年估值走势', style='Accent.TButton',
                                        command=self._view_val_chart, state='disabled')
        self.btn_val_chart.pack(side='left')
        self.val_show_pe = tk.BooleanVar(value=True)
        self.val_show_dy = tk.BooleanVar(value=True)
        self.val_show_pr = tk.BooleanVar(value=False)
        ttk.Checkbutton(pbar, text='PE', variable=self.val_show_pe).pack(side='left', padx=(6, 0))
        ttk.Checkbutton(pbar, text='股息率', variable=self.val_show_dy).pack(side='left', padx=(2, 0))
        ttk.Checkbutton(pbar, text='分红率', variable=self.val_show_pr).pack(side='left', padx=(2, 0))
        ttk.Separator(pbar, orient='vertical').pack(side='left', fill='y', padx=(8, 8))
        ttk.Label(pbar, text='截止交易日：', style='Muted.TLabel').pack(side='left', padx=(12, 0))
        self.dv_date_entry = ttk.Entry(pbar, width=12)
        self.dv_date_entry.pack(side='left', padx=(4, 0))
        self.dv_date_entry.insert(0, '')   # 空=最新
        ttk.Label(pbar, text='（格式 2025-06-30，留空=最新交易日）30%/70% 线 + 当前位置，两系列可叠加',
                  style='Muted.TLabel').pack(side='left', padx=(10, 0))

        wrap = ttk.Frame(tab, style='Card.TFrame')
        wrap.grid(row=3, column=0, sticky='nsew')
        wrap.rowconfigure(0, weight=1); wrap.columnconfigure(0, weight=1)
        self.dv = ttk.Treeview(wrap, show='headings')
        vs = ttk.Scrollbar(wrap, orient='vertical', command=self.dv.yview)
        hs = ttk.Scrollbar(wrap, orient='horizontal', command=self.dv.xview)
        self.dv.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        self.dv.tag_configure('pe_low', background='#fff2cc')
        self.dv.tag_configure('analysis_buy', background='#c6efce', foreground='#166534')
        self.dv.tag_configure('analysis_other', background='#dbeafe', foreground='#1e40af')
        self.dv.tag_configure('analysis_err', background='#fee2e2', foreground='#991b1b')
        self.dv.tag_configure('special', background='#c6efce')
        self.dv.grid(row=0, column=0, sticky='nsew')
        vs.grid(row=0, column=1, sticky='ns')
        hs.grid(row=1, column=0, sticky='ew')
        self._editor = CellEditor(self.dv)   # 复用编辑器类（数据查看只读，不启用保存）
        self.dv.bind('<<TreeviewSelect>>', self._on_dv_select)
        self.dv.bind('<Button-1>', self._on_dv_heading_click, add='+')
        self.dv.bind('<Double-1>', self._on_dv_double, add='+')

    def _load_data_view(self, which):
        path = OUT_FILT if which == '筛选后' else OUT_FULL
        if not os.path.exists(path):
            self._clear_tree(self.dv)
            self.dv_count.config(text='文件尚未生成，请先运行')
            return
        try:
            import highlight
            df = pd.read_csv(path, encoding='utf-8-sig')
            df['代码'] = df['代码'].astype(str).str.replace(r'\D', '', regex=True).str.zfill(6)
            df = df.reset_index(drop=True)
            pe_low, special = highlight.compute_flags(df)
        except Exception:
            df = pd.read_csv(path, encoding='utf-8-sig')
            df['代码'] = df['代码'].astype(str).str.replace(r'\D', '', regex=True).str.zfill(6)
            df = df.reset_index(drop=True)
            pe_low = special = None
        # 加载稳健型分析缓存
        cache = self._load_analysis_cache()
        df['稳健型单股分析'] = df['代码'].map(lambda c: cache.get(c, ''))

        # 计算「正常化TTM股息率」(最新分红率_raw)：近12个月（TTM）普通现金股息总和 ÷ 当前股价
        try:
            import stock_db as _db
            conn = _db.connect()
            ttm = pd.read_sql_query(
                "SELECT code, SUM(per_share) AS ttm_ps FROM div_hist "
                "WHERE ann_date >= date('now','-365 days') GROUP BY code", conn)
            conn.close()
            ttm_map = dict(zip(ttm['code'], ttm['ttm_ps'])) if not ttm.empty else {}
        except Exception:
            ttm_map = {}
        df = self._prepare_data_view(df, ttm_map)

        self.dv_df = df
        self.dv_pe_low = pe_low
        self.dv_special = special
        self.dv_sort = ['', True]          # [列, 升序?]
        self.dv_filters = {}               # {列名: 筛选表达式}
        self._render_data_view()

    @staticmethod
    def _prepare_data_view(df, ttm_map):
        """数据查看页字段处理：
        - 行业：优先用 CSV 自带列；缺失时从 vr_stocks 缓存补（不触网），置于 名称 之后
        - 最新分红率_raw = 近12月(TTM)现金股息总和 ÷ 当前股价 × 100（正常化TTM股息率）
        - 去掉 EPS分红率、昨日分红率
        - 最新分红率 → 最新价格去年分红率
        - 最新分红率_raw 紧随 最新价格去年分红率 之后
        """
        df = df.copy()
        # 0) 行业列：缺失则从本地缓存(vr_stocks.industry)补，并置于 名称 之后
        if '行业' not in df.columns and '代码' in df.columns:
            try:
                import stock_db as _db
                conn = _db.connect()
                ind_map = _db.get_industry_map(conn)
                conn.close()
                if ind_map:
                    df['行业'] = df['代码'].astype(str).str.zfill(6).map(lambda c: ind_map.get(c, ''))
            except Exception:
                pass
        if '行业' in df.columns and '名称' in df.columns:
            cols0 = list(df.columns)
            cols0.remove('行业')
            cols0.insert(cols0.index('名称') + 1, '行业')
            df = df[cols0]
        if '最新价' in df.columns:
            df['最新分红率_raw'] = (
                df['代码'].astype(str).str.zfill(6).map(lambda c: ttm_map.get(c, pd.NA))
                / df['最新价'].replace(0, pd.NA) * 100.0
            ).round(2)
        # 1) 去掉 EPS分红率、昨日分红率
        drop_cols = [c for c in ('EPS分红率', '昨日分红率') if c in df.columns]
        if drop_cols:
            df = df.drop(columns=drop_cols)
        # 2) 最新分红率 → 最新价格去年分红率
        if '最新分红率' in df.columns:
            df = df.rename(columns={'最新分红率': '最新价格去年分红率'})
        # 3) 最新分红率_raw 紧随 最新价格去年分红率 之后
        cols = list(df.columns)
        if '最新价格去年分红率' in cols and '最新分红率_raw' in cols:
            cols.remove('最新分红率_raw')
            cols.insert(cols.index('最新价格去年分红率') + 1, '最新分红率_raw')
            df = df[cols]
        return df

    def _header_name_at(self, e):
        region = self.dv.identify_region(e.x, e.y)
        if region != 'heading':
            return None
        col = self.dv.identify_column(e.x)
        try:
            return self.dv['columns'][int(col[1:]) - 1]
        except Exception:
            return None

    def _on_dv_heading_click(self, e):
        name = self._header_name_at(e)
        if name is None:
            return
        if self.dv_sort[0] == name:
            self.dv_sort[1] = not self.dv_sort[1]
        else:
            self.dv_sort = [name, True]
        self._render_data_view()

    def _on_dv_double(self, e):
        name = self._header_name_at(e)
        if name is None:
            return
        self._open_col_filter(name)

    def _open_col_filter(self, col):
        win = tk.Toplevel(self.root)
        win.title(f'筛选列：{col}')
        win.geometry('420x200')
        win.resizable(False, False)
        win.configure(bg=BG)
        f = ttk.Frame(win, style='Card.TFrame', padding=16)
        f.pack(fill='both', expand=True)
        ttk.Label(f, text=f'筛选「{col}」列', style='H2.TLabel').pack(anchor='w', pady=(0, 6))
        ttk.Label(f, text='条件（支持文本包含，或数值比较：>30 / <5 / >=10 / =是）：',
                  style='Muted.TLabel').pack(anchor='w')
        entry = ttk.Entry(f, width=40)
        entry.pack(anchor='w', pady=(4, 4))
        entry.insert(0, self.dv_filters.get(col, ''))
        entry.focus_set()

        bar = ttk.Frame(f, style='Card.TFrame')
        bar.pack(anchor='w', pady=(8, 0))
        ttk.Button(bar, text='确定', style='Accent.TButton', width=8,
                   command=lambda: self._commit_col_filter(col, entry.get(), win)).pack(side='left')
        ttk.Button(bar, text='清除本列', style='Small.TButton',
                   command=lambda: self._commit_col_filter(col, '', win)).pack(side='left', padx=(8, 0))
        ttk.Button(bar, text='清除全部', style='Small.TButton',
                   command=self._clear_all_dv_filters).pack(side='left', padx=(8, 0))
        ttk.Button(bar, text='取消', style='Small.TButton',
                   command=win.destroy).pack(side='left', padx=(8, 0))
        entry.bind('<Return>', lambda e: self._commit_col_filter(col, entry.get(), win))

    def _commit_col_filter(self, col, expr, win):
        expr = expr.strip()
        if expr:
            self.dv_filters[col] = expr
        else:
            self.dv_filters.pop(col, None)
        win.destroy()
        self._render_data_view()

    def _clear_all_dv_filters(self):
        self.dv_filters = {}
        self._render_data_view()

    def _selected_dv_name(self):
        sel = self.dv.selection()
        if not sel:
            return ''
        cols = list(self.dv['columns'])
        if '名称' not in cols:
            return ''
        return str(self.dv.item(sel[0], 'values')[cols.index('名称')])

    def _fetch_baidu_pe(self, code):
        """百度估值周频PE-TTM（period='全部'，自上市日至今），用于把走势图往前延伸到东财逐日数据之前（可到~2013）。"""
        try:
            df = ak.stock_zh_valuation_baidu(symbol=code, indicator='市盈率(TTM)', period='全部')
            d = df.rename(columns={'date': '日期', 'value': 'value'})[['日期', 'value']].copy()
            d['日期'] = pd.to_datetime(d['日期'], errors='coerce')
            d['value'] = pd.to_numeric(d['value'], errors='coerce')
            return d.dropna(subset=['日期', 'value'])
        except Exception:
            return None

    def _log_dy(self, code, msg):
        try:
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(f'[股息率 {code}] {msg}\n')
        except Exception:
            pass

    def _fetch_dividend_yield(self, code):
        """构建历史股息率日线（%）：年度股息率（分子=最近已宣告会计年度每股分红合计，年报预案公告日切换；分母=当日收盘价）。
        复用于 div_hist 共享模块（含缓存），与排名列的"近10年股息率百分位"口径一致。"""
        try:
            return div_hist.get_daily_yield(code)
        except Exception as e:
            self._log_dy(code, f'股息率序列失败: {type(e).__name__} {str(e)[:120]}')
            return None

    def _view_val_chart(self):
        code = self._selected_dv_code()
        if not code:
            messagebox.showinfo('提示', '请先在数据列表中选中一行股票。')
            return
        name = self._selected_dv_name()
        date_str = self.dv_date_entry.get().strip()
        show_pe = self.val_show_pe.get()
        show_dy = self.val_show_dy.get()
        show_pr = self.val_show_pr.get()
        if not (show_pe or show_dy or show_pr):
            messagebox.showinfo('提示', '请至少勾选一项：PE / 股息率 / 分红率。')
            return
        end = None
        if date_str:
            try:
                end = pd.Timestamp(date_str)
            except Exception:
                messagebox.showwarning('提示', '日期格式有误，请用如 2025-06-30。')
                return

        pe_w = cur_pe = pe30 = pe70 = None
        if show_pe:
            conn = stock_db.connect()
            pe = stock_db.get_pe(conn, code)
            conn.close()
            if pe is None or pe.empty:
                messagebox.showinfo('提示', f'没有 {code} 的 PE 历史数据。')
            else:
                pe = pe.copy()
                pe['日期'] = pd.to_datetime(pe['日期'], errors='coerce')
                pe = pe.dropna(subset=['日期']).sort_values('日期')
                pe['value'] = pd.to_numeric(pe['value'], errors='coerce')
                pe = pe.dropna(subset=['value'])
                if pe.empty:
                    messagebox.showinfo('提示', '无有效 PE 数据。')
                else:
                    end_pe = end if end is not None else pe['日期'].iloc[-1]
                    start = end_pe - pd.Timedelta(days=3650)   # 截止日往前10年
                    if pe['日期'].iloc[0] > start:
                        ext = self._fetch_baidu_pe(code)
                        if ext is not None:
                            ext = ext[(ext['日期'] <= end_pe) & (ext['日期'] >= start)]
                            before = ext[ext['日期'] < pe['日期'].iloc[0]]
                            if not before.empty:
                                pe = pd.concat([before, pe]).sort_values('日期').drop_duplicates('日期')
                    pe_w = pe[pe['日期'] <= end_pe]
                    if pe_w.empty:
                        pe_w = pe
                    pe_w = pe_w[pe_w['日期'] >= start]
                    if pe_w.empty:
                        pe_w = pe
                    cur_pe = pe_w['value'].iloc[-1]
                    pe30 = pe_w['value'].quantile(0.30)
                    pe70 = pe_w['value'].quantile(0.70)

        dy_w = cur_dy = dy30 = dy70 = None
        if show_dy:
            dy = self._fetch_dividend_yield(code)
            if dy is None or dy.empty:
                messagebox.showinfo('提示', f'没有 {code} 的历史股息率数据（需巨潮分红详情+新浪日线）。')
            else:
                end_dy = end if end is not None else dy['日期'].iloc[-1]
                start = end_dy - pd.Timedelta(days=3650)
                dy_w = dy[dy['日期'] <= end_dy]
                if dy_w.empty:
                    dy_w = dy
                dy_w = dy_w[dy_w['日期'] >= start]
                if dy_w.empty:
                    dy_w = dy
                cur_dy = dy_w['value'].iloc[-1]
                dy30 = dy_w['value'].quantile(0.30)
                dy70 = dy_w['value'].quantile(0.70)

        pr_w = cur_pr = pr30 = pr70 = None
        if show_pr:
            pr = self._fetch_payout_history(code)
            if pr is None or pr.empty:
                messagebox.showinfo('提示', f'没有 {code} 的历史分红率数据（需分红明细+每股收益）。')
            else:
                end_pr = end if end is not None else pr['日期'].iloc[-1]
                start = end_pr - pd.Timedelta(days=3650)
                pr_w = pr[pr['日期'] <= end_pr]
                if pr_w.empty:
                    pr_w = pr
                pr_w = pr_w[pr_w['日期'] >= start]
                if pr_w.empty:
                    pr_w = pr
                cur_pr = pr_w['value'].iloc[-1]
                pr30 = pr_w['value'].quantile(0.30)
                pr70 = pr_w['value'].quantile(0.70)

        if pe_w is None and dy_w is None and pr_w is None:
            return
        # 各序列延展到“最新日期(今天)”：年度分红率等低频序列止步于较早的公告日，
        # 会导致图表最新时间不是今天。无新数据时按最后值前移(Carry-forward)，
        # 使 PE/股息率/分红率 三条线都画到今天，图表标题也显示今天。
        today = pd.Timestamp.today().normalize()
        target_end = end if end is not None else today
        pe_w = self._extend_series_to(pe_w, target_end)
        dy_w = self._extend_series_to(dy_w, target_end)
        pr_w = self._extend_series_to(pr_w, target_end)
        self._show_val_plot(code, name, pe_w, cur_pe, pe30, pe70,
                            dy_w, cur_dy, dy30, dy70, pr_w, cur_pr, pr30, pr70)

    def _fetch_payout_history(self, code):
        """分红率年度序列（%）= 现金分红总额/归母净利润，按预案公告日对齐日期轴。复用 div_hist。"""
        try:
            return div_hist.get_payout_history(code)
        except Exception as e:
            self._log_dy(code, f'分红率序列失败: {type(e).__name__} {str(e)[:120]}')
            return None

    @staticmethod
    def _extend_series_to(w, target_end):
        """将序列按最后值前移(Carry-forward)到 target_end，使图表画到最新日期。
        target_end 之前的已有数据不动；已在 target_end 及之后则原样返回。"""
        if w is None or w.empty:
            return w
        last_date = w['日期'].iloc[-1]
        if last_date >= target_end:
            return w
        last_val = w['value'].iloc[-1]
        extra = pd.DataFrame([{'日期': target_end, 'value': last_val}])
        return pd.concat([w, extra]).sort_values('日期').reset_index(drop=True)

    def _show_val_plot(self, code, name, pe_w, cur_pe, pe30, pe70,
                       dy_w, cur_dy, dy30, dy70, pr_w, cur_pr, pr30, pr70):
        parts = [t for t, v in (('PE', pe_w is not None), ('股息率', dy_w is not None),
                                ('分红率', pr_w is not None)) if v]
        win = tk.Toplevel(self.root)
        win.title(f'近10年估值走势（{"+".join(parts)}） · {name}({code})')
        win.geometry('920x560')
        fig = Figure(figsize=(9, 5.2), dpi=100)
        ax = fig.add_subplot(111)
        series = []
        if pe_w is not None:
            series.append('pe')
        if dy_w is not None:
            series.append('dy')
        if pr_w is not None:
            series.append('pr')
        # 轴分配：主轴给第1个序列，其余各建一个右轴并右移错开
        axmap = {series[0]: ax}
        if len(series) > 1:
            a2 = ax.twinx()
            a2.spines['right'].set_position(('outward', 0))
            axmap[series[1]] = a2
        if len(series) > 2:
            a3 = ax.twinx()
            a3.spines['right'].set_position(('outward', 70))
            axmap[series[2]] = a3
        style = {
            'pe': ('PE-TTM', '#2563eb', '#60a5fa', '#1e40af'),
            'dy': ('股息率(%)', '#d97706', '#fbbf24', '#b45309'),
            'pr': ('分红率(%)', '#7c3aed', '#c4b5fd', '#5b21b6'),
        }
        datas = {'pe': (pe_w, cur_pe, pe30, pe70),
                 'dy': (dy_w, cur_dy, dy30, dy70),
                 'pr': (pr_w, cur_pr, pr30, pr70)}
        first = last = None
        handles, labels = [], []
        for key in series:
            w, cur, p30, p70 = datas[key]
            axn = axmap[key]
            label, col, l30, l70 = style[key]
            axn.plot(w['日期'], w['value'], color=col, linewidth=1.3, label=label)
            axn.axhline(p30, color=l30, linestyle='--', linewidth=1.0,
                        label=f'{label} 30%线 = {p30:.2f}')
            axn.axhline(p70, color=l70, linestyle='--', linewidth=1.0,
                        label=f'{label} 70%线 = {p70:.2f}')
            ld = w['日期'].iloc[-1]
            axn.plot(ld, cur, 'o', color=col, markersize=7,
                     label=f'当前{label} = {cur:.2f}')
            axn.set_ylabel(label, color=col)
            axn.tick_params(axis='y', labelcolor=col)
            if first is None:
                first = w['日期'].iloc[0]
            last = w['日期'].iloc[-1]
            handles += axn.get_lines()
            labels += [l.get_label() for l in axn.get_lines()]
        ax.set_title(f'{name}（{code}） 近10年估值走势  {first.date()} ~ {last.date()}')
        ax.set_xlabel('日期')
        ax.grid(True, linestyle=':', alpha=0.5)
        ax.legend(handles, labels, loc='best', fontsize=8)
        fig.autofmt_xdate()
        canvas = FigureCanvasTkAgg(fig, master=win)
        canvas.get_tk_widget().pack(fill='both', expand=True)
        canvas.draw()

    def _update_dv_filter_bar(self):
        items = [f'{c}:{v}' for c, v in self.dv_filters.items()]
        self.dv_filter_lbl.config(text='  '.join(items) if items else '（无）')

    def _update_dv_headings(self):
        cols = list(self.dv['columns'])
        for c in cols:
            mark = ' ▾' if c in self.dv_filters else ''
            self.dv.heading(c, text=c + mark)

    def _dv_filter_mask(self, df, col, expr):
        s = df[col]
        num = pd.to_numeric(s, errors='coerce')
        # 数值列支持区间：3-5 或 3~5 或 3..5（含端点）
        if num.notna().mean() > 0.9:
            m = re.match(r'^\s*(\d+(?:\.\d+)?)\s*[-~:]{1,2}\s*(\d+(?:\.\d+)?)\s*$', expr)
            if m:
                lo, hi = float(m.group(1)), float(m.group(2))
                lo, hi = min(lo, hi), max(lo, hi)
                return num.between(lo, hi)
        first = expr[0]
        if first in ('>', '<', '='):
            try:
                if first == '=':
                    return s.astype(str).str.strip() == expr[1:].strip()
                if expr[:2] in ('>=', '<='):
                    op, val = expr[:2], float(expr[2:])
                    return num >= val if op == '>=' else num <= val
                op, val = expr[0], float(expr[1:])
                return num > val if op == '>' else num < val
            except Exception:
                return s.astype(str).str.contains(expr, na=False, regex=False)
        return s.astype(str).str.contains(expr, na=False, regex=False)

    def _render_data_view(self):
        df = self.dv_df
        if df is None:
            return
        for col, expr in self.dv_filters.items():
            df = df[self._dv_filter_mask(df, col, expr)]
        if self.dv_sort[0]:
            col, asc = self.dv_sort[0], self.dv_sort[1]
            try:
                num = pd.to_numeric(df[col], errors='coerce')
                if num.notna().mean() > 0.9:
                    df = df.assign(_n=num).sort_values('_n', ascending=asc).drop(columns='_n')
                else:
                    df = df.sort_values(col, ascending=asc, key=lambda s: s.astype(str))
            except Exception:
                try:
                    df = df.sort_values(col, ascending=asc)
                except Exception:
                    pass
        self._render(self.dv, df,
                     None if self.dv_pe_low is None else self.dv_pe_low.reindex(df.index),
                     None if self.dv_special is None else self.dv_special.reindex(df.index))
        self.dv_count.config(text=f'显示 {len(df)} / {len(self.dv_df)} 行')
        self._update_dv_filter_bar()
        self._update_dv_headings()

    def _on_dv_select(self, _e=None):
        sel = self.dv.selection()
        state = 'normal' if sel else 'disabled'
        self.btn_jump.config(state=state)
        self.btn_val_chart.config(state=state)

    def _selected_dv_code(self):
        sel = self.dv.selection()
        if not sel:
            return None
        cols = list(self.dv['columns'])
        if '代码' not in cols:
            return None
        values = self.dv.item(sel[0], 'values')
        return norm_code(values[cols.index('代码')]) or None

    def _selected_dv_codes(self):
        """返回当前在列表中人工选中的股票代码列表（已规范化）。"""
        sel = self.dv.selection()
        if not sel:
            return []
        cols = list(self.dv['columns'])
        if '代码' not in cols:
            return []
        idx = cols.index('代码')
        out = []
        for iid in sel:
            values = self.dv.item(iid, 'values')
            if idx < len(values):
                c = norm_code(values[idx])
                if c and c not in out:
                    out.append(c)
        return out

    def _jump_selected_to_config(self):
        code = self._selected_dv_code()
        if not code:
            messagebox.showinfo('提示', '请先在数据列表中选中一行股票。')
            return
        self._jump_to_config(code)

    def _jump_to_config(self, code):
        """切换到手动配置页并自动选中/展开该股票进行编辑。"""
        self.cfg_search.delete(0, 'end')
        self.cfg_only.set(False)
        if not any(r['代码'] == code for r in self.cfg_rows):
            row = {'代码': code, '名称': '', '是否保留': '',
                   '买入提醒pe': '', '买入提醒价格': '', '买入pb': ''}
            src = self._result_row_for(code)
            if src:
                row['名称'] = src.get('名称', '')
                for k in CFG_EDITABLE:
                    row[k] = src.get(k, '')
            self.cfg_rows.append(row)
        self._render_config()
        iid = next((str(i) for i, r in enumerate(self.cfg_rows) if r['代码'] == code), None)
        if iid is None:
            return
        self.nb.select(self.nb.tabs()[2])
        self.cfg_tv.see(iid)
        self.cfg_tv.selection_set(iid)
        self.cfg_tv.focus_set()
        self.root.after(60, lambda: self._cfg_editor.edit(iid, '是否保留'))

    def _result_row_for(self, code):
        """从结果 CSV 读取某代码一行的 L~O 值（用于跳转时带入）。"""
        for path in (OUT_FILT, OUT_FULL):
            if os.path.exists(path):
                try:
                    df = pd.read_csv(path, encoding='utf-8-sig')
                    df['代码'] = df['代码'].astype(str).str.replace(r'\D', '', regex=True).str.zfill(6)
                    hit = df[df['代码'] == code]
                    if not hit.empty:
                        r = hit.iloc[0]
                        return {'代码': code, '名称': _s(r.get('名称')),
                                '是否保留': _s(r.get('是否保留')),
                                '买入提醒pe': _s(r.get('买入提醒pe')),
                                '买入提醒价格': _s(r.get('买入提醒价格')),
                                '买入pb': _s(r.get('买入pb'))}
                except Exception:
                    continue
        return None

    @staticmethod
    def _render(tv, df, pe_low=None, special=None):
        tv.delete(*tv.get_children())
        cols = [str(c) for c in df.columns]
        tv['columns'] = cols
        for c in cols:
            tv.heading(c, text=c)
            w = min(max(len(str(c)) * 16 + 20, 80), 180)
            if c == '稳健型单股分析':
                w = 140
            tv.column(c, width=w, anchor='w', stretch=False)
        BUY_SIGNALS = {'BUY', 'ACCUMULATE', 'STRONG_ACCUMULATE', 'OVERWEIGHT'}
        for i, (_, r) in enumerate(df.iterrows()):
            tag = ''
            if special is not None and special.iloc[i]:
                tag = 'special'
            elif pe_low is not None and pe_low.iloc[i]:
                tag = 'pe_low'
            vals = ['' if pd.isna(v) else str(v) for v in r]
            tags = [tag] if tag else []
            # 稳健型分析列高亮
            if '稳健型单股分析' in cols:
                sig_val = vals[cols.index('稳健型单股分析')]
                if sig_val in BUY_SIGNALS:
                    tags.append('analysis_buy')
                elif sig_val in ('HOLD', 'WAIT', 'NEUTRAL', ''):
                    pass
                elif 'ERROR' in sig_val:
                    tags.append('analysis_err')
                else:
                    tags.append('analysis_other')
            tv.insert('', 'end', values=vals, tags=tuple(tags))

    @staticmethod
    def _clear_tree(tv):
        tv.delete(*tv.get_children())

    # ---------- 稳健型分析缓存 ----------
    def _load_analysis_cache(self):
        if os.path.exists(ANALYSIS_CACHE):
            try:
                with open(ANALYSIS_CACHE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_analysis_cache(self, cache):
        os.makedirs(DATA, exist_ok=True)
        with open(ANALYSIS_CACHE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)

    def _clear_analysis_cache(self):
        """清理所有行的稳健型单股分析列结果。"""
        if os.path.exists(ANALYSIS_CACHE):
            try:
                os.remove(ANALYSIS_CACHE)
            except Exception:
                pass
        self._load_data_view(self.dv_choice.get())
        self._post('log', '已清理稳健型分析缓存\n', 'run')

    def _batch_conservative_analysis(self):
        if self.running:
            messagebox.showinfo('提示', '有任务正在运行，请稍后。')
            return
        df = self.dv_df
        if df is None or df.empty:
            messagebox.showinfo('提示', '请先运行1号任务生成数据。')
            return
        # 人工选中则只分析选中股票；未选中则分析全部
        sel_codes = self._selected_dv_codes()
        if sel_codes:
            codes = sel_codes
            scope = f'选中 {len(codes)} 只'
        else:
            codes = df['代码'].tolist()
            scope = f'全部 {len(codes)} 只'
        cache = self._load_analysis_cache()
        pending = [c for c in codes if c not in cache]
        if not pending:
            messagebox.showinfo('提示', f'{scope} 中的股票均已分析完成（共 {len(codes)} 只）。')
            return
        if not messagebox.askyesno('确认',
                f'将对「{scope}」进行稳健型批量分析，其中 {len(pending)} 只待分析。\n'
                f'稳健型模式分析每只约需10~30秒，全部完成可能需要较长时间。\n\n'
                '是否开始批量分析？'):
            return
        self.running = True
        self.batch_paused = False
        self.btn_batch_analysis.config(state='disabled')
        self.btn_batch_pause.config(state='normal', text='暂停')
        self.btn_run.config(state='disabled')
        threading.Thread(target=self._batch_analysis_worker,
                         args=(codes, cache), daemon=True).start()

    def _toggle_batch_pause(self):
        """暂停/继续 稳健型批量分析。"""
        if not self.running:
            return
        self.batch_paused = not getattr(self, 'batch_paused', False)
        if self.batch_paused:
            self.btn_batch_pause.config(text='继续')
            self._post('log', '⏸ 稳健型批量分析已暂停（点击「继续」恢复）\n', 'run')
        else:
            self.btn_batch_pause.config(text='暂停')
            self._post('log', '▶ 稳健型批量分析已继续\n', 'run')

    def _batch_analysis_worker(self, codes, cache):
        from valresearch.main import analyze as vr_analyze
        import datetime
        today = datetime.date.today().isoformat()
        total = len(codes)
        ok = 0
        fail = 0
        for i, code in enumerate(codes):
            if code in cache:
                continue
            # 暂停轮询：被暂停时阻塞等待，每 0.5s 检查一次
            while getattr(self, 'batch_paused', False) and self.running:
                time.sleep(0.5)
            if not self.running:
                break
            try:
                self._post('status', f'分析 {i+1}/{total} {code}…', ACCENT)
                rep = vr_analyze(code, today, 'conservative')
                sig = ''
                try:
                    sig = rep.signal.get('final_signal', '')
                except Exception:
                    try:
                        sig = rep.signal.final_signal
                    except Exception:
                        pass
                cache[code] = sig or 'N/A'
                ok += 1
                if (i + 1) % 10 == 0 or (i + 1) == total:
                    self._post('log', f'[分析进度] {i+1}/{total}  ✓{ok} ✕{fail}\n', 'run')
            except Exception as e:
                cache[code] = f'ERROR'
                fail += 1
                self._post('log', f'[分析失败] {code}: {e}\n', 'err')
            if (i + 1) % 5 == 0:
                self._save_analysis_cache(cache)
                self._post('status', f'分析进度 {i+1}/{total}', ACCENT)
        self._save_analysis_cache(cache)
        self._post('status', f'分析完成 ✓{ok} ✕{fail}', GREEN)
        self._post('log', f'\n稳健型批量分析完成：成功 {ok}，失败 {fail}\n')
        self.running = False
        self.batch_paused = False
        self.btn_batch_analysis.config(state='normal')
        self.btn_batch_pause.config(state='disabled', text='暂停')
        self.btn_run.config(state='normal')
        # 刷新数据查看
        try:
            self._load_data_view(self.dv_choice.get())
        except Exception:
            pass

    # ---------- 页签3：手动配置 ----------
    def _build_config_tab(self, nb):
        tab = ttk.Frame(nb, style='Card.TFrame', padding=10)
        nb.add(tab, text='  手动配置  ')
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(2, weight=1)

        # 工具栏
        bar = ttk.Frame(tab, style='Card.TFrame')
        bar.grid(row=0, column=0, sticky='ew', pady=(0, 6))
        ttk.Label(bar, text='搜索代码：', style='Muted.TLabel').pack(side='left')
        self.cfg_search = ttk.Entry(bar, width=12)
        self.cfg_search.pack(side='left', padx=(4, 4))
        self.cfg_search.bind('<KeyRelease>', lambda e: self._render_config())
        self.cfg_only = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text='仅已配置', variable=self.cfg_only,
                        command=self._render_config).pack(side='left', padx=(8, 0))
        ttk.Button(bar, text='添加股票', style='Small.TButton',
                   command=self._add_config_stock).pack(side='left', padx=(14, 4))
        self.cfg_add_code = ttk.Entry(bar, width=8)
        self.cfg_add_code.pack(side='left')
        ttk.Button(bar, text='从结果载入', style='Small.TButton',
                   command=self._reload_from_result).pack(side='left', padx=(10, 4))
        ttk.Button(bar, text='重新加载', style='Small.TButton',
                   command=self._load_config).pack(side='left')
        ttk.Button(bar, text='💾 保存配置', style='Accent.TButton',
                   command=self._save_config).pack(side='right')

        tip = tk.Label(tab, text='双击单元格可编辑：是否保留(是/否)、买入提醒pe、买入提醒价格、买入pb。'
                                '保存后写入 data/排除/手动配置.csv，下次运行自动按新值计算、判断与展示。',
                       bg=CARD, fg=MUTED, font=('Microsoft YaHei', 9), anchor='w', justify='left')
        tip.grid(row=1, column=0, sticky='ew', pady=(0, 6))

        wrap = ttk.Frame(tab, style='Card.TFrame')
        wrap.grid(row=2, column=0, sticky='nsew')
        wrap.rowconfigure(0, weight=1); wrap.columnconfigure(0, weight=1)
        self.cfg_tv = ttk.Treeview(wrap, columns=CONFIG_COLS, show='headings')
        vs = ttk.Scrollbar(wrap, orient='vertical', command=self.cfg_tv.yview)
        hs = ttk.Scrollbar(wrap, orient='horizontal', command=self.cfg_tv.xview)
        self.cfg_tv.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        widths = {'代码': 80, '名称': 120, '是否保留': 90, '买入提醒pe': 110,
                  '买入提醒价格': 110, '买入pb': 90}
        for c in CONFIG_COLS:
            self.cfg_tv.heading(c, text=c)
            self.cfg_tv.column(c, width=widths[c], anchor='w', stretch=False)
        self.cfg_tv.grid(row=0, column=0, sticky='nsew')
        vs.grid(row=0, column=1, sticky='ns')
        hs.grid(row=1, column=0, sticky='ew')
        # 内联编辑：仅 4 个可编辑列写入 cfg_rows
        self._cfg_editor = CellEditor(
            self.cfg_tv, editable=CFG_EDITABLE, commit=self._on_cfg_edit,
            value_map={'是否保留': ['是', '否']})

    def _on_cfg_edit(self, item, col, new):
        idx = int(item)
        field = CFG_EDITABLE.get(col)
        if field is None:
            return
        self.cfg_rows[idx][field] = new

    def _load_config(self):
        """从《手动配置.csv》载入（并叠加结果中的代码/名称）。"""
        rows = []
        if os.path.exists(MANUAL):
            m = pd.read_csv(MANUAL, encoding='utf-8-sig')
            m['代码'] = m['代码'].astype(str).str.replace(r'\D', '', regex=True).str.zfill(6)
            for _, r in m.iterrows():
                rows.append({
                    '代码': r['代码'],
                    '名称': '',
                    '是否保留': _s(r.get('是否保留')),
                    '买入提醒pe': _s(r.get('买入提醒pe')),
                    '买入提醒价格': _s(r.get('买入提醒价格')),
                    '买入pb': _s(r.get('买入pb')),
                })
        self._fill_names(rows)
        self.cfg_rows = rows
        self._render_config()

    def _reload_from_result(self):
        """从《分红率排名（筛选后）.csv》载入全部股票作为候选，并叠加已保存的配置。"""
        path = OUT_FILT if os.path.exists(OUT_FILT) else OUT_FULL
        if not os.path.exists(path):
            messagebox.showinfo('提示', '请先运行1号任务生成结果文件。')
            return
        df = pd.read_csv(path, encoding='utf-8-sig')
        df['代码'] = df['代码'].astype(str).str.replace(r'\D', '', regex=True).str.zfill(6)
        saved = {r['代码']: r for r in self.cfg_rows}
        rows = []
        for _, r in df.iterrows():
            s = saved.get(r['代码'], {})
            rows.append({
                '代码': r['代码'], '名称': str(r.get('名称', '')),
                '是否保留': s.get('是否保留', ''),
                '买入提醒pe': s.get('买入提醒pe', ''),
                '买入提醒价格': s.get('买入提醒价格', ''),
                '买入pb': s.get('买入pb', ''),
            })
        self.cfg_rows = rows
        self._render_config()

    def _fill_names(self, rows):
        """从结果文件补全股票名称。"""
        path = OUT_FILT if os.path.exists(OUT_FILT) else OUT_FULL
        if not os.path.exists(path):
            return
        df = pd.read_csv(path, encoding='utf-8-sig')
        df['代码'] = df['代码'].astype(str).str.replace(r'\D', '', regex=True).str.zfill(6)
        names = dict(zip(df['代码'].astype(str), df['名称'].astype(str)))
        for r in rows:
            if not r['名称']:
                r['名称'] = names.get(r['代码'], '')

    def _add_config_stock(self):
        code = self.cfg_add_code.get().strip().replace(r'\D', '')
        if not code:
            messagebox.showwarning('提示', '请输入 6 位股票代码。')
            return
        code = code.zfill(6)
        if any(r['代码'] == code for r in self.cfg_rows):
            messagebox.showinfo('提示', '该代码已在列表中。')
            return
        self.cfg_rows.append({'代码': code, '名称': '', '是否保留': '',
                              '买入提醒pe': '', '买入提醒价格': '', '买入pb': ''})
        self._fill_names(self.cfg_rows)
        self.cfg_add_code.delete(0, 'end')
        self._render_config()

    def _render_config(self):
        kw = self.cfg_search.get().strip()
        only = self.cfg_only.get()
        self.cfg_tv.delete(*self.cfg_tv.get_children())
        for i, r in enumerate(self.cfg_rows):
            if only and not any(r[c] for c in CFG_EDITABLE):
                continue
            if kw and kw not in r['代码']:
                continue
            self.cfg_tv.insert('', 'end', iid=str(i),
                               values=[r[c] for c in CONFIG_COLS])

    def _save_config(self):
        try:
            self._save_config_impl()
        except Exception as e:
            traceback.print_exc()
            self._log_error()
            messagebox.showerror('保存失败', f'保存配置时出错：\n{e}\n\n详情见 data/error.log')

    def _log_error(self):
        try:
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write('\n' + '-' * 40 + '\n')
                traceback.print_exc(file=f)
        except Exception:
            pass

    def _save_config_impl(self):
        if not os.path.isdir(EXCL_DIR):
            os.makedirs(EXCL_DIR, exist_ok=True)
        out = []
        for r in self.cfg_rows:
            if not any(r[c] for c in CFG_EDITABLE):
                continue   # 未配置的行不写入
            row = {'代码': r['代码']}
            row.update({c: r[c] for c in CFG_EDITABLE})
            out.append(row)
        if not out:
            messagebox.showinfo('提示', '没有已配置的行需要保存。')
            return
        df = pd.DataFrame(out)
        # 合并同代码：手动配置以 代码 为主键
        df['代码'] = df['代码'].astype(str).str.replace(r'\D', '', regex=True).str.zfill(6)
        df = df.groupby('代码', as_index=False).first()
        df.to_csv(MANUAL, index=False, encoding='utf-8-sig')
        saved = len(df)
        if messagebox.askyesno('已保存', f'已保存 {saved} 只股票的配置 → data/排除/手动配置.csv\n\n是否重新执行1号任务？'):
            self.nb.select(self.nb.tabs()[0])          # 跳到「运行」页
            self.root.after(300, self.run_task)

    # ---------- 行为（worker 线程只入队，主线程轮询更新 UI） ----------
    def _poll_loop(self):
        while True:
            try:
                item = self.q.get_nowait()
            except queue.Empty:
                break
            try:
                self._handle(item)
            except Exception:
                pass
        self.root.after(30, self._poll_loop)

    def _handle(self, item):
        kind = item[0]
        if kind == 'log':
            self._append(item[1], item[2])
        elif kind == 'bar':
            self.progress.config(value=max(0.0, min(100.0, item[1])))
        elif kind == 'step':
            desc, state = item[1], item[2]
            dot, lab = self.step_labels[desc]
            sym, color = {'idle': ('○', MUTED), 'run': ('◐', ACCENT),
                          'done': ('✓', GREEN), 'fail': ('✕', RED)}[state]
            dot.config(text=sym, foreground=color)
        elif kind == 'status':
            self.status.config(text=item[1], foreground=item[2])
        elif kind == 'results':
            self.res_full.config(text=item[1]); self.res_filt.config(text=item[2])
            self.btn_open.config(state='normal')
            # 完成后刷新查看页签
            try:
                self._load_data_view(self.dv_choice.get())
            except Exception:
                pass
            try:
                self._load_config()
            except Exception:
                pass

    def _post(self, *item):
        self.q.put(item)

    def _append(self, text, tag=None):
        self.log.config(state='normal')
        self.log.insert('end', text, tag)
        self.log.see('end')
        self.log.config(state='disabled')

    def _set_bar(self, value):
        self._post('bar', value)

    def _parse_progress(self, line, step_start):
        m = re.search(r'\[PE进度\]\s*(\d+)/(\d+)', line)
        if m and int(m.group(2)) > 0:
            a, b = int(m.group(1)), int(m.group(2))
            val = step_start + (a / b) * 50
            self._post('bar', val)
            self._post('status', f'运行中… {int(round(val))}%', ACCENT)

    def run_task(self):
        if self.running:
            return
        self.running = True
        self.btn_run.config(state='disabled')
        self.btn_open.config(state='disabled')
        self.status.config(text='运行中…', foreground=ACCENT)
        self._post('bar', 0)
        for _, desc in STEPS:
            self._post('step', desc, 'idle')
        self.log.config(state='normal'); self.log.delete('1.0', 'end'); self.log.config(state='disabled')
        self.res_full.config(text='运行中…'); self.res_filt.config(text='')
        threading.Thread(target=self._work, daemon=True).start()

    def _work(self):
        for f in (OUT_FULL, OUT_FILT):
            try:
                os.remove(f)
            except FileNotFoundError:
                pass
        # 清理稳健型分析缓存
        if os.path.exists(ANALYSIS_CACHE):
            try:
                os.remove(ANALYSIS_CACHE)
            except Exception:
                pass
        self._post('log', '已清理旧输出文件\n', 'run')

        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONUTF8'] = '1'
        env['PYTHONUNBUFFERED'] = '1'

        ok = True
        for idx, (script, desc) in enumerate(STEPS):
            step_start = idx * 50.0
            self._post('bar', step_start)
            self._post('step', desc, 'run')
            self._post('log', f'—— {desc}（{script}）——\n', 'run')
            try:
                proc = subprocess.Popen(
                    [sys.executable, os.path.join(BASE, script)],
                    cwd=BASE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    env=env, encoding='utf-8', errors='replace', bufsize=1,
                )
                for line in iter(proc.stdout.readline, ''):
                    self._post('log', line, None)
                    self._parse_progress(line, step_start)
                proc.stdout.close()
                code = proc.wait()
                if code != 0:
                    self._post('log', f'\n[失败] {script} 退出码 {code}\n', 'err')
                    self._post('step', desc, 'fail')
                    ok = False
                    break
                self._post('step', desc, 'done')
                self._post('bar', step_start + 50.0)
            except Exception as e:
                self._post('log', f'\n[异常] {script}: {e}\n', 'err')
                self._post('step', desc, 'fail')
                ok = False
                break
            self._post('log', '\n')

        self._finish(ok)

    def _finish(self, ok):
        if ok:
            self._post('bar', 100)
        if ok and os.path.exists(OUT_FILT):
            full_n = self._count(OUT_FULL)
            filt_n = self._count(OUT_FILT)
            self._post('results',
                       f'● 全量：分红率排名.csv  （{full_n} 只）',
                       f'● 筛选后：分红率排名（筛选后）.csv  （{filt_n} 只）')
            self._post('status', f'完成 · 全量 {full_n} / 筛选后 {filt_n}', GREEN)
            self._post('log', '✅ 1号任务执行完成！\n')
            self._post('log', f'  全量: {full_n} 只\n  筛选后: {filt_n} 只\n')
            # 稳健型批量分析不再自动启动，请到「数据查看」页签手动开启
            self._post('log', '\n分红率排名已完成。如需稳健型单股分析，请切换到「数据查看」页签点击「稳健型批量分析」按钮手动开启。\n', 'run')
        else:
            self._post('status', '失败，请查看日志', RED)
            self._post('log', '❌ 执行失败，请检查上方日志。\n', 'err')
        self._post('bar', 0 if not ok else 100)
        self.btn_run.config(state='normal')
        self.running = False

    @staticmethod
    def _count(path):
        try:
            with open(path, 'rb') as f:
                return sum(1 for _ in f) - 1
        except Exception:
            return 0

    def open_folder(self):
        if sys.platform.startswith('win'):
            os.startfile(os.path.dirname(OUT_FILT))
        else:
            subprocess.Popen(['open', os.path.dirname(OUT_FILT)])


def _s(v):
    """值 -> 去空字符串；NaN -> ''。"""
    if v is None or pd.isna(v):
        return ''
    s = str(v).strip()
    return '' if s.lower() == 'nan' else s


class CellEditor:
    """Treeview 内联单元格编辑器：双击进入，回车/失焦提交。"""

    def __init__(self, tv, editable=None, commit=None, value_map=None):
        self.tv = tv
        self.editable = editable or {}      # {列名: 字段名}
        self.commit = commit                # fn(item, 列名, 新值)
        self.value_map = value_map or {}    # {列名: [可选值]} -> 双击显示可选列表
        self.entry = None
        self._item = None
        self._col = None
        tv.bind('<Double-1>', self._on_double, add='+')
        tv.bind('<Button-1>', self._on_click, add='+')

    def _col_name(self, col):
        try:
            return self.tv['columns'][int(col.replace('#', '')) - 1]
        except Exception:
            return None

    def edit(self, iid, col_name):
        """编程方式打开某行某列的内联编辑器（用于从其他页跳转）。"""
        self._close(commit=True)
        if col_name not in self.editable:
            return
        try:
            col = '#%d' % (self.tv['columns'].index(col_name) + 1)
        except ValueError:
            return
        self.tv.see(iid)
        bbox = self.tv.bbox(iid, col)
        if not bbox:
            return
        self._item, self._col = iid, col_name
        opts = self.value_map.get(col_name)
        if opts:
            self._open_combobox(bbox, opts)
        else:
            self._open_entry(bbox)

    def _on_click(self, e):
        if self.entry:
            self._close(commit=True)

    def _on_double(self, e):
        if self.entry:
            self._close(commit=True)
        region = self.tv.identify_region(e.x, e.y)
        if region != 'cell':
            return
        item = self.tv.identify_row(e.y)
        col = self.tv.identify_column(e.x)
        if not item or not col:
            return
        cname = self._col_name(col)
        if cname not in self.editable:
            return
        bbox = self.tv.bbox(item, col)
        if not bbox:
            return
        self._item, self._col = item, cname
        opts = self.value_map.get(cname)
        if opts:
            self._open_combobox(bbox, opts)
        else:
            self._open_entry(bbox)

    def _open_entry(self, bbox):
        e = tk.Entry(self.tv)
        e.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])
        e.insert(0, self.tv.set(self._item, self._col))
        e.select_range(0, 'end')
        e.focus()
        self.entry = e
        e.bind('<Return>', lambda _: self._close(True))
        e.bind('<Escape>', lambda _: self._close(False))
        e.bind('<FocusOut>', lambda _: self._close(True))

    def _open_combobox(self, bbox, opts):
        cb = ttk.Combobox(self.tv, values=opts, state='readonly')
        cb.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])
        cur = self.tv.set(self._item, self._col)
        cb.set(cur if cur in opts else opts[0])
        cb.focus()
        self.entry = cb
        cb.bind('<<ComboboxSelected>>', lambda _: self._close(True))
        cb.bind('<Return>', lambda _: self._close(True))
        cb.bind('<Escape>', lambda _: self._close(False))

    def _close(self, commit):
        if self.entry is None:
            return
        item, col = self._item, self._col
        new = self.entry.get()
        self.entry.destroy()
        self.entry = None
        self._item = self._col = None
        if commit:
            self.tv.set(item, column=col, value=new)
            if self.commit:
                self.commit(item, col, new)


LOGIC_TEXT = """1号任务 · A股分红率排名 —— 计算逻辑
==================================================
一、分红率
  分红率 = 2025自然年内每股分红合计 / 当日收盘价 × 100
  分红口径：股权登记日在 2025-01-01~2025-12-31、方案已实施、现金分红>0。
  报告期覆盖：20240930/20241231/20250331/20250630/20250930，
  同一笔按(代码+股权登记日)去重；每股分红=现金分红比例(每10股)/10 求和。
  最新分红率用最新价，昨日分红率用昨收。

二、近10年PE百分位（雪球口径，位于当前PB之后）
  数据源：东财逐日估值 stock_value_em，覆盖约8.6年逐交易日（约2090个样本/只，
  比月频数据精度大幅提升；东财该接口上限约2093行/只）。
  取序列最后一日"当前PE-TTM"。
  百分位 = 历史样本中低于当前PE的天数 / 总样本天数 × 100
  含义：数值越小说明当前估值处于近十年越低的位置（越便宜）。
  逐日PE落库到 pe_hist、逐日PB落库到 pb_hist（本地永久缓存，复算不走远程）。
  同时输出两列：当前PE（末值）、当前PB（末值）。

二·补、是否满足近5年增长（位于当前PB之后、近10年PE百分位之前）
  数据源：东财财务摘要 stock_financial_abstract 的"营业总收入"与"净利润"，
  取最近5个完整会计年度（2021~2025 年报）。
  判断为"是"需同时满足：
    1) 5年内任何一年的营收、净利润均 > 0（不允许为负）
    2) 上一年(最新)营收与净利润 均 > 5年前(最早) 相应值（整体趋势增长）
    3) 中间年份"下降年份" ≤ 2（下降年份 = 该年营收与净利润均较上一年下降）
  否则为"否"。年度数据落库到 finance5（本地永久缓存，复算不走远程）。

三、筛选条件
  1. 仅沪深主板：代码前缀 60/00（排除创业板300/301、科创板688/689、北交所）
  2. 排除 ST
  3. 近5年(2020~2024)每年均有现金分红（连续性交集）
  4. 最新分红率 > 3.0%，按最新分红率降序排列

四、排除数据合并与最终筛选
  从 data/排除/ 全部文件按代码并集，取 是否保留(J)/买入提醒pe(L)/
  买入提醒价格(M)/买入pb(N)，逐列取第一个非空值(coalesce)合并。
  手动配置（data/排除/手动配置.csv，应用内编辑）为权威：覆盖其他文件，
  其"是否保留"以手动配置为准。任一文件"是否保留==否"即排除，
  得到《分红率排名（筛选后）.csv》。
  注：已去掉"分红率涨跌幅"列；新增"当前PE/当前PB"列位于昨日分红率之后。
  列序：排名 代码 名称 每股分红合计 最新价 昨收 最新分红率 昨日分红率
        当前PE 当前PB 是否满足近5年增长 近10年PE百分位 是否保留 买入提醒pe 买入提醒价格 买入pb

五、高亮与满足提醒
  1) 低位高亮(黄)：近10年PE百分位 < 30
  2) 满足提醒高亮(绿)：是否保留==是，且满足 买入提醒pe/买入提醒价格/买入pb 任一（空列跳过）
     · 当前PE ≤ 买入提醒pe (L)
     · 当前价(最新价) ≤ 买入提醒价格 (M)
     · 当前PB ≤ 买入pb (N)
  绿色优先于黄色。应用内「数据查看」页签与导出的 Excel(.xlsx) 均带此高亮。

六、本地历史数据（D:\\stockdata\\hist.db）
  dividend 分红 / spot 行情 / pe_hist 逐日PE / pb_hist 逐日PB /
  valuation_current 当前PE·PB，本地有则读本地，缺失才远程抓取并缓存。

七、应用内操作
  ·「数据查看」页签：直接查看 csv 数据（可切换 全量/筛选后），带黄/绿高亮，
    实际文件仍生成于 data/ 目录。
  ·「手动配置」页签：双击编辑 L~O 列（是否保留/买入提醒pe/买入提醒价格/买入pb），
    保存到 data/排除/手动配置.csv，下次运行按新值计算、判断与展示。
"""


def main():
    # pythonw 无控制台时 sys.stdout/stderr 为 None，会导致 akshare 内部 tqdm 进度条崩溃
    if sys.stdout is None:
        sys.stdout = io.StringIO()
    if sys.stderr is None:
        sys.stderr = io.StringIO()
    root = tk.Tk()

    def _hook(exc_type, exc, tb):
        try:
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write('\n' + '-' * 40 + '\n')
                f.write(''.join(traceback.format_exception(exc_type, exc, tb)))
        except Exception:
            pass

    root.report_callback_exception = _hook
    sys.excepthook = _hook
    TaskApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
