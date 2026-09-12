"""装配层：复用官方 ``build_filter_stack``，仅在骨架 filter 之后插入本项目 pass。

不复制官方装配逻辑，因此官方升级（新增 filter / 调整顺序）能自动继承；
本项目只做两件事：
1. 换装 ``SpacesAroundOperatorsFilter``（泛型尖括号）；
2. 在官方 indent filter 之后插入 ``LayoutPass`` / ``AlignPass``。
"""

from sqlparse import engine, filters, formatter, split as upstream_split

from sqlfmt_ext.filters.operators import SpacesAroundOperatorsFilter
from sqlfmt_ext.options import validate_options
from sqlfmt_ext.passes.align import AlignPass
from sqlfmt_ext.passes.layout import LayoutPass

# 官方产出「换行骨架」的 filter；本项目 pass 插在它们之后
_SKELETON_FILTERS = (filters.AlignedIndentFilter, filters.ReindentFilter)


def _swap_operators_filter(stack):
    """把官方 SpacesAroundOperatorsFilter 实例换成支持泛型尖括号的子类实例。"""
    for index, flt in enumerate(stack.stmtprocess):
        if type(flt) is filters.SpacesAroundOperatorsFilter:
            stack.stmtprocess[index] = SpacesAroundOperatorsFilter()


def _assemble(opts):
    """按已验证的选项装配 FilterStack。"""
    stack = formatter.build_filter_stack(engine.FilterStack(), opts)
    _swap_operators_filter(stack)

    position = len(stack.stmtprocess)
    for index, flt in enumerate(stack.stmtprocess):
        if isinstance(flt, _SKELETON_FILTERS):
            position = index + 1
    stack.stmtprocess[position:position] = [LayoutPass(opts), AlignPass(opts)]
    return stack


def build_stack(options=None):
    """返回 (FilterStack, 已验证选项)。调用方需自行追加 SerializerUnicode。"""
    opts = validate_options(options)
    return _assemble(opts), opts


def _run(sql, opts):
    stack = _assemble(opts)
    stack.postprocess.append(filters.SerializerUnicode())
    return "".join(stack.run(sql))


def format_sql(sql, options=None):
    """格式化单条 SQL（不 strip，行为对齐官方 ``sqlparse.format``）。"""
    return _run(sql, validate_options(options))


def format_statements(sql, options=None):
    """按 ``;`` 拆分逐条格式化后以空行拼接（行为对齐旧 ``sqlfilefmt``）。"""
    opts = validate_options(options)
    return "\n\n".join(_run(stmt, opts).strip() for stmt in upstream_split(sql))
