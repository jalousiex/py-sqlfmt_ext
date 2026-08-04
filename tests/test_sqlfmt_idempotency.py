import pytest

from tests.sqlfmt_test_helpers import format_with_entry_defaults, selected_cases


@pytest.mark.parametrize("case", selected_cases(), ids=lambda case: case.name)
def test_sqlfmt_entry_should_be_idempotent(case):
    first_pass = format_with_entry_defaults(case.input_sql)
    second_pass = format_with_entry_defaults(first_pass)
    assert second_pass == first_pass, "二次格式化结果发生变化"


if __name__ == "__main__":
    unittest.main()
