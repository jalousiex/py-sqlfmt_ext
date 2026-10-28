"""分词层验收：字符串字面量里的「反斜杠 + 反斜杠」必须在正确位置闭合。

背景（U17 / S19，见 `.claude/plan/diffs.md` §3.4 与 `.claude/plan/stages.md` §9.23）：
官方 0.6.0 的字符串正则是「单引号 + 双写单引号 / 反斜杠加引号 / 非引号」三选一 ——
它把「反斜杠 + 引号」当转义，**却没有「反斜杠 + 反斜杠」这一支**。于是 MySQL / Doris
里表示「一个反斜杠」的双反斜杠字面量里，第 2 个反斜杠正好与紧随的引号配成
「反斜杠 + 引号」，字符串**不闭合**，一路吞到下一个引号 —— 中间整段 SQL
（字段列表、case when、from …）全被并进**同一个**字符串 token。
症状却表现为「列对齐错乱」，属下游表象（见技能的元规则一）。

本文件钉的是**根因**（token 边界）；端到端行为由 ``cases/escape/`` 两个 fixture
（输出回归 + 收敛 + 幂等）覆盖。
"""

from sqlfmt_ext.lexer import build_lexer


def _string_tokens(sql, dialect="doris"):
    """取出所有字符串类 token 的取值（跳过空白）。"""
    return [
        value
        for ttype, value in build_lexer(dialect).get_tokens(sql)
        if value.strip() and "String" in str(ttype)
    ]


def test_escaped_backslash_string_is_not_swallowed():
    """核心回归：双反斜杠字面量不再把后面的 SQL 吞进字符串 token。"""
    sql = r"select concat(a, '\\', b) as joined, c from t"
    assert _string_tokens(sql) == [r"'\\'"]


def test_escaped_backslash_in_the_middle_of_string():
    """字符串中间的双反斜杠同样不吞后面的内容。"""
    sql = r"select 'x\\y' as v, c from t"
    assert _string_tokens(sql) == [r"'x\\y'"]


def test_doubled_quote_and_escaped_quote_still_work():
    """官方已支持的两种转义不受影响（回溯后取值与官方一致）。"""
    assert _string_tokens("select 'a''b' from t") == ["'a''b'"]
    assert _string_tokens(r"select 'a\'b' from t") == [r"'a\'b'"]


def test_double_quoted_symbol_closes_at_escaped_backslash():
    """双引号侧同机理：官方正则同样缺「反斜杠 + 反斜杠」这一支。"""
    assert _string_tokens(r'select "a\\" as v, c from t') == [r'"a\\"']


def test_generic_dialect_also_fixes_the_escape():
    """这条补丁与方言无关（上游缺陷修正），``dialect=None`` 同样生效。"""
    sql = r"select concat(a, '\\', b) as joined, c from t"
    assert _string_tokens(sql, dialect=None) == [r"'\\'"]
