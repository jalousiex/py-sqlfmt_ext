"""S7-a 门禁：以**新实现**（`sqlfmt_ext`）为准的收敛性与幂等性。

与 `tests/test_sqlfmt_convergence.py` / `test_sqlfmt_idempotency.py` 的关系：
那两份跑在旧 fork 上、是迁移期的 **oracle**（删 fork 前不能动基线，见 PLAN §9.4 S7-d）；
本文件只问「新实现自己满足不满足这两个性质」，用于 S7-a 验收。
迁移完成后本文件并入 `tests/`，那时两侧合成一份。

收敛口径：把 canonical 的 token 间隔空白**确定性压平**（只改空白，不改 token 类型与
顺序）后再格式化一次，结果应仍等于 canonical —— 即「输出只取决于 token 流」。

运行：``.venv\\Scripts\\python.exe -m pytest tests_migration/ -q``
"""

import pytest

from sqlfmt_ext import format_statements
from tests.fixtures.sql_cases import SQL_CASES, normalize_sql
from tests.fixtures.whitespace import flatten_whitespace

# 新实现下**仍然**「输出依赖输入空白」的用例 → 原因（修好一个删一个）。
# 按实测填写（不是照抄旧套件的 KNOWN_DIVERGENT）：旧套件 6 条里
#   * `dml/sqltest1_s06` 已**不在列** —— S5a 的 `MULTIWORD_REGEX` 兜底让多个
#     `lateral view` 不再被挤进 `from` 行，新实现已收敛 ✓（净收益）；
#   * `case/sqltest4_s03` 属**基线未重定**，S7-d 处理后应删除此项；
#   * 其余 3 条是同一类真差异：注释（块注释 / 行首注释）与分号布局仍受输入换行影响；
#   * `ddl/sqltest0_s04` 的「ON COMMIT 刻意分行」是**口径本身**（白名单行为），
#     旧套件同样登记，非缺陷。
KNOWN_DIVERGENT = {
    "case/sqltest4_s03": (
        "基线未重定：canonical 仍是旧口径（`case` 与首个 `when` 分两行），"
        "本实现按结构性口径同行 —— 见 PLAN §9.4 S7-d，重定后该项应删除"
    ),
    "comma/sqltest7_s02": "块注释之间的换行被压掉（comma_first=True）",
    "cte/sqltest2_s01": "where 后行首注释 / 分号布局依赖输入换行",
    "nested/sqltest3_s01": "块注释后的换行 / 行首注释对齐依赖输入换行",
    "ddl/sqltest0_s04": "ON COMMIT 刻意分行，属白名单行为，非缺陷",
}


def _format(sql_text, case):
    return normalize_sql(format_statements(sql_text, case.options))


def _params(known):
    params = []
    for case in SQL_CASES:
        reason = known.get(case.name)
        marks = (pytest.mark.xfail(strict=True, reason=reason),) if reason else ()
        params.append(pytest.param(case, id=case.name, marks=marks))
    return params


@pytest.mark.parametrize("case", _params(KNOWN_DIVERGENT))
def test_flattened_input_should_converge(case):
    canonical = normalize_sql(case.expected_sql)
    variant = flatten_whitespace(canonical)
    assert _format(variant, case) == canonical, "压平输入空白后输出发生变化"


@pytest.mark.parametrize("case", _params({}))  # 幂等不共用收敛的 xfail 清单
def test_format_should_be_idempotent_from_expected(case):
    once = _format(normalize_sql(case.expected_sql), case)
    assert _format(once, case) == once, "二次格式化结果发生变化"


@pytest.mark.parametrize("case", _params({}))
def test_format_should_be_idempotent_from_input(case):
    once = _format(case.input_sql, case)
    assert _format(once, case) == once, "从输入 SQL 出发的二次格式化结果发生变化"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
