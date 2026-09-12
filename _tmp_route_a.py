"""路线 A 影响面测量：把 StripWhitespaceFilter 切回官方「折叠换行」语义后的效果。"""
import random
import sys

sys.path.insert(0, ".")

import sqlfmt  # noqa: E402
from sqlparse.filters import others  # noqa: E402
from sqlparse import sql  # noqa: E402
from sqlparse import tokens as T  # noqa: E402
from tests.fixtures.sql_cases import SQL_CASES  # noqa: E402
from tests.sqlfmt_test_helpers import scramble_whitespace  # noqa: E402


def official_stripws_default(tlist):
    last_was_ws = False
    is_first_char = True
    for token in tlist.tokens:
        if token.is_whitespace:
            token.value = "" if last_was_ws or is_first_char else " "
        last_was_ws = token.is_whitespace
        is_first_char = False


local_stripws_default = others.StripWhitespaceFilter._stripws_default


def fmt(sql, options):
    return sqlfmt.sqlfilefmt(sql, **options).strip("\n")


SEEDS = (0, 1, 2)

# 1) 当前实现：canonical 是否幂等
# 2) 切官方 strip：canonical 输出是否不变
# 3) 切官方 strip：打乱输入是否收敛
current_bad, official_bad = [], []
scramble_bad_official, scramble_bad_local = [], []

for case in SQL_CASES:
    canonical = case.expected_sql.strip("\n")
    options = case.options

    others.StripWhitespaceFilter._stripws_default = staticmethod(local_stripws_default)
    cur = fmt(case.input_sql, options)
    if cur != canonical:
        current_bad.append(case.name)

    others.StripWhitespaceFilter._stripws_default = staticmethod(official_stripws_default)
    off = fmt(case.input_sql, options)
    if off != canonical:
        official_bad.append(case.name)

    b_local = b_official = None
    for seed in SEEDS:
        variant = scramble_whitespace(canonical, random.Random(f"{case.name}:{seed}"))
        if variant == canonical:
            continue
        others.StripWhitespaceFilter._stripws_default = staticmethod(official_stripws_default)
        if fmt(variant, options) != canonical and b_official is None:
            b_official = (seed, variant)
        others.StripWhitespaceFilter._stripws_default = staticmethod(local_stripws_default)
        if fmt(variant, options) != canonical and b_local is None:
            b_local = (seed, variant)
    if b_official:
        scramble_bad_official.append((case.name, b_official[0]))
    if b_local:
        scramble_bad_local.append((case.name, b_local[0]))

others.StripWhitespaceFilter._stripws_default = staticmethod(local_stripws_default)

print(f"总用例: {len(SQL_CASES)}")
print(f"\n[1] 当前实现 canonical 不幂等/不匹配: {len(current_bad)}")
for n in current_bad:
    print("   -", n)

print(f"\n[2] 切官方 strip 后 canonical 输出变化: {len(official_bad)}")
for n in official_bad:
    print("   -", n)

print(f"\n[3] 打乱后不收敛（官方 strip）: {len(scramble_bad_official)}")
for n, s in scramble_bad_official:
    print(f"   - {n} (seed={s})")

print(f"\n[4] 打乱后不收敛（当前 strip）: {len(scramble_bad_local)}")
for n, s in scramble_bad_local:
    print(f"   - {n} (seed={s})")

print("\n[5] 官方 strip 下打乱不收敛的首个样例：")
for n, s in scramble_bad_official[:3]:
    case = next(c for c in SQL_CASES if c.name == n)
    canonical = case.expected_sql.strip("\n")
    variant = scramble_whitespace(canonical, random.Random(f"{n}:{s}"))
    others.StripWhitespaceFilter._stripws_default = staticmethod(official_stripws_default)
    got = fmt(variant, case.options)
    others.StripWhitespaceFilter._stripws_default = staticmethod(local_stripws_default)
    print("=" * 70)
    print(f"[{n}] seed={s}")
    print("--- 打乱输入 ---")
    print(variant)
    print("--- 实际输出 ---")
    print(got)
