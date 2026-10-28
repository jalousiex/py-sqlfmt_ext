---
name: sqlfmt-parity
description: sqlfmt 对拍修复：维护「官方 sqlparse 0.6.0 + sqlfmt_ext/ 小侵入外挂层」的口径正确性，把每个格式化差异落成补偿或登记为已知发散。当需要排查格式化差异（列对齐 / 分组 / 分词 / 折行）、新增或调整补偿、推进 .claude/plan/stages.md 的某个阶段、核对门槛数字时使用。典型触发：pytest 出现 FAILED 或 XPASS、列对齐整体错乱、字段列表不展开、关键字没触发换行、DDL 字段列错位、注释换行不稳定、方言词表缺失。
---

# sqlfmt 对拍修复

## 用途

维护「官方 `sqlparse` 0.6.0 + `sqlfmt_ext/` 小侵入外挂层」这一实现的**口径正确性**：
官方包保持 pristine（pip 依赖），本项目所有差异一律用补偿层实现，行为由 `tests/` 的门禁钉住。

> **本技能不重复项目机制**：阶段如何推进（开工四步 / 阶段内规则 / 收工六步 / 汇报格式）、
> 硬约束、当前进度与断点，权威出处是 **`AGENTS.md`「阶段推进协议」** +
> **`.claude/plan/status.md` §3 状态表** + **`.claude/plan/stages.md` §9 断点卡** + **`MEMORY.md`**。
> 本技能只补充「怎么诊断、怎么改」这部分手法。

工作流是**诊断驱动**的：先证明根因（分组？分词？入参？算术？），再动手；
改完必须跑**全量**门禁，而不是只看本次用例。

## 前置（每次动手前必做）

按 `AGENTS.md` 的**开工四步**加载：`.claude/plan/stages.md` §9 断点卡 → `MEMORY.md` → `AGENTS.md`
（硬约束 + 元规则）→ `.claude/plan/status.md` §3 状态表；然后跑一次门槛确认基线：

```powershell
.venv\Scripts\python.exe -m pytest -q        # 期望数字见 .claude/plan/status.md §3.1（唯一真身）
```

工作目录必须是仓库根，复用现有 `.venv`（不要新建）。

## 硬约束（违反即为错误方案）

- **C1** 不改、不复制官方 `sqlparse` 源码（它只是 pip 依赖）。
- **C2** 不 monkey-patch；只子类化 + 换装实例。
- **C3** 不复制官方 `build_filter_stack` 的装配逻辑。
- **C4** 不用「改官方 strip 让它保留换行」的魔改；输出不得依赖输入空白。
- **C5** 各 pass 只允许改写 `Whitespace` token（不改 ttype、不重排、不删非空白 token）。

## 元规则（历史失败模式的固化，逐条都真踩过）

- **元规则一**：列对齐 / 字段列表**整体**错乱时，**先怀疑分组口径，再查 pass**。
  （S6 段 7 个「列对齐」用例里 6 个的真因是分组/分词：U15 尾逗号吞子句关键字、U16 缺
  `DATETIME`、U13 CREATE 早退、S6b 项内尾随空白与相邻续接列表。）
- **元规则二**：定性先写**最小重现**（现写个临时脚本探针，见本技能「坑位」与 `plan/history.md` §9.4），
  别拿整条 fixture 下结论。
- **元规则三**（元规则二的边界）：孤立片段与真实 fixture 行为不一致时，**以真实 fixture 的探针为准**。
  「抽出来跑是好的」**不等于**实现正确（S6b 就栽在这里：真因只在整条 fixture 里显形）。
- **元规则四**：改对齐 / 换行算术前，先确认差异只可能来自**入参**（offset / 列表项集合 /
  分组形状）——算术本身极少是元凶。
- **元规则五**：同一根因的改动常常**成对出现**（分组侧 + 布局侧），改完必须跑全量门禁。
- **元规则六**：验证「某处改动是否真是元凶」的硬手段是把它换成 **no-op**（或提前 `return`）
  再跑一遍；现象不变说明找错了地方。
- **元规则七**（S7 新增）：`passes/layout.py` 的 `_process()` 是**按组类名分发**的
  （`_process_{cls}`）。任何「把括号包进别的组」的补偿都会让 layout 阶段**收不到**那个括号
  （U13 的 `t (…)` 被包成 `Function` → 字段列表永不展开）。排查时先 dump 树看**括号的父组是谁**。

## 工作流

### 步骤 1 — 界定缺口（只读，可并行）

1. 跑门槛拿失败清单：`pytest -q`（FAILED / XPASS 两类，XPASS 说明「已登记项修好了」，要删项）。
2. 逐用例看差异性质：纯**空白宽度**（对齐类）／**结构性折行**／**分组或形状错**。
   据此选诊断路径；不要一上来就读 pass 代码。

### 步骤 2 — 定性（最小重现 → 真实 fixture）

- 先抽**最小片段**复现（自写 `_tmp_*.py`，放仓库根，用完删；`.gitignore` 已覆盖）。
- 片段结论不足以定案时（元规则三），改打**真实 fixture** 的中间量。
- 常用中间量：
  - **树**：`engine` + `sqlfmt_ext.grouping.group(stmt)` 后递归打印 `type(token).__name__` 与 `value`；
  - **列对齐**：列表项集合、每项 `as_offset` / `alias_len`、汇总 `max_as_offset` / `max_alias_len`；
  - **DDL 字段列**：`field_lines`、每列 `max_offset`、每个 token 的 offset；
  - **该不该换行**：语句层每个 token 对 `split_words` / `join_words` 的命中。

### 步骤 3 — 锁定原因归属

按此顺序判断，避免改错层：

1. **树形不同** → 分词组（`sqlfmt_ext/grouping.py`）。对照 `references/u-series-diffs.md`
   看是否已有同类补偿（U1–U17），并注意每处补偿的**调用时序约束**。
2. **树形相同、中间量不同** → 入参问题（offset / 列表项集合 / 注释吸收逻辑）。
3. **树形与中间量都相同** → 才看 `passes/align.py` / `passes/layout.py`（此时多半是
   「空白写到了错误的相邻位置」，而不是算术）。

### 步骤 4 — 实施

- 补偿一律加在 `sqlfmt_ext/`，遵守 C1–C5。
- **时序是第二根因**：放错位置会被官方后续步骤或 `_group_level` 重新归并掉，表现为
  「打印命中了分支，但最终树没变」。分组补偿的调用顺序与「必须放在 `_walk` 之前 / 之后」
  都写在 `references/u-series-diffs.md` 与函数 docstring 里。
- 临时探针放**独立脚本**，不要往源码里塞 `print`；真塞了必须当轮删掉。

### 步骤 5 — 验收与收工

```powershell
.venv\Scripts\python.exe -m pytest -q
```

必须同时满足：**0 failed**，且 `xfail` 数量只减不增（修好一项就删一项）。然后按
`AGENTS.md` 的**收工六步**落地：刷新 `.claude/plan/stages.md` §9 断点卡与
`.claude/plan/status.md` §3.2 状态表、`MEMORY.md` 沉淀长期事实、追加当日记忆、提交
（一个阶段一个可 revert 提交；含不可逆动作要写回退方式）。

汇报**末尾还要附部署提示**：改了 `sqlfmt_ext/` 行为 → 全局工具仍是旧版本，需
`uv tool install --force --reinstall .` 重装（同版本不带 `--reinstall` 不会重装包），
有下游机器还要 `uv run python scripts/build_package.py` 重新打包分发。
细则是 `.claude/rules/stage-protocol-阶段推进协议.md` 的「部署提示」一节。

> 若判定的结论是「这条差异**不修**」（例如 `ON COMMIT` 刻意分行属口径本身），
> 登记进收敛门禁的 `KNOWN_DIVERGENT`，**必须写清原因**，并在 `.claude/plan/diffs.md` §4 说明为什么。

## 坑位（每条都是真踩过的）

- `FilterStack.run(sql)` 返回**生成器**，不消费等于没跑。
- **临时探针写进独立脚本，不要往源码里塞 `print`**；真塞了当轮删掉。
- 比对不能只比「非空白 token 序列」（格式化不重排 token，恒等），要比**行内容**才能分离换行位置差异。
- **一次把探针的两侧模式 + `@相对路径` 补齐**，否则要来回跑好几轮（S6a/S6b 都是补完探针才一步定案）。
- **「关掉它做对照」**是验证元凶的硬手段：把可疑改动换成 no-op（或提前 `return`）再跑一遍，
  现象不变说明找错了地方。
- `git commit -m` 的消息**不要带 ASCII 双引号或反引号**（PowerShell 会吞 → 提交静默不执行）。

## 资源

- `references/u-series-diffs.md` — 官方 0.6.0 与旧 fork 的 U1–U17 差异、根因、补偿落点与**时序约束**。
- `references/grouping-and-layout.md` — `grouping.py` 补偿清单、官方分组步骤顺序、注释缩进口径、
  架构决策，以及 `group()` 的真实调用次序。
- `references/tooling.md` — 诊断手法与**坑位**（其中若提到 `_tmp_*.py` 脚本，说明那是迁移期脚本，
  已在 S7 删除；按本技能「坑位」现写即可）。
- `references/progress-and-targets.md` — 指针：进度与门槛的权威出处是
  `.claude/plan/status.md` §3 与 `.claude/plan/stages.md` §9。
- `scripts/run_gates.py` — 门禁脚本：跑唯一套件 `tests/` 并断言「摘要 == 期望」且「无 xfail」
  （默认期望值即当前门槛；改门槛时同步 `.claude/plan/status.md` §3.1，它是唯一真身）。日常也可直接 `pytest -q`。
