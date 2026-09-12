"""打印打乱不收敛用例的差异。"""
import difflib
import random
import sys

sys.path.insert(0, ".")

import sqlfmt  # noqa: E402
from tests.fixtures.sql_cases import SQL_CASES  # noqa: E402
from tests.sqlfmt_test_helpers import scramble_whitespace  # noqa: E402

NAMES = sys.argv[1:] or ["dml/sqltest1_s01", "aggregate/sqltest5_s01"]

for name in NAMES:
    case = next(c for c in SQL_CASES if c.name == name)
    canonical = case.expected_sql.strip("\n")
    for seed in (0, 1, 2):
        variant = scramble_whitespace(canonical, random.Random(f"{name}:{seed}"))
        got = sqlfmt.sqlfilefmt(variant, **case.options).strip("\n")
        if got == canonical:
            print(f"[{name}] seed={seed} OK")
            continue
        print("=" * 70)
        print(f"[{name}] seed={seed}")
        print("--- 打乱输入 ---")
        print(variant)
        print("--- diff (期望 -> 实际) ---")
        for line in difflib.unified_diff(
            canonical.splitlines(keepends=True),
            got.splitlines(keepends=True),
            fromfile="expected",
            tofile="actual",
            lineterm="",
        ):
            print(line.rstrip("\n"))
        break
