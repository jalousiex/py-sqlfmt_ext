# PLAN — 基于官方 sqlparse 重构 py-sqlfmt

> 状态：已定稿，开始分步实施
> 制定：2026-09-12
> 关联：[AGENTS.md](AGENTS.md) · [README.md](README.md)

---

## 1. 目标 / 非目标 / 硬约束

### 目标
1. **唯一目的**：SQL 格式化效果更美观、符合个人习惯。
2. **可低成本合并官方更新**（主要是分词、方言特性）。
3. **收敛性**：输出只取决于 token 流，与输入空白无关。
4. **幂等性**：格式化两次结果一致。

### 非目标
- 不做 SQL 语义校验；不重排、不增删非空白 token。

### 硬约束（重构不变量）
| # | 约束 | 理由 |
|---|---|---|
| C1 | 不修改、不复制 `sqlparse` 源码；官方包保持 pristine，只作 pip 依赖 | 官方更新可低成本合并 |
| C2 | 不 monkey-patch 官方函数；需要改行为的 filter 用「子类化 + 换装实例」 | 改动可审计、可撤销 |
| C3 | 不复制官方 `build_filter_stack` 装配逻辑 | 官方新增/调整 filter 顺序能自动继承 |
| C4 | 不使用「strip 阶段保留换行」的魔改 | 旧擦除层的根因 |
| C5 | pass 只允许改写 `Whitespace` token；不得改 `ttype` / 顺序 / 删除非空白 token | 保证骨架与对齐职责分离 |

---

## 2. 架构

### 2.1 管线（落地形态）

```
sql
 → DialectLexer（官方 Lexer 子类，追加 Doris 分词补丁）  （本项目）
 → StatementSplitter / grouping / 其余 preprocess      （官方）
 → 官方 SpacesAroundOperatorsFilter                    （本项目换装子类，泛型尖括号）
 → 官方 strip（换行压成 ''/' '）                        （官方）
 → LayoutPass  ← 唯一的换行骨架 + 同行对齐规则集        （本项目）
 → SerializerUnicode                                   （官方）
```

**相对计划的两处修订（落地后确认）：**

1. **官方 `AlignedIndentFilter` 不再放进 stack。** 它只有 `char` 一个参数、
   缩进口径也不同（每级 8 列 vs 本项目 6 列），留在 stack 里只会产出一份立刻
   被覆盖的空白。装配仍完全由官方 `build_filter_stack` 决定，本项目只是在装配
   后**原位摘掉**它（同 `_swap_operators_filter` 的手法）。
2. **对齐规则以 mixin 组合进 `LayoutPass`，不做成独立后置 pass。** 断行宽度与
   列对齐互相依赖（例如 CASE 的 THEN 对齐要先知道条件宽度），拆开需要重复遍历
   并重复计算偏移，收益不抵风险。规则集仍物理隔离在 `align.py`。

**核心洞察**：官方 strip 之后 token 流里没有任何原始换行，因此
「换行骨架」完全由官方 filter 决定，本项目只做**增量修饰**。
旧实现之所以需要一整套擦除层（`_remove_prev_newline` / `_collapse_newline(s)` /
`_normalize_newlines` / `_pull_inline` / `_prev_non_whitespace`），唯一原因是
本地改写了 strip 让换行残留；新架构下这类函数**结构性不存在**，
收敛性从「需要维护」变成「不可能违反」。

### 2.2 分层职责

| 文件 | 职责 | 允许依赖 |
|---|---|---|
| `sqlfmt_ext/options.py` | 默认选项 + 扩展项校验，转交官方 `validate_options` | 官方 |
| `sqlfmt_ext/policy.py` | 格式化口径：换行锚点关键字（`split_words`/`join_words`/`by_words`）+ 分词补丁表 | 官方 |
| `sqlfmt_ext/lexer.py` | `DialectLexer`：官方 `Lexer` 子类，初始化后追加方言补丁 | 官方 |
| `sqlfmt_ext/stack.py` | 装配：复用官方 `build_filter_stack`，注入 lexer、换装 operators filter、摘换行 filter | 官方 |
| `sqlfmt_ext/filters/` | 官方 filter 的**子类**（唯一允许替换官方行为的地方） | 官方 |
| `sqlfmt_ext/passes/layout.py` | 断行骨架 + 缩进宽度（唯一换行决策处） | 官方 |
| `sqlfmt_ext/passes/align.py` | 同行空白宽度（列对齐规则集，mixin） | 官方 |
| `sqlfmt.py` | **最终**只作薄 shim，转发到 `sqlfmt_ext` | `sqlfmt_ext` |

### 2.3 迁移期共存

```
仓库根 sqlparse/        旧 fork，仅作行为参考与 oracle，不删直到 S6
sqlfmt_ext/             新实现
tests/                  主套件（当前跑在旧 fork 上，S6 后切到新实现）
tests_migration/        对拍进度条（跑在官方 + 新实现上）
```

`tests_migration/conftest.py` 把仓库根挪到 `sys.path` 末尾，让 `.venv` 的官方包优先；
S7 删除 fork 后该 conftest 一并删除。

> ⚠️ **两个套件不能在同一次 pytest 会话里一起跑**：上面这个 `sys.path` 调整是
> **进程级**副作用（同进程只能加载一个 `sqlparse`），而 `tests/` 依赖仓库内旧
> fork。混跑会静默出现「主套件 117 个失败」。`tests_migration/conftest.py` 里的
> `pytest_configure` 已经把这种混跑拦成明确报错，并提示分别运行的方式。

---

## 3. 现状基线（度量，2026-09-12）

### 3.1 对拍基线

`.venv\Scripts\python.exe _tmp_parity.py`

| 类别 | 数量 |
|---|---|
| 逐字节一致 | 1 / 31（`debug/sqldebug_s02`） |
| 仅空白宽度不同 | 6 / 31 |
| 换行骨架不同 | 24 / 31 |

> **当前进度（2026-09-13，S6 完成）**：`pytest tests_migration/ -q` → **`31 passed`**
> （`KNOWN_DIFF` **已清空**）+ **1 条有意偏离**（`case/s03`，已是断言项，见 §4）。
> 实现能复现的用例**已全部通过**，下一段 = **S7 收敛 / 删 fork**（执行卡见 §9.4）。
> （空白归一化 U11 曾一次性把 8 个用例从「待实现规则」变成逐字节一致——它们的首处差异
> 本来就是该处 ±1 列宽，不是换行骨架差异，见 §3.5、§9.2。）

> **修正**：早先 `_tmp_official_ai4.py` 得出的「28/31 骨架一致」是**偏乐观**的结论——
> 当时只把 `AlignedIndentFilter` + `strip` 换成官方，其余（`grouping` / `sql` /
> `lexer` / `keywords` / `operators` / `statement_splitter`）仍是 fork 实现。
> 全官方 pipeline 下差异大得多。**全官方 pipeline 才是真实基线。**

### 3.2 差异归因

24 个骨架差异收敛为 **6 组规则**（见 §4），不是 24 个独立 bug。
其中「注释强制换行」一条规则覆盖 12 个用例。

### 3.3 测试现状

| 套件 | 命令 | 现状 |
|---|---|---|
| 全套件（唯一） | `.venv\Scripts\python.exe -m pytest -q` | `239 passed`（0 failed / 0 xfailed） |

> 迁移期的「主套件（旧 fork）+ 对拍进度条（`tests_migration/`）」两套件已在 S7 随 fork
> 一起删除（见 §9.4），旧对拍用例并入了 `tests/`。四个门禁（输出回归 / 幂等 / 收敛 / 对拍）
> 现在都在 `tests/` 里；收敛门禁的 `KNOWN_DIVERGENT` 已在 S10 清空（见 §9.7）。

### 3.4 上游 0.6.0 与旧 fork 的语义差异清单（迁移的真实成本）

用脚本逐项对比得到的结论：旧 fork 不是「官方 + 小补丁」，而是 **sqlparse 0.5.x
+ 大量改写**。把基线换成官方 0.6.0 后，以下差异会直接影响输出，已确认的有：

| # | 位置 | 差异 | 处置 |
|---|---|---|---|
| U1 | 官方 `keywords.SQL_REGEX` | 缺 Doris 条目（`ON COMMIT`/`REFRESH`/`DISTRIBUTED BY`/`LATERAL VIEW` 等） | ✅ 已在 `policy.py` 以追加方式补上 |
| U2 | 官方 `lexer.Lexer` | 模块级单例，`FilterStack.run` 硬引用 | ✅ `DialectLexer` 子类 + `FilterStack.run` 覆写（只改 lexer 来源） |
| U3 | 官方 `TokenList.token_next_by` | 没有 `_reverse` 参数 | ✅ 用 `_token_prev_by` 等价实现 |
| U4 | 官方 `IdentifierList.get_identifiers` | 不过滤注释（fork 过滤） | ✅ 在 `_process_identifierlist` 里过滤 |
| U5 | 官方 `Case.get_cases` | fork 增加了 `--` 注释占位逻辑（官方无注释分支，CASE 内行注释被并进条件） | ✅ 在 `LayoutPass._get_cases` 里按本项目口径重写同一遍历（不动官方类）；`case/sqltest4_s02` 因此转正 |
| U6 | 官方 `Where.M_CLOSE` / `TypedLiteral.M_CLOSE` | 实测官方仅在 `Where.M_CLOSE` 里**多**一个 `'INTERSECT'`，`TypedLiteral.M_CLOSE` 相同 | ✅ 结论：无需补偿。现有 fixture 的 WHERE 内不含 `INTERSECT`/`ORDER BY` 等，分组边界一致 |
| U7 | 官方 `NameAliasMixin.get_real_name` | fork 取**第一个**点号，官方取最后一个 | ✅ 结论：无需补偿。全量检索官方包，`get_real_name`/`get_name` 已无 filter 调用点；本项目 pass 也不调用 |
| U8 | 官方 `statement_splitter` / `lexer.find_delimited_spans` | 0.6.0 是新实现（嵌套块、美元引号） | ✅ 对现有 fixture 无影响 |
| U9 | 官方 `grouping.valid_next` | fork 允许关键字作字段名 | ⏳ 未处理，暂未观察到影响 |
| U10 | 官方 `keywords.SQL_REGEX` 规则顺序 | 词表里有 `OVER`，但更靠前的「函数名」正则 `[A-ZÀ-Ü]\w*(?=\()` 把 `over(` 先判成 `Name`，`sql.Over` 永远分不出来 | ✅ 已修：`policy.PRECEDENCE_REGEX` + lexer「优先级补丁」插入点 |
| U11 | 官方 lexer 的空白粒度 | **每个空白字符各一个 token**（fork 用 `[^\S\r\n]+` 合并成一个） | ✅ 已修：`whitespace.merge_whitespace_runs` + `filters/whitespace.py::StripWhitespaceFilter`（strip 前先合并空白段），见 §3.5 |

**结论**：U5–U7 是「官方内部语义」差异，无法通过外挂层参数解决，只能
（a）在本项目里做等价补偿，或（b）接受少量输出差异。
每条都要单独评估，属于 S2–S5 的隐藏成本。

### 3.5 U11：官方 lexer 的空白是「逐字符」token（列对齐 ±1 的根因）

实测（`.venv` 官方 0.6.0）：

```
>>> sqlparse.parse('select a' + ' '*82 + 'as b')[0]
空白 token 数 = 84，每个 value 长度都是 1
```

即官方 lexer 把**每个空白字符**各产出一个 token；随后官方 `strip` 把一段连续空白
变成「首个 token 保留 `' '`、其余全部置 `''`」。旧 fork 的 lexer 用 `[^\S\r\n]+`
把一段空白合并成**一个** token，因此 fork 里所有「改写某个相邻空白 token」的代码
（`_set_adjacent_ws`、`_collapse_newline`、`_remove_prev_newline`、
`_take_comments_before`）都建立在「一段空白 = 一个 token」这个前提上。

移植到官方 token 流后前提不成立：`_set_adjacent_ws` 只改写紧邻目标的**那一个**空
token（通常是 value 为 `''` 的那个），同一段里保留的 `' '` 与其余空 token 仍在原地
→ **列宽整体多 1**（`aggregate/sqltest5_s01`、`s02` 当前唯一残留差异：
`select TJNY` 的 `as` 落在 94 列，期望 93 列），并在树里留下大量 value 为 `''` 的
空白 token（实测单个 `Identifier` 内能堆 82 个）。

**证据链**：`_tmp_ws_when.py` 在 LayoutPass 前后审计空空白 token（前 246 / 后 243）；
`_tmp_align_trace.py` 打印被替换的空白 token（官方侧 `ws='' ws_idx=83`，
fork 侧 `ws=' ' ws_idx=1`）；两侧 `_identifier_layouts` 的汇总值**完全一致**
（`max_as_offset=94`、`as_offset=12`）——差异只出在「改哪个空白 token」。

**落地处置（最终版，比原计划更靠上游）**：在**官方 strip 之前**（而不是
`LayoutPass` 入口）先把每层 token 列表里的连续空白合并成一个 —— 新增
`sqlfmt_ext/whitespace.py::merge_whitespace_runs`，并用
`sqlfmt_ext/filters/whitespace.py::StripWhitespaceFilter`（官方 filter 的子类，
符合 C2）在 `_stripws()` 之前调用它，再换装进 stack。

为什么必须放在 strip **之前**：官方 `_stripws_identifierlist` 只删掉逗号前的
**最后一个**空白 token（它假设「一段空白 = 一个 token」）；逐字符空白下它在
`' '*82` 里只删掉 1 个，剩下的 1 个空格留在逗号前，与 `AlignMixin` 填好的对齐
空白叠加 → **非 AS 字段的末尾逗号整体多 1 列**。合并后再 strip，删掉的就是整段。
`LayoutPass.process` 入口保留同一函数的兜底调用（幂等，无重复语义）。

合并只做 Whitespace 改写（C5）：value 取拼接（段内字符总量不变，`TokenList.value`
缓存无需刷新），ttype 沿用段首 token —— 与官方 strip 逐字符产出时「首 token 保留
值、其余置空」的口径一致，**不引入也不消除任何换行语义**（`is_newline` 仍等价于
「该段首字符是换行」）。

**效果**：对拍 `5/26` → **`14/17`**。8 个原以为需要 L2/L3/A1 规则的用例
（`aggregate/s01`、`cte/s01`、`ddl/s05`、`dml/s03`、`dml/s05`、`dml/s07`、
`dml/s08`、`window/s02`）实际只是这一条 ±1，转正后 §4 的规则→用例映射需按
**剩余 17 个**重算（见 §4）。

---

## 4. 规则总表（**规划期记录**：全部已落地，行内标注收尾阶段）

旧 fork 参考位置：`sqlparse/filters/aligned_indent.py`（下称 `ai.py`，S7 已随 fork 删除）。
**注意**：参考的是「期望语义」，不是「实现方式」——旧实现里与擦除相关的部分一律不移植。
L1 的**跨注释组**部分（同层并列的两段注释不共享一行）在 **S9** 才补成结构性口径，
见 §9.6；L5 的口径在 S5c 重定、S7 重定基线。

### LayoutPass（只改换行位置）

| # | 规则 | 目标用例 | 旧参考 |
|---|---|---|---|
| L1 | **注释强制换行**：单行 `--`、块 `/* */`、`/*-*/` 强制换行标记，前后各自成行；连续注释按原分组保留换行 | 12 个 | `ai.py::_process_comment`(497)、`_take_comments_before`(172) |
| L2 | **括号内字段列表展开**：CREATE / ALTER / INSERT 的 `(cols)` 逐列换行 | 7 个 | `ai.py::_process_parenthesis`(204) |
| L3 | **语句 / CTE 换行**：`as with ... as (` 中 `as` 后换行 | 3 个 | `ai.py::_split_statements`(899)、`_process_statement`(197) |
| L4 | **多 LATERAL VIEW 各自分行** | 1 个 | `ai.py::_is_lateral_view_list`(160)、`_split_kwds`(812) |
| L5 | **CASE 首个 WHEN 独占一行**（⚠️ 旧实现在 `has_nl and direct_after_case` 上判定，即**依赖输入换行**；官方 strip 之下没有该换行，需重新定义为结构性规则，或在 S7 重定基线） | 1 个 | `ai.py::_process_case`(427) |
| L6 | **`select * from` 折叠同行** | 1 个 | `ai.py::_is_simple_select_star`(870) |
| L7 | **`ON COMMIT` 刻意分行**（白名单；S9 已结构化 —— 命中者一律按分词切开，不再看输入写在哪一行） | 1 个 | `ai.py::_normalize_newlines`(87) 白名单 |

### AlignPass（只改同行空白宽度）

| # | 规则 | 目标用例 | 旧参考 |
|---|---|---|---|
| A1 | **字段列表对齐**：`AS` / 别名按列右对齐，逗号前填充 | 6 个 | `ai.py::_identifier_layout`(633)、`_identifier_layouts`(656)、`_apply_identifier_layout`(672)、`_align_identifierlist`(703)、`_set_adjacent_ws`(619) |
| A2 | **DDL 列块对齐**：名称 / 类型 / 约束 / 默认值 / 注释分列对齐 | 覆盖在 L2 用例内 | `ai.py::_create_field_lines`(716)、`_create_column_target`(750)、`_align_create_columns`(760) |
| A3 | **注释列对齐**：行首注释跟随所属列 | 覆盖在 L1 用例内 | `ai.py::_process_comment`(497) 中的对齐分支 |

### 明确**不移植**（旧架构遗留）

`ai.py` 的 `_flatten_up_to_token`(28)、`_remove_prev_newline`(58)、
`_collapse_newlines`(81)、`_normalize_newlines`(87)、`_collapse_newline`(122)、
`_pull_inline`(131)、`_prev_non_whitespace`(149)、`_fold_case_newlines`(395)。
这些是「strip 保留换行」的补丁，C4 下天然消失。

### 规则 → 用例映射（2026-09-12 第三轮刷新）

分类口径用 `_tmp_check.py` 的摘要（「S 类」= 该用例每一处差异行都只是空白宽度/列对齐）。
**L1（注释断行）、L2（括号字段列表展开）、L4（多 LATERAL VIEW）已清零**（S3 / S4 / S5a）。

```
S6b 列表末尾列 (3): case/s01 | nested/s01 | window/s03

合计 3，与当前 3 个 xfailed 一一对应
（S6 起点是 7 个：nested/s02 与 window/s01 由 U15 修好；ddl/s02 由 U16 修好；
  ddl/s01 由 U13 补包修好）

有意偏离 (1): case/s03（`case` 与首个 `when` 同行 —— 旧基线那处折行依赖输入换行，
             按结构性口径重定，见下方清单）
```

> `ddl/s01` 除了列对齐，还差一条**分组**差异（官方 `group_functions` 对
> CREATE+TABLE 提前 `return`，fork 没有这个条件 → `duplicate key(...)` /
> `range(...)` / `hash(...)` 被字段列表分支误展开），见 §9.3「S4c」。

#### 对旧 fork 的有意偏离清单（S7 交付必须交代）

**定义**：新架构**刻意不复现**旧基线的用例。与「未复现」不同，这些不是待做项，而是**口径重定**。
登记在 `tests_migration/test_parity.DEVIATIONS`，并且是**断言项而不是 xfail** —— 基线或实现任一侧
漂移都会红（xfail 会让漂移静默通过）。每项必须写清「差在哪、为什么」。

| # | 用例 | 旧基线 | 新口径 | 为什么 |
|---|---|---|---|---|
| 1 | `case/sqltest4_s03` | `case` 与首个 `when` 各占一行 | 首个 `when` 与 `case` 同行：`case when b in ('X', 'Y') then …` | 旧基线**依赖输入换行**（该用例的 `input.sql` 就是 `case` 换行 + `when` 顶格），属 C4 禁止依赖的行为；「同行」才是仓库主导口径 —— `sqltest4_s01`（**没有 input 文件**，即 canonical 即输入，`case` 后仅在有注释时才换行）、`sqltest4_s02`、`dml/sqltest1_s06` 全部同形。与旧基线的差异**仅此一处折行**，`when b = 'NUMBER'    then …` / `else … c` / `end as type_name` 的列对齐逐字节相同。 |

> **迁移期不动 fixture**：`case/sqltest4_s03.sql` 同时是主套件（旧 fork）的期望输出 ——
> 旧 fork 靠「保留输入换行」产出那个折行，改了它主套件立刻变红（`170 passed, 6 xfailed` 门槛）。
> 等 S7 删掉 fork 后，若用户认可新口径，再把该 fixture 正式重定并从 `DEVIATIONS` 移除；
> 届时那个定向变换会失效，`test_parity` 里的 `assert transformed != expected` 会直接报错提醒。

**U9 的教训**：`debug/sqldebug_s01` 首版被归成 A1「列对齐未实现」，真因是**分组**——
官方 `group_as.valid_prev` 拒绝「关键字作 AS 左值」（旧 fork 放宽成 `True`），
`select level as depth` 直接散架。凡是「列对齐整体乱掉」的用例，先查分组再查对齐。

**首版映射（U11 之前，30 个 xfailed）供追溯**：

```
L1 (12): case/s01 s02 | comma/s01 s02 | cte/s01 s02 | dml/s01 s05
         nested/s01 s02 | window/s01 s03
L2  (7): ddl/s01 s02 s03 s06 | dml/s02 s03 s04
L3  (1): ddl/s05
L4  (1): dml/s06      L5: case/s03      L6: generic/s01      L7: ddl/s04
A1  (6): aggregate/s01 s02 | debug/sqldebug_s01 | dml/s07 s08 | window/s02
```

U11 落地后 **L3 / L6 / L7 整条消失**，L1 少 4 个、L2 少 1 个、A1 少 5 个 —— 这些都是
「一段空白被拆成多个 token」造成的假差异，规则本身在 S1 就已（部分）生效。
**教训**：规则→用例的映射必须用**最小化输入**（把用例压成单空格/单换行）复核，
否则会把空白粒度问题的表现误记成「某条布局规则未实现」。

---

## 5. 分步实施

每个步骤的验收统一为两条：
- **净效果**：对拍套件中 `xfailed` 数量下降到该步骤的目标值；
- **不回归**：主套件保持 `170 passed, 6 xfailed`。

| 步骤 | 内容 | 目标 | 对拍 | 状态 |
|---|---|---|---|---|
| **S0** | 计划落地 + 骨架 + 对拍进度条 | — | 1 / 30 | ✅ 完成 |
| **S1** | 把布局引擎移植到官方 0.6.0 之上：方言 lexer、分词补丁、`LayoutPass`（断行+对齐规则集）、摘掉官方换行 filter | 骨架跑通且不崩 | **4 / 27** | ✅ 完成 |
| **S2** | 上游语义差异补偿 U5–U7（`Case.get_cases` 注释占位、`Where.M_CLOSE`、`get_real_name`） | 实测收敛为 1 项 | 4 / 27 | ✅ 完成：U5 落地；U6/U7 经检索确认无影响（见 §3.4）。`case/sqltest4_s02` 转正，`s03` 转 KNOWN_DIFF（等 L5 结构性规则） |
| **S3** | `LayoutPass` L1 注释强制换行（结构性规则：`--` 与 `/*-*/` 强制断行、连续注释各自成行） | +11 | **16 / 15** | ✅ 完成（U11 + S3c + U9 分组补偿，L1 已清零） |
| **S4** | `LayoutPass` L2 括号字段列表展开（真因 = 分组口径 U12） | +5 | 21 / 10 | ✅ 完成 |
| **S5a** | `policy` LATERAL VIEW 分词兜底（L4 多 `lateral view` 各自分行） | +1 | **22 / 9** | ✅ 完成 |
| **S5b** | U14 + `_create_guard` 边界 + 注释串按层级缩进（`cte/s02`） | +2 | **24 / 7** | ✅ 完成 |
| **S4c** | 官方 `group_functions` 的 CREATE+TABLE 早退严于 fork（`ddl/s01`） | +1 | — | ⏳ 可并入 S6 |
| **S6** | 列对齐收尾（真因多为**分组/分词**：U15 尾逗号、U16 缺 `DATETIME`、U13 CREATE 早退、S6b 相邻续接列表） | +7 | **31 / 0** | ✅ 完成（起点 7 个全部带回） |
| **S7** | 收敛 + 幂等 + 入口切换 + 删 fork + 改 README + 处置有意偏离清单 | 新实现通过全部 4 套测试 | **172 passed / 4 xfailed** | ✅ 完成（S7-a~e 五个独立提交，见 §9.4） |
| **S9** | 注释断行的结构性口径：跨注释组强制换行 + `ON COMMIT` 白名单结构化 | 收敛门禁 4 xfail → 1 | **175 passed / 1 xfailed** | ✅ 完成（见 §9.6） |
| **S10** | 「注释保持列 0」判据结构化：收窄到**语句前导注释**，语句尾注释按层级归一 | 收敛门禁 1 xfail → 0 | **176 passed / 0 xfailed** | ✅ 完成（见 §9.7） |
| **S10-b** | 收尾注释改「按所在层级对齐」；`;` 作为分段终止符**一律顶列 0**（前面不特殊处理） | 口径修订 | **176 passed / 0 xfailed** | ✅ 完成（见 §9.8） |
| **S8-a** | 方言层收成**单一真身**：`dialects` 登记表 + `lexer`/`LayoutPass`/`grouping` 都从它取；未知方言报错；建 `dialect` topic | 方言用例 | **185 passed** | ✅ 完成（见 §9.9） |
| **S8-b** | 方言词表归位（分词层词表也进 `dialects`）+ 补齐 20 个 Doris 类型名 | 方言用例 | **192 passed** | ✅ 完成（见 §9.10） |
| **S8-c** | SQL Server：`GO` 批分隔符、`[ ]` 标识符、`TOP`、`WITH(NOLOCK)` | 方言用例 | **215 passed** | ✅ 完成（见 §9.11） |
| **S8-d** | MySQL 方言：补齐 11 个类型名、表选项换行锚点、`ON DUPLICATE KEY UPDATE` 合并、`select straight_join` / `= values(col)` 的表达式内锚点 guard | 方言用例 | **234 passed** | ✅ 完成（见 §9.12） |
| **S11** | DDL 字段列序：约束列查找不得越过 `DEFAULT`（`default null` 的 `null` 是默认值，不是约束） | 通用 DDL 用例 | **239 passed** | ✅ 完成（见 §9.13） |

> **方言优先级（用户口径，2026-09-13）**：**Doris / SelectDB 最优先 → 其次 MySQL →
> Oracle / SQL Server 暂缓**。S8-c（SQL Server）已完成并保留，不回退、也不再往前推
> （`PLAN §9` 头部同口径）。**S8-a~d 至此全部收，方言路线走完。**

> 对拍列格式：`passed / xfailed`。
> **L1 的规则要从「依赖输入换行」改成「结构性判定」**：`/*-*/` 与 `--` 强制断行、
> 块注释 `/* */` 跟随原分组——这才是收敛性要求下的正确形态，也是旧实现做不到的。

**S3 明细（本轮已完成 / 未完成）**：

- ✅ 分组口径三条（`sqlfmt_ext/grouping.py`）：①裸 `interval 1 day` 预成组
  `TypedLiteral`（官方 `M_CLOSE` 只认 `T.String.Single`）；②注释打断逗号列表的
  归并；③官方 `align_comments` 的「并入前一个 TokenList」用
  `_unabsorb_trailing_comments` 撤销，并按 fork 口径用 `_absorb_leading_comments`
  并入**后**一个 `IdentifierList` 首位。`comma/sqltest7_s01` 因此转正。
- ✅ `OVER (` 判回 `Keyword`（U10），`sql.Over` 分组恢复（分词语序问题，不是布局问题）。
- ✅ **U11 卡点已解决**（本轮主要产出，+9 用例，见 §3.5）。原计划把空白归一化放在
  `LayoutPass.process` 入口；实际落地在更上游——`filters/whitespace.py` 在官方
  `_stripws()` **之前**合并空白段，顺带修掉了官方 `_stripws_identifierlist` 在逐字符
  空白下「只删掉逗号前 1 个空 token」导致的对齐偏 1。
- ⏭ 未系统化：`--` / `/*-*/` 的**结构性强制断行**规则尚未重写，现在是照搬 fork 的
  `_process_comment`（其内部仍隐含「一段空白 = 一个 token」的前提，U11 已让该前提成立，
  但「依赖输入换行」的部分——`prev_.is_newline` 分支——仍需改成结构性判定）。

### S6 收尾清单
1. `sqlfmt.py` 改为薄 shim：`from sqlfmt_ext import format_statements`，保留 `DEFAULT_OPTIONS` 与 CLI 参数不变。
2. `tests/sqlfmt_test_helpers.py` 改为调用 `sqlfmt_ext`。
3. 删除 `sqlparse/`（旧 fork）、`tests_migration/conftest.py`、`_tmp_*.py`。
4. `tests_migration/test_parity.py` 并入 `tests/`，去掉全部 `xfail`。
5. **更新 `AGENTS.md`**：架构图、关键文件表（`pytests/` → `tests/` 的路径错误一并修正）、测试命令。
6. **更新 `README.md`**。
7. `pyproject.toml` 保持 `sqlparse>=0.6,<0.7`。

### S7 方言路线（**旧编号**，内容归 S8）

> **2026-09-13 注**：本表已**过期**。S7a 由 **S8-a** 完成，且真实缺口与当初设想不同 ——
> 不是「往 `dialects.py` 补声明」，而是「方言层本身是死的」（死代码 + 两套真身 + 未知方言静默降级）。
> 落地见 `§9.9` / `§9.9.1`；S8-b / S8-c 仍未开工。

| 阶段 | 内容 |
|---|---|
| S7a | Doris/SelectDB：`DISTRIBUTED BY` / `DUPLICATE KEY` / `AGGREGATE KEY` / `UNIQUE KEY` / `PARTITION BY` / `PROPERTIES` 等声明式注册（已在 `dialects.py` 留位） |
| S7b | 官方缺失的关键字按 **MySQL 兼容**口径适配，仅「追加声明」，不改官方已有条目 |
| S7c | SQL Server：`GO` 批分隔符、`[ ]` 标识符、`TOP`、`WITH(NOLOCK)` 等 |

---

## 6. 测试策略

| 套件 | 文件 | 断言 | 门禁 |
|---|---|---|---|
| 输出回归 | `tests/test_sqlfmt_output_regression.py` | `format(input) == expected` | 必须全绿 |
| 幂等性 | `tests/test_sqlfmt_idempotency.py` | `format(format(x)) == format(x)`，且 input→input 也幂等 | 必须全绿 |
| 收敛性 | `tests/test_sqlfmt_convergence.py` | 把 canonical 的 token 间隔空白**确定性压平**后，输出仍等于 canonical | 已知 6 个不收敛用例先 `xfail(strict=True)` |
| 对拍进度条 | `tests_migration/test_parity.py` | 新实现输出 == fixture 期望 | 迁移期 `xfail(strict=True)` 清单（当前 17 个），S7 结束清零 |

**方法论约束**（踩过的坑，写进约定）：
- 比对「非空白 token 序列」是**无效指标**（格式化不重排 token，恒等）。
- 必须比「行内容（去缩进、去标点前空格）」才能分离换行位置差异。
- 本地逗号前有对齐空格（`a ,` vs `a,`），统计前必须归一化。
- `xfail(strict=True)` 是进度条机制：修好一个就 XPASS 失败，强制清理清单。

**用例扩充**：从现有用例中挑几条做**非破坏性空白打乱**，作为收敛性的强测试
（工具：`tests/sqlfmt_test_helpers.py::flatten_whitespace` / `scramble_whitespace`）。

---

## 7. 风险与回退

| 风险 | 影响 | 对策 |
|---|---|---|
| 官方骨架输出与旧 fork 差异过大，L 类规则膨胀 | S2–S4 工作量超预期 | S0 已把差异归因为 6 组规则；若某组规则膨胀，允许「极少美观差异待定」，并在 `KNOWN_DIFF` 中显式标注 |
| CJK 对齐宽度口径不一致（字节宽 vs 显示宽） | S5 对齐列宽偏差 | 先固化现有口径（旧实现用 gbk 字节长），S5 单独决策是否改为显示宽 |
| 双轨期 `sys.path` 手段脆弱 | 测试相互污染 | `tests_migration/conftest.py` 已校验 `sqlparse.__file__` 含 `site-packages`；S6 一次性拆除 |
| 迁移中途需要临时回到旧实现 | — | 迁移期旧 fork 完整保留，`sqlfmt.py` 未改动，随时可回退 |

---

## 8. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-12 | 初稿：确立方案 A（官方包作 pip 依赖）、四段管线、6 组规则拆分、S0–S7 步骤拆分 |
| 2026-09-12 | S1 落地后的修订：①官方 `AlignedIndentFilter` 不再进 stack，改由 `LayoutPass` 独占换行骨架；②对齐规则改为 mixin 组合而非独立后置 pass；③新增 §3.4 上游语义差异清单（U1–U9），步骤表按实际成本重排（新增 S2 语义补偿）。 |
| 2026-09-12 | §4「明确不移植」更正：`*_newline` / `_pull_inline` / `_remove_prev_newline` 等函数**保留**——在官方 strip 之下它们不再承担「擦除输入换行」的职责，而是管理本 pass 自己插入的空白，属于固有工具；真正被删掉的只有 `_flatten_up_to_token` 的调用语义变化与旧 fork 的 strip 魔改。 |
| 2026-09-12 | S2 完成：①U5 以 `LayoutPass._get_cases` 本地实现补偿（对拍验证：CASE 条目形状与 fork 逐项一致），②U6/U7 实测无影响、仅记录不动代码；③发现 L5「CASE 首个 WHEN 独占一行」在旧实现里依赖输入换行（`has_nl`），属**不收敛**行为，需在 S5 定结构性规则或 S7 重定基线，`case/sqltest4_s03` 暂列 `KNOWN_DIFF`。 |
| 2026-09-12 | S3 进行中：①分组补偿层扩到四条（裸 `interval` 字面量预成组、注释打断列表的归并、`align_comments` 前并/后并口径回正、`_refresh_values`）；②lexer 新增「优先级补丁」插入点，`OVER (` 判回 `Keyword`（U10）；③对拍 **4/27 → 5/26**（`comma/sqltest7_s01` 转正），主套件保持 `170 passed, 6 xfailed`；④定位列对齐 ±1 的根因 = 官方 lexer 逐字符空白 token（U11，见 §3.5），列为下一步第一优先；⑤新增 §9 断点续做章节。 |
| 2026-09-12 | **U11 落地，对拍 `5/26` → `14/17`**：①新增 `sqlfmt_ext/whitespace.py::merge_whitespace_runs`；②新增 `sqlfmt_ext/filters/whitespace.py::StripWhitespaceFilter`，在官方 `_stripws()` 之前合并空白段，并换装进 stack（`stack._swap_whitespace_filter`）；③`LayoutPass.process` 入口保留幂等兜底调用。修掉两类问题：`_set_adjacent_ws` 改写错 token（列宽 +1）与官方 `_stripws_identifierlist` 只删 1 个空 token（逗号前残留 1 空格）。8 个用例转正后**重新校准 §4 规则→用例映射**：L3/L6/L7 整条消失，L1 12→8、L2 7→6、A1 6→1。 |
| 2026-09-12 | 工具整理：`_tmp_cmp.py` 的两侧选项与主套件口径对齐（去掉多传的 `comma_align`、按 `;` 拆分后以空行拼接、支持 `@相对路径` 直接喂 fixture）；`_tmp_*.py` 加入 `.gitignore`（迁移期临时脚本，S7 统一删除）。 |
| 2026-09-12 | **S5a 落地，对拍 `21/10` → `22/9`**：`policy.MULTIWORD_REGEX` 在 `LATERAL VIEW <白名单 UDTF>` 之后补一条兜底 `(LATERAL\s+VIEW)\b` —— UDTF 不在白名单时（如 `EXPLODE_JSON_ARRAY_JSON`）`lateral`/`view` 会各自成词，`split_words` 的 `LATERAL\s+VIEW` 对两个单词 token 都匹配不上（`match` 是拿整条正则去 search 单个 token 的 normalized），多个 `lateral view` 全被挤在 `from` 行（且旧 fork 靠输入换行侥幸通过，属已知不收敛用例）。→ 转正 `dml/sqltest1_s06`。 |
| 2026-09-12 | **S6b 第一击：注释前导空白整段搬出组，对拍 `28/3` → `29/2`**。①`grouping._unabsorb_trailing_comments` 里「吃掉注释前导空白」原来是 **`if` 只吃一个 token** —— 分组阶段空白是**逐字符** token（U11 家族第 N 次），输入里 7 个空格只吃掉 1 个，剩 6 个留在**项内**，而 `_identifier_layout` 给无别名项算 offset 要用 `len(项的末行)`，于是 `max_as_offset` 被抬高 1、**整列连带 +1**（`window/sqltest6_s03` 的 `select a      ,` 变 7 格、`b as b1` 变 `b  as b1`）→ 改成 `while` 整段吃。②但①把注释搬回同层后，`passes/layout._process_comment` 的 M_OPEN 支原来靠 `_ends_with_comment(前一段以注释结尾)` 认「注释串延续」，此时后续成员是**同层并列的注释**，认不出来 → `cte/sqltest2_s02` 退回列 0；补一条「紧邻的前一个非空白兄弟本身就是注释」的判定。**两条必须一起改**。`window/sqltest6_s03` 转正。 |
| 2026-09-12 | **U13 落地（S6c）：CREATE+TABLE 早退补包，对拍 `27/4` → `28/3`**。官方 `group_functions` 开头「本层同时有 `CREATE`+`TABLE` 且无 `AS` → 整条 `return`」，fork 没有这个条件 → `duplicate key(id,name)` / `range(date_trunc(…))` / `hash(ID)` 在 fork 里是 `Function`，官方这边退化成裸 `Name`+`Parenthesis`，被字段列表分支按 `(a,b,c)` 展开。新增 `grouping._wrap_create_table_calls`（+`_wrap_bare_calls`/`_call_head`）：**在官方分组之后**把本层「`Name`/`Identifier[Name]`/非子句 `Keyword` + 紧随 `Parenthesis`」包成 `sql.Function`（放之后而不是之前：之前括号还没成组，得先替官方跑 `group_parenthesis`，会打乱官方各步骤的先后假设）。`ddl/sqltest0_s01` 转正。 |
| 2026-09-12 | **U16：官方词表缺 `DATETIME`（分词差异），对拍 `26/5` → `27/4`**。官方 `Name.Builtin` 段与旧 fork **逐条相同**，缺的只是 `DATETIME` —— fork 的关键字正则不要求词尾边界，`DATE`（`Name.Builtin`）会把 `DATETIME` 一起前缀命中；官方是整词匹配，于是 `datetime` 落成普通 `Name`，被 `group_identifier` 与字段名粘成一个 `Identifier` → `_create_field_lines` 的类型列取不到 token → **整条 DDL 字段对齐的列基准全错**。修法：`policy.KEYWORDS_TYPES = {"DATETIME": T.Name.Builtin}` + `DialectLexer.default_initialization` 里 `add_keywords`（与 `KEYWORDS_DORIS` 同渠道）。`ddl/sqltest0_s02` 转正；`ddl/sqltest0_s01` 的**对齐**部分也随之修好，残差只剩 U13。**定位手法**：`_tmp_ddlprobe.py --fork/--new` 打两侧 `field_lines` / 每列 `max_offset` / 每个 token 的 offset，一眼看出 fork 的 `['id2','datetime',…]` 对我们变成了 `['id2 datetime', None, …]`。 |
| 2026-09-12 | **S6 起点即回本：U15 分组差异，对拍 `24/7` → `26/5`**。官方 `group_identifier_list` 的 `valid_next` 认 `T.Keyword`，于是**尾逗号**后面的子句关键字（`from`）被当成下一个列表项**吞进列表**：`select (1) as wc, F_USER_CODE as POSTUSERCODE , from …` 的列表变成 `…, POSTUSERCODE , from`，列对齐于是按「`from` + 表名」算基准 → 末项少一格、`from` 行被补出一大段空白。新增 `grouping._trim_clause_tail`（**必须在 `_walk` 之后**，否则 `_group_level` 会把它重新吞回；只处理「尾逗号 + 子句关键字」形状，关键字前必须是逗号，连同逗号与空白退回父层）。`nested/sqltest3_s02`、`window/sqltest6_s01` 转正。**再次印证元规则：列对齐错乱先怀疑分组。** |
| 2026-09-12 | **S5 清零：`cte/sqltest2_s02` 转正，对拍 `23/8` → `24/7`**。该用例一共三层根因：①U14（`OVER` 隔着注释时官方不并进 `Function`）→ `grouping._attach_over_to_functions`；②`_create_guard` 只拿 `SELECT` 当边界，把 `WITH` 之后本该正常建列表的 CTE 体括号一起跳掉 → 改成「`with`/`select`/`values` 中最先者」；③**注释串缩进口径（用户定）**：「原本在列 0 的保持不变，其它的随所在层级对齐」→ `_break_between_comments` 用 `self.nl(0).value`（= 换行 + 本层缩进）代替只剩换行，`_process_comment` 的括号支在前一段「以注释结尾」时改取那段内容的偏移。踩坑：`sql.Comment` 也是 `TokenList`，判「以注释结尾」必须先判自身；第 ③ 条必须收窄否则踩 `comma/sqltest7_s01`。 |
| 2026-09-12 | **S5b 收口（U14 + `_create_guard` 边界）**：`cte/sqltest2_s02` 从 18/18 行差异降到 **1/22 行**（且全部为空白宽度）。第二个根因是 `_create_guard` 只拿 `SELECT` 当边界，把 `WITH` 之后本该正常建列表的 CTE 体括号一起跳掉了；改成 fork 原文口径「with/select/values 中最先出现的那个」（`WITH` 是 `T.Keyword.CTE`，要用 `ttype in T.Keyword` 判）。残差 1 行 = 注释串缩进，取证表明旧 fork 那处是**输入换行+空格驱动**（单行输入下它压根不拆注释串），需口径决策，见 §9.3「S5b」。两套件无回归：`23/8`、`170/6`。 |
| 2026-09-12 | **S5b 分组侧落地（U14）**：新增 `grouping._attach_over_to_functions` —— 官方 `group_functions` 用「下标相邻」判定是否把 `OVER` 并进 `Function`，`)` 与 `over` 之间夹注释时判定失败；补偿把它搬回 `Function` 并还原 fork 的列表项形状（显式 `as rn` 与隐式 `over(…) rn` 两种写法都覆盖）。孤立复现已与期望**逐字节相同**；整条 `cte/sqltest2_s02` 的残差是 **CTE / `create view` 上下文**里同一个列表不展开，属另一根因（入口已写在 §9.3）。两套件无回归：`23/8`、`170/6`。 |
| 2026-09-12 | **S5c 定性（用户拍板「按 (i) 做」）**：`case` 与首个 `when` 取**同行**口径，`case/sqltest4_s03` 登记为**有意偏离**（`test_parity.DEVIATIONS`：理由 + 对 canonical 的定向变换，**断言**而非 xfail，另加「变换失效即报错」守卫），对拍 `22/9` → **`23/8` + 1 条有意偏离**。**没有改任何 fixture、没动主套件**（s03 的 canonical 同时钉住旧 fork 的输出回归测试，改了主套件立刻红）。§4 新增「对旧 fork 的有意偏离清单」，S7 交付时按此清单向用户交代。 |
| 2026-09-12 | 按 `improve-agent` 的「历史失败模式 → 指令修订」思路修正 `AGENTS.md`：①修掉事实错误（用例目录 `pytests/` → 实际的 `tests/`，并补上两套件的跑法与门槛）；②补「架构」为迁移期四段流水线（`DialectLexer`→官方分组+补偿→`StripWhitespaceFilter`→`LayoutPass`），旧 fork 标注为仅作 oracle；③新增「硬约束 C1–C5」与两条元规则（**列对齐错乱先怀疑分组**；**结论必须写成最小重现**）；④补诊断工具清单与三个坑（`FilterStack.run` 返回生成器、两实现须分进程、不能比非空白 token 序列）。 |
| 2026-09-12 | **S4 落地，对拍 `16/15` → `21/10`**（+5：`dml/s01 s02 s04`、`ddl/s03 s06`）：①`grouping.py` 新增 `_pre_wrap_object_name`，官方分组前把 DDL/INSERT 的对象名链预包成 `Identifier`（U12）；②`_SQLCLS` 补 `sql.Parenthesis`，修 `values (…), (…)` 多行值列表不成组；③新增 `_create_guard` + `_flatten_identifier_lists`，复刻 fork 的 CREATE/ALTER「SELECT 前不建列表」守卫并把官方多建的列表摊平；④`_process_parenthesis` 字段列表分支对「首个子列表以注释开头」不再插换行/删空白（注释与 `(` 同行）。主套件保持 `170 passed, 6 xfailed`。`ddl/s01` 残留归 S4c（官方 `group_functions` 的 CREATE+TABLE 早退严于 fork）。 |

---

## 9. 断点续做（下一次会话从这里开始）

> 落盘时间：2026-09-13（S11 收工刷新），**S1–S7、S9、S10、S10-b、S8-a~d、S11 全部完成**
> （S7-a~e 五个提交见 §9.4 末尾，S9 见 §9.6，S10 见 §9.7，S10-b 见 §9.8，S8-a 见 §9.9，
> S8-b 见 §9.10，S8-c 见 §9.11，S8-d 见 §9.12，S11 见 §9.13），**门槛 `pytest -q` → `239 passed`（0 failed / 0 xfailed）**，
> 收敛门禁 `KNOWN_DIVERGENT` **已清空**，无遗留偏离清单。
>
> **本节是「阶段断点卡」**：每阶段的开工点与残留都记在这里。配合
> [AGENTS.md](AGENTS.md) 的「**阶段推进协议**」（开工四步 / 收工六步 / 汇报格式）使用。
>
> **方言优先级（用户口径，2026-09-13 定）**：**Doris / SelectDB 最优先 → 其次 MySQL →
> Oracle / SQL Server 暂缓不做**。**S8-a~d 至此全部收**：Doris/SelectDB 与 MySQL 已适配；
> SQL Server（S8-c）已完成并保留（不回退、也不再往前推）；Oracle 未开工。
>
> **下一步开工点**：方言路线已走完，S11 已收，剩下的都是**共享缺口**（同时影响 Doris/MySQL），
> 各自需先开新阶段卡再动手：
> 1. `LIMIT m, n` 被逗号折行、ALTER 多子句不换行；
> 2. 官方判成 `Keyword` 的类型名（Doris 的 `json`/`map`；MySQL 的 `double`/`enum`/`set`/
>    `time`/`year`）—— 覆盖 = 改写官方条目，与 `dialects` 原则冲突，需专门设计再定；
> 3. S11 的已知边界：`DEFAULT` **之后**写的列级约束词（`id int default 0 primary key`）
>    不再进约束列（判据是「约束列查找止于 `DEFAULT`」，见 §9.13）。

### 9.1 复现当前状态

```powershell
.venv\Scripts\python.exe -m pytest -q                   # 门槛：239 passed（0 failed / 0 xfailed）
.venv\Scripts\python.exe -m pytest -q -k convergence    # 只看收敛门禁（此刻全绿，无 xfail）
```

只有一套测试（S7 删 fork 后 `tests_migration/` 已并入 `tests/`）。

**残留：无。** 收敛门禁的 `KNOWN_DIVERGENT` 已在 S10 清空 —— 上一版留的 `cte/sqltest2_s01`
正是本轮「列 0 口径」决策的直接产物，判据结构化后两条输入路径归一到同一份输出（见 §9.7）；
其最终的落列（注释按层级、`;` 顶列 0）由 **S10-b** 定稿（见 §9.8）。

### 9.2 空白归一化（U11）最终形态

| 文件 | 改动 |
|---|---|
| `sqlfmt_ext/whitespace.py` | **新增**：`merge_whitespace_runs(tlist)` —— 递归合并每层连续的空白 token，value 拼接、ttype 沿用段首 |
| `sqlfmt_ext/filters/whitespace.py` | **新增**：`StripWhitespaceFilter` = 官方 `StripWhitespaceFilter` 子类，覆写 `process` 在 `self._stripws(stmt)` **之前**调用合并；其余逻辑与官方逐行一致 |
| `sqlfmt_ext/stack.py` | 新增 `_swap_whitespace_filter`，在 `_replace_skeleton_filters` 之前换装 |
| `sqlfmt_ext/passes/layout.py` | `LayoutPass.process` 入口加 `merge_whitespace_runs(stmt)` 兜底（幂等） |
| `tests_migration/test_parity.py` | 8 个用例从 `KNOWN_DIFF` 删除 |

**为什么必须放在 strip 之前**（关键，别再挪回 `LayoutPass`）：官方
`_stripws_identifierlist` 只删掉逗号前的**最后一个**空白 token；逐字符空白下它在
`' '*82` 里只删掉 1 个，剩下的 1 个空格留在逗号前，与 `AlignMixin` 填好的对齐
空白叠加 → 非 AS 字段的末尾逗号整体多 1 列。

### 9.3 分段任务卡（迁移期记录 · 已过期，只作历史）

> **本节是 S4–S7 迁移期的原始记录**：当时的「两套测试」「对拍 passed/xfailed」
> 「`KNOWN_DIFF` / `DEVIATIONS`」都随旧 fork 一起在 S7 删掉了，现在只有
> `tests/` 一套件、只有收敛门禁里的 `KNOWN_DIVERGENT`。读它是为了看**根因与教训**，
> 里面的命令与门槛数字**不要再执行/比对**。
>
> 分段原则（仍然适用）：**一段 = 一条规则 / 一个根因**，上下文只读该段需要的文件；
> 需要跨文件探索的先用 `code-explorer` 子代理，把结论（不是文件内容）带回主线。

| 段 | 目标 | 涉及用例（当前 9 xfailed） | 主读文件 | 状态 |
|---|---|---|---|---|
| S4 | L2 括号字段列表展开（真因 = 分组口径） | `dml/s01 s02 s04`、`ddl/s03 s06` | `grouping.py` + `passes/layout.py::_process_parenthesis` | ✅ 完成（16 → 21） |
| S5a | L4 多 `lateral view` 各自分行 | `dml/s06` | `policy.MULTIWORD_REGEX` | ✅ 完成（21 → 22） |
| S5b | U14 + `_create_guard` 边界 + 注释串按层级缩进 | `cte/s02` | `grouping.py` + `passes/layout.py`（`_break_between_comments` / `_process_comment`） | ✅ 完成（22 → 24） |
| S4c | 官方 `group_functions` 的 CREATE+TABLE 早退严于 fork | `ddl/s01` | `grouping.py` + `passes/layout.py::_process_parenthesis` | ⏳ 可与 S6 合并 |
| S5c | `case` 与首个 `when` 同行（口径重定 + 有意偏离登记） | `case/s03` | `tests_migration/test_parity.py::DEVIATIONS` | ✅ 完成（22 → 23） |
| S6a | U16：官方词表缺 `DATETIME`（分词）→ DDL 字段列基准全错 | `ddl/s01 s02` | `policy.KEYWORDS_TYPES` + `lexer.py` | ✅ 完成（26 → 27；`ddl/s01` 残差转为 U13） |
| S6b | 列表末尾列口径（末项逗号列 ±2 / 整体 +1） | `case/s01`、`nested/s01`、`window/s03` | `align.py::_identifier_layouts` / `_apply_identifier_layout` | ⏳ 下一段 |
| S6c | U13：官方 `group_functions` 的 CREATE+TABLE 早退 | `ddl/s01` | `grouping.py::_wrap_create_table_calls` | ✅ 完成（27 → 28） |
| S6 | （起点 7 个）U15 尾逗号吞子句关键字 | `nested/s02`、`window/s01` | `grouping.py::_trim_clause_tail` | ✅ 完成（24 → 26） |
| S7 | 收敛 + 幂等 + 入口切换 + 删 fork + 改 AGENTS/README + 删 `_tmp_*` | — | — | ✅ 完成（终值 172/4） |

**分段推进的操作要点（省上下文的做法）**
1. **先分类再动手**：`python _tmp_check.py` 只看摘要（每例首 2 处差异 + 「是否只是空白宽度」），
   一条命令拿到全部 10 个用例的格局，再决定这段做哪一类。
2. **一次只读该段需要的文件**：S4 只读 `layout.py` 的 `_process_parenthesis` /
   `_process_identifierlist` + `grouping.py`；跨文件搞清楚「官方某步是不是在别处发生」时，
   用 `code-explorer` 子代理，只把结论带回主线。
3. **最小重现优先**：`_tmp_cmp.py --fork/--new "<最小片段>"`，两侧并排看一眼就能定性；
   能用 1 行 SQL 复现就不要拿 40 行 fixture 试。
4. **对齐类问题先怀疑分组**（U9 的教训），分组对了再查 `align.py`。

**S3c 已收（2026-09-12）**：Comment 组内相邻注释强制各自成行（结构性，不依赖输入换行），
`comma/sqltest7_s02` 转正。踩坑：`sql.Comment` 是**分组类**，裸注释 token 属于
`T.Comment` 的**token 类型**，判定要用 `isinstance(tk, sql.Comment) or tk.ttype in T.Comment`。

**U9 已收（2026-09-12）**：官方 `group_as.valid_prev` 拒绝关键字作 AS 左值，旧 fork 放宽成
`True`。补偿 = 在官方分组**之前**把那个关键字本身包成 `Identifier`（其余全交给官方）：
`group_identifier` 先于 `group_as` 把右值裸 `Name` 包成 `Identifier`，于是官方树天然是
`Identifier[level, ws, as, ws, Identifier[depth]]`，与 fork 完全同形。`debug/sqldebug_s01` 转正。
**必须排除 `END`**：它是 `sql.Case.M_CLOSE`，`group_case` 早于 `group_as` 且
`token_next_by` 不递归，提前包住 `END` 会让 CASE 分组整个散架（`case/sqltest4_s02` 曾因此回归）。

**S4 已收（2026-09-12）→ 对拍 `16/15` 变 `21/10`**。根因与最小重现（`insert into
db.tb (user_id, name, age) values (1, 'a', 2);`）：官方树是
`Identifier[db, '.', Function[tb ( IdentifierList[user_id, name, age] )]]` ——
`group_functions` 把「`T.Name` 紧跟 `Parenthesis`」无条件当函数；又因
`group_identifier` 是 `@recurse(sql.Identifier)`（**不递归进 `Identifier` 子组**），
括号里的裸 `T.Name` 再也包不成 `Identifier`，`_process_parenthesis` 于是早退、字段列表不展开。

四处改动：

1. **`grouping.py::_pre_wrap_object_name`（官方分组前）**：锚定 `INTO` / `TABLE` / `VIEW`
   之后的「对象名链」（`T.Name` / `T.String.Symbol` / `.` / `AS Name`，可跳过官方词条化的
   `IF NOT EXISTS`），**只有链尾紧跟 `(`** 时才包成 `sql.Identifier`。官方
   `group_functions` 只看本层裸 `T.Name`、不递归，链一包住它就看不见了；括号因此升到
   语句层，被 `group_identifier` 正常收住。`insert into t (a) select f(x)` 这类无 `(` 的形状
   不受影响。→ 转正 `dml/s01 s02 s04`。
2. **`grouping.py::_SQLCLS` 补 `sql.Parenthesis`**：官方 `group_identifier_list` 的 `sqlcls`
   不含它，`values (…), (…)` 这种「括号作列表项」的多行值列表在官方分组下永远成不了
   `IdentifierList`（`LayoutPass._process_values` 依赖它已成形）。→ 转正 `dml/s04`。
3. **`grouping.py::_create_guard` + `_flatten_identifier_lists`**：复刻 fork
   `group_identifier_list` 开头的 CREATE/ALTER 守卫 —— `CREATE`/`ALTER` 且**无** `SELECT`
   时整条不建列表；有 `SELECT` 时 `SELECT` **之前**的子组不建列表（源码注释：「不需要处理：
   create/alter/insert 后，且在 with/select/values 前的 1-2 个括号」）。官方会建，所以这里把
   多出来的那层列表**摊平**回父层（不改变 token 相对顺序），让
   `_process_parenthesis` 的字段列表分支与 `_align_create_columns` 看到 fork 的扁平结构。
   → 转正 `ddl/s03 s06`；`cte/s02` 的对齐偏移也更接近期望。
4. **`passes/layout.py::_process_parenthesis`（字段列表分支）**：首个子列表以注释开头
   （`_absorb_leading_comments` 把注释放进列表首位）时，**既不插换行、也不做
   `_remove_prev_newline`** —— 注释与 `(` 同行才是 fork 口径，首个换行交给
   `_process_identifierlist` 插到注释之后。

**S4c（`ddl/sqltest0_s01` 残留，未做）**：官方 `group_functions` 开头是
`has_create and has_table and not has_as → return`，**fork 没有这个条件**（fork 的早退是
`has_insert and has_values`，另有「跳过表名与列名括号」「`has_table` 认 `TABLE`/`VIEW`」）。
于是 CREATE 语句里的 `duplicate key(id,name)`、`range(date_trunc(p_dt,'month'))`、`hash(ID)`
在 fork 里是 `Function`（`_process_function` 保持单行），在本实现里是「`Identifier`/`Name`
+ 裸 `Parenthesis`」，被 `_process_parenthesis` 的字段列表分支（`in_root and in_xdl_list`）
误展开。可行方向二选一：①官方分组**前**先调用官方 `group_parenthesis` 预建括号，再按 fork
口径只对 CREATE 语句把 `Name/Keyword + Parenthesis` 预包成 `sql.Function`；②把
`_process_parenthesis` 的展开条件收紧到「对象名链**紧跟的第一个**括号」。**先做 S5**，
本项可与 S6 合并。

**S5a 已收（2026-09-12）→ 对拍 `21/10` 变 `22/9`**：`policy.MULTIWORD_REGEX` 里
`LATERAL VIEW <白名单 UDTF>` 之后补一条兜底 `(LATERAL\s+VIEW)\b`。UDTF 不在白名单时
（fixture 用的是 `EXPLODE_JSON_ARRAY_JSON` / `explode_json_object`）`lateral` / `view`
会各自成词，而 `split_words` 的 `LATERAL\s+VIEW` 是拿**整条正则**去 `search` 单个 token
的 `normalized`（`Token.match` 的语义），两个单词 token 谁都匹配不上 → 多个 `lateral view`
全被挤在 `from` 行。旧 fork 之所以「对」，是因为它靠**输入换行**保留（该用例在
`_tmp_measure.py` 的确定性压平下不收敛）。→ 转正 `dml/sqltest1_s06`。

**S5b 进行中（2026-09-12）：分组侧已补偿，残差另有根因。**

根因（U14）：官方 `group_functions` 判定要不要把 `OVER` 并进 `Function` 用的是**下标相邻**
（形如 `over_idx - 1 == tidx + 1`）。容得下 `)` 与 `over` 之间的**空白**（无注释时本实现
与 fork 完全同形：`Function[Identifier[row_number], Parenthesis, ws, Over]`），
但**容不下中间的 `Comment`**（多占一个下标）→ `OVER` 被留在 `Function` 外面，
而它前面那个注释随即把外面的 `IdentifierList` 打断（列表不再按项展开）。

**已落地**：`sqlfmt_ext/grouping.py::_attach_over_to_functions`（官方分组**后**、
`_walk`/注释还原**之后**调用；放在 `_walk` 之前会被 `_group_level` 重新归并掉）。
它做一次靶向搬移，还原 fork 的形状：`Function` 吸收「ws + 注释 + Over」，
再把「Function + ws + 别名」重新包成同一个列表项（别名两种写法都覆盖：
显式 `as rn` 与隐式 `over(...)    rn`；后者还要把别名的 ws 一起搬走，
并把被误建的 `IdentifierList[rn, ',', from]` 摘掉别名后摊平回本层）。
踩过的坑：`_is_alias` 必须先判 `isinstance(token, sql.Identifier)` 再看 `ttype`
—— 分组的 `ttype` 是 `None`，先判 `ttype is None` 会把已包成 `Identifier` 的别名漏掉。

**验证**：把该 fixture 的那条 select 单独拿出来跑

    _tmp_cmp.py --new "select EMPLID as EmpCode, ROW_NUMBER() --\nover(partition by EMPLID order by BGN_DTTM desc, /*-*/\n(ifnull(a,0)) asc)    rn       ,\nfrom ODS.PS_HPS_PERS2MDM_VW_001 t1"

输出与期望第 4–8 行**逐字节相同**；两种别名形态的树也与 `_tmp_forkidx.py` 完全同形。

**第二个根因（同段内一并修掉）：`_create_guard` 的边界取错。**
整条 fixture 仍差，但把同一条 select 单独跑是对的 → 说明与 U14 无关，是**语句类型 `CREATE`**
引起的差异。二分结论：`create view x as (select …)` **在 fork 里也不展开**（我们复刻正确），
`with w as (select …)` 就正常 → 真凶是 `grouping._create_guard` 只把 **`SELECT`** 当边界：
`create view … as -- with c as (select …) … select * from c` 里 CTE 体括号（在 `with` 之后、
fork 明确会正常建列表）被一起跳掉、内层列表被摊平。fork 的原文口径是
「create/alter/insert 后，且在 **with/select/values** 前的 1-2 个括号」，所以边界应该是
**三者中最先出现的那个**。注意 `WITH` 的 ttype 是 `T.Keyword.CTE`，`Token.match(T.Keyword, …)`
匹配不上，必须用 `ttype in T.Keyword`。

**验证**：修完守卫边界后，`cte/sqltest2_s02` 从「18/18 行差异」降到
**「1/22 行差异，且全部是空白宽度」**；关掉守卫做对照会破 2 个 DDL 用例，说明守卫本身必须留。

**第三个根因（用户定的口径）：注释串里「原本不在列 0」的那些要按所在层级缩进。**
修完前两个根因后只剩 1 行：期望 `       --and t1.Rowkey=1`（缩进 7），本实现是列 0。

用户口径（2026-09-12 原话）：「这里不是都顶列 0 的，是原本是列 0 的，保持不变，
其它的随所在层级对齐。」落地点在 `passes/layout.py`：
（**2026-09-13 修订**：这句里的「原本是列 0」不再由输入空白判定，已收窄为结构性条件
「**语句前导注释**」；子句内的收尾注释按所在层级缩进，而分段终止符 `;` 一律顶列 0 ——
见 §9.7 / §9.8。）

1. `_break_between_comments` 里「两条注释之间有空白」那一支原来把空白写成 `self.n`
   （只剩换行 → 列 0），改成 `self.nl(0).value` —— `nl(0)` 的语义**本就是**「换行 + 本层缩进」
   （`self.n + self.char * self.leading_ws`）；原本贴行首的（前一条注释自带 `\n`）走 `elif`
   分支保持列 0 不动 ✓ 正是口径里的「原本是列 0 的保持不变」。
2. `_process_comment` 的 `hasattr(plist, "M_OPEN")` 支：以前一律取**括号内容的起始列**。
   当注释组**前面还有内容**、且那段内容**以注释结尾**（`_ends_with_comment`）时，
   改取那段内容的偏移 —— 该注释是上一条注释串的延续，应与它同层级。
   例：CTE 体括号里的 `--c`，父是括号（内容起始列 0），但它该对齐到 `where 1 = 1` 内容的 7。

**坑（两个，都踩过）**：
- `sql.Comment` 自己也是 `TokenList`，`_ends_with_comment` 若先往下钻会落到
  `Token.Comment.Single` 上判成 False —— 必须先判「本身就是注释」。
- 第 2 条必须收窄到「前一段以注释结尾」：放宽会踩 `comma/sqltest7_s01`（那里前一段是逗号、
  注释是行尾注释，误用该偏移会把 `)` 行推歪，`24 spaces → 37 spaces`）。

**结果**：`cte/sqltest2_s02` 与期望**逐字节一致**，对拍 `23/8` → **`24/7`**。

**S5c 已收（2026-09-12，用户拍板口径）→ 对拍 `22/9` 变 `23/8` + 1 条有意偏离**：
`case` 与首个 `when` **同行**（`case when b in ('X','Y') then …`），把 `case/sqltest4_s03` 登记为
**有意偏离**而不是改 fixture —— 详见 §4「对旧 fork 的有意偏离清单」。

决策依据（当时摆给用户的三条证据，别再重推）：
1. 旧基线那处折行**依赖输入换行**（该用例 `input.sql` 就是 `case` 换行 + `when` 顶格），
   属 C4 禁止依赖的行为，算不上可移植基线；
2. 「同行」是主导口径且**当前全通过**：`sqltest4_s01`（**无 input 文件**，`case` 后仅在有注释时
   换行）、`sqltest4_s02`、`dml/sqltest1_s06`；只有 s03 一例是折行形；
3. 差异**仅此一处折行**：`when b = 'NUMBER'    then …` / `else … c` / `end as type_name`
   的列对齐逐字节相同（`_tmp_check.py -v` 的 6/6 行差异全是这一处引起的整体平移）。

实施落点：`tests_migration/test_parity.py` 新增 `DEVIATIONS` 表（理由 + 对 canonical 的定向变换
`re.sub(r"case\n\s*when", "case when", exp, count=1)`），**断言**而非 xfail；并加
`assert transformed != expected` 守卫，S7 正式重定基线后这条会主动报错提醒删除。
**主套件与任何 fixture 都没动**（改了会破 fork 的输出回归测试）。

**S6 剩余 3 个（交接信息，对拍 `28/3`）**：**只剩 S6b 一族**，三者同一入口。

> **S6b 已定位到机制层（2026-09-12 第十轮，只诊断未改代码）**：
> 症状「整体 +1 格」的真因是**列表项的组里带着尾随空白**，而
> `_identifier_layout` 给无别名项算 offset 的公式是
> `as_offset = _get_offset(token) + 1 + len(str(token).splitlines()[-1].encode("gbk"))`
> —— **它把项内尾随空白也算进宽度**。
> 以 `window/sqltest6_s03` 为例（`select a, b /*-*/, /*-*/ b as b1, c, * from tab t where …`）：
> - 我们：项 `b` 的 `str()` 是 `'b '`（strip 后项内还剩 1 个空格）→ `as_offset = 7+1+2 = 10`
>   → `max_as_offset = 10` → **所有项**的 alias 填充 +1（`a` 6→7 格、`b` 6→7 格），
>   且 `b as b1` 的 `as` 前多一格（`b  as b1`）；
> - fork：同一项测到的是 `'b'` → `as_offset = 9` → `max_as_offset = 9` → 全部正确。
>
> **验证手法**（都要用真实 fixture，孤立复现不触发）：
> `python _tmp_align_probe.py "@tests/fixtures/cases/window/sqltest6_s03.sql"` 看
> `as_offset=10 text='b '`（我们）—— 注意**孤立片段跑同一个列表是对的**（`as_offset=9 text='b'`），
> 所以别用「抽出来跑」当结论。
>
> **待查（下一步从这里开始）**：是谁把空白留在了**项内部**而 fork 没有。两个重点嫌疑：
> 1. `grouping._unabsorb_trailing_comments` 的收尾判定要求「组尾**最后一个 token 是注释**」
>    （`while isinstance(tlist.tokens[start-1], sql.Comment)`）—— 若组尾是
>    `[.., 注释, 空白]`（注释后面还拖一个空白），这段循环不会触发，注释与空白就都留在项里；
> 2. `LayoutPass._process_comment` 的「紧贴前边的增加一个空格」（`plist.insert_before(pidx, ' ')`）
>    —— 此时 `plist` 可能就是该项本身，空白被塞进项内，而注释随后又被搬走。
> 建议先给 `_unabsorb_trailing_comments` 加「尾部空白先跳过再找注释尾巴」的判定试一次，
> 跑 `_tmp_align_probe.py @该用例` 看 `text=` 是否变回 `'b'`，再跑两套件。
>
> **第十一轮补录（实验结论，已回滚）**：真凶确认是 `_unabsorb_trailing_comments` 里
> 「吃掉注释前导空白」的 **`if` 只吃一个 token** —— 分组阶段空白还是**逐字符** token（U11），
> 输入里那 7 个空格只会被吃掉 1 个，剩下 6 个留在项里。把它改成 `while`（整段吃）后：
> `window/sqltest6_s03` **立刻 XPASS**（项 `b` 测回 `'b'`、`max_as_offset` 回到 9），
> 但 **`cte/sqltest2_s02` 变红**（它需要那段空白留在组里）。所以只差一个**形状判据**。
> 下次开工第一步：`python _tmp_align_probe.py --fork/--new "@tests/fixtures/cases/cte/sqltest2_s02.sql"`
> 对比两侧组尾形状（探针的 `--fork` 模式已在本轮补上），定好「什么时候整段吃、什么时候只吃一个」再改。
>
> **第十一轮结论（已落地，见 §8 变更记录）**：判据不用再定 —— 直接**整段吃**（`while`）即可，
> 但必须**同时**改 `passes/layout._process_comment` 的 M_OPEN 支：补一条
> 「紧邻的前一个非空白兄弟本身就是注释」也算法注释串延续（整段搬出后，注释串的后续成员是
> **同层并列**的注释，原来的 `_ends_with_comment(前一段以注释结尾)` 认不出来）。
> **两条是一对，拆开会各红一个**（只改前者 → `cte/sqltest2_s02` 退回列 0；只改后者 → 无效）。
> `window/sqltest6_s03` 已转正 → 对拍 `29/2`。
>
> **S6b 剩余 2 个（交接）**：**两个都已转正，S6 收尾完成**（对拍 **31/0**）。
>
> **第十五轮：`nested/sqltest3_s01` 转正（30/1 → 31/0）**。形态实测（新探针
> `_tmp_shape.py`：只打**语句层**兄弟序列、把空白折叠成 `ws(n)`）：list A 以
> `Function[ROW_NUMBER()]` 收尾，`/*-*/ + over(…) as rn` **及其后 4 个长项自成 list B**
> （`str(list B)` 以 `/*-*/\n` 开头）→ 两张表各自算 `max_as_offset`（我们 20 / fork 101）。
> 两处修（缺一不可）：
> ①合并条件补 `_is_comment(first) or first.ttype in T.Comment` —— 注释在这里是
> **`sql.Comment` 组**（`ttype` 为 `None`），只判 `ttype` 会漏。**这正是上一轮「注释开头」
> 实验失败的真正原因：不是形态假设错，是判据写错了**；
> ②`group()` 里 **`_attach_over_to_functions` 要在 `_normalize_adjacent_lists` 之后再跑一次**
> —— 合并把「`Function` + 注释 + `Over`」重新凑回同一层之后，补包才认得出（fork 的
> `ROW_NUMBER() /*-*/\n over(…) as rn` 是**一项**，我们原本是 `ROW_NUMBER()` 与
> `over(…) as rn` **两项**）。修后 `max_as_offset=101 max_alias_len=14` 与 fork 逐值一致，
> 差异行 9/39 → 2/39 → **0**。
>
> **第十四轮（本轮）**：`case/sqltest4_s01` **已转正** —— 新增
> `grouping._extend_adjacent_lists` + `_normalize_adjacent_lists`（探针实测最后一处断点：
> `t.*` 待在**另一张以逗号开头的畸形表** `'      ,\n       t.*'` 里，而官方 `_group` 的
> 「快照下标 − 累计偏移」在多次合并后漂移、末尾逗号轮不到）。修法 = 按**活下标**重扫，
> 把「紧邻同类组 + 尾逗号 + 真实项」并进去（等价官方 `extend=True`），并在
> **`_attach_over_to_functions` 之后再跑一遍**（U14 补包合回去之前，两张表还不相邻）。
> 探针口径：`as_offset=11 alias_len=4 as=N text='t.*'` 与 fork 完全一致 ✓。
> 试过但**无效且已回退**：把合并条件放宽到「第二张表以注释 / `Over` 开头」——对
> `nested/sqltest3_s01` 无效果（说明它的形态又不是这两种）。
>
> **`nested/sqltest3_s01` 现状（下一个开工点）**：主 select 列表被切成**两张表** ——
> 我们 `max_as_offset=20 max_alias_len=8`（4 项，最后一项只有 `ROW_NUMBER()`、无别名；
> 它才是 `as_offset=20` 的来源），而 fork 是 `max_as_offset=101 max_alias_len=14`（8 项，
> 最后一项是 `ROW_NUMBER() /*-*/\n over(…) as rn` 合体，另外还有 `[location]…`/`H2_…`/
> `H3_…`/`lead(…)` 四长项）。**也就是：`/*-*/ + over(…) as rn` 及其后 4 项在我们这边
> 自成第二张表** → 每张表各自算 `max_as_offset`，列宽自然差一大截。
> 下一步：给 `_extend_adjacent_lists` 加临时打印，**在 `_normalize_adjacent_lists` 收尾后**
> dump 语句层真实的兄弟序列（A / 中间是什么 / B），按实际形态定条件（别再用猜测的
> 「注释/Over 开头」）。
> - `case/sqltest4_s01`：末项 `rn       ,` 我们**多 2 格**，且 `t.*` **没被断到下一行**
>   （我们 `… asc)    rn         , t.*`，期望 `rn       ,` + 换行 + `       t.*`）。
>   **已定位到分组层（第十二轮）**：两侧探针对照显示 fork 的 select 列表有 **6 项**，
>   最后一项是 `as_offset=11 alias_len=4 as=N text='t.*'`；**我们只有 5 项、缺 `t.*`**
>   —— `t.*` 掉在**语句层**（`_tmp_nt.py @fixture` 里显示为顶层的 `Identifier 't.*'`），
>   所以它既没换行也不参与对齐（末项 `is_last` 的 +1 也就落到了错的项上，多出那 2 格）。
>   **已用「关掉它做对照」排除**：`_trim_clause_tail`（U15 那条）**不是**元凶（关掉后 `t.*`
>   仍在列表外）。下一步：拿 `_tmp_nt.py @fixture` 与 `_tmp_forkidx.py`（同一 fixture）对比
>   **列表边界**，重点怀疑两点：①第 5 项里的 `--` 注释把官方的列表构建提前截断，
>   而我们 `_group_level` 的续接没接上；②`t.*` 是 `Identifier[t, Wildcard]`，
>   官方 `group_identifier_list` 的 `imt(i=sqlcls…)` 对它的判定与 fork 不同。
>
>   **第十二轮补记（机制推断 + 工具缺口，未改代码）**：
>   列表在**最后一个逗号处**断掉，而 `_group_level` 的续接接不上这种断点，原因是
>   **`valid_prev` 判定**：从「尾逗号」起建组时，逗号前的真实 token 就是**这个 `IdentifierList`
>   自己**，而 `_real_item`（`imt(i=_SQLCLS…)`）不认 `IdentifierList` → 组建不起来，
>   于是 `, t.*` 只能散在语句层。官方那边（`extend=True`）的语义是**扩展相邻同类组**，
>   我们的续接层没有这一步。
>   **修法方向**：给 `_group_level` 加一条「若待建组起点前紧邻的真实 token 是同层
>   `IdentifierList`，则**把它一起扩进去**」（即把 `, item` 并进那个已有列表，而不是新建组），
>   与官方 `extend=True` 对齐。注意要点：扩展后要 `_refresh_values`，且**只**在
>   「同层 + 紧邻」时做，避免把 `ddl` 那类多列表场景串起来（跑全量对拍验证）。
>   **工具缺口**：`_tmp_forkidx.py` **还不支持 `@相对路径`**（它把 `@tests/...` 当 SQL 解析，
>   会出现 `Operation '/'` 这种假 token）——下一轮先给它补上，再和 `_tmp_nt.py` 两侧对齐列表边界。
>   **已补（第十三轮）**：`_tmp_forkidx.py` 现在支持 `@相对路径` ✓。补完立刻拿到 fork 的
>   `group_tokens` 轨迹，**直接印证了修法方向**：fork 是**逐步扩展同一个列表** ——
>   `IdentifierList start=5 end=9 → end=10 → …`（`start` 不变、`end` 递增），
>   也就是官方的 `extend=True` 一直在把「尾逗号 + 下一项」并进同一个列表。
>   **试过的第一步**：在 `_group_level` 的 `valid_prev` 里外加
>   `or isinstance(token, sql.IdentifierList)` —— **对 `case/sqltest4_s01` 无效果、也无回归**，
>   说明触发点不在这个回调上（已回滚，只留注释说明）。
>   **下一步（下一位接手从这里开始）**：**diff 官方 `engine/grouping.py::_group` 与旧 fork 的
>   `_group`**（fork 的 `grouping.py` 与官方差 432 行，很可能就改在这里）；重点看 fork 是怎么
>   在 `start` 已经是同类组时「扩进去」而不是「新建组」的，再把这一条搬进我们的续接层。

### 9.4 S7 执行卡（含「有意偏离」处置决定）

> 决策人：AI（用户 2026-09-12 授权「你最佳实践处理」）。执行顺序**不可调换**，
> 每步一个独立提交，失败就 `git revert` 单个提交即可回退。

**S7-a 门禁转正** ✅ **完成**（提交 `14973fc`）：新增 `tests_migration/test_convergence.py`
（跑在新实现上），实测**幂等 62 项全绿**、收敛 31 个里 5 个不一致（按实测登记，
`dml/sqltest1_s06` 已**不在**列 —— S5a 兜底带来的净收益）；压平口径抽到
`tests/fixtures/whitespace.py`（不导入 `sqlfmt`）。

**S7-b 入口切换**：`sqlfmt.py` 的 `sqlfilefmt()` 改为调用 `sqlfmt_ext.format_statements`，
`DEFAULT_OPTIONS` 保持同名同义；`sqlparse` 从 vendored 目录变为 pip 依赖（`>=0.6,<0.7`）。

> **S7-b 附加动作（实测必需）**：新增**仓库根 `conftest.py`**，把「让已安装官方包胜出」的
> `sys.path` 调整提到根级 —— 否则 `tests/` 会话会用仓库根的旧 fork 去喂 `sqlfmt_ext`
> （root 在 `sys.path` 里胜出）→ 静默错乱。
>
> **S7-b 实测的 6 个失败（窗口期已知，分类如下，S7-c/d 各自处置）**：
>
> | 失败项 | 性质 | 处置 |
> |---|---|---|
> | `test_sqlfmt_output_regression[case/sqltest4_s03]` | 基线未重定（= 有意偏离） | **S7-d** 重定 fixture |
> | `test_sqlfmt_convergence[dml/sqltest1_s06]` | **陈旧 xfail**：新实现已收敛 → XPASS(strict) | S7-c 迁移 `tests/` 时删掉该项（好消息） |
> | `test_layout_variants[case-operation]` | 同一处偏离的**内联期望**（`case` / `when` 分两行） | **S7-d** 一并重定 |
> | `test_layout_variants` 的 3 个 `ddl-column-*` | ✅ **已修（提交 `31d2e72`，见下）** | 不再需要登记 |
>
> 即：**「实现切换」与「基线翻转」不可能在同一提交里都绿**（`tests/` 的输出回归钉着旧基线），
> 这是卡片允许的短暂窗口，S7-b 的提交信息里写明了。

**S7-c 删 fork（独立提交，用户指定）**：`git rm -r sqlparse/`；处置依赖它的 `tests/`
（迁移到新实现或按需删除）；删掉 `tests_migration/conftest.py` 里的 `sys.path` 共存 hack。
**提交信息里必须写清「这是不可逆动作、回退方式」**。

> ✅ **完成（提交 `31d2e72` 之后那一个）**。实测：
> `import sqlparse` → `.venv\...\site-packages\sqlparse`（dist 0.6.0）✓；
> `tests/` **2 failed, 169 passed, 5 xfailed**（失败只剩 `case/s03` 输出回归与
> `layout_variants[case-operation]` 这条同一偏离的内联期望 → 都是 S7-d）；
> `tests_migration/` 119 passed, 5 xfailed 不变；
> **两套件同会话** `pytest tests tests_migration` → 288 passed, 10 xfailed ✓（删 fork 前不可能）。
> 同时删掉 `tests_migration/conftest.py`（sys.path hack + 混跑守卫）与
> `tests/test_sqlfmt_convergence.py` 里的陈旧 xfail `dml/sqltest1_s06`，
> `pyproject.toml` 的 pytest 注释也去掉了「迁移期两个 sqlparse」的说法。

**S7-d 有意偏离处置（本次决定：正式重定基线，清单归零）**
- **做法**：删 fork 之后，用**另一个独立提交**把 `tests/fixtures/cases/case/sqltest4_s03.sql`
  改成本实现的口径（`case` 与首个 `when` 同行），随后删掉
  `tests_migration/test_parity.py` 里的 `DEVIATIONS` 条目（该条的「变换失效」守卫会自动提示），
  `case/s03` 变成普通通过用例，**偏离清单归零**。
- **理由（最佳实践）**：①删 fork 前不能改——主套件还钉着旧基线，改了立刻红；
  ②删 fork 后若留着「断言型偏离」，等于把一个**已经没有对照对象**的特殊分支长期养在测试里
  （维护成本 + 后人困惑）；③单独一个提交，回退就是 revert 它。
- **提交信息模板**：`chore(baseline): 重定 case/sqltest4_s03 基线（case 与首个 when 同行）；旧基线依赖输入换行，口径 2026-09-12 决策 — 至此有意偏离清单归零`。

**S7-e 收口**：README / AGENTS.md 更新（删掉「迁移期两个 sqlparse」「两套件分开跑」等迁移期说明），
`_tmp_*.py` 一并删除（PLAN §9.3 顶部已有约定）。

> ✅ **S7 全部完成**（S7-a~e 五个独立提交 + 一个 DDL 顺带修复）：
> `14973fc`（a 门禁转正）→ `e1378e5`（b 入口切换）→ `8de1fb7`（c 删 fork，不可逆）
> → `a257560`（d 基线重定、偏离清单归零）→ `4471cd6`（e 收口）；
> 期间 `31d2e72` 修掉 ddl 字段列表被 U13 误包进 `Function` 导致「整条 DDL 折成一行」的缺口。
>
> **收口后的形态**：`sqlfmt.py`（薄壳 CLI）→ `sqlfmt_ext/`（官方 0.6.0 的外挂补偿层）；
> `sqlparse` 是 pip 依赖；只有一套测试 `tests/`；验收门槛
> **`.venv\Scripts\python.exe -m pytest -q` → `172 passed, 4 xfailed`（0 failed）**。
> §2.3「迁移期共存」、§3.3 的双套件门槛、§9.3 的收尾清单都是**已兑现的历史记录**，
> 阅读时以本节与 §9 头部为准。
> - `nested/sqltest3_s01`：`end` 后逗号列我们**窄很多**（期望对齐到很宽的一列 → 目标列由
>   列表里某个长项决定）。同上先两侧对照。
> 现网代码保持 `if`（两套件 `28/3` + `170/6` 绿）。

*S6b —— 列表末尾列（`case/sqltest4_s01`、`nested/sqltest3_s01`、`window/sqltest6_s03`）*
- `case/sqltest4_s01`：末项 `rn       ,` 我们**多 2 格**，且 `t.*` 没被断到下一行
  （我们 `… asc)    rn         , t.*`，期望 `rn       ,` + 换行 + `t.*`）；
- `nested/sqltest3_s01`：`end` 后逗号列我们**窄很多**（期望把它对齐到很宽的一列 →
  目标列由列表里某个长项决定），`H1_HUKOU … as CityName /*-*/` 那行同理；
- `window/sqltest6_s03`：整体 **+1 格**（`select a      ,` 6 格 vs 我们 7 格，`b /*-*/` 同理）。
- 入口：`align.py::_identifier_layouts`（`max_as_offset` / `max_alias_len` 的汇总）+
  `_apply_identifier_layout` 的 `is_last` 分支。
  **关键前提：这两个函数与旧 fork 已逐行 diff 过、完全相同**，所以偏差只可能来自
  **入参**（`as_offset` / `max_as_offset` / `alias_len`）或**列表项集合**。
  先用 `_tmp_align_probe.py "<该语句>"` 把两侧的 `[layouts]` / `[apply]` 打出来对齐再动。
  **两个「照抄 fork 的怪癖」别当 bug 改掉**：无别名时 `alias_len == len('None') == 4`；
  `is_last` 会额外 `+1`。

*已收（本轮）*：S6a = U16（`DATETIME` 进词表）修好 `ddl/s02`，诊断手法 `_tmp_ddlprobe.py`；
S6c = U13（`_wrap_create_table_calls` 在官方分组后补包 `Function`）修好 `ddl/s01`。

*S6b —— 列表末尾列（3 个）*
- `case/sqltest4_s01`：末项 `rn       ,` 我们**多 2 格**，且 `t.*` 没被断到下一行
  （我们 `… asc)    rn         , t.*`，期望 `rn       ,` + 换行 + `t.*`）；
- `nested/sqltest3_s01`：`end` 后逗号列我们**窄很多**（期望把它对齐到很宽的一列 →
  目标列由列表里某个长项决定），`H1_HUKOU … as CityName /*-*/` 那行同理；
- `window/sqltest6_s03`：整体 **+1 格**（`select a      ,` 6 格 vs 我们 7 格，`b /*-*/` 同理）。
- 入口：`align.py::_identifier_layouts`（`max_as_offset` / `max_alias_len` 的汇总）+
  `_apply_identifier_layout` 的 `is_last` 分支。
  **注意两个「照抄 fork 的怪癖」，别当 bug 改掉**：无别名时 `alias_len == len('None') == 4`；
  `is_last` 会额外 `+1`。改之前先用 `_tmp_align_probe.py` 把两侧的
  `[layouts]` / `[apply]` 打出来对齐，再动算术。

### 9.4 诊断工具（**已全部删除**，需要时现场写 `_tmp_*.py`）

S7 把迁移期的探针（`_tmp_check.py` / `_tmp_cmp.py --fork` / `_tmp_align_*.py` /
`_tmp_forkidx.py` …）连同旧 fork 一起删了 —— 那些脚本的 `--fork` 侧已无处可跑。
`.gitignore` 仍忽略 `_tmp_*`，所以**诊断脚本一律现场写、用完即删**。诊断手法（元规则一~七、
工作流、坑位）见技能 `.codebuddy/skills/sqlfmt-parity/`，不要再在这里复制一份。

唯一**没有** fork 也能用的形状：直接读树。

```python
# _tmp_dump.py：在 LayoutPass 入口 dump 语句层 token（带 ttype / is_newline / 缓存 value）
import sqlfmt_ext.stack as st
orig = st.LayoutPass.process
def patched(self, stmt):
    for tk in stmt.tokens:
        print(type(tk).__name__, repr(tk.value), tk.ttype, "is_nl=", tk.is_newline)
    return orig(self, stmt)
st.LayoutPass.process = patched
from sqlfmt_ext import format_statements
print(format_statements("..."))
```

**排查踩过的坑**：
- `FilterStack.run(sql)` 返回**生成器**，不消费等于没跑 → 自建探针时必须
  `list(stack.run(sql))`，否则「探针没打印」会被误判成「没有该现象」。
- 官方 `Lexer.get_tokens()` 产出的是 `(ttype, value)` **元组**，不是 Token 对象。
- `Token.is_newline` 是**构造期按 ttype 缓存**的属性、`Token.normalized` 同理，
  strip 之后 value 变了、这两个不变 —— 想验证「输出是否依赖输入空白」，
  用压平输入 `tests.fixtures.whitespace.flatten_whitespace` 跑一遍再比即可。
- 探针要打「真实 fixture」而不是抽出来的片段：很多形状只在完整 fixture 里出现
  （§8 第十五轮 `nested/sqltest3_s01` 的教训）。

### 9.5 不要做的事

- 不要用「改 ttype / 删非空白 token / 重排」的手法对齐（C5）。
- 不要用「改官方 strip 让它保留换行」的魔改（C4）—— 想利用「输入这里有个换行」时，
  先看 `Token.is_newline` 那类**缓存属性**（它就是残留，见 §9.6）。
- 不要把诊断脚本留在仓库里（`_tmp_*` 用完即删）。

### 9.6 S9 已收（2026-09-13）：注释断行的结构性口径 —— 收敛门禁 4 xfail → 1

**靶子**：F6（收敛门禁）剩的 4 个 xfail，全部是「输出仍依赖输入空白」，且都是注释/分号
的**结构性断行**没做透：`comma/sqltest7_s02`、`nested/sqltest3_s01`、`ddl/sqltest0_s04`、
`cte/sqltest2_s01`。

**复现**：`tests/fixtures/whitespace.flatten_whitespace` 把 canonical 的换行压成空格再格式化，
输出必须还是 canonical。四项实测差异只有三处根因（诊断脚本用完即删）：

| 用例 | 根因 |
|---|---|
| `comma/sqltest7_s02`、`nested/sqltest3_s01` | 两段相邻注释「各占一行」只由**组内**规则（`_break_between_comments`）保证；而这两段注释经官方 `align_comments` 并组、又被 `_unabsorb_trailing_comments` 拆回后，是**同层并列的两个 `Comment` 组** —— 组内规则看不到它们，旧实现只剩「输入里这里正好有换行」（`prev_.is_newline`）兜着，压平即失效 |
| `ddl/sqltest0_s04` | `ON COMMIT` 白名单只做了一半：输入写 `on\ncommit` 时保留分行，写 `on commit` 时不管 → 输出依赖输入 |

**改动**（都在 `sqlfmt_ext/passes/layout.py`，无新文件）：

1. **`_break_before_sibling_comment`（新增）**：`_break_between_comments` 的同一条规则
   「两段注释不共享一行」，扩到**同层并列的注释组**。判据是结构性的「**前一段注释自己不带
   行尾换行**」（`-- x` 的 token 含行尾换行、块注释不含）→ 换行 `self.nl(0)`（本层缩进）。
   在 `_process_comment` 里紧跟 `_break_between_comments` 调用（必须在它那个「只处理
   `--` / `/*-*/`」的早退之前）。
   为什么不并组：试过在 `grouping` 层把相邻注释并成一个组，**回归 4 个用例**
   （`ddl/sqltest0_s05`、`window/sqltest6_s02`、`case/sqltest4_s01`、`cte/sqltest2_s02`）——
   那些是**行注释**串，后一段的缩进要交给 `_process_comment` 的对齐逻辑（列 7），
   并组会把它们拉回列 0。判据必须落在「前一段自不自带换行」上。
2. **`_normalize_newlines` 的 `keep_newline` 白名单改成结构性**：命中者（`ON COMMIT`）
   一律 `self.n.join(tk.value.split())` 切开，不管输入是 `on\ncommit` 还是 `on commit`。
   `normalized` 同步更新（`'ON\nCOMMIT'`，下游都走 `\s+` 正则匹配，不受影响）。

**证据**：改后 `pytest -q` → `175 passed, 1 xfailed`；4 项里 3 项 **XPASS(strict)** 报错
（说明确实收敛），按纪律从 `tests/test_sqlfmt_convergence.py::KNOWN_DIVERGENT` 删除并写明原因。
`172 passed` 那批（输出回归 / 幂等）一个没动。

**验收**：`.venv\Scripts\python.exe -m pytest -q` → **`175 passed, 1 xfailed`（0 failed）**。

**残留 / 下一步**：
- `cte/sqltest2_s01` 留作**已登记的发散**（不是缺口）：canonical 把 `-- 顶行首注释` 放在列 0、
  `;` 也放列 0，而这一摆放**只能由输入空白判定**（`prev_.is_newline` 分支，即用户定的
  「注释串原本在列 0 的保持不变」口径）。压平输入后该注释本来不在列 0，任何**结构性**实现都
  给不出 canonical 那两行 → 要收敛只能重定该 fixture 的注释缩进口径，属**口径决策**，
  留给用户拍板（若要拍：新起一段，别顺手改 fixture）。
- 下一阶段按 §3 状态表：**S8 方言补完**（Doris/SelectDB → SQL Server）。

**回退方式**：两处改动各自独立 —— `_process_comment` 里的那一行调用（删掉即回到
「依赖输入换行」）与 `_normalize_newlines` 里新增的 `if` 分支（删掉即回到「只在输入已是
换行时保留」）。`KNOWN_DIVERGENT` 的两处删项也各自 revert 即可，`xfail(strict=True)`
会在回退不彻底时主动报错。

---

### 9.7 S10 已收（2026-09-13）：「注释保持列 0」判据结构化 —— 收敛门禁 1 xfail → 0

**决策原文**（用户 2026-09-13 拍板）：「原本在 0 列，改在语句前的限定，即 ddl/dml 等
**单个 stmt 真实开始之前**的时候适用。」

**靶子**：收敛门禁最后一个 xfail `cte/sqltest2_s01` —— 也是全仓最后一处「输出依赖输入空白」。

**根因**：canonical 把 `where … = 0` 尾部的 `-- 顶行首注释` 与 `;` 都摆在列 0，而决定点是
`_process_comment` 收尾的 `prev_.is_newline`，字面意思「**输入里**这个注释前面是换行」→
保持原样（`self.n`，列 0）。压平输入后那个换行变成空格，判据为 False，注释被并回上一行、
`;` 落到 7 列。**判据读的是输入空白，与 C4 天然冲突** —— 不是实现缺口。

**改动**（都在 `sqlfmt_ext/passes/layout.py`；无新文件、**无 fixture 改动**）：

| # | 位置 | 改动 |
|---|---|---|
| ① | `_process_comment` 早退 | 判据由 `self._get_offset(tlist, relative=False) == 0` 换成新增的 `_is_stmt_leading_comment(tlist)`：**结构性**判定「它之前（逐层向上追问祖先层）不存在任何有效 token」，即决策原文说的**语句前导注释**。列 0 的适用范围就此收窄到这一类 |
| ② | `_process_comment` 收尾（`prev_.is_newline` 支） | 补一条结构性等价：新增 `_closes_its_level(plist, pidx)` =「其后本层只余空白与语句结束符 `;`」。两条输入路径归一到「本层换行 + 列 0」 |

**②的判据为什么必须卡在 `;` 上**：`;` 常被官方分组收进**子句组内部**（`where …\n-- x\n;`
里 `;` 就在 `Where` 组中），所以「其后无内容」对 `-- 顶行首注释` 并不成立（后面还有 `;`），
必须显式放行 `;`；同时又**必须要求 `;` 存在** —— 层内最后一个 token 的**行内**注释
（`EmpCode -- 员工编码`）同样满足「其后无内容」，放行它就会把行内注释强行换行，实测回归
`comma/sqltest7_s02`、`dml/sqltest1_s02`（两个用例都已复现并修回）。

**证据**：`cte/sqltest2_s01` 的 canonical **不需要重定** —— 执行卡原计划的「按实跑输出重定」
没有发生。改后原样输入与压平输入产出**同一份、且与现有 canonical 逐字节相同**的输出
（`-- 顶行首注释` 与 `;` 都在列 0）。全量门禁 `176 passed`，其余 175 项一项没动。

**验收**：`.venv\Scripts\python.exe -m pytest -q` → **`176 passed`（0 failed / 0 xfailed）**；
`tests/test_sqlfmt_convergence.py::KNOWN_DIVERGENT` 最后一项按 XPASS(strict) 提示删除并写明原因
（该常量现为空）。

**残留 / 下一步**：
- 语义无残留。收工时记过「一处口径细节」备查：`-- 顶行首注释` 物理上位于 `Where` 组内，却被
  归一到了语句层缩进（列 0），与「按所在层级对齐」的字面读法（`Where` 层 = 列 7）不同。
  **用户随即拍板按层级对齐** → 已在 **S10-b 修订**（见 §9.8）：② 的 `self.n` 换成 `nl(0).value`，
  该 fixture 也一并按新口径重定。
- 下一阶段：**S8 方言补完**（开工前先补执行卡）。

**回退方式**：改动只有 `layout.py` 的两处判据 + 两个新增辅助方法
（`_is_stmt_leading_comment` / `_closes_its_level`）+ `KNOWN_DIVERGENT` 的一处删项，
`git revert` 本阶段提交即可（`xfail(strict=True)` 会在回退不彻底时主动报错）。

---

### 9.8 S10-b 已收（2026-09-13）：收尾注释按层级对齐、`;` 顶列 0

**决策原文**（用户，分两次给出）：

1. 「关于语句前的顶行 `--` 注释，以及结尾的分号，可以换个思路，希望它与**所在层级**对齐 ——
   即最外层的就顶 0 列，但子查询、包括 `where` 内的，其实应该是**缩进**的。」
2. （紧接着的纠正）「`;` 分号只在**分段 SQL 结尾**，它应该在 sqlfmt 中有处理，或者在前边过程中
   **不特殊处理它，只在最后将它顶 0 列**。」

**两条口径合起来**：

- **注释**：按**所在层级**对齐 —— 语句前导注释位于语句之外、层级为 0 → 列 0；子句内的收尾注释
  缩进到该子句内容列（`where` 层 = 列 7）。
- **`;`**：它是**分段终止符**（`format_statements` 按它切分语句），不是任何子句的内容 →
  **一律顶列 0**；前面各步**不碰它**，只在 layout 收尾统一兜底。

**靶子**：S10 把「本层收尾注释」的缩进统一成 `self.n`（纯换行 = 列 0），在子句组内部是错的
—— 那句注释本该缩进到列 7。

**改动**（都在 `sqlfmt_ext/passes/layout.py`）：

| # | 位置 | 改动 |
|---|---|---|
| ① | `_process_comment` 的「本层收尾注释」支 | `prev_.value = self.n` → `self.nl(0).value`（`nl(0)` = 换行 + **本层缩进**，即 `self.n + char * leading_ws`） |
| ② | `LayoutPass.process` **收尾**（`_process` 之后） | 新增 `_normalize_trailing_semicolon` + `_last_content`：取语句里最后一个非空白 token，若是 `;` 就把它与前一个 token 之间的空白规范化，使 `;` 顶列 0 |

**②为什么要放在「最后」**（用户口径的要点，也是踩过的坑）：中途给 `;` 前的空白「设成缩进」
方向就错了 —— 先按 ① + 一个临时方案把 `;` 缩进到 7 列时，第二次格式化会读到上一遍留下的空白、
被别处改成 1 个空格，**幂等与收敛同时红**。改成「前边不特殊处理 + 收尾统一兜底」后，两条输入
路径自然归一。

**②要覆盖两种「独占一行」形态**（实测 dump 得来）：

- 换行在 `;` 前的**空白 token** 里 → 置为单个换行；
- 换行由**前一个行注释**自带（行注释 token 尾部带换行）、中间那段空白只剩缩进 →
  把这段缩进**抹掉**。

同行写法（`select 1 ;`）不动。

**粒度**：`_is_stmt_leading_comment`（语句前导注释 → 列 0）**保持不变** —— 用户说的「最外层顶
0 列」正是它：语句前导注释位于语句之外、不属于任何子句，层级天然为 0。

**证据**：`cte/sqltest2_s01` 三条对照全等（原样输入 / 压平输入 / 输出再格式化输出）；其余 175 项
一项没动。

**验收**：`.venv\Scripts\python.exe -m pytest -q` → **`176 passed`（0 failed / 0 xfailed）**。
`tests/fixtures/cases/cte/sqltest2_s01.sql` 按**实跑输出重定**（不手写，沿用 S7-d 做法），尾部为：

```
 where t.EmpRecordNum = 0
       -- 顶行首注释
;
```

**残留 / 下一步**：无。下一阶段 **S8 方言补完**（开工前先补执行卡）。

**回退方式**：`git revert <本阶段提交>` —— `layout.py` 的 ①+② 与一个 fixture 重定，
纯文本、无不可逆动作。

---

### 9.9 S8-a 执行卡（方言层，2026-09-13 开工）

**背景**：`PLAN §3` 状态表只剩 **S8**。§5 的「S7 方言路线」（旧编号 S7a/b/c，内容归 S8）写的是
「Doris/SelectDB 声明式注册 → 官方缺失关键字按 MySQL 兼容追加 → SQL Server 适配」。
**但勘测发现真实缺口不在「补词表」，而在「方言层本身是死的」**（下表全部实测）。

**勘测结论**：

| # | 缺口 | 证据 |
|---|---|---|
| 1 | `dialects.py` **零调用**（`apply_dialect` / `split_words_for` / `get_dialect` / `DIALECTS` 无任何消费方）；其 `extra_split_words` 与 `policy.split_words` **重复声明**且从未被读 | 全仓 grep 只命中 `dialects.py` 自身与 `PLAN` 历史段 |
| 2 | **两套真身**：`lexer.SUPPORTED_DIALECTS = ("doris","selectdb")`（硬编码）vs `dialects.DIALECTS`（还含 `None`/`mysql`/`sqlserver`）→ 表里声明的方言**运行时不存在** | `dialect="mysql"` / `"sqlserver"` 的输出与 `dialect=None` **逐字节相同** |
| 3 | **未知方言静默降级**：`dialect="typo"` 不报错，直接走通用路径（拼错即静默换方言） | 同上探针 |
| 4 | **零方言 fixture**：`TOPIC_META` 无 `dialect` topic、`cases/` 无方言 SQL → 没有验收通道 | —— |
| 5 | Doris 锚点词**其实已生效**（`policy.split_words` 里本就有 `DISTRIBUTED BY` / `(DUPLICATE\|UNIQUE\|AGGREGATE)` / `PARTITION BY` / `PROPERTIES` / `BUILD` / `REFRESH` / `ON …`），只是**注册在 `policy` 而非 `dialects`** | `dialect="doris"` 下 `duplicate key…` / `distributed by …` / `properties …` 各自独占一行 ✓ |

> **修正一条旧勘测**：先前记的「`extra_split_words` 声明了没人消费 → 往 `policy.split_words`
> 追加不生效」只说对了一半 —— **词确实生效**（它们本来就在 `policy.split_words` 里），
> **不生效的是 `dialects.py` 那份重复声明**（另：`layout.py:36` 的类属性确实是导入期快照，
> 但因为是"快照同一个对象"，所以没暴露问题）。

**本轮（S8-a）目标**：把「方言」从**装饰性模块**变成**真开关**，并给它建验收通道。

1. **单一真身**：`dialects.DIALECTS` 作为唯一方言登记表；`lexer` 删掉硬编码的 `SUPPORTED_DIALECTS`，
   改为向 `dialects` 查询（方言是否存在 + 要不要打分词补丁）。
2. **未知方言报错**：`options.validate_options` 用 `dialects` 校验 → `dialect="typo"` 抛
   `SQLParseError`，不再静默降级。
3. **让声明通道变活**：`Dialect.extra_split_words` 由 `LayoutPass` **消费**（实例属性，
   替代 `layout.py:36` 的导入期类属性快照）；`policy.split_words` 只留**通用**词，
   Doris 专属词移进 `dialects` 声明。
4. **验收通道**：新建 `tests/fixtures/cases/dialect/` + `TOPIC_META["dialect"]`
   （topic 级 `options={"dialect": "doris"}`，`_build_case` 已支持，见 `sql_cases.py:71`）。
   用例要能证明**开关真的起作用**：同一 SQL 在 `dialect=None` 下**不触发** Doris 专属换行。

**验收**：

- `.venv\Scripts\python.exe -m pytest -q` → 原有 176 项**一项不变**（默认仍是 `doris`，
  词表归属搬家不影响输出），另加新增 `dialect/*` 用例；
- 同一条 Doris DDL：`dialect="doris"` 与 `dialect=None` 的输出**不同**（开关生效）；
- `dialect="typo"` 抛 `SQLParseError`。

**风险 / 雷区**：

- 现有 fixture **全部**用默认 `doris`（`FILE_OPTIONS` 只有 `align_list` / `comma_first`）→
  词表搬家理论上不碰它们，但**必须全量跑门禁**确认。
- `ON COMMIT` 属**通用** DDL（`ddl/sqltest0_s04` 依赖它，`_normalize_newlines` 的 `keep_newline`
  白名单也按它写死）→ 搬词时**必须把它留在通用表**，只把 `ON MANUAL` / `ON SCHEDULE` 归 Doris。
- `LayoutPass.split_words` 从类属性改实例属性后，`_next_token` / `_split_kwds` / `_process_comment`
  里都必须走 `self.split_words`（已确认无类级直接引用），改完要复查一遍。

**回退方式**：`git revert <本阶段提交>` —— `dialects.py` / `lexer.py` / `options.py` / `layout.py` /
`policy.py` 五处文本改动 + 新增 `cases/dialect/` 与 `TOPIC_META` 一行；纯文本、无不可逆动作。
**S8-b（MySQL 兼容追加）/ S8-c（SQL Server）不在本轮**，本轮做完再各自开卡。

#### 9.9.1 S8-a 已收（2026-09-13）

**改动**（7 个文件）：

| 文件 | 改动 |
|---|---|
| `dialects.py` | 重写为**单一真身**：`Dialect(name, lexer_patches, extra_split_words, notes)`；Doris 的 7 个换行锚点词在 `_DORIS_SPLIT_WORDS` 中声明；删掉真死代码（`apply_dialect` / `_APPLIED` / 往官方 `SQL_REGEX` 注入）；新增 `available()` 与 `all_split_words()` |
| `lexer.py` | 删硬编码的 `SUPPORTED_DIALECTS`，改问 `dialects.get_dialect(...).lexer_patches` |
| `options.py` | 方言校验：未知方言抛 `SQLParseError`（并列出可用值），不再静默降级 |
| `layout.py` | `split_words` 从**类属性（导入期快照）**改为**实例属性** = `policy.split_words + dialects.split_words_for(dialect)` |
| `policy.py` | `split_words` 只留**通用**词，Doris 专属词移入 `dialects`；`ON COMMIT` 收窄为 `\bON\s+COMMIT\b`（它属通用 DDL，`ddl/sqltest0_s04` 依赖） |
| `grouping.py` | `_is_clause_keyword` 的词表由 `policy.split_words` 换成 `_CLAUSE_WORDS` = 通用词 + **所有**方言锚点词的并集 |
| `tests/` | 新增 `fixtures/cases/dialect/sqltest0_s01.sql`（Doris 建表，实跑输出定稿）+ `TOPIC_META["dialect"]` + `test_sqlfmt_dialect.py`（4 条断言） |

**本次最重要的发现（根因 + 教训）**：搬词后 `properties (1);` 突然与 `distributed by hash(id)` 挤到
同一行。顺序对照实验（把 `PROPERTIES` 手动放回 `policy.split_words` 开头即恢复）指向**分组层**：

> `grouping._is_clause_keyword` 硬引用 `policy.split_words` 判「这是不是子句关键字」。词搬走后
> `PROPERTIES` 不再被认作子句头 → `_wrap_create_table_calls`（U13）把它当函数名，把
> `properties (1)` 包成 `Function` → `_split_kwds` 在**本层**再也看不到这个 Keyword（不递归进子组）
> → 换行消失。

**教训（可复用）**：换行锚点词有**两个消费方** —— 布局层（要不要换行）与**分组层**（是不是子句头）。
分组层那个**必须与方言无关**（取所有方言的并集）：否则**换方言会连带改变分组形状**，表现为
「开关一动，整条 SQL 的结构都变」。与元规则一「列对齐错乱先怀疑分组」同源。

**验收**：`.venv\Scripts\python.exe -m pytest -q` → **`185 passed`（0 failed / 0 xfailed）**。

- 原 176 项**一项没动**（默认方言仍是 `doris`，词表归属搬家不影响输出）；
- 新增 9 项：`dialect/sqltest0_s01` 进三个门禁（输出回归 / 幂等 ×2 / 收敛）+ `test_sqlfmt_dialect.py` 4 条；
- 开关证据：同一条 Doris DDL，`dialect="doris"` 与 `dialect=None` 输出**不同**（后者与输入逐字节相同）；
- `dialect="typo"` → `SQLParseError: unknown dialect: 'typo'; available: doris, generic, mysql, selectdb, sqlserver`。

**残留 / 下一步**：

- `mysql` / `sqlserver` 目前只是**登记**（`lexer_patches=False`、无锚点词）→ 行为等同通用。
  S8-b 补 MySQL 兼容声明，S8-c 补 SQL Server（`GO` / `[ ]` / `TOP` / `WITH(NOLOCK)`）。
- `LATERAL VIEW` 仍留在**通用**词表（generic 下因分词层不合并而天然不生效），未按方言拆分 ——
  暂按「本项目通用增强」处理，S8-b 再评估。

**回退方式**：`git revert <本阶段提交>`（7 处文本改动 + 新增 topic/测试；纯文本、无不可逆动作）。

---

### 9.10 S8-b 执行卡（方言词表归位 + Doris 类型名补齐，2026-09-13 开工）

**背景**：S8-a 只把**换行锚点词**收进了 `dialects`；**分词层的方言词表还留在 `policy`**
（`KEYWORDS_DORIS` / `KEYWORDS_TYPES`，全局、与方言无关），`lexer` 直接读 `policy`。S8-b 把这条也收进去，
并补齐 Doris/SelectDB 在官方 0.6.0 下**缺失的类型名**。

**勘测证据（实测，本轮已跑）**：一条含 Doris 常用类型的建表语句，**列对齐直接错乱**：

```sql
create table dw.t (id int64, name varchar(20), v1 string, v2 datev2, v3 datetimev2(3), v4 decimalv3(10, 2), v5 largeint, v6 bitmap, v7 json);
```

```text
       id int64                    ,   ← 字段名与类型挤在一起（被粘成同一个 Identifier）
       name        varchar(20)     ,   ← 正常
       v1          string          ,   ← 正常
       v2 datev2                   ,   ← 异常
       v3          datetimev2(3)   ,   ← 异常
       v4          decimalv3(10, 2),   ← 异常
       v5 largeint                 ,   ← 异常
       v6 bitmap                   ,   ← 异常
       v7 json                         ← 正常
```

token 级证据：`int64` / `datev2` / `datetimev2` / `decimalv3` / `largeint` / `bitmap` 全部落成
**普通 `T.Name`**，而 `varchar` / `string` 是 `T.Name.Builtin`、`json` 是 `T.Keyword` —— 前者于是被
`group_identifier` 与字段名**粘成一个 `Identifier`**，`_create_field_lines` 的类型列取不到 token，
**整列基准错**（与 U16 完全同一机理，U16 只补了 `DATETIME` 一个词）。

**官方 0.6.0 已有的内置类型**（43 个）：`ARRAY BIGINT BINARY BIT BLOB BOOLEAN CHAR CHARACTER DATE DEC
DECIMAL FILE_TYPE FLOAT INT INT8 INTEGER INTERVAL LONG NATURALN NUMBER NUMERIC NVARCHAR PLS_INTEGER
POSITIVE POSITIVEN REAL ROWID ROWLABEL ROWNUM SERIAL SERIAL8 SIGNED SIGNTYPE SIMPLE_DOUBLE SIMPLE_FLOAT
SIMPLE_INTEGER SMALLINT SYS_REFCURSOR TEXT TINYINT UNSIGNED UROWID UTL_FILE VARCHAR VARCHAR2 VARYING`
（注意：**没有** `DOUBLE`、`INT16/32/64/128`、`DATEV2`、`DATETIME`、`DATETIMEV2`、`DECIMALV3`、`LARGEINT`、
`BITMAP`、`HLL`、`JSONB`、`VARIANT`、`QUANTILE_STATE`、`AGG_STATE`、`IPV4`、`IPV6`、`MAP`(官方是 Keyword)、`STRUCT`）

**待补清单**（→ `T.Name.Builtin`）：`INT16` `INT32` `INT64` `INT128` `LARGEINT` `DOUBLE` `DATEV2`
`DATETIMEV2` `DECIMALV2` `DECIMALV3` `BITMAP` `HLL` `JSONB` `VARIANT` `QUANTILE_STATE` `AGG_STATE`
`IPV4` `IPV6`（`DATETIME` 已在 `KEYWORDS_TYPES`；`MAP` 官方已是 `Keyword`，不动）。

**本轮做法**：

1. `Dialect` 增加 `extra_keywords: dict`（词 → ttype）；`lexer` 按方言注入
   （内容 = 现有 `KEYWORDS_DORIS` + 上面的类型名）。
2. 把 `policy.KEYWORDS_DORIS` / `policy.KEYWORDS_TYPES` **迁入** `dialects` 的 Doris 声明 ——
   `policy` 不再持有方言词（S8-a 只迁走了锚点词，这次补齐分词层）。
3. 按清单补齐类型名。

**验收**：

- 上面那条建表语句的**列对齐正确**（类型列起始一致，字段名与类型不再是同一个 `Identifier`）；
- 新增 `tests/fixtures/cases/dialect/sqltest1_s01.sql` 把它固化（实跑输出定稿）+ `test_sqlfmt_dialect.py` 加断言；
- `dialect=None` 下 `int64` 等仍是普通 `Name`（开关仍只在 doris/selectdb 生效）；
- 门禁：原 185 项 + 新增。**唯一已知影响面**是 `dml/sqltest8_s01`（含 `ARRAY<VARIANT>`）——
  `VARIANT` 变 `Builtin` 后该用例输出若有变化，逐条判断是「修正」还是「回归」。

**风险 / 雷区**：

- `VARIANT` 已在 fixture 里（见上）。
- `DOUBLE` / `MAP` 等若被当**列名**会误判（MySQL 里它们是保留字，作列名须反引号）→ 风险低，
  但加词后必须全量跑门禁。
- 迁移词表时 `policy` 里若还有别处引用 → 已 grep 确认只有 `lexer.py` 两行（`add_keywords`）。

**回退方式**：`git revert <本阶段提交>`（`dialects.py` / `lexer.py` / `policy.py` / 测试与 fixture；
纯文本、无不可逆动作）。

#### 9.10.1 S8-b 已收（2026-09-13）

**改动**（5 处）：

| 文件 | 改动 |
|---|---|
| `dialects.py` | `Dialect` 增加 `extra_keywords`（`((word, ttype), ...)`）；Doris/SelectDB 声明新增 `_DORIS_MODEL_KEYWORDS`（`BUCKETS`/`AUTO`/`PROPERTIES`）与 `_DORIS_TYPE_NAMES`（20 个类型名），合成 `_DORIS_EXTRA_KEYWORDS` |
| `lexer.py` | `add_keywords(policy.KEYWORDS_DORIS / KEYWORDS_TYPES)` → `add_keywords(dict(dialect.extra_keywords))`（分词词表也走方言声明） |
| `policy.py` | 删 `KEYWORDS_DORIS` / `KEYWORDS_TYPES`（方言词不再散落在通用层），docstring 标明去向 |
| `tests/` | 新增 `cases/dialect/sqltest1_s01.sql`（Doris 全类型建表）+ `test_sqlfmt_dialect.py` 加 2 条断言 |

**补齐的 20 个类型名**：`AGG_STATE BITMAP DATETIME DATEV2 DATETIMEV2 DECIMALV2 DECIMALV3 DOUBLE
HLL INT16 INT32 INT64 INT128 IPV4 IPV6 JSONB LARGEINT QUANTILE_STATE STRUCT VARIANT`
（`DATETIME` 是 U16 补过的，本次一并归位到方言声明）。

**效果（证据）**：勘测里那条建表语句从「字段名与类型挤在一起、列基准错」变成**列对齐正确**：

```text
       id       int64           ,
       name     varchar(20)     ,
       v1       string          ,
       v2       datev2          ,
       v3       datetimev2(3)   ,
       v4       decimalv3(10, 2),
       v5       largeint        ,
       v6       bitmap          ,
       v7 jsonb
```

**`dialect=None` 仍错乱**（`id int64`、`v2 datev2`… 粘在一起）→ 开关只在 doris/selectdb 生效，
这条已写成断言。

**验收**：`.venv\Scripts\python.exe -m pytest -q` → **`192 passed`（0 failed / 0 xfailed）**；
原 185 项一项没动；新增 7 项（新 fixture 进三个门禁 + 2 条断言，另加 case-integrity 的 1 项）；
已知影响面 `dml/sqltest8_s01`（含 `ARRAY<VARIANT>`）**输出无变化** ✓。

**残留 / 下一步**：

- `json` 在官方词表里是 `T.Keyword`（不是 `Name.Builtin`）→ **未覆盖**：覆盖它等于「改写官方已有
  条目」，与 `dialects.py` 的原则冲突。真要用（Doris 里 `json` 是类型名，行内对齐会差一格）需另开一段。
- `MAP` 同理由（官方是 `Keyword`）未动。
- 下一步 **S8-c（SQL Server 适配）**：`GO` 批分隔符、`[ ]` 标识符、`TOP`、`WITH(NOLOCK)`。

**回退方式**：`git revert <本阶段提交>`（5 处文本改动 + 新增 fixture/断言；纯文本、无不可逆动作）。

---

### 9.11 S8-c 执行卡：SQL Server 适配（`GO` / `TOP` / `WITH(NOLOCK)` / `[ ]`）

**背景**：S8-a/S8-b 只把**词表**变成了开关 —— `dialect="sqlserver"` 与 `dialect=None` 至今
**逐字节相同**（SQL Server 一支零行为差异）。开工前逐条实测四个目标构造：

| # | 构造 | 实测现状（官方 0.6.0 + 本项目） | 处置 |
|---|---|---|---|
| 1 | `[id]` / `[dbo].[t]` | 官方就认（落 `Token.Name`），输出已正确 | **不改**，只固化 fixture |
| 2 | `TOP 10` | `top` 落 `T.Name` → 被 `group_identifier` 包成 `Identifier`，紧跟的**数字**又被 `group_identifier_list` 的 extend 收进**第一个列表项** → 列表成 `[10 id, name]`，字段列基准取到数字上：`select top 10   id,\n           name` | **修**（分组层，官方分组**前**预包） |
| 3 | `WITH (NOLOCK)` | `with (nolock)` 的 `with` 落 `Keyword.CTE` → `LayoutPass._split_statements` 认 `T.CTE` → **独占一行**；而 `with(nolock)`（`(` 紧贴）先被官方「函数名」正则截成 `Name` → 粘在表名后。**同一语义两种写法两种输出** | **修**（分词层，方言优先级规则） |
| 4 | `GO` 批分隔 | `GO` 是官方 `T.Keyword`，但切分**只按 `;`** → 无分号时 `select 1\nGO\nselect 2` 被排成 `select 1 go`（胶成一条语句）；且输出随输入空白/大小写漂移（`'go\n\nselect 2;'` vs `'go\nselect 2;'`） | **修**（切分层，按 token 切批） |

**目标（本轮只做这一件）**：让 `sqlserver` 成为**行为真的不同**的方言，并修掉 2/3/4。

1. `dialects.Dialect` 声明拆细：`lexer_patches: bool` → `multiword_patches`（Doris 多词补丁
   `policy.MULTIWORD_REGEX`）+ `precedence_patches`（通用优先级补丁 `policy.PRECEDENCE_REGEX`）；
   新增 `extra_lexer_rules`（**只对本方言生效**的优先级规则）与 `batch_separator: str`。
   理由：SQL Server 要「优先级补丁」（`over (`）但**不要** Doris 的 `PARTITION BY` /
   `DISTRIBUTED BY` 那套多词合并。
2. SQL Server 声明 = `precedence_patches=True` + `extra_lexer_rules=((r"WITH\b(?=\s*\()", T.Keyword),)`
   + `extra_keywords=(("TOP", T.Keyword), ("PERCENT", T.Keyword))` + `batch_separator="GO"`。
   `WITH(?=\s*\()` 只吃「`WITH` 紧跟 `(`」，CTE（`with cte as (…)`）不受影响。
3. `grouping.py` 新增**官方分组前**的 `_pre_merge_top_clause`：把 `TOP <n> [PERCENT]`（含括号形
   `TOP (<n>)`）合并成**单个 `T.Keyword` token**，词值按空格归一（`top    10` 的原始间距不漏进输出）。
   选 `Keyword` 而非 `Identifier` 组是**对照实验的结论**：`Identifier` 组会被
   `group_identifier_list` 的 extend 吸进列表（首字段前多 2~6 格、后一个字段被并进同一项、
   其余退回 DML 列），`Keyword` 不会被吸 —— 合并后列表恢复成 `[id, name]`，对齐基准回到真实字段名。
   合并后大小写交给官方 `KeywordCaseFilter`（预处理层，早于分组）统一，因此 `TOP 10` 与 `top 10`
   输出一致、幂等确定。**闸门 = 「`TOP` 在本方言下是不是 `T.Keyword`」**（靠第 2 条的关键字声明）：
   其余方言与 `dialect=None` 的官方基线行为不变。
4. `stack.format_statements` 增加**批切分**：判据取自**分词结果**（「独占一个 token 的
   `GO`」），不看行首形态 —— 这样压平空白后的输入与 canonical 走同一条路径，**收敛门禁不破**。
   逐批仍走原 `;` 切分，批之间用 `\n<sep>\n\n` 连接，末尾有分隔符则补一行；空批（连续
   `GO` / 只有空白）直接丢弃。
5. 验收通道：新增 `tests/fixtures/cases/sqlserver/`（4 个 fixture）+ `TOPIC_META["sqlserver"]`
   （topic 级 `options={"dialect": "sqlserver"}`）+ `test_sqlfmt_dialect.py` 补断言。

**验收（门槛数字）**：
- 原 **192 项一项不变**（默认方言仍 doris；四个构造都不在既有 fixture 里，`[ ]`/`top`/`with (`/`go`
  已 grep 确认零命中）；
- `dialect="sqlserver"`：①`select top 10 id, name …` 字段列对齐正确；②`from dbo.t t with (nolock)`
  不换行；③`select 1\nGO\nselect 2` 切成两批且 `GO` 独占一行；
- `dialect=None`：三处**都不生效**（`top 10` 仍错位、`with (nolock)` 仍换行、`GO` 不切批）→ 开关真起作用；
- `.venv\Scripts\python.exe -m pytest -q` → 192 + 新增（4 个 fixture 进四个门禁 + 断言）。

**风险 / 雷区**：
- `TOP` 合并的判据是「`TOP` 后紧跟数字或 `(<数字>)`」：`select top from t` / `select top, x`
  不触发（已实测）；`TOP (@n)` 变量形式**不猜**、保持原样。
- 批分隔符按**独立 token** 判，**不解析字符串/注释内容**（sqlcmd 同款口径）：字符串里独占一行的
  `go` 会被切 —— 目前无此形状用例，登记为已知边界。
- `batch_separator` 输出**恒为声明字面量**（`GO`，与输入大小写无关），不受 `keyword_case` 影响 →
  满足 C4/收敛；若用户要小写 `go`，改 `dialects.py` 里那一个字符串即可。
- `dialects.Dialect` 字段改名会波及 `lexer.py`（唯一消费方，已 grep）；`mysql`/`generic` 保持两个
  开关全 False（与主基线 `dialect=None` 一致）。

**回退方式**：`git revert <本阶段提交>`（`dialects.py` / `lexer.py` / `stack.py` / `grouping.py`
四文件文本改动 + 新增 topic/fixture/断言；纯文本、无不可逆动作）。

#### 9.11.1 S8-c 已收（2026-09-13）

**改动**（5 个文件 + 1 个新 topic）：

| 文件 | 改动 |
|---|---|
| `dialects.py` | `Dialect.lexer_patches` 拆成 `multiword_patches`（Doris 多词合并）+ `precedence_patches`（通用 `OVER (` 补丁）；新增 `extra_lexer_rules`（方言专属优先级规则）与 `batch_separator`；新增 `batch_separator_for()`；声明 `sqlserver`（`WITH(?=\()` 规则 + `TOP`/`PERCENT` 关键字 + `batch_separator="GO"`） |
| `lexer.py` | 按 `multiword_patches` / `precedence_patches` / `extra_lexer_rules` 三项分别注入（此前是一个 `lexer_patches` 开关） |
| `grouping.py` | 新增 `_pre_merge_top_clause` + `_top_clause_span`，在**官方分组前**跑；docstring 补第 6 条缺口 |
| `stack.py` | `format_statements` 增加批切分：`_split_batches`（按分词结果判「独立 `GO` token」）/ `_join_batches`；原主体抽成 `_format_batch` |
| `tests/` | 新增 `cases/sqlserver/sqltest0_s01.sql`（`[ ]` + 表提示）、`sqltest1_s01.sql`（`top 10`）、`sqltest1_s02.sql`（`top (10) percent`）、`sqltest2_s01.sql`（`GO` 两批）+ `TOPIC_META["sqlserver"]` + `test_sqlfmt_dialect.py` 3 条断言 |

**效果（证据）**：`dialect="sqlserver"` 与 `dialect=None` 至此**输出不同**（此前逐字节相同）：

```text
top 10    sqlserver: select top 10 id  ,           generic: select top 10   id,
                               name                              name
with hint sqlserver:   from dbo.t with (nolock);   generic:   from dbo.t
                                                             with (nolock);
GO batch  sqlserver: select 1 \n GO \n\n select 2  generic: select 1 go \n\n select 2
```

**验收**：`.venv\Scripts\python.exe -m pytest -q` → **`215 passed`（0 failed / 0 xfailed）**。

- 原 192 项一项没动（默认方言仍 `doris`；四个构造在既有 fixture 里 grep 零命中）；
- 新增 23 项：4 个 fixture 各进四个门禁（输出回归 1 + 幂等 2 + 收敛 1 + case-integrity 1 = 5）
  = 20，加 `test_sqlfmt_dialect.py` 3 条 = 23；
- 开关证据：`dialect=None` 下三处**都不生效**（`top 10` 仍错位、`with (nolock)` 仍换行、`GO` 不切批）。

**残留 / 下一步**：
- 批分隔符不解析字符串/注释内容（字符串里独占一行的 `go` 会被切）—— 与 sqlcmd 按行口径同级，
  登记为已知边界（`PLAN §9.11` 风险条目）。
- `json` / `map` 官方判成 `Keyword`，本项目不改写官方条目 → 未覆盖（见 §9.10.1 残留）。
- 方言路线（S8-a/b/c）**至此走完**；`mysql` 仍是纯登记（与通用路径一致）。

**回退方式**：`git revert <本阶段提交>`（5 处文本改动 + 新增 topic/fixture/断言；纯文本、无不可逆动作）。

---

### 9.12 S8-d 执行卡：MySQL 方言（2026-09-13 勘测，待开工）

**优先级（用户口径）**：Doris / SelectDB 最优先 → **其次 MySQL** → Oracle / SQL Server 暂缓。

**背景**：`dialect="mysql"` 目前是**纯登记** —— 勘测实测 `mysql == generic : True`（与
`dialect=None` 逐字节相同）。拿「一条含 `comment` / 索引 / 表选项的建表 + `on duplicate key update`
+ `straight_join` + ALTER」做勘测，逐条缺口：

| # | 构造 | 实测现状 | 处置 |
|---|---|---|---|
| 1 | 类型名 | `mediumint bool varbinary tinytext mediumtext longtext tinyblob mediumblob longblob datetime zerofill` **11 个**落普通 `Name` → 不带括号时被 `group_identifier` 与字段名粘成一个 `Identifier`：`content mediumtext`、`data longblob`、`created_at datetime` 挤进同一列 | **修**：进 `extra_keywords`（`T.Name.Builtin`），与 U16 同机理 |
| 2 | 表选项 | `) engine=innodb auto_increment=1 default charset=utf8mb4 collate=utf8mb4_general_ci comment='员工表'` 全挤在 `)` 之后；现存的换行是 `wrap_after=30` 撞出来的（`… default` / `charset = …` / `comment = …`） | **修**：`extra_split_words` 补锚点，各自成行 |
| 3 | `ON DUPLICATE KEY UPDATE` | `duplicate` 落 `Name`、整段未合并 → 被切成 `on duplicate key` / `update b =` / `values(b);` 三行 | **修**：多词合并成一个 `Keyword` |
| 4 | `STRAIGHT_JOIN` / `VALUES(col)` | `straight_join` 被 `policy._join_words` 命中 → `select` 后被硬断行（`select\nstraight_join a.id  ,`）；`b = values(b)` 里的 `values` 撞通用锚点 → 右值被甩到下一行 | **修**：加**结构性 guard**「锚点紧跟 `SELECT`（select 修饰符）或紧跟 `=`（赋值右值）时不换行」 |
| 5 | 索引定义 | 复查：`idx_dept (dept_id)` 被官方 `group_functions` 包成 `Function` → 落在**类型列**并与真实类型列对齐，输出**已对齐** | **不改**（不是缺陷；改「整体一项」只会让逗号跑到最右，属风格取舍） |
| 6 | `DOUBLE/ENUM/SET/JSON/TIME/YEAR` | 官方判成 `Keyword`（不是 `Name.Builtin`） | **不改**（覆盖 = 改写官方条目，与 `dialects` 原则冲突），登记 |
| 7 | `LIMIT 10, 20` / ALTER 多子句 | 被逗号折行 / 后半段全挤一行 —— **Doris 同样如此**（勘测里 `mysql == doris : True` 的那条 ALTER 即证据） | **不修**（Doris/MySQL 共享缺口，另开阶段） |

**目标（本轮只做这一件）**：让 `mysql` 成为**行为真的不同**的方言，并修掉 1–5。声明形态沿用
S8-c 拆出来的字段（**不新增字段**）：

```python
mysql = Dialect(
    name="mysql",
    precedence_patches=True,          # MySQL 8 有窗口函数 → 需要 OVER ( 补丁
    extra_lexer_rules=(               # **只对本方言生效**，不套 Doris 的 DISTRIBUTED BY / BUILD 那套
        (r"ON\s+DUPLICATE\s+KEY\s+UPDATE\b", T.Keyword),
        (r"PARTITION\s+BY\b", T.Keyword),
    ),
    extra_keywords=(...11 个类型名...),
    extra_split_words=(...表选项锚点...),
)
```

**实现期的两处纠偏**（勘测时的判断有误，开工时按实测改正；已同步到 `§9.12.1`）：

1. 换行锚点是**对单个 token** 做正则匹配（`Token.match(ttype, values, regex=True)` 拿 values 里每条
   **整正则**去 `search` 一个 token 的 value）→ **`ENGINE\s*=` 这种跨 token 的写法永远匹配不上**
   （`engine` 与 `=` 是两个 token）。正确做法：锚点写**裸词**（`ENGINE` / `CHARSET` / `COLLATE` /
   `ROW_FORMAT` / `AUTO_INCREMENT`），跨词的 `DEFAULT CHARSET` 先用 `extra_lexer_rules` 合并成一个 token。
2. 裸 `COMMENT` 锚点**不会**拆散列级 `comment '主键'` —— 字段列表的列布局走
   `align._create_field_lines`（按逗号切段），`_split_kwds` 在那里根本不跑。实测 MySQL 建表的
   `comment '主键'` 稳在「注释列」。因此 `COMMENT` **不需要**收窄、也不必重复声明 ——
   `policy.split_words` 里已有一条**通用**锚点（不能动它）。

**验收（门槛数字）**：
- 原 **215 项一项不变**（默认方言仍 `doris`；MySQL 构造在既有 fixture 里 grep 零命中）；
- `dialect="mysql"`：①建表类型列与字段名不粘连（列对齐正确）；②`)` 之后每个表选项各占一行；
  ③`on duplicate key update` 不被切断、`b = values(b)` 不被拆行；
- **与方言无关**（结构性 guard，`doris` / `None` 同时受益）：④`select straight_join …` 的字段仍与
  `select` 同行；
- `dialect=None`：①②③**都不生效** → 开关真起作用；
- `.venv\Scripts\python.exe -m pytest -q` → 215 + 新增（3 个 fixture × 5 门禁 + 4 条断言 = 19）。

**风险 / 雷区**：
- 换行锚点是**整 token 匹配**（见上「纠偏 1」）—— 新锚点写完必须**实跑**确认真的生效，别只写进声明；
- `_split_kwds` 的结构性 guard 是**通用**改动（`policy` 词表一个字没改）→ 必须跑全量门禁确认零回归；
- `extra_split_words` 会被 `grouping._CLAUSE_WORDS` 取并集（分组形状与方言无关）→ 新锚点会
  **同时**影响分组判定，别只测换行；
- `mysql` 一旦 `precedence_patches=True`，`over (` 行为与 `doris` 一致，需确认既有 fixture 无回归。

**回退方式**：`git revert <本阶段提交>`（`dialects.py` / 可能 `policy.py` / `grouping.py` 文本改动
+ 新增 topic/fixture/断言；纯文本、无不可逆动作）。

#### 9.12.1 S8-d 已收（2026-09-13）

**改动**（4 个文件 + 1 个新 topic；`policy.py` / `grouping.py` **一个字没动**）：

| 文件 | 改动 |
|---|---|
| `dialects.py` | 声明 `mysql`：`precedence_patches=True`（MySQL 8 窗口函数的 `OVER (`）+ `extra_lexer_rules`（`ON DUPLICATE KEY UPDATE`、`DEFAULT CHARSET`、`PARTITION BY` 三个多词合并）+ `extra_keywords`（`_MYSQL_TYPE_NAMES` 11 个）+ `extra_split_words`（`_MYSQL_SPLIT_WORDS` 7 个表选项锚点） |
| `passes/layout.py` | 新增 `_is_expression_anchor`，在 `_split_kwds` 里跳过「落在表达式内部」的锚点词（紧跟 `SELECT` / 紧跟 `=`）—— **通用**规则，不看输入空白 |
| `tests/` | 新增 `cases/mysql/sqltest0_s01.sql`（建表：类型名 + 表选项）、`sqltest1_s01.sql`（upsert）、`sqltest2_s01.sql`（`straight_join`）+ `TOPIC_META["mysql"]` + `test_sqlfmt_dialect.py` 4 条断言 |

**补齐的 11 个类型名**：`BOOL DATETIME LONGBLOB LONGTEXT MEDIUMBLOB MEDIUMINT MEDIUMTEXT
TINYBLOB TINYTEXT VARBINARY ZEROFILL`。`DOUBLE` / `ENUM` / `SET` / `JSON` / `TIME` / `YEAR`
官方是 `Keyword` → **不改写官方条目**，登记（同 §9.10.1 的 `JSON`/`MAP`）。

**效果（证据）**：

```text
类型名   mysql: content    mediumtext,          generic: content mediumtext        ,
表选项   mysql: )  ⏎ engine = innodb ⏎ auto_increment = 1 ⏎ default charset = utf8mb4
         generic: ) engine = innodb default ⏎ charset = utf8mb4     ← 换行是 wrap_after 撞的
upsert   mysql: on duplicate key update b = values(b);
         generic: on duplicate key ⏎ update b = values(b);
straight_join（通用 guard，doris/None 同样受益）:
         select straight_join a.id  ,        ← 修前是 select ⏎ straight_join a.id  ,
                      a.name
```

**验收**：`.venv\Scripts\python.exe -m pytest -q` → **`234 passed`（0 failed / 0 xfailed）**。

- 原 215 项一项没动；新增 19 项 = 3 个 fixture × 5 门禁（输出回归 1 + 幂等 2 + 收敛 1 +
  case-integrity 1）+ `test_sqlfmt_dialect.py` 4 条；
- `dialect=None` 下类型名 / 表选项 / upsert 三处**都不生效** → 开关真起作用；
- 冒烟（14 条 MySQL 构造：反引号、窗口函数、CTE、`insert … set`、`replace into`、`limit/offset`、
  `group by`/`having`、`left join`、多语句）与 `dialect=None` **逐条相同**（唯一 DIFF 是表选项，
  即本轮目标）。

**残留 / 下一步**：

- ✅ **`default null` 的列序**（已由 **S11** 收，见 §9.13）：`dept_id int(11) default null` 里 `default`
  排在 `null` 前，而 `align._create_field_lines` 的列序假设是「约束 → default」。
  属 `align.py` 的**通用**列序假设（Doris/Postgres 同受影响）。
- `LIMIT m, n` 被逗号折行、ALTER 多子句不换行：**Doris/MySQL 共享缺口**（同上）。
- Doris 的 `DUPLICATE` 锚点会在 MySQL 的 `on duplicate key update` 里误触发（跨方言组合；
  单独用 `dialect=mysql` 无此问题）。
- **方言路线（S8-a → S8-d）至此全部走完**：Doris/SelectDB（最优先）、MySQL 已适配；
  Oracle / SQL Server 按用户口径**暂缓**（SQL Server 已完成并保留）。

**回退方式**：`git revert <本阶段提交>`（4 处文本改动 + 新增 topic/fixture/断言；纯文本、无不可逆动作）。

---

### 9.13 S11 执行卡 + 已收（2026-09-13）：DDL 字段列序 —— `DEFAULT` 之后的值不是约束

**背景 / 靶子**：`§9.12.1` 残留第 1 条。MySQL 导出的建表几乎每个可空列都写 `DEFAULT NULL`，
即「**默认值 → 约束**」的**反序**形态（本项目既有 fixture 全是正序，所以一直没暴露）：

```sql
create table t (dept_id int(11) default null, name varchar(10) not null default 'x' comment '姓名');
```

```text
修前：
create table t (
       dept_id int(11) default null                            ,
       name    varchar(10)     not null default 'x' comment 'c'
);
```

**根因（实测 dump `_create_field_lines` 的 `field_lines` 得出）**：该方法按**固定列序**逐列查找
（名称 → 类型 → 约束 → `DEFAULT` → `COMMENT`），每列都从上一列的命中位置**向后**找。于是：

| 字段 | col2（约束） | col3（`DEFAULT`） |
|---|---|---|
| `dept_id int(11) default null` | **`null`** ← 越过了 `default`，把默认值当约束 | （空） |
| `name varchar(10) not null default 'x' comment 'c'` | `not null` | `default` |

`null` 被当成约束列内容后，该行约束列的 offset 落到很右边 → `_create_column_target` 的
`max_offset` 被抬高 → **整块字段（含其它行）的列基准连带错乱**（元规则一：列对齐错乱先怀疑「归类/分组」）。

**改动**（`sqlfmt_ext/passes/align.py::_create_field_lines`，一处；只写 `Whitespace`，符合 C5）：
字段内**先定位 `DEFAULT`**，把**约束列**的查找范围（`token_next_by` 的 `end`）收窄到 `default_idx`；
`DEFAULT` 自身与注释列仍按原范围查找。与方言无关，`doris` / `mysql` / 通用路径同时受益。

**证据**：修后 `field_lines` 归位（col2 空、col3 `default`），输出为：

```text
create table t (
       dept_id    int(11)                  default null                                ,
       name       varchar(10)     not null default 'x'               comment '姓名'    ,
       amount     decimal(10, 2)           default 0                                   ,
       flag       tinyint(1)      null                                                 ,
       created_at datetime        not null default current_timestamp comment '创建时间'
);
```

- `dialect="doris"` 与 `dialect="mysql"` 输出**逐字节相同**；
- 正序形态（`not null default 0`、`default '0' comment …`）输出**未变** —— `ddl/sqltest0_s01`、
  `ddl/sqltest0_s02`、`mysql/sqltest0_s01` 原样通过；
- 「约束列空、default 非空」的行会把 `default` 对齐到 default 列（即补一段空白），
  这与 `_align_create_columns` docstring 里 `created_at TIMESTAMP … DEFAULT CURRENT_TIMESTAMP`
  的既有口径**同形**，不是新引入的形态。

**验收**：`.venv\Scripts\python.exe -m pytest -q` → **`239 passed`（0 failed / 0 xfailed）**。
原 234 项一项没动；新增 5 项 = `tests/fixtures/cases/ddl/sqltest0_s07.sql`（**实跑输出定稿**，
沿用 S7-d 做法）+ `sqltest0_s07.input.sql`（单行原始 DDL）这一用例进四个门禁
（输出回归 / 幂等 ×2 / 收敛）+ `case-integrity` 1。

**已知边界（登记，不在本轮修）**：判据是「约束列查找**止于** `DEFAULT`」→ 写在 `DEFAULT`
**之后**的列级约束词（`id int default 0 primary key`）不再进约束列。常见形态不受影响
（`not null` 在 `default` 前；主键多为表级 `primary key (id)`）。

**残留 / 下一步**：见 §9 头部「下一步开工点」（`LIMIT m, n` 折行 / ALTER 多子句、官方 `Keyword` 类型名）。

**回退方式**：`git revert <本阶段提交>`（`align.py` 一处 + 新增 fixture 与 `.input.sql`；纯文本、无不可逆动作）。
