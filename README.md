# py-sqlfmt 项目定位

这是一个基于官方 `sqlparse` 包进行二次定制的 SQL 格式化项目。
仓库内保留了 `sqlparse/` 源码结构，并在根目录提供了 `sqlfmt.py` 作为项目侧格式化入口，便于直接按当前团队约定的默认参数执行格式化。

当前内置基础版本可见于 `sqlparse/__init__.py`，版本号为 `0.5.3`。

## 项目定位

本项目不是重新实现 SQL parser，而是在官方 `sqlparse` 能力之上做工程化落地：

1. 保留官方包目录，方便继续跟踪上游实现。
2. 通过 `sqlfmt.py` 固化默认格式化参数，减少日常手工传参。
3. 使用 `unittest` + 文件夹夹具维护回归用例，确保格式化输出稳定。

## 当前默认格式化行为

`sqlfmt.py` 中封装的 `sqlfmt()` / `sqlfilefmt()` 默认使用以下关键选项：

1. 关键字转小写：`keyword_case="lower"`
2. 缩进宽度：`indent_width=4`
3. 对齐重排：`reindent_aligned=True`
4. 每行换行阈值：`wrap_after=30`
5. 操作符两侧加空格：`use_space_around_operators=True`

说明：目录输入时会递归回写文件；单文件输入时输出到标准输出。

## 在 VS Code 中运行 unittest

仓库已配置为使用 Python 扩展的 `unittest` 发现机制，相关设置位于 `.vscode/settings.json`。

当前配置要点：

1. 启用 `unittest`，关闭 `pytest`
2. 测试目录为 `tests`
3. 测试文件模式为 `test_*.py`
4. 工作目录固定为工作区根目录

在 VS Code 中可直接使用：

1. Testing 视图进行测试发现与执行
2. 编辑器中的运行测试按钮执行单个测试文件或测试类

## 命令行运行测试

在项目根目录执行：

```bash
python -m unittest discover -s tests -p "test_*.py"
```

当前测试覆盖三类校验：

1. 用例完整性校验
2. 格式化输出回归校验
3. 幂等性校验

详细测试约定见 `tests/README.md`。

## 目录说明

1. `sqlparse/`：官方 `sqlparse` 包源码及本地定制实现
2. `sqlfmt.py`：项目入口，封装默认格式化参数
3. `tests/`：`unittest` 测试与 SQL 夹具
4. `.vscode/settings.json`：VS Code 测试发现配置

## 常用示例

格式化单个 SQL 文件：

```bash
python sqlfmt.py path/to/file.sql
```

递归格式化目录内文件：

```bash
python sqlfmt.py path/to/sql-dir
```

# py-sqlfmt 项目实现逻辑说明

## 1. 整体架构

```
sqlfmt.py (入口)
  └─ sqlparse.format() → formatter.py
       ├─ validate_options()     # 校验选项
       └─ build_filter_stack()   # 构建过滤器链
            └─ FilterStack.run()
                 ├─ lexer.tokenize()        # 词法分析 → Token 流
                 ├─ StatementSplitter       # 按 ; 分割语句
                 ├─ grouping.group()        # 语法分组 → Token 树
                 └─ 过滤器链处理每个 Statement:
                      ├─ StripWhitespaceFilter
                      └─ AlignedIndentFilter  ← 核心对齐逻辑
```

## 2. 核心流程

### 2.1 词法分析 (lexer.py)
- 基于正则 `SQL_REGEX` 将 SQL 文本拆分为 Token 流
- 每个 Token 有 `ttype`（类型）和 `value`（值）
- 关键字通过 `keywords.py` 中的字典识别，赋予对应 `ttype`（如 `T.Keyword.DML`, `T.Keyword`, `T.Name.Builtin` 等）

### 2.2 语法分组 (engine/grouping.py)
- 将扁平的 Token 流组织成树形结构
- 关键分组类型（定义在 `sql.py`）：
  - `Statement` — 顶层语句
  - `Identifier` — 标识符（表名、列名、别名等）
  - `IdentifierList` — 逗号分隔的标识符列表（SELECT 列、FROM 表）
  - `Function` — 函数调用 `func(args)`
  - `Parenthesis` — 括号 `(...)`
  - `Where` — WHERE 子句
  - `Case` — CASE WHEN 表达式
  - `Comparison` — 比较表达式
  - `Over` — OVER 窗口子句
  - `Comment` — 注释

### 2.3 对齐过滤器 (filters/aligned_indent.py) — 核心

`AlignedIndentFilter` 是格式化对齐的核心，通过**深度优先遍历** Token 树实现。

#### 关键属性
- `self.indent` — 缩进层级（每层 = `len("select")` = 6 个空格）
- `self.offset` — Token 级对齐偏移（用于对齐到特定列）
- `self.leading_kwd = "select"` — 基准关键字，决定缩进单位宽度
- `self.char` — 缩进字符（空格）

#### `leading_ws` 属性
```python
self.offset + self.indent * len(self.leading_kwd)
```
即：基础偏移 + 缩进层级 × 6

#### `nl(offset)` 方法
```python
def nl(self, offset=1):
    offset = -len(offset) if not isinstance(offset, int) else offset
    return Token(Whitespace, '\n' + ' ' * (self.leading_ws + offset))
```
- `offset` 为字符串时：右对齐（扣除该字符串长度）
- `offset` 为整数时：左对齐偏移量
- 默认 `offset=1` 表示 SELECT 后空一格

#### 上下文管理器
- `indent(self, n=1)` — 临时增加缩进层级
- `offset(self, n=0)` — 临时增加 Token 偏移

#### 处理入口
```python
def process(self, stmt):
    self._curr_stmt = stmt
    self._process(stmt)  # 按类型分发
```

#### 类型分发 `_process()`
```python
def _process(self, tlist):
    func_name = "_process_{cls}".format(cls=type(tlist).__name__.lower())
    func = getattr(self, func_name, self._process_default)
    func(tlist)
```

已实现的处理方法：
| 方法 | 处理类型 | 职责 |
|------|---------|------|
| `_process_statement` | Statement | 清理首行空白，委托给 default |
| `_process_parenthesis` | Parenthesis | 括号内缩进、子查询处理、DDL 字段对齐 |
| `_process_identifierlist` | IdentifierList | 逗号分隔列表的换行对齐、AS/逗号对齐 |
| `_process_case` | Case | CASE WHEN THEN ELSE END 对齐 |
| `_process_function` | Function | 函数内注释处理 |
| `_process_comment` | Comment | 强制换行注释 `/*-*/`、单行注释对齐 |
| `_process_default` | 默认 | 遍历 split_words 关键字换行 + 递归子组 |

#### `_process_default` 流程
```
with indent(self):           # 缩进+1
    _split_statements(tlist) # DDL/DML/CTE 前换行
    _split_kwds(tlist)       # split_words 关键字前换行
# 递归处理子组
for sgroup in tlist.get_sublists():
    _process(sgroup)
```

#### `_split_kwds` — 关键字换行
遍历 `split_words` 中定义的关键字（FROM, WHERE, JOIN, AND, OR 等），在每个关键字前插入换行 + 缩进。关键字本身的文本长度会被扣除（右对齐效果）。

#### `_split_statements` — 语句分割
在 DDL/DML/CTE 关键字前插入换行。

### 2.4 关键字列表 (keywords_list.py)

```python
split_words = (
    "FROM",           # 匹配 FROM 关键字
    join_words,       # 匹配各种 JOIN
    by_words,         # 匹配 GROUP BY, ORDER BY
    "WHERE", "AND", "OR", "HAVING", "LIMIT",
    "UNION", "VALUES", "SET", "BETWEEN", "EXCEPT",
    ...
)
```

`_split_kwds` 使用 `_next_token()` 在 Token 树中**深度优先**搜索匹配 `split_words` 的关键字 Token，并在其前插入换行。

## 3. 关键数据流

```
SQL 文本
  → lexer: Token 流 (ttype + value)
  → grouping: Token 树 (Statement > IdentifierList > Identifier > Function > Parenthesis > ...)
  → AlignedIndentFilter.process():
     深度优先遍历 Token 树
     在每个节点按类型分发处理
     关键字前插入换行+缩进
     括号内增加缩进层级
     列表元素对齐
  → 格式化后的 Statement
  → str(statement) → 输出
```

## 4. 缩进计算示例

假设 `indent=1, offset=0`：
- `leading_ws = 0 + 1*6 = 6`
- `nl(0)` = `\n` + 6 空格 → 关键字对齐到 SELECT 后
- `nl("FROM")` = `\n` + (6-4) = 2 空格 → FROM 右对齐（扣除自身长度）
- `nl(1)` = `\n` + 7 空格 → 比关键字多缩进 1

## 5. 当前 lateral view 的问题

`LATERAL VIEW` 在 `keywords.py` 中被识别为单个 Keyword token（`lateral view explode`），但它**不在 `split_words` 列表中**，因此 `_split_kwds` 不会在它前面插入换行。

同时，在 grouping 后，`lateral view explode(...)` 被组织为 FROM 子句 Identifier 内的嵌套 Function，而不是独立的顶层关键字。

**解决方案**：将 `LATERAL\s+VIEW` 加入 `split_words`，使其像 FROM、WHERE 一样自动换行对齐。