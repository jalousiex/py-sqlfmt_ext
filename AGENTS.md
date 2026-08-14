# AGENTS.md — py-sqlfmt AI 指令

基于 `sqlparse` 二次定制的 SQL 格式化工具。详细说明见 [README.md](README.md)。

## 架构

```
sqlfmt.py → sqlparse.format()
  → lexer.tokenize()        # 正则分词 → Token 流
  → StatementSplitter       # 按 ; 分割语句
  → grouping.group()        # 语法分组 → Token 树
  → AlignedIndentFilter     # 核心：深度优先遍历，关键字前换行+缩进
```

## 关键文件

| 文件 | 职责 |
|------|------|
| `sqlfmt.py` | 入口，`sqlfilefmt()` 拆分语句后逐条格式化，`.strip()` 后用 `\n\n` 拼接 |
| `sqlparse/filters/aligned_indent.py` | 核心对齐逻辑，`_process()` 按 Token 类型分发处理 |
| `sqlparse/filters/reindent.py` | 缩进宽度调整 |
| `sqlparse/keywords_list.py` | `split_words` 定义哪些关键字前换行 |
| `sqlparse/engine/grouping.py` | Token 流 → 树形结构（Statement/IdentifierList/Function/Parenthesis 等） |

## 默认格式化参数

`keyword_case=lower`, `indent_width=4`, `reindent_aligned=True`, `wrap_after=30`, `use_space_around_operators=True`, `comma_align=True`

定义在 `sqlfmt.py` 的 `DEFAULT_OPTIONS` 字典中。

## 测试约定

- `pytests/fixtures/cases/<topic>/*.sql` — fixture 文件**即期望输出**，测试验证幂等性
- 新增用例：在对应 `cases/<topic>/` 下添加 `.sql` 文件，在 `pytests/fixtures/sql_cases.py` 的 `TOPIC_META` 中注册 topic
- 需要非默认选项的用例：在 `FILE_OPTIONS` 中按文件名映射选项
- 运行测试：`python -m pytest pytests/ -v`
- 筛选用例：`SQLFMT_CASE_TAGS=comma python -m pytest pytests/ -v`

## 项目约定

- 低频参数不做 CLI 参数，优先用 `DEFAULT_OPTIONS` 模块级变量
- 不要自动创建 venv，复用现有 `.venv`
- 无风险只读命令改动后直接终端验证，不等确认
- 不修改工作区外文件