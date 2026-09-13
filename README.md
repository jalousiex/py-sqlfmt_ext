# sqlfmt_ext

基于官方 `sqlparse` 的 SQL 格式化工具：**不改官方源码**，把团队口径做成一层外挂补偿
（`sqlfmt_ext/`），固化默认参数，并用回归 / 收敛 / 幂等三类用例钉住输出稳定。

方言优先级：**Doris / SelectDB 最优先 → 其次 MySQL → Oracle / SQL Server 暂缓**。
`dialect="doris"`（默认）/ `"selectdb"` 已适配 Doris 建表模型定义词与类型名；
`dialect="mysql"` 已适配建表类型名、表选项换行、`ON DUPLICATE KEY UPDATE`；
SQL Server（`dialect="sqlserver"`）已适配 `GO` 批分隔符、`TOP`、`WITH(NOLOCK)`，但按优先级暂不再推进。

## 安装

```bash
# 开发环境（本仓库内）：可编辑安装，改代码即时生效
python -m pip install -r requirements-dev.txt

# 使用环境：装发布物（wheel），与开发环境隔离
pip install sqlfmt_ext-0.1.0-py3-none-any.whl
```

运行依赖 `sqlparse>=0.6,<0.7` 见 `pyproject.toml`，安装时自动解析。

## 使用

```bash
# 无参数：打印用法（选项一览）
sqlfmt_ext

# 格式化单文件（输出到 stdout）
sqlfmt_ext path/to/file.sql

# 递归格式化目录
sqlfmt_ext path/to/sql-dir

# 原地回写
sqlfmt_ext path/to/file.sql --in-place

# 不依赖 PATH 的等价写法（与上面同一个 main，三种写法等价）
python -m sqlfmt_ext path/to/file.sql
python -m sqlfmt_ext.cli path/to/file.sql

# 库内调用
python -c "from sqlfmt_ext import format_statements; print(format_statements('select 1'))"
```

### DBeaver 外部格式化程序

| 栏 | 填 |
|------|------|
| 程序 | `…\pythoncore-3.14-64\Scripts\sqlfmt_ext.exe` |
| 参数 | `${file}` |

也可用 `python.exe` + 参数 `-m sqlfmt_ext.cli ${file}`（不依赖 PATH 与 exe 落点）。
结果走 stdout、由 DBeaver 回填编辑器，**不要加 `--in-place`**。

## 测试

```bash
python -m pytest -q
```

覆盖：用例完整性、格式化输出回归（fixture 即期望）、收敛性（压平输入空白后输出不变）、
幂等性（二次格式化不变）、方言开关，另加选项行为（`comma_first` / `align_list`）与布局变体的定向用例。
**当前门槛数字与阶段状态见 `.claude/plan/status.md`**（本项目门槛数字的唯一真身）。

## 构建与发布

```bash
# 打主包 wheel → scripts/output/wheels/wheelhouse/<名>-<版本>/
python scripts/build_package.py

# 连依赖一起打成离线 ZIP（内网 / 无源环境分发）
python scripts/build_package.py --with-deps

# 指定新版本号（同时改写 pyproject.toml 的 version）
python scripts/build_package.py 0.1.1

# 把最新构建物装进主环境
# 默认取 SQLFMT_MAIN_PYTHON 或 %LOCALAPPDATA%\Python\pythoncore-3.14-64
python scripts/install_to_main.py
```

VSCode 任务：`安装：可编辑到项目 .venv` / `构建：打 wheel` / `部署：装到主环境（脱开 venv）` / `测试：门禁 pytest`。
部署任务用 `"type": "process"` 且直接取 `.vscode/settings.json` 里 `sqlfmt.mainEnvPython` 指定的解释器
（不经 shell、不走 PATH），因此**不受当前激活的 .venv 影响**；换机器只改这一个配置键。

发布到源（预留，尚未执行）：拿到 wheel 后上传到目标源 —— 官方源可 `python -m twine upload dist/*.whl`，
内网源则把 wheel（连同 `--with-deps` 拉到的依赖）放进源目录。

## 目录

| 路径 | 说明 |
|------|------|
| `sqlfmt_ext/cli.py` | CLI 入口（`sqlfmt_ext` 命令与 `python -m sqlfmt_ext.cli` 共用同一份 main） |
| `sqlfmt_ext/` | 补偿层：官方 filter 的替换/追加 + 本项目 pass（分组、布局、对齐、分词兜底） |
| `scripts/` | 构建与部署：`build_package.py`（出 wheel / 离线 ZIP）、`install_to_main.py`（装进主环境） |
| `tests/` | pytest 测试与 SQL 夹具（`tests/fixtures/cases/<topic>/*.sql`） |
| `requirements-dev.txt` | 开发依赖（pip / build / pytest + `-e .`） |
| `.claude/rules/` | 阶段推进协议（开工四步 / 阶段内铁律 / 收工六步 / 汇报格式） |
| `.claude/plan/` | **计划真身**：大纲 / 状态 / 阶段卡 / 差异 / 归档（见下表） |

### 计划文件（`.claude/plan/`）

| 文件 | 内容 |
|---|---|
| `PLAN.md` | 目标 / 非目标 / 硬约束 §1、架构 §2、测试策略 §6、风险与回退 §7 |
| `status.md` | 阶段状态与门槛 §3（**门槛数字唯一真身**）、门禁清单、已知边界 |
| `stages.md` | **断点卡**（下一步开工点）+ 各阶段卡 §9.x |
| `diffs.md` | 上游语义差异 U1–U16 §3.4、布局/对齐规则表 §4、补偿落点与时序 |
| `history.md` | 归档：迁移期（S0–S7）记录与变更记录 |

章号沿用原 `PLAN.md`，因此代码注释里的 `PLAN §9.x` 等引用仍可按章号导航。

---

## AI 指引

> 常驻指令（硬约束 + 阶段推进协议 + 懒加载索引）在根 `AGENTS.md`；
> 「怎么诊断、怎么改」的手法在技能 `sqlfmt-parity`。本节的定位是**架构与约定**。

### 架构概要

```text
sqlfmt_ext.cli → sqlfmt_ext.format_statements()
  → 方言批切分（仅当 batch_separator 非空，如 sqlserver 的 GO）
  → 官方 lexer.tokenize()        # 正则分词（DialectLexer 追加方言词表 / 优先级规则）
  → 官方 StatementSplitter       # 按 ; 分割语句
  → sqlfmt_ext.grouping.group()  # 官方分组 + 本项目补偿（11 处，见 .claude/plan/diffs.md §4.4）
  → sqlfmt_ext.passes.layout     # 核心：深度优先遍历，关键字前换行 + 缩进
  → sqlfmt_ext.passes.align      # 列表 AS / 别名列对齐
  → 官方 SerializerUnicode
```

**硬约束**：不修改官方 `sqlparse` 源码（用替换 filter / 追加 pass / 事后补偿实现），
不靠删除或改写非空白 token、不靠重排 token 来对齐。全文见 `.claude/plan/PLAN.md` §1。

### 关键文件

- `sqlfmt_ext/cli.py` — CLI 入口；`format_statements()` 拆分语句后逐条格式化，`.strip()` 后用 `\n\n` 拼接
- `sqlfmt_ext/passes/layout.py` — 核心布局：`_process()` **按组类名分发**（`_process_{cls}`），
  所以任何「把括号包进别的组」的补偿都会改变这里收到的组
- `sqlfmt_ext/passes/align.py` — 列对齐（`_identifier_layouts` / `_create_field_lines`）
- `sqlfmt_ext/grouping.py` — 官方 `grouping` 前/后的补偿（`_wrap_create_table_calls` /
  `_attach_over_to_functions` / `_extend_adjacent_lists` / `_trim_clause_tail` 等，
  每处 docstring 都写明「为什么需要」与「为什么放这个位置」）
- `sqlfmt_ext/lexer.py` · `sqlfmt_ext/stack.py` — `DialectLexer`；复用官方 `build_filter_stack` 后**换装 / 摘除** filter
- `sqlfmt_ext/filters/` — 替换官方的空白 / 操作符 filter
- `sqlfmt_ext/policy.py` — **通用**关键字与多词关键字口径（`LATERAL VIEW`、`OVER(` 的优先级补丁等）
- `sqlfmt_ext/dialects.py` — **方言的唯一真身**：`Dialect(name, multiword_patches,
  precedence_patches, extra_lexer_rules, extra_keywords, extra_split_words, type_name_keywords,
  batch_separator, notes)`。
  分词层（方言关键字与**类型名**、方言专属优先级规则）、布局层（`DISTRIBUTED BY` 等换行锚点）、
  批切分层（SQL Server 的 `GO`）都从这里取声明；未知方言由 `options` 直接报错（不再静默降级）
- `sqlfmt_ext/options.py` — 默认参数与校验（扩展项 `align_list` / `dialect`）

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

### 默认格式化参数

`keyword_case=lower`、`indent_width=4`、`reindent_aligned=True`、`wrap_after=30`、
`use_space_around_operators=True`、`align_list=True`（扩展项）、`dialect="doris"`（扩展项）

低频参数**不做 CLI 参数**，优先改 `sqlfmt_ext/options.py` 的模块级默认值。
