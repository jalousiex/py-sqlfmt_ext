"""格式化策略：换行锚点关键字与方言分词补丁。

这里只放「本项目自己的格式化口径」和「官方分词表缺失的补丁」，
不复制官方数据表——官方关键字仍由 ``sqlparse.keywords`` 提供。

分词补丁的取舍
--------------
官方 0.6.0 的分词表与本项目历史输出存在少数差异，逐条列在此处以保证输出稳定：

* ``LATERAL VIEW <UDTF>`` 合并为单个 Keyword（多词关键字，避免被拆成两行）；
* Doris/SelectDB 的模型定义关键字（官方没有，按 MySQL 兼容适配）。

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
    "SET",
    "BETWEEN",
    "EXCEPT",
    "COMMENT",
    "ROLLUP",
    "PROPERTIES",
    r"BUILD\s+(IMMEDIATE|DEFERRED)\b",
    r"\bREFRESH\b",
    r"\bON\s+(MANUAL|SCHEDULE|COMMIT)\b",
    r"(DUPLICATE|UNIQUE|AGGREGATE)\b",
    r"(AUTO\s+)?PARTITION\s+BY\b",
    r"DISTRIBUTED\s+BY\b",
    r"\bON",
    r"LATERAL\s+VIEW",
)

# --- 分词补丁 ---------------------------------------------------------------

# 需要先于官方「通用单词」规则生效的多词关键字。
MULTIWORD_REGEX = (
    (r"(LATERAL\s+VIEW\s+)(EXPLODE|INLINE|PARSE_URL_TUPLE|POSEXPLODE|STACK)\b", T.Keyword),
    (r"BUILD\s+(IMMEDIATE|DEFERRED)\b", T.Keyword),
    (r"\bREFRESH\b", T.Keyword),
    (r"\bON\s+(MANUAL|SCHEDULE|COMMIT)\b", T.Keyword),
    (r"(DUPLICATE|UNIQUE|AGGREGATE)\b", T.Keyword),
    (r"(AUTO\s+)?PARTITION\s+BY\b", T.Keyword),
    (r"DISTRIBUTED\s+BY\b", T.Keyword),
)

# Doris/SelectDB 词表：官方没有，按 MySQL 兼容适配
KEYWORDS_DORIS = {
    "BUCKETS": T.Keyword,
    "AUTO": T.Keyword,
    "PROPERTIES": T.Keyword,
}

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
