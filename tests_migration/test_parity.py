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
_STMT_SPLIT = "语句/CTE 换行规则（LayoutPass）未实现"

# 未复现用例 → 原因（修好一个删一个）
KNOWN_DIFF = {
    # --- LayoutPass：注释强制换行（覆盖最多，优先做） ---
    "case/sqltest4_s01": _COMMENT,
    "case/sqltest4_s02": _COMMENT,
    "comma/sqltest7_s01": _COMMENT,
    "comma/sqltest7_s02": _COMMENT,
    "cte/sqltest2_s01": _COMMENT,
    "cte/sqltest2_s02": _COMMENT,
    "dml/sqltest1_s01": _COMMENT,
    "dml/sqltest1_s05": _COMMENT,
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
    "dml/sqltest1_s03": _FIELD_LIST,
    "dml/sqltest1_s04": _FIELD_LIST,
    # --- LayoutPass：语句/CTE 换行 ---
    "ddl/sqltest0_s05": _STMT_SPLIT,
    "ddl/sqltest0_s04": "ON COMMIT 刻意分行（白名单行为）",
    "dml/sqltest1_s06": "多个 LATERAL VIEW 未各自分行（LayoutPass）",
    "generic/sqltest8_s01": "`select * from` 未折叠同行（LayoutPass）",
    "case/sqltest4_s03": "CASE 首个 WHEN 未独占一行（LayoutPass）",
    # --- AlignPass：列对齐 ---
    "aggregate/sqltest5_s01": _ALIGN,
    "aggregate/sqltest5_s02": _ALIGN,
    "debug/sqldebug_s01": _ALIGN,
    "dml/sqltest1_s07": _ALIGN,
    "dml/sqltest1_s08": _ALIGN,
    "window/sqltest6_s02": _ALIGN,
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
