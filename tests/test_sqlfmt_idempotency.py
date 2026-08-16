import pytest

from tests.sqlfmt_test_helpers import (
    case_expected,
    format_with_entry_defaults,
    format_with_options,
    selected_cases,
)


@pytest.mark.parametrize("case", selected_cases(), ids=lambda case: case.name)
def test_sqlfmt_entry_should_be_idempotent(case):
    # 对于 input ≠ expected 的用例，验证 expected 本身是幂等的
    sql = case_expected(case)
    if case.options:
        first_pass = format_with_options(sql, **case.options)
        second_pass = format_with_options(first_pass, **case.options)
    else:
        first_pass = format_with_entry_defaults(sql)
        second_pass = format_with_entry_defaults(first_pass)
    assert second_pass == first_pass, "二次格式化结果发生变化"


if __name__ == "__main__":
    unittest.main()
