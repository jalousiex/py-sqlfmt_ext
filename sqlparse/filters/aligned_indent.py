#
# Copyright (C) 2009-2020 the sqlparse authors and contributors
# <see AUTHORS file>
#
# This module is part of python-sqlparse and is released under
# the BSD License: https://opensource.org/licenses/BSD-3-Clause

from sqlparse import keywords_list, sql
from sqlparse import tokens as T
from sqlparse.utils import imt, indent, offset


class AlignedIndentFilter:
    join_words = keywords_list.join_words
    by_words = keywords_list.by_words
    split_words = keywords_list.split_words

    def __init__(self, char=" ", n="\n", align_list=False, comma_first=False):
        self.n = n
        self.offset = 0  # Token级对齐偏移
        self.indent = 0  # TokenList级关键字缩进
        self.char = char
        self.align_list = align_list
        self.comma_first = comma_first
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
        """删除 tidx 前空白及尾换行，始终返回本层更新后的索引和前一 token。"""
        while True:
            pidx, prev_ = tlist.token_prev(tidx, skip_ws=False)
            if not prev_ or not prev_.is_whitespace:
                break
            del tlist.tokens[pidx]
            tidx -= 1

        if prev_ is None:
            if tlist.parent:
                self._remove_prev_newline(tlist.parent, tlist.parent.token_index(tlist))
        elif prev_.value.rstrip(" ").endswith(self.n):
            if prev_.is_group:
                self._remove_prev_newline(prev_, len(prev_.tokens))
            else:
                prev_.value = prev_.value.rstrip()

        # TokenList.value 是缓存字符串，子 group 发生变更后需同步刷新。
        tlist.value = str(tlist)
        return tidx, prev_

    @staticmethod
    def _collapse_newlines(tlist):
        """把 tlist 直接子级中含换行的空白 token 就地折叠为单空格（保持同行）。"""
        for tk in tlist.tokens:
            if tk.is_whitespace and "\n" in tk.value:
                tk.value = " "

    def _collapse_newline(self, token, prev_token=None):
        """折叠非注释边界的空白换行，返回是否已处理。"""
        if not token.is_whitespace or self.n not in token.value:
            return False
        if prev_token is not None and imt(prev_token, t=T.Comment, i=sql.Comment):
            return False
        token.value = " "
        return True

    def _pull_inline(self, group, anchor, after=False):
        """折叠 anchor 一侧相邻的换行空白，使被折叠内容回到 anchor 同一行。"""
        idx = group.token_index(anchor)
        whitespace_indexes = []
        while True:
            idx, ws = (group.token_next if after else group.token_prev)(idx, skip_ws=False)
            if not ws or not ws.is_whitespace:
                break
            whitespace_indexes.append(idx)

        if not any(self.n in group.tokens[index].value for index in whitespace_indexes):
            return

        for index in sorted(whitespace_indexes, reverse=True):
            del group.tokens[index]
        inserter = group.insert_after if after else group.insert_before
        inserter(anchor, sql.Token(T.Whitespace, " "))

    def _prev_non_whitespace(self, tlist, tidx):
        """返回 tidx 前的首个非空白 token，以及连续空白中是否包含换行。"""
        has_nl = False
        while True:
            pidx, prev_ = tlist.token_prev(tidx, skip_ws=False)
            if not prev_ or not prev_.is_whitespace:
                return pidx, prev_, has_nl
            has_nl = has_nl or self.n in prev_.value
            tidx = pidx

    @staticmethod
    def _is_lateral_view_list(tlist):
        """判断 IdentifierList 是否是 LATERAL VIEW 后的列列表。"""
        plist = tlist.parent
        if not plist:
            return False
        pidx = plist.token_index(tlist)
        vidx, prev_ = plist.token_prev(pidx, skip_cm=True)
        if prev_ and prev_.match(T.Keyword, "VIEW"):
            _, prev2_ = plist.token_prev(vidx, skip_cm=True)
            return bool(prev2_ and prev2_.match(T.Keyword, "LATERAL"))
        return bool(prev_ and prev_.match(T.Keyword, r"LATERAL\s+VIEW", regex=True))

    def _take_comments_before(self, tlist, tidx):
        """移除 tidx 前连续空白和注释，返回原顺序的注释。"""
        comments = []
        idx = tidx
        while idx > 0:
            idx, token = tlist.token_prev(idx, skip_ws=False)
            if token is None:
                break
            if isinstance(token, sql.Comment):
                token.value = token.value.rstrip()
                if token.tokens and token.tokens[-1].value.endswith(self.n):
                    token.tokens[-1].value = token.tokens[-1].value.rstrip()
                comments.insert(0, token)
                continue
            if not token.is_whitespace:
                break

        idx = tidx
        while idx > 0:
            idx, token = tlist.token_prev(idx, skip_ws=False)
            if not token or not (token.is_whitespace or isinstance(token, sql.Comment)):
                break
            del tlist.tokens[idx]
        return comments

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

        # lateral view 后的列列表不做换行对齐，保持同行
        if self._is_lateral_view_list(tlist):
            # lateral view 后的列列表保持同行，仅折叠已有换行
            self._collapse_newlines(tlist)
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
            # 首字段前（leading keyword 后）若有换行，折叠为单空格，使其回到同一行
            if plist := tlist.parent:
                lidx = plist.token_index(tlist)
                _, lead, found_nl = self._prev_non_whitespace(plist, lidx)
                # 仅当前导是 DML 关键字(如 select)时折叠，避免影响 INSERT 括号内字段列表
                if found_nl and lead is not None and lead.ttype is T.DML:
                    self._remove_prev_newline(plist, lidx)
                    plist.insert_before(tlist, sql.Token(T.Whitespace, " "))
                    offset = self._get_offset(tlist[0])

        if self.comma_first:
            # 逗号在行首模式：在每个逗号前换行，注释移到 identifier 后
            cf_offset = len(self.leading_kwd)
            # 第一遍：收集注释并清除空白，在逗号前换行
            comment_map = {}  # id(identifier) -> [comments]
            for i, token in enumerate(identifiers):
                if token.match(T.Keyword, self.join_words, regex=True) or token.match(
                    T.Keyword, self.by_words, regex=True
                ):
                    continue
                tidx = tlist.token_index(token)
                # 找前一个逗号
                _, comma = tlist.token_prev(tidx, skip_cm=True)
                if not (comma and comma.match(T.Punctuation, ",")):
                    continue
                cidx = tlist.token_index(comma)
                comments = self._take_comments_before(tlist, cidx)
                if comments:
                    # 注释属于前一个 identifier；i==0 时属于被 pop 的首个 identifier
                    prev_identifier = identifiers[i - 1] if i > 0 else tlist[0]
                    comment_map[id(prev_identifier)] = comments
                # 在逗号前插入换行
                tlist.insert_before(comma, self.nl(cf_offset))

            # 第二遍：把注释附加到对应 identifier 后（含被 pop 的首个 identifier）
            all_identifiers = [tlist[0]] + identifiers
            for token in all_identifiers:
                for c in comment_map.get(id(token), []):
                    if token.is_group:
                        token.insert_after(token[-1], sql.Token(T.Whitespace, " "))
                        token.insert_after(token[-1], c)
                    else:
                        tlist.insert_after(token, sql.Token(T.Whitespace, " "))
                        tlist.insert_after(token, c)

            self._process_default(tlist, stmts=False)
        else:
            # 默认模式：在每个 identifier 前换行
            for _, token in enumerate(identifiers):
                if not (
                    token.match(T.Keyword, self.join_words, regex=True)
                    or token.match(T.Keyword, self.by_words, regex=True)
                ):
                    tidx = tlist.token_index(token)
                    _, _ = self._remove_prev_newline(tlist, tidx)
                    tlist.insert_before(token, self.nl(offset))
            self._process_default(tlist, stmts=False)
            # 对齐逻辑：仅 align_list 开启时执行
            if self.align_list:
                self._align_identifierlist(list(tlist.get_identifiers()))

    def _fold_case_newlines(self, tokens):
        """折叠 when/then 内容中非注释强制的换行为单空格，注释前的换行是语法所需，保留。

        Operation（如 ``a || b``）不会被其它流程单独重新缩进，需递归展开处理。
        """
        prev_tok = None
        for tk in tokens:
            if tk == "":  # get_cases 中用于占位的空字符串
                continue
            if self._collapse_newline(tk, prev_tok):
                continue
            elif isinstance(tk, sql.Operation):
                self._fold_case_newlines(tk.tokens)
            if not tk.is_whitespace:
                prev_tok = tk

    def _case_condition_widths(self, cases, case_offset, offset):
        """计算各 CASE 条件宽度和最大宽度，供 THEN/ELSE 对齐使用。"""
        widths = []
        max_width = 0
        for cond, _ in cases:
            cond_len = 0
            if cond:
                for index, line in enumerate("".join(map(str, cond)).split(self.n)):
                    if index:
                        cond_len = len(line.encode("gbk")) - case_offset - offset
                    else:
                        cond_len = len(line.encode("gbk"))
                    max_width = max(max_width, cond_len)
            widths.append(cond_len)
        return widths, max_width

    def _process_case(self, tlist):
        # 先处理为深度遍历，后处理为广度遍历，处理注释换行
        self._process_default(tlist, stmts=False)

        # 为了计算注释换行后长度，需要考虑到行首的全部偏移
        case_offset = self._get_offset(tlist.token_first(), relative=False)
        offset_ = len("case ")
        cases = tlist.get_cases()  # 跳过空白后注释的换行无法识别
        # 折叠 when/then 中非注释强制的换行，避免遗留原始输入的随意折行
        for cond, value in cases:
            if cond:
                self._fold_case_newlines(cond)
            self._fold_case_newlines(value)
        # align the end as well
        end_token = tlist.token_next_by(m=(T.Keyword, "END"))[1]
        cases.append((None, [end_token]))

        condition_width, max_cond_width = self._case_condition_widths(cases, case_offset, offset_)

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
                else:
                    # 首个when：仅当原始输入在case后直接换行（无注释）时才重新对齐，
                    # 否则保持原有的同行/注释强制换行不变（含占位空字符串场景）
                    if stmt != "":
                        tidx_stmt = tlist.token_index(stmt)
                        _, prev_tok, has_nl = self._prev_non_whitespace(tlist, tidx_stmt)
                        direct_after_case = bool(prev_tok and prev_tok.match(T.Keyword, "CASE"))
                        if has_nl and direct_after_case:
                            _, _ = self._remove_prev_newline(tlist, tidx_stmt)
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

        # comma_first 模式下，IdentifierList 中的注释已由 _process_identifierlist 处理，跳过
        if self.comma_first and isinstance(tlist.parent, sql.IdentifierList):
            return

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
    def _set_adjacent_ws(self, container, ref, width, after=False):
        """将 ref 一侧的同行空白替换为固定宽度，而非叠加。"""
        idx = container.token_index(ref)
        adjacent = container.token_next if after else container.token_prev
        ws_idx, ws = adjacent(idx, skip_ws=False)
        if ws and ws.is_whitespace and self.n not in ws.value:
            if width > 0:
                ws.value = self.char * width
            else:
                del container.tokens[ws_idx]
        elif width > 0:
            inserter = container.insert_after if after else container.insert_before
            inserter(ref, sql.Token(T.Whitespace, self.char * width))

    def _identifier_layout(self, token):
        """解析列表项的 AS/别名位置，并折叠 AS 两侧的非必要换行。"""
        alias = as_tk = None
        if token.is_group and not hasattr(token, "M_OPEN"):
            nidx, _ = token.token_next(idx=-1, skip_cm=True)
            _, alias = token.token_next_by(idx=nidx, i=sql.Identifier)
            _, as_tk = token.token_next_by(m=(T.Keyword, "AS"))
            if as_tk and alias is None:
                _, next_tk = token.token_next(token.token_index(as_tk), skip_cm=True)
                if next_tk is not None and next_tk.ttype is T.Keyword:
                    alias = next_tk
            if as_tk:
                self._pull_inline(token, as_tk, after=False)
                self._pull_inline(token, as_tk, after=True)

        if as_tk:
            as_offset = self._get_offset(as_tk)
        elif alias:
            as_offset = self._get_offset(alias)
        else:
            as_offset = self._get_offset(token) + 1 + len(str(token).splitlines()[-1].encode("gbk"))
        return as_offset, as_tk, len(str(alias).encode("gbk")), alias

    def _identifier_layouts(self, tlist):
        """解析列表布局并汇总 AS、别名列的目标宽度。"""
        layouts = []
        as_placehold = 0
        max_as_offset = 0
        max_alias_len = 0
        for token in tlist:
            layout = self._identifier_layout(token)
            as_offset, as_tk, alias_len, alias = layout
            if as_tk:
                as_placehold = 3
            max_as_offset = min(120, max(max_as_offset, as_offset))
            max_alias_len = max(max_alias_len, alias_len if alias else 0)
            layouts.append(layout)
        return layouts, as_placehold, max_as_offset, max_alias_len

    def _apply_identifier_layout(self, token, layout, max_as_offset, max_alias_len, as_placehold, is_last):
        """按已汇总的列宽设置单个列表项的 AS、别名和逗号前空白。"""
        as_offset, as_tk, alias_len, alias = layout
        as_ws = max_as_offset - as_offset
        trailing_extra = 0
        if as_tk:
            self._set_adjacent_ws(token, as_tk, max(1, 1 + as_ws))
        else:
            as_ws += as_placehold
            if alias:
                self._set_adjacent_ws(token, alias, max(1, 1 + as_ws))
            else:
                trailing_extra = max(0, as_ws)

        if not self.comma_first and max_alias_len:
            alias_ws = max_alias_len + (-alias_len if alias else 1)
            if as_offset > max_as_offset:
                alias_ws = max(0, alias_ws - (as_offset - max_as_offset))
            if is_last:
                alias_ws += 1
            alias_ws += trailing_extra
        else:
            alias_ws = trailing_extra

        if not alias_ws:
            return
        if token.is_group:
            self._set_adjacent_ws(token, token[-1], alias_ws, after=True)
        else:
            self._set_adjacent_ws(token.parent, token, alias_ws, after=True)

    def _align_identifierlist(self, tlist):
        """字段列表对齐，逗号对齐"""
        layouts, as_placehold, max_as_offset, max_alias_len = self._identifier_layouts(tlist)
        for token, layout in zip(tlist, layouts):
            self._apply_identifier_layout(
                token,
                layout,
                max_as_offset,
                max_alias_len,
                as_placehold,
                token == tlist[-1],
            )

    def _create_field_lines(self, tlist):
        """收集 DDL/INSERT 字段定义的名称、类型、约束、默认值、注释和结尾 token。"""
        field_lines = []
        last_field = True
        prev_idx = 0
        end_idx, end_token = tlist.token_next_by(m=(T.Punctuation, ","), idx=prev_idx)
        while end_idx:
            field_line = []
            for token_type in (
                {},
                {"t": T.Name.Builtin, "i": sql.Function},
                {"m": (T.Keyword, ["NOT NULL", "NULL", "PRIMARY KEY"])},
                {"m": (T.Keyword, ["DEFAULT"])},
                {"m": (T.Keyword, "COMMENT")},
            ):
                if token_type:
                    idx, token = tlist.token_next_by(idx=prev_idx, end=end_idx, **token_type)
                else:
                    idx, token = tlist.token_next(idx=prev_idx, skip_cm=True)
                if idx:
                    prev_idx = idx
                field_line.append(token)

            _, _ = self._remove_prev_newline(tlist, end_idx)
            field_line.append(end_token)
            field_lines.append(field_line)

            prev_idx = end_idx
            end_idx, end_token = tlist.token_next_by(m=(T.Punctuation, ","), idx=prev_idx)
            if not end_idx and last_field:
                end_idx, end_token = len(tlist.tokens) - 1, tlist.tokens[-1]
                last_field = False
        return field_lines

    def _create_column_target(self, field_lines, index, column):
        """计算一个 DDL 字段列的 token 和目标偏移。"""
        tokens = [next((token for token in line[index:] if token), None) for line in field_lines]
        max_offset = max(
            self._get_offset(token) + (0 if line[index] else 1) for line, token in zip(field_lines, tokens)
        )
        if all(not token for token in column):
            max_offset -= 1
        return tokens, max_offset

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
        field_lines = self._create_field_lines(tlist)
        for index, column in enumerate(zip(*field_lines)):
            tokens, max_offset = self._create_column_target(field_lines, index, column)
            for tk in tokens:
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

    def _should_inline_after_keyword(self, tlist, tidx, token):
        """判断关键字后是否应折叠为同行（关键字 + 右侧表达式）。"""
        if token.match(T.Keyword, self.join_words, regex=True):
            return True
        if token.match(T.Keyword, self.by_words, regex=True):
            return True

        if token.match(T.Keyword, ["FROM", "WHERE", "HAVING"]):
            return True

        if token.match(T.Keyword, "ON"):
            _, next_ = tlist.token_next(tidx, skip_cm=True)
            if next_ and next_.match(T.Keyword, "COMMIT"):
                return False
            return True

        return False

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
            # SELECT * FROM / SELECT t.* FROM 不换行
            if token.normalized == "FROM" and self._is_simple_select_star(tlist, tidx):
                # 删除 FROM 前已有的换行，替换为普通空格
                tidx, _ = self._remove_prev_newline(tlist, tidx)
                pidx, prev_ = tlist.token_prev(tidx, skip_ws=False)
                if prev_ and not prev_.is_whitespace:
                    tlist.insert_before(tidx, sql.Token(T.Whitespace, " "))
                    tidx += 1
                # FROM 后若已存在换行，折叠为单空格
                self._pull_inline(tlist, token, after=True)
                tidx, token = self._next_token(tlist, tidx)
                continue

            # joins, group/order by, lateral view are special case. only consider the first
            # word as aligner
            if (
                token.match(T.Keyword, self.join_words, regex=True)
                or token.match(T.Keyword, self.by_words, regex=True)
                or token.match(T.Keyword, r"LATERAL\s+VIEW", regex=True)
            ):
                # 折叠 token 内部已有的换行（如 lexer 将 "left\n   join" 合并为单 token）
                if self.n in token.value:
                    token.value = " ".join(token.value.split())
                token_indent = token.value.split()[0]
            elif token is token_notkey_:
                token_indent = 1
            else:
                token_indent = token.value

            # 插入包括缩进处理, 直接跳过就缺少了缩进, 所以先删除前边紧邻空白中的换行
            tidx, _ = self._remove_prev_newline(tlist, tidx)
            # token_indent表示关键字占用的缩进, 会被扣除掉
            tlist.insert_before(token, self.nl(token_indent))

            # 某些子句要求“关键字 + 右侧”同行，清理关键字后的已有换行。
            if self._should_inline_after_keyword(tlist, tidx, token):
                self._pull_inline(tlist, token, after=True)

            tidx += 1
            if token_notkey_ and token is first_keyword:
                # 关键字后为换行注释，直接跳到下一个非注释token
                tidx, token = tlist.token_index(token_notkey_), token_notkey_
            else:
                tidx, token = self._next_token(tlist, tidx)

    @staticmethod
    def _is_simple_select_star(tlist, from_tidx):
        """检查 FROM 前是否只有 SELECT * / SELECT alias.* 的简单查询。"""
        # 收集 FROM 之前所有非空白、非注释 token
        prev_tokens = []
        pidx = from_tidx
        while True:
            pidx, pt = tlist.token_prev(pidx, skip_ws=True)
            if not pt:
                break
            prev_tokens.append(pt)
        # 反转恢复顺序
        prev_tokens.reverse()
        # 过滤掉无关 token
        meaningful = [t for t in prev_tokens if not t.is_whitespace and not imt(t, t=T.Comment, i=sql.Comment)]
        if len(meaningful) < 2:
            return False
        # 第一个必须是 SELECT
        if not meaningful[0].match(T.Keyword.DML, "SELECT"):
            return False
        # 其余 token 只能是 * 或 alias.* 模式
        values = [t.value for t in meaningful[1:]]
        joined = "".join(values)
        # 匹配 * 或 alias.*
        import re

        if re.fullmatch(r"\*|[A-Za-z_]\w*\.\*", joined):
            return True
        return False

    def _split_statements(self, tlist):
        ttypes = T.CTE, T.Keyword.DML, T.Keyword.DDL

        def is_alter_table_drop(token_):
            if not token_ or token_.normalized != "DROP":
                return False

            # 忽略行首注释，判断语句是否以 ALTER TABLE 开头
            heads = [tk for tk in tlist.tokens if not tk.is_whitespace and not imt(tk, t=T.Comment, i=sql.Comment)]
            if len(heads) < 3:
                return False

            return heads[0].match(T.Keyword.DDL, "ALTER") and heads[1].match(T.Keyword, "TABLE") and token_ in heads[2:]

        # tidx为当前处理的token的索引, token为当前处理的token对象
        tidx, token = tlist.token_next_by(t=ttypes)
        while token:
            # 插入换行带有缩进, 所以先删除前边紧邻空白中的换行, 再插入
            tidx, ws_ = self._remove_prev_newline(tlist, tidx)
            if ws_:
                if is_alter_table_drop(token):
                    tlist.insert_before(tidx, sql.Token(T.Whitespace, " "))
                    tidx += 1
                else:  # 首行不缩进，回退，非根节点
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
