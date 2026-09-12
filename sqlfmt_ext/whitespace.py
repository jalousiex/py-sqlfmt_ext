"""空白粒度工具：恢复「一段连续空白 = 一个 token」的前提。

官方 0.6.0 的 lexer 对**每个空白字符**各产出一个 token（``' ' * 82`` → 82 个
token，每个 value 长度 1），而本项目从旧 fork 移植来的布局/对齐代码都建立在
「一段连续空白 = 一个 token」这个前提上（旧 fork 的 lexer 用 ``[^\\S\\r\\n]+``
把一段空白合并成一个 token）。

前提不成立时的典型故障：``AlignMixin._set_adjacent_ws`` 只会改写紧邻目标的
**那一个**空 token（该段中 value 为 ``''`` 的最后一个），段首保留的 ``' '``
仍在原地 → 列宽整体多 1；``_remove_prev_newline`` 也要循环删除整段。

这里只做 Whitespace 改写（符合 C5）：合并后 value 取拼接（段内字符总量不变，
因此 ``TokenList.value`` 缓存无需刷新），ttype 沿用段首 token——与官方 strip
逐字符产出时「首 token 保留值、其余置空」的口径一致，不引入新的换行语义。
"""


def merge_whitespace_runs(tlist):
    """就地合并 ``tlist`` 每层中连续的空白 token（含嵌套子组）。"""
    tokens = tlist.tokens
    merged = []
    for token in tokens:
        if token.is_group:
            merge_whitespace_runs(token)
        prev_ = merged[-1] if merged else None
        if prev_ is not None and prev_.is_whitespace and token.is_whitespace:
            prev_.value += token.value
            continue
        merged.append(token)
    if len(merged) != len(tokens):
        tlist.tokens[:] = merged
