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
    # `comma/sqltest7_s02`、`nested/sqltest3_s01` 已删：S9 把「两段注释不共享一行」
    # 从组内规则扩到**同层并列的注释组**（`LayoutPass._break_before_sibling_comment`），
    # 判据由 `prev_.is_newline` 换成「前一段注释自己不带行尾换行」。
    # `ddl/sqltest0_s04` 已删：S9 把 `ON COMMIT` 白名单改成结构性（命中者一律按分词切开）。
    # `dml/sqltest1_s06` 已删：入口切到新实现后它**不再依赖输入换行**
    # （S5a 的 `policy.MULTIWORD_REGEX` 兜底让多个 lateral view 各自分行）——
    # 这项留着会因 XPASS(strict) 反而变红。
    # `cte/sqltest2_s01` 已删（S9-g）：唯一剩下的发散项。原判据是 `prev_.is_newline`
    # ——「输入里该注释是否在行首」，与 C4 天然冲突。改为结构性判据
    # `LayoutPass._closes_its_level`（其后本层只余空白与语句结束符 `;`），
    # 压平输入后同样成立，两条路径归一。**当前 `KNOWN_DIVERGENT` 为空**。
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
