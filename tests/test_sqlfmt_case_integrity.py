import pytest

from tests.sqlfmt_test_helpers import case_expected, case_input, selected_cases


def test_cases_should_be_defined_and_unique():
    cases = selected_cases()
    assert cases, "筛选后无可用 SQL 用例"
    names = [case.name for case in cases]
    assert len(names) == len(set(names)), "用例名称必须唯一"


@pytest.mark.parametrize("case", selected_cases(), ids=lambda case: case.name)
def test_case_fields_should_not_be_empty(case):
    assert case.name.strip(), "用例名称不能为空"
    assert case.note.strip(), "用例说明不能为空"
    assert case_input(case), "输入 SQL 不能为空"
    assert case_expected(case), "期望 SQL 不能为空"
    assert case.tags, "用例至少应包含一个标签"
