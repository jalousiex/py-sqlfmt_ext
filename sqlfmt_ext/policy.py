"""格式化策略：换行锚点关键字与方言分词补丁。

这里只放「本项目自己的格式化口径」和「官方分词表缺失的补丁」，
不复制官方数据表——官方关键字仍由 ``sqlparse.keywords`` 提供。

分词补丁的取舍
--------------
官方 0.6.0 的分词表与本项目历史输出存在少数差异，逐条列在此处以保证输出稳定：

* ``LATERAL VIEW <UDTF>`` 合并为单个 Keyword（多词关键字，避免被拆成两行）；
* Doris/SelectDB 的模型定义关键字与类型名 → 已收进 `dialects.py`（``Dialect.extra_keywords``），
  本模块不再持有方言词；
* ``OVER (`` 判回 Keyword（官方词表里有 ``OVER``，但被更靠前的「函数名」正则
  ``[A-ZÀ-Ü]\\w*(?=\\()`` 抢先判成 ``Name``，导致 ``sql.Over`` 永远分不出来）。
* **字符串字面量里的转义反斜杠**（反斜杠 + 反斜杠）→ 官方字符串正则只认「反斜杠 + 引号」
  这一支转义，不认「反斜杠 + 反斜杠」，于是含两个反斜杠的字符串**不闭合**，把后面的
  整段 SQL 吞进同一个字符串 token（见 ``STRING_ESCAPE_REGEX``）。

每条都写成「追加/前置」，不改写官方已有条目。
"""

import re

from sqlparse import tokens as T

# ``/*-*/`` 的专用 ttype 别名。官方没有 ``ForceNewline``，但 TokenType 支持动态
# 派生子类型，这里派生一个别名供本项目使用（不修改官方 tokens 模块）。
FORCE_NEWLINE = T.Comment.Multiline.ForceNewline

# --- 换行锚点关键字 ---------------------------------------------------------

_join_words = (
    r"((LEFT\s+|RIGHT\s+|FULL\s+)?"
    r"(INNER\s+|OUTER\s+|STRAIGHT\s+)?|"
    r"(CROSS\s+|NATURAL\s+)?)?JOIN\b|"
    r"UNION\s+ALL\b"
)

join_words = _join_words
by_words = r"(GROUP|ORDER)\s+BY\b"

# 命中即在关键字前换行；匹配到多词关键字时只取首个单词参与对齐宽度。
# 这里只放**通用**词：方言专属词（Doris 的 `DISTRIBUTED BY` / `PROPERTIES` 等）在
# ``dialects.py`` 里声明，由 ``LayoutPass`` 运行时合并进来（见 `.claude/plan/stages.md` §9.9）。
split_words = (
    "FROM",
    _join_words,
    by_words,
    "WHERE",
    "AND",
    r"\bOR",
    "HAVING",
    "LIMIT",
    "UNION",
    "VALUES",
    # 词边界必须显式写：``Token.match`` 对每条锚点做 ``re.search``（非整词），
    # 裸 ``SET`` 会在 ``OFFSET`` / ``CHARSET`` 内部命中 → 关键字被误判成子句头、
    # 换行落到 ``offset`` 之前（``limit 20⏎offset 10``）。``INSERT … SET`` 是独立词，
    # 加了边界仍照常换行。
    r"\bSET\b",
    "BETWEEN",
    "EXCEPT",
    "COMMENT",
    "ROLLUP",
    r"\bON\s+COMMIT\b",
    # 后缀词边界必须写：`\bON` 只约束了前缀，会在 `ONLY` / `ONLINE` 内部命中
    # （两者官方都判成 `T.Keyword`）→ 它们被当成子句头独占了整行。
    # `ON COMMIT` / `ON MANUAL` / `ON SCHEDULE` 是多词 token，`\bON\b` 照样命中。
    r"\bON\b",
    r"LATERAL\s+VIEW",
)

# --- 分词补丁 ---------------------------------------------------------------

# 需要先于官方「通用单词」规则生效的多词关键字。
MULTIWORD_REGEX = (
    (r"(LATERAL\s+VIEW\s+)(EXPLODE|INLINE|PARSE_URL_TUPLE|POSEXPLODE|STACK)\b", T.Keyword),
    # UDTF 不在上面白名单时的兜底：``LATERAL VIEW`` 至少要并成一个 Keyword。
    # 否则 ``lateral`` 与 ``view`` 各自成词，split_words 里的 ``LATERAL\s+VIEW``
    # 对两个单词 token 都匹配不上（match 是拿整条正则去 search 单个 token 的
    # normalized），多个 lateral view 就全被挤在 ``from`` 同一行。
    (r"(LATERAL\s+VIEW)\b", T.Keyword),
    (r"BUILD\s+(IMMEDIATE|DEFERRED)\b", T.Keyword),
    (r"\bREFRESH\b", T.Keyword),
    (r"\bON\s+(MANUAL|SCHEDULE|COMMIT)\b", T.Keyword),
    (r"(DUPLICATE|UNIQUE|AGGREGATE)\b", T.Keyword),
    (r"(AUTO\s+)?PARTITION\s+BY\b", T.Keyword),
    (r"DISTRIBUTED\s+BY\b", T.Keyword),
)

# 需要早于官方「函数名」正则（``[A-ZÀ-Ü]\w*(?=\()`` → Name）生效的补丁。
# 官方词表里本就有 ``'OVER': tokens.Keyword``，但 ``over(`` 会被函数名正则先截走，
# 于是 ``sql.Over.M_OPEN`` 永远匹配不上，``over (...)`` 退化成普通 ``Function``，
# 后续对齐取错偏移。这里把它判回 Keyword。
PRECEDENCE_REGEX = (
    (r"OVER\b(?=\s*\()", T.Keyword),
)

# 官方「函数名」正则之前的锚点
PRECEDENCE_ANCHORS = (r"(?<=\.)[A-ZÀ-Ü]\w*",)

# --- 字符串字面量里的转义反斜杠（S19 / U17）------------------------------------
#
# 官方字符串正则只认「反斜杠 + 引号」这一支转义，**不认**「反斜杠 + 反斜杠」。
# 于是一个含两个反斜杠的字符串字面量（MySQL / Doris 里写两个反斜杠 = 一个反斜杠）
# **不闭合**：第 2 个反斜杠正好与紧随其后的引号配成「反斜杠 + 引号」，字符串一路
# 吞到下一个引号，中间整段 SQL（字段列表、case when、from …）全被并进**同一个**
# ``T.Literal.String.Single`` token。
#
# 这不是排版问题，是**分词**问题：分组与布局看到的输入已经残缺（症状却表现为
# 「列对齐错乱」，见技能的元规则一）。
# 下面两条规则把「反斜杠 + 任意字符」当成一个转义单元，于是两个反斜杠被整体吃掉，
# 字符串在**正确位置**闭合。与官方正则相比，只在「反斜杠后面不是引号」时有差别；
# 其余（双写单引号、反斜杠转义引号、结尾单个反斜杠）经回溯后与官方**完全一致**。
#
# 与方言无关（所有方言都打，含 ``dialect=None``）：这是**上游缺陷的修正**而非方言
# 特性 —— 让 generic 基线继续保留「吞掉整段 SQL」的行为没有价值。
STRING_ESCAPE_REGEX = (
    (r"'(''|\\.|[^'])*'", T.Literal.String.Single),
    (r'"(""|\\.|[^"])*"', T.Literal.String.Symbol),
)

# 官方两条字符串规则的 pattern：用作插入锚点（本项目的规则插到它们**之前**）
STRING_ANCHORS = (
    r"'(''|\\'|[^'])*'",
    r'"(""|\\"|[^"])*"',
)

# 方言关键字与类型名（Doris 的 ``BUCKETS`` / ``PROPERTIES`` / ``INT64`` / ``DATEV2`` …）
# **不在这里** —— 它们已收进 `dialects.py` 的方言声明（``Dialect.extra_keywords``）。
# 本模块只保留**通用**词表与分词口径，见 `.claude/plan/stages.md` §9.10。

# 官方多词关键字区块的定位锚点（依次尝试，取第一个命中的）
ANCHOR_PATTERNS = (
    r"CREATE(\s+OR\s+REPLACE)?\b",
    r"IF\s+NOT\s+EXISTS\b",
    r"(NOT\s+)?NULL\b",
)


def compiled(entries):
    """(pattern, ttype) → Lexer 需要的 (matcher, ttype)。

    使用与官方 ``Lexer.set_SQL_REGEX`` 一致的编译选项。
    """
    flags = re.IGNORECASE | re.UNICODE
    return [(re.compile(pattern, flags).match, ttype) for pattern, ttype in entries]


def pattern_of(matcher):
    """从 ``re.compile(...).match`` 取回原始 pattern 字符串。"""
    pattern = getattr(matcher, "__self__", None)
    return getattr(pattern, "pattern", None)
