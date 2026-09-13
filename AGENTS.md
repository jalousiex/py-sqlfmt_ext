# AGENTS.md — py-sqlfmt AI 指令

基于官方 `sqlparse` 的小侵入**外挂层**（不改官方源码），详细说明见 [README.md](README.md)。

> **重构已完成（S1–S7）**：唯一实现是 `sqlfmt_ext/`，跑在官方 `sqlparse 0.6.0` 之上；
> 曾 vendored 的旧 fork 已删除，`sqlparse` 现在是 pip 依赖（`>=0.6,<0.7`，见 `pyproject.toml`）。
> 差异清单（U1–U16）、每处补偿的落点与时序约束、迁移过程记录见 [PLAN.md](PLAN.md)。
>
> 验收门槛：`pytest tests/ -q` → **`172 passed, 4 xfailed`**（0 failed）。
> 那 4 个 xfail 是收敛门禁里**已登记**的「输出仍依赖输入空白」用例，每项都写清了原因。

## 阶段推进协议（常驻指令：每阶段开工 / 收工都照此执行）

本项目按**阶段**推进（S1…S8，权威清单见 [PLAN.md](PLAN.md) §3 状态表）。
长会话里上下文会被压缩，所以**不依赖记忆**：每阶段的输入、验收、落地都写在文件里，
按下面的清单「读 → 做 → 写」即可，任何一轮都能无损接手。

### 最初目的（防止阶段目标漂移）

> **唯一目的是「格式化结果更美观、符合个人习惯」**；另外三条都是手段：
> ② 能低成本合并官方更新 → 所以做成**外挂层**而不是 fork（硬约束 C1–C3）；
> ③ 收敛性：输出只取决于 token 流、与输入空白无关 → C4；
> ④ 幂等性：格式化两次结果一致 → C5（只改空白、不重排、不增删非空白 token）。
>
> **非目标**：不做 SQL 语义校验；不重排、不增删非空白 token。
>
> 任何阶段方案若违反 ②③④ 之一（典型：改官方 strip 让换行残留、按输入有无换行决定布局），
> **直接否掉** —— 不要因为它能让当前用例通过就接受。

### 开工：重新加载阶段性目标（四步，别省）

1. `PLAN.md` **§9 断点卡** → 找到「下一步开工点」，**本阶段只做这一件事**；
2. `MEMORY.md` → 长期事实（U 系列差异、口径决策、踩过的坑）；
3. 本文件 → 硬约束 C1–C5 + 元规则一~六；
4. `PLAN.md` **§3 状态表** → 各阶段 ✅/⏳ 与门槛数字；
   并跑一次门槛确认基线：`.venv\Scripts\python.exe -m pytest -q`（当前应为 `172 passed, 4 xfailed`）。

四者若互相矛盾，**以 §9 为准，并顺手把另外两处改对** —— 信息不一致本身就是缺陷。

### 阶段内规则

- 一次只推一个阶段；**阶段边界不可讨价还价**：发现需要新设计的大改（跨阶段），
  先把它写成 §9 里的一个新阶段（目标 + 验收），再开工，不要在本阶段里顺手展开。
- 验收只看门槛（`pytest -q` 的数字 + fixture 逐字节一致）；「看起来对了」不算结论。
- 诊断优先用**最小重现**（元规则二）与**关掉它做对照**（元规则六）。

### 收工：落地清单（六步，缺一不可）

1. 门槛跑绿（数字写进 §3 状态表）；
2. `PLAN.md §9` 刷新断点卡：本阶段结论、**下一步开工点**、已知残留（含「为什么不做」）；
3. `PLAN.md §3` 状态表：阶段标 ✅、填新门槛；
4. `MEMORY.md`：只沉淀**长期事实**（新口径 / 新约定 / 新坑），不留过程；
5. `.codebuddy/memory/<今天>.md`：追加当日记录（靶子 / 根因 / 证据 / 残留），供跨会话续做；
6. 提交：一个阶段 = 一个（或一组能一一 revert 的）提交；若含**不可逆动作**，提交信息必须写
   「不可逆 + 回退方式」；提交消息**不要带 ASCII 双引号或反引号**（PowerShell 会吞，导致提交静默不执行）。

### 汇报格式（固定）

`靶子 → 根因 → 改动 → 证据 → 验收（门槛数字）→ 残留 / 下一步`；只给结论与证据，不贴大段代码。

### 关键信息索引（谁说了算）

| 要查什么 | 看哪里 |
|---|---|
| 目标 / 非目标 / 硬约束 C1–C5 | 本节摘要 + `PLAN.md` §1 |
| 阶段状态与门槛 | `PLAN.md` §3 |
| 当前阶段目标 / 断点 / 下一步开工点 | `PLAN.md` §9 |
| 官方 0.6.0 与旧 fork 的语义差异（U1–U16）、补偿落点与**调用时序**约束 | `PLAN.md` §3.4 / §4、`MEMORY.md` |
| 长期口径决策、踩过的坑 | `MEMORY.md` |
| 代码地图与架构 | `README.md`「AI 指引」+ `PLAN.md` §2.2 |

## 架构

**唯一实现**：`sqlfmt_ext/`，跑在 `.venv` 的官方 `sqlparse 0.6.0` 之上。

```
sqlfmt.py → format_statements()
  → DialectLexer            # 官方词表 + Doris 分词补丁（policy.py）
  → StatementSplitter       # 按 ; 分割语句（官方）
  → grouping.group()        # 官方分组 + 本项目口径补偿（grouping.py）
  → StripWhitespaceFilter   # 官方 strip；之前先合并逐字符空白（whitespace.py）
  → LayoutPass              # 唯一换行/缩进决策处（passes/layout.py + passes/align.py）
```

**历史形态（S7 收口时已删除）**：仓库内曾 vendored 一份旧 fork 作行为 oracle，
它的入口是 `sqlfmt.py → sqlparse.format()`，核心是把 `AlignedIndentFilter` 改成
「深度优先遍历 + 关键字前换行缩进」。

## 硬约束（改代码前必读，详见 PLAN.md §1）

- **C1** 不改、不复制官方 `sqlparse` 源码（它只是 pip 依赖）
- **C2** 不 monkey-patch，只「子类化 + 换装实例」
- **C3** 不复制官方 `build_filter_stack` 的装配逻辑
- **C4** 不用「改官方 strip 让它保留换行」的魔改
- **C5** 各 pass 只允许改写 `Whitespace` token（不改 ttype、不重排、不删非空白 token）

**元规则一：列对齐 / 字段列表整体错乱时，先怀疑分组口径，再查 pass。**
（S6 段的 7 个「列对齐」用例里，5 个的真因是分组/分词：U15 尾逗号吞子句关键字、U16 缺 `DATETIME`、
U13 CREATE 早退、S6b 项内尾随空白。）

**元规则二：定性先写最小重现**（现写个临时脚本，见「诊断工具」；单行片段输入即可），别拿整条 fixture 下结论。

**元规则三（元规则二的边界）：孤立片段与真实 fixture 行为不一致时，以 `@fixture` 的两侧探针为准。**
「抽出来跑是好的」**不等于**实现正确——S6b 就栽在这里：同一个 select 列表抽出来跑完全正确，
真因（项内尾随空白抬高 `max_as_offset`）只有在 `_tmp_align_probe.py --fork/--new "@真实fixture"` 里才显形。
**两次对照都做，且必须用同一份输入。**

**元规则四：改对齐/换行算术前，先 diff 我方与 fork 的对应函数。**
逐行相同就别改算术——差异只可能在**入参**（offset / 列表项集合 / 分组形状）。
S6a 就是这样一步锁定的（`align.py` 三个函数与 fork 完全一致 → 直接去查 `field_lines`）。

**元规则五：同一根因的改动常常成对出现（分组侧 + 布局侧），改完必须跑全量对拍。**
S6b 的「注释前导空白整段搬出组」必须与「注释串延续改判同层兄弟」**同时**改，
单独改会各红一个用例（只改前者 → `cte/sqltest2_s02` 退回列 0；只改后者 → 无效）。
**别只看目标用例的绿，先看全量对拍有没有别的红。**

## 关键文件

| 文件 | 职责 |
|------|------|
| `sqlfmt.py` | 入口，`sqlfilefmt()` 拆分语句后逐条格式化，`.strip()` 后用 `\n\n` 拼接 |
| `sqlfmt_ext/passes/layout.py` | **核心**：`LayoutPass`，断行+缩进（唯一换行决策处），继承 `AlignMixin` |
| `sqlfmt_ext/passes/align.py` | `AlignMixin`：标识符列表 / DDL 字段 / 注释列对齐 |
| `sqlfmt_ext/grouping.py` | 官方分组前后的口径补偿（U 系列差异都记在 `MEMORY.md`） |
| `sqlfmt_ext/policy.py` | 换行锚点词、Doris 分词补丁、优先级补丁 |
| `sqlfmt_ext/lexer.py` · `sqlfmt_ext/stack.py` | `DialectLexer`；复用官方 `build_filter_stack` 后换装 |
| `sqlparse`（pip 依赖） | 官方 0.6.0，**不改其源码**；口径差异一律用 `sqlfmt_ext/` 的补偿实现 |

## 默认格式化参数

`keyword_case=lower`、`indent_width=4`、`reindent_aligned=True`、`wrap_after=30`、`use_space_around_operators=True`、`align_list=True`（扩展项）、`dialect="doris"`（扩展项）

定义在 `sqlfmt_ext/options.py`（`DEFAULT_OPTIONS` + `EXTENSION_DEFAULTS`）；`sqlfmt.py` 保留同名 `DEFAULT_OPTIONS` 供 CLI 使用。

## 测试约定

- 用例目录是 **`tests/`**（不是 `pytests/`）：`tests/fixtures/cases/<topic>/*.sql` — fixture 文件**即期望输出**，测试验证幂等性
- 新增用例：在对应 `cases/<topic>/` 下添加 `.sql` 文件，在 `tests/fixtures/sql_cases.py` 的 `TOPIC_META` 中注册 topic
- 需要非默认选项的用例：在 `FILE_OPTIONS` 中按文件名映射选项
- 唯一入口：`.venv\Scripts\python.exe -m pytest tests/ -q` — **必须保持 `172 passed, 4 xfailed`**（0 failed）
- `xfail(strict=True)` 的 4 处是**收敛门禁**里已登记的用例（输出仍依赖输入空白），每项都写清了原因；修好一项就删一项，不要新增「无原因」的 xfail
- 仓库根 `conftest.py` 会校验 `sqlparse.__file__` 来自 site-packages —— 防止再出现「仓库内 vendored 包遮蔽官方包」的老问题
- 筛选用例：`SQLFMT_CASE_TAGS=comma .venv\Scripts\python.exe -m pytest tests/ -v`

## 诊断工具

迁移期的 `_tmp_*.py` 探针脚本已在 S7 收口时**全部删除**（旧 fork 也没了，`--fork/--new` 双侧对照已无意义）。
需要时**现写一个临时脚本**放仓库根（`_tmp_*.py` 已在 `.gitignore`，用完删掉），推荐套路：

- 入口：`from sqlfmt_ext import format_statements`；要看中间态就 `stack.build_stack()` 自建 FilterStack 分步跑
- 看**树**：`from sqlparse import engine` + `sqlfmt_ext.grouping.group(stmt)` 后递归打印
  `type(token).__name__` 与 `token.value`（含 `@相对路径` 直接喂 fixture）
- 看**中间量**：分组之后 / layout 之后各 dump 一次。列对齐问题看**列表项集合**与
  `max_as_offset` / `max_alias_len`；DDL 看 `field_lines` 与每列 `max_offset`

**坑位（每条都是真踩过的）**
- `FilterStack.run(sql)` 返回**生成器**，不消费等于没跑。
- fork 与新实现必须**两次独立进程**跑（同进程只能加载一个 `sqlparse`）；fork 侧脚本要显式传 `align_list=True`。
- 比对不能只比「非空白 token 序列」（格式化不重排 token，恒等），要比「行内容」才能分离换行位置差异。
- **诊断脚本一次补齐两侧模式 + `@相对路径`**：少了就得来回跑好几轮（S6a/S6b 都是补完探针才一步定案）。
- **临时探针用运行时 patch 写进 `_tmp_*.py`，不要往源码里塞 `print`**；真塞了必须当轮删掉。
- **「关掉它做对照」是验证元凶的硬手段**：把可疑改动换成 no-op（或 `return None` 提前退出）再跑一次，
  现象若不变说明找错了地方（S4c/守卫边界就是这么被证伪/证实的）。

## 项目约定

- 低频参数不做 CLI 参数，优先用 `DEFAULT_OPTIONS` 模块级变量
- 不要自动创建 venv，复用现有 `.venv`
- 无风险只读命令改动后直接终端验证，不等确认
- 不修改工作区外文件