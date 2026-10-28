# 差异与补偿 — 上游语义差异（U1–U17）与规则总表

> 用途：排查格式化差异、往 `sqlfmt_ext/` 加补偿之前读这里。
> 章号沿用原 `PLAN.md`（本文件含 §3.4 与 §4）。**诊断手法**（元规则一~七、工作流、坑位）
> 在技能 `sqlfmt-parity`（`.claude/skills/sqlfmt-parity/`），本文件不重复。

---

## §3.4 上游 0.6.0 与旧 fork 的语义差异清单

旧 fork 不是「官方 + 小补丁」，而是 **sqlparse 0.5.x + 大量改写**。把基线换成官方 0.6.0 后，
以下差异会直接影响输出。**结论**：U5–U7 是「官方内部语义」差异，无法通过外挂层参数解决，
只能在本项目里做等价补偿或接受少量差异。

| # | 位置 | 差异 | 处置（落点） |
|---|---|---|---|
| U1 | 官方 `keywords.SQL_REGEX` | 缺 Doris 条目（`ON COMMIT`/`REFRESH`/`DISTRIBUTED BY`/`LATERAL VIEW` 等） | ✅ 以**追加**方式补：现由 `dialects` 的 `extra_keywords` / `_DORIS_SPLIT_WORDS` 声明 |
| U2 | 官方 `lexer.Lexer` | 模块级单例，`FilterStack.run` 硬引用 | ✅ `DialectLexer` 子类 + `FilterStack.run` 覆写（只改 lexer 来源） |
| U3 | 官方 `TokenList.token_next_by` | 没有 `_reverse` 参数 | ✅ `stack._token_prev_by` 等价实现 |
| U4 | 官方 `IdentifierList.get_identifiers` | 不过滤注释（fork 过滤） | ✅ 在 `LayoutPass._process_identifierlist` 里过滤 |
| U5 | 官方 `Case.get_cases` | fork 增加了 `--` 注释占位逻辑（官方无注释分支，CASE 内行注释被并进条件） | ✅ `LayoutPass._get_cases` 按本项目口径本地重写同一遍历（不动官方类） |
| U6 | 官方 `Where.M_CLOSE` / `TypedLiteral.M_CLOSE` | 官方仅在 `Where.M_CLOSE` 里**多**一个 `'INTERSECT'` | ✅ 无需补偿（现有 fixture 的 WHERE 内不含它，分组边界一致） |
| U7 | 官方 `NameAliasMixin.get_real_name` | fork 取**第一个**点号，官方取最后一个 | ✅ 无需补偿（全量检索官方包：已无 filter / pass 调用点） |
| U8 | 官方 `statement_splitter` / `lexer.find_delimited_spans` | 0.6.0 是新实现（嵌套块、美元引号） | ✅ 对现有 fixture 无影响 |
| U9 | 官方 `grouping.valid_next` | fork 允许关键字作字段名 | ✅ `grouping._wrap_keyword_alias_lhs`（**必须排除 `END`**（`Case.M_CLOSE`）与 `NULL`） |
| U10 | 官方 `keywords.SQL_REGEX` 规则顺序 | 词表里有 `OVER`，但更靠前的「函数名」正则 `[A-ZÀ-Ü]\w*(?=\()` 把 `over(` 先判成 `Name` | ✅ `policy.PRECEDENCE_REGEX` + lexer **index 0** 优先级补丁 |
| U11 | 官方 lexer 的空白粒度 | **每个空白字符各一个 token**（fork 用 `[^\S\r\n]+` 合并成一个） | ✅ `whitespace.merge_whitespace_runs` + `filters/whitespace.py::StripWhitespaceFilter`（在官方 `_stripws()` **之前**合并） |
| U12 | 官方 `group_functions` | 把「`T.Name` 紧跟 `Parenthesis`」无条件当函数 → DDL/INSERT 对象名链的括号收不住，字段列表不展开 | ✅ `grouping._pre_wrap_object_name`（**官方分组前**，链尾紧跟 `(` 才包） |
| U13 | 官方 `group_functions` 的 CREATE+TABLE 早退 | 官方「`has_create and has_table and not has_as → return`」严于 fork → `duplicate key(...)` 等被字段列表分支误展开 | ✅ `grouping._wrap_create_table_calls`（**官方分组后**，`_call_head` 排除子句关键字） |
| U14 | 官方 `group_functions` 的 `OVER` 判定 | 用**下标相邻**判是否把 `OVER` 并进 `Function` → `)` 与 `over` 之间夹注释时判定失败 | ✅ `grouping._attach_over_to_functions`（**两处调用**：官方分组后立即一次 + `group()` 最后一步一次，见 §4.4） |
| U15 | 官方 `group_identifier_list.valid_next` | 认 `T.Keyword` → **尾逗号**后的子句关键字被吞进列表，列基准取错 | ✅ `grouping._trim_clause_tail`（**`_walk` 之后**） |
| U16 | 官方词表缺方言**类型名**（如 `DATETIME`） | 官方**整词匹配** → 类型名落普通 `Name` → 与字段名粘成一个 `Identifier` → **DDL 列基准全错** | ✅ 类型词表归位 `dialects`（Doris 20 个 + MySQL 11 个）；`JSON` 等官方判成 `Keyword` 的走 `type_name_keywords` |
| U17 | 官方 `keywords.SQL_REGEX` 的**字符串**正则 `'(''|\\'|[^'])*'` | 只认「反斜杠 + 引号」这一支转义，**不认「反斜杠 + 反斜杠」** → 含双反斜杠的字符串字面量**不闭合**，把后续整段 SQL 吞进同一个字符串 token（症状表现为「列对齐整体错乱」） | ✅ `policy.STRING_ESCAPE_REGEX`（单引号 + 双引号两条）+ `lexer.py` **无条件**插入（与方言无关，含 `dialect=None`）。**这条是官方自身的缺陷（不是 fork 差异）** —— 属「上游缺陷修正」 |

### §3.4.1 三个最常踩的坑

- **分词**：`Token.match(ttype, values, regex=True)` 对 values 里每条**整正则** `search` →
  **多词关键字必须先合并成一个 token** 才能被 `split_words` 匹配；反过来，`\b` 写松了会被 `search`
  在**词内部**命中（`straight_join` 撞 `JOIN\b`）。
- **换行锚点是「整 token 匹配」**：`LayoutPass.split_words` 的条目拿整条正则 `search` **单个 token**
  的 value → `ENGINE\s*=` 这类跨 token 写法**永远匹配不上**（`engine` 与 `=` 是两个 token），
  跨词锚点必须先用 `extra_lexer_rules` 合并成一个 token（S8-d 踩过）。**反向的坑**：因为是 `search`
  而不是整词匹配，**纯词锚点会在别的词内部命中**（裸 `SET` 撞 `OFFSET`/`CHARSET`，S12；
  `\bON` 撞 `ONLY`/`ONLINE`，S16）→ 纯字母锚点一律写 `\bXXX\b`，**前缀后缀都要**。
  该坑只对「官方判成 `T.Keyword` 的词」生效（锚点只匹配 Keyword token），实测没踩到的词不必改。
- **分组**：官方 `group_identifier_list.sqlcls` **不含 `sql.Parenthesis`** → `_SQLCLS` 补上；
  `_create_guard`+`_flatten_identifier_lists` 边界 = `with`/`select`/`values` 中**最先出现**者；
  `Token.match(T.Keyword, ("WITH",…))` **匹配不上** `T.Keyword.CTE`，须写 `ttype in T.Keyword`。

---

## §4 规则总表

布局规则全在 `passes/layout.py`，对齐规则全在 `passes/align.py`（以 mixin 组合进 `LayoutPass`）。
旧 fork 参考位置 `sqlparse/filters/aligned_indent.py`（S7 已随 fork 删除）—— 参考的是
**「期望语义」**，与擦除相关的部分一律不移植。

### 4.1 布局规则（只改换行位置）

| # | 规则 | 旧参考 |
|---|---|---|
| L1 | **注释强制换行**：单行 `--`、块 `/* */`、`/*-*/` 强制换行标记，前后各自成行；连续注释按原分组保留换行 | `ai.py::_process_comment`、`_take_comments_before` |
| L2 | **括号内字段列表展开**：CREATE / ALTER / INSERT 的 `(cols)` 逐列换行 | `ai.py::_process_parenthesis` |
| L3 | **语句 / CTE 换行**：`as with ... as (` 中 `as` 后换行 | `ai.py::_split_statements`、`_process_statement` |
| L4 | **多 LATERAL VIEW 各自分行** | `ai.py::_is_lateral_view_list`、`_split_kwds` |
| L5 | **CASE 首个 WHEN 独占一行** —— ⚠️ 旧实现依赖**输入换行**；S5c 已按结构性口径**重定**为「同行」 | `ai.py::_process_case` |
| L6 | **`select * from` 折叠同行** | `ai.py::_is_simple_select_star` |
| L7 | **`ON COMMIT` 刻意分行**（S9 已结构化：命中者一律按分词切开，不看输入写在哪一行） | `ai.py::_normalize_newlines` 白名单 |

### 4.2 对齐规则（只改同行空白宽度）

| # | 规则 | 旧参考 |
|---|---|---|
| A1 | **字段列表对齐**：`AS` / 别名按列右对齐，逗号前填充 | `ai.py::_identifier_layout(s)`、`_apply_identifier_layout`、`_align_identifierlist`、`_set_adjacent_ws` |
| A2 | **DDL 列块对齐**：名称 / 类型 / 约束 / 默认值 / 注释分列对齐 | `ai.py::_create_field_lines`、`_create_column_target`、`_align_create_columns` |
| A3 | **注释列对齐**：行首注释跟随所属列 | `ai.py::_process_comment` 的对齐分支 |

### 4.3 明确**不移植**（旧架构遗留）

`ai.py` 的 `_flatten_up_to_token`、`_remove_prev_newline`、`_collapse_newlines`、
`_normalize_newlines`、`_collapse_newline`、`_pull_inline`、`_prev_non_whitespace`、
`_fold_case_newlines` —— 这些是「strip 保留换行」的补丁，C4 下天然消失。
（`LayoutPass` 内部的同名增减空白工具是**另一回事**：它们管理本 pass 自己插入的空白。）

---

## §4.4 `grouping.py` 补偿层（11 处补偿 / 12 个调用点）与调用时序

**官方分组前**：
1. `_group_interval_literals` —— 裸 `interval 1 day` 预成组 `TypedLiteral`（官方 `M_CLOSE` 只认 `T.String.Single`）
2. `_wrap_keyword_alias_lhs`（U9）
3. `_pre_wrap_object_name`（U12）
4. `_pre_merge_top_clause` —— `TOP <n> [PERCENT]` / `TOP (<n>)` 合成**单个 `T.Keyword`**
   （闸门 = TOP 在本方言是不是 `Keyword`；`Identifier` 组会被列表 extend 吸走，实测失败）

**官方分组后**：
5. `_attach_over_to_functions`（U14 **第一次**，**必须早于 `_walk`**）：官方 `align_comments`
   会把「`)`` 与 ``over`` 之间」的注释并进 `Function` 末尾，此时 `over(…) as x` 还只是本层的
   `Identifier` 兄弟。拖到 `_walk` 之后，`_group_level` 已把它当成**新列表项的开头**（列表在
   `Function` 处被切断）→ 同一张字段列表被拆成两张、各自算列基准，`over` 被顶到很远的列上。
6. `_walk` / `_group_level` + `_splice_continuations`
7. `_unabsorb_trailing_comments` + `_absorb_leading_comments`（撤销官方 `align_comments` 的「并入前一个 TokenList」）
8. `_create_guard` + `_flatten_identifier_lists`（边界 = `with`/`select`/`values` 中最先者）
9. `_trim_clause_tail`（U15，**必须在 `_walk` 之后**）
10. `_wrap_create_table_calls`（U13）
11. `_extend_adjacent_lists` + `_normalize_adjacent_lists`（按**活下标**重扫并回）
12. `_attach_over_to_functions`（U14 **第二次**，**最后一步**；`_normalize_adjacent_lists` 并回后
    才凑齐「`Function` + 注释 + `Over`」的 `nested/sqltest3_s01` 靠这一次）

辅助 `_refresh_values`：`TokenList.value` 是构造期缓存，搬动 token 后必须刷新。

**U13 这类「把括号包进别的组」会让 layout 收不到那个括号** → 排查先看**括号的父组是谁**
（`LayoutPass._process` **按组类名分发**）。

## §4.5 换行锚点两个消费方（长期口径）

同一个锚点词被两处消费，**必须分开看**：

| 消费方 | 取词表 | 口径 |
|---|---|---|
| 布局层（`LayoutPass.split_words`） | `policy.split_words` + **本方言**的 `extra_split_words` | 是否换行 |
| 分组层（`grouping._is_clause_keyword`） | `dialects.all_split_words()` = 通用词 + **所有方言**锚点的并集 | 子句头 → `properties (1)` 包 `Function` 还是留关键字 |

分组层**必须与方言无关**：否则「开关一动，整条 SQL 的结构都变」（S8-a 实测踩过）。
