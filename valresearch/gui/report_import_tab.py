# -*- coding: utf-8 -*-
"""财报导入分析页签。"""
from valresearch.parsing import PDFParser, BankInterpreter, DataValidator, AIInterpreter
from valresearch.data.providers import IndustryDataProvider
from dataclasses import dataclass

import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import threading
import queue

ACCENT = '#3b82f6'
BG = '#f4f6fb'
CARD = '#ffffff'
TEXT = '#1f2937'
MUTED = '#6b7280'

BANK_INDUSTRIES = {'银行', '证券', '保险'}


class ReportImportTab:
    def __init__(self, nb):
        self.nb = nb
        self.q = queue.Queue()
        self.tab = ttk.Frame(nb, style='Card.TFrame', padding=12)
        self.ip = IndustryDataProvider()
        self.busy = False
        self._build()
        self.root = self.tab.winfo_toplevel()
        self.root.after(40, self._poll)

    def _build(self):
        main_frame = ttk.Frame(self.tab, padding='12')
        main_frame.pack(fill='both', expand=True)

        input_frame = ttk.LabelFrame(main_frame, text='输入信息', padding='12')
        input_frame.pack(fill='x', pady=(0, 12))

        grid_opts = {'sticky': 'w', 'padx': 8, 'pady': 6}

        ttk.Label(input_frame, text='股票代码：').grid(row=0, column=0, **grid_opts)
        self.code_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.code_var, width=15).grid(row=0, column=1, **grid_opts)

        ttk.Label(input_frame, text='财报PDF文件：').grid(row=0, column=2, **grid_opts)
        self.pdf_path_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.pdf_path_var, width=40).grid(row=0, column=3, **grid_opts)
        ttk.Button(input_frame, text='选择文件', command=self._select_pdf).grid(row=0, column=4, padx=4)

        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill='x', pady=(0, 12))

        self.btn_parse = ttk.Button(action_frame, text='开始解析', command=self._start_parse)
        self.btn_parse.pack(side='left', padx=(0, 8))

        self.btn_import = ttk.Button(action_frame, text='确认导入', command=self._import_data, state='disabled')
        self.btn_import.pack(side='left', padx=(0, 8))

        self.btn_cancel = ttk.Button(action_frame, text='取消', command=self._reset)
        self.btn_cancel.pack(side='left')

        progress_frame = ttk.Frame(main_frame)
        progress_frame.pack(fill='x', pady=(0, 12))

        self.progress = ttk.Progressbar(progress_frame, mode='determinate')
        self.progress.pack(fill='x', side='left', padx=(0, 12))

        self.status = tk.Label(progress_frame, text='就绪', fg=MUTED, font=('Arial', 9))
        self.status.pack(side='left')

        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill='both', expand=True)

        nb_content = ttk.Notebook(content_frame)
        nb_content.pack(fill='both', expand=True)

        self.out = scrolledtext.ScrolledText(nb_content, state='disabled', wrap='word',
                                            font=('Consolas', 9), bg='#111827', fg='#e5e7eb',
                                            insertbackground='white')
        nb_content.add(self.out, text='解析结果')

        self.validation_out = scrolledtext.ScrolledText(nb_content, state='disabled', wrap='word',
                                                       font=('Consolas', 9), bg='#111827', fg='#e5e7eb',
                                                       insertbackground='white')
        nb_content.add(self.validation_out, text='数据验证')

        self.interpretation_out = scrolledtext.ScrolledText(nb_content, state='disabled', wrap='word',
                                                           font=('Consolas', 9), bg='#111827', fg='#e5e7eb',
                                                           insertbackground='white')
        nb_content.add(self.interpretation_out, text='专业解读')

        self._clear_output()
        self._clear_validation_output()
        self._clear_interpretation_output()

    def _select_pdf(self):
        file_path = filedialog.askopenfilename(
            title='选择财报PDF文件',
            filetypes=[('PDF文件', '*.pdf'), ('所有文件', '*.*')]
        )
        if file_path:
            self.pdf_path_var.set(file_path)

    def _start_parse(self):
        if self.busy:
            return

        symbol = self.code_var.get().strip()
        pdf_path = self.pdf_path_var.get().strip()

        if not symbol:
            messagebox.showerror('错误', '请输入股票代码')
            return

        if not pdf_path:
            messagebox.showerror('错误', '请选择财报PDF文件')
            return

        industry_info = self.ip.get_industry(symbol)
        industry = industry_info.get('industry', '') if industry_info else ''
        industry_type = industry_info.get('industry_type', '') if industry_info else ''

        if not any(k in industry for k in BANK_INDUSTRIES) and not any(k in industry_type for k in BANK_INDUSTRIES):
            messagebox.showwarning('提示', f'当前行业：{industry or industry_type}\n暂不支持该行业的财报解读，仅支持银行业')
            return

        self._set_busy(True, '正在解析...')

        t = threading.Thread(target=self._parse_thread, args=(symbol, pdf_path, industry_type), daemon=True)
        t.start()

    def _parse_thread(self, symbol, pdf_path, industry_type):
        try:
            self.q.put(('prog', 10, '加载PDF...'))

            parser = PDFParser(pdf_path, symbol)
            parse_result = parser.parse()

            self.q.put(('prog', 40, '数据验证...'))

            validator = DataValidator(symbol)
            validation_result = validator.validate(parse_result)

            self.q.put(('prog', 60, '银行业专业解读...'))

            bank_interpreter = BankInterpreter(parse_result)
            bank_analysis = bank_interpreter.interpret()

            self.q.put(('prog', 80, '大模型解读...'))

            ai_interpreter = AIInterpreter(parse_result, bank_analysis)
            ai_result = ai_interpreter.interpret()

            self.q.put(('prog', 100, '解析完成'))

            self.q.put(('result', {
                'parse_result': parse_result,
                'validation_result': validation_result,
                'bank_analysis': bank_analysis,
                'ai_result': ai_result
            }))

        except Exception as e:
            self.q.put(('err', str(e)))
            self._set_busy(False, '解析失败')

    def _import_data(self):
        if not hasattr(self, '_last_result'):
            return

        self._set_busy(True, '正在导入数据...')

        t = threading.Thread(target=self._import_thread, args=(self._last_result,), daemon=True)
        t.start()

    def _import_thread(self, result):
        try:
            parse_result = result['parse_result']
            validation_result = result['validation_result']
            bank_analysis = result['bank_analysis']
            ai_result = result['ai_result']

            import sqlite3
            from pathlib import Path

            db_path = Path(__file__).resolve().parents[2] / 'data' / 'annual_reports.db'
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO annual_reports (symbol, report_date, report_type, report_year, report_period, source_file)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                parse_result.symbol,
                parse_result.report_date,
                parse_result.report_type,
                int(parse_result.report_date[:4]),
                parse_result.report_date,
                str(self.pdf_path_var.get())
            ))

            report_id = cursor.lastrowid

            for metric in parse_result.metrics:
                cursor.execute('''
                    INSERT INTO financial_data (report_id, category, metric_name, metric_value, metric_unit, period, is_consolidated, page_number, confidence)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    report_id,
                    'extracted',
                    metric.metric_name,
                    metric.value,
                    metric.unit,
                    metric.period,
                    1 if metric.is_consolidated else 0,
                    metric.page_number,
                    metric.confidence
                ))

            for interp in bank_analysis.capital_adequacy + bank_analysis.asset_quality + bank_analysis.profitability + bank_analysis.liquidity:
                cursor.execute('''
                    INSERT INTO bank_interpretation (report_id, interpretation_type, metric_name, metric_value, rating, analysis)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    report_id,
                    interp.interpretation_type,
                    interp.metric_name,
                    interp.metric_value,
                    interp.rating,
                    interp.analysis
                ))

            cursor.execute('''
                INSERT INTO ai_interpretation (report_id, model_name, model_version, interpretation_summary, risk_assessment, investment_advice)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                report_id,
                ai_result.model_name,
                ai_result.model_version,
                ai_result.interpretation_summary,
                ai_result.risk_assessment,
                ai_result.investment_advice
            ))

            conn.commit()
            conn.close()

            self.q.put(('import_success', f'成功导入{report_id}条记录'))

        except Exception as e:
            self.q.put(('err', f'导入失败: {str(e)}'))
            self._set_busy(False, '导入失败')

    def _reset(self):
        self._clear_output()
        self._clear_validation_output()
        self._clear_interpretation_output()
        self.code_var.set('')
        self.pdf_path_var.set('')
        self.progress['value'] = 0
        self.status.config(text='就绪')
        self.btn_import.config(state='disabled')
        self._last_result = None

    def _set_busy(self, busy: bool, msg: str):
        self.busy = busy
        if busy:
            self.btn_parse.config(state='disabled')
            self.status.config(text=msg)
        else:
            self.btn_parse.config(state='normal')
            self.status.config(text=msg)

    def _clear_output(self):
        self.out.config(state='normal')
        self.out.delete('1.0', 'end')
        self.out.config(state='disabled')

    def _clear_validation_output(self):
        self.validation_out.config(state='normal')
        self.validation_out.delete('1.0', 'end')
        self.validation_out.config(state='disabled')

    def _clear_interpretation_output(self):
        self.interpretation_out.config(state='normal')
        self.interpretation_out.delete('1.0', 'end')
        self.interpretation_out.config(state='disabled')

    def _append(self, text, tag=None, widget='out'):
        if widget == 'out':
            w = self.out
        elif widget == 'validation_out':
            w = self.validation_out
        else:
            w = self.interpretation_out
        w.config(state='normal')
        w.insert('end', text + '\n', tag)
        w.see('end')
        w.config(state='disabled')

    def _poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                kind = item[0]

                if kind == 'prog':
                    self.progress['value'] = item[1]
                    self.status.config(text=item[2])

                elif kind == 'result':
                    self._last_result = item[1]
                    self._display_result(self._last_result)
                    self._set_busy(False, '解析完成')
                    self.btn_import.config(state='normal')

                elif kind == 'import_success':
                    self._set_busy(False, '导入成功')
                    self._append(f'\n{item[1]}', widget='out')
                    messagebox.showinfo('成功', '财报数据已成功导入数据库')

                elif kind == 'err':
                    self._append(f'\n错误: {item[1]}', 'err', widget='out')
                    self._set_busy(False, '失败')

        except queue.Empty:
            pass

        self.root.after(40, self._poll)

    def _display_result(self, result):
        parse_result = result['parse_result']
        validation_result = result['validation_result']
        bank_analysis = result['bank_analysis']
        ai_result = result['ai_result']

        self._clear_output()
        self._clear_validation_output()
        self._clear_interpretation_output()

        L = []

        L.append('=' * 64)
        L.append('PDF解析结果')
        L.append('=' * 64)
        L.append(f'股票代码: {parse_result.symbol}')
        L.append(f'报告日期: {parse_result.report_date}')
        L.append(f'报告类型: {parse_result.report_type}')
        L.append(f'提取指标数: {len(parse_result.metrics)}')
        L.append(f'文字段落数: {len(parse_result.text_sections)}')

        if parse_result.parse_warnings:
            L.append('\n警告:')
            for w in parse_result.parse_warnings:
                L.append(f'  · {w}')

        if parse_result.parse_errors:
            L.append('\n错误:')
            for e in parse_result.parse_errors:
                L.append(f'  · {e}')

        L.append('\n' + '=' * 64)
        L.append('核心财务数据')
        L.append('=' * 64)
        for metric in parse_result.metrics[:20]:
            L.append(f'{metric.metric_name}: {metric.value} {metric.unit}')

        self._append('\n'.join(L), widget='out')

        self._display_validation(validation_result)
        self._display_interpretation(bank_analysis, ai_result)

    def _display_validation(self, validation_result):
        L = []

        L.append('=' * 64)
        L.append('数据验证结果')
        L.append('=' * 64)
        L.append(validation_result.summary)

        if validation_result.comparisons:
            L.append('\n详细对比:')
            for comp in validation_result.comparisons:
                status_icon = {'match': '✓', 'warning': '⚠', 'error': '✗'}.get(comp.status, '?')
                L.append(f'  {status_icon} {comp.metric_name}:')
                L.append(f'     PDF: {comp.pdf_value:.2f}, API: {comp.api_value:.2f}, 差异: {comp.diff_percent:.2f}%')

        self._append('\n'.join(L), widget='validation_out')

    def _display_interpretation(self, bank_analysis, ai_result):
        L = []

        L.append('=' * 64)
        L.append('银行业专业解读')
        L.append('=' * 64)

        sections = [
            ('资本充足性分析', bank_analysis.capital_adequacy),
            ('资产质量分析', bank_analysis.asset_quality),
            ('盈利能力分析', bank_analysis.profitability),
            ('流动性分析', bank_analysis.liquidity)
        ]

        for section_title, interpretations in sections:
            if interpretations:
                L.append(f'\n【{section_title}】')
                for interp in interpretations:
                    rating_icon = {
                        'excellent': '★★★★★',
                        'good': '★★★★',
                        'average': '★★★',
                        'poor': '★★',
                        'warning': '★'
                    }.get(interp.rating, 'N/A')
                    L.append(f'{rating_icon} {interp.metric_name}: {interp.metric_value:.2f}%')
                    L.append(f'   {interp.analysis}')

        overall = bank_analysis.overall_assessment
        L.append(f'\n【综合评价】')
        L.append(f'综合评分: {overall["overall_score"]:.2f}')
        L.append(f'总体评级: {overall["overall_rating"]}')
        L.append(f'{overall["summary"]}')
        L.append(f'投资建议: {overall["investment_advice"]}')

        if overall.get('risk_alerts'):
            L.append('\n风险提示:')
            for alert in overall['risk_alerts']:
                L.append(f'  · {alert}')

        self._append('\n'.join(L), widget='interpretation_out')


def build_report_import_tab(nb):
    tab = ReportImportTab(nb)
    return tab