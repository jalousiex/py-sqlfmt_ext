"""分组补偿层：官方 ``grouping.group`` 前后各补一处缺口。

本文件只**调用**官方 ``_group`` 这个遍历原语，不复制官方任何分组实现。
官方分组在本项目口径下有三条缺口：

1. **裸 ``interval N unit`` 不成组**（官方分组之前补）。
   官方 ``group_typed_literal`` 的 ``M_CLOSE`` 是 ``T.String.Single``，只支持
   ``interval '1 day'``；Doris/MySQL 更常见的是 ``interval 1 day``。不成组时
   ``-`` 运算符失去右操作数，会连带把字段列表切碎（``comma/sqltest7_s01``）。
   见 ``_group_interval_literals``。

2. **注释会打断逗号列表**（官方分组之后补）。
   官方 ``group_identifier_list`` 用 ``imt(token, i=sqlcls, t=ttypes)`` 判定列表项，
   ``ttypes`` 里虽然含 ``T.Comment``，但 ``group_comments`` 先跑，注释此时已经是
   ``sql.Comment`` 分组（``ttype`` 为 ``None``），于是判定失败：

       select a, /*m*/ b from t      # 官方分组下拿不到 IdentifierList

   旧 fork 的做法是把 ``sql.Comment`` 加进 ``sqlcls``；本项目不改官方源码，改为
   在官方分组**之后**追加一层「容忍注释」的列表归并：只换掉官方 ``_group`` 的两个
   判定回调——``valid_prev`` 把 ``Comment`` 也当作合法前项，``valid_next`` 遇到
   ``Comment`` 时向后看、只有其后仍有真实列表项才允许跨过它成组，并在 ``post`` 里
   把成组区间延伸到那个真实列表项。成组区间连续，区间内的注释因此会像旧 fork 一样
   成为 ``IdentifierList`` 的子项。

3. **官方 ``align_comments`` 会把注释并入前一个 ``TokenList``**（官方分组之后补）。
   注释因此成了那个组的末尾 token，后续 token（典型是同级闭括号）在 ``LayoutPass``
   里对不齐。旧 fork 的分组从不并入。见 ``_unabsorb_trailing_comments``。

4. **官方 ``group_as`` 不接受「关键字作别名左值」**（官方分组之前补）。
   官方 ``valid_prev`` 是 ``token.normalized == 'NULL' or not token.is_keyword``，
   而旧 fork 放宽成 ``True``（源码注释：「支持关键字作为字段名」）。
   ``level``/``rows`` 这类词在官方词表里是关键字，于是 ``select level as depth``
   的 ``level as depth`` 不成组，``group_identifier_list`` 会把 ``level`` 当成独立
   列表项，字段列表被切碎、列对齐整体失效。见 ``_wrap_keyword_alias_lhs``。

5. **官方 ``group_functions`` 会把「DDL/INSERT 的对象名加字段列表」误判成函数调用**
   （官方分组之前补）。
   官方判定是「``T.Name`` 紧跟 ``Parenthesis`` 即 ``Function``」，不区分位置。
   ``insert into db.tb (user_id, name, age)`` 里 ``tb`` 后面紧跟 ``(``，于是被包成
   ``Function[tb (…)]``，再被 ``group_period`` 收进 ``Identifier[db, '.', Function]``。
   危害是连锁的：   ``group_identifier`` 的 ``@recurse(sql.Identifier)`` **不递归进
   ``Identifier`` 子组**，于是括号里的裸 ``T.Name`` 再也包不成 ``Identifier``，
   ``LayoutPass._process_parenthesis`` 于是把这段当成普通函数括号、字段列表不展开
   （S4 的 5 个用例）。旧 fork 在 ``group_functions`` 里有「跳过表名+列名括号」
   的专门分支，本项目不改官方源码，改为在官方分组**之前**把对象名链预包成
   ``Identifier``：``group_functions`` 只看本层的裸 ``T.Name``、不递归，链一包住
   它就看不见了。见 ``_pre_wrap_object_name``。
"""

from sqlparse import sql
from sqlparse import tokens as T
from sqlparse.engine import grouping as official
from sqlparse.utils import imt

# 与官方 ``group_identifier_list`` 的判定口径基本一致（含 ``T.Comment``），
# 仅补一个 ``sql.Parenthesis``：官方 ``sqlcls`` 不含它，于是 ``values (…), (…)``
# 这种「括号作列表项」的多行值列表在官方分组下永远成不了 ``IdentifierList``
# （``LayoutPass._process_values`` 依赖它已经成组）。旧 fork 的 ``sqlcls`` 含
# ``sql.Parenthesis``。
_SQLCLS = (
    sql.Function,
    sql.Case,
    sql.Identifier,
    sql.Comparison,
    sql.IdentifierList,
    sql.Operation,
    sql.Parenthesis,
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


def _refresh_values(token):
    """自底向上刷新 ``TokenList.value``。

    官方 ``TokenList`` 的 ``value`` 是构造时缓存的字符串（``__init__`` 里
    ``''.join(...)`` 一次），就地增删子 token 不会自动更新。本模块会搬动 token，
    因此必须自己刷新，否则 ``LayoutPass`` 里 ``prev_.value.rstrip().endswith(n)``
    这类基于缓存值的判定会按旧内容工作（曾把注释顶到下一行）。
    """
    while token is not None:
        if isinstance(token, sql.TokenList):
            token.value = "".join(child.value for child in token.tokens)
        token = token.parent


def _group_interval_literals(tlist):
    """把裸 ``interval <数值> <单位>`` 预成组为 ``TypedLiteral``。

    必须在官方 ``group`` **之前**跑：官方 ``group_typed_literal`` 的 ``M_CLOSE``
    只认 ``T.String.Single``，裸数值不会被收进 ``TypedLiteral``，随后
    ``group_operator`` 的 ``-`` 失去右操作数，最终把字段列表切成两段。
    """

    def match(token):
        # ``Name.Builtin`` 不是关键字，``normalized`` 保持原样小写，
        # 因此不能用 ``token.match(ttype, "INTERVAL")`` 判定，只能比 value。
        return token.ttype is T.Name.Builtin and token.value.upper() == "INTERVAL"

    def valid_prev(token):
        return token is not None

    def valid_next(token):
        if token is None or token.ttype not in official.T_NUMERICAL:
            return False
        # 单位关键字不能缺：``interval 1`` 本身不是合法字面量
        _, unit = tlist.token_next(tlist.token_index(token))
        return unit is not None and unit.match(*sql.TypedLiteral.M_EXTEND)

    def match_to_extend(token):
        return isinstance(token, sql.TypedLiteral)

    def valid_final(token):
        return token is not None and token.match(*sql.TypedLiteral.M_EXTEND)

    def post(tlist_, pidx, tidx, nidx):
        return tidx, nidx

    official._group(  # noqa: SLF001 官方遍历原语，配合本项目判定回调使用
        tlist, sql.TypedLiteral, match, valid_prev, valid_next, post, extend=False
    )
    official._group(  # noqa: SLF001 官方遍历原语，配合本项目判定回调使用
        tlist, sql.TypedLiteral, match_to_extend, valid_prev, valid_final, post, extend=True
    )


_WRAP_ALIAS_LHS_EXCLUDE = frozenset({
    # 官方 valid_prev 已显式放行 NULL，不需要我们掺和
    "NULL",
    # END 是 sql.Case 的 M_CLOSE，而官方 group_case 早于 group_as 运行、
    # 且 token_next_by 不递归子组：提前把 END 包成 Identifier 会让 group_case
    # 找不到收尾关键字，整个 CASE 分组散架（case/sqltest4_s02 的回归）。
    "END",
})


def _wrap_keyword_alias_lhs(tlist):
    """把官方 ``group_as`` 拒绝的「关键字左值」预包成 ``Identifier``。

    官方 ``group_as.valid_prev`` 是 ``token.normalized == 'NULL' or not token.is_keyword``：
    **关键字不能作 AS 的左值**。旧 fork 放宽成 ``True``（源码注释「支持关键字作为字段名」）。
    ``level``/``rows`` 这类词在官方词表里是关键字，于是 ``select level as depth`` 里
    ``level as depth`` 不成组，``group_identifier_list`` 会把 ``level`` 当独立列表项，
    字段列表被切碎、列对齐整体失效（``debug/sqldebug_s01``）。

    这里**只做一件最小的事**：把该关键字本身包成 ``sql.Identifier``。分组时机在官方
    ``group`` **之前**，因此后续官方步骤照常工作：

    - ``group_identifier`` 先于 ``group_as`` 运行，会把右值的裸 ``T.Name`` 包成
      ``Identifier``（这正是官方树里别名总是嵌套 ``Identifier`` 的原因）；
    - 轮到 ``group_as`` 时左值已是 ``Identifier``（``is_keyword`` 为 False），
      ``valid_prev`` 自然通过；``post`` 返回 ``(pidx, nidx)`` 且 ``extend=True``，
      于是**扩展**左值那个 ``Identifier``，得到与官方完全同形的
      ``Identifier[level, ws, as, ws, Identifier[depth]]``。

    只在「左值是关键字且不是 ``NULL``」这一种官方明确拒绝的形状上动手，其余形状
    官方自己能处理，不抢跑。
    """

    def match(token):
        return token.is_keyword and token.normalized == "AS"

    def valid_prev(token):
        return (
            token is not None
            and token.is_keyword
            and token.normalized not in _WRAP_ALIAS_LHS_EXCLUDE
        )

    def valid_next(token):
        # 右值是括号的（``with x as (...)``）不碰；那种形状左值是 Name，本来也进不来
        return token is not None and not token.match(T.Punctuation, "(")

    def post(tlist_, pidx, tidx, nidx):
        # 只包左值：别名整体仍由官方 group_as 成组
        return pidx, pidx

    official._group(  # noqa: SLF001 官方遍历原语，配合本项目判定回调使用
        tlist, sql.Identifier, match, valid_prev, valid_next, post
    )


_OBJECT_NAME_ANCHORS = frozenset({"INTO", "TABLE", "VIEW"})
_NAME_CHAIN_TTYPES = (T.Name, T.String.Symbol)


def _pre_wrap_object_name(tlist):
    """把「DDL/INSERT 的对象名链」预包成 ``Identifier``（官方分组之前）。

    官方 ``group_functions`` 只看本层的裸 ``T.Name`` 是否紧跟 ``Parenthesis``，
    不区分函数调用与「表名 + 字段列表」。``insert into db.tb (user_id, …)`` 于是
    被包成 ``Identifier[db, '.', Function[tb (…)]]``；``group_identifier`` 不递归进
    ``Identifier`` 子组，括号里的裸 ``Name`` 从此包不成 ``Identifier``，字段列表
    不展开（模块 docstring 第 5 条）。

    这里在官方分组之前，把「锚点关键字之后的对象名链」包成一个 ``Identifier``。
    锚点只有三类：``INTO``（INSERT）、``TABLE`` / ``VIEW``（CREATE …），
    并且**只有当链尾后面确实紧跟 ``(`` 时**才包：

    - ``insert into t select f(x) …``：``t`` 后面不是 ``(``，不包，
      官方照常把 ``f(x)`` 认成 ``Function``（与 fork 一致）；
    - ``create table a.b (…)``：官方 ``group_period`` 本来也会把 ``a.b`` 收成
      ``Identifier``，这里只是把时机提前到 ``group_functions`` 之前，形状不变。

    包住的 ``Identifier`` 是 ``_group`` 的 ``cls``，官方各步都不会再递归进去，
    因此内部裸 ``Name`` 保持原样（与 fork 的 ``Identifier[db, '.', tb]`` 同形），
    而括号升到本层后会被 ``group_identifier`` 正常收住。
    """

    # 快照遍历：``group_tokens`` 会就地改动 ``tlist.tokens``，位置要实时取
    for anchor in list(tlist.tokens):
        if not (anchor.is_keyword and anchor.normalized in _OBJECT_NAME_ANCHORS):
            continue
        idx = tlist.token_index(anchor)
        if idx is None:
            continue

        nidx, next_ = tlist.token_next(idx)
        # ``IF [NOT] EXISTS`` 被官方词表整句词条化成一个 Keyword token
        while next_ is not None and next_.is_keyword and next_.normalized.startswith("IF"):
            nidx, next_ = tlist.token_next(nidx)
        if next_ is None or next_.ttype not in _NAME_CHAIN_TTYPES:
            continue

        start = end = nidx
        cur = nidx
        while True:
            nidx, next_ = tlist.token_next(cur)
            if next_ is None:
                break
            if next_.ttype in _NAME_CHAIN_TTYPES or next_.match(T.Punctuation, "."):
                end = cur = nidx
            elif next_.is_keyword and next_.normalized == "AS":
                # ``insert into t as x (…)``：少见的形状，让链继续往前走
                cur = nidx
            else:
                break

        _, after = tlist.token_next(end)
        if after is not None and after.match(T.Punctuation, "("):
            tlist.group_tokens(sql.Identifier, start, end)


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


def _splice_continuations(tlist):
    """把「跟在本层逗号之后」的子 ``IdentifierList`` 摊平到本层。

    官方 ``group_identifier_list`` 先按注释把列表切成若干段，各段已各自成组。
    本层再做归并时，若直接把这些子列表整块并进来，就会得到
    ``IdentifierList`` 套 ``IdentifierList`` 的畸形结构（对齐阶段会按两层
    缩进累加，列位置完全错乱）。这类「续接」子列表在官方遍历里只有一种来源：
    紧跟在某个逗号之后。先摊平它们，再统一归并成一张平表。
    """
    idx = 0
    while idx < len(tlist.tokens):
        token = tlist.tokens[idx]
        if isinstance(token, sql.IdentifierList):
            _, prev_ = tlist.token_prev(idx, skip_cm=True)
            if prev_ is not None and _match(prev_):
                tlist.tokens[idx:idx + 1] = token.tokens
                for child in token.tokens:
                    child.parent = tlist
                _refresh_values(tlist)
                continue  # 摊平后可能又暴露出新的续接子列表，重新检查本位置
        idx += 1


def _unabsorb_trailing_comments(tlist):
    """把官方 ``align_comments`` 并入前一个 ``TokenList`` 的注释提回父层。

    官方 ``align_comments`` 会把注释与它前面的 ``TokenList`` 合成一组
    （``extend=True``），好让注释跟着那个 token 走；副作用是注释成了该组的**末尾**。
    于是 ``LayoutPass._process_comment`` 里 ``plist[-1] == tlist`` 的判定会让它放弃
    对齐，紧跟在注释后的 token（典型是同级闭括号 ``)``）就落到行首。
    旧 fork 的分组从不并入，注释始终留在它字面所在的那一层（父层紧随其后）。
    这里还原成同一形状：注释连同紧邻的前导空白一起提到父层、放在该组之后。
    """

    for sgroup in list(tlist.get_sublists()):
        _unabsorb_trailing_comments(sgroup)

    parent = tlist.parent
    if parent is None:
        return

    # 从组尾往前收集「注释（及其前导空白）」构成的尾巴
    start = len(tlist.tokens)
    while start > 0 and isinstance(tlist.tokens[start - 1], sql.Comment):
        start -= 1
        if start > 0 and tlist.tokens[start - 1].is_whitespace:
            start -= 1
    # 全是注释的组保持原样，否则等于把整组搬走
    if start == 0 or start == len(tlist.tokens):
        return

    tail = tlist.tokens[start:]
    del tlist.tokens[start:]
    idx = parent.token_index(tlist) + 1
    for offset, token in enumerate(tail):
        token.parent = parent
        parent.tokens.insert(idx + offset, token)
    _refresh_values(tlist)


def _absorb_leading_comments(tlist):
    """把紧跟在 ``IdentifierList`` 前面的注释并到该列表首位。

    官方 ``align_comments`` 只把注释并到它**前面**的 TokenList 末尾；旧 fork 相反，
    并到它**后面**的 IdentifierList 首位，注释说得很清楚：「否则 select 后有注释时
    IdentifierList 取首个 Identifier 的位置不对」。本项目按 fork 口径补这一步，
    否则 ``group_concat(-- c\\n a, b)`` 里注释停在括号层，换行后取错对齐偏移。
    """

    for sgroup in list(tlist.get_sublists()):
        _absorb_leading_comments(sgroup)

    idx = 0
    while idx < len(tlist.tokens):
        token = tlist.tokens[idx]
        if _is_comment(token):
            _, next_ = tlist.token_next(idx, skip_cm=True)
            if isinstance(next_, sql.IdentifierList):
                del tlist.tokens[idx]
                next_.insert_before(0, token)
                token.parent = next_
                _refresh_values(tlist)
                continue
        idx += 1


def _create_guard(tlist):
    """复刻旧 fork ``group_identifier_list`` 的 CREATE/ALTER 守卫。

    fork 在 ``group_identifier_list`` 开头做两件事（源码注释：「不需要处理：
    create/alter/insert 后，且在 with/select/values 前的 1-2 个括号」）：

    - ``CREATE``/``ALTER`` 且整条语句**没有** ``SELECT`` → 直接 ``return``，
      整条语句一个列表都不建；
    - 有 ``SELECT`` → 只跳过 ``SELECT`` **之前**的子组（典型是 ``create view x
      (col…) as select …`` 的字段列表括号），``SELECT`` 之后照常。

    官方 ``group_identifier_list`` 没有这层守卫，字段列表括号里会多出一个
    ``IdentifierList``，于是 ``LayoutPass._process_parenthesis`` 的字段列表分支
    把换行插到了那个列表前面 —— 而注释被 ``_absorb_leading_comments`` 放在列表
    首位，换行就落到了注释前面（``ddl/sqltest0_s03``）。

    返回 ``None`` 表示本层无守卫；``False`` 表示整层跳过；整数表示只跳过下标小于
    它的子组。
    """

    has_create = False
    for token in tlist.tokens:
        if token.ttype is T.DDL and token.normalized in ("CREATE", "ALTER"):
            has_create = True
            break
    if not has_create:
        return None

    for idx, token in enumerate(tlist.tokens):
        # 边界是「with / select / values 里最先出现的那个」——fork 的注释原文就是
        # 「create/alter/insert 后，且在 with/select/values 前的 1-2 个括号」。
        # 只认 SELECT 会把 `create view … as -- with c as (select …) … select * from c`
        # 这种 CTE 也一起跳掉：CTE 体括号在 `with` 之后，fork 是会正常建列表的
        # （漏掉就表现为 CTE 里的 select 列表不展开，`cte/sqltest2_s02`）。
        # 注意 `WITH` 是 `T.Keyword.CTE`，用 `Token.match(T.Keyword, …)` 匹配不上，
        # 必须用 `ttype in T.Keyword`。
        if token.match(T.DML, "SELECT") or (
            token.ttype in T.Keyword and token.value.upper() in ("WITH", "VALUES")
        ):
            return idx
    return False


def _flatten_identifier_lists(tlist):
    """把本层直属的 ``IdentifierList`` 子组整体摊平回本层（不改变 token 相对顺序）。

    ``_create_guard`` 说明的两种情形里，旧 fork 的 ``group_identifier_list``
    **不会**建列表，官方却会建。多出来的那层列表有两处副作用：

    - ``LayoutPass._process_parenthesis`` 的字段列表分支会把换行插到「列表」前面，
      而 ``_absorb_leading_comments`` 把前导注释放在列表首位，换行于是落到注释
      之前（``ddl/sqltest0_s03`` 期望注释与 ``(`` 同行）；
    - ``_align_create_columns`` 依赖括号内的扁平结构取字段基准偏移。

    这里把官方多出来的那层去掉，还原成 fork 的扁平形状。
    """

    for sgroup in list(tlist.get_sublists()):
        _flatten_identifier_lists(sgroup)

    idx = 0
    while idx < len(tlist.tokens):
        token = tlist.tokens[idx]
        if isinstance(token, sql.IdentifierList):
            tlist.tokens[idx:idx + 1] = token.tokens
            for child in token.tokens:
                child.parent = tlist
            _refresh_values(tlist)
            continue  # 摊平后同一位置可能又是子列表，重新检查
        idx += 1


def _walk(tlist):
    guard = _create_guard(tlist)
    if guard is False:
        # CREATE/ALTER 且无 SELECT：fork 整条不建列表，官方建的都摊平掉
        _flatten_identifier_lists(tlist)
        return
    _splice_continuations(tlist)
    for sgroup in list(tlist.get_sublists()):
        if guard is not None and tlist.token_index(sgroup) < guard:
            # SELECT 之前的子组（典型是字段列表括号）fork 不建列表
            _flatten_identifier_lists(sgroup)
            continue
        _walk(sgroup)
    # 已经是列表的层不再归并，否则会在列表内部再套一层列表
    if isinstance(tlist, sql.IdentifierList):
        return
    _group_level(tlist)


def _is_alias(token):
    """``over(...)`` 后面的隐式别名（``… asc)    rn`` 里的 ``rn``）。

    注意先判 ``Identifier`` 组：分组的 ``ttype`` 是 ``None``，用 ``ttype`` 判空会把
    已包成 ``Identifier`` 的别名直接漏掉。
    """
    if token is None or isinstance(token, sql.Comment):
        return False
    if isinstance(token, sql.Identifier):
        return True
    if token.ttype is None:
        return False
    return token.ttype in T.Name or token.ttype in T.String


def _last_function_of(token):
    """沿「最后一个非空白子 token」下钻，返回其中的 ``Function``；找不到返回 ``None``。"""
    while isinstance(token, sql.TokenList):
        if isinstance(token, sql.Function):
            return token
        nxt = None
        for child in reversed(token.tokens):
            if not child.is_whitespace:
                nxt = child
                break
        if nxt is None:
            return None
        token = nxt
    return None


def _attach_over_to_functions(tlist):
    """把 ``)`` 与 ``OVER`` 之间**夹着注释**的 ``OVER (…)`` 并回 ``Function``（U14）。

    官方 ``group_functions`` 判定要不要把 ``OVER`` 并进 ``Function`` 用的是**下标相邻**
    （``over_idx - 1 == tidx + 1``）：``)`` 与 ``over`` 之间只有空白时没问题（与 fork 同形，
    ``Function[Identifier, Parenthesis, ws, Over]``），夹了 ``Comment`` 时判定失败 ——
    ``OVER`` 被留在 ``Function`` 外面，而它前面的注释随即把外面的 ``IdentifierList``
    打断（列表不再按项展开、``over`` 也不另起一行 → ``cte/sqltest2_s02``）。

    这里做一次**靶向搬移**，还原 fork 的形状（fork 的 ``group_functions`` 本身就产出它）::

        IdentifierList[…,
          Identifier[Function[Identifier, Parenthesis, ws, Comment, Over], ws, as, ws, Identifier]]

    只在守卫全部成立时动手（锚点以 ``Function`` 且以 ``Parenthesis`` 收尾、中间只有
    空白与注释、后面那个子组以 ``Over`` 开头），否则原样返回。
    """

    for sgroup in list(tlist.get_sublists()):
        _attach_over_to_functions(sgroup)

    idx = 0
    while idx < len(tlist.tokens):
        holder = tlist.tokens[idx]
        if isinstance(holder, sql.Over):
            # 无显式 AS：官方把 `over(...)` 直接放在这一层（外面没套 Identifier）
            over, rest, end = holder, [], idx
        elif (
            isinstance(holder, sql.TokenList)
            and holder.tokens
            and isinstance(holder.tokens[0], sql.Over)
        ):
            # `over(...) as rn`：别名和 Over 在同一个子组里
            over, rest, end = holder.tokens[0], holder.tokens[1:], idx
        else:
            idx += 1
            continue

        # 往回收集「空白 + 注释」段；段内至少要有一个注释，否则官方已经处理过
        cursor = idx - 1
        comments = 0
        while cursor >= 0:
            token = tlist.tokens[cursor]
            if token.is_whitespace:
                cursor -= 1
                continue
            if isinstance(token, sql.Comment):
                comments += 1
                cursor -= 1
                continue
            break

        anchor = tlist.tokens[cursor] if cursor >= 0 else None
        fn = _last_function_of(anchor)
        if (
            not comments
            or fn is None
            or not fn.tokens
            or not isinstance(fn.tokens[-1], sql.Parenthesis)
        ):
            idx += 1
            continue

        # 锚点之后到 holder 之前（空白 + 注释）连同 Over 一起搬进 Function
        if rest:
            # `over(...) as rn`：别名与 Over 同在一个子组。只把 Over 搬进 Function，
            # 子组剩下的部分（ws + as + ws + 别名）就是同一列表项的其余内容。
            into_function = [*tlist.tokens[cursor + 1:idx], over]
            end = idx
        else:
            # 隐式别名（`… asc)    rn`）：它在 Over 后面，是本层的兄弟 token
            alias_ws = []
            scan = idx + 1
            while scan < len(tlist.tokens) and tlist.tokens[scan].is_whitespace:
                alias_ws.append(tlist.tokens[scan])
                scan += 1
            alias = tlist.tokens[scan] if scan < len(tlist.tokens) else None
            into_function = tlist.tokens[cursor + 1:idx + 1]
            if _is_alias(alias):
                rest = [*alias_ws, alias]
                end = scan
            elif (
                isinstance(alias, sql.IdentifierList)
                and alias.tokens
                and _is_alias(alias.tokens[0])
            ):
                # 别名被夹在一个多出来的列表里（`rn` + `,` + `from`）：摘出别名，
                # 剩下的 `,` / `from` 摊平回本层 —— fork 的尾部逗号本来就是散的
                rest = [*alias_ws, alias.tokens[0]]
                del alias.tokens[0]
                tlist.tokens[scan:scan + 1] = alias.tokens
                for child in alias.tokens:
                    child.parent = tlist
                end = scan - 1

        for child in into_function:
            child.parent = fn
        fn.tokens.extend(into_function)

        container = fn.parent if fn.parent is not None else anchor
        if rest:
            # 与 fork 同形：把「Function + 别名」重新包成同一个列表项
            new_item = sql.Identifier([fn, *rest])
            new_item.parent = container
            pos = container.token_index(fn)
            container.tokens[pos:pos + 1] = [new_item]
        del tlist.tokens[cursor + 1:end + 1]
        _refresh_values(fn)
        # 搬走后下标要重新检查（本层 token 数已变）
        continue

    return tlist


def group(stmt):
    """官方分组 + 本项目补偿。调用方用它替换 ``grouping.group``。"""
    _group_interval_literals(stmt)  # 必须在官方分组之前
    _wrap_keyword_alias_lhs(stmt)  # 必须在官方分组之前
    _pre_wrap_object_name(stmt)  # 必须在官方分组之前
    stmt = official.group(stmt)
    _walk(stmt)
    _unabsorb_trailing_comments(stmt)
    _absorb_leading_comments(stmt)
    _attach_over_to_functions(stmt)
    return stmt
