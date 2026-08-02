#
# Copyright (C) 2009-2020 the sqlparse authors and contributors
# <see AUTHORS file>
#
# This module is part of python-sqlparse and is released under
# the BSD License: https://opensource.org/licenses/BSD-3-Clause

from sqlparse import keywords_list, sql
from sqlparse import tokens as T
from sqlparse.exceptions import SQLParseError
from sqlparse.utils import imt, recurse

JOIN_WORDS = keywords_list.join_words
BY_WORDS = keywords_list.by_words
SPLIT_WORDS = keywords_list.split_words

# Limits to prevent DoS on malformed/deeply nested SQL
MAX_GROUPING_DEPTH = 100
MAX_GROUPING_TOKENS = 10000

T_NUMERICAL = (T.Number, T.Number.Integer, T.Number.Float)
T_STRING = (T.String, T.String.Single, T.String.Symbol)
T_NAME = (T.Name, T.Name.Placeholder)


def _group_matching(tlist, cls, depth=0):
    """Groups Tokens that have beginning and end."""
    if MAX_GROUPING_DEPTH is not None and depth > MAX_GROUPING_DEPTH:
        raise SQLParseError(f"Maximum grouping depth exceeded ({MAX_GROUPING_DEPTH}).")
    if MAX_GROUPING_TOKENS is not None and len(tlist.tokens) > MAX_GROUPING_TOKENS:
        raise SQLParseError(f"Maximum number of tokens exceeded ({MAX_GROUPING_TOKENS}).")
    opens = []
    tidx_offset = 0
    token_list = list(tlist)

    for idx, token in enumerate(token_list):
        tidx = idx - tidx_offset

        if token.is_whitespace:
            continue

        if token.is_group and not isinstance(token, cls):
            _group_matching(token, cls, depth + 1)
            continue

        if token.match(*cls.M_OPEN):
            opens.append(tidx)

        elif token.match(*cls.M_CLOSE):
            try:
                open_idx = opens.pop()
            except IndexError:
                continue
            close_idx = tidx
            tlist.group_tokens(cls, open_idx, close_idx)
            tidx_offset += close_idx - open_idx


def group_brackets(tlist):
    _group_matching(tlist, sql.SquareBrackets)


def group_parenthesis(tlist):
    _group_matching(tlist, sql.Parenthesis)


def group_case(tlist):
    _group_matching(tlist, sql.Case)


def group_if(tlist):
    _group_matching(tlist, sql.If)


def group_for(tlist):
    _group_matching(tlist, sql.For)


def group_begin(tlist):
    _group_matching(tlist, sql.Begin)


def group_typecasts(tlist):
    def match(token):
        return token.match(T.Punctuation, "::")

    def valid(token):
        return token is not None

    def post(tlist, pidx, tidx, nidx):
        return pidx, nidx

    valid_prev = valid_next = valid
    _group(tlist, sql.Identifier, match, valid_prev, valid_next, post)


def group_tzcasts(tlist):
    def match(token):
        return token.ttype == T.Keyword.TZCast

    def valid_prev(token):
        return token is not None

    def valid_next(token):
        return token is not None and (
            token.is_whitespace or token.match(T.Keyword, "AS") or token.match(*sql.TypedLiteral.M_CLOSE)
        )

    def post(tlist, pidx, tidx, nidx):
        return pidx, nidx

    _group(tlist, sql.Identifier, match, valid_prev, valid_next, post)


def group_typed_literal(tlist):
    # definitely not complete, see e.g.:
    # https://docs.microsoft.com/en-us/sql/odbc/reference/appendixes/interval-literal-syntax
    # https://docs.microsoft.com/en-us/sql/odbc/reference/appendixes/interval-literals
    # https://www.postgresql.org/docs/9.1/datatype-datetime.html
    # https://www.postgresql.org/docs/9.1/functions-datetime.html
    def match(token):
        return imt(token, m=sql.TypedLiteral.M_OPEN)

    def match_to_extend(token):
        return isinstance(token, sql.TypedLiteral)

    def valid_prev(token):
        return token is not None

    def valid_next(token):
        return token is not None and imt(token, m=sql.TypedLiteral.M_CLOSE)

    def valid_final(token):
        return token is not None and token.match(*sql.TypedLiteral.M_EXTEND)

    def post(tlist, pidx, tidx, nidx):
        return tidx, nidx

    _group(
        tlist,
        sql.TypedLiteral,
        match,
        valid_prev,
        valid_next,
        post,
        extend=False,
    )
    _group(
        tlist,
        sql.TypedLiteral,
        match_to_extend,
        valid_prev,
        valid_final,
        post,
        extend=True,
    )


def group_period(tlist):
    def match(token):
        for ttype, value in (
            (T.Punctuation, "."),
            (T.Operator, "->"),
            (T.Operator, "->>"),
        ):
            if token.match(ttype, value):
                return True
        return False

    def valid_prev(token):
        sqlcls = sql.SquareBrackets, sql.Identifier
        ttypes = T.Name, T.String.Symbol
        return imt(token, i=sqlcls, t=ttypes)

    def valid_next(token):
        # issue261, allow invalid next token
        return True

    def post(tlist, pidx, tidx, nidx):
        # next_ validation is being performed here. issue261
        sqlcls = sql.SquareBrackets, sql.Function
        ttypes = T.Name, T.String.Symbol, T.Wildcard, T.String.Single
        next_ = tlist[nidx] if nidx is not None else None
        valid_next = imt(next_, i=sqlcls, t=ttypes)

        return (pidx, nidx) if valid_next else (pidx, tidx)

    _group(tlist, sql.Identifier, match, valid_prev, valid_next, post)


def group_as(tlist):
    def match(token):
        return token.is_keyword and token.normalized == "AS"

    def valid_prev(token):
        return True  # 支持关键字作为字段名

    def valid_next(token):
        ttypes = T.DML, T.DDL, T.CTE
        # CTE with as ()
        return not imt(token, t=ttypes) and token is not None

    def post(tlist, pidx, tidx, nidx):
        return pidx, nidx

    _group(tlist, sql.Identifier, match, valid_prev, valid_next, post)


def group_assignment(tlist):
    def match(token):
        return token.match(T.Assignment, ":=")

    def valid(token):
        return token is not None and token.ttype not in (T.Keyword,)

    def post(tlist, pidx, tidx, nidx):
        m_semicolon = T.Punctuation, ";"
        snidx, _ = tlist.token_next_by(m=m_semicolon, idx=nidx)
        nidx = snidx or nidx
        return pidx, nidx

    valid_prev = valid_next = valid
    _group(tlist, sql.Assignment, match, valid_prev, valid_next, post)


def group_comparison(tlist):
    sqlcls = (
        sql.Parenthesis,
        sql.Function,
        sql.Identifier,
        sql.Operation,
        sql.TypedLiteral,
    )
    ttypes = T_NUMERICAL + T_STRING + T_NAME

    def match(token):
        return token.ttype == T.Operator.Comparison

    def valid(token):
        if imt(token, t=ttypes, i=sqlcls):
            return True
        elif token and token.is_keyword and token.normalized == "NULL":
            return True
        else:
            return False

    def post(tlist, pidx, tidx, nidx):
        return pidx, nidx

    valid_prev = valid_next = valid
    _group(tlist, sql.Comparison, match, valid_prev, valid_next, post, extend=False)


@recurse(sql.Identifier)
def group_identifier(tlist):
    ttypes = (T.String.Symbol, T.Name)
    sqlcls = sql.Case

    tidx, token = tlist.token_next_by(t=ttypes, i=sqlcls)
    while token:
        tlist.group_tokens(sql.Identifier, tidx, tidx)
        tidx, token = tlist.token_next_by(t=ttypes, i=sqlcls, idx=tidx)


@recurse(sql.Over)
def group_over(tlist):
    # M_OPEN = (T.Keyword, 'OVER') over未被识别为keyword, 匹配不成功, 改了lexer先匹配关键字再Name
    tidx, token = tlist.token_next_by(m=sql.Over.M_OPEN)
    while token:
        nidx, next_ = tlist.token_next(tidx)
        if imt(next_, i=sql.Parenthesis, t=T.Name):
            tlist.group_tokens(sql.Over, tidx, nidx)
        tidx, token = tlist.token_next_by(m=sql.Over.M_OPEN, idx=tidx)


def group_arrays(tlist):
    sqlcls = sql.SquareBrackets, sql.Identifier, sql.Function
    ttypes = T.Name, T.String.Symbol

    def match(token):
        return isinstance(token, sql.SquareBrackets)

    def valid_prev(token):
        return imt(token, i=sqlcls, t=ttypes)

    def valid_next(token):
        return True

    def post(tlist, pidx, tidx, nidx):
        return pidx, tidx

    _group(
        tlist,
        sql.Identifier,
        match,
        valid_prev,
        valid_next,
        post,
        extend=True,
        recurse=False,
    )


def group_operator(tlist):
    # 修正+-开头的场景
    ttypes = T_NUMERICAL + T_STRING + T_NAME
    sqlcls = (
        sql.SquareBrackets,
        sql.Parenthesis,
        sql.Function,
        sql.Identifier,
        sql.Operation,
        sql.TypedLiteral,
    )

    def match(token):
        return imt(token, t=(T.Operator, T.Wildcard))

    def valid_prev(token):
        if imt(token, i=sqlcls, t=ttypes) or (
            token and token.match(T.Keyword, ("CURRENT_DATE", "CURRENT_TIME", "CURRENT_TIMESTAMP"))
        ):
            return True
        elif token and token.match(T.Punctuation, (",", "(")):
            return True

    def valid_next(token):
        return imt(token, i=sqlcls, t=ttypes) or (
            token and token.match(T.Keyword, ("CURRENT_DATE", "CURRENT_TIME", "CURRENT_TIMESTAMP"))
        )

    def post(tlist, pidx, tidx, nidx):
        tlist[tidx].ttype = T.Operator
        if tlist[pidx].match(T.Punctuation, (",", "(")):
            return tidx, nidx
        else:
            return pidx, nidx

    _group(
        tlist,
        sql.Operation,
        match,
        valid_prev,
        valid_next,
        post,
        extend=False,
        skip_cm=True,
    )


def group_identifier_list(tlist):
    # tokenlist没有ttype, 入口进来即最外层statment
    # 按_group默认迭代处理子组难以控制，故把循环提出来
    # 用装饰器是深度优先

    stmt_info = dict.fromkeys(["create", "insert", "select", "values"], (None, None))

    stmt_info["create"] = tlist.token_next_by(m=(T.DDL, ["CREATE", "ALTER"]))
    stmt_info["insert"] = tlist.token_next_by(m=(T.DML, ["INSERT"]))
    stmt_info["select"] = tlist.token_next_by(t=T.CTE, m=(T.DML, ["SELECT"]))
    stmt_info["values"] = tlist.token_next_by(i=sql.Values)

    m_role = T.Keyword, ("null", "role")
    sqlcls = (
        sql.Function,
        sql.Case,
        sql.Identifier,
        sql.Comparison,
        sql.Parenthesis,
        sql.IdentifierList,
        sql.Operation,
        sql.Comment,
    )
    ttypes = T_NUMERICAL + T_STRING + T_NAME + (T.Keyword, T.Comment, T.Wildcard)

    def match(token):
        return token.match(T.Punctuation, ",")

    def valid_prev(token):
        return imt(token, i=sqlcls, m=m_role, t=ttypes) and not token.is_keyword or token.match(T.Keyword, "NULL")

    def valid_next(token):
        return imt(token, i=sqlcls, m=m_role, t=ttypes) and not token.is_keyword or token.match(T.Keyword, "NULL")

    def post(tlist, pidx, tidx, nidx):
        return pidx, nidx

    # index可能是0，不能直接判断index是否True
    if stmt_info["create"][1] and not stmt_info["select"][1]:
        return

    # 手动深度遍历
    for sgroup in tlist.get_sublists():
        idx = tlist.token_index(sgroup)
        # 不需要处理：create/alter/insert后,且在with/select/values前的1-2个括号
        if (
            stmt_info["select"][1] and idx < stmt_info["select"][0]
            # or stmt_info["values"][1]
            # and idx < stmt_info["values"][0]
        ):
            continue
        if not isinstance(sgroup, sql.IdentifierList):
            group_identifier_list(sgroup)

    _ = 1
    _group(
        tlist,
        sql.IdentifierList,
        match,
        valid_prev,
        valid_next,
        post,
        extend=True,
        recurse=False,
        skip_cm=True,
    )


@recurse(sql.Comment)
def group_comments(tlist):
    """将注释或换行合并为Comment类, 改为连续单行注释不合并"""
    # return
    tidx, token = tlist.token_next_by(t=T.Comment)
    while token:
        eidx, end = tlist.token_not_matching(
            lambda tk: imt(tk, t=T.Comment.Mutiline) or tk.is_newline,
            idx=tidx + 1,
        )
        if end is not None:
            eidx, end = tlist.token_prev(eidx, skip_ws=False)
            tlist.group_tokens(sql.Comment, tidx, eidx)

        tidx, token = tlist.token_next_by(t=T.Comment, idx=tidx)


@recurse(sql.Where)
def group_where(tlist):
    tidx, token = tlist.token_next_by(m=sql.Where.M_OPEN)
    while token:
        eidx, end = tlist.token_next_by(m=sql.Where.M_CLOSE, idx=tidx)

        if end is None:
            end = tlist._groupable_tokens[-1]
        else:
            end = tlist.tokens[eidx - 1]
        # TODO: convert this to eidx instead of end token.
        # i think above values are len(tlist) and eidx-1
        eidx = tlist.token_index(end)
        tlist.group_tokens(sql.Where, tidx, eidx)
        tidx, token = tlist.token_next_by(m=sql.Where.M_OPEN, idx=tidx)


@recurse()
def group_aliased(tlist):
    I_ALIAS = (
        sql.Parenthesis,
        sql.Function,
        sql.Case,
        sql.Identifier,
        sql.Operation,
        sql.Comparison,
    )

    tidx, token = tlist.token_next_by(i=I_ALIAS, t=[T.Number, T.String], m=(T.Keyword, "NULL"))
    while token:
        nidx, next_ = tlist.token_next(tidx)
        if isinstance(next_, sql.Identifier):
            tlist.group_tokens(sql.Identifier, tidx, nidx, extend=True)
        tidx, token = tlist.token_next_by(i=I_ALIAS, t=[T.Number, T.String], m=(T.Keyword, "NULL"), idx=tidx)


@recurse(sql.Function)
def group_functions(tlist):
    _, has_create = tlist.token_next_by(m=(T.DDL, ["CREATE", "ALTER"]))
    _, has_table = tlist.token_next_by(m=(T.Keyword, ["TABLE", "VIEW"]))
    _, has_insert = tlist.token_next_by(m=(T.DML, ["INSERT"]))
    _, has_values = tlist.token_next_by(m=(T.Keyword, ["VALUES"]))
    if has_insert and has_values:  # 值列表插入，不需要识别函数
        return

    tidx = 0
    # 在 create 或 insert 后，需要跳过后续连续可能有括号的内容
    # 如 create table schema.tbl (a int) as with ww as (select * from tbl1) select * from ww
    if has_create and has_table or has_insert:
        m_role = [(T.Punctuation, "."), (T.Keyword, "AS")]
        tidx, token = tlist.token_next_by(t=T.Name, idx=tidx)  # DDL后一定有表名，跳过if exists等
        nidx, next_ = tlist.token_next(tidx, skip_cm=True)
        while (
            next_
            and not next_.match(T.Keyword, ("KEY", "HASH", "RANGE", "LIST"))
            and not next_.ttype == T.DML
            and imt(next_, i=sql.Parenthesis, m=m_role, t=[T.Name, T.Keyword])
        ):
            tidx = nidx
            nidx, next_ = tlist.token_next(nidx, skip_cm=True)
    tidx, token = tlist.token_next_by(t=[T.Name, T.Keyword], idx=tidx)

    # 关键字也支持再识别为函数，但要排除select ()等情况
    while token:
        if (
            not token.match(T.Keyword, SPLIT_WORDS, True)
            and not token.match(T.DML, ("SELECT"))
            and not token.match(
                T.Keyword,
                (
                    "CASE",
                    "THEN",
                    "WHEN",
                    "ELSE",
                    "DISTINCT",
                    "AS",
                    "IN",
                    "EXISTS",
                ),
            )
        ):
            nidx, next_ = tlist.token_next(tidx, skip_cm=True)
            if isinstance(next_, sql.Parenthesis):
                # 删除括号前边的空格
                _, prev_ = tlist.token_prev(nidx, skip_ws=False)
                if prev_ and prev_.is_whitespace:
                    prev_.value = ""
                over_idx, over = tlist.token_next(nidx, skip_cm=True)
                if over and isinstance(over, sql.Over):
                    eidx = over_idx
                else:
                    eidx = nidx
                tlist.group_tokens(sql.Function, tidx, eidx)
        tidx, token = tlist.token_next_by(
            t=[T.Name, T.Keyword], idx=tidx
        )  # 如max(a), 先识别为关键字，不是Name; REGEXP(a,b)


@recurse(sql.Identifier)
def group_order(tlist):
    """Group together Identifier and Asc/Desc token"""
    tidx, token = tlist.token_next_by(t=T.Keyword.Order)
    while token:
        pidx, prev_ = tlist.token_prev(tidx)
        if imt(prev_, i=sql.Identifier, t=T.Number):
            tlist.group_tokens(sql.Identifier, pidx, tidx)
            tidx = pidx
        tidx, token = tlist.token_next_by(t=T.Keyword.Order, idx=tidx)


@recurse()
def align_comments(tlist):
    """将注释合并到前后边的 IdentifierList"""
    tidx, token = tlist.token_next_by(i=sql.Comment)
    while token and False:
        pidx, prev_ = tlist.token_prev(tidx)
        # 排除两个单行comment合并
        if isinstance(prev_, sql.IdentifierList) and not prev_.value.startswith("--"):
            tlist.group_tokens(sql.IdentifierList, pidx, tidx, extend=True)
            tidx = pidx
        tidx, token = tlist.token_next_by(i=sql.Comment, idx=tidx)
    # 合并到后边，否则select后有注释时IdentifierList取首个Identifier的位置不对
    tidx, token = tlist.token_next_by(i=sql.Comment)
    while token and token[0].ttype is T.Comment.Single:
        nidx, next_ = tlist.token_next(tidx)
        if isinstance(next_, sql.IdentifierList):
            next_.insert_before(0, token)
            del tlist.tokens[tidx]
        tidx, token = tlist.token_next_by(i=sql.Comment, idx=tidx)


def group_values(tlist):
    tidx, token = tlist.token_next_by(m=(T.Keyword, "VALUES"))
    start_idx = tidx
    end_idx = -1
    while token:
        if isinstance(token, sql.Parenthesis):
            end_idx = tidx
        tidx, token = tlist.token_next(tidx)
    if end_idx != -1:
        tlist.group_tokens(sql.Values, start_idx, end_idx, extend=True)


def group(stmt):
    for func in [
        group_comments,
        # _group_matching
        group_brackets,
        group_parenthesis,
        group_case,
        group_if,
        group_for,
        group_begin,
        group_over,
        group_functions,
        group_where,
        group_period,
        group_arrays,
        group_identifier,
        group_order,
        group_typecasts,
        group_tzcasts,
        group_typed_literal,
        group_operator,
        group_comparison,
        group_as,
        group_aliased,
        group_assignment,
        group_values,
        group_identifier_list,
        align_comments,
    ]:
        func(stmt)
    return stmt


def _group(
    tlist,
    cls,
    match,
    valid_prev=lambda t: True,
    valid_next=lambda t: True,
    post=lambda tl, pi, ti, ni: (pi, ni),
    extend=True,
    recurse=True,
    skip_cm=False,
    depth=0,
):
    """Groups together tokens that are joined by a middle token. i.e. x < y"""
    if MAX_GROUPING_DEPTH is not None and depth > MAX_GROUPING_DEPTH:
        raise SQLParseError(f"Maximum grouping depth exceeded ({MAX_GROUPING_DEPTH}).")
    if MAX_GROUPING_TOKENS is not None and len(tlist.tokens) > MAX_GROUPING_TOKENS:
        raise SQLParseError(f"Maximum number of tokens exceeded ({MAX_GROUPING_TOKENS}).")

    tidx_offset = 0
    pidx, prev_ = None, None
    for idx, token in enumerate(list(tlist)):
        if token.is_whitespace:
            continue

        if skip_cm and imt(token, t=T.Comment, i=sql.Comment):
            continue

        if recurse and token.is_group and not isinstance(token, cls):
            _group(
                token,
                cls,
                match,
                valid_prev,
                valid_next,
                post,
                extend,
                recurse,
                skip_cm,
                depth + 1,
            )

        tidx = idx - tidx_offset
        if tidx < 0:
            continue

        if match(token):
            nidx, next_ = tlist.token_next(tidx, skip_cm=skip_cm)
            if prev_ and next_ and valid_prev(prev_) and valid_next(next_):
                from_idx, to_idx = post(tlist, pidx, tidx, nidx)
                grp = tlist.group_tokens(cls, from_idx, to_idx, extend=extend)

                tidx_offset += to_idx - from_idx
                pidx, prev_ = from_idx, grp
                continue

        pidx, prev_ = tidx, token
