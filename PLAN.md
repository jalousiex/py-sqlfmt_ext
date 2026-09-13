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
| 主套件（旧 fork） | `.venv\Scripts\python.exe -m pytest tests/ -q` | `170 passed, 6 xfailed` |
| 对拍进度条（新外挂） | `.venv\Scripts\python.exe -m pytest tests_migration/ -q` | `29 passed, 2 xfailed` + 1 有意偏离 |
| 诊断报告 | `.venv\Scripts\python.exe _tmp_gap.py` | 逐用例首处差异 + 异常容错 |

已复现 28：以 §4 的规则→用例映射与 `tests_migration/test_parity.KNOWN_DIFF` 为准
（后者只剩 3 条未复现条目，且逐条带根因；另有 1 条**有意偏离**登记在
`test_parity.DEVIATIONS`，是断言项而非待做项，见 §4。不再手工维护重复名单）。

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

## 4. 规则总表（全部待实现项）

旧 fork 参考位置：`sqlparse/filters/aligned_indent.py`（下称 `ai.py`）。
**注意**：参考的是「期望语义」，不是「实现方式」——旧实现里与擦除相关的部分一律不移植。

### LayoutPass（只改换行位置）

| # | 规则 | 目标用例 | 旧参考 |
|---|---|---|---|
| L1 | **注释强制换行**：单行 `--`、块 `/* */`、`/*-*/` 强制换行标记，前后各自成行；连续注释按原分组保留换行 | 12 个 | `ai.py::_process_comment`(497)、`_take_comments_before`(172) |
| L2 | **括号内字段列表展开**：CREATE / ALTER / INSERT 的 `(cols)` 逐列换行 | 7 个 | `ai.py::_process_parenthesis`(204) |
| L3 | **语句 / CTE 换行**：`as with ... as (` 中 `as` 后换行 | 3 个 | `ai.py::_split_statements`(899)、`_process_statement`(197) |
| L4 | **多 LATERAL VIEW 各自分行** | 1 个 | `ai.py::_is_lateral_view_list`(160)、`_split_kwds`(812) |
| L5 | **CASE 首个 WHEN 独占一行**（⚠️ 旧实现在 `has_nl and direct_after_case` 上判定，即**依赖输入换行**；官方 strip 之下没有该换行，需重新定义为结构性规则，或在 S7 重定基线） | 1 个 | `ai.py::_process_case`(427) |
| L6 | **`select * from` 折叠同行** | 1 个 | `ai.py::_is_simple_select_star`(870) |
| L7 | **`ON COMMIT` 刻意分行**（白名单） | 1 个 | `ai.py::_normalize_newlines`(87) 白名单 |

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
| **S8** | 方言层补完（Doris/SelectDB）+ SQL Server 适配 | 方言用例 | — | ⏳ 待做，可并行 |

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

### S7 方言路线

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

> 落盘时间：2026-09-13，**S1–S7 全部完成**（S7-a~e 五个提交，见 §9.4 末尾小结），
> **门槛 `pytest -q` → `172 passed, 4 xfailed`（0 failed）**，无遗留偏离清单。
>
> **本节是「阶段断点卡」**：每阶段的开工点与残留都记在这里。配合
> [AGENTS.md](AGENTS.md) 的「**阶段推进协议**」（开工四步 / 收工六步 / 汇报格式）使用。
> 下一个可开工的阶段见 §3 状态表：**S8（方言补完）**，以及 §4 末尾那条未系统化项
> （`--` / `/*-*/` 的**结构性强制断行**规则 —— 收敛门禁剩下的 4 个 xfail 正属这一族）。

### 9.1 复现当前状态

```powershell
.venv\Scripts\python.exe -m pytest tests/ -q            # 170 passed, 6 xfailed（旧 fork，必须保持）
.venv\Scripts\python.exe -m pytest tests_migration/ -q  # 31 passed（新外挂，KNOWN_DIFF 已清空；另有 1 条有意偏离是断言项）
.venv\Scripts\python.exe _tmp_check.py                  # 逐用例精确 diff（当前唯一主力诊断）
```

两个套件**不要在同一次 pytest 会话里跑**（进程级 `sys.path` 副作用，见 §2.3）。

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

### 9.3 分段任务卡（一次只做一段；每段结束跑两套测试 + 提交）

> 分段原则：**一段 = 一条规则 / 一个根因**，上下文只读该段需要的文件；
> 需要跨文件探索的先用 `code-explorer` 子代理，把结论（不是文件内容）带回主线。
> 每段收尾动作固定：`pytest tests/ -q`（须 170 passed, 6 xfailed）→
> `pytest tests_migration/ -q` → 更新 `test_parity.KNOWN_DIFF` → 更新本文件进度 → commit。

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
| S7 | 收敛 + 幂等 + 入口切换 + 删 fork + 改 AGENTS/README + 删 `_tmp_*` | — | — | ⏳ |

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

### 9.4 诊断工具（仓库根 `_tmp_*.py`，已在 `.gitignore`，S7 统一删除）

| 脚本 | 用途 |
|---|---|
| `_tmp_check.py` | **主力**：逐用例打印期望/实际首处差异（repr 精确到空白），可带用例名过滤 |
| `_tmp_cmp.py --fork/--new "<sql>"` | 同一片段两侧输出对照；`\n` 表示换行；`@相对路径` 直接喂 fixture 文件；两侧选项已与主套件口径对齐 |
| `_tmp_align_dbg.py --fork/--new` | 打印 `_identifier_layouts` 汇总值（as_offset 列表 / max_as_offset） |
| `_tmp_align_trace.py --fork/--new` | 打印 `_apply_identifier_layout`/`_set_adjacent_ws` 入参与被替换的空白 token |
| `_tmp_ws_when.py` | 在 LayoutPass 前后审计「value 为空的空白 token」数量（U11 后应接近 0） |
| `_tmp_forkidx.py "<sql>"` | 打印 fork 树（带下标）+ IdentifierList 成组区间 |
| `_tmp_count.py --fork/--new` | 数某一列（如 `as`）的落位 |

**排查踩过的坑**：
- `FilterStack.run(sql)` 返回**生成器**，不消费等于没跑 → 自建探针时必须
  `list(stack.run(sql))`，否则「探针没打印」会被误判成「没有该现象」。
- 官方 `Lexer.get_tokens()` 产出的是 `(ttype, value)` **元组**，不是 Token 对象。
- fork 与新实现要用**两次独立进程**跑（同进程只能加载一个 `sqlparse`）。
- 对比 fork 输出时**选项必须与主套件一致**（`sqlfmt.DEFAULT_OPTIONS`）：
  多传一个 `comma_align=True` 就会凭空多出空行，很容易误判成「新实现缺规则」。
- **规则→用例映射要用最小化输入复核**（见 §4 末尾「首版映射」教训）。

### 9.5 不要做的事

- 不要改 `sqlparse/`（旧 fork）——迁移期它是 oracle，S7 才删。
- 不要用「改 ttype / 删非空白 token / 重排」的手法对齐（C5）。
- 不要把迁移期的 `sys.path` 调整写进 `tests_migration/` 之外的 conftest。
- 不要 commit 之前跑混两个套件的 pytest 会话。
