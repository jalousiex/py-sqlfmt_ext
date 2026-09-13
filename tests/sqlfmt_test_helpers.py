import os

from sqlfmt_ext import format_statements
from tests.fixtures.sql_cases import SQL_CASES, normalize_sql

# 空白改写（压平/打乱）已抽到 `tests/fixtures/whitespace.py`：那边**不导入入口模块**，
# 迁移期新实现（`sqlfmt_ext`）的门禁才能复用同一口径。这里保持对外名字不变。
from tests.fixtures.whitespace import (  # noqa: F401
    SCRAMBLE_SEPARATORS,
    flatten_whitespace,
    scramble_whitespace,
)


def format_with_entry_defaults(sql_text: str) -> str:
    # 使用入口默认行为进行格式化（与旧 sqlfmt.sqlfilefmt 的默认口径逐项一致）。
    return normalize_sql(format_statements(sql_text))


def format_with_options(sql_text: str, **options) -> str:
    """使用自定义选项进行格式化。"""
    return normalize_sql(format_statements(sql_text, options))


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
