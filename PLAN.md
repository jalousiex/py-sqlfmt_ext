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
| 对拍进度条（新外挂） | `.venv\Scripts\python.exe -m pytest tests_migration/ -q` | `4 passed, 27 xfailed` |
| 诊断报告 | `.venv\Scripts\python.exe _tmp_gap.py` | 逐用例首处差异 + 异常容错 |

已复现：`debug/sqldebug_s02`、`case/sqltest4_s03`（CASE 首个 WHEN）、
`generic/sqltest8_s01`（`select * from` 折叠）、`ddl/sqltest0_s04`（`ON COMMIT`）。

### 3.4 上游 0.6.0 与旧 fork 的语义差异清单（迁移的真实成本）

用脚本逐项对比得到的结论：旧 fork 不是「官方 + 小补丁」，而是 **sqlparse 0.5.x
+ 大量改写**。把基线换成官方 0.6.0 后，以下差异会直接影响输出，已确认的有：

| # | 位置 | 差异 | 处置 |
|---|---|---|---|
| U1 | 官方 `keywords.SQL_REGEX` | 缺 Doris 条目（`ON COMMIT`/`REFRESH`/`DISTRIBUTED BY`/`LATERAL VIEW` 等） | ✅ 已在 `policy.py` 以追加方式补上 |
| U2 | 官方 `lexer.Lexer` | 模块级单例，`FilterStack.run` 硬引用 | ✅ `DialectLexer` 子类 + `FilterStack.run` 覆写（只改 lexer 来源） |
| U3 | 官方 `TokenList.token_next_by` | 没有 `_reverse` 参数 | ✅ 用 `_token_prev_by` 等价实现 |
| U4 | 官方 `IdentifierList.get_identifiers` | 不过滤注释（fork 过滤） | ✅ 在 `_process_identifierlist` 里过滤 |
| U5 | 官方 `Case.get_cases` | fork 增加了 `--` 注释占位逻辑 | ⏳ 未处理，影响 CASE 内注释 |
| U6 | 官方 `Where.M_CLOSE` / `TypedLiteral.M_CLOSE` | fork 移除了 `GROUP BY`/`ORDER BY`/`LIMIT`/`UNION`，并给数字补 `M_CLOSE` | ⏳ 未处理，影响 WHERE 分组边界 |
| U7 | 官方 `NameAliasMixin.get_real_name` | fork 取**第一个**点号，官方取最后一个 | ⏳ 影响 `a.b.c` 别名 |
| U8 | 官方 `statement_splitter` / `lexer.find_delimited_spans` | 0.6.0 是新实现（嵌套块、美元引号） | ✅ 对现有 fixture 无影响 |
| U9 | 官方 `grouping.valid_next` | fork 允许关键字作字段名 | ⏳ 未处理，暂未观察到影响 |

**结论**：U5–U7 是「官方内部语义」差异，无法通过外挂层参数解决，只能
（a）在本项目里做等价补偿，或（b）接受少量输出差异。
每条都要单独评估，属于 S2–S5 的隐藏成本。

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
| L5 | **CASE 首个 WHEN 独占一行** | 1 个 | `ai.py::_process_case`(427) |
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

### 规则 → 用例映射

```
L1 (12): case/s01 s02 | comma/s01 s02 | cte/s01 s02 | dml/s01 s05
         nested/s01 s02 | window/s01 s03
L2  (7): ddl/s01 s02 s03 s06 | dml/s02 s03 s04
L3  (1): ddl/s05                ← 另需补齐 dml/s02、s03 里 CTE 的部分（与 L2 叠加）
L4  (1): dml/s06
L5  (1): case/s03
L6  (1): generic/s01
L7  (1): ddl/s04
A1  (6): aggregate/s01 s02 | debug/sqldebug_s01 | dml/s07 s08 | window/s02

合计 12+7+1+1+1+1+1+6 = 30，与 baseline 的 30 个 xfailed 一一对应（无遗漏、无重复）
```

---

## 5. 分步实施

每个步骤的验收统一为两条：
- **净效果**：对拍套件中 `xfailed` 数量下降到该步骤的目标值；
- **不回归**：主套件保持 `170 passed, 6 xfailed`。

| 步骤 | 内容 | 目标 | 对拍 | 状态 |
|---|---|---|---|---|
| **S0** | 计划落地 + 骨架 + 对拍进度条 | — | 1 / 30 | ✅ 完成 |
| **S1** | 把布局引擎移植到官方 0.6.0 之上：方言 lexer、分词补丁、`LayoutPass`（断行+对齐规则集）、摘掉官方换行 filter | 骨架跑通且不崩 | **4 / 27** | ✅ 完成 |
| **S2** | 上游语义差异补偿 U5–U7（`Case.get_cases` 注释占位、`Where.M_CLOSE`、`get_real_name`） | — | — | ⏳ 待做，**建议先做**（影响面最大） |
| **S3** | `LayoutPass` L1 注释强制换行（确定性规则：`--` 与 `/*-*/` 强制断行） | +12 | 16 / 15 | ⏳ 待做（最大单项） |
| **S4** | `LayoutPass` L2 括号字段列表展开 | +7 | 23 / 8 | ⏳ 待做 |
| **S5** | `LayoutPass` L3 语句/CTE 换行 + L4 多 LATERAL VIEW | +2 | 25 / 6 | ⏳ 待做 |
| **S6** | `AlignPass` A1–A3 列对齐（含 CJK 宽度口径） | +6 | **31 / 0** | ⏳ 待做 |
| **S7** | 收敛 + 幂等 + 入口切换 + 删 fork + 改 AGENTS.md/README | 新实现通过全部 4 套测试 | — | ⏳ 待做 |
| **S8** | 方言层补完（Doris/SelectDB）+ SQL Server 适配 | 方言用例 | — | ⏳ 待做，可并行 |

> 对拍列格式：`passed / xfailed`。
> **L1 的规则要从「依赖输入换行」改成「结构性判定」**：`/*-*/` 与 `--` 强制断行、
> 块注释 `/* */` 跟随原分组——这才是收敛性要求下的正确形态，也是旧实现做不到的。

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
| 对拍进度条 | `tests_migration/test_parity.py` | 新实现输出 == fixture 期望 | 迁移期 30 个 `xfail(strict=True)`，S5 结束清零 |

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
