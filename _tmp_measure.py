"""收敛性度量：canonical 幂等 + 打乱后是否收敛回 canonical。"""
import random
import sys

sys.path.insert(0, ".")

import sqlfmt  # noqa: E402
import sqlparse  # noqa: E402
from tests.fixtures.sql_cases import SQL_CASES  # noqa: E402
from tests.sqlfmt_test_helpers import scramble_whitespace  # noqa: E402

SEEDS = (0, 1, 2)
CANON_ONLY = "--canon-only" in sys.argv

bad_canon, bad_scramble = [], []


def fmt(sql, options):
    return sqlfmt.sqlfilefmt(sql, **options).strip("\n")


for case in SQL_CASES:
    canonical = case.expected_sql.strip("\n")
    if fmt(case.input_sql, case.options) != canonical:
        bad_canon.append(case.name)
    if CANON_ONLY:
        continue
    for seed in SEEDS:
        variant = scramble_whitespace(canonical, random.Random(f"{case.name}:{seed}"))
        if variant == canonical:
            continue
        if fmt(variant, case.options) != canonical:
            bad_scramble.append((case.name, seed))
            break

print(f"总用例 {len(SQL_CASES)}")
print(f"[canonical 不匹配] {len(bad_canon)}: {bad_canon}")
if not CANON_ONLY:
    print(f"[打乱不收敛] {len(bad_scramble)}")
    for n, s in bad_scramble:
        print(f"   - {n} (seed={s})")
