# 阶段卡 — 断点卡与各阶段记录

> 本文件 = 每阶段的**断点续做卡**（原 `PLAN.md` §9）。**章号沿用原编号** ——
> 代码注释与技能里的 `PLAN §9.x` 引用**指本文件同号小节**（§9.3 / §9.4 已归档到 `history.md`）。
> 阶段状态与门槛数字以 `status.md` 为准；硬约束见 `PLAN.md` §1；差异机理见 `diffs.md`。
>
> **开工第 1 步读这里**（§9 断点卡的「下一步开工点」）；**收工第 2 步刷新这里**。

---

## §9 断点卡

> 落盘时间：2026-09-16（E2 收工刷新）。
> **S1–S7、S9、S10、S10-b、S8-a~d、S11–S18、E1、E2 全部完成**，门槛与 `KNOWN_DIVERGENT` 现状见 `status.md §3`。

**方言优先级（用户口径，2026-09-13 定）**：**Doris / SelectDB 最优先 → 其次 MySQL →
Oracle / SQL Server 暂缓不做**。S8-a~d 至此全部收：Doris/SelectDB 与 MySQL 已适配；
SQL Server（S8-c）已完成并保留（不回退、也不再往前推）；Oracle 未开工。

**下一步开工点（2026-10-24，S18 收工刷新）**：**无** —— S18（`over` 前夹注释的分组时序）已收，
卡见本文件 §9.22；S17（独立 `@` 定制行原样保留）见 §9.21；
E2（工具链切 uv + 部署形态改 `uv tool install`）与方言路线也已走完。

**当前无「必须做」的缺口**：剩下的都是**登记在案的已知边界 / 事实**（都不影响现有 fixture，各自需先开
新阶段卡再动手），清单见 `status.md §3.5`（其中第 9–12 条是 E2 登记的 uv 类事实）；写卡前请先做下面这条巡检。

**巡检结论（2026-09-13，S16 期间做的一轮）**：拿一段真实风格的 Doris 建表 + CTE/窗口/`case`/`having`
查询跑过，输出与既有 fixture 口径**逐项一致**，没有发现新缺口。两处「看着不齐」的形态是**既定口径**，
不是缺陷：①`having` / `comment` 顶列 0 —— 锚点关键字**右端对齐到 `leading_ws`（6）**，7/6 字符的关键字
恰好落到列 0（与 `ddl/sqltest0_s06` 的 `comment` 一致）；②CTE 体的 `select` 顶列 0（见 `cte/sqltest2_s01`）。
**要开新阶段就别再靠「感觉」找缺口**：先拿真实语料跑一遍并与既有 fixture 口径对照，确认是**新缺口**
再写卡（参考技能 `sqlfmt-parity` 的元规则一~七）。

## §9.1 复现当前状态

```powershell
uv run pytest -q                   # 门槛数字见 status.md §3.1
uv run pytest -q -k convergence    # 只看收敛门禁
```

只有一套测试（S7 删 fork 后 `tests_migration/` 已并入 `tests/`）。**残留：无。**

## §9.2 空白归一化（U11）最终形态

| 文件 | 改动 |
|---|---|
| `sqlfmt_ext/whitespace.py` | `merge_whitespace_runs(tlist)` —— 递归合并每层连续的空白 token，value 拼接、ttype 沿用段首 |
| `sqlfmt_ext/filters/whitespace.py` | `StripWhitespaceFilter` = 官方 `StripWhitespaceFilter` 子类，覆写 `process` 在 `self._stripws(stmt)` **之前**调用合并；其余逐行同官方 |
| `sqlfmt_ext/stack.py` | `_swap_whitespace_filter`，在 `_replace_skeleton_filters` 之前换装 |
| `sqlfmt_ext/passes/layout.py` | `LayoutPass.process` 入口加 `merge_whitespace_runs(stmt)` 兜底（幂等） |

**为什么必须放在 strip 之前**（关键，别再挪回 `LayoutPass`）：官方 `_stripws_identifierlist` 只删掉
逗号前的**最后一个**空白 token；逐字符空白下它在 `' '*82` 里只删掉 1 个，剩下的 1 个空格留在逗号前，
与 `AlignMixin` 填好的对齐空白叠加 → 非 AS 字段的末尾逗号整体多 1 列。（机理与证据链见 `history.md §3.5`。）

## §9.5 不要做的事

- 不要用「改 ttype / 删非空白 token / 重排」的手法对齐（C5）。
- 不要用「改官方 strip 让它保留换行」的魔改（C4）—— 想利用「输入这里有个换行」时，
  先看 `Token.is_newline` 那类**缓存属性**（它就是残留）。
- 不要把诊断脚本留在仓库里（`_tmp_*` 用完即删）。

---

## §9.6 S9 已收（2026-09-13）：注释断行的结构性口径 —— 收敛门禁 4 xfail → 1

**靶子**：收敛门禁剩的 4 个 xfail，全部是「输出仍依赖输入空白」，且都是注释/分号的结构性断行没做透：
`comma/sqltest7_s02`、`nested/sqltest3_s01`、`ddl/sqltest0_s04`、`cte/sqltest2_s01`。

| 用例 | 根因 |
|---|---|
| `comma/sqltest7_s02`、`nested/sqltest3_s01` | 两段相邻注释「各占一行」只由**组内**规则（`_break_between_comments`）保证；而这两段注释经官方 `align_comments` 并组、又被 `_unabsorb_trailing_comments` 拆回后，是**同层并列的两个 `Comment` 组** —— 组内规则看不到它们，旧实现只剩「输入里这里正好有换行」（`prev_.is_newline`）兜着，压平即失效 |
| `ddl/sqltest0_s04` | `ON COMMIT` 白名单只做了一半：输入写 `on\ncommit` 时保留分行，写 `on commit` 时不管 → 输出依赖输入 |

**改动**（都在 `sqlfmt_ext/passes/layout.py`，无新文件）：

1. **`_break_before_sibling_comment`（新增）**：把同一条规则「两段注释不共享一行」扩到**同层并列的
   注释组**。判据是结构性的「**前一段注释自己不带行尾换行**」（`-- x` 的 token 含行尾换行、块注释不含）
   → 换行 `self.nl(0)`（本层缩进）。在 `_process_comment` 里紧跟 `_break_between_comments` 调用
   （必须在它那个「只处理 `--` / `/*-*/`」的早退**之前**）。
   **为什么不并组**：试过在 `grouping` 层把相邻注释并成一个组，**回归 4 个用例**
   （`ddl/sqltest0_s05`、`window/sqltest6_s02`、`case/sqltest4_s01`、`cte/sqltest2_s02`）——
   那些是**行注释**串，后一段的缩进要交给 `_process_comment` 的对齐逻辑（列 7），并组会把它们拉回列 0。
2. **`_normalize_newlines` 的 `keep_newline` 白名单改成结构性**：命中者（`ON COMMIT`）一律
   `self.n.join(tk.value.split())` 切开，不管输入是 `on\ncommit` 还是 `on commit`。

**证据**：改后 4 项里 3 项 **XPASS(strict)** 报错（说明确实收敛），按纪律从
`tests/test_sqlfmt_convergence.py::KNOWN_DIVERGENT` 删除并写明原因；`172 passed` 那批一个没动。

**残留 / 下一步**：`cte/sqltest2_s01` 留作**已登记的发散**（canonical 的注释与 `;` 摆在列 0，而这
**只能由输入空白判定**）→ 属口径决策，**已由 S10 / S10-b 收**（见 §9.7 / §9.8）。

**回退方式**：两处改动各自独立 —— `_process_comment` 里的那一行调用（删掉即回到「依赖输入换行」）
与 `_normalize_newlines` 里新增的 `if` 分支。

## §9.7 S10 已收（2026-09-13）：「注释保持列 0」判据结构化 —— 收敛门禁 1 xfail → 0

**决策原文**（用户）：「原本在 0 列，改在语句前的限定，即 ddl/dml 等**单个 stmt 真实开始之前**的时候适用。」

**根因**：canonical 把 `where … = 0` 尾部的 `-- 顶行首注释` 与 `;` 都摆在列 0，而决定点是
`_process_comment` 收尾的 `prev_.is_newline`（字面意思「**输入里**这个注释前面是换行」）。
**判据读的是输入空白，与 C4 天然冲突** —— 不是实现缺口。

**改动**（都在 `passes/layout.py`；无新文件、无 fixture 改动）：

| # | 位置 | 改动 |
|---|---|---|
| ① | `_process_comment` 早退 | 判据由 `_get_offset(...) == 0` 换成新增的 `_is_stmt_leading_comment(tlist)`：**结构性**判定「它之前（逐层向上追问祖先层）不存在任何有效 token」→ 列 0 的适用范围收窄到**语句前导注释** |
| ② | `_process_comment` 收尾（`prev_.is_newline` 支） | 补结构性等价：新增 `_closes_its_level(plist, pidx)` =「其后本层只余空白与语句结束符 `;`」 |

**②为什么必须卡在 `;` 上**：`;` 常被官方分组收进**子句组内部**，所以「其后无内容」对
`-- 顶行首注释` 并不成立（后面还有 `;`），必须显式放行 `;`；同时又**必须要求 `;` 存在** ——
层内最后一个 token 的**行内**注释（`EmpCode -- 员工编码`）同样满足「其后无内容」，放行它会强行换行，
实测回归 `comma/sqltest7_s02`、`dml/sqltest1_s02`。

**证据 / 验收**：`cte/sqltest2_s01` 的 canonical **不需要重定** —— 原样输入与压平输入产出同一份、
且与现有 canonical 逐字节相同的输出；全量门禁通过（数字见 `status.md §3.2`）。

**残留 / 下一步**：一处口径细节 —— 那句注释物理上位于 `Where` 组内，却被归一到了语句层缩进（列 0），
与「按所在层级对齐」的字面读法（`Where` 层 = 列 7）不同 → **用户随即拍板按层级对齐**，已由 **S10-b** 修订。

**回退方式**：`layout.py` 两处判据 + 两个新增辅助方法 + `KNOWN_DIVERGENT` 一处删项，`git revert` 即可。

## §9.8 S10-b 已收（2026-09-13）：收尾注释按层级对齐、`;` 顶列 0

**决策原文**（用户，分两次给出）：①「语句前的顶行 `--` 注释、以及结尾的分号，希望它与**所在层级**对齐
—— 即最外层的就顶 0 列，但子查询、包括 `where` 内的，其实应该是**缩进**的。」②「`;` 分号只在
**分段 SQL 结尾** …… 在**前边过程中不特殊处理它，只在最后将它顶 0 列**。」

**两条口径合起来**：

- **注释**：按**所在层级**对齐 —— 语句前导注释位于语句之外、层级为 0 → 列 0；子句内的收尾注释
  缩进到该子句内容列（`where` 层 = 列 7）。
- **`;`**：它是**分段终止符**（`format_statements` 按它切分语句），不是任何子句的内容 →
  **一律顶列 0**；前面各步**不碰它**，只在 layout 收尾统一兜底。

**改动**（都在 `passes/layout.py`）：

| # | 位置 | 改动 |
|---|---|---|
| ① | `_process_comment` 的「本层收尾注释」支 | `prev_.value = self.n` → `self.nl(0).value`（`nl(0)` = 换行 + **本层缩进**） |
| ② | `LayoutPass.process` **收尾** | 新增 `_normalize_trailing_semicolon` + `_last_content`：取最后一个非空白 token，若是 `;` 就把它与前一个 token 之间的空白规范化，使 `;` 顶列 0 |

**②为什么必须放在「最后」**（也是踩过的坑）：中途给 `;` 前的空白「设成缩进」方向就错了 ——
先按 ① + 一个临时方案把 `;` 缩进到 7 列时，第二次格式化会读到上一遍留下的空白、被别处改成 1 个空格，
**幂等与收敛同时红**。改成「前边不特殊处理 + 收尾统一兜底」后两条输入路径自然归一。

**②要覆盖两种「独占一行」形态**（实测 dump 得来）：换行在 `;` 前的**空白 token** 里 → 置为单个换行；
换行由**前一个行注释**自带、中间那段空白只剩缩进 → 把这段缩进**抹掉**。同行写法（`select 1 ;`）不动。

**粒度**：`_is_stmt_leading_comment` 保持不变 —— 用户说的「最外层顶 0 列」正是它。

**证据 / 验收**：`cte/sqltest2_s01` 三条对照全等（原样输入 / 压平输入 / 输出再格式化输出）；其余项一项没动。
该 fixture 按**实跑输出重定**（不手写，沿用 S7-d 做法），尾部为 `where … = 0` / `      -- 顶行首注释` / `;`。

**残留 / 下一步**：无。

---

## §9.9 S8-a 已收（2026-09-13）：方言层收成单一真身

**勘测结论**（原计划以为缺口在「补词表」，实测缺口在「**方言层本身是死的**」）：`dialects.py` **零调用**；
`lexer.SUPPORTED_DIALECTS` 与 `dialects.DIALECTS` **两套真身** → 表里声明的方言运行时不存在
（`dialect="mysql"` 与 `dialect=None` **逐字节相同**）；**未知方言静默降级**；**零方言 fixture**（无验收通道）；
Doris 锚点词其实已生效，只是**注册在 `policy` 而非 `dialects`**。

**改动**（7 个文件）：

| 文件 | 改动 |
|---|---|
| `dialects.py` | 重写为**单一真身**：`Dialect(name, lexer_patches, extra_split_words, notes)`；Doris 的锚点词在 `_DORIS_SPLIT_WORDS` 声明；删死代码（`apply_dialect` / `_APPLIED` / 往官方 `SQL_REGEX` 注入）；新增 `available()` / `all_split_words()` |
| `lexer.py` | 删硬编码 `SUPPORTED_DIALECTS`，改问 `dialects.get_dialect(...).lexer_patches` |
| `options.py` | 未知方言抛 `SQLParseError`（并列出可用值），不再静默降级 |
| `layout.py` | `split_words` 从**类属性（导入期快照）**改为**实例属性** = `policy.split_words + dialects.split_words_for(dialect)` |
| `policy.py` | 只留**通用**词；`ON COMMIT` 收窄为 `\bON\s+COMMIT\b`（它是通用 DDL，`ddl/sqltest0_s04` 依赖） |
| `grouping.py` | `_is_clause_keyword` 的词表换成 `_CLAUSE_WORDS` = 通用词 + **所有**方言锚点的并集 |
| `tests/` | 新增 `cases/dialect/sqltest0_s01.sql` + `TOPIC_META["dialect"]` + `test_sqlfmt_dialect.py`（4 条断言） |

**最重要的发现（根因 + 教训）**：搬词后 `properties (1);` 突然与 `distributed by hash(id)` 挤到同一行。
顺序对照实验指向**分组层**：`grouping._is_clause_keyword` 硬引用 `policy.split_words` 判「这是不是子句
关键字」，词搬走后 `PROPERTIES` 不再被认作子句头 → `_wrap_create_table_calls`（U13）把它当函数名包成
`Function` → `_split_kwds` 在**本层**再也看不到这个 Keyword（不递归进子组）→ 换行消失。

> **教训（可复用）**：换行锚点词有**两个消费方** —— 布局层（要不要换行）与**分组层**（是不是子句头）；
> 分组层那个**必须与方言无关**（取所有方言的并集），否则「开关一动，整条 SQL 的结构都变」。
> 见 `diffs.md §4.5`。

**验收**：原 176 项一项没动；新增 9 项；开关证据：同一条 Doris DDL，`dialect="doris"` 与 `dialect=None`
输出**不同**；`dialect="typo"` → `SQLParseError: unknown dialect: 'typo'; available: doris, generic,
mysql, selectdb, sqlserver`。

**残留 / 下一步**：`mysql` / `sqlserver` 当时只是**登记**（行为等同通用）→ 由 S8-c / S8-d 收；
`LATERAL VIEW` 仍留通用词表（见 `status.md §3.5`）。

## §9.10 S8-b 已收（2026-09-13）：方言词表归位 + Doris 类型名补齐

**靶子**：S8-a 只把**换行锚点词**收进 `dialects`；**分词层词表还在 `policy`**（全局、与方言无关）。
实测一条含 Doris 常用类型的建表语句**列对齐直接错乱**：

```text
       id int64                    ,   ← 字段名与类型挤在一起（被粘成同一个 Identifier）
       v2 datev2                   ,   ← 异常
       v5 largeint                 ,   ← 异常
       v7 json                         ← 正常
```

token 级证据：`int64` / `datev2` / `datetimev2` / `decimalv3` / `largeint` / `bitmap` 全部落成
**普通 `T.Name`**，于是被 `group_identifier` 与字段名**粘成一个 `Identifier`** → 类型列取不到 token
→ **整列基准错**（与 U16 完全同一机理）。

**改动**：`Dialect` 增加 `extra_keywords`；`lexer` 改按方言注入；`policy` 删 `KEYWORDS_DORIS` /
`KEYWORDS_TYPES`（方言词不再散落在通用层）。

**补齐的 20 个类型名**：`AGG_STATE BITMAP DATETIME DATEV2 DATETIMEV2 DECIMALV2 DECIMALV3 DOUBLE
HLL INT16 INT32 INT64 INT128 IPV4 IPV6 JSONB LARGEINT QUANTILE_STATE STRUCT VARIANT`
（`DATETIME` 是 U16 补过的，本次归位到方言声明）。

**证据**：同一语句变成列对齐正确；`dialect=None` 仍错乱（`id int64`、`v2 datev2` 粘在一起）
→ 开关只在 doris/selectdb 生效，已写成断言。

**残留 / 下一步**：`json` 官方是 `T.Keyword` → **未覆盖**（覆盖它等于改写官方已有条目）→ 由 S14 收；
⚠️ **更正**：`MAP` 官方是 **`Name.Builtin`**（不是 `Keyword`），`map<string, int>` 的错乱来自
**尖括号实参里的逗号** → 由 S15 收。

## §9.11 S8-c 已收（2026-09-13）：SQL Server 适配

**四个目标构造的实测现状与处置**：

| # | 构造 | 实测现状 | 处置 |
|---|---|---|---|
| 1 | `[id]` / `[dbo].[t]` | 官方就认（落 `Token.Name`），输出已正确 | 不改，只固化 fixture |
| 2 | `TOP 10` | `top` 落 `T.Name` → 被 `group_identifier` 包成 `Identifier`，紧跟的**数字**又被列表 extend 收进**第一个列表项** → 字段列基准取到数字上 | **修**（分组层，官方分组**前**预包） |
| 3 | `WITH (NOLOCK)` | `with` 落 `Keyword.CTE` → `_split_statements` 认 `T.CTE` → **独占一行**；而 `with(nolock)` 先被官方「函数名」正则截成 `Name` → 粘在表名后。**同一语义两种写法两种输出** | **修**（分词层，方言优先级规则） |
| 4 | `GO` 批分隔 | 切分**只按 `;`** → 无分号时 `select 1\nGO\nselect 2` 被胶成一条语句；且输出随输入空白/大小写漂移 | **修**（切分层，按 token 切批） |

**改动**（5 个文件 + 1 个新 topic）：

| 文件 | 改动 |
|---|---|
| `dialects.py` | `lexer_patches` 拆成 `multiword_patches` + `precedence_patches`；新增 `extra_lexer_rules`（方言专属）与 `batch_separator`；声明 `sqlserver`（`WITH(?=\()` 规则 + `TOP`/`PERCENT` 关键字 + `GO`） |
| `lexer.py` | 按三项分别注入 |
| `grouping.py` | 新增 `_pre_merge_top_clause` + `_top_clause_span`（官方分组前） |
| `stack.py` | `format_statements` 增加批切分：`_split_batches`（按分词结果判「独立 `GO` token」）/ `_join_batches`；原主体抽成 `_format_batch` |
| `tests/` | 新增 `cases/sqlserver/` 4 个 fixture + `TOPIC_META["sqlserver"]` + 3 条断言 |

**关键决策（对照实验的结论）**：`TOP <n>` 合并成 **`Keyword`** 而非 `Identifier` 组 —— `Identifier` 组会被
`group_identifier_list` 的 extend 吸进列表（首字段前多 2~6 格、后一个字段被并进同一项），`Keyword` 不会被吸。
**闸门 = 「`TOP` 在本方言下是不是 `T.Keyword`」**（靠关键字声明），其余方言与 `dialect=None` 基线行为不变。

**批切分批的判据取自分词结果**（「独占一个 token 的 `GO`」），不看行首形态 —— 这样压平空白后的输入与
canonical 走同一条路径，**收敛门禁不破**。

**验收**：原 192 项一项没动；新增 23 项；`dialect="sqlserver"` 与 `dialect=None` 至此**输出不同**。

**残留 / 下一步**：批分隔符不解析字符串/注释内容（见 `status.md §3.5`）；`json` / `map` 未覆盖；
方言路线（S8-a/b/c）至此走完，`mysql` 仍是纯登记 → 由 S8-d 收。

## §9.12 S8-d 已收（2026-09-13）：MySQL 方言

**背景**：`dialect="mysql"` 当时是**纯登记**（实测 `mysql == generic : True`）。逐条缺口：

| # | 构造 | 处置 |
|---|---|---|
| 1 | 11 个类型名（`mediumint` / `mediumtext` / `longblob` / `datetime` …）落普通 `Name` → 与字段名粘在一起 | **修**：进 `extra_keywords`（U16 同机理） |
| 2 | 表选项全挤在 `)` 之后（现存换行是 `wrap_after=30` 撞出来的） | **修**：`extra_split_words` 补锚点 |
| 3 | `ON DUPLICATE KEY UPDATE` 未合并 → 被切成三行 | **修**：多词合并成一个 `Keyword` |
| 4 | `straight_join` 被 `_join_words` 命中 → `select` 后硬断行；`b = values(b)` 的右值被甩到下一行 | **修**：加**结构性 guard**「锚点紧跟 `SELECT`（select 修饰符）或紧跟 `=`（赋值右值）时不换行」 |
| 5 | `idx_dept (dept_id)` 被包成 `Function` → 落在类型列并与真实类型列对齐 | **不改**（不是缺陷，属风格取舍） |
| 6 | `DOUBLE` / `JSON` / `TIME` / `YEAR` 官方判成 `Keyword` | **S14 已收**（走 `type_name_keywords`，不覆盖词表） |
| 7 | `LIMIT 10, 20` / ALTER 多子句 | **不修**（Doris/MySQL 共享缺口）→ 由 S12 / S13 收 |

**实现期的两处纠偏**（勘测时判断有误，开工按实测改正）：

1. 换行锚点是**对单个 token** 做正则匹配 → **`ENGINE\s*=` 这种跨 token 写法永远匹配不上**。
   正确做法：锚点写**裸词**，跨词的 `DEFAULT CHARSET` 先用 `extra_lexer_rules` 合并成一个 token。
2. 裸 `COMMENT` 锚点**不会**拆散列级 `comment '主键'` —— 字段列表走 `align._create_field_lines`
   （按逗号切段），`_split_kwds` 在那里根本不跑 → `COMMENT` 不需要收窄、也不必重复声明。

**改动**（4 个文件 + 1 个新 topic；`policy.py` / `grouping.py` **一个字没动**）：`dialects.py` 声明 `mysql`；
`passes/layout.py` 新增 `_is_expression_anchor`（**通用**规则，不看输入空白）。

**补齐的 11 个类型名**：`BOOL DATETIME LONGBLOB LONGTEXT MEDIUMBLOB MEDIUMINT MEDIUMTEXT TINYBLOB
TINYTEXT VARBINARY ZEROFILL`。

**证据 / 验收**：原 215 项一项没动；新增 19 项；`dialect=None` 下类型名 / 表选项 / upsert 三处**都不生效**；
14 条 MySQL 构造冒烟与 `dialect=None` **逐条相同**（唯一 DIFF 是表选项，即本轮目标）。

**残留 / 下一步**：`default null` 列序 → **S11 收**；`LIMIT m, n` / ALTER 多子句 → **S12 / S13 收**；
Doris 的 `DUPLICATE` 锚点在 MySQL 的 `on duplicate key update` 里误触发（跨方言组合，见 `status.md §3.5`）。

## §9.13 S11 已收（2026-09-13）：DDL 字段列序 —— `DEFAULT` 之后的值不是约束

**靶子**：MySQL 导出的建表几乎每个可空列都写 `DEFAULT NULL`，即「**默认值 → 约束**」的**反序**形态
（既有 fixture 全是正序，所以一直没暴露）。

**根因**：`align._create_field_lines` 按**固定列序**逐列查找（名称 → 类型 → 约束 → `DEFAULT` → `COMMENT`），
每列都从上一列的命中位置**向后**找。于是 `dept_id int(11) default null` 的**约束列**越过了 `default`、
把 `null` 当约束 → 该行约束列的 offset 落到很右边 → `max_offset` 被抬高 → **整块字段（含其它行）的
列基准连带错乱**（元规则一：列对齐错乱先怀疑「归类/分组」）。

**改动**（`passes/align.py::_create_field_lines` 一处；只写 `Whitespace`，符合 C5）：字段内**先定位
`DEFAULT`**，把**约束列**的查找范围收窄到 `default_idx`；`DEFAULT` 自身与注释列仍按原范围查找。
与方言无关，`doris` / `mysql` / 通用路径同时受益。

**证据**：修后 `field_lines` 归位（col2 空、col3 `default`）；`dialect="doris"` 与 `dialect="mysql"`
输出**逐字节相同**；正序形态（`not null default 0`）输出**未变**。

**验收**：原 234 项一项没动；新增 5 项（`cases/ddl/sqltest0_s07.sql` **实跑输出定稿** + `.input.sql`）。

**已知边界**：判据是「约束列查找**止于** `DEFAULT`」→ 写在 `DEFAULT` **之后**的列级约束词
（`id int default 0 primary key`）不再进约束列（见 `status.md §3.5`）。

## §9.14 S12 已收（2026-09-13）：LIMIT 子句

**靶子**（`doris` / `mysql` 相同）：`limit 10,` + `20;` 被逐项展开；`offset 10;` 顶列 0 独占一行。

**根因（两处，独立）**：

| # | 现象 | 根因 |
|---|---|---|
| ① | `limit 10,` / `20;` | 官方 `group_identifier_list` 把 `10, 20` 收成 `IdentifierList`，`_process_identifierlist` 按列表逐项换行 —— 但 `m, n` 是「偏移量, 行数」参数对，不是列表 |
| ② | `offset 10;` 顶列 0 | **`SET` 锚点在做子串匹配**：`Token.match` 对每条锚点做 `re.search`（不是整词），裸 `SET` 在 `OFFSET` 内部命中。同族：`CHARSET` 也含 `set`（MySQL 表选项换行此前是**巧合**命中的） |

**改动**：①`policy.py` 的 `"SET"` → `r"\bSET\b"`（`INSERT … SET` 仍照常换行 ✓）；
②`layout.py` 新增 `_is_limit_list`（父层紧邻的前一个非空白 token 是 `LIMIT` 关键字），
在 `_process_identifierlist` 里照 `_is_lateral_view_list` 的既有手法早退。

**证据**：`limit 20 offset 10;` 与 `limit 10, 20;` 均同行；冒烟对照 `select * from t offset 10` ✓
（原为顶列换行）、`update t set a = 1` ✓、`insert into t set a = 1` ✓。

**验收**：原 239 项一项没动；新增 5 项（`cases/dml/sqltest1_s09.sql` + `.input.sql`）。

**残留 / 下一步**：ALTER 多子句 → **S13 收**；`SET` 之外的纯词锚点（`AND` / `COMMENT` / `\bON`…）
登记待观察 —— 其中 `ON` 有实证 → **S16 收**。

## §9.15 S13 已收（2026-09-13）：ALTER 多子句换行

**约束（决定实现形态）**：动作词（`ADD`/`DROP`/`MODIFY`/`CHANGE`/`RENAME`）**不能**直接进
`policy.split_words` —— 首个动作词前也会换行，而 `ddl/sqltest0_s06` 第 1 条
`alter table X drop column Y` 期望**同行**（`_split_statements` 里还专门有个 `is_alter_table_drop`
特例保住 `DROP`）。所以规则必须是「**本层有多个动作子句时**才换行」。

**改动**（`passes/layout.py`，三处）：①类属性 `alter_actions`（6 个动作词正则）+ `alter_action_indent = 3`；
②`_is_alter_action(token)` —— **按 `normalized` 自己匹配**，不用 `Token.match(T.Keyword, …)`（后者是
**身份比较**，`DROP` 的 ttype 是 `T.Keyword.DDL`，永远匹配不上 —— 同一个坑在分组层踩过）；
③`_split_alter_actions(tlist)`，在 `_process_default` 里紧跟 `_split_kwds` 之后调用。

**缩进口径**：用**固定列 3**（调用处传 `alter_action_indent - leading_ws`，因为 `nl(n)` 是叠加在
`leading_ws` 上的），而不是右对齐 —— 动作词长度不一（`add` 3 / `drop` 4 / `modify` 6），右对齐会参差不齐。

**不受影响**（逐条实测）：单动作 `alter table X drop column Y`（同行）、`alter table X rename to Y`、
单动作 + 括号列表照旧展开、`comment '…' after Email` 仍按既有口径折到列 0。

**验收**：原 244 项一项没动（`ddl/sqltest0_s06` 三条 ALTER 输出逐字节不变）；新增 5 项。

**残留 / 下一步**：`CONVERT`（MySQL 专有）未纳入动作词（见 `status.md §3.5`）。

## §9.16 S14 已收（2026-09-13）：官方判成 `Keyword` 的类型名

**勘测（先实测再定方案，纠正了两条旧记载）**：

| 词 | 官方 ttype（实测） | 结论 |
|---|---|---|
| `json` | `T.Keyword` | **要修**（Doris / MySQL 的列类型） |
| `double` / `time` / `year` | `T.Keyword` | **要修**（MySQL） |
| `map` | **`Name.Builtin`** | ⚠️ 旧记「官方是 `Keyword`」**有误** —— 类型列本来就能取到；错乱来自尖括号实参逗号 → S15 |
| `enum('x','y')` / `set('p')` | `Name` + `Function`（被官方「函数名」正则先截走） | **不需要修** —— 本来就正常对齐 |

**设计（不覆盖、不改写官方词表）**：把「哪些词在本方言里是类型名」作为**方言声明**
（`Dialect.type_name_keywords`）→ 只有**对齐层**的 DDL 类型列消费它。分词表一个字不动；
`dialect=None` 行为完全不变。

**改动**（4 个文件）：`dialects.py` 增加 `type_name_keywords`（Doris：`JSON`；MySQL：`DOUBLE`/`JSON`/
`TIME`/`YEAR`）+ `type_name_keywords_for()`；`passes/layout.py` 的 `__init__` 把声明的词编译成
**带词边界**的正则（避免 `TIME` 之类在别的关键字内部被 `re.search` 命中）；`passes/align.py` 的类型列
判据加上 `"m": (T.Keyword, self.type_name_keywords, True)`（`imt` 的 `i`/`m`/`t` 是 **OR** 关系）。

**验收**：原 249 项一项没动；新增 10 项（`cases/mysql/sqltest0_s02.sql`、`cases/dialect/sqltest2_s01.sql`）。

**残留 / 下一步**：尖括号泛型 → **S15 收**；S14 **没有**动分词层，因此 `json` / `double` 在**非 DDL
上下文**仍是 `Keyword` —— 有意为之（改分词会波及全局）。

## §9.17 S15 已收（2026-09-13）：泛型尖括号里的实参逗号

**靶子**：`map<string, int>` 的实参逗号被当成 DDL 字段分隔符 → 一个字段被拆成两行。

**根因**：DDL 字段列表的切段完全按 `,` —— `align._create_field_lines` 用
`token_next_by(m=(T.Punctuation, ","))`，`layout._process_parenthesis` 的字段列表分支也用同一手法换行；
而 `map<…>` / `struct<…>` 的逗号在 `<…>` **内部**。

**勘测到的结构细节（决定实现）**：`<` / `>` 是 `T.Operator.Comparison` 的**单个 token**；
**`>>` 是合并后的单个 token**（`array<map<string, int>>`）→ 深度必须按**字符数**增减，不能按 1；
`<=` / `>=` / `<>` 混了其它字符 → 不参与深度（否则比较表达式会被误判）。

**改动**（`align.py` 两处新增 + `layout.py` 一处替换；只改「找哪个逗号」，不动树、不删 token）：
`_angle_delta(token)`（全字符同号才计入，`>>` 记 −2）；`_next_field_comma(tlist, idx)`（向后找**深度为 0**
的逗号，返回形态与 `token_next_by` 一致）；`_create_field_lines` 两处与 `_process_parenthesis` 的
DDL/INSERT 字段列表分支改用后者（并顺手把「找不到逗号后仍调 `token_next(None)`」改成显式 `break`）。

**验收**：原 259 项一项没动；新增 5 项（`cases/dialect/sqltest3_s01.sql` + `.input.sql`）。

**残留 / 下一步**：`_process_parenthesis` 的 **WHERE 分支**未做深度感知（见 `status.md §3.5`）。

## §9.18 S16 已收（2026-09-13）：`ON` 锚点补后缀词边界

**来源**：S16 之前先做了一轮**真实语料巡检**（见 §9 巡检结论），顺手验证 S12 登记的「纯字母锚点」风险，
**其中 `ON` 有实证**：`select * from only t;` → `from` 后被折断；`… comments, online from t;` → `online`
独占一行且顶列 0。

**根因**：`policy.split_words` 里的锚点是 `r"\bON"` —— **只约束了前缀**。`ONLY` / `ONLINE`
（官方都判成 `T.Keyword`）会在 `re.search` 下命中；`_split_kwds` 于是把关键字当子句头换行，
`token_indent` 取该 token 的值（6 字符）→ `nl(leading_ws - 6)` = 列 0。

**为什么只有 `ON` 有实证**：锚点只对**被官方判成 `T.Keyword` 的 token** 生效，而官方词表里含其它纯词
锚点子串（`AND` / `COMMENT` / `OR` / `FROM` …）的关键字并不存在 —— 所以本轮**只改 `ON`**，其余登记待观察。

**改动**：`policy.py` 一行：`r"\bON"` → `r"\bON\b"`。`ON COMMIT` / `ON MANUAL` / `ON SCHEDULE` 都是
多词 token，`\bON\b` 照样命中。

**验收**：原 264 项一项没动（含 `join … on` 既有用例）；新增 5 项（`cases/dml/sqltest1_s10.sql` + `.input.sql`）。

**残留 / 下一步**：**当前无必须做的缺口**，四条已知边界见 `status.md §3.5`；巡检方法见 §9 头部。

## §9.19 诊断（S7 之后）

迁移期探针已随旧 fork 全部删除，`.gitignore` 仍忽略 `_tmp_*` → **诊断脚本一律现场写、用完即删**。
诊断手法（元规则一~七、工作流、坑位）见技能 `sqlfmt-parity`；探针坑位与「直接读树」的写法见
`history.md §9.4`。

---

## §9.20 E2 工具链切 uv + 部署形态改 `uv tool install` 已收（2026-09-16）

**用户原话**：「参考 `C:\_OneDrive\_cloud\5-Project\python\py-dolphin_scheduler\` 的做法，将项目改为 uv 管理，
**不兼容历史**，**不再往 py 主解释器安装**，统一使用 **`uv tool install`** 安装（即本机开发之外也按发布部署形态，
由其它场景调用）」。按本轮问答选定：部署 = **文档一行命令 + VSCode 任务**（`install_to_main.py` 删除）、
tool 解释器**交给 uv 自选**（工作区已 pin `.python-version`）、`--with-deps` 的 pip 用法**保留并登记为声明例外**。

**靶子（四件）**：

① **工具链是 pip 口径**：开发依赖在 `requirements-dev.txt`（`pip install -e .`）、构建走 `pip wheel`、
部署走 `scripts/install_to_main.py` 的 `pip install --force-reinstall` → 与「uv 唯一工具链」的要求相反。
② **部署形态是「往主解释器装」**：E1 的双环境模型把 wheel 装进 `pythoncore-3.14-64`（日常使用与 DBeaver 都指向它），
与「不往全局解释器装包」的环境纪律冲突，也让「本机跑的是哪份代码」依赖某个解释器的状态。
③ **仓库里没有 `uv.lock`**：依赖解析结果不可复现；仓库根的 `.python-version`（3.11）**未跟踪**，
换机器时 uv 选哪个解释器不确定。
④ **dolphin 的 S23 留了一个待验证前提**：其阶段卡明确写着「uv 工具链约定」要**等 `py-sqlfmt_ext` 按同一约定
改造完**再抽成跨项目公共能力 —— 本次正是该提案的验证时机（形态只能是**约定 + 事实清单**，不做成公共包）。

**根因**：

① pip 与 uv 的能力边界不同却混用 —— pip 的 `--force-reinstall` 以**整环境**为粒度（没有「只重装主包」的选项），
「同版本重新部署」必然连带重解析依赖；uv 以**包**为粒度，且原生提供 `tool` 环境（「一个命令 + 独立环境」）。
② 「装主解释器」这套形态的价值来自 pip 的记忆负担（找解释器 / `--find-links` / `--force-reinstall` / 手工自检），
这部分负担 `uv tool install` 原生不存在，于是 `install_to_main.py`（153 行胶水）变成多余的一层。
③ 本阶段是**环境与工程链路**改造，与格式化口径（C1–C5）正交 —— 门槛数字必须与 E1/S16 相同（见 A1），
`sqlfmt_ext/` 与 `tests/` **零改动**。

**改动**（边界，宁少不多）：

| 类别 | 文件 | 动作 |
|---|---|---|
| 依赖 | `pyproject.toml` | 加 `[dependency-groups] dev`（替代 `requirements-dev.txt`）；其余段不动 |
| 依赖 | `requirements-dev.txt` | **删除**（**不留 pip 退路**） |
| 依赖 | `uv.lock` · `.python-version` | **新增并入库**（依赖锁定可复现 + 解释器基线） |
| 构建 | `scripts/build_package.py` | `pip wheel` → `uv build --wheel --out-dir`；加 `_require_uv()`（缺 uv 报错给指引，**不回落 pip**）；`--with-deps` 保留 `python -m pip download` 并注明为**声明例外** |
| 部署 | `scripts/install_to_main.py` | **删除**（部署改 `uv tool install`） |
| 文案 | `sqlfmt_ext/__init__.py` · `conftest.py` | 仅把「依赖缺失提示 / 守卫措辞」改成 uv 口径，逻辑不动 |
| IDE | `.vscode/tasks.json` · `settings.json` | 四任务改 uv（同步 / 构建 / 部署 / 门禁）；删 `sqlfmt.mainEnvPython` |
| 文档 | `README.md` · `AGENTS.md` | 安装 / 使用（含 DBeaver 路径）/ 测试 / 构建与发布 / uv 源与 lock；硬约束新增 **C6** |
| 计划 | `status.md` · `PLAN.md` · `history.md` · 本文件 | 锚点 + 状态表 + 门禁 + 已知边界；风险表；变更记录 |

**验收锚点（E2，期望值）**：

| # | 判据 | 期望 |
|---|---|---|
| A1 | `.venv\Scripts\python.exe -m pytest -q` | **269 passed**（0 failed / 0 xfailed），与 E1/S16 相同 |
| A2 | `uv lock --check` | 退出码 **0** |
| A3 | `uv sync --frozen` | 无变更（不静默改环境） |
| A4 | pip 残留扫描（排除 `.claude/plan/` 历史记录） | 只剩**声明例外**：`build_package.py` 的 `pip download` 与其文档说明 |
| A5 | `uv tool list` / exe 落点 | 含 `sqlfmt_ext v0.1.0`；`%USERPROFILE%\.local\bin\sqlfmt_ext.exe` 存在 |
| A6 | **在项目目录之外**调用该 exe | 输出与门禁 fixture 一致（cwd 在仓库内会命中源码 → 假绿，不算证据） |
| A7 | 主解释器 `pythoncore-3.14-64` | 已**无** `sqlfmt_ext`（不再往主解释器装） |
| A8 | 仓库内 pip 形态残留 | `requirements-dev.txt` / `scripts/install_to_main.py` 已不存在；`sqlfmt.mainEnvPython` 已移除 |

**实测结果**：**A1–A8 全部满足**（逐条证据见下表 #4 / #5 / #6 / #7 / #9 / #10 / #11）。
另**额外达成**：`uv lock --check` 与 `uv sync --frozen` 均无变更；残留扫描把「例外登记指向」也一并补齐。

**回退方式**：整体一次 `git revert`（含恢复 `install_to_main.py` / `requirements-dev.txt` / README / VSCode 任务）；
旧 `.venv`（3.14.3）**改名保留**为 `.venv.bak-3.14`（可逆，非删除）；tool 环境退场 = `uv tool uninstall sqlfmt_ext`；
主解释器卸载的恢复 = 用旧 wheel 重装（`uv pip install --python <主解释器> <旧 wheel>`）。

**证据（实测）**：

| # | 场景 | 结果 |
|---|---|---|
| 1 | `uv --version` / `uv tool list`（改造前） | `uv 0.12.14`；`No tools installed`；用户级 `%APPDATA%\uv\uv.toml` 已存在 |
| 2 | `uv lock`（首次） | **暴露 `requires-python` 声明缺陷**：`No solution found … (markers: python_full_version == '3.9.*')`；实测依赖元数据 `sqlparse-0.6.0.dist-info/METADATA` → `Requires-Python: >=3.10` → 改成 `>=3.10` 后 `Resolved 11 packages` |
| 3 | `uv sync` | `.venv` 重建为 **3.11.9**（`pyvenv.cfg`：`home=…pythoncore-3.11-64`、`uv = 0.12.14`、**无 `Scripts\pip.exe`**）；`sqlfmt-ext==0.1.0` 可编辑装源码；`sqlparse` 来自 `.venv` 的 site-packages |
| 4 | **A1** 门槛 | `.venv\Scripts\python.exe -m pytest -q` → **269 passed**（0 failed / 0 xfailed） |
| 5 | **A2 / A3** | `uv lock --check` 退出码 0（`Resolved 11 packages`）；`uv sync --frozen` → `Checked 8 packages`（无变更） |
| 6 | **A8** 构建 | `python scripts\build_package.py` → 内部 `uv build --wheel --out-dir …` 出 `sqlfmt_ext-0.1.0-py3-none-any.whl`；包内只含 `sqlfmt_ext/**` + dist-info（无 egg-info / pyc）；`finally` 清理后仓库根无 `build/` `dist/` `*.egg-info` |
| 7 | **A5** 部署 | `uv tool install --force --reinstall <wheel>` → `Installed 1 executable: sqlfmt_ext`；`uv tool list` = `sqlfmt-ext v0.1.0`；`%USERPROFILE%\.local\bin\sqlfmt_ext.exe` 存在；tool 环境在 `%APPDATA%\uv\tools\sqlfmt-ext`（其 `pyvenv.cfg` → **3.14.3**） |
| 8 | 同版本重装语义（决定 README 写法） | `uv tool install <wheel>`（**不带 flag**）→ 只 `Checked 2 packages` + 重写可执行文件，**不重装包** ⇒ 同版本重新部署**必须带 `--reinstall`**（README 与 VSCode 任务据此写） |
| 9 | **A6** 项目目录之外自检 | cwd = `%TEMP%`，exe 输出与 `tests/fixtures/cases/ddl/sqltest0_s07.sql` **逐字符一致** |
| 10 | **A7** 主解释器 | `uv pip list --python <主>` 无 `sqlfmt` / `sqlparse`；`…pythoncore-3.14-64\Scripts\sqlfmt_ext.exe` 不存在；项目目录外 `find_spec('sqlfmt_ext')` → `None` ⇒ **主解释器本来就没装过本项目**，无需卸载（原计划的破坏性动作变成空操作） |
| 11 | **A4** 残留扫描（全仓，只读子代理） | 入库现行文件**无**机器 / 个人专属路径；pip 用法只剩声明例外；**修掉 2 处漏网**（`python -m pip install uv` 指引、`pyproject.toml` 注释里的已删文件名）+ **1 处悬空指向**（多处写「登记在 `status.md` §3.5」而该条目当时不存在 → 已补 §3.5 第 9–12 条） |
| 12 | `uv python find` 两处差异（解释 tool 环境为何是 3.14） | 项目内 → `.venv\Scripts\python.exe`；项目外 → `pythoncore-3.14-64` ⇒ `uv tool install` 用**默认发现**的解释器，**不读 `.python-version`**（登记为 `status.md` §3.5 第 9 条） |

**残留 / 下一步**：

- **旧 `.venv`（3.14.3）未删，改名保留为 `.venv.bak-3.14`**（可逆；已忽略，不入库）。新版开发环境已验证
  可用（证据 3/4），确认无问题后**由你删除**该目录即可 —— `uv sync` 能凭 `uv.lock` 重建。
- **DBeaver 的程序路径需你手工改**为 `%USERPROFILE%\.local\bin\sqlfmt_ext.exe`（README 表已更新为新路径；
  旧路径 `…pythoncore-3.14-64\Scripts\sqlfmt_ext.exe` 实测**并不存在**，即原有配置本身未落地）。
- ~~**VSCode「部署」任务与 README 各写一处 wheel 版本号**~~ —— **已于 2026-10-24 关闭**：两处都改成
  **不含版本号**的形态（任务 = `uv tool install --force --reinstall .` 源码直装；README = 一行
  `Get-ChildItem … | Sort-Object LastWriteTime | Select-Object -Last 1` 自动取最新 wheel）；
  `sqlfmt_ext.__version__` 也改成运行期从元数据读（唯一真身 = `pyproject.toml`），不再手写。
- **dev(3.11.9) 与 tool(3.14.3) 解释器不同**：`uv tool install` 不读 `.python-version`（§3.5 第 9 条）。
  要让二者一致就加 `--python`；本次按用户口径「交给 uv 自选」**不加**。
- **`--with-deps` 仍用 `python -m pip download`**：全项目唯一保留的 pip 用法（§3.5 第 10 条），别顺手「统一」掉。
- **仓库根游离文件 `主动修改列表,其它为格式差异.txt`** 含机器路径与旧仓库名（`C:\_Dev\python\venv-vsc\…`、
  `py-sqlfmt`）：**本阶段未引入**，按「既有文件只提示不删」处理 —— 是否入库由你定。
- 本阶段**没有**动 `sqlfmt_ext/` 与 `tests/` 任何一行（C1–C5 继续成立），门槛数字与 E1/S16 相同。

## §9.21 S17 已收（2026-10-11）：独立 `@` 定制行原样保留

**缺口**：用户给出的 `@DWS.OA_AI_CREDIT_USAGE_F.sql` 与 `@DWS.OA_AI_CREDIT_QUOTA_F.sql` 被格式化器合并到同一行。

**原因**：这类独立 `@` 行是定制指令，不是待布局的 SQL；普通语句流水线会将它们作为相邻 token 处理。

**改动**：`stack.py` 在 `format_sql` 与 `format_statements` 入口共享按物理行隔离逻辑；独立且去除前导空格后以 `@` 开头的整行保持原文，其余片段继续走对应原格式化路径。测试覆盖两个入口、用户示例、带外围空格的 `@` 行及相邻 SQL。

**证据 / 验收**：原始示例探针中两条引用分别保留；窄测试 `18 passed`；全量门禁 `271 passed`（0 failed / 0 xfailed）。

**残留 / 下一步**：无。S17 之后暂无待推进阶段；下次发现新缺口时先按巡检要求复现并另开阶段卡。

**回退方式**：回退 `stack.py` 的入口隔离逻辑、`test_layout_variants.py` 的回归测试及 S17 阶段记录即可。

## §9.22 S18 已收（2026-10-24）：`over` 前夹注释时的分组时序

**缺口**（用户样例 `C:\Users\lilj7\Desktop\over格式.sql`）：`sum(…) --` 后面的 `over(…)` 排在
标准缩进（列 13），而 `first_value(…) --` 后面的 `over(…)` 被顶到列 93：

```text
       first_value(Amount_DQYE)                                                              --
                                                                                             over(partition by AccCompanyCode,
```

用户口径：「`first_value` 后的 `over` 与 `sum` 后的**一样**，在注释换行后按标准长度缩进对齐」。

**原因**（元规则一：列对齐错乱先怀疑分组）：三张 `/` 两张列表。官方 `align_comments` 把
「`)` 与 `over` 之间」的注释并进前一个 `Function` 末尾
（`Function[Identifier, Parenthesis, ws, Comment]`），于是
- `_group_level` 看不到「`Function` + 注释 + `Over`」这个形状 → `over(…) as x` 被当成**新列表项的开头**，
  字段列表在 `first_value(…)` 处被**切成两张**；
- 两张列表各自算 `as` / 别名列基准 → 第二张的基准被其余长项抬高，`over` 落到列 93；
- U14（`_attach_over_to_functions`）原守卫要求「`Function` 末尾是 `Parenthesis`」且「锚点与 holder
  之间**本层**存在注释」——注释在 `Function` 内部，两条都不成立，且它当时排在 `_walk` **之后**，
  列表早已切完，命中了也补不回来。

**改动**（`sqlfmt_ext/grouping.py`，两个函数 + 一行调用）：
1. 新增 `_trailing_comment_run(fn)`：识别「`Function` 末尾 `Parenthesis` + 空白 + 注释」
   这一形态（返回末尾注释个数，`0` = 不是这形态）。
2. `_attach_over_to_functions` 的守卫放宽：本层注释段为空但 `Function` 末尾是上条形态时同样成立
   （注释已经在 `Function` 里，搬 `Over` 时顺序自然正确：`Function[…, Parenthesis, ws, Comment, ws, Over]`）。
3. `group()` 在 `official.group(stmt)` **之后、`_walk` 之前**先调用一次
   `_attach_over_to_functions`；末尾那次保留（`_normalize_adjacent_lists` 并回后才凑形的
   `nested/sqltest3_s01` 靠它）。

**证据**（同一份用户样例，修复前 → 修复后）：
```text
       first_value(Amount_DQYE) --                                        ← 注释回到行内
             over(partition by AccCompanyCode, AccDeptCode, VendorCode, --
                               Account_type order by PERIOD_ID desc) as Amount_DQYE_first  , -- 基准月原始期末余额
```
`over` 由列 93 → 列 13（与 `sum` 那条相同），`partition by` 列表与 `Account_type` 也回到 31 列。

**验收**：新增 `cases/window/sqltest6_s04.sql`（实跑输出定稿）+ `.input.sql`（用户原始输入）；
原 271 项**一项没动**，门槛 **276 passed**（0 failed / 0 xfailed）；
样例幂等 + 收敛（压平输入）均为真。

**残留 / 下一步**：
- 隐式别名形（`row_number() /*c*/ over(…) rn`）仍**不幂等** —— 实测**改动前就如此**，非本阶段引入，
  未修（见 `status.md` §3.5 第 13 条）。
- 未动 U14 的其余判据（多词/无别名形）与 layout 层；本阶段只改分组时序。

**回退方式**：`git revert` 单个提交（`grouping.py` 的 `_trailing_comment_run` + 守卫 + 提前调用，
及 `cases/window/sqltest6_s04*` 两个 fixture）。
