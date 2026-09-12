"""诊断：官方 strip 语义下，canonical 与打乱输入的 strip 结果是否一致。"""
import random
import sys

sys.path.insert(0, ".")

import sqlparse  # noqa: E402
from sqlparse.filters import others  # noqa: E402
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


def stripped(text):
    others.StripWhitespaceFilter._stripws_default = staticmethod(official_stripws_default)
    out = sqlparse.format(text, strip_whitespace=True)
    others.StripWhitespaceFilter._stripws_default = staticmethod(local_stripws_default)
    return out


NAMES = ["dml/sqltest1_s01", "aggregate/sqltest5_s01", "window/sqltest6_s02"]

for name in NAMES:
    case = next(c for c in SQL_CASES if c.name == name)
    canonical = case.expected_sql.strip("\n")
    base = stripped(canonical)
    for seed in (0, 1):
        variant = scramble_whitespace(canonical, random.Random(f"{name}:{seed}"))
        got = stripped(variant)
        same = got == base
        print("=" * 70)
        print(f"[{name}] seed={seed}  strip 结果一致: {same}")
        if not same:
            print("--- canonical strip ---")
            print(repr(base[:400]))
            print("--- variant strip ---")
            print(repr(got[:400]))
