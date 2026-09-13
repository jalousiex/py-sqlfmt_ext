# 归档 — 迁移期（S0–S7）与变更记录

> **何时读**：追溯「当初为什么这么定」。**当前状态一律以 `status.md` / `stages.md` 为准**，
> 本文件里的命令、门槛数字与临时脚本都是**当时口径**，不要再执行 / 比对。
> 章号沿用原 `PLAN.md`（本文件含 §2.3、§3.1/§3.2/§3.5、§5、§8、§9.3、§9.4）。

---

## §2.3 迁移期共存（已结束）

迁移期曾并存：仓库根 `sqlparse/`（旧 fork，作 oracle）、`sqlfmt_ext/`（新实现）、
`tests/`（主套件，跑在旧 fork）、`tests_migration/`（对拍进度条）。
`tests_migration/conftest.py` 把仓库根挪到 `sys.path` 末尾让官方包优先，并**禁止两套件同会话混跑**
（`sys.path` 调整是进程级副作用 → 混跑会静默出现大量失败）。

**S7-c 已删除**：`sqlparse/` 旧 fork、`tests_migration/`、共存 hack，全部随五个提交收口。

## §3.1–§3.2 迁移期对拍基线与差异归因

全官方 pipeline 下的起点：逐字节一致 **1 / 31**、仅空白宽度 **6 / 31**、换行骨架 **24 / 31**。
24 个骨架差异收敛为**有限几组规则**（不是 24 个独立 bug），其中「注释强制换行」一条覆盖 12 个用例。

> **修正**：早先 `_tmp_official_ai4.py` 得出的「28/31 骨架一致」是**偏乐观**的结论 ——
> 当时只把 `AlignedIndentFilter` + `strip` 换成官方，其余（`grouping` / `sql` / `lexer` /
> `keywords` / `operators` / `statement_splitter`）仍是 fork 实现。**全官方 pipeline 才是真实基线。**

**首版规则→用例映射（U11 之前，30 个 xfailed）**：

```
L1 (12): case/s01 s02 | comma/s01 s02 | cte/s01 s02 | dml/s01 s05
         nested/s01 s02 | window/s01 s03
L2  (7): ddl/s01 s02 s03 s06 | dml/s02 s03 s04
L3  (1): ddl/s05        L4 (1): dml/s06      L5: case/s03
L6  (1): generic/s01    L7 (1): ddl/s04
A1  (6): aggregate/s01 s02 | debug/sqldebug_s01 | dml/s07 s08 | window/s02
```

U11 落地后 **L3 / L6 / L7 整条消失**，L1 少 4 个、L2 少 1 个、A1 少 5 个。
**教训**：规则→用例的映射必须用**最小化输入**复核，否则会把空白粒度问题的表现误记成
「某条布局规则未实现」。

## §3.5 U11：官方 lexer 的空白是「逐字符」token（列对齐 ±1 的根因）

实测：`sqlparse.parse('select a' + ' '*82 + 'as b')[0]` → **空白 token 数 = 84，每个 value 长度都是 1**。
官方 `strip` 再把一段连续空白变成「首个 token 保留 `' '`、其余全部置 `''`」；旧 fork 用
`[^\S\r\n]+` 把一段空白合并成**一个** token，所以 fork 里所有「改写某个相邻空白 token」的代码
（`_set_adjacent_ws` / `_collapse_newline` / `_remove_prev_newline` / `_take_comments_before`）
都建立在「一段空白 = 一个 token」这个前提上。

移植到官方 token 流后前提不成立 → **列宽整体 +1**，并在树里留下大量 value 为 `''` 的空白 token。

**为什么必须放在 strip 之前**：官方 `_stripws_identifierlist` 只删掉逗号前的**最后一个**空白 token
（它假设「一段空白 = 一个 token」）；逐字符空白下它在 `' '*82` 里只删掉 1 个，剩下的 1 个空格留在
逗号前，与 `AlignMixin` 填好的对齐空白叠加 → **非 AS 字段的末尾逗号整体多 1 列**。

**证据链**：`_tmp_ws_when.py` 审计空空白 token（前 246 / 后 243）；`_tmp_align_trace.py` 打印被替换的
空白 token（官方侧 `ws='' ws_idx=83`、fork 侧 `ws=' ' ws_idx=1`）；两侧 `_identifier_layouts` 的汇总值
**完全一致**（`max_as_offset=94`、`as_offset=12`）—— 差异只出在「改哪个空白 token」。

**效果**：对拍 `5/26` → **`14/17`**。最终形态见 `stages.md §9.2`。

## §5 分步实施（迁移期 S0–S7）—— 当时的验收口径

当时的验收两条：**净效果**（对拍 `xfailed` 降到目标值）+ **不回归**（主套件保持 `170 passed, 6 xfailed`）。
阶段状态与门槛已并入 `status.md §3.2`，此处只留**过程性结论**：

- **S1**：先把骨架搭在官方 0.6.0 上（方言 lexer、分词补丁、`LayoutPass`、摘官方换行 filter）。
- **S2**：U5 落地（`Case.get_cases` 注释占位）；U6/U7 经检索确认无影响 —— **「先实测再补」省掉了两处
  不必要的补偿**。
- **S3**：分组口径三条 + U10 + U11（本轮主要产出，+9 用例）；L1 的结构性强制断行**尚未**系统化。
- **S4**：真因不是布局而是**分组口径**（U12）—— 再次印证元规则一。
- **S5a/b/c**：分词兜底（L4）、U14 + `_create_guard` 边界 + 注释串层级缩进、`case`/`when` 口径重定。
- **S6**：起点 7 个「列对齐」用例，真因**全部**是分组或分词（U15 尾逗号吞子句关键字、U16 缺
  `DATETIME`、U13 CREATE 早退、S6b 相邻续接列表）—— 元规则一的最强证据。
- **S7**：a 门禁转正 → b 入口切换 → c 删 fork（不可逆）→ d 基线重定（有意偏离清单归零）→ e 收口。

**S7-b 实测的 6 个失败（窗口期已知）**：「实现切换」与「基线翻转」不可能在同一提交里都绿
（`tests/` 的输出回归钉着旧基线）—— 卡片允许的短暂窗口，提交信息里写明了。

**S7-d 决策（最佳实践）**：删 fork 后**不留**「断言型偏离」—— 对照对象已不存在，留着只是长期养的
特殊分支（维护成本 + 后人困惑）；用独立提交把 fixture 重定成新口径，回退就是 revert 它。

## §8 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-12 | 初稿：确立方案 A（官方包作 pip 依赖）、四段管线、6 组规则拆分、S0–S7 步骤拆分 |
| 2026-09-12 | S1 落地后的修订：①官方 `AlignedIndentFilter` 不再进 stack，改由 `LayoutPass` 独占换行骨架；②对齐规则改为 mixin 组合而非独立后置 pass；③新增 §3.4 上游语义差异清单（U1–U9），步骤表按实际成本重排（新增 S2 语义补偿） |
| 2026-09-12 | §4「明确不移植」更正：`*_newline` / `_pull_inline` / `_remove_prev_newline` 等**保留** —— 在官方 strip 之下它们不再承担「擦除输入换行」，而是管理本 pass 自己插入的空白；真正删掉的只有 `_flatten_up_to_token` 的调用语义变化与旧 fork 的 strip 魔改 |
| 2026-09-12 | S2 完成：①U5 以 `LayoutPass._get_cases` 本地实现补偿；②U6/U7 实测无影响、仅记录不动代码；③发现 L5 在旧实现里依赖输入换行（`has_nl`），属**不收敛**行为，`case/sqltest4_s03` 暂列 `KNOWN_DIFF` |
| 2026-09-12 | S3 进行中：分组补偿扩到四条；lexer 新增「优先级补丁」插入点（U10）；对拍 `4/27 → 5/26`；定位列对齐 ±1 根因 = U11 |
| 2026-09-12 | **U11 落地，对拍 `5/26` → `14/17`**：新增 `whitespace.merge_whitespace_runs` + `StripWhitespaceFilter`（strip 前合并）；修掉「改错空白 token（+1 列）」与「官方 `_stripws_identifierlist` 只删 1 个空 token」两类问题 |
| 2026-09-12 | 工具整理：`_tmp_cmp.py` 两侧选项与主套件口径对齐；`_tmp_*.py` 加入 `.gitignore` |
| 2026-09-12 | **S5a 落地，对拍 `21/10` → `22/9`**：`MULTIWORD_REGEX` 补 `(LATERAL\s+VIEW)\b` 兜底（UDTF 不在白名单时两个单词 token 谁都匹配不上） |
| 2026-09-12 | **S6b 第一击：注释前导空白整段搬出组，`28/3` → `29/2`**：`_unabsorb_trailing_comments` 吃前导空白的 `if` 改成 `while`（分组阶段空白逐字符，只吃 1 个会把剩余空白留在项内 → `max_as_offset` 抬高 1、整列 +1）；同时补 `_process_comment` 的「紧邻前一个非空白兄弟本身就是注释」判定（**两条必须一起改**） |
| 2026-09-12 | **U13 落地，`27/4` → `28/3`**：`_wrap_create_table_calls` 在官方分组后把「`Name`/`Identifier[Name]`/非子句 `Keyword` + 紧随 `Parenthesis`」包成 `sql.Function`（放之后：之前括号还没成组） |
| 2026-09-12 | **U16 落地，`26/5` → `27/4`**：官方词表缺 `DATETIME`（整词匹配、fork 是前缀命中）→ 类型名落 `Name` → 与字段名粘成一个 `Identifier` → DDL 列基准全错。**定位手法**：`_tmp_ddlprobe.py` 打两侧 `field_lines` / 每列 `max_offset` |
| 2026-09-12 | **U15 落地，`24/7` → `26/5`**：官方 `group_identifier_list.valid_next` 认 `T.Keyword` → 尾逗号后的子句关键字被吞进列表。新增 `_trim_clause_tail`（**必须在 `_walk` 之后**） |
| 2026-09-12 | **S5 清零（`cte/sqltest2_s02`），`23/8` → `24/7`**：三层根因 —— U14、`_create_guard` 边界取错（应为 `with`/`select`/`values` 中最先者）、注释串层级缩进口径。坑：`sql.Comment` 也是 `TokenList`，判「以注释结尾」必须先判自身 |
| 2026-09-12 | **S5c 定性（用户拍板）**：`case` 与首个 `when` 取**同行**，`case/sqltest4_s03` 登记为**有意偏离**（断言而非 xfail + 「变换失效即报错」守卫）；**未改任何 fixture** |
| 2026-09-12 | 按「历史失败模式 → 指令修订」修正 `AGENTS.md`：①修事实错误（用例目录）；②补架构为迁移期四段流水线；③新增硬约束 C1–C5 与两条元规则；④补诊断工具清单与三个坑 |
| 2026-09-12 | **S4 落地，`16/15` → `21/10`**：U12 预包对象名链、`_SQLCLS` 补 `sql.Parenthesis`、`_create_guard`+`_flatten_identifier_lists`、`_process_parenthesis` 首个子列表以注释开头时不插换行 |
| 2026-09-13 | S7-a~e 五个提交（`14973fc`→`e1378e5`→`8de1fb7`→`a257560`→`4471cd6`）+ `31d2e72`（修 DDL 被 U13 误包）—— 门槛 `172 passed, 4 xfailed` |
| 2026-09-13 | **S9 / S10 / S10-b 收**：注释断行结构性口径、语句前导注释判据、收尾注释按层级 + `;` 顶列 0 → `176 passed`（收敛门禁清空） |
| 2026-09-13 | **S8-a~d 收**：方言层从「装饰性模块」变成真开关（单一真身 + 未知方言报错 + `GO` 批切分 + MySQL 适配）→ `234 passed` |
| 2026-09-13 | **S11–S16 收**：DDL 列序、LIMIT、ALTER 多子句、`Keyword` 类型名、泛型尖括号、`ON` 词边界 → `269 passed` |
| 2026-09-13 | **计划重构**：根 `PLAN.md` 拆分为 `.claude/plan/{PLAN,status,stages,diffs,history}.md`（大纲 / 状态 / 阶段 / 差异 / 归档），消除 §3 与 §5 两张重复状态表、重复的 S6b 段落与重复的 §9.4；门槛数字收敛为 `status.md` 单一真身 |

## §9.3 分段任务卡（迁移期原始记录，已过期）

**分段原则（仍然适用）**：**一段 = 一条规则 / 一个根因**，上下文只读该段需要的文件；
需要跨文件探索的先用 `code-explorer` 子代理，把结论（不是文件内容）带回主线。

| 段 | 目标 | 状态 |
|---|---|---|
| S4 | L2 括号字段列表展开（真因 = 分组口径 U12） | ✅ 16 → 21 |
| S5a | L4 多 `lateral view` 各自分行 | ✅ 21 → 22 |
| S5b | U14 + `_create_guard` 边界 + 注释串按层级缩进 | ✅ 22 → 24 |
| S5c | `case` 与首个 `when` 同行（口径重定） | ✅ 22 → 23 |
| S6a | U16：官方词表缺 `DATETIME` | ✅ 26 → 27 |
| S6b | 列表末尾列口径（项内尾随空白 / 相邻续接列表） | ✅ 28 → 31 |
| S6c | U13：官方 `group_functions` 的 CREATE+TABLE 早退 | ✅ 27 → 28 |
| S6 | U15 尾逗号吞子句关键字 | ✅ 24 → 26 |
| S7 | 收敛 + 幂等 + 入口切换 + 删 fork + 改文档 | ✅ 终值 172/4 |

**分段推进的操作要点（省上下文的做法）**：
1. **先分类再动手**：一条命令拿到全部用例的格局（每例首 2 处差异 + 「是否只是空白宽度」），再决定这段做哪一类。
2. **一次只读该段需要的文件**；跨文件搞清楚「官方某步是不是在别处发生」时用子代理，只把结论带回主线。
3. **最小重现优先**：能用 1 行 SQL 复现就不要拿 40 行 fixture 试。
4. **对齐类问题先怀疑分组**（U9 的教训），分组对了再查 `align.py`。

**S3c**：Comment 组内相邻注释强制各自成行（结构性，不依赖输入换行）。
踩坑：`sql.Comment` 是**分组类**，裸注释 token 属于 `T.Comment` 的**token 类型**，判定要用
`isinstance(tk, sql.Comment) or tk.ttype in T.Comment`。

**U9**：官方 `group_as.valid_prev` 拒绝关键字作 AS 左值。补偿 = 在官方分组**之前**把那个关键字本身
包成 `Identifier`（其余全交给官方）→ 官方树天然是 `Identifier[level, ws, as, ws, Identifier[depth]]`。
**必须排除 `END`**（`sql.Case.M_CLOSE`，`group_case` 早于 `group_as` 且 `token_next_by` 不递归）。

**S6b 的定位过程（多轮，结论）**：症状「整体 +1 格」的真因是**列表项的组里带着尾随空白**，而
`_identifier_layout` 给无别名项算 offset 时把项内尾随空白也算进宽度。根因 = 分组阶段空白是逐字符
token（U11 家族）→ 修法是「整段吃空白」+ 布局侧配对改动。
后两例（`case/sqltest4_s01`、`nested/sqltest3_s01`）根因是**相邻同类列表**（`extend=True` 语义）：
`_extend_adjacent_lists` + `_normalize_adjacent_lists` 按**活下标**重扫并回，并在
`_attach_over_to_functions` 之后再跑一遍。判据踩坑：注释在这里是 **`sql.Comment` 组**（`ttype` 为
`None`），只判 `ttype` 会漏 —— 这正是上一轮「注释开头」实验失败的真正原因。
**工具缺口**：探针要支持 `@相对路径` 喂真实 fixture（孤立片段复现不出来，元规则三）。

## §9.4 S7 执行卡（含「有意偏离」处置决定）与诊断工具

**执行顺序不可调换**，每步一个独立提交，失败就 `git revert` 单个提交即可回退：

- **S7-a 门禁转正** ✅：新增收敛门禁（跑在新实现上），压平口径抽到 `tests/fixtures/whitespace.py`。
- **S7-b 入口切换** ✅：`sqlfmt.py` 改调 `sqlfmt_ext.format_statements`；`sqlparse` 变 pip 依赖。
  **附加动作（实测必需）**：新增仓库根 `conftest.py` 把「让已安装官方包胜出」的 `sys.path` 调整提到
  根级 —— 否则 `tests/` 会话会用仓库根的旧 fork 喂 `sqlfmt_ext`（root 在 `sys.path` 里胜出）→ 静默错乱。
- **S7-c 删 fork** ✅（不可逆，提交信息写明回退方式）：`git rm -r sqlparse/`，删 `tests_migration/conftest.py`。
- **S7-d 有意偏离处置** ✅：重定 `case/sqltest4_s03.sql` 基线（`case` 与首个 `when` 同行），偏离清单归零。
- **S7-e 收口** ✅：更新 README / AGENTS.md，删 `_tmp_*.py`。

**诊断工具（已全部删除，需要时现场写 `_tmp_*.py`）**：迁移期探针随旧 fork 一起删了（`--fork` 侧已无
处可跑）。`.gitignore` 仍忽略 `_tmp_*`，脚本一律现场写、用完即删。诊断手法见技能 `sqlfmt-parity`。
唯一**没有** fork 也能用的形状是直接读树：在 `LayoutPass.process` 外层 patch 一下 dump 语句层 token
（`type` / `value` / `ttype` / `is_newline`）再跑 `format_statements`。

**排查踩过的坑**：
- `FilterStack.run(sql)` 返回**生成器**，不消费等于没跑 → 自建探针必须 `list(...)`。
- 官方 `Lexer.get_tokens()` 产出的是 `(ttype, value)` **元组**，不是 Token 对象。
- `Token.is_newline` / `normalized` 是**构造期缓存**，strip 之后 value 变了它们不变 → 想验证
  「输出是否依赖输入空白」，用 `tests.fixtures.whitespace.flatten_whitespace` 压平输入再跑一遍比。
- 探针要打**真实 fixture** 而不是抽出来的片段（很多形状只在完整 fixture 里出现）。
