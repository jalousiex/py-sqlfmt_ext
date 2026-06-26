#
# Copyright (C) 2009-2020 the sqlparse authors and contributors
# <see AUTHORS file>
#
# This module is part of python-sqlparse and is released under
# the BSD License: https://opensource.org/licenses/BSD-3-Clause

from sqlparse import keywords_list, sql
from sqlparse import tokens as T
from sqlparse.utils import indent, offset


class AlignedIndentFilter:
    join_words = keywords_list.join_words
    by_words = keywords_list.by_words
    split_words = keywords_list.split_words

    def __init__(self, char=" ", n="\n"):
        self.n = n
        self.offset = 0  # Token级对齐偏移
        self.indent = 0  # TokenList级关键字缩进
        self.char = char
        self.leading_kwd = "select"
        self._curr_stmt = None

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
        # 以self的indent、offset计算，若是token为左对齐点，若是关键字为右对齐点
        return self.offset + self.indent * len(self.leading_kwd)

    def _get_offset(self, token, relative=True):
        """展开stmt到token, 计算token前最后一行的长度, 添加relative控制是否扣除self已有缩进"""
        raw = "".join(map(str, self._flatten_up_to_token(token)))
        line = "" if raw.endswith(self.n) else (raw or "\n").splitlines()[-1]
        # Now take current offset into account and return relative offset.
        return max(0, len(line.encode("gbk")) - len(self.char * self.leading_ws) * relative)

    def nl(self, offset=1):
        """默认offset = 1 represent a single space after SELECT"""
        # 传字符串则回退该字符串长度, 即右对齐
        offset = -len(offset) if not isinstance(offset, int) else offset
        # add two for the space and parenthesis
        # 本层的前置空白 + 新增缩进 + 新增偏移
        return sql.Token(T.Whitespace, self.n + self.char * (self.leading_ws + offset))

    def _remove_prev_newline(self, tlist, tidx=0):
        """在整个stmt, 清除前边连续空白, 但只返回本层prev, 包括单行注释后的换行, 记得清除后必须重新换行对齐"""
        pidx, prev_ = tlist.token_prev(tidx, skip_ws=False)
        while prev_ and prev_.is_whitespace:
            # 空白节点不会单独成组, 一定是其它非空白子节点, 处理其末尾换行
            del tlist.tokens[pidx]
            tidx -= 1
            pidx, prev_ = tlist.token_prev(tidx, skip_ws=False)

        if prev_ and prev_.value.rstrip(" ").endswith(self.n):  # 'where 1=1 --\n '
            if prev_.is_group:
                _, _ = self._remove_prev_newline(prev_, len(prev_.tokens))
            else:
                prev_.value = prev_.value.rstrip()
        elif prev_:
            pass
        else:
            # 向上
            plist = tlist.parent
            if plist:
                _, _ = self._remove_prev_newline(plist, plist.token_index(tlist))

        # 更新属性
        tlist.value = str(tlist)
        return tidx, prev_

    def _process_statement(self, tlist):
        if len(tlist.tokens) > 0 and tlist.tokens[0].is_whitespace and self.indent == 0:
            tlist.tokens.pop(0)

        # process the main query body
        self._process(sql.TokenList(tlist.tokens))

    def _process_parenthesis(self, tlist):
        plist = tlist.parent
        pidx = plist.token_index(tlist)

        slist = list(tlist.get_sublists())
        no_sgroups = False if slist else True
        #  or tt.normalized == tt.value 可判断字段列表：(a,b,c)
        if slist and all([isinstance(t, sql.IdentifierList) and all([not tt.is_group for tt in t]) for t in slist]):
            simple_parenthesis = True
        else:
            simple_parenthesis = False

        # 直接返回：无子组的空括号; 单元素; vaules列表; 不含括号的
        if (
            no_sgroups
            or simple_parenthesis
            or tlist.within(sql.Case)
            and isinstance(tlist._groupable_tokens[0], sql.IdentifierList)
            or tlist.within(sql.Values)
        ):
            return

        in_xdl_list = True if self._curr_stmt.get_type() in ["CREATE", "INSERT", "ALTER"] else False

        if plist:
            # 在父对象向前查找select
            pnidx, _ = plist.token_next_by(m=(T.DML, "SELECT"), idx=pidx, _reverse=True)
            # 当前括号不在括号中, 不是父的第一个token(嵌套子查询的父是自身), 不是子查询(前边没有select)
            in_root = (
                True
                if not tlist.within(sql.Parenthesis)
                and plist.token_first(skip_cm=True) is not tlist
                and not pnidx
                and not tlist.within(sql.Where)
                else False
            )
        else:
            in_root = True

        # if this isn't a subquery, don't re-indent
        _, token = tlist.token_next_by(m=(T.DML, "SELECT"))
        if token:
            # 括号缩进，首层不需要缩进
            with indent(self, 0 if in_root else 1):
                # 括号内容的缩进, select已经在_split_kwds换行
                with offset(self, 0 if in_root else 1):
                    self._process_default(tlist)
                    _, _ = self._remove_prev_newline(tlist, len(tlist.tokens) - 1)
                    tlist.insert_before(tlist[-1], self.nl(0))
        elif tlist.within(sql.Where):  # or tlist.within(sql.Function)
            # 括号缩进
            with indent(self):
                # 括号内容的缩进
                with indent(self):
                    # tlist.insert_after(tlist[0], self.nl())
                    nidx, next_ = tlist.token_next(0, skip_cm=True)
                    while next_ and nidx > 0:
                        nidx, _ = self._remove_prev_newline(tlist, nidx)
                        tlist.insert_before(next_, self.nl())
                        # 查找下一个逗号，处理列表换行
                        nidx, next_ = tlist.token_next_by(m=(T.Punctuation, ","), idx=nidx + 1)
                        nidx, next_ = tlist.token_next(nidx, skip_cm=True)
                self._process_default(tlist)
                # 新增对齐逻辑
                self._align_create_columns(tlist)
                # de-indent last parenthesis
                _, _ = self._remove_prev_newline(tlist, len(tlist.tokens) - 1)
                tlist.insert_before(tlist[-1], self.nl())
        # 在 Create/Insert 中，字段定义 # 无子列组的，如值列表
        elif in_root and in_xdl_list or no_sgroups:
            if tlist.value in ["(*)"] or not "," in tlist.value:
                return
            # 括号缩进
            with indent(self, 1 if no_sgroups else 0):
                # 括号内容的缩进
                with indent(self):
                    nidx, next_ = tlist.token_next(0, skip_cm=True)
                    while next_ and nidx > 0:
                        nidx, _ = self._remove_prev_newline(tlist, nidx)
                        tlist.insert_before(next_, self.nl())
                        nidx, next_ = tlist.token_next_by(m=(T.Punctuation, ","), idx=nidx + 1)
                        nidx, next_ = tlist.token_next(nidx, skip_cm=True)
                self._process_default(tlist, stmts=False)
                # 新增对齐逻辑
                self._align_create_columns(tlist)
                # de-indent last parenthesis
                _, _ = self._remove_prev_newline(tlist, len(tlist.tokens) - 1)
                tlist.insert_before(tlist[-1], self.nl(1 if no_sgroups else 0))

        else:  # 进入括号后若不迭代，则不会再处理子组
            # process the inside of the parenthesis
            self._process_default(tlist, stmts=False)

    def _process_values(self, tlist):
        """VALUES 列表, 计算第2个元素偏移, 查找逗号进行换行对齐"""
        # values列表已经组合为identifierlist，不需要单独处理
        self._process_default(tlist)

    def _process_identifierlist(self, tlist):
        # columns being selected, 也处理了如with列表， values列表
        # case 中的括号值列表不处理
        if tlist.within(sql.Case) and tlist.parent and isinstance(tlist.parent, sql.Parenthesis):
            self._process_function(tlist)
            return

        # 判断是否在函数调用的括号内（如 explode(...)），这类不做 AS/逗号对齐
        # 判断依据：父括号内不含 DML/DDL（即不是子查询括号），且不在 INSERT 语句中
        in_func_paren = False
        if isinstance(tlist.parent, sql.Parenthesis):
            _, has_dml = tlist.parent.token_next_by(t=(T.DML, T.DDL))
            if not has_dml and self._curr_stmt.get_type() != "INSERT":
                in_func_paren = True

        # lateral view 后的列列表不做换行对齐，保持同行
        if plist := tlist.parent:
            pidx = plist.token_index(tlist)
            _, prev_ = plist.token_prev(pidx, skip_cm=True)
            if prev_ and prev_.match(T.Keyword, r"LATERAL\s+VIEW", regex=True):
                self._process_default(tlist, stmts=False)
                return

        offset = self._get_offset(tlist[0])
        # WITH列表，取WITH后的第一个token的偏移
        if plist := tlist.parent:
            pidx = plist.token_index(tlist)
            _, prev_ = plist.token_prev(pidx, skip_cm=True)
            if prev_:
                if prev_.ttype is T.CTE:
                    offset = self._get_offset(plist[0])
                if plist := plist.parent:
                    pidx = plist.token_index(tlist.parent)
                    _, prev_ = plist.token_prev(pidx, skip_cm=True)
                    if prev_ and prev_.match(T.Keyword, "IN") and isinstance(tlist, sql.IdentifierList):
                        self._process_default(tlist, stmts=False)
                        return

        identifiers = list(tlist.get_identifiers())
        if identifiers[0] == tlist[0]:  # select后的第一个token不需要对齐
            identifiers.pop(0)
        # 对齐当前组合的首个
        for _, token in enumerate(identifiers):
            if not (
                token.match(T.Keyword, self.join_words, regex=True) or token.match(T.Keyword, self.by_words, regex=True)
            ):
                # 先删除前边紧邻空白中的换行
                _, _ = self._remove_prev_newline(tlist, tlist.token_index(token))
                tlist.insert_before(token, self.nl(offset))
        self._process_default(tlist, stmts=False)
        # 新增对齐逻辑
        self._align_identifierlist(list(tlist.get_identifiers()))

    def _process_case(self, tlist):
        # 先处理为深度遍历，后处理为广度遍历，处理注释换行
        self._process_default(tlist, stmts=False)

        # 为了计算注释换行后长度，需要考虑到行首的全部偏移
        case_offset = self._get_offset(tlist.token_first(), relative=False)
        offset_ = len("case ")
        cases = tlist.get_cases()  # 跳过空白后注释的换行无法识别
        # align the end as well
        end_token = tlist.token_next_by(m=(T.Keyword, "END"))[1]
        cases.append((None, [end_token]))

        # 考虑换行.split(self.n, 1)[0]
        condition_width = []
        max_cond_width = 0
        for cond, _ in cases:
            if cond:
                cond_ = "".join(map(str, cond)).split(self.n)
                cond_len = 0
                for i, c in enumerate(cond_):  # 有多行的后续行考虑when及空格的对齐长度
                    if i > 0:
                        # 深度遍历时：有换行的需要扣除偏移前的空白长度 - case_offset - offset_
                        # 广度遍历时：注释换行都在行首+1，加上换行缩进长度 + offset_
                        cond_len = len(c.encode("gbk")) - case_offset - offset_
                    else:
                        cond_len = len(c.encode("gbk"))
                    max_cond_width = max(max_cond_width, cond_len)
                condition_width.append(cond_len)
            else:
                condition_width.append(0)
        # condition_width = [len(' '.join(map(str, cond)).encode('gbk'))
        #                    if cond else 0 for cond, _ in cases]

        # 添加本层新增偏移
        case_offset = self._get_offset(tlist.token_first())
        with offset(self, case_offset):
            for i, (cond, value) in enumerate(cases):
                # cond is None when 'end'
                stmt = cond[0] if cond else value[0]
                # 记录value的原始偏移
                if i < len(cases) - 1 and len(value) > 1:
                    ws_ = self._get_offset(value[1], relative=False)
                else:
                    ws_ = None

                if i > 0:  # 换行并对齐when的左侧
                    _, _ = self._remove_prev_newline(tlist, tlist.token_index(stmt))
                    cond_offset = offset_ if i < len(cases) - 1 else 0
                    tlist.insert_before(stmt, self.nl(cond_offset))

                if cond:  # 补齐when条件长度，即对齐then的左侧
                    ws = max_cond_width - condition_width[i]
                    if ws:
                        tlist.insert_after(cond[-1], sql.Token(T.Whitespace, self.char * ws))
                elif value[0] != "" and value[0].match(T.Keyword, "ELSE"):  # 补齐else前的空格长度，也对齐then
                    ws = max_cond_width
                    tlist.insert_after(value[0], sql.Token(T.Whitespace, self.char * ws))

                if ws_:
                    # value有换行的需要同步添加对齐空白，通过原始偏移计算
                    ws_ = self._get_offset(value[1], relative=False) - ws_
                    for tk in sql.TokenList(value).flatten():
                        if tk.is_whitespace and tk.value.startswith(self.n):
                            tk.value = self.n + self.char * (len(tk.value) - 1 + ws_)

    def _process_function(self, tlist):
        # 函数单独处理，识别嵌套的强制换行注释
        for sgroup in tlist.get_sublists():
            if sgroup.is_group:
                self._process_function(sgroup)
            if isinstance(sgroup, sql.Comment):
                self._process_comment(sgroup)

    def _process_comment(self, tlist):
        # 深度遍历时的注释要基于父对象处理，在后一token前换行，含新增的强制换行

        # 不处理行首注释，只处理需要换行的单行注释和强制换行
        # 括号带有缩进，获取偏移时是自动换行的只有一个空白，改为不考虑相对偏移
        if self._get_offset(tlist, relative=False) == 0 or (
            not tlist.value.rstrip() == "/*-*/" and not tlist.value.startswith("--")
        ):
            return

        # 取父对象及在父对象中的位置
        plist = tlist.parent
        # while isinstance(plist, sql.Comment):
        #     plist, tlist = plist.parent, plist
        pidx = plist.token_index(tlist)

        # 单行注释后的空换行会被合并，--x\n\n\n变为'--x\n',' ',''
        # 空格影响后边连续换行注释的行首判断，newline无法删除，故倒序遍历替换为空字符
        for idx in range(len(tlist.tokens) - 1, -1, -1):
            if tlist.tokens[idx].is_newline:
                tlist.tokens[idx].value = ""
            else:  # 倒序遇到非newline退出
                break

        n_ = 0  # 默认缩进层级
        offset_ = 0  # 默认整体偏移

        # 特殊情况的偏移
        pidx_, prev_ = plist.token_prev(pidx, skip_cm=True)
        nidx_, next_ = plist.token_next(pidx, skip_cm=True)

        if (
            next_
            and isinstance(next_, sql.Over)
            or isinstance(plist, sql.Case)
            and next_
            and not next_.match(T.Keyword, ["WHEN", "ELSE", "END"])
        ):
            # over前换行，case条件中换行，则增加缩进
            n_ = 1

        # 是select后首个注释
        if prev_ and prev_.match(T.DML, "SELECT"):
            offset_ = self._get_offset(tlist)
        # 前一token是identifierlist, 取identifierlist的偏移
        # 与over括号中的identifierlist重叠，需排除
        elif prev_ and isinstance(prev_, sql.IdentifierList) and not prev_.within(sql.Over):
            offset_ = self._get_offset(prev_)
        # 子查询前的单行注释对齐，对齐子查询左侧
        elif next_ and (next_.match(T.DML, "SELECT") or next_.ttype is T.CTE):
            offset_ = self._get_offset(next_)
        # case中，在end前的单行注释对齐when左侧
        elif isinstance(plist, sql.Case):
            # 取其后一token的偏移，注意当前是在as对齐之前
            if next and not next_.match(T.Keyword, ["END"]):
                nnext_, _ = plist.token_next_by(m=plist.M_OPEN)
                if nnext_ is not None:
                    offset_ = self._get_offset(plist.token_next(nnext_, skip_cm=False)[1])
            # 否则取父对象首个token的偏移，不跳过注释 skip_cm=True
            else:
                offset_ = self._get_offset(plist.token_first())
        # 父对象是括号、Over，取其后一token的偏移，注意当前是在as对齐之前
        elif hasattr(plist, "M_OPEN"):
            nnext_, _ = plist.token_next_by(m=plist.M_OPEN)
            if nnext_ is not None:
                offset_ = self._get_offset(plist.token_next(nnext_, skip_cm=True)[1])
        else:
            pprev_ = None
            if plist.parent:
                _, pprev_ = plist.parent.token_prev(plist.parent.token_index(plist), skip_cm=True)
            # with列表中的注释，取父对象的首个token的偏移
            if pprev_ and pprev_.ttype is T.CTE:
                offset_ = self._get_offset(pprev_)
            # 否则取父对象首个token的偏移，不跳过注释 skip_cm=True
            else:
                offset_ = self._get_offset(plist.token_first())

        # 设置缩进层级
        with indent(self, n_):
            # 设置前置偏移
            with offset(self, offset_):
                # 判断前边紧挨的token情况
                _, prev_ = plist.token_prev(pidx, skip_ws=False)
                if prev_ and prev_.is_newline:
                    # 行首不处理，且将行首的newline从空白转回换行
                    prev_.value = self.n
                    return
                # 紧贴前边的增加一个空格，行首不处理
                if pidx > 0 and not prev_.is_whitespace:
                    plist.insert_before(pidx, sql.Token(T.Whitespace, " "))
                    pidx += 1
                # 判断前边紧挨的非空白token情况
                _, prev_ = plist.token_prev(pidx)
                # 关键字后的注释，不处理
                if prev_ and prev_.match(T.Keyword, self.split_words, regex=True):
                    return
                # 前边是有换行的，重新对齐换行
                if pidx > 0 and prev_.value.rstrip(" ").endswith(self.n):
                    pidx, _ = self._remove_prev_newline(plist, pidx)
                    plist.insert_before(pidx, self.nl(offset=0))
                    pidx += 1

                # 注释是当前层级最后一个token
                if plist and plist[-1] == tlist:
                    return
                # 判断后边紧挨的token情况
                _, next_ = plist.token_next(pidx, skip_ws=False)
                if next_ and next_.value.startswith(self.n):
                    # 开头为换行则不处理，是之前添加的换行对齐
                    return
                # 判断后边紧挨的非空白token情况, 若是注释则留到下次遍历处理，否则影响行首判断
                nidx_, next_ = plist.token_next(pidx)
                if next_ and not isinstance(next_, sql.Comment):
                    pidx, _ = self._remove_prev_newline(plist, nidx_)
                    plist.insert_before(pidx, self.nl(offset=0))
                    pidx += 1

    # ====添加的列表对刘处理
    def _align_identifierlist(self, tlist):
        """字段列表对齐，逗号对齐"""

        as_lists = []
        as_placehold = 0
        max_as_offset = 0
        max_alias_len = 0

        # 收集所有别名位置
        for token in tlist:
            # 查找identifier # 有子组，但不是括号、case、函数等
            if token.is_group and not hasattr(token, "M_OPEN"):
                nidx, _ = token.token_next(idx=-1, skip_cm=True)  # 占位，防止order by中 a desc将a取为alias
                _, alias = token.token_next_by(idx=nidx, i=sql.Identifier)
                _, as_tk = token.token_next_by(m=(T.Keyword, "AS"))
            else:  # 无子组的，如 *
                alias, as_tk = None, None

            if as_tk:
                as_placehold = 3  # 只要存在as，就保留 as的宽度
                as_offset = self._get_offset(as_tk)
            elif alias:
                as_offset = self._get_offset(alias)
            else:  # as和alias都没有时，计算长度也要多1个空格。取token.value丢失了原始换行
                as_offset = self._get_offset(token) + 1 + len(str(token).splitlines()[-1].encode("gbk"))
            # 计算AS关键字前的最大长度, 限制最多120个字符
            max_as_offset = min(120, max(max_as_offset, as_offset))
            alias_len = len(str(alias).encode("gbk"))
            max_alias_len = max(max_alias_len, alias_len if alias else 0)
            as_lists.append((as_offset, as_tk, alias_len, alias))

        # 二次遍历进行对齐
        for token, (as_offset, as_tk, alias_len, alias) in zip(tlist, as_lists):
            # as对齐：有as的在as前添加，没有as的在identifier前添加, 都没有的加在最后
            as_ws = max_as_offset - as_offset
            if as_tk:
                if as_ws:
                    token.insert_before(as_tk, sql.Token(T.Whitespace, self.char * as_ws))
            else:
                as_ws += as_placehold
                if as_ws:
                    if alias:
                        token.insert_before(alias, sql.Token(T.Whitespace, self.char * as_ws))
                    elif token.is_group:
                        token.insert_after(token[-1], sql.Token(T.Whitespace, self.char * as_ws))
                    else:
                        token.parent.insert_after(token, sql.Token(T.Whitespace, self.char * as_ws))
            # 逗号对齐，列表有alias时才处理，没有alias的添加一个前置空格
            if max_alias_len:
                alias_ws = max_alias_len + (-alias_len if alias else 1)
                if as_offset > max_as_offset:  # 再扣除超长的部分
                    alias_ws = max(0, alias_ws - (as_offset - max_as_offset))
                if token == tlist[-1]:
                    alias_ws += 1  # 添加末尾逗号的宽度
                if alias_ws:
                    if token.is_group:
                        token.insert_after(token[-1], sql.Token(T.Whitespace, self.char * alias_ws))
                    else:
                        token.parent.insert_after(token, sql.Token(T.Whitespace, self.char * alias_ws))

    def _align_create_columns(self, tlist):
        """Create Insert 语句中字段定义的对齐处理, 列表首位已对齐

        查找, 对字段名、数据类型、约束条件、默认值、注释分别对齐
        例如:
        CREATE TABLE test (
            id          INTEGER     PRIMARY KEY                           comment '注释',
            name        VARCHAR(50) NOT NULL,
            created_at  TIMESTAMP               DEFAULT CURRENT_TIMESTAMP
        )
        """
        field_lines = []  # 存储字段行信息

        # 收集字段信息
        last_flag = True  # 是否未处理最后一个字段
        prev_idx = 0  # 上一次查找起点
        end_idx, token = tlist.token_next_by(m=(T.Punctuation, ","), idx=prev_idx)
        while end_idx:
            field_line = []  # 存储字段行信息
            # 字段identifier, 肯定存在
            idx, token_ = tlist.token_next(idx=prev_idx, skip_cm=True)
            if idx:
                prev_idx = idx
            field_line.append(token_)

            # 查找类型, 如varchar(2)当前组合为函数了
            idx, token_ = tlist.token_next_by(idx=prev_idx, end=end_idx, t=T.Name.Builtin, i=sql.Function)
            if idx:
                prev_idx = idx
            field_line.append(token_)

            # 查找约束
            idx, token_ = tlist.token_next_by(
                idx=prev_idx, end=end_idx, m=(T.Keyword, ["NOT NULL", "NULL", "PRIMARY KEY"])
            )
            if idx:
                prev_idx = idx
            field_line.append(token_)

            # 查找默认值
            idx, token_ = tlist.token_next_by(idx=prev_idx, end=end_idx, m=(T.Keyword, ["DEFAULT"]))
            if idx:
                prev_idx = idx
            field_line.append(token_)

            # 查找注释
            idx, token_ = tlist.token_next_by(idx=prev_idx, end=end_idx, m=(T.Keyword, "COMMENT"))
            if idx:
                prev_idx = idx
            field_line.append(token_)

            # 记录逗号位置，兜底，清理空白
            _, _ = self._remove_prev_newline(tlist, end_idx)
            field_line.append(token)
            field_lines.append(field_line)

            prev_idx = end_idx  # 更新查找起点
            end_idx, token = tlist.token_next_by(m=(T.Punctuation, ","), idx=prev_idx)
            if not end_idx and last_flag:  # 处理最后一个字段
                end_idx, token = len(tlist.tokens) - 1, tlist.tokens[-1]
                last_flag = False

        # 应用对齐，对tlist的切片修改无效, 处理前置空白更合理，元素不一定存在
        field_cols = list(zip(*field_lines))  # 解包为字段行列表
        for j, col in enumerate(field_cols):  # 按元素列遍历, 最后一列是兜底的逗号
            tokens = []
            max_offset = 0
            # 从每行中解出当前列开始的元素切片, 过滤掉None值，再取首个元素
            for line in field_lines:
                tokens.append(next((t for t in line[j:] if t), None))
                # 使用了后一元素的，添加1个空白长度
                max_offset = max(max_offset, self._get_offset(tokens[-1]) + (0 if line[j] else 1))
            # 如果col全是None，则扣减不必要的空白长度
            if all(not t for t in col):
                max_offset -= 1

            for i, tk in enumerate(tokens):  # 按行遍历，元素列表位置即行位置
                # 从当前索引的位置开始, 遍历后续token, 过滤掉None值 直到找到第一个有效token
                offset = self._get_offset(tk)
                ws = max_offset - offset
                if ws > 0:
                    tlist.insert_before(tk, sql.Token(T.Whitespace, self.char * ws))

    # ====以上为ttype预处理
    def _next_token(self, tlist, idx=-1):
        """使用match查找匹配T.Keyword, self.split_words的token, 启用正则匹配"""
        split_words = T.Keyword, self.split_words, True
        tidx, token = tlist.token_next_by(m=split_words, idx=idx)
        # treat "BETWEEN x and y" as a single statement
        if token and token.normalized == "BETWEEN":
            tidx, token = self._next_token(tlist, tidx)
            if token and token.normalized == "AND":
                tidx, token = self._next_token(tlist, tidx)

        return tidx, token

    def _split_kwds(self, tlist):
        # 遍历关键字, _next_token查找匹配T.Keyword,self.split_words的关键字token

        tidx, token = self._next_token(tlist)
        token_notkey_ = None
        first_keyword = None
        if token:  # 首个关键字后接单行注释的情况，需要特殊处理
            first_keyword = token
            _, next_ = tlist.token_next(tidx)
            if next_ and next_.value.startswith("--") and next_.value.endswith(self.n):
                _, token_notkey_ = tlist.token_next(tidx, skip_cm=True)
        while token:
            # joins, group/order by, lateral view are special case. only consider the first
            # word as aligner
            if (
                token.match(T.Keyword, self.join_words, regex=True)
                or token.match(T.Keyword, self.by_words, regex=True)
                or token.match(T.Keyword, r"LATERAL\s+VIEW", regex=True)
            ):
                token_indent = token.value.split()[0]
            elif token is token_notkey_:
                token_indent = 1
            else:
                token_indent = token.value

            # 插入包括缩进处理, 直接跳过就缺少了缩进, 所以先删除前边紧邻空白中的换行
            tidx, _ = self._remove_prev_newline(tlist, tidx)
            # token_indent表示关键字占用的缩进, 会被扣除掉
            tlist.insert_before(token, self.nl(token_indent))

            tidx += 1
            if token_notkey_ and token is first_keyword:
                # 关键字后为换行注释，直接跳到下一个非注释token
                tidx, token = tlist.token_index(token_notkey_), token_notkey_
            else:
                tidx, token = self._next_token(tlist, tidx)

    def _split_statements(self, tlist):
        ttypes = T.CTE, T.Keyword.DML, T.Keyword.DDL
        # tidx为当前处理的token的索引, token为当前处理的token对象
        tidx, token = tlist.token_next_by(t=ttypes)
        while token:
            # 插入换行带有缩进, 所以先删除前边紧邻空白中的换行, 再插入
            tidx, ws_ = self._remove_prev_newline(tlist, tidx)
            if ws_:  # 首行不缩进，回退，非根节点
                tlist.insert_before(tidx, self.nl("SELECT"))
                tidx += 1
            tidx, token = tlist.token_next_by(t=ttypes, idx=tidx)

    def _process_default(self, tlist, stmts=True):
        # 遍历DDL、DML, 遍历self.split_words关键字, 然后遍历子查询
        with indent(self):
            self._split_statements(tlist) if stmts else None
            self._split_kwds(tlist) if stmts else None
        # 子组会在后续迭代中进入，不能放到缩进内，比如statement第一次进入，where就会作为子组
        # process any sub-sub statements 在sgroup前插入token后，sgroup会再次进入
        sgroup_prev = None
        for sgroup in tlist.get_sublists():
            if sgroup is sgroup_prev:
                continue
            sgroup_prev = sgroup
            idx = tlist.token_index(sgroup)
            _, prev_ = tlist.token_prev(idx, skip_cm=True)
            # HACK: make "group/order by" work. Longer than max_len.
            offset_ = 3 if (prev_ and prev_.match(T.Keyword, self.by_words, regex=True)) else 0
            with offset(self, offset_):
                self._process(sgroup)

    def _process(self, tlist):
        # 先按tlist类型预处理, 然后到default通用处理（遍历子查询）
        func_name = "_process_{cls}".format(cls=type(tlist).__name__.lower())
        # 获取self对象中名为func_name的方法, 如果不存在, 则返回self._process_default方法
        func = getattr(self, func_name, self._process_default)
        func(tlist)
        # if __debug__: print('='*8+func_name+'\n'+str(self._curr_stmt), flush=True)
        pass

    def process(self, stmt):
        # 处理入口
        self._curr_stmt = stmt
        self._process(stmt)
        return stmt
