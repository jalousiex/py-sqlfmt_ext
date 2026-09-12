"""对比进入 AlignedIndentFilter 的语句文本（定位收敛差异来源）。"""
import difflib
import random
import sys

sys.path.insert(0, ".")

import sqlfmt  # noqa: E402
from sqlparse.filters import AlignedIndentFilter  # noqa: E402
from tests.fixtures.sql_cases import SQL_CASES  # noqa: E402
from tests.sqlfmt_test_helpers import scramble_whitespace  # noqa: E402

recorded = []
_orig_process = AlignedIndentFilter.process


def spy(self, stmt):
    recorded.append(str(stmt))
    return _orig_process(self, stmt)


AlignedIndentFilter.process = spy

name = sys.argv[1] if len(sys.argv) > 1 else "aggregate/sqltest5_s01"
case = next(c for c in SQL_CASES if c.name == name)
canonical = case.expected_sql.strip("\n")

recorded.clear()
sqlfmt.sqlfilefmt(case.input_sql, **case.options)
base = "\n<<<STMT>>>\n".join(recorded)

variant = scramble_whitespace(canonical, random.Random(f"{name}:0"))
if variant == canonical:
    print("variant == canonical, skip")
    sys.exit()
recorded.clear()
sqlfmt.sqlfilefmt(variant, **case.options)
got = "\n<<<STMT>>>\n".join(recorded)

print(f"[{name}] AlignedIndentFilter 输入是否一致: {base == got}  (语句数 {len(recorded)})")
if base != got:
    for line in difflib.unified_diff(
        base.splitlines(keepends=True),
        got.splitlines(keepends=True),
        fromfile="canonical-input",
        tofile="variant-input",
        lineterm="",
    ):
        print(line.rstrip("\n"))
