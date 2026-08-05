# py-sqlfmt

基于 `sqlparse` 二次定制的 SQL 格式化工具，固化团队默认参数，维护回归用例确保输出稳定。

## 使用

```bash
# 格式化单文件（输出到 stdout）
python sqlfmt.py path/to/file.sql

# 递归格式化目录
python sqlfmt.py path/to/sql-dir

# 原地回写
python sqlfmt.py path/to/file.sql --in-place
```

## 测试

```bash
python -m pytest tests/ -v
```

测试覆盖三类：用例完整性、格式化输出回归、幂等性。详细约定见 `tests/README.md`。

## 目录

| 路径 | 说明 |
|------|------|
| `sqlparse/` | 官方 sqlparse 源码 + 本地定制 |
| `sqlfmt.py` | 项目入口，封装默认参数 |
| `tests/` | pytest 测试与 SQL 夹具 |

---

## AI 指引

### 架构概要

```
sqlfmt.py → sqlparse.format()
  → lexer.tokenize()        # 正则分词 → Token 流
  → StatementSplitter       # 按 ; 分割语句
  → grouping.group()        # 语法分组 → Token 树
  → AlignedIndentFilter     # 核心：深度优先遍历，关键字前换行+缩进
```

### 关键文件

- `sqlfmt.py` — 入口，`sqlfilefmt()` 拆分语句后逐条格式化，`.strip()` 后用 `\n\n` 拼接
- `filters/aligned_indent.py` — 核心对齐逻辑，`_process()` 按 Token 类型分发处理
- `filters/reindent.py` — 缩进宽度调整
- `keywords_list.py` — `split_words` 定义哪些关键字前换行
- `engine/grouping.py` — Token 流 → 树形结构（Statement/IdentifierList/Function/Parenthesis 等）

### 测试约定

- `tests/fixtures/cases/` 下的 `.sql` 文件**即期望输出**，测试验证幂等性（格式化后期望输出不变）
- 新增用例只需在对应 `cases/<topic>/` 下添加 `.sql` 文件，无需改测试代码
- `TOPIC_META` 在 `tests/fixtures/sql_cases.py` 中注册新 topic

### 默认格式化参数

`keyword_case=lower`, `indent_width=4`, `reindent_aligned=True`, `wrap_after=30`, `use_space_around_operators=True`