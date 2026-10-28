# PLAN — sqlfmt_ext 计划大纲

> **本目录是计划的唯一真身**（原根目录 `PLAN.md` 于 2026-09-13 拆分到此）。
> 定位：官方 `sqlparse` 之上的小侵入**外挂层**（`sqlfmt_ext/`，不改官方源码）。
> **唯一目的：格式化结果更美观、符合个人习惯** —— 外挂层 / 收敛性 / 幂等性都是手段。
>
> 阶段推进协议（开工四步 / 阶段内铁律 / 收工六步 / 汇报格式）在
> `.claude/rules/stage-protocol-阶段推进协议.md`；项目常驻指令在根 `AGENTS.md`。

## 文件分工（同一信息只存一处，其余写引用）

| 文件 | 内容 | 读取时机 |
|---|---|---|
| `PLAN.md`（本文件） | 目标 / 非目标 / 硬约束 §1、架构 §2、测试策略 §6、风险与回退 §7 | 需要「为什么这么设计」时 |
| `status.md` | 阶段状态与门槛 §3（**门槛数字唯一真身**）、四类门禁、命令 | 开工第 4 步；收工刷新 |
| `stages.md` | **断点卡**（当前位置 / 下一步开工点 / 已知边界）+ 各阶段卡 §9.x | 开工第 1 步；每阶段收工刷新 |
| `diffs.md` | 上游语义差异 U1–U17 §3.4、布局/对齐规则表 §4、补偿落点与时序 | 排查差异、改 `sqlfmt_ext/` 时 |
| `history.md` | 归档：迁移期（S0–S7）记录与变更记录 | 追溯历史决策（一般读不到） |

**章号约定**：各文件**沿用原 `PLAN.md` 的章号** —— §1/§2/§6/§7 在本文件，§3 在 `status.md`
（其中 §3.4 在 `diffs.md`）、§4 在 `diffs.md`，§9.x 在 `stages.md`、§9.3/§9.4 在 `history.md`。
因此**代码注释与技能里的 `PLAN §9.x` 等引用仍可直接导航**（跨文件时按章节号查本表）。

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
| C1 | 不修改、不复制 `sqlparse` 源码；官方包保持 pristine，只作依赖 | 官方更新可低成本合并 |
| C2 | 不 monkey-patch 官方函数；需要改行为的 filter 用「子类化 + 换装实例」 | 改动可审计、可撤销 |
| C3 | 不复制官方 `build_filter_stack` 装配逻辑 | 官方新增/调整 filter 顺序能自动继承 |
| C4 | 不使用「strip 阶段保留换行」的魔改；**输出不得依赖输入空白** | 旧擦除层的根因 |
| C5 | pass 只允许改写 `Whitespace` token；不得改 `ttype` / 顺序 / 删除非空白 token | 保证骨架与对齐职责分离 |
| C6 | 工具链唯一 **uv**（开发 `uv sync` / 构建 `uv build` / 部署 `uv tool install`）：不回落 pip、不往 py 主解释器装；唯一声明例外是 `--with-deps` 的 `pip download` | 环境可复现（`uv.lock` + `.python-version`）；「本机跑的是哪份代码」不再依赖某个解释器的状态 |

> 违反 C4 / C5 的方案**直接否掉**，哪怕它能让当前用例通过。
> C6 的唯一声明例外登记在 `status.md` §3.5（`uv pip` 无 `download` 子命令，离线 ZIP 无 uv 等价物）。

---

## 2. 架构

### 2.1 管线（落地形态）

```
sql
 → DialectLexer（官方 Lexer 子类，追加方言分词补丁）  （本项目）
 → StatementSplitter / grouping / 其余 preprocess      （官方 + 本项目补偿）
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

**核心洞察**：官方 strip 之后 token 流里没有任何原始换行，因此「换行骨架」完全由
官方 filter + 本项目 `LayoutPass` 决定，本项目只做**增量修饰**。旧实现之所以需要
一整套擦除层（`_remove_prev_newline` / `_collapse_newline(s)` / `_normalize_newlines` /
`_pull_inline` / `_prev_non_whitespace`），唯一原因是本地改写了 strip 让换行残留；
新架构下这类函数**结构性不存在**，收敛性从「需要维护」变成「不可能违反」。

### 2.2 分层职责

| 文件 | 职责 | 允许依赖 |
|---|---|---|
| `sqlfmt_ext/options.py` | 默认选项 + 扩展项校验，转交官方 `validate_options` | 官方 |
| `sqlfmt_ext/policy.py` | **通用**格式化口径：换行锚点关键字（`split_words`/`join_words`）+ 通用分词补丁表 | 官方 |
| `sqlfmt_ext/dialects.py` | 方言**唯一真身**：分词层 / 布局层 / 切分层声明 | 官方 |
| `sqlfmt_ext/lexer.py` | `DialectLexer`：官方 `Lexer` 子类，初始化后追加方言补丁 | 官方 |
| `sqlfmt_ext/stack.py` | 装配：复用官方 `build_filter_stack`，注入 lexer、换装 operators filter、摘换行 filter、方言批切分 | 官方 |
| `sqlfmt_ext/grouping.py` | 官方分组**前/后**的补偿（11 处，见 §4） | 官方 |
| `sqlfmt_ext/filters/` | 官方 filter 的**子类**（唯一允许替换官方行为的地方） | 官方 |
| `sqlfmt_ext/whitespace.py` | 空白段合并（U11，供 `filters/whitespace.py` 在官方 strip 前调用） | 官方 |
| `sqlfmt_ext/passes/layout.py` | 断行骨架 + 缩进宽度（唯一换行决策处） | 官方 |
| `sqlfmt_ext/passes/align.py` | 同行空白宽度（列对齐规则集，mixin） | 官方 |
| `sqlfmt_ext/cli.py` | CLI 入口：`sqlfmt_ext` 命令与 `python -m sqlfmt_ext.cli` 共用同一份 main | `sqlfmt_ext` |

---

## 6. 测试策略

| 套件 | 文件 | 断言 | 门禁 |
|---|---|---|---|
| 用例完整性 | `tests/test_sqlfmt_case_integrity.py` | fixture 与 `TOPIC_META` / `FILE_OPTIONS` 一致 | 必须全绿 |
| 输出回归 | `tests/test_sqlfmt_output_regression.py` | `format(input) == expected` | 必须全绿 |
| 幂等性 | `tests/test_sqlfmt_idempotency.py` | `format(format(x)) == format(x)`，且 input→input 也幂等 | 必须全绿 |
| 收敛性 | `tests/test_sqlfmt_convergence.py` | 把 canonical 的 token 间隔空白**确定性压平**后，输出仍等于 canonical | `KNOWN_DIVERGENT` 已清空，别新增无原因的 xfail |

**只有一套测试** `tests/`（S7 删 fork 后迁移期的 `tests_migration/` 已并入）；
门槛命令与当前数字见 `status.md` §3。

**方法论约束**（踩过的坑，写进约定）：
- 比对「非空白 token 序列」是**无效指标**（格式化不重排 token，恒等）。
- 必须比「行内容（去缩进、去标点前空格）」才能分离换行位置差异。
- 本地逗号前有对齐空格（`a ,` vs `a,`），统计前必须归一化。
- `xfail(strict=True)` 是进度条机制：修好一个就 XPASS 失败，强制清理清单。

**用例扩充**：从现有用例中挑几条做**非破坏性空白打乱**，作为收敛性的强测试
（工具：`tests/fixtures/whitespace.py::flatten_whitespace`）。

---

## 7. 风险与回退

| 风险 | 影响 | 对策 |
|---|---|---|
| 官方骨架输出与旧 fork 差异大（已发生） | 迁移期工作量超预期 | 差异已归因为有限几组规则（`diffs.md` §4），非 N 个独立 bug |
| CJK 对齐宽度口径不一致（字节宽 vs 显示宽） | 对齐列宽偏差 | 固化现有口径（沿用 gbk 字节长）；如要改显示宽，先开新阶段卡 |
| 补偿层与官方升级耦合 | 官方改分组形状会波及补偿 | C1–C3 保证官方 pristine；升级后跑全量门禁 + 真实语料巡检 |
| 「凭感觉找缺口」 | 修了其实不是缺口的东西 | **先巡检**：拿真实语料跑一遍并与既有 fixture 口径对照，确认是新缺口再写卡 |
| 不可逆动作（删 fork、重定 fixture） | 难以回退 | 一阶段一提交、可单独 `git revert`；含不可逆动作必须写「回退方式」 |
| 工具链 / 依赖不可复现（换机器或换源后装不起来） | 「本机能跑、别处不能」 | `uv.lock` 与 `.python-version` 入库；C6 唯一工具链；换源后重跑 `uv lock`（见 `status.md` §3.5） |
| 部署后自检假绿（cwd 在仓库内 → 命中源码） | 误判「装好了」 | 自检一律在**项目目录之外**跑（`conftest.py` 与 `stages.md` §9.6 记过这个坑） |
