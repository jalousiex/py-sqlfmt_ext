"""装配层：复用官方 ``build_filter_stack``，只替换「负责换行的那个 filter」。

为什么不再保留官方 ``AlignedIndentFilter``
----------------------------------------
官方 ``AlignedIndentFilter`` 只有一个 ``char`` 参数，既不接受本项目的
``align_list`` / ``comma_first``，缩进口径也不同；留在 stack 里只会产出一份
立刻被 ``LayoutPass`` 覆盖的空白，徒增耦合。因此装配后把它摘掉，换成
``LayoutPass``；官方其余 filter（分组、strip、操作符空格、序列化）与装配
**顺序**仍完全由官方 ``build_filter_stack`` 决定。
"""

from sqlparse import engine, filters, formatter
from sqlparse.engine import grouping

from sqlfmt_ext import policy  # noqa: F401  确保分词补丁 ttype 已派生
from sqlfmt_ext.filters.operators import SpacesAroundOperatorsFilter
from sqlfmt_ext.lexer import build_lexer
from sqlfmt_ext.options import validate_options
from sqlfmt_ext.passes.layout import LayoutPass

# 官方产出「换行骨架」的 filter：由本项目 LayoutPass 取代
_SKELETON_FILTERS = (filters.AlignedIndentFilter, filters.ReindentFilter)


class FilterStack(engine.FilterStack):
    """官方 ``FilterStack`` + 可注入的方言 lexer。

    官方 ``FilterStack.run`` 硬引用 ``sqlparse.lexer`` 的模块级单例，无法把本
    项目构造的 lexer 传进去。这里覆写 ``run``，**只改「lexer 来源」这一点**，
    其余步骤与官方实现逐行一致（因此官方对 run 的改动需要同步）。
    """

    def __init__(self, lexer=None):
        super().__init__()
        self.lexer = lexer if lexer is not None else build_lexer()

    def run(self, sql, encoding=None):
        stream = self.lexer.get_tokens(sql, encoding)

        for filter_ in self.preprocess:
            stream = filter_.process(stream)

        stream = engine.StatementSplitter().process(stream)

        for stmt in stream:
            if self._grouping:
                stmt = grouping.group(stmt)
            for filter_ in self.stmtprocess:
                filter_.process(stmt)
            for filter_ in self.postprocess:
                stmt = filter_.process(stmt)
            yield stmt


def _swap_operators_filter(stack):
    """把官方 SpacesAroundOperatorsFilter 实例换成支持泛型尖括号的子类实例。"""
    for index, flt in enumerate(stack.stmtprocess):
        if type(flt) is filters.SpacesAroundOperatorsFilter:
            stack.stmtprocess[index] = SpacesAroundOperatorsFilter()


def _replace_skeleton_filters(stack, opts):
    """摘掉官方换行 filter，原位换成本项目 LayoutPass。"""
    position = None
    kept = []
    for flt in stack.stmtprocess:
        if isinstance(flt, _SKELETON_FILTERS):
            if position is None:
                position = len(kept)
            continue
        kept.append(flt)

    if position is None:
        position = len(kept)
    kept.insert(position, LayoutPass(opts))
    stack.stmtprocess[:] = kept


def _assemble(opts):
    """按已验证的选项装配 FilterStack（装配顺序交给官方）。"""
    stack = FilterStack(build_lexer(opts.get("dialect")))
    formatter.build_filter_stack(stack, opts)
    _swap_operators_filter(stack)
    _replace_skeleton_filters(stack, opts)
    return stack


def _name(flt):
    return f"{type(flt).__module__}.{type(flt).__name__}"


def build_stack(options=None):
    """返回 (FilterStack, 已验证选项)。调用方需自行追加 SerializerUnicode。"""
    opts = validate_options(options)
    return _assemble(opts), opts


def stack_pipeline(options=None):
    """返回 (preprocess, stmtprocess, postprocess) 的名字列表，便于诊断。"""
    stack, _ = build_stack(options)
    return (
        [_name(f) for f in stack.preprocess],
        [_name(f) for f in stack.stmtprocess],
        [_name(f) for f in stack.postprocess],
    )


def format_sql(sql, options=None):
    """格式化单条 SQL（不 strip，行为对齐官方 ``sqlparse.format``）。"""
    opts = validate_options(options)
    stack = _assemble(opts)
    stack.postprocess.append(filters.SerializerUnicode())
    return "".join(stack.run(sql))


def format_statements(sql, options=None):
    """按 ``;`` 拆分逐条格式化后以空行拼接（行为对齐旧 ``sqlfilefmt``）。"""
    opts = validate_options(options)
    lexer = build_lexer(opts.get("dialect"))

    splitter = FilterStack(lexer)
    statements = [str(stmt).strip() for stmt in splitter.run(sql)]

    stack = _assemble(opts)
    stack.postprocess.append(filters.SerializerUnicode())
    return "\n\n".join("".join(stack.run(stmt)).strip() for stmt in statements)
