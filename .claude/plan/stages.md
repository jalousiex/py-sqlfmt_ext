# 阶段卡 — 断点卡与各阶段记录

> 本文件 = 每阶段的**断点续做卡**（原 `PLAN.md` §9）。**章号沿用原编号** ——
> 代码注释与技能里的 `PLAN §9.x` 引用**指本文件同号小节**（§9.3 / §9.4 已归档到 `history.md`）。
> 阶段状态与门槛数字以 `status.md` 为准；硬约束见 `PLAN.md` §1；差异机理见 `diffs.md`。
>
> **开工第 1 步读这里**（§9 断点卡的「下一步开工点」）；**收工第 2 步刷新这里**。

---

## §9 断点卡

> 落盘时间：2026-09-13（S16 收工刷新）。
> **S1–S7、S9、S10、S10-b、S8-a~d、S11–S16 全部完成**，门槛与 `KNOWN_DIVERGENT` 现状见 `status.md §3`。

**方言优先级（用户口径，2026-09-13 定）**：**Doris / SelectDB 最优先 → 其次 MySQL →
Oracle / SQL Server 暂缓不做**。S8-a~d 至此全部收：Doris/SelectDB 与 MySQL 已适配；
SQL Server（S8-c）已完成并保留（不回退、也不再往前推）；Oracle 未开工。

**下一步开工点**：方言路线已走完，S11–S16 已收。**当前无「必须做」的缺口**，
剩下的都是**登记在案的已知边界**（都不影响现有 fixture，各自需先开新阶段卡再动手），
清单见 `status.md §3.5`；写卡前请先做下面这条巡检。

**巡检结论（2026-09-13，S16 期间做的一轮）**：拿一段真实风格的 Doris 建表 + CTE/窗口/`case`/`having`
查询跑过，输出与既有 fixture 口径**逐项一致**，没有发现新缺口。两处「看着不齐」的形态是**既定口径**，
不是缺陷：①`having` / `comment` 顶列 0 —— 锚点关键字**右端对齐到 `leading_ws`（6）**，7/6 字符的关键字
恰好落到列 0（与 `ddl/sqltest0_s06` 的 `comment` 一致）；②CTE 体的 `select` 顶列 0（见 `cte/sqltest2_s01`）。
**要开新阶段就别再靠「感觉」找靶子**：先拿真实语料跑一遍并与既有 fixture 口径对照，确认是**新缺口**
再写卡（参考技能 `sqlfmt-parity` 的元规则一~七）。

## §9.1 复现当前状态

```powershell
.venv\Scripts\python.exe -m pytest -q                   # 门槛数字见 status.md §3.1
.venv\Scripts\python.exe -m pytest -q -k convergence    # 只看收敛门禁
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
