"""迁移对拍：新外挂层（官方 filter + 本项目 pass）对 fixture 的复现度。

迁移期间尚未复现的用例先 ``xfail(strict=True)``：修好一个就会 XPASS 失败，
提示把该项从 ``KNOWN_DIFF`` 里删掉。清单清空即为迁移完成。

运行：``.venv\\Scripts\\python.exe -m pytest tests_migration/ -q``
"""

import pytest

from sqlfmt_ext import format_statements
from tests.fixtures.sql_cases import SQL_CASES, normalize_sql

_ALIGN = "列对齐（AlignPass）未实现"
_CASE_FIRST_WHEN = "CASE 首个 WHEN 布局待定结构性规则（LayoutPass L5）"

# 未复现用例 → 原因（修好一个删一个）
KNOWN_DIFF = {
    # --- S5：结构性折行 ---
    # s03 的期望输出（case 后首个 when 独占一行）在旧实现里依赖**输入换行**判定，
    # 属已知不收敛用例；官方 strip 之下没有该换行可用，必须先定下结构性规则
    # （L5）或重定基线，暂列 KNOWN_DIFF。
    "case/sqltest4_s03": _CASE_FIRST_WHEN,
    # 窗口函数断行：期望 `ROW_NUMBER() --` 独占一行、`over(...)` 另起。
    # 真因是分组口径（U14）：官方 group_functions 用「下标相邻」判定要不要把 OVER
    # 并进 Function，`)` 与 `over` 之间**隔着注释**时判定失败 → 注释把列表打断，
    # 见 PLAN §9.3「S5b」。
    "cte/sqltest2_s02": "U14：`)` 与 `over` 之间的注释挡住官方 over 并入 Function",
    # --- S6：列对齐（含注释列 / 末尾逗号列 / from 缩进） ---
    "case/sqltest4_s01": _ALIGN,
    # ddl/s01 除对齐外还差一条：官方 `group_functions` 对 CREATE+TABLE 提前 return，
    # 比 fork 多这个条件，导致 `duplicate key(...)` / `range(...)` / `hash(...)`
    # 没被包成 Function，被字段列表分支误展开（见 PLAN §9.3 S4c）
    "ddl/sqltest0_s01": _ALIGN,
    "ddl/sqltest0_s02": _ALIGN,
    "nested/sqltest3_s01": _ALIGN,
    "nested/sqltest3_s02": _ALIGN,
    "window/sqltest6_s01": _ALIGN,
    "window/sqltest6_s03": _ALIGN,
}


def _params():
    params = []
    for case in SQL_CASES:
        reason = KNOWN_DIFF.get(case.name)
        marks = (pytest.mark.xfail(strict=True, reason=reason),) if reason else ()
        params.append(pytest.param(case, id=case.name, marks=marks))
    return params


@pytest.mark.parametrize("case", _params())
def test_parity(case):
    got = normalize_sql(format_statements(case.input_sql, case.options))
    assert got == normalize_sql(case.expected_sql)
