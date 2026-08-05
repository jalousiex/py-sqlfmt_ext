import os

import sqlfmt

from tests.fixtures.sql_cases import SQL_CASES, normalize_sql


def format_with_entry_defaults(sql_text: str) -> str:
    # 使用 sqlfmt 入口函数默认行为进行格式化。
    return normalize_sql(sqlfmt.sqlfilefmt(sql_text))


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
