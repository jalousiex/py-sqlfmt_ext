#
# Copyright (C) 2009-2020 the sqlparse authors and contributors
# <see AUTHORS file>
#
# This module is part of python-sqlparse and is released under
# the BSD License: https://opensource.org/licenses/BSD-3-Clause

from sqlparse import sql, tokens as T
from sqlparse.utils import offset, indent


class ReindentFilter:
    join_words = (r'((LEFT\s+|RIGHT\s+|FULL\s+)?'
                  r'(INNER\s+|OUTER\s+|STRAIGHT\s+)?|'
                  r'(CROSS\s+|NATURAL\s+)?)?JOIN\b')
    by_words = r'(GROUP|ORDER)\s+BY\b'
    split_words = ('FROM',
                   join_words, by_words,
                   'WHERE', 'AND', 'OR',
                   'UNION', 'VALUES',
                   'SET', 'BETWEEN', 'EXCEPT',
                   'HAVING', 'LIMIT')

    def __init__(self, width=2, char=' ', wrap_after=0, n='\n',
                 comma_first=False, indent_after_first=False,
                 indent_columns=False, compact=False):
        self.n = n
        self.width = width
        self.char = char
        self._max_kwd_len = len('select')
        self.indent = 1 if indent_after_first else 0
        self.offset = 0
        self.wrap_after = wrap_after
        self.comma_first = comma_first
        self.indent_columns = indent_columns
        self.compact = compact
        self._curr_stmt = None
        self._last_stmt = None
        self._last_func = None

    def _flatten_up_to_token(self, token):
        """Yields all tokens up to token but excluding current."""
        if token.is_group:
            token = next(token.flatten())

        for t in self._curr_stmt.flatten():
            if t == token:
                break
            yield t

    @property
    def leading_ws(self):
        return self.offset + self.indent * self.width

    def _get_offset(self, token):
        raw = ''.join(map(str, self._flatten_up_to_token(token)))
        line = (raw or '\n').splitlines()[-1]
        # Now take current offset into account and return relative offset.
        return len(line) - len(self.char * self.leading_ws)

    def nl(self, offset=0):
        # offset = 1 represent a single space after SELECT
        # 传字符串则回退该字符串长度，即右对齐
        offset = -len(offset) if not isinstance(offset, int) else offset
        # add two for the space and parenthesis
        # 本层的前置空白 + 新增缩进 + 新增偏移
        return sql.Token(
            T.Whitespace,
            self.n + self.char * (self.leading_ws + offset))

    def _remove_prev_newline(self, tlist, tidx=0):
        """在整个stmt的token级别，清除前边连续空白节点的末尾换行，但只返回本层prev"""
        pidx, prev_ = tlist.token_prev(tidx, skip_ws=True)
        if prev_:
            for tk in tlist[pidx: tidx]:
                # 空白节点不会单独成组，一定是其它非空白子节点
                if tk.is_whitespace:
                    del tlist.tokens[tlist.token_index(tk)]
                    tidx -= 1
                # 多行注释中的换行？
                if str(tk.__str__()).find(self.n) > 0:
                    if tk.is_group:
                        _, _ = self._remove_prev_newline(tk, len(tk.tokens))
                    else: # elif tk.ttype is not T.Comment.Single:
                        # 换行后有空格的很可能是本程序对齐用的，故只清除末尾换行
                        tk.value = tk.__str__().rstrip(self.n)
                        # tk.normalized = tk.value.upper() if tk.is_keyword else tk.value
        else:
            # 头部空白处理
            for pidx in range(0, tidx):
                if tlist.tokens[pidx].is_whitespace:
                    del tlist.tokens[pidx]
                    tidx -= 1
            if tlist.parent is not None:
                # 例如Where-where的首个Keyword-where，向上一层
                _, _ = self._remove_prev_newline(tlist.parent, tlist.parent.token_index(tlist))

        # 更新属性
        tlist.value = tlist.__str__()
        # tlist.normalized = tlist.value.upper() if tlist.is_keyword else tlist.value
        return tidx, prev_


    def _next_token(self, tlist, idx=-1):
        """match需要类型和切分词都满足"""
        m_split = (T.Keyword, self.split_words, True)
        tidx, token = tlist.token_next_by(m=m_split, idx=idx)
        # treat "BETWEEN x and y" as a single statement
        if token and token.normalized == 'BETWEEN':
            tidx, token = self._next_token(tlist, tidx)

            if token and token.normalized == 'AND':
                tidx, token = self._next_token(tlist, tidx)

        return tidx, token

    def _split_kwds(self, tlist):
        # 遍历关键字，_next_token查找下一个关键字token
        tidx, token = self._next_token(tlist)
        while token:
            # joins, group/order by are special case. only consider the first
            # word as aligner
            if (
                token.match(T.Keyword, self.join_words, regex=True)
                or token.match(T.Keyword, self.by_words, regex=True)
            ):
                token_indent = token.value.split()[0]
            else:
                token_indent = str(token)

            # 插入包括缩进处理，直接跳过就缺少了缩进，所以先删除前边紧邻空白中的换行
            tidx, ws_ = self._remove_prev_newline(tlist, tidx)
            tlist.insert_before(token, self.nl(self._max_kwd_len - len(token_indent)))
            tidx += 1
            tidx, token = self._next_token(tlist, tidx)

    def _split_statements(self, tlist):
        ttypes = T.Keyword.DML, T.Keyword.DDL
        tidx, token = tlist.token_next_by(t=ttypes)
        while token:
            # 插入包括缩进处理，直接跳过就缺少了缩进，所以先删除前边紧邻空白中的换行
            tidx, ws_ = self._remove_prev_newline(tlist, tidx)
            if ws_ and ws_.normalized != '(': # 首行不处理
                tlist.insert_before(tidx, self.nl())
                tidx += 1
            tidx, token = tlist.token_next_by(t=ttypes, idx=tidx)

    def _process(self, tlist):
        func_name = '_process_{cls}'.format(cls=type(tlist).__name__)
        func = getattr(self, func_name.lower(), self._process_default)
        func(tlist)

    def _process_where(self, tlist):
        tidx, token = tlist.token_next_by(m=(T.Keyword, 'WHERE'))
        if not token:
            return
        tlist.insert_before(tidx, self.nl())
        with indent(self):
            self._process_default(tlist)

    def _process_parenthesis(self, tlist):
        # if this isn't a subquery, don't re-indent
        ttypes = T.Keyword.DML, T.Keyword.DDL
        _, is_dml_dll = tlist.token_next_by(t=ttypes)
        _, first = tlist.token_next_by(m=sql.Parenthesis.M_OPEN)
        if first is None:
            return

        # 下层的缩进
        with indent(self, 1 if is_dml_dll else 0):
            tlist.tokens.insert(0, self.nl()) if is_dml_dll else None
            with offset(self, self._get_offset(first) + 1):
                self._process_default(tlist, not is_dml_dll)

    def _process_function(self, tlist):
        self._last_func = tlist[0]
        self._process_default(tlist)

    def _process_identifierlist(self, tlist):
        identifiers = list(tlist.get_identifiers())
        if self.indent_columns:
            first = next(identifiers[0].flatten())
            num_offset = 1 if self.char == '\t' else self.width
        else:
            first = next(identifiers.pop(0).flatten())
            num_offset = 1 if self.char == '\t' else self._get_offset(first)

        if not tlist.within(sql.Function) and not tlist.within(sql.Values):
            with offset(self, num_offset): # 非精确长度，仅第一个token
                position = 0
                for token in identifiers:
                    # 内层\n拼接后丢失了？是否改为token.__str__()
                    position += len(token.value) + 1
                    # 折行设置，判断若加入当前标识，是否超长
                    if position > (self.wrap_after - self.offset):
                        adjust = 0
                        if self.comma_first:
                            adjust = -2
                            _, comma = tlist.token_prev(
                                tlist.token_index(token))
                            if comma is None:
                                continue
                            token = comma
                        # 插入包括缩进处理，直接跳过就缺少了缩进，所以先删除前边紧邻空白中的换行
                        tidx, ws_ = self._remove_prev_newline(tlist, tidx)
                        tlist.insert_before(token, self.nl(offset=adjust))
                        if self.comma_first:
                            _, ws = tlist.token_next(
                                tlist.token_index(token), skip_ws=False)
                            if (ws is not None
                                    and ws.ttype is not T.Text.Whitespace):
                                tlist.insert_after(
                                    token, sql.Token(T.Whitespace, ' '))
                        position = 0
        else:
            # ensure whitespace
            for token in tlist:
                _, next_ws = tlist.token_next(
                    tlist.token_index(token), skip_ws=False)
                if token.value == ',' and not next_ws.is_whitespace:
                    tlist.insert_after(
                        token, sql.Token(T.Whitespace, ' '))

            end_at = self.offset + sum(len(i.value) + 1 for i in identifiers)
            adjusted_offset = 0
            if (self.wrap_after > 0
                    and end_at > (self.wrap_after - self.offset)
                    and self._last_func):
                adjusted_offset = -len(self._last_func.value) - 1

            with offset(self, adjusted_offset), indent(self):
                if adjusted_offset < 0:
                    tlist.insert_before(identifiers[0], self.nl())
                position = 0
                for token in identifiers:
                    # Add 1 for the "," separator
                    position += len(token.value) + 1
                    if (self.wrap_after > 0
                            and position > (self.wrap_after - self.offset)):
                        adjust = 0
                        tlist.insert_before(token, self.nl(offset=adjust))
                        position = 0
        self._process_default(tlist)

    def _process_case(self, tlist):
        iterable = iter(tlist.get_cases())
        cond, _ = next(iterable)
        first = next(cond[0].flatten())

        with offset(self, self._get_offset(tlist[0])):
            with offset(self, self._get_offset(first)):
                for cond, value in iterable:
                    str_cond = ''.join(str(x) for x in cond or [])
                    str_value = ''.join(str(x) for x in value)
                    end_pos = self.offset + 1 + len(str_cond) + len(str_value)
                    if (not self.compact and end_pos > self.wrap_after):
                        token = value[0] if cond is None else cond[0]
                        tlist.insert_before(token, self.nl())

                # Line breaks on group level are done. let's add an offset of
                # len "when ", "then ", "else "
                with offset(self, len("WHEN ")):
                    self._process_default(tlist)
            end_idx, end = tlist.token_next_by(m=sql.Case.M_CLOSE)
            if end_idx is not None and not self.compact:
                tlist.insert_before(end_idx, self.nl())

    def _process_values(self, tlist):
        tlist.insert_before(0, self.nl())
        tidx, token = tlist.token_next_by(i=sql.Parenthesis)
        first_token = token
        while token:
            ptidx, ptoken = tlist.token_next_by(m=(T.Punctuation, ','),
                                                idx=tidx)
            if ptoken:
                if self.comma_first:
                    adjust = -2
                    offset = self._get_offset(first_token) + adjust
                    tlist.insert_before(ptoken, self.nl(offset))
                else:
                    tlist.insert_after(ptoken,
                                       self.nl(self._get_offset(token)))
            tidx, token = tlist.token_next_by(i=sql.Parenthesis, idx=tidx)

    def _process_comment(self, tlist):
        # 新增的强制换行属于Comment子类，故设置该入口处理
        tidx, token = tlist.token_next_by(t=T.ForceNewline)
        plist = tlist.parent
        pidx = plist.token_index(tlist)
        _, first = plist.token_next_by(i=(sql.Identifier, sql.IdentifierList))
        flattens = sql.TokenList(list(self._curr_stmt.flatten()))
        while token :
            offset_ = self._get_offset(first)
            # 在函数或值列表中的，将偏移加到后续tlist上，以便带到其子组
            if tlist.within(sql.Function) or tlist.within(sql.Values):
                _, next_ = plist.token_next(pidx, skip_cm=True)
                if next_:
                    next_.offset = offset_
            # 对齐换行
            _, next_ = plist.token_next(pidx, skip_ws=False)
            if next_ and not next_.value.startswith(self.n):
                tlist.insert_after(token, self.nl(offset_))
                tidx += 1

            _, prev_ = flattens.token_prev(flattens.token_index(token), skip_ws=False)
            # 紧贴前边的增加一个空格
            if prev_ and not prev_.is_whitespace:
                tlist.insert_before(token, sql.Token(T.Whitespace, ' '))
                tidx += 1
            tidx, token = tlist.token_next_by(t=T.Comment.ForceNewline, idx=tidx)
            # continue # 继续会跳过外层的后续break
            #break

    # ====以上为ttype预处理
    def _process_default(self, tlist, stmts=True):
        # 遍历DMDL、DML，遍历关键字，然后遍历子查询
        self._split_statements(tlist) if stmts else None
        self._split_kwds(tlist) if stmts else None
        for sgroup in tlist.get_sublists():  # 子对象必须is_goup
            with offset(self, sgroup.offset): # 继承强制换行的偏移
                self._process(sgroup)

    def process(self, stmt):
        self._curr_stmt = stmt
        self._process(stmt)

        if self._last_stmt is not None:
            nl = '\n' if str(self._last_stmt).endswith('\n') else '\n\n'
            stmt.tokens.insert(0, sql.Token(T.Whitespace, nl))

        self._last_stmt = stmt
        return stmt
