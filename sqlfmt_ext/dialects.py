"""方言层：Doris/SelectDB 优先（官方缺失时按 MySQL 兼容适配），预留 SQL Server。

原则
----
- 只用「追加声明」的方式扩展：往官方 ``sqlparse.keywords.SQL_REGEX`` 追加多词
  token 规则、往 ``AlignedIndentFilter`` 的关键字集合追加换行关键字。
- 不改写官方已有条目，卸载后行为与官方完全一致。
- ``dialect=None``（默认）不注册任何东西，保证与官方对齐的基线可比。
"""

from dataclasses import dataclass

from sqlparse import keywords as _upstream_keywords


@dataclass(frozen=True)
class Dialect:
    name: str
    extra_regex: tuple = ()  # ((regex, ttype), ...) 追加到 SQL_REGEX 顶部
    extra_split_words: tuple = ()  # 追加到 AlignedIndentFilter.split_words
    extra_join_words: tuple = ()
    extra_by_words: tuple = ()
    notes: str = ""


# Doris/SelectDB 的分区、分布、模型定义关键字：官方没有，按 MySQL 兼容适配。
# 只声明「需要参与换行的整段关键字」，具体多词合并依赖官方 SQL_REGEX 已合并的 token。
_DORIS_SPLIT_WORDS = (
    r"DISTRIBUTED\s+BY",
    r"DUPLICATE\s+KEY",
    r"AGGREGATE\s+KEY",
    r"UNIQUE\s+KEY",
    r"PARTITION\s+BY",
    r"PROPERTIES",
)

_DORIS = Dialect(
    name="doris",
    extra_split_words=_DORIS_SPLIT_WORDS,
    notes="SelectDB 同族；官方缺失，按 MySQL 兼容适配",
)

DIALECTS = {
    None: Dialect(name="generic"),
    "mysql": Dialect(name="mysql"),
    "doris": _DORIS,
    "selectdb": Dialect(
        name="selectdb",
        extra_split_words=_DORIS.extra_split_words,
        notes="与 doris 同族，共用关键字声明",
    ),
    "sqlserver": Dialect(
        name="sqlserver",
        notes="待适配：GO 批处理分隔符、[ ] 标识符、TOP、WITH(NOLOCK) 等",
    ),
}

# 已注册的 (dialect_name, regex) 组合，避免重复注入
_APPLIED = set()


def get_dialect(name):
    if name not in DIALECTS:
        raise KeyError(f"未知方言：{name!r}，可选：{sorted(k for k in DIALECTS if k)}")
    return DIALECTS[name]


def apply_dialect(name):
    """把方言声明注入官方分词表（幂等）。返回对应的 Dialect。"""
    dialect = get_dialect(name)
    regex_entries = list(dialect.extra_regex)
    if regex_entries:
        for entry in regex_entries:
            if (dialect.name, entry) in _APPLIED:
                continue
            # 追加到顶部，让多词关键字先于单关键字被合并
            _upstream_keywords.SQL_REGEX.insert(0, entry)
            _APPLIED.add((dialect.name, entry))
    return dialect


def split_words_for(name):
    """返回该方言追加的 split_words（供 AlignedIndentFilter 子类使用）。"""
    return tuple(get_dialect(name).extra_split_words)
