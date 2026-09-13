"""方言层：Doris/SelectDB 优先（官方缺失时按 MySQL 兼容适配），预留 SQL Server。

原则
----
- 只用「追加声明」的方式扩展：往官方分词表追加多词 token 规则、往本项目的换行锚点表
  追加关键字；不改写官方已有条目。
- ``dialect=None`` 时**不追加任何东西**，与官方基线可比。
- **本模块是方言的唯一真身**：分词层（``lexer``）与布局层（``passes/layout``）都到这里取
  声明，不再各自硬编码白名单（2026-09-13 起，见 `PLAN §9.9`）。
"""

from dataclasses import dataclass

from sqlparse import tokens as T


@dataclass(frozen=True)
class Dialect:
    """一个方言的全部声明（声明式，消费方各自取需要的那一项）。"""

    name: str
    # 是否应用 ``policy.MULTIWORD_REGEX``（多词关键字合并，Doris 系那套）
    multiword_patches: bool = False
    # 是否应用 ``policy.PRECEDENCE_REGEX``（``OVER (`` 这类**通用**优先级补丁）
    precedence_patches: bool = False
    # **只对本方言生效**的优先级规则：``((pattern, ttype), ...)``，插到官方分词表最前
    extra_lexer_rules: tuple = ()
    # 追加到官方分词词表的条目：``((word, ttype), ...)``（关键字与类型名都走这里）
    extra_keywords: tuple = ()
    # 追加到 ``LayoutPass.split_words`` 的换行锚点词（只影响换行，不影响分词）
    extra_split_words: tuple = ()
    # 批分隔符（SQL Server 的 ``GO``）：**独占一个 token** 时把输入切成多批。
    # 空串 = 该方言没有批分隔符概念（只按 ``;`` 切分）。输出恒用这里的字面量。
    batch_separator: str = ""
    notes: str = ""


# --- Doris / SelectDB -------------------------------------------------------

# 分词层词表补丁（官方 0.6.0 缺失，按 MySQL 兼容适配）：
#
# * 建表模型定义关键字：``BUCKETS`` / ``AUTO`` / ``PROPERTIES``；
# * **数据类型名** —— 这条必须补：官方是**整词匹配**，而 Doris 的类型名（``INT64`` /
#   ``DATEV2`` / ``DATETIMEV2`` / ``DECIMALV3`` / ``LARGEINT`` / ``BITMAP`` …）都不在官方
#   词表里，于是落成普通 ``Name``，被 ``group_identifier`` 与字段名**粘成一个 ``Identifier``**，
#   ``_create_field_lines`` 的类型列取不到 token → DDL 字段对齐的**列基准全错**
#   （U16 记的就是这个机理，当时只补了 ``DATETIME`` 一个词；S8-b 一次性补齐同类）。
#   旧 fork 之所以没暴露：它的关键字正则不要求词尾边界，``DATE`` / ``INT`` 会把
#   ``DATETIME`` / ``INT64`` 前缀命中。
_DORIS_MODEL_KEYWORDS = ("BUCKETS", "AUTO", "PROPERTIES")

_DORIS_TYPE_NAMES = (
    "AGG_STATE",
    "BITMAP",
    "DATETIME",
    "DATEV2",
    "DATETIMEV2",
    "DECIMALV2",
    "DECIMALV3",
    "DOUBLE",
    "HLL",
    "INT16",
    "INT32",
    "INT64",
    "INT128",
    "IPV4",
    "IPV6",
    "JSONB",
    "LARGEINT",
    "QUANTILE_STATE",
    "STRUCT",
    "VARIANT",
)

_DORIS_EXTRA_KEYWORDS = tuple((w, T.Keyword) for w in _DORIS_MODEL_KEYWORDS) + tuple(
    (w, T.Name.Builtin) for w in _DORIS_TYPE_NAMES
)

# 官方词表与换行锚点都缺这些「建表模型定义」关键字，按 MySQL 兼容适配。
# 这里只声明需要参与换行的整段关键字；多词合并仍由 ``policy`` 的分词补丁负责
# （词没被合并成一个 token 时不必列在这里 —— 单 token 的正则匹配不上多词）。
_DORIS_SPLIT_WORDS = (
    "PROPERTIES",
    r"BUILD\s+(IMMEDIATE|DEFERRED)\b",
    r"\bREFRESH\b",
    r"\bON\s+(MANUAL|SCHEDULE)\b",
    r"(DUPLICATE|UNIQUE|AGGREGATE)\b",
    r"(AUTO\s+)?PARTITION\s+BY\b",
    r"DISTRIBUTED\s+BY\b",
)

_DORIS = Dialect(
    name="doris",
    multiword_patches=True,
    precedence_patches=True,
    extra_keywords=_DORIS_EXTRA_KEYWORDS,
    extra_split_words=_DORIS_SPLIT_WORDS,
    notes="SelectDB 同族；官方缺失，按 MySQL 兼容适配",
)

# --- SQL Server -------------------------------------------------------------

# ``WITH (NOLOCK)`` 的表提示必须让 ``WITH`` **不是** ``Keyword.CTE``：官方词表里 ``WITH`` 落
# ``Keyword.CTE``，而 ``LayoutPass._split_statements`` 认 ``T.CTE``，于是 ``t with (nolock)``
# 里的 ``with`` 被换行成独占一行；同义的 ``with(nolock)``（``(`` 紧贴）却先被官方「函数名」
# 正则截成 ``Name``，仍旧粘在表名后 —— **同一语义两种写法两种输出**。
# 这条优先级规则把「``WITH`` 紧跟 ``(``」判回普通 ``Keyword``：CTE 的形状是
# ``WITH <名字> AS (``，``(`` 不会紧跟 ``WITH``，因此不受影响（实测 ``with cte as (…)`` 无变化）。
_SQLSERVER_EXTRA_LEXER_RULES = ((r"WITH\b(?=\s*\()", T.Keyword),)

# ``TOP`` / ``PERCENT`` 官方词表里都没有（落 ``T.Name``）→ 官方 ``KeywordCaseFilter`` 也不会
# 碰它们。声明成关键字有两个作用：
#   1. 大小写交给官方 pass 统一决定（``keyword_case`` 生效），分组层合成的 ``TOP <n>``
#      不再保留输入大小写（``TOP 10`` 与 ``top 10`` 输出一致）；
#   2. 合并步骤以「``TOP`` 是不是 ``T.Keyword``」为闸 —— 只有声明过 TOP 的方言才会把
#      ``TOP <n> [PERCENT]`` 合成一个 token，其余方言（含 ``dialect=None`` 官方基线）行为不变。
_SQLSERVER_EXTRA_KEYWORDS = (("TOP", T.Keyword), ("PERCENT", T.Keyword))

DIALECTS = {
    None: Dialect(name="generic", notes="不追加任何东西，与官方基线可比"),
    "mysql": Dialect(name="mysql", notes="预留：目前与通用路径一致"),
    "doris": _DORIS,
    "selectdb": Dialect(
        name="selectdb",
        multiword_patches=True,
        precedence_patches=True,
        extra_keywords=_DORIS_EXTRA_KEYWORDS,
        extra_split_words=_DORIS_SPLIT_WORDS,
        notes="与 doris 同族，共用声明",
    ),
    # 只要「优先级补丁」（``over (``），**不要** Doris 的多词合并（``PARTITION BY`` /
    # ``DISTRIBUTED BY`` 那套是 Doris 语义，套到 T-SQL 上会改变 token 边界）。
    # ``[ ]`` 标识符官方本就支持，无需声明。
    "sqlserver": Dialect(
        name="sqlserver",
        precedence_patches=True,
        extra_lexer_rules=_SQLSERVER_EXTRA_LEXER_RULES,
        extra_keywords=_SQLSERVER_EXTRA_KEYWORDS,
        batch_separator="GO",
        notes="GO 批分隔符 / TOP / WITH(NOLOCK)；[ ] 标识符官方已支持",
    ),
}


def get_dialect(name):
    """按名字取方言声明；未知方言抛 ``KeyError``（由选项层转成 ``SQLParseError``）。"""
    if name not in DIALECTS:
        raise KeyError(name)
    return DIALECTS[name]


def available():
    """可用方言名（``None`` 用 ``generic`` 表示），用于错误信息。"""
    return sorted("generic" if k is None else k for k in DIALECTS)


def split_words_for(name):
    """该方言追加的换行锚点词（供 ``LayoutPass`` 使用）。"""
    return tuple(get_dialect(name).extra_split_words)


def batch_separator_for(name):
    """该方言的批分隔符（``""`` = 没有这个概念，供 ``stack.format_statements`` 使用）。"""
    return get_dialect(name).batch_separator


def all_split_words():
    """**所有**方言声明的换行锚点词的并集（按声明序去重）。

    分组补偿层判「这是不是子句关键字」时用（``grouping._is_clause_keyword``）—— 该判断
    与当前方言无关：无论跑哪种方言，``DISTRIBUTED BY`` 都是子句头，不该被
    ``_wrap_create_table_calls`` 当成函数调用包起来。若这里只看当前方言，换方言就会让
    同一段 SQL 的分组形状跟着变（实测：``PROPERTIES`` 漏在并集外时，
    ``properties (1)`` 被误包成 ``Function``，换行随之消失）。
    """
    words = []
    for dialect in DIALECTS.values():
        for word in dialect.extra_split_words:
            if word not in words:
                words.append(word)
    return tuple(words)
