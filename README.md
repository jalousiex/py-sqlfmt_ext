# py-sqlfmt

基于官方 `sqlparse` 的 SQL 格式化工具：**不改官方源码**，把团队口径做成一层外挂补偿
（`sqlfmt_ext/`），固化默认参数，并用回归 / 收敛 / 幂等三类用例钉住输出稳定。
优先支持 Doris / SelectDB 方言（`dialect="doris"`）。

## 安装

```bash
pip install -e .          # 依赖 sqlparse>=0.6,<0.7（见 pyproject.toml）
```

## 使用

```bash
# 格式化单文件（输出到 stdout）
python sqlfmt.py path/to/file.sql

# 递归格式化目录
python sqlfmt.py path/to/sql-dir

# 原地回写
python sqlfmt.py path/to/file.sql --in-place

# 库内调用
python -c "from sqlfmt_ext import format_statements; print(format_statements('select 1'))"
```

## 测试

```bash
python -m pytest -q
```

覆盖四类：用例完整性、格式化输出回归（fixture 即期望）、收敛性（压平输入空白后输出不变）、
幂等性（二次格式化不变）。

## 目录

| 路径 | 说明 |
|------|------|
| `sqlfmt.py` | CLI 入口（薄壳：默认参数 + 读取/回写文件） |
| `sqlfmt_ext/` | 补偿层：官方 filter 的替换/追加 + 本项目 pass（分组、布局、对齐、分词兜底） |
| `tests/` | pytest 测试与 SQL 夹具（`tests/fixtures/cases/<topic>/*.sql`） |

---

## AI 指引

### 架构概要

```text
sqlfmt.py → sqlfmt_ext.format_statements()
  → 官方 lexer.tokenize()        # 正则分词（DialectLexer 追加方言词表）
  → 官方 StatementSplitter       # 按 ; 分割语句
  → sqlfmt_ext.grouping.group()  # 官方分组 + 本项目补偿（见下）
  → sqlfmt_ext.passes.layout     # 核心：深度优先遍历，关键字前换行 + 缩进
  → sqlfmt_ext.passes.align      # 列表 AS / 别名列对齐
  → 官方 SerializerUnicode
```

**硬约束**：不修改官方 `sqlparse` 源码（用替换 filter / 追加 pass / 事后补偿实现），
不靠删除或改写非空白 token、不靠重排 token 来对齐。

### 关键文件

- `sqlfmt.py` — CLI 入口；`sqlfilefmt()` 拆分语句后逐条格式化，`.strip()` 后用 `\n\n` 拼接
- `sqlfmt_ext/passes/layout.py` — 核心布局：`_process()` **按组类名分发**（`_process_{cls}`），
  所以任何「把括号包进别的组」的补偿都会改变这里收到的组
- `sqlfmt_ext/passes/align.py` — 列对齐（`_identifier_layouts` / `_create_field_lines`）
- `sqlfmt_ext/grouping.py` — 官方 `grouping` 之后的补偿（`_wrap_create_table_calls` /
  `_attach_over_to_functions` / `_extend_adjacent_lists` / `_trim_clause_tail` 等，
  每处 docstring 都写明「为什么需要」与「为什么放这个位置」）
- `sqlfmt_ext/lexer.py` · `sqlfmt_ext/stack.py` — `DialectLexer`；复用官方 `build_filter_stack` 后**换装 / 摘除** filter
- `sqlfmt_ext/filters/` — 替换官方的空白 / 操作符 filter
- `sqlfmt_ext/policy.py` — 关键字与多词关键字口径（含方言补充，如 `DATETIME`）
- `sqlfmt_ext/options.py` — 默认参数与校验（扩展项 `align_list` / `dialect`）

`PLAN.md` 记录了「官方 0.6.0 与旧 fork 的语义差异清单（U1–U16）」、每处补偿的落点与
时序约束，以及迁移收口（S1–S7）与后续阶段（S9 注释断行的结构性口径）的进展。

### 测试约定

- `tests/fixtures/cases/` 下的 `.sql` 文件**即期望输出**（同时作为输入，除非同目录存在
  `<name>.input.sql`）；新增用例只需加 `.sql` 文件，无需改测试代码
- 新 topic 在 `tests/fixtures/sql_cases.py` 的 `TOPIC_META` 注册；需要非默认选项的用例在
  同文件的 `FILE_OPTIONS` 里按文件名映射
- 按标签筛选用例：`SQLFMT_CASE_TAGS=comma python -m pytest -v`
- 收敛 / 幂等门禁里的 `KNOWN_DIVERGENT` 每项都必须写清原因；修好一项就删一项
  （`xfail(strict=True)` 会在修好时主动报错提示）
- 仓库根 `conftest.py` 会校验 `sqlparse.__file__` 来自 site-packages —— 防止「仓库内 vendored 包
  遮蔽官方包」的老问题复发
- 门槛：**`175 passed, 1 xfailed`（0 failed）**；那 1 个 xfail 是收敛门禁里已登记的
  「输出仍依赖输入空白」用例

### 默认格式化参数

`keyword_case=lower`、`indent_width=4`、`reindent_aligned=True`、`wrap_after=30`、
`use_space_around_operators=True`、`align_list=True`（扩展项）、`dialect="doris"`（扩展项）

低频参数**不做 CLI 参数**，优先改 `sqlfmt_ext/options.py` 的模块级默认值。
