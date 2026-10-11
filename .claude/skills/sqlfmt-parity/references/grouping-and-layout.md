# 分组补偿层与布局架构

## `sqlfmt_ext/` 结构

| 文件 | 职责 |
|---|---|
| `options.py` | `DEFAULT_OPTIONS`（`dialect` 默认 `"doris"`）+ 官方 `validate_options` |
| `policy.py` | 换行锚点词、Doris 分词补丁、`PRECEDENCE_REGEX`、`KEYWORDS_TYPES` |
| `lexer.py` | `DialectLexer`：`default_initialization()` 后追加词表/规则 |
| `stack.py` | 复用官方 `build_filter_stack`，只做「覆写 `run` 注入 lexer / 换装 operators、whitespace filter / 摘官方 `AlignedIndentFilter`+`ReindentFilter`，原位放 `LayoutPass`」 |
| `grouping.py` | 官方分组前后的口径补偿（见下） |
| `whitespace.py` | `merge_whitespace_runs`（U11） |
| `filters/whitespace.py` · `filters/operators.py` | 官方子类 |
| `passes/layout.py` | `LayoutPass`：**唯一**换行/缩进决策处，继承 `AlignMixin` |
| `passes/align.py` | `AlignMixin`：标识符列表 / DDL 字段 / 注释列对齐 |
| `dialects.py` | `Dialect` dataclass + 注册表（doris / selectdb / sqlserver 留位） |

**两处架构决策**
1. 官方 indent filter **不进 stack**——它每级 8 列，本项目 6 列。
2. 对齐用 **mixin** 而非后置 pass——断行宽度与对齐互相依赖。

**子类化坑**：官方 `process()` 里以**类名**硬引用自己的 `_process`，子类覆盖 `_process` 时必须**同时覆盖 `process`**，否则覆盖无效。

## 官方分组步骤顺序（查「谁先谁后」）

```
group_comments, group_brackets, group_parenthesis, group_case, group_if, group_for,
group_begin, group_over, group_functions, group_where, group_period, group_arrays,
group_identifier, group_order, group_typecasts, group_tzcasts, group_typed_literal,
group_operator, group_comparison, group_as, group_aliased, group_assignment,
align_comments, group_identifier_list, group_values
```

要点：
- `group_identifier` 是 `@recurse(sql.Identifier)`——**不递归进 `Identifier` 子组**，只包裸 `T.Name`/`T.String.Symbol`。
- `group_period` / `group_functions` 早于它；`group_as` / `group_identifier_list` / `group_values` 最后。
- 官方 `group_identifier_list` 是 `_group(..., recurse=True)`，**会递归进 `Parenthesis`**——「语句层没建列表」不代表括号里没建；想「不建」必须在官方之后摊平回来。

## `grouping.py` 补偿层（10 处）

**官方前**
1. `_group_interval_literals` — 裸 `interval N unit` 预成 `TypedLiteral`（官方 `group_typed_literal.M_CLOSE` 只认 `T.String.Single`）。
2. `_wrap_keyword_alias_lhs` — U9。
3. `_pre_wrap_object_name` — U12。

**官方后**
4. `_walk` / `_group_level` + `_splice_continuations` — 容忍注释的逗号列表归并；`recurse=False`，自己递归、跳过已成组的 `IdentifierList`，续接子列表先摊平防嵌套。
5. `_unabsorb_trailing_comments` + `_absorb_leading_comments` — 撤销官方 `align_comments` 的「并入**前一个** TokenList 末尾」，还原 fork 口径「并入**后一个** `IdentifierList` 首位」。
6. `_create_guard` + `_flatten_identifier_lists` — 复刻 fork 的 CREATE/ALTER 守卫。
7. `_trim_clause_tail` — U15。
8. `_wrap_create_table_calls` — U13。
9. `_extend_adjacent_lists` + `_normalize_adjacent_lists` — 官方 `_group` 用「快照下标 − 累计 `tidx_offset`」定位，多次合并后**偏移记账漂移**，末尾逗号轮不到；fork 的语义是「扩展相邻同类组」。按**活下标**重扫本层并回（等价官方 `extend=True`）。
   - 合并条件包含「第二张表以**注释**开头」时，必须写 `_is_comment(first) or first.ttype in T.Comment` —— 分组阶段的注释是 **`sql.Comment` 组**，`ttype` 为 `None`，只判 `ttype` 会**静默漏掉**（曾因此误判成「形态假设错」）。
10. `_attach_over_to_functions` — U14。

**调用顺序是「穿插两次」的**（`group()` 里的真实次序，改动前务必核对）：

```
_official.group(stmt) → _walk → _wrap_create_table_calls → _trim_clause_tail
  → _unabsorb_trailing_comments → _absorb_leading_comments
  → _attach_over_to_functions          # 第 1 次
  → _normalize_adjacent_lists          # U14 补包合回去之前，两张表还不相邻
  → _attach_over_to_functions          # 第 2 次：合并把 Function + 注释 + Over 凑回同层后才认得出
```

少任何一次都会让某个用例单独变红（`case/sqltest4_s01` 与 `nested/sqltest3_s01` 各依赖一次）。

**辅助**：`_refresh_values` — `TokenList.value` 是构造期缓存，搬动 token 后**必须刷新**。

## 遍历坑

`group_tokens` 会**就地改动** `tlist.tokens`。所以遍历要用 `for anchor in list(tlist.tokens)` + `tlist.token_index(anchor)`（后者返回可能为 `None`，必须检查），不要用 `range(len(...))`（会 `IndexError`）。

## 注释缩进口径（用户 2026-09-12 定，长期有效）

> 「注释串**原本在列 0 的保持不变，其它的随所在层级对齐**。」

落点两处：
1. `_break_between_comments` 里「两条注释之间有空白」那一支用 `self.nl(0).value`——`nl(0)` 的语义**本就是**「换行 + 本层缩进」（`self.n + self.char * self.leading_ws`），不要写成只剩换行。
2. `_process_comment` 的 `hasattr(plist, "M_OPEN")` 支：当注释组前面还有内容、且那段内容**以注释结尾**时，改取**那段内容的偏移**（注释串延续 → 同层级）。

**两个坑**
- `sql.Comment` **自己也是 `TokenList`**。判「以注释结尾」必须**先判自身**再下钻；先下钻会落到 `Token.Comment.Single`（普通 Token）上判成 False。
- 第 2 条必须**收窄**到「以注释结尾」。放宽会踩 `comma/sqltest7_s01`（前一段是逗号的行尾注释，误用该偏移会把 `)` 行从 24 空格推到 37）。

另：`sql.Comment` 是**分组类**，裸注释 token 是 `T.Comment` **token 类型**；判定要写 `isinstance(tk, sql.Comment) or tk.ttype in T.Comment`。
