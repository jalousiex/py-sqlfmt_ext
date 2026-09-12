"""``StripWhitespaceFilter`` 子类：把空白粒度恢复成「一段 = 一个 token」。

官方 strip 的每一步都隐含「一段连续空白已经是单个 token」（这正是官方自己
lexer 的产物所不具备的，见 ``sqlfmt_ext.whitespace``）：

* ``_stripws_identifierlist`` 只删掉逗号前的**最后一个**空白 token。在逐字符
  空白下，一段 82 个空格的 token 只会被删掉 1 个，剩下 1 个空格留在逗号前，
  与 ``AlignMixin`` 填好的对齐空白叠加 → 非 AS 字段的末尾逗号整体多 1 列。
* ``_stripws_default`` 把一段空白变成「首个保留 ``' '``、其余置 ``''``」，
  留下大量空 value 的空白 token 干扰相邻改写。

因此在官方 ``_stripws`` 之前先合并空白段即可同时解决两者：合并后
``_stripws_identifierlist`` 删除的就是整段，``_stripws_default`` 也只面对
一段一个 token。除此之外（递归顺序、``_stripws_parenthesis``、首尾处理）与
官方实现逐行一致。
"""

from sqlparse.filters.others import (
    StripWhitespaceFilter as _UpstreamStripWhitespaceFilter,
)

from sqlfmt_ext.whitespace import merge_whitespace_runs


class StripWhitespaceFilter(_UpstreamStripWhitespaceFilter):
    def process(self, stmt, depth=0):
        [self.process(sgroup, depth + 1) for sgroup in stmt.get_sublists()]
        merge_whitespace_runs(stmt)
        self._stripws(stmt)
        if depth == 0 and stmt.tokens and stmt.tokens[-1].is_whitespace:
            stmt.tokens.pop(-1)
        return stmt
