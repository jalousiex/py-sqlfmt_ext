"""迁移对拍诊断：新外挂层（官方 filter + 本项目 pass）对 fixture 的复现度。"""

import os
import re
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.normcase(os.path.abspath(p or os.getcwd())) != os.path.normcase(_ROOT)]
sys.path.append(_ROOT)

import sqlparse  # noqa: E402

assert "site-packages" in sqlparse.__file__, sqlparse.__file__

from tests.fixtures.sql_cases import SQL_CASES, normalize_sql  # noqa: E402
from sqlfmt_ext import format_statements  # noqa: E402


def skeleton(text):
    """保留换行与 token 顺序，去掉缩进/对齐空白与标点前对齐空格。"""
    out = []
    for line in text.splitlines():
        line = " ".join(line.split())
        line = re.sub(r"\s+([,;)\]])", r"\1", line)
        out.append(line)
    return out


exact, skeleton_only, layout_diff = [], [], []
for case in SQL_CASES:
    expected = normalize_sql(case.expected_sql)
    got = normalize_sql(format_statements(case.input_sql, case.options))
    if got == expected:
        exact.append(case.name)
    elif skeleton(got) == skeleton(expected):
        skeleton_only.append(case.name)
    else:
        layout_diff.append(case.name)

print(f"官方 sqlparse: {sqlparse.__version__} ({sqlparse.__file__})")
print(f"总用例 {len(SQL_CASES)}")
print(f"\n[A] 逐字节一致          {len(exact)}/{len(SQL_CASES)}")
print(f"[B] 仅空白宽度不同      {len(skeleton_only)}/{len(SQL_CASES)}")
print(f"[C] 换行骨架不同        {len(layout_diff)}/{len(SQL_CASES)}")

print("\n--- [B] 仅空白宽度差异 ---")
for name in skeleton_only:
    print("   ", name)
print("\n--- [C] 换行骨架差异（首处差异）---")
by_name = {case.name: case for case in SQL_CASES}
for name in layout_diff:
    case = by_name[name]
    expected = skeleton(normalize_sql(case.expected_sql))
    got = skeleton(normalize_sql(format_statements(case.input_sql, case.options)))
    print("=" * 60)
    print(f"[{name}] 行数 期望{len(expected)} vs 新{len(got)}")
    for i in range(max(len(expected), len(got))):
        a = expected[i] if i < len(expected) else "<无>"
        b = got[i] if i < len(got) else "<无>"
        if a != b:
            print(f"  第{i}行 期望: {a}")
            print(f"  第{i}行 新  : {b}")
            break
