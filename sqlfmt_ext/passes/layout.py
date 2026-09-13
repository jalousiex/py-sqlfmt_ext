"""断行骨架：本项目唯一的换行与缩进决策处。

本 pass 在官方 strip 之后运行。官方 strip 把所有空白（含换行）压成 ``''``/``' '``，
因此进入本 pass 时 token 流里**不含任何原始换行**——所有换行都由本 pass 按 token
结构决定，输出与输入空白无关。

这带来两个结构性好处：

* 收敛性不再依赖「擦除层」是否覆盖到某处：没有输入换行可泄漏；
* 旧实现里 ``_remove_prev_newline`` / ``_pull_inline`` / ``_normalize_newlines``
  这些函数不再是补丁，而是本 pass 管理**自己插入的空白**的固有工具。

对齐规则（同行空白宽度）见 ``align.py``，以 mixin 组合进来。
"""

import re

from sqlparse import sql
from sqlparse import tokens as T
from sqlparse.utils import imt, indent, offset

from .. import dialects, policy
from ..whitespace import merge_whitespace_runs
from .align import AlignMixin


class LayoutPass(AlignMixin):
    """断行 + 缩进骨架。

    只改写 ``Whitespace`` token 的值，不改 ttype、不改 token 顺序、不删除非空白
    token。
    """

    join_words = policy.join_words
    by_words = policy.by_words

    def __init__(self, options=None):
        opts = dict(options or {})
        self.n = "\n"
        self.char = opts.get("indent_char", " ")
        self.offset = 0  # Token级对齐偏移
        self.indent = 0  # TokenList级关键字缩进
        self.align_list = opts.get("align_list", True)
        self.comma_first = opts.get("comma_first", False)
        self.leading_kwd = "select"
        self._curr_stmt = None
        # 换行锚点词 = 通用词 + 方言追加词。**必须挂在实例上**：`policy.split_words` 是
        # 模块级元组，写成类属性就成了导入期快照，方言层后续追加的词永远看不到
        # （见 `PLAN §9.9`）。
        self.split_words = tuple(policy.split_words) + dialects.split_words_for(opts.get("dialect", "doris"))

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

    def _normalize_newlines(self, stmt):
        """折叠原始输入里无语义的换行，避免它们残留到格式化结果中。

        处理两类情况：
        1. lexer 合并的多词关键字/操作符 token 内部的换行（如 not null、not like）；
        2. 关键字之后紧跟的空白换行（如 exists 后的子查询、DDL 列定义里
           comment 与注释值之间、default 与默认值之间）。

        CASE 之后的换行决定 WHEN 是否另起一行，因此保持原样。
        """
        # commit 属 DML 关键字，_split_statements 会刻意让它另起一行（见 ddl/sqltest0_s04）
        # 白名单是**结构性**的：命中者一律按分词切开（`on` / `commit` 各占一行），
        # 输入写在一行时也这样切，否则输出会依赖输入空白。
        keep_newline = {"ON COMMIT"}
        prev_ = None
        for tk in stmt.flatten():
            if tk.is_whitespace:
                if (
                    self.n in tk.value
                    and prev_ is not None
                    and prev_.is_keyword
                    and not prev_.match(T.Keyword, "CASE")
                ):
                    # 同时修正 ttype/is_newline，否则下游仍会把该 token 当作换行
                    tk.value = " "
                    tk.ttype = T.Whitespace
                    tk.is_newline = False
                continue
            if (
                tk.is_keyword
                and " ".join(tk.normalized.split()) in keep_newline
                and self.n not in tk.value
            ):
                tk.value = self.n.join(tk.value.split())
                tk.normalized = tk.value.upper()
            elif (
                self.n in tk.value
                and (tk.is_keyword or tk.ttype in T.Operator or tk.ttype is T.Name.Builtin)
                and " ".join(tk.normalized.split()) not in keep_newline
            ):
                tk.value = " ".join(tk.value.split())
                tk.normalized = tk.value.upper()
            prev_ = tk

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
            pnidx, _ = self._token_prev_by(plist, pidx, m=(T.DML, "SELECT"))
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
                    # 首个子列表以注释开头（`_absorb_leading_comments` 把注释并进列表
                    # 首位）时，注释与 `(` 同行才是 fork 口径：首个换行交给
                    # `_process_identifierlist` 插到注释之后，这里既不能插换行、也不能
                    # 让 `_remove_prev_newline` 把 `(` 后那个空格删掉
                    if not (
                        isinstance(next_, sql.IdentifierList)
                        and bool(next_.tokens)
                        and self._is_comment(next_.tokens[0])
                    ):
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

        # 官方 get_identifiers() 不过滤注释，这里补上（注释不作为列表项参与对齐）
        identifiers = [tk for tk in tlist.get_identifiers() if not isinstance(tk, sql.Comment)]
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
                # 官方 get_identifiers 会把注释也算作列表项，对齐时需剔除
                self._align_identifierlist([tk for tk in tlist.get_identifiers() if not isinstance(tk, sql.Comment)])

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

    @staticmethod
    def _get_cases(tlist, skip_ws=False):
        """本项目口径的 ``Case.get_cases``：为 CASE 内的 ``--`` 注释保留占位。

        官方 0.6.0 的 ``Case.get_cases`` 没有注释分支，CASE 内的行注释会被直接
        并入条件；注释被换行后条件看起来就不像紧跟在 CASE 之后（见
        ``case/sqltest4_s01``）。这里按本项目口径重写同一遍历，只在本 pass 内使用，
        不修改官方类。
        """
        CONDITION = 1
        VALUE = 2

        ret = []
        mode = CONDITION
        for token in tlist.tokens:
            if token.match(T.Keyword, "CASE"):
                continue
            elif token.ttype in T.Whitespace:
                # case 后 when 前的空白需要跳过
                if skip_ws or not ret or not ret[-1][0]:
                    continue
            elif token.value.startswith("--"):
                # 需要一个占位，否则被换行后条件被认为跟在 case 后没有处理
                if not ret:
                    ret.append((None, [""]))
                if not ret[-1][0]:
                    continue
            elif token.match(T.Keyword, "WHEN"):
                ret.append(([], []))
                mode = CONDITION
            elif token.match(T.Keyword, "THEN"):
                mode = VALUE
            elif token.match(T.Keyword, "ELSE"):
                ret.append((None, []))
                mode = VALUE
            elif token.match(T.Keyword, "END"):
                mode = None

            # First condition without preceding WHEN
            if mode and not ret:
                ret.append(([], []))

            if mode == CONDITION:
                ret[-1][0].append(token)
            elif mode == VALUE:
                ret[-1][1].append(token)

        return ret

    def _process_case(self, tlist):
        # 先处理为深度遍历，后处理为广度遍历，处理注释换行
        self._process_default(tlist, stmts=False)

        # 为了计算注释换行后长度，需要考虑到行首的全部偏移
        case_offset = self._get_offset(tlist.token_first(), relative=False)
        offset_ = len("case ")
        cases = self._get_cases(tlist)  # 跳过空白后注释的换行无法识别
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

    @staticmethod
    def _is_comment(token):
        """判断 token 是否为注释 —— 既覆盖 `sql.Comment` 分组，也覆盖裸注释 token。"""
        return isinstance(token, sql.Comment) or token.ttype in T.Comment

    @staticmethod
    def _closes_its_level(plist, pidx):
        """``pidx`` 处的注释是否紧接在**语句结束符** ``;`` 之前（本层内只隔着空白）。

        用来替代「输入里它在行首」这一输入依赖判据 —— 两者都刻画「该注释独占
        本层末尾一行」，而后者压平输入后信息就丢了。`;` 常被收进子句组内部
        （`where … \\n-- x\\n;` 里 ``;`` 就在 ``Where`` 组中），故按「其后本层
        只剩空白 + ``;``」判定。

        必须要求 ``;`` **存在**：本层最后一个 token 的注释（`EmpCode -- 员工编码`
        那种行内注释）同样满足「其后无内容」，但它是跟着前面的 token 走的，
        不能因此被换行（`comma/sqltest7_s02`、`dml/sqltest1_s02` 会回归）。
        """
        rest = [tk for tk in plist.tokens[pidx + 1 :] if not tk.is_whitespace]
        return bool(rest) and all(tk.value == ";" for tk in rest)


    def _is_stmt_leading_comment(self, tlist):
        """该注释是否位于某条语句**真实开始之前**（语句前导注释）。

        口径（2026-09-13，PLAN §9.7）：只有这种注释才「保持列 0」，判据必须是
        **结构性**的 —— 它之前不存在任何有效 token（空白与注释都不算）。

        实现：只看**本层** ``tlist`` 之前的兄弟；本层没有有效 token 就向上一层追问，
        直到顶层。嵌入括号 / 列表里的注释，其祖先层里必然有 ``with`` / ``select``
        之类的有效 token，因此天然为 False。
        """
        plist = tlist.parent
        if plist is None:
            return False
        idx = plist.token_index(tlist)
        for tk in plist.tokens[: idx or 0]:
            if tk.is_whitespace or self._is_comment(tk):
                continue
            return False
        return self._is_stmt_leading_comment(plist)


    def _break_between_comments(self, tlist):
        """Comment 组内相邻注释强制各自成行 —— 两个注释不共享一行。

        这是**结构性**规则，不依赖输入空白：旧实现靠「strip 保留换行」的残留把两个
        注释分开，一旦输入被压平（收敛性测试）它们就被挤到同一行，因此
        `comma/sqltest7_s02` 与 `nested/sqltest3_s01` 在旧实现里是已知不收敛用例。

        注意 ``--`` 行注释的 token 自带行尾 ``\\n``，此时已经在新行行首，无需处理。
        """
        tokens = tlist.tokens
        for idx in range(1, len(tokens)):
            token = tokens[idx]
            if not self._is_comment(token):
                continue
            prev_ = tokens[idx - 1]
            if prev_.is_whitespace:
                if self.n in prev_.value:
                    continue
                # 两条注释之间有空白 → 这条注释原本不贴行首（不是列 0），
                # 按**所在层级**缩进（`nl(0)` 的语义就是「换行 + 本层缩进」）；
                # 原本就贴行首的走下面的 `elif`，保持列 0 不动。
                prev_.value = self.nl(0).value
            elif self._is_comment(prev_):
                # `--` 注释的 token 自带行尾换行，此时已经在新行行首
                if prev_.value.endswith(self.n):
                    continue
                tlist.insert_before(token, self.nl(0))

    def _break_before_sibling_comment(self, tlist):
        """与本层紧邻的前一段注释**不共享一行** —— `_break_between_comments` 的同一条规则。

        `_break_between_comments` 只管**同一个** ``sql.Comment`` 组里的兄弟 token；
        而两段相邻注释往往落在**同层并列的两个 ``Comment`` 组**里：官方
        ``align_comments`` 会把后一段并进前一段所在的组，随后
        `_unabsorb_trailing_comments` 又把它拆回原位。这种形状下旧实现只靠
        「输入里这里正好有个换行」（`_process_comment` 后半段的 ``prev_.is_newline``）
        才把它们分开，输入一压平就被挤回同一行 —— 收敛门禁的
        `comma/sqltest7_s02`、`nested/sqltest3_s01` 正是卡在这里。

        判据换成结构性的：**前一段注释自己不带行尾换行**（``-- x`` 的 token 含换行，
        块注释不含）说明两者此刻必定同处一行，需要强制换行；反之行注释自己已经另起
        一行，缩进交给 `_process_comment` 的对齐逻辑，不动它。
        """
        plist = tlist.parent
        if plist is None:
            return
        pidx = plist.token_index(tlist)
        if pidx is None or pidx <= 0:
            return
        prev_ws = plist.tokens[pidx - 1]
        if not prev_ws.is_whitespace or self.n in prev_ws.value:
            return
        _, prev_ = plist.token_prev(pidx, skip_ws=True)
        if prev_ is None or not self._is_comment(prev_):
            return
        if prev_.value.endswith(self.n):
            return
        prev_ws.value = self.nl(0).value

    @staticmethod
    def _ends_with_comment(token):
        """``token`` 的最后一个非空白后代是不是注释（注释串延续的标志）。

        注意 ``sql.Comment`` 自己也是 ``TokenList``：进到它内部会掉到
        ``Token.Comment.Single`` 上，所以必须先判「本身就是注释」再往下钻。
        """
        while True:
            if isinstance(token, sql.Comment) or token.ttype in T.Comment:
                return True
            if not isinstance(token, sql.TokenList):
                return False
            last = None
            for child in reversed(token.tokens):
                if not child.is_whitespace:
                    last = child
                    break
            if last is None:
                return False
            token = last

    def _process_comment(self, tlist):
        # 深度遍历时的注释要基于父对象处理，在后一token前换行，含新增的强制换行
        # 注释组内相邻注释先各自成行（结构性规则，与下方「跟随输入换行」的分支无关）
        self._break_between_comments(tlist)
        # 同层并列的注释组之间同理（`align_comments` + `_unabsorb_trailing_comments`
        # 让相邻注释成为两个并列组，组内规则看不到它们）
        self._break_before_sibling_comment(tlist)

        # comma_first 模式下，IdentifierList 中的注释已由 _process_identifierlist 处理，跳过
        if self.comma_first and isinstance(tlist.parent, sql.IdentifierList):
            return

        # 语句前导注释（位于本条语句第一个有效 token 之前）**结构性**保持列 0：
        # 判据是结构位置，不再看输入里它写没写在行首（口径 2026-09-13，见 PLAN §9.7）。
        if self._is_stmt_leading_comment(tlist):
            return

        # 只处理需要换行的单行注释和强制换行
        if not tlist.value.rstrip() == "/*-*/" and not tlist.value.startswith("--"):
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
            opener = plist.tokens[nnext_] if nnext_ is not None else None
            # 紧邻的前一个非空白兄弟本身就是注释 → 也是「注释串延续」的一种形态：
            # `_unabsorb_trailing_comments` 把注释连同前导空白搬回本层后，注释串的
            # 后续成员是**同层并列**的注释，而不是「某个组以注释结尾」。
            _, prev_any = plist.token_prev(pidx, skip_ws=True, skip_cm=False)
            if (
                prev_ is not None
                and prev_ is not opener
                and isinstance(prev_, sql.TokenList)
                and self._ends_with_comment(prev_)
            ) or isinstance(prev_any, sql.Comment):
                # 注释前还有内容（不是紧跟括号/over 的开口）→ 与**前一段内容的层级**对齐，
                # 而不是括号内容的起始列。
                # 例：`with c as ( … where 1 = 1 --a\n--b\n       --c )` 里，`--c` 是独立的
                # Comment 组，父是 CTE 体括号（内容起始列 0），但它该对齐到 where 内容的 7。
                content = prev_
                if isinstance(content, sql.TokenList):
                    inner = content.token_first()
                    if inner is not None and inner.ttype is not None and inner.ttype in T.Keyword:
                        _, inner = content.token_next(content.token_index(inner), skip_cm=True)
                    if inner is not None:
                        content = inner
                offset_ = self._get_offset(content)
            elif nnext_ is not None:
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
                if prev_ and prev_.is_whitespace and (
                    prev_.is_newline or self._closes_its_level(plist, pidx)
                ):
                    # 「本层收尾注释」旧判据只有 `prev_.is_newline`（输入里它在行首），
                    # 于是缩进完全由输入空白决定（C4 违背，`cte/sqltest2_s01` 最后一个
                    # 收敛缺口）。补一条**结构性**等价：它之后本层再无内容（只余语句
                    # 结束符 `;`）—— 压平输入时同样成立，两条路径归一。
                    # 语句前导注释保持列 0 的规则已在 `_process_comment` 开头 return。
                    prev_.value = self.nl(0).value
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

    # ====以上为ttype预处理
    @staticmethod
    def _token_prev_by(tlist, index, i=None, m=None, t=None):
        """反向查找 token，返回 ``(idx, token)``。

        官方 ``TokenList.token_next_by`` 只支持正向查找（``_token_matching`` 的
        ``reverse`` 没有暴露到公开方法），这里按同样的 ``imt`` 语义补一个。
        """
        for idx in range(index - 1, -1, -1):
            token = tlist.tokens[idx]
            if imt(token, i, m, t):
                return idx, token
        return None, None

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
        """判断关键字后是否应折叠为同行（关键字 + 右侧表达式）。

        能被 _next_token 命中的都是行首 split_words 关键字。除集合运算符
        UNION/EXCEPT（其后是新的查询体，由 _split_statements 另起一行）之外，
        其余关键字的右侧表达式都应紧随其后，避免原始输入里的随意换行被保留，
        例如 where 子句里 and 与其后的条件应折叠到同一行。
        """
        # UNION/EXCEPT 后接新的查询体，不能与关键字同行
        if token.match(T.Keyword, [r"\bUNION\b", r"\bEXCEPT\b"], regex=True):
            return False

        if token.match(T.Keyword, "ON"):
            _, next_ = tlist.token_next(tidx, skip_cm=True)
            if next_ and next_.match(T.Keyword, "COMMIT"):
                return False

        return True

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
                    token.normalized = token.value.upper()
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

    def _last_content(self, tlist):
        """返回 ``(父 list, 下标)``，指向 ``tlist`` 里最后一个非空白 token（会下钻子组）。"""
        for i in range(len(tlist.tokens) - 1, -1, -1):
            tk = tlist.tokens[i]
            if tk.is_whitespace:
                continue
            if isinstance(tk, sql.TokenList) and tk.tokens:
                found = self._last_content(tk)
                if found is not None:
                    return found
            return tlist, i
        return None

    def _normalize_trailing_semicolon(self, stmt):
        """把语句末尾的 `;` 顶到列 0 —— `;` 是**分段终止符**，不参与子句层级缩进。

        口径（2026-09-13，见 `PLAN §9.8`）：`;` 是 `format_statements` 用来切分语句的
        边界，它不是任何子句的内容；但官方分组会把它收进**子句组内部**（如 ``Where``）。
        所以前面各步**一律不为它做特殊处理**，只在每轮 layout 的**最后**统一兜底：
        `;` 独占一行时顶列 0。

        「独占一行」有两种形态，都要归一：换行在 `;` 前的**空白 token** 里（置为单个
        换行）；换行由**前一个行注释**自带、空白只剩缩进（把这段缩进抹掉）。
        同行写法（`select 1 ;`）不动。
        """
        found = self._last_content(stmt)
        if found is None:
            return
        plist, idx = found
        if str(plist.tokens[idx].value) != ";":
            return
        _, prev_ = plist.token_prev(idx, skip_ws=False)
        if prev_ is None or not prev_.is_whitespace:
            return
        if self.n in prev_.value:
            prev_.value = self.n
            return
        prev_idx = plist.token_index(prev_)
        _, before = plist.token_prev(prev_idx, skip_ws=False)
        if before is not None and self._is_comment(before) and str(before.value).endswith(self.n):
            prev_.value = ""

    def process(self, stmt):
        # 处理入口
        self._curr_stmt = stmt
        # 兜底（正常路径已由 StripWhitespaceFilter 归一）：恢复「一段空白 = 一个 token」
        merge_whitespace_runs(stmt)
        self._normalize_newlines(stmt)
        self._process(stmt)
        # 收尾兜底：语句终止符 `;` 永远顶列 0（不参与子句层级缩进）
        self._normalize_trailing_semicolon(stmt)
        return stmt
