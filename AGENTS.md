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
**元规则二：任何结论都要写成最小重现**（`_tmp_cmp.py --fork/--new "<片段>"`），
不要拿整条 fixture 下结论——历史上两次误判根因都是这么来的。

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

`_tmp_check.py`（逐用例首 2 处差异 + 「是否只是空白宽度」，`-v` 看全量）·
`_tmp_cmp.py --fork/--new "<片段>"`（两侧输出对照）·
`_tmp_nt.py` / `_tmp_forkidx.py`（两侧 token 树 dump）。

**踩过的坑**：`FilterStack.run(sql)` 返回**生成器**，不消费等于没跑；
fork 与新实现必须**两次独立进程**跑（同进程只能加载一个 `sqlparse`，fork 侧脚本要显式传 `align_list=True`）；
比对不能只比「非空白 token 序列」（格式化不重排 token，恒等），要比「行内容」才能分离换行位置差异。

## 项目约定

- 低频参数不做 CLI 参数，优先用 `DEFAULT_OPTIONS` 模块级变量
- 不要自动创建 venv，复用现有 `.venv`
- 无风险只读命令改动后直接终端验证，不等确认
- 不修改工作区外文件