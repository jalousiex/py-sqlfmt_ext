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

> **当前进度（2026-09-12 更新）**：`pytest tests_migration/ -q` → **`14 passed, 17 xfailed`**。
> 空白归一化（U11）一次性把 8 个用例（`aggregate/s01`、`cte/s01`、`ddl/s05`、
> `dml/s03`、`dml/s05`、`dml/s07`、`dml/s08`、`window/s02`）从「待实现规则」变成逐字节
> 一致——它们的首处差异本来就是该处 ±1 列宽，不是换行骨架差异（见 §3.5、§9.3）。

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
| 对拍进度条（新外挂） | `.venv\Scripts\python.exe -m pytest tests_migration/ -q` | `14 passed, 17 xfailed` |
| 诊断报告 | `.venv\Scripts\python.exe _tmp_gap.py` | 逐用例首处差异 + 异常容错 |

已复现（14）：`debug/sqldebug_s02`、`case/sqltest4_s03`（CASE 首个 WHEN）、
`generic/sqltest8_s01`（`select * from` 折叠）、`ddl/sqltest0_s04`（`ON COMMIT`）、
`comma/sqltest7_s01`（分组口径）、`aggregate/sqltest5_s01`/`s02`、`cte/sqltest2_s01`、
`ddl/sqltest0_s05`、`dml/sqltest1_s03`/`s05`/`s07`/`s08`、`window/sqltest6_s02`。

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
**L1 已清零**：剩下的注释类用例（`cte/s02`、`nested/s01 s02`、`window/s01 s03`）
首处差异已全部退化为空白宽度，即注释断行本身已经对了。

```
S6 对齐 (7): cte/s02 | nested/s01 | nested/s02 | window/s01 | window/s03
             ddl/s02 | ddl/s06
S4 字段列表 (5): ddl/s01 | ddl/s03 | dml/s01 | dml/s02 | dml/s04
S5 (3): case/s01（CASE 内 as 列对齐 + 折行）| case/s03（首个 when 独占行）
        | dml/s06（L4 多 LATERAL VIEW）

合计 7+5+3 = 15，与当前 15 个 xfailed 一一对应
```

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
| **S4** | `LayoutPass` L2 括号字段列表展开（残留疑为分组口径差异，待核） | +5 | 16 / 15 | ⏳ 待做 |
| **S5** | `LayoutPass` L4 多 LATERAL VIEW + L5 CASE 折行 | +3 | 19 / 12 | ⏳ 待做 |
| **S6** | `AlignPass` 列对齐收尾（注释列 / 末尾逗号 / `as` 列） | +7 | **31 / 0** | ⏳ 待做 |
| **S7** | 收敛 + 幂等 + 入口切换 + 删 fork + 改 AGENTS.md/README | 新实现通过全部 4 套测试 | — | ⏳ 待做 |
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

---

## 9. 断点续做（下一次会话从这里开始）

> 落盘时间：2026-09-12（第二轮），U11 已完成，**对拍 14/17**，S3 的 L1 结构性规则待写。

### 9.1 复现当前状态

```powershell
.venv\Scripts\python.exe -m pytest tests/ -q            # 170 passed, 6 xfailed（旧 fork，必须保持）
.venv\Scripts\python.exe -m pytest tests_migration/ -q  # 14 passed, 17 xfailed（新外挂，进度条）
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

| 段 | 目标 | 涉及用例（当前 15 xfailed） | 主读文件 | 状态 |
|---|---|---|---|---|
| S4 | L2 括号字段列表展开（**先核分组口径**） | `ddl/s01 s03`、`dml/s01 s02 s04` | `passes/layout.py::_process_parenthesis/_process_identifierlist` + `grouping.py` | ⏳ 下一段 |
| S5 | L4 多 `LATERAL VIEW` 各自分行；L5 `case` 后首个 `when` + CASE 折行 | `dml/s06`、`case/s03`、`case/s01` | `_is_lateral_view_list`、`_process_case` | ⏳ |
| S6 | 列对齐收尾（末尾逗号列 / `as` 列 / 注释列 / `from` 缩进） | `cte/s02`、`nested/s01 s02`、`window/s01 s03`、`ddl/s02 s06` | `passes/align.py` | ⏳ |
| S7 | 收敛 + 幂等 + 入口切换 + 删 fork + 改 AGENTS/README + 删 `_tmp_*` | — | — | ⏳ |

**分段推进的操作要点（省上下文的做法）**
1. **先分类再动手**：`python _tmp_check.py` 只看摘要（每例首 2 处差异 + 「是否只是空白宽度」），
   一条命令拿到全部 15 个用例的格局，再决定这段做哪一类。
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

**S4 起点（交接信息）**：剩下 3 类，`_tmp_check.py` 摘要直接给出：
S6 对齐 7 个、S4 字段列表 5 个、S5 折行 3 个。注释类（L1）已清零，不用再碰 `_process_comment`；
`case/s01` 的 21 处差异里夹着 CASE 折行，归 S5 一并看。

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
