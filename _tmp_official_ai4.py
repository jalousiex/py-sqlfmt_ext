"""度量（行级）：官方对齐路径与本地期望，换行位置是否一致（忽略缩进/空白宽度）。"""
import re
import sys

sys.path.insert(0, ".")

from sqlparse import filters  # noqa: E402
from sqlparse.filters import others  # noqa: E402
from sqlparse.filters.aligned_indent import AlignedIndentFilter as OfficialAI  # noqa: E402

from tests.fixtures.sql_cases import SQL_CASES  # noqa: E402
import sqlfmt  # noqa: E402


class OfficialAdapter(OfficialAI):
    def __init__(self, char=" ", align_list=False, comma_first=False, **kwargs):
        super().__init__(char=char, **kwargs)


def official_stripws_default(tlist):
    last_was_ws = False
    is_first_char = True
    for token in tlist.tokens:
        if token.is_whitespace:
            token.value = "" if last_was_ws or is_first_char else " "
        last_was_ws = token.is_whitespace
        is_first_char = False


LOCAL_AI = filters.AlignedIndentFilter
LOCAL_STRIP = others.StripWhitespaceFilter._stripws_default


def fmt(sql, options):
    return sqlfmt.sqlfilefmt(sql, **options).strip("\n")


def indent_only(text):
    """保留换行与 token 顺序，去掉缩进/对齐空白与「标点前对齐空格」。"""
    out = []
    for line in text.splitlines():
        line = " ".join(line.split())
        line = re.sub(r"\s+([,;)\]])", r"\1", line)
        out.append(line)
    return out


exact, indent_only_diff, line_diff = [], [], []

filters.AlignedIndentFilter = OfficialAdapter
others.StripWhitespaceFilter._stripws_default = staticmethod(official_stripws_default)
try:
    for case in SQL_CASES:
        canonical = case.expected_sql.strip("\n")
        got = fmt(case.input_sql, case.options)
        if got == canonical:
            exact.append(case.name)
        elif indent_only(got) == indent_only(canonical):
            indent_only_diff.append(case.name)
        else:
            line_diff.append(case.name)
finally:
    others.StripWhitespaceFilter._stripws_default = staticmethod(LOCAL_STRIP)
    filters.AlignedIndentFilter = LOCAL_AI

print(f"总用例 {len(SQL_CASES)}")
print(f"[A] 完全一致                    {len(exact)}: {exact}")
print(f"[B] 换行位置一致，仅缩进/宽度   {len(indent_only_diff)}: {indent_only_diff}")
print(f"[C] 换行位置不同                {len(line_diff)}: {line_diff}")
print("\n[C] 明细：")
for name in line_diff:
    case = next(c for c in SQL_CASES if c.name == name)
    canonical = case.expected_sql.strip("\n")
    filters.AlignedIndentFilter = OfficialAdapter
    others.StripWhitespaceFilter._stripws_default = staticmethod(official_stripws_default)
    got = fmt(case.input_sql, case.options)
    others.StripWhitespaceFilter._stripws_default = staticmethod(LOCAL_STRIP)
    filters.AlignedIndentFilter = LOCAL_AI
    a, b = indent_only(canonical), indent_only(got)
    print("=" * 70)
    print(f"[{name}]  行数 {len(a)} vs {len(b)}")
    for i in range(max(len(a), len(b))):
        x = a[i] if i < len(a) else "<无>"
        y = b[i] if i < len(b) else "<无>"
        if x != y:
            print(f"   第 {i} 行:")
            print(f"     期望: {x}")
            print(f"     官方: {y}")
            break
