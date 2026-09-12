"""分组补偿层：在官方 ``grouping.group`` 之上补齐「注释打断列表」的缺口。

问题
----
官方 ``group_identifier_list`` 用 ``imt(token, i=sqlcls, t=ttypes)`` 判定列表项，
``ttypes`` 里虽然含 ``T.Comment``，但 ``group_comments`` 先跑，注释此时已经是
``sql.Comment`` 分组（``ttype`` 为 ``None``），于是**注释会把列表打断**：

    select a, /*m*/ b from t      # 官方分组下拿不到 IdentifierList

旧 fork 的做法是把 ``sql.Comment`` 加进 ``sqlcls``；本项目不改官方源码，改为在
官方分组之后追加一层「容忍注释」的列表归并。

做法
----
复用官方 ``_group`` 的遍历（不复制其实现），只换掉两个判定回调：

* ``valid_prev``：把 ``Comment`` 也当作合法的前项；
* ``valid_next``：遇到 ``Comment`` 时向后看，只有其后仍有真实列表项才允许跨过它
  成组，并在 ``post`` 里把成组区间延伸到那个真实列表项。

成组区间是连续的，区间内的注释因此会像旧 fork 一样成为 ``IdentifierList`` 的子项。
"""

from sqlparse import sql
from sqlparse import tokens as T
from sqlparse.engine import grouping as official
from sqlparse.utils import imt

# 与官方 ``group_identifier_list`` 的判定口径保持一致（含 ``T.Comment``）。
_SQLCLS = (
    sql.Function,
    sql.Case,
    sql.Identifier,
    sql.Comparison,
    sql.IdentifierList,
    sql.Operation,
)
_TTYPES = official.T_NUMERICAL + official.T_STRING + official.T_NAME + (T.Keyword, T.Comment, T.Wildcard)
_M_ROLE = T.Keyword, ("null", "role")


def _match(token):
    """与官方一致：以逗号作为列表分隔符。"""
    return token.match(T.Punctuation, ",")


def _is_comment(token):
    return isinstance(token, sql.Comment)


def _real_item(token):
    """官方口径的「合法列表项」判定（不把 Comment 分组算进去）。"""
    return token is not None and imt(token, i=_SQLCLS, m=_M_ROLE, t=_TTYPES)


def _group_level(tlist):
    """对本层做一次「容忍注释」的逗号列表归并。"""

    def skip_comments(tidx):
        """跳过连续注释，返回其后第一个真实列表项的下标；没有则 None。"""
        while True:
            nidx, next_ = tlist.token_next(tidx)
            if next_ is None:
                return None
            if not _is_comment(next_):
                return nidx if _real_item(next_) else None
            tidx = nidx

    def valid_prev(token):
        return _is_comment(token) or _real_item(token)

    def valid_next(token):
        if token is None:
            return False
        if _is_comment(token):
            # 注释本身不是列表项：只有其后仍有真实列表项时才值得跨过它成组
            return skip_comments(tlist.token_index(token)) is not None
        return _real_item(token)

    def post(tlist_, pidx, tidx, nidx):
        if _is_comment(tlist_.tokens[pidx]):
            # 前项是注释时向前找回真实前项，避免列表起点落在注释上
            prev_idx, prev_ = tlist_.token_prev(pidx)
            if prev_ is not None and valid_prev(prev_):
                pidx = prev_idx
        if _is_comment(tlist_.tokens[nidx]):
            end = skip_comments(nidx)
            if end is not None:
                nidx = end
        return pidx, nidx

    # recurse=False：递归由本模块自己做，便于跳过已成组的 IdentifierList
    official._group(  # noqa: SLF001 官方遍历原语，配合本项目判定回调使用
        tlist,
        sql.IdentifierList,
        _match,
        valid_prev,
        valid_next,
        post,
        extend=True,
        recurse=False,
    )


def _walk(tlist):
    for sgroup in list(tlist.get_sublists()):
        _walk(sgroup)
    # 已经是列表的层不再归并，否则会在列表内部再套一层列表
    if isinstance(tlist, sql.IdentifierList):
        return
    _group_level(tlist)


def group(stmt):
    """官方分组 + 注释容忍补偿。调用方用它替换 ``grouping.group``。"""
    stmt = official.group(stmt)
    _walk(stmt)
    return stmt
