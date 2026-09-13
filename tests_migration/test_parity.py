"""迁移对拍：新外挂层（官方 filter + 本项目 pass）对 fixture 的复现度。

**已全绿**（S7-d 起）：31 个用例逐字节复现 canonical。原先这里有两张登记表 ——
`KNOWN_DIFF`（**还没做**）与 `DEVIATIONS`（**故意不做**，口径重定）—— 现在都已清空：

* 前者在 S6 收尾时清空（7 个列对齐用例全部带回）；
* 后者唯一一条（`case/sqltest4_s03`：`case` 与首个 `when` 是否同行）已随 **S7-d 正式重定基线**
  —— 旧基线依赖**输入换行**（属 C4 禁止的行为），新口径是同形用例一致的结构性口径。

于是本文件退化成一份普通的对拍测试。S7-e 会把它并入 `tests/`。

运行：``.venv\\Scripts\\python.exe -m pytest tests_migration/ -q``
"""

import pytest

from sqlfmt_ext import format_statements
from tests.fixtures.sql_cases import SQL_CASES, normalize_sql


@pytest.mark.parametrize("case", SQL_CASES, ids=lambda case: case.name)
def test_parity(case):
    got = normalize_sql(format_statements(case.input_sql, case.options))
    expected = normalize_sql(case.expected_sql)
    assert got == expected
