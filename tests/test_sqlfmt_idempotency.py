import pytest

from tests.sqlfmt_test_helpers import (
    case_expected,
    case_input,
    format_with_entry_defaults,
    format_with_options,
    selected_cases,
)


def _twice(sql, case):
    if case.options:
        first_pass = format_with_options(sql, **case.options)
        second_pass = format_with_options(first_pass, **case.options)
    else:
        first_pass = format_with_entry_defaults(sql)
        second_pass = format_with_entry_defaults(first_pass)
    return first_pass, second_pass


@pytest.mark.parametrize("case", selected_cases(), ids=lambda case: case.name)
def test_sqlfmt_entry_should_be_idempotent(case):
    # 对于 input ≠ expected 的用例，验证 expected 本身是幂等的
    first_pass, second_pass = _twice(case_expected(case), case)
    assert second_pass == first_pass, "二次格式化结果发生变化"


@pytest.mark.parametrize("case", selected_cases(), ids=lambda case: case.name)
def test_sqlfmt_entry_should_be_idempotent_from_input(case):
    # 直接对输入 SQL 二次格式化，结果同样必须稳定
    first_pass, second_pass = _twice(case_input(case), case)
    assert second_pass == first_pass, "从输入 SQL 出发的二次格式化结果发生变化"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
