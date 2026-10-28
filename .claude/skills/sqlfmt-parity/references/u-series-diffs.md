# U 系列差异（官方 sqlparse 0.6.0 vs 旧 fork）

旧 fork = sqlparse 0.5.x 的大改写（`keywords.py` 差 1916 行、`grouping.py` 432、`aligned_indent.py` 948）。
**旧 fork 与对拍套件已在 S7 删除**（提交 `8de1fb7`）：仓库内没有 vendored `sqlparse`，
`pyproject.toml` 里它是 pip 依赖（`>=0.6,<0.7`）。本文的清单是**机理追溯** —— 每处补偿为什么存在、
调用时序受什么约束 —— **不是在跑的对照实验**（没有 `--fork` 侧可跑了）。

全部条目均已处置。每条给出：现象 → 根因 → 补偿落点 → **时序约束**。

## API / 引擎类

| 编号 | 现象 | 补偿 |
|---|---|---|
| U1–U4 | fork 独有 API：`FilterStack.run` 硬引用模块级 lexer 单例、无 `token_next_by(_reverse=True)`、`IdentifierList.get_identifiers` 不过滤注释、Doris 分词词表缺失 | `stack.FilterStack` 覆写 `run`；自写 `_token_prev_by`；调用处过滤注释；`policy` 补词表 |
| U5 | 官方 `Case.get_cases` 缺 fork 的 `--` 注释占位 | `LayoutPass._get_cases` 本地重写 |
| U6–U8 | 官方内部语义差异 | 实测无影响，**无需补偿** |
| U11 | 官方 lexer 空白是**逐字符** token（`' '*82` → 82 个长 1 的 token） | `whitespace.merge_whitespace_runs` + `filters/whitespace.StripWhitespaceFilter`。**必须在官方 `_stripws()` 之前**合并，否则 `_stripws_identifierlist` 只删逗号前最后一个空 token → 末尾逗号多 1 列 |

## 分词类

| 编号 | 现象 | 补偿 |
|---|---|---|
| U10 | 官方词表本有 `OVER`，但更靠前的「函数名正则」`[A-ZÀ-Ü]\w*(?=\()` 先把 `over(` 判成 `Name`，`sql.Over` 永远分不出来 | `policy.PRECEDENCE_REGEX` + lexer **index 0** 的优先级补丁 |
| U16 | 官方词表缺 `DATETIME`。两侧 `Name.Builtin` 段逐条相同，但 fork 的关键字正则**不要词尾边界**（`DATE` 把 `DATETIME` 前缀命中）→ `datetime` 落成普通 `Name` → 被 `group_identifier` 与字段名粘成 `Identifier` → DDL **类型列**取不到 token → 整条 DDL 列基准全错 | `policy.KEYWORDS_TYPES = {"DATETIME": T.Name.Builtin}`。**同类（`INT64`/`INT32`/`DATE32`…）照此加一条** |
| U17 | **官方自身的缺陷**（不是 fork 差异）：官方字符串正则 `'(''|\\'|[^'])*'` 只认「反斜杠 + 引号」这一支转义，**不认「反斜杠 + 反斜杠」** → 含双反斜杠的字符串字面量（MySQL / Doris 里表示「一个反斜杠」）**不闭合**，一路吞到下一个引号，中间整段 SQL 并进**同一个**字符串 token → 症状是「列对齐整体错乱 / 函数被拆开 / `'ex%'` 变 `'ex % '」 | `policy.STRING_ESCAPE_REGEX`（单引号 + 双引号两条，把「反斜杠 + 任意字符」当一个转义单元）+ `lexer.py` **无条件**插入（与方言无关，含 `dialect=None`）。与官方正则相比**只差**「反斜杠后面不是引号」这一种情形；`''` / `\'` / 结尾单反斜杠经回溯后与官方完全一致 |

**分词坑**：`Token.match(ttype, values, regex=True)` 是拿 values 里每一条**整正则**去 `pattern.search(token.normalized)`。所以多词关键字必须**先合并成一个 token** 才可能被 `split_words` 匹配（`lateral` + `view` 两个 token 谁都匹配不上 `LATERAL\s+VIEW`）。已给 `LATERAL VIEW` 补兜底合并（白名单条目之后按顺序尝试）。

## 分词组类

| 编号 | 现象 | 补偿 | 时序约束 |
|---|---|---|---|
| U9 | 官方 `group_as.valid_prev` 拒绝关键字作 AS 左值（fork 放宽成 `True`）→ `select level as depth` 别名不成组 → 字段列表被切碎 | `_wrap_keyword_alias_lhs`：只把该关键字本身包成 `Identifier` | 官方分组**前**。**必须排除 `END`**（`sql.Case.M_CLOSE`，提前包住会让 `group_case` 散架）与 `NULL` |
| U12 | 官方 `group_functions` 对「`T.Name` 紧跟 `Parenthesis`」无条件包 `Function`，叠加 `group_identifier` 不递归进 `Identifier` 子组 → DDL/INSERT 对象名链括号里的裸 `Name` 永不成 `Identifier`、字段列表不展开 | `_pre_wrap_object_name`：把对象名链预包成 `Identifier`（**只有链尾紧跟 `(`** 才包） | 官方分组**前** |
| U13 | 官方 `group_functions` 开头「本层同时有 `CREATE`+`TABLE` 且无 `AS` → 整条 `return`」（fork 没有）→ CREATE 里的 `duplicate key(...)`/`range(date_trunc(…))`/`hash(ID)` 退化成裸 `Name` + `Parenthesis`，被字段列表分支误展开 | `_wrap_create_table_calls`（+`_wrap_bare_calls`/`_call_head`）：把本层「`Name`/`Identifier[Name]`/非子句 `Keyword` + 紧随 `Parenthesis`」包成 `sql.Function` | 官方分组**之后**。放之前括号还没成组，得替官方跑 `group_parenthesis`，会打乱官方各步骤的先后假设。`_call_head` 必须排除**子句关键字** |
| U14 | 官方 `group_functions` 用**下标相邻**（`over_idx - 1 == tidx + 1`）判定要不要把 `OVER` 并进 `Function`；`)` 与 `over` 之间夹 `Comment` 时失败 → 注释把 `IdentifierList` 打断 | `_attach_over_to_functions`：把「ws + 注释 + Over」塞回 `Function`，再重包列表项；覆盖显式 `as rn` 与隐式 `over(…) rn` 两种写法 | **必须是 `group()` 的最后一步**。放 `_walk` 之前会被 `_group_level` 重新归并掉 |
| U15 | 官方 `group_identifier_list.valid_next` 认 `T.Keyword`，**尾逗号**后紧跟的子句关键字（`from`）被当成下一个列表项吞进列表 → 列对齐按「`from` + 表名」算基准 | `_trim_clause_tail`：把关键字连同逗号与空白退回父层（文本顺序不变） | **必须在 `_walk` 之后**，否则 `_group_level` 会重新吞回。只处理「尾逗号 + 子句关键字」这一种形状 |
| 补充 | 官方 `group_identifier_list.sqlcls` **不含 `sql.Parenthesis`**（`values (…),(…)` 永不成 `IdentifierList`，而 `_process_values` 依赖它） | `_SQLCLS` 补上 `sql.Parenthesis` | — |
| 补充 | fork 的 `group_identifier_list` 开头有 **CREATE/ALTER 守卫**（`CREATE`/`ALTER` 且无 `SELECT` → 整条不建列表；有 `SELECT` → `SELECT` **之前**的子组不建列表） | `_create_guard` + `_flatten_identifier_lists` 把官方多建的列表摊平 | 官方分组**之后** |

**`_create_guard` 边界坑**：边界应是 `with` / `select` / `values` 中**最先出现**的那个（只拿 `SELECT` 当边界会把 CTE 体括号一起跳掉 → `cte/sqltest2_s02`）。
**ttype 坑**：`WITH` 的 ttype 是 `T.Keyword.CTE`，`Token.match(T.Keyword, ("WITH",…))` **匹配不上**，必须写 `token.ttype in T.Keyword and token.value.upper() in ("WITH","VALUES")`。

**U14 三个坑**（别再踩）：
1. 调用位置必须在 `_walk` / `_unabsorb_trailing_comments` / `_absorb_leading_comments` **之后**。
2. `_is_alias` 要先判 `isinstance(token, sql.Identifier)` 再看 `ttype`——分组类的 `ttype` 是 `None`，写成「先 `if token.ttype is None: return False`」会把已包成 `Identifier` 的别名漏掉。
3. 换行/删除的**下标要一起算**：把 ws 段搬进 `Function` 时，删除区间必须覆盖 ws 段本身，否则同一 token 会出现在两处。
