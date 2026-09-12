import os
import random

import sqlfmt
from sqlparse import lexer
from sqlparse import tokens as T

from tests.fixtures.sql_cases import SQL_CASES, normalize_sql

# 打乱后用作 token 间隔的空白候选（含多种换行写法，用于暴露换行未折叠的问题）
SCRAMBLE_SEPARATORS = (
    " ",
    "  ",
    "\n",
    "\n",
    "\n    ",
    " \n ",
    "\n\t",
    "\t",
)


def _rewrite_separators(sql_text: str, pick, reflow_keywords: bool) -> str:
    """重写 token 之间的空白（可选：多词关键字内部的空白）。

    pick(allow_empty) 返回该边界要写入的空白字符串。非空白 token 的 value
    原样保留，因此 SQL 语义与 token 类型不变。
    """
    out = []
    prev = None
    pending_ws = False
    for ttype, value in lexer.tokenize(sql_text):
        if ttype in T.Whitespace:
            pending_ws = True
            continue

        if prev is not None:
            ptype, pvalue = prev
            if ptype is T.Comment.Single and not pvalue.endswith(("\n", "\r")):
                # 单行注释必须保留换行，否则会把后续 SQL 吞进注释
                out.append("\n")
            elif pending_ws:
                # 上一 token 自带换行时允许压成空串，避免堆出空行
                allow_empty = bool(out and out[-1].endswith(("\n", "\r")))
                out.append(pick(allow_empty))

        if reflow_keywords and ttype in T.Keyword and any(c.isspace() for c in value):
            value = "".join(pick(False) if c.isspace() else c for c in value)
        out.append(value)

        prev = (ttype, value)
        pending_ws = False

    return "".join(out)


def flatten_whitespace(sql_text: str) -> str:
    """确定性压平：把所有 token 间隔空白统一成单个空格，用于收敛门禁。

    只改空白、不改 token 类型与顺序，因此格式化结果「应当」与输入空白无关。
    """
    return _rewrite_separators(sql_text, lambda allow_empty: " ", reflow_keywords=True)


def scramble_whitespace(
    sql_text: str, rng: random.Random, separators=SCRAMBLE_SEPARATORS, reflow_keywords=False
) -> str:
    """随机打乱 token 之间的空白，用于本地探索。

    默认不改多词关键字（如 not null）内部的空白，保证 token 流与输入完全一致；
    需要覆盖 lexer 合并路径时传 reflow_keywords=True。
    """

    def pick(allow_empty):
        pool = (("",) + tuple(separators)) if allow_empty else tuple(separators)
        return rng.choice(pool)

    return _rewrite_separators(sql_text, pick, reflow_keywords=reflow_keywords)


def format_with_entry_defaults(sql_text: str) -> str:
    # 使用 sqlfmt 入口函数默认行为进行格式化。
    return normalize_sql(sqlfmt.sqlfilefmt(sql_text))


def format_with_options(sql_text: str, **options) -> str:
    """使用自定义选项进行格式化。"""
    return normalize_sql(sqlfmt.sqlfilefmt(sql_text, **options))


def case_expected(case) -> str:
    return normalize_sql(case.expected_sql)


def case_input(case) -> str:
    return normalize_sql(case.input_sql)


def selected_cases():
    # 通过 SQLFMT_CASE_TAGS 进行标签筛选，多个标签按 AND 匹配。
    tag_filter = os.getenv("SQLFMT_CASE_TAGS", "").strip()
    if not tag_filter:
        return SQL_CASES

    required = {t.strip() for t in tag_filter.split(",") if t.strip()}
    if not required:
        return SQL_CASES

    return [case for case in SQL_CASES if required.issubset(set(case.tags))]
