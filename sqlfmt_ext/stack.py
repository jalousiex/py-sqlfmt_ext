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
from sqlparse import tokens as T

from sqlfmt_ext import dialects, grouping, policy  # noqa: F401  确保分词补丁 ttype 已派生
from sqlfmt_ext.filters.operators import SpacesAroundOperatorsFilter
from sqlfmt_ext.filters.whitespace import StripWhitespaceFilter
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
                stmt = grouping.group(stmt)  # 本项目补偿层：官方分组 + 注释容忍归并
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


def _swap_whitespace_filter(stack):
    """把官方 StripWhitespaceFilter 实例换成「先合并空白段再 strip」的子类实例。"""
    for index, flt in enumerate(stack.stmtprocess):
        if type(flt) is filters.StripWhitespaceFilter:
            stack.stmtprocess[index] = StripWhitespaceFilter()


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
    _swap_whitespace_filter(stack)
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
    return _format_preserving_at_lines(sql, lambda part: _format_sql_part(part, opts))


def _format_sql_part(sql, opts):
    stack = _assemble(opts)
    stack.postprocess.append(filters.SerializerUnicode())
    return "".join(stack.run(sql))


def format_statements(sql, options=None):
    """按 ``;`` 拆分逐条格式化后以空行拼接（行为对齐旧 ``sqlfilefmt``）。

    方言声明了 ``batch_separator``（SQL Server 的 ``GO``）时，先按批分隔符切批，
    逐批走上面那条原路，批之间插一行分隔符。
    """
    opts = validate_options(options)
    return _format_preserving_at_lines(sql, lambda part: _format_statements_part(part, opts))


def _format_preserving_at_lines(sql, format_part):
    """原样保留独立 ``@`` 行，其余片段分别格式化。"""
    output = []
    pending = []
    for line in sql.splitlines(keepends=True):
        if line.lstrip(" \t").startswith("@"):
            formatted = format_part("".join(pending)) if pending else ""
            if formatted:
                output.append(formatted)
                if not formatted.endswith(("\n", "\r")):
                    output.append("\r\n" if "\r\n" in sql else "\n")
            output.append(line)
            pending.clear()
        else:
            pending.append(line)
    if pending:
        output.append(format_part("".join(pending)))
    return "".join(output)


def _format_statements_part(sql, opts):
    separator = dialects.batch_separator_for(opts.get("dialect"))
    if not separator:
        return _format_batch(sql, opts)

    lexer = build_lexer(opts.get("dialect"))
    batches, trailing, seen = _split_batches(sql, separator, lexer)
    if not seen:
        return _format_batch(sql, opts)
    return _join_batches(batches, separator, trailing, opts)


def _format_batch(sql, opts):
    """按 ``;`` 拆分逐条格式化后以空行拼接（``format_statements`` 的主体）。"""
    lexer = build_lexer(opts.get("dialect"))

    splitter = FilterStack(lexer)
    statements = [str(stmt).strip() for stmt in splitter.run(sql)]

    stack = _assemble(opts)
    stack.postprocess.append(filters.SerializerUnicode())
    return "\n\n".join("".join(stack.run(stmt)).strip() for stmt in statements)


def _split_batches(sql, separator, lexer):
    """按「独占一个 token 的批分隔符」切批。

    判据取自**分词结果**而不是「该行是否只写了 ``GO``」：这样压平空白的输入与 canonical
    走同一条路径，收敛门禁不会因为换行被压掉而失效（``.claude/plan/stages.md`` §9.11）。代价是不解析
    字符串/注释内容 —— 与 sqlcmd 的按行口径同级，登记为已知边界。

    返回 ``(batches, trailing, seen)``：``batches`` 为批文本（空批已丢弃），``trailing``
    表示输入以分隔符收尾，``seen`` 表示出现过批分隔符（为假时调用方走原路径）。
    """
    wanted = separator.upper()
    batches = []
    current = []
    seen = 0
    trailing = False
    for ttype, value in lexer.get_tokens(sql):
        if ttype in T.Keyword and value.upper() == wanted:
            seen += 1
            batches.append("".join(current))
            current = []
            trailing = True
            continue
        current.append(value)
        if value.strip():
            trailing = False
    tail = "".join(current)
    if tail.strip():
        batches.append(tail)
    return [b for b in batches if b.strip()], trailing, seen


def _join_batches(batches, separator, trailing, opts):
    """批之间插一行批分隔符；批内语句仍用空行（原口径）。

    形态：``<批>`` → ``\\n<sep>`` → ``\\n\\n<下一批>``；最后一个批若以分隔符收尾则补一行。
    """
    out = []
    for index, text in enumerate(batches):
        if index:
            out.append("\n\n")
        out.append(_format_batch(text, opts))
        if index < len(batches) - 1 or trailing:
            out.append("\n" + separator)
    return "".join(out)
