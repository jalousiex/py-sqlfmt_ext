"""迁移对拍：新外挂层（官方 filter + 本项目 pass）对 fixture 的复现度。

两张登记表，语义完全不同，**不要混**：

* ``KNOWN_DIFF``：**还没做**的用例 → ``xfail(strict=True)``。修好一个就会 XPASS 失败，
  提示把该项删掉。清单清空 = 迁移把该复现的都复现了。
* ``DEVIATIONS``：**故意不做**的用例（口径重定）→ **断言**而非 xfail。理由见 PLAN §4
  「对旧 fork 的有意偏离清单」。用 xfail 的话，基线或实现发生漂移会静默通过，
  所以这里把「新基线」写成对 canonical 的定向变换，再断言真实相等。

运行：``.venv\\Scripts\\python.exe -m pytest tests_migration/ -q``
"""

import re

import pytest

from sqlfmt_ext import format_statements
from tests.fixtures.sql_cases import SQL_CASES, normalize_sql

_ALIGN = "列对齐（AlignPass）未实现"

# 未复现用例 → 原因（修好一个删一个）
KNOWN_DIFF = {
    # --- S5：结构性折行 ---
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

# 有意偏离：新架构**不打算**复现旧基线的用例（口径重定，不是「还没做」）。
# 每项 = (理由, 把 canonical 变换成新基线的方式)；理由必须写清「差在哪、为什么」，
# 因为这是 S7 交付时要向用户交代的清单（见 PLAN §4）。
DEVIATIONS = {
    "case/sqltest4_s03": (
        "【口径重定】旧基线把 `case` 与首个 `when` 分到两行，但那依赖**输入换行**"
        "（本用例的 input.sql 就是 `case` 换行、`when` 顶格，属 C4 禁止依赖的行为）。"
        "新架构按结构性口径把首个 `when` 并回 `case` 同行 —— 与 sqltest4_s01（无 input 文件，"
        "`case` 后仅在有注释时才换行）、sqltest4_s02、dml/sqltest1_s06 同形。"
        "与旧基线的差异**仅此一处折行**：`when b = 'NUMBER'    then …`、`else … c`、"
        "`end as type_name` 的列对齐逐字节相同（见 PLAN §9.3「S5c」）。",
        # canonical 开头是：`       case` / `            when b in ('X', 'Y') then …`
        lambda exp: re.sub(r"case\n\s*when", "case when", exp, count=1),
    ),
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
    expected = normalize_sql(case.expected_sql)

    deviation = DEVIATIONS.get(case.name)
    if deviation is not None:
        reason, transform = deviation
        transformed = transform(expected)
        # 变换失效说明 canonical 已经变了（例如 S7 正式重定基线），此时这条偏离
        # 已经过期，必须复核而不是继续静默通过。
        assert transformed != expected, f"DEVIATIONS 变换已失效，请复核：{reason}"
        expected = transformed

    assert got == expected
