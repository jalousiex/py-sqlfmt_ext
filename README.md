# sqlfmt_ext

`sqlfmt_ext` 是一个基于官方 `sqlparse` 的 SQL 格式化工具。它以**无侵入**的外挂方式扩展了官方功能，固化了符合团队习惯的美化与缩进规则，并原生支持 **Doris / SelectDB** 等现代数据仓库 SQL 方言。

---

## ✨ 核心特性

- 🎯 **无侵入扩展**：不修改、不复制 `sqlparse` 源码，在保持语义与词法安全的前提下实现精致排版。
- 🚀 **现代方言支持**：
  - **Doris / SelectDB**（默认）：支持建表模型定义（如 `DUPLICATE KEY`、`DISTRIBUTED BY`）、数据类型及计算语法。
  - **MySQL**：适配建表类型名、表选项换行与 `ON DUPLICATE KEY UPDATE` 子句。
  - **SQL Server**：支持 `GO` 批分隔符、`TOP` 及 `WITH(NOLOCK)`。
- 📐 **精细化对齐**：支持 SELECT 表达式 AS 别名列对齐、括号内字段列表智能展开与缩进。
- 🔒 **收敛与幂等**：内置严苛的测试用例，确保多次格式化结果完全一致（幂等性）且不依赖输入空白。

---

## 📦 安装与部署

本项目统一使用现代 Python 包管理工具 [uv](https://github.com/astral-sh/uv) 进行环境与部署管理。

### 1. 作为全局 CLI 工具安装（推荐）

打包出 wheel 后安装到全局隔离环境，命令行随时可用：

```powershell
# 安装到全局隔离 tool 环境
uv tool install .

# 构建打包
uv run python scripts/build_package.py

# 分发whl后安装
uv tool install --force --reinstall "scripts/output/wheels/wheelhouse/sqlfmt_ext-0.1.0/sqlfmt_ext-0.1.0-py3-none-any.whl"
```

安装完成后，命令行可以直接调用 `sqlfmt_ext`（自动写入用户 PATH 环境变量）。

### 2. 作为项目本地开发环境

在克隆仓库后，一键建环境并同步依赖：

```powershell
# 初始化并同步本地 3.11 开发环境（.venv）
uv sync

# 检出即复现（要求与 uv.lock 严格一致）
uv sync --frozen

# 在其它项目中安装源码联动版本
uv tool install --editable ./path-to-project
```

### 3. 断网机器离线安装

打包产物是纯 Python 的 `py3-none-any` wheel，Windows / Linux / 架构通用，唯一硬性要求是
目标机 **Python ≥ 3.10**（sqlparse 0.6.0 的 Requires-Python 下限）。

`scripts/build_package.py --with-deps` 产出的离线 zip（如 `sqlfmt_ext-0.1.0-py3-none-any.zip`）
内含主包与依赖两个 wheel，两条安装路径任选：

**路径 A —— 目标机有 pip（推荐，装完有 `sqlfmt_ext` 命令）**

把 zip 拷到断网机，解包成一个目录，用 `--no-index` 让 pip 只查本地目录、绝不联网：

```powershell
# Windows
Expand-Archive -Path sqlfmt_ext-0.1.0-py3-none-any.zip -DestinationPath sqlfmt_wheels
py -m pip install --no-index --find-links sqlfmt_wheels
sqlfmt_ext --help
```

```bash
# Linux
mkdir -p ~/sqlfmt_wheels && unzip -o sqlfmt_ext-0.1.0-py3-none-any.zip -d ~/sqlfmt_wheels
python3 -m pip install --no-index --find-links ~/sqlfmt_wheels sqlfmt_ext
sqlfmt_ext --help
```

两个 wheel 在同一目录，`--no-index` 会从本地解析依赖（sqlparse 一并安装），全程不碰网络。

**路径 B —— 目标机完全没有 pip（纯解包，`python -m` 方式）**

wheel 本质是 zip，纯 Python 包可直接解包进环境，不经过 pip：

```powershell
# Windows：解包进当前解释器的 site-packages（语义等同 pip 安装）
py -c "import zipfile,site; [zipfile.ZipFile(f).extractall(site.getsitepackages()[0]) for f in ['sqlfmt_ext-0.1.0-py3-none-any.whl','sqlparse-0.6.0-py3-none-any.whl']]"
py -m sqlfmt_ext --help
```

```bash
# Linux：解包到任意目录后用 PYTHONPATH 指过去（解 zip 即等于解了两个 wheel）
mkdir -p ~/sqlfmt_ext && unzip -o sqlfmt_ext-0.1.0-py3-none-any.zip -d ~/sqlfmt_ext
export PYTHONPATH=~/sqlfmt_ext
python -m sqlfmt_ext --help
```

> 路径 B 没有 `sqlfmt_ext` 命令（入口点由 pip 注册），统一走 `python -m sqlfmt_ext`；
> [sqlfmt_ext/__main__.py](./sqlfmt_ext/__main__.py) 与 console script 共享同一份 CLI 实现，行为一致。

---

## 💡 使用指南

### 命令行 (CLI)

在全局安装后可直接使用 `sqlfmt_ext`，在开发仓库内可以通过 `uv run` 调度：

```powershell
# 查看帮助与参数选项
sqlfmt_ext --help

# 格式化单文件（结果输出到 stdout）
sqlfmt_ext path/to/file.sql

# 格式化目录下所有 SQL 文件
sqlfmt_ext path/to/sql-dir/

# 原地回写（直接覆盖原文件）
sqlfmt_ext path/to/file.sql --in-place

# 开发环境下指定方言与关键字大小写格式化
uv run python -m sqlfmt_ext.cli path/to/file.sql -k upper
```

#### 常用 CLI 参数

| 参数 | 说明 | 示例 / 可选值 |
|---|---|---|
| `--in-place` | 原地覆盖更新文件 | 标志位（直接修改文件） |
| `-k`, `--keywords` | 关键字大小写 | `lower` (默认), `upper`, `capitalize` |
| `-i`, `--identifiers` | 标识符大小写 | `lower`, `upper`, `capitalize` |
| `--indent_width` | 缩进空格数 | 数字，默认 `4` |
| `-a`, `--reindent_aligned` | 语句与列自动对齐 | 标志位 |
| `--comma_first` | 逗号前置风格 | 标志位 |
| `--align_list` | 列表与别名列对齐 | 标志位（默认开启） |

### Python API

可以在 Python 代码中作为第三方库调用：

```python
from sqlfmt_ext import format_statements

sql = "select id, name, count(1) as total from user_tb where status = 1 group by id, name"
formatted = format_statements(sql, options={"dialect": "doris", "keyword_case": "upper"})
print(formatted)
```

---

## 🛠️ IDE 与客户端集成

### DBeaver 外部格式化程序设置

在 DBeaver 中配置外部格式化程序，即可使用 `sqlfmt_ext` 一键格式化编辑器中的 SQL：

1. 打开设置：`Preferences` -> `Database` -> `Editors` -> `SQL Editor` -> `Formatting`
2. 更改 **Formatter** 为 `External Formatter`
3. 配置如下参数：

| 设置项 | 填写内容 |
|---|---|
| **Command / 程序** | `sqlfmt_ext.exe` |
| **Arguments / 参数** | `${file}` |

*注：在 DBeaver 中请**不要**添加 `--in-place` 参数，格式化结果会通过 `stdout` 自动回填到编辑器中。*

---

## ⚙️ 默认格式化风格

| 选项名 | 默认值 | 说明 |
|---|---|---|
| `dialect` | `"doris"` | 方言选型（可选 `"doris"`, `"selectdb"`, `"mysql"`, `"sqlserver"`） |
| `keyword_case` | `"lower"` | 关键字小写（如 `select`, `from`, `where`） |
| `indent_width` | `4` | 基础缩进宽度为 4 个空格 |
| `reindent_aligned` | `True` | 自动开启子句与表达式对齐 |
| `align_list` | `True` | 开启 AS 别名列与多行列表垂直对齐 |
| `wrap_after` | `30` | 超过指定长度后适度换行 |
| `use_space_around_operators` | `True` | 运算符两侧保留空格 |

---

## 🛠️ 本地开发与测试

```powershell
# 1. 初始化 / 同步开发环境
uv sync

# 2. 运行完整测试套件 (269+ 用例)
uv run pytest -q

# 3. 仅运行收敛性测试
uv run pytest -q -k convergence

# 4. 构建发布 Wheel 包
uv run python scripts/build_package.py
```

---

## 📚 开发者指南与相关文档

针对参与 `sqlfmt_ext` 开发、调试或需要深入了解架构设计的开发人员，请参阅：

- [AGENTS.md](AGENTS.md)：AI 编码规范、硬约束（C1-C6）与阶段推进协议。
- [.claude/plan/status.md](.claude/plan/status.md)：阶段状态、测试门槛数字与已知边界清单。
- [.claude/plan/PLAN.md](.claude/plan/PLAN.md)：设计架构、优化目标与测试策略。
- [.claude/plan/diffs.md](.claude/plan/diffs.md)：上游 `sqlparse` 语义差异表与规则细节。

