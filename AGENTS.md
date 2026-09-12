# AGENTS.md — py-sqlfmt AI 指令

基于 `sqlparse` 二次定制的 SQL 格式化工具。详细说明见 [README.md](README.md)。

> **正在进行重构**：目标形态是「官方 sqlparse 之上的小侵入外挂」。
> 计划、步骤拆分与验收标准见 [PLAN.md](PLAN.md)。
> 迁移期新实现位于 `sqlfmt_ext/`，对拍进度条跑 `pytest tests_migration/ -q`。
>
> ⚠️ 迁移期有**两个** `sqlparse`：仓库内旧 fork（`tests/` 用）与 `.venv` 里的
> 官方包（`tests_migration/` 用）。**必须分开跑**，同一次 pytest 会话里混跑会被
> 直接拦截报错——同进程只能加载一个。

## 架构

**迁移期（当前形态）**：`sqlfmt_ext/` 是唯一实现，跑在 `.venv` 的官方 `sqlparse 0.6.0` 之上。

```
sqlfmt.py → format_statements()
  → DialectLexer            # 官方词表 + Doris 分词补丁（policy.py）
  → StatementSplitter       # 按 ; 分割语句（官方）
  → grouping.group()        # 官方分组 + 本项目口径补偿（grouping.py）
  → StripWhitespaceFilter   # 官方 strip；之前先合并逐字符空白（whitespace.py）
  → LayoutPass              # 唯一换行/缩进决策处（passes/layout.py + passes/align.py）
```

**旧形态（仅作行为 oracle，S7 删除）**：`sqlparse/` 里的 fork，
`sqlfmt.py → sqlparse.format()`，核心是把 `AlignedIndentFilter` 改成
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

**元规则二：定性先写最小重现**（`_tmp_cmp.py --fork/--new "<片段>"`），别拿整条 fixture 下结论。

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
| `sqlparse/` | 旧 fork，迁移期只作行为 oracle，**不要改**（S7 删除） |

## 默认格式化参数

`keyword_case=lower`, `indent_width=4`, `reindent_aligned=True`, `wrap_after=30`, `use_space_around_operators=True`, `comma_align=True`

定义在 `sqlfmt.py` 的 `DEFAULT_OPTIONS` 字典中。

## 测试约定

- 用例目录是 **`tests/`**（不是 `pytests/`）：`tests/fixtures/cases/<topic>/*.sql` — fixture 文件**即期望输出**，测试验证幂等性
- 新增用例：在对应 `cases/<topic>/` 下添加 `.sql` 文件，在 `tests/fixtures/sql_cases.py` 的 `TOPIC_META` 中注册 topic
- 需要非默认选项的用例：在 `FILE_OPTIONS` 中按文件名映射选项
- 主套件（旧 fork）：`.venv\Scripts\python.exe -m pytest tests/ -q` — **必须保持 `170 passed, 6 xfailed`**
- 对拍进度条（新外挂）：`.venv\Scripts\python.exe -m pytest tests_migration/ -q` — `xfail(strict=True)`，修好一个就从 `KNOWN_DIFF` 删掉
- 两个套件**不要在同一次 pytest 会话里跑**（`tests_migration/conftest.py` 的 `sys.path` 调整是进程级副作用）
- 筛选用例：`SQLFMT_CASE_TAGS=comma .venv\Scripts\python.exe -m pytest tests/ -v`

## 诊断工具（迁移期临时脚本，未跟踪；S7 统一删除）

| 脚本 | 用途 |
|---|---|
| `_tmp_check.py [-v] [用例名]` | 逐用例首 2 处差异 + 「是否只是空白宽度」，看全局格局 |
| `_tmp_cmp.py --fork/--new "<片段>"` | 两侧**输出**对照 |
| `_tmp_nt.py "<片段>"` / `_tmp_forkidx.py` | 两侧 **token 树** dump（都支持 `@相对路径`） |
| `_tmp_align_probe.py --fork/--new @fixture` | **列对齐中间量**：`[layouts]` 的 `max_as_offset`/`max_alias_len`／每项 `as_offset`／`[apply]` 前后文本 |
| `_tmp_ddlprobe.py --fork/--new @fixture` | **DDL 字段列**中间量：`field_lines`／每列 `max_offset`／每个 token 的 offset |
| `_tmp_lv.py "<片段>"` | 语句层每个 token 对 `split_words` 的命中（查「关键字没触发换行」） |

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