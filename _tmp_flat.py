"""检验假设：把所有 token 间隔空白确定性地压成单个空格后，当前实现能否收敛。"""
import random
import sys

sys.path.insert(0, ".")

import sqlfmt  # noqa: E402
from tests.fixtures.sql_cases import SQL_CASES  # noqa: E402
from tests.sqlfmt_test_helpers import scramble_whitespace  # noqa: E402

bad = []
for case in SQL_CASES:
    canonical = case.expected_sql.strip("\n")
    flat = scramble_whitespace(canonical, random.Random(0), separators=(" ",))
    got = sqlfmt.sqlfilefmt(flat, **case.options).strip("\n")
    if got != canonical:
        bad.append(case.name)

print(f"总用例 {len(SQL_CASES)}，压成单空格后不收敛: {len(bad)}")
for n in bad:
    print("   -", n)

print("\n首个不收敛样例细节：")
if bad:
    case = next(c for c in SQL_CASES if c.name == bad[0])
    canonical = case.expected_sql.strip("\n")
    flat = scramble_whitespace(canonical, random.Random(0), separators=(" ",))
    got = sqlfmt.sqlfilefmt(flat, **case.options).strip("\n")
    print("=" * 70)
    print(f"[{case.name}]")
    print("--- 压平输入 ---")
    print(flat)
    print("--- 实际输出 ---")
    print(got)
    print("--- 期望 ---")
    print(canonical)
