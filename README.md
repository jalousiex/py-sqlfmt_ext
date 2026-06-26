# py-sqlfmt

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