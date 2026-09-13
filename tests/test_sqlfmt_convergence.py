"""收敛性测试：格式化结果应只取决于 token 流，而与输入空白无关。

做法：把每个用例的期望输出（canonical）的 token 间隔空白确定性压平成单个空格，
再格式化一次，结果应仍等于 canonical。

已知偏离的用例先 xfail（strict=True）——修好一个就会变成 XPASS 失败，提示删除该项，
避免"已知失败"清单无限期滞留。
"""

import pytest

from tests.sqlfmt_test_helpers import (
    case_expected,
    flatten_whitespace,
    format_with_entry_defaults,
    format_with_options,
    selected_cases,
)

# 已知「输出依赖输入空白」的用例 → 原因（修好一个删一个）
KNOWN_DIVERGENT = {
    # `case/sqltest4_s03` 已删：S7-d 重定基线为「`case` 与首个 `when` 同行」后，
    # 该用例的 canonical 本身即稳定形态，压平输入空白不再改变输出。
    "comma/sqltest7_s02": "块注释之间的换行被压掉（comma_first=True）",
    "cte/sqltest2_s01": "where 后行首注释 / 分号布局依赖输入换行",
    "ddl/sqltest0_s04": "ON COMMIT 刻意分行，属白名单行为，非缺陷",
    # `dml/sqltest1_s06` 已删：入口切到新实现后它**不再依赖输入换行**
    # （S5a 的 `policy.MULTIWORD_REGEX` 兜底让多个 lateral view 各自分行）——
    # 这项留着会因 XPASS(strict) 反而变红。
    "nested/sqltest3_s01": "块注释后的换行 / 行首注释对齐依赖输入换行",
}


def _convergence_params():
    params = []
    for case in selected_cases():
        marks = ()
        reason = KNOWN_DIVERGENT.get(case.name)
        if reason:
            marks = pytest.mark.xfail(strict=True, reason=reason)
        params.append(pytest.param(case, id=case.name, marks=marks))
    return params


def _format(sql_text, case):
    if case.options:
        return format_with_options(sql_text, **case.options)
    return format_with_entry_defaults(sql_text)


@pytest.mark.parametrize("case", _convergence_params())
def test_flattened_input_should_converge(case):
    canonical = case_expected(case)
    variant = flatten_whitespace(canonical)
    assert _format(variant, case) == canonical, "压平输入空白后输出发生变化"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
