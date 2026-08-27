# -*- coding: utf-8 -*-
"""P0-7 数据查看页「稳健型批量分析」支持人工多选 / 全选。

核心：_selected_dv_codes 应从列表当前选中行提取代码（已规范化、去重、按行序）。
用轻量 Mock 模拟 Treeview（无需真实 GUI / tkinter）。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import run_task as rt


class _FakeDV:
    def __init__(self, columns, rows):
        self._columns = list(columns)
        self._rows = [tuple(r) for r in rows]   # 每行 value 元组
        self._sel = []                          # 选中的行索引(整数)

    def __getitem__(self, key):
        # self.dv['columns']
        return self._columns

    def selection(self):
        return [str(i) for i in self._sel]

    def item(self, iid, what):
        # 仅用到 values
        return self._rows[int(iid)]


class _FakeApp:
    def __init__(self, columns, rows):
        self.dv = _FakeDV(columns, rows)


def _make():
    cols = ['排名', '代码', '名称', '最新价格去年分红率', '最新分红率_raw']
    rows = [
        (1, '605368', 'X', 5.0, 5.6),
        (2, '600519', 'Y', 2.0, 1.8),
        (3, '000001', 'Z', 3.0, 2.1),
    ]
    return _FakeApp(cols, rows)


def test_no_selection_returns_empty():
    app = _make()
    assert rt.TaskApp._selected_dv_codes(app) == [], '未选中应返回空列表'


def test_selection_returns_codes_in_row_order():
    app = _make()
    app.dv._sel = [0, 2]          # 选第 1、3 行
    codes = rt.TaskApp._selected_dv_codes(app)
    assert codes == ['605368', '000001'], f'应为选中行代码且按行序, 实际 {codes}'


def test_selection_dedup():
    app = _make()
    # 重复选中同一行 → 去重
    app.dv._sel = [1, 1, 0]
    codes = rt.TaskApp._selected_dv_codes(app)
    assert codes == ['600519', '605368'], f'应去重且按行序, 实际 {codes}'


if __name__ == '__main__':
    test_no_selection_returns_empty()
    test_selection_returns_codes_in_row_order()
    test_selection_dedup()
    print('== P0-7 数据查看页多选/全选 全部通过 ==')
