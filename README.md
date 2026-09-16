# sqlfmt_ext

基于官方 `sqlparse` 的 SQL 格式化工具：**不改官方源码**，把团队口径做成一层外挂补偿
（`sqlfmt_ext/`），固化默认参数，并用回归 / 收敛 / 幂等三类用例钉住输出稳定。

方言优先级：**Doris / SelectDB 最优先 → 其次 MySQL → Oracle / SQL Server 暂缓**。
`dialect="doris"`（默认）/ `"selectdb"` 已适配 Doris 建表模型定义词与类型名；
`dialect="mysql"` 已适配建表类型名、表选项换行、`ON DUPLICATE KEY UPDATE`；
SQL Server（`dialect="sqlserver"`）已适配 `GO` 批分隔符、`TOP`、`WITH(NOLOCK)`，但按优先级暂不再推进。

## 安装

**工具链统一用 uv**（本项目自 E2 起不再走 pip）；开发环境与使用环境分开，互不干扰：

```powershell
# 开发环境（本仓库内）：建 / 同步 .venv —— 可编辑安装，改代码即时生效
uv sync

# 需要「检出即复现」时用（lock 与本地不一致会直接报错，不静默改环境）
uv sync --frozen
```

运行依赖 `sqlparse>=0.6,<0.7` 见 `pyproject.toml`，**实际解析版本记在 `uv.lock`**（已入库）；
开发依赖（pytest）在 `pyproject.toml` 的 `[dependency-groups] dev`。
解释器版本由仓库根 **`.python-version`**（3.11）决定 —— 开发环境与门禁都用它。

**使用环境不是装进 py 主解释器**：日常使用（含 DBeaver 等外部调用）走 **`uv tool install`**，
装到 uv 的**隔离 tool 环境**，命令落在 `%USERPROFILE%\.local\bin\sqlfmt_ext.exe` —— 见「构建与发布」。

> **uv 不读 pip 的配置文件**（本机 pip 里配的内网源对它无效）—— 源的配置方式见「构建与发布」里的
> 「uv 的包索引」小节。

## 使用

```powershell
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

> 三种写法**不分环境**：`sqlfmt_ext` 命令来自 `uv tool install` 的隔离环境（使用形态），
> `python -m …` 用的是当前解释器（开发环境 `.venv`，或 tool 环境自己的解释器）。

### DBeaver 外部格式化程序

| 栏 | 填 |
|------|------|
| 程序 | `%USERPROFILE%\.local\bin\sqlfmt_ext.exe` |
| 参数 | `${file}` |

也可用解释器 + 参数 `-m sqlfmt_ext.cli ${file}`（不依赖 PATH 与 exe 落点）——
tool 环境的解释器在 `uv tool dir` 下的 `sqlfmt-ext\Scripts\python.exe`。
结果走 stdout、由 DBeaver 回填编辑器，**不要加 `--in-place`**。

## 测试

```powershell
.venv\Scripts\python.exe -m pytest -q
```

覆盖：用例完整性、格式化输出回归（fixture 即期望）、收敛性（压平输入空白后输出不变）、
幂等性（二次格式化不变）、方言开关，另加选项行为（`comma_first` / `align_list`）与布局变体的定向用例。
**当前门槛数字与阶段状态见 `.claude/plan/status.md`**（本项目门槛数字的唯一真身）。

## 构建与发布

```powershell
# 打主包 wheel（脚本内部走 `uv build`）→ scripts/output/wheels/wheelhouse/<名>-<版本>/
python scripts\build_package.py

# 指定新版本号（同时改写 pyproject.toml 的 version）
python scripts\build_package.py 0.1.1

# 连依赖一起打成离线 ZIP（内网 / 无源环境分发）
python scripts\build_package.py --with-deps
```

**部署 = `uv tool install`（装进隔离 tool 环境，不动 py 主解释器）**：

```powershell
# 命令落在 %USERPROFILE%\.local\bin\sqlfmt_ext.exe
# 同版本重新部署**必须带 --reinstall** —— 不加时 uv 只做 Checked、不重装（实测）
uv tool install --force --reinstall "scripts\output\wheels\wheelhouse\sqlfmt_ext-0.1.0\sqlfmt_ext-0.1.0-py3-none-any.whl"

# 查看 / 卸载
uv tool list
uv tool uninstall sqlfmt_ext
```

> 版本号变了要同步两处：上面这行命令（README）与 `.vscode/tasks.json` 的「部署」任务。

**部署后自检必须在项目目录之外跑** —— cwd 在仓库内时源码会被塞进 `sys.path`，命中的是仓库源码
而不是安装副本，结果不可信：

```powershell
cd $env:TEMP
& "$env:USERPROFILE\.local\bin\sqlfmt_ext.exe" "<仓库>\tests\fixtures\cases\ddl\sqltest0_s07.input.sql"   # 输出应与同名 .sql 一致
```

VSCode 任务：`开发：uv sync` / `构建：打 wheel` / `部署：uv tool install（隔离 tool 环境）` / `测试：门禁 pytest`。
部署任务用 `"type": "process"` 直接调 `uv`（不经 shell、不走 PATH）。

**uv 的包索引（换机器必看）**：uv **不读 pip 的配置文件**，本机 pip 里配的内网源对它无效。
本组织做法是写**用户级** `%APPDATA%\uv\uv.toml`：

```toml
index-url = "https://<内网源主机>/repository/pypi-proxy/simple"
```

换机器 / 换源三选一：① 照上面写用户级 `uv.toml`；② 设 `$env:UV_INDEX_URL='<源地址>'`；
③ 单次命令加 `--index-url <源地址>`。

> ⚠️ **`uv.lock` 会记录解析时用的源地址** —— 换源后必须重跑 `uv lock`，
> 否则 `uv lock --check` 与 `uv sync --frozen` 会判定与本地不一致。

**唯一保留的 pip 用法**：`--with-deps` 的 `python -m pip download` —— uv 的 `pip` 子命令**没有 `download`**，
而离线 ZIP 要的是「只取 wheel、不安装」（`uv pip install --target` 是解包安装），无 uv 等价物。
该例外登记在 `.claude/plan/status.md` §3.5，别顺手「统一」掉。

发布到源（预留，尚未执行）：拿到 wheel 后上传到目标源 —— 官方源可 `python -m twine upload dist/*.whl`，
内网源则把 wheel（连同 `--with-deps` 拉到的依赖）放进源目录。

## 目录

| 路径 | 说明 |
|------|------|
| `sqlfmt_ext/cli.py` | CLI 入口（`sqlfmt_ext` 命令与 `python -m sqlfmt_ext.cli` 共用同一份 main） |
| `sqlfmt_ext/` | 补偿层：官方 filter 的替换/追加 + 本项目 pass（分组、布局、对齐、分词兜底） |
| `scripts/build_package.py` | 构建：`uv build` 出 wheel（可选 `--with-deps` 打离线 ZIP，见「构建与发布」） |
| `tests/` | pytest 测试与 SQL 夹具（`tests/fixtures/cases/<topic>/*.sql`） |
| `uv.lock` | **依赖锁定**（已入库）：`uv sync` 据它装环境；换源后需重跑 `uv lock` |
| `.python-version` | 解释器基线（开发环境用）—— `uv sync` / 门禁的解释器版本 |
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
