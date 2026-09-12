"""``SpacesAroundOperatorsFilter`` 子类：类型参数里的尖括号不加空格。

官方会把 ``ARRAY<VARIANT>`` 变成 ``ARRAY < VARIANT >``，这里补上「尖括号处于
类型参数上下文」的判断，用法：在官方 stack 里换装本类实例，不改官方源码。

注意：官方 ``process()`` 里以类名硬引用了自己的 ``_process``，所以子类必须同时
覆盖 ``process``，否则覆盖无效。
"""

from sqlparse.filters.others import (
    SpacesAroundOperatorsFilter as _UpstreamSpacesAroundOperatorsFilter,
)
from sqlparse import sql
from sqlparse import tokens as T


class SpacesAroundOperatorsFilter(_UpstreamSpacesAroundOperatorsFilter):
    # 类型参数中的尖括号不应加空格：ARRAY<VARIANT>, MAP<STRING,INT>
    _TYPE_KEYWORDS = {"ARRAY", "MAP", "STRUCT", "UNIONTYPE"}

    @staticmethod
    def _is_type_angle_bracket(tlist, tidx, token):
        """检查 < 或 > 是否处于类型参数上下文中（如 ARRAY<VARIANT>）。"""
        # 支持 >> 等合并的尖括号（嵌套泛型 ARRAY<MAP<A,B>>）
        if not token.value or all(c in "<>" for c in token.value):
            is_angle = True
        else:
            return False

        def _last_value(tok):
            """递归获取 token 的最后一个有意义的值。"""
            if tok.is_group:
                for child in reversed(tok.tokens):
                    if not child.is_whitespace:
                        return _last_value(child)
                return ""
            return tok.value.upper()

        def _first_value(tok):
            """递归获取 token 的第一个有意义的值。"""
            if tok.is_group:
                for child in tok.tokens:
                    if not child.is_whitespace:
                        return _first_value(child)
                return ""
            return tok.value.upper()

        pidx, prev_ = tlist.token_prev(tidx, skip_ws=True)
        nidx, next_ = tlist.token_next(tidx, skip_ws=True)

        if "<" in token.value:
            # < 前面是类型关键字或 >（嵌套），后面是类型名或 <（嵌套）
            if prev_ and (
                _last_value(prev_) in SpacesAroundOperatorsFilter._TYPE_KEYWORDS
                or prev_.value == ">"
            ):
                return True
            if next_ and (
                _first_value(next_) in SpacesAroundOperatorsFilter._TYPE_KEYWORDS
                or next_.value == "<"
            ):
                return True
        if ">" in token.value:
            # > 前面是类型名/关键字/>/数字，后面是 ) , > 
            if prev_ and (
                _last_value(prev_) in SpacesAroundOperatorsFilter._TYPE_KEYWORDS
                or prev_.ttype == T.Name.Builtin
                or prev_.value == ">"
            ):
                return True
            if next_ and next_.value in (")", ",", ">"):
                return True

        return False

    @staticmethod
    def _process(tlist):
        ttypes = (T.Operator, T.Comparison)
        tidx, token = tlist.token_next_by(t=ttypes)
        while token:
            # 跳过类型参数中的尖括号
            if SpacesAroundOperatorsFilter._is_type_angle_bracket(tlist, tidx, token):
                tidx, token = tlist.token_next_by(t=ttypes, idx=tidx)
                continue

            nidx, next_ = tlist.token_next(tidx, skip_ws=False)
            if (
                next_
                and next_.ttype != T.Whitespace
                and not isinstance(next_, sql.Parenthesis)
            ):
                tlist.insert_after(tidx, sql.Token(T.Whitespace, " "))

            pidx, prev_ = tlist.token_prev(tidx, skip_ws=False)
            if prev_ and prev_.ttype != T.Whitespace:
                tlist.insert_before(tidx, sql.Token(T.Whitespace, " "))
                tidx += 1  # has to shift since token inserted before it

            tidx, token = tlist.token_next_by(t=ttypes, idx=tidx)

    def process(self, stmt):
        # 与官方一致地递归处理子组，但调用本类（子类）的 _process
        [self.process(sgroup) for sgroup in stmt.get_sublists()]
        SpacesAroundOperatorsFilter._process(stmt)
        return stmt
