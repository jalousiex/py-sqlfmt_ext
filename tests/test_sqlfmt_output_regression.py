import difflib

import pytest

from tests.sqlfmt_test_helpers import (
    case_expected,
    format_with_entry_defaults,
    selected_cases,
)


@pytest.mark.parametrize("case", selected_cases(), ids=lambda case: case.name)
def test_sqlfmt_entry_output_should_match_expected(case):
    actual_output = format_with_entry_defaults(case.input_sql)
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


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
