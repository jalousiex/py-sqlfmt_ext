"""迁移对拍：新外挂层（官方 filter + 本项目 pass）对 fixture 的复现度。

迁移期间尚未复现的用例先 ``xfail(strict=True)``：修好一个就会 XPASS 失败，
提示把该项从 ``KNOWN_DIFF`` 里删掉。清单清空即为迁移完成。

运行：``.venv\\Scripts\\python.exe -m pytest tests_migration/ -q``
"""

import pytest

from sqlfmt_ext import format_statements
from tests.fixtures.sql_cases import SQL_CASES, normalize_sql

_ALIGN = "列对齐（AlignPass）未实现"
_COMMENT = "注释强制换行规则（LayoutPass）未实现"
_FIELD_LIST = "括号内字段列表未展开（LayoutPass）"
_CASE_FIRST_WHEN = "CASE 首个 WHEN 布局待定结构性规则（LayoutPass L5）"

# 未复现用例 → 原因（修好一个删一个）
KNOWN_DIFF = {
    # --- LayoutPass：注释强制换行（覆盖最多，优先做） ---
    "case/sqltest4_s01": _COMMENT,
    # s03 的期望输出（case 后首个 when 独占一行）在旧实现里依赖**输入换行**判定，
    # 属已知不收敛用例；官方 strip 之下没有该换行可用，必须先定下结构性规则
    # （L5）或重定基线，暂列 KNOWN_DIFF。
    "case/sqltest4_s03": _CASE_FIRST_WHEN,
    "comma/sqltest7_s02": _COMMENT,
    "cte/sqltest2_s02": _COMMENT,
    "dml/sqltest1_s01": _COMMENT,
    "nested/sqltest3_s01": _COMMENT,
    "nested/sqltest3_s02": _COMMENT,
    "window/sqltest6_s01": _COMMENT,
    "window/sqltest6_s03": _COMMENT,
    # --- LayoutPass：括号内字段列表展开 ---
    "ddl/sqltest0_s01": _FIELD_LIST,
    "ddl/sqltest0_s02": _FIELD_LIST,
    "ddl/sqltest0_s03": _FIELD_LIST,
    "ddl/sqltest0_s06": _FIELD_LIST,
    "dml/sqltest1_s02": _FIELD_LIST,
    "dml/sqltest1_s04": _FIELD_LIST,
    # --- LayoutPass：语句/CTE 换行 ---
    "dml/sqltest1_s06": "多个 LATERAL VIEW 未各自分行（LayoutPass）",
    # --- AlignPass：列对齐 ---
    "debug/sqldebug_s01": _ALIGN,
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
