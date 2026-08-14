"""测试 align_list 和 comma_first 参数行为

用例通过 tests/fixtures/cases/comma/ 下的 .sql fixture 文件定义，
文件内容即为格式化后的预期输出（幂等）。
"""

import difflib

import pytest

from pytests.fixtures.sql_cases import SQL_CASES
from pytests.sqlfmt_test_helpers import case_expected, format_with_options


def _comma_cases():
    """筛选 comma topic 的用例。"""
    return [c for c in SQL_CASES if "comma" in c.tags]


@pytest.mark.parametrize("case", _comma_cases(), ids=lambda case: case.name)
def test_comma_option_output_should_match_expected(case):
    """使用用例指定的 options 格式化，结果应与 fixture 文件一致。"""
    actual_output = format_with_options(case.input_sql, **case.options)
    expected_output = case_expected(case)
    diff = "".join(
        difflib.unified_diff(
            expected_output.splitlines(keepends=True),
            actual_output.splitlines(keepends=True),
            fromfile="expected",
            tofile="actual",
            lineterm="",
        )
    )
    assert actual_output == expected_output, f"格式化输出与期望不一致\n{diff}"


@pytest.mark.parametrize("case", _comma_cases(), ids=lambda case: case.name)
def test_comma_option_should_be_idempotent(case):
    """使用用例指定的 options 二次格式化，结果应不变。"""
    first_pass = format_with_options(case.input_sql, **case.options)
    second_pass = format_with_options(first_pass, **case.options)
    assert second_pass == first_pass, "二次格式化结果发生变化"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
