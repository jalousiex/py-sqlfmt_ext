# 状态 — sqlfmt_ext 阶段状态与门槛

> 本文件是**门槛数字的唯一真身**：别处（`AGENTS.md` / `README.md` / `MEMORY.md` / 技能）
> 一律只写命令 + 指向本文件。阶段**过程**（靶子 / 根因 / 证据 / 残留）在 `stages.md`。
> 计划大纲与硬约束见 `PLAN.md`；章号沿用原 `PLAN.md`（本文件 = §3）。

## §3.1 门槛（唯一真身）

```powershell
uv run pytest -q
```

| 项 | 值 |
|---|---|
| 当前门槛 | **`269 passed`（0 failed / 0 xfailed）** |
| 收敛门禁 `KNOWN_DIVERGENT` | **已清空**（S10 收口），别新增无原因的 xfail |
| 唯一测试套件 | `tests/`（迁移期的 `tests_migration/` 随旧 fork 在 S7 删除） |

只需看收敛门禁时：`uv run pytest -q -k convergence`。

**环境与部署命令（E2 起统一 uv）**：

```powershell
uv sync                                        # 开发环境（按 .python-version 取解释器）
uv sync --frozen                               # 检出即复现（与 lock 不一致直接报错）
uv lock --check                                # 依赖锁定一致性（期望退出码 0）
uv run python scripts\build_package.py         # 构建 wheel（脚本内部走 uv build）
uv tool install --force --reinstall "<wheel>"  # 部署：隔离 tool 环境，不装 py 主解释器
```

> `uv tool install` **不读 `.python-version`**（实测 tool 环境落在 3.14.3，而 dev 环境按 pin 落在 3.11.9）——
> 要让两者一致必须显式加 `--python`；本次按用户口径「交给 uv 自选」不加。详见 §3.5。

## §3.2 阶段状态表（时间序；门槛列按当时口径）

> S7 之前是对拍口径（`passed / xfailed`，跑在新实现上）；S7 起是唯一套件的 `pytest` 数字。
> 每行的**过程与根因**见 `stages.md` 对应小节（§9.x 章号一致）。

| 阶段 | 内容 | 门槛 | 状态 |
|---|---|---|---|
| **S0** | 计划落地 + 骨架 + 对拍进度条 | 1 / 30 | ✅ |
| **S1** | 布局引擎移植到官方 0.6.0 之上（方言 lexer、分词补丁、`LayoutPass`、摘官方换行 filter） | 4 / 27 | ✅ |
| **S2** | 上游语义差异补偿 U5–U7（`Case.get_cases` 注释占位、`Where.M_CLOSE`、`get_real_name`） | 4 / 27 | ✅ U5 落地；U6/U7 实测无影响 |
| **S3** | L1 注释强制换行改成结构性规则（+ U11 空白归一化、U10 `OVER (` 优先级、U9 分组补偿） | 16 / 15 | ✅ |
| **S4** | L2 括号字段列表展开（真因 = 分组口径 U12） | 21 / 10 | ✅ |
| **S5a** | L4 多 `lateral view` 各自分行（分词兜底） | 22 / 9 | ✅ |
| **S5b** | U14 + `_create_guard` 边界 + 注释串按层级缩进 | 24 / 7 | ✅ |
| **S5c** | `case` 与首个 `when` 同行（口径重定 + 有意偏离登记，S7-d 已归零） | 23 / 8 | ✅ |
| **S6** | 列对齐收尾（真因多为分组/分词：U15 尾逗号、U16 缺 `DATETIME`、U13 CREATE 早退、S6b 相邻续接列表） | 31 / 0 | ✅ |
| **S7** | 收敛 + 幂等 + 入口切换 + 删 fork + 重定基线（五提交 `14973fc`→`4471cd6`） | 172 passed / 4 xfailed | ✅ |
| **S9** | 注释断行的结构性口径：跨注释组强制换行 + `ON COMMIT` 白名单结构化 | 175 passed / 1 xfailed | ✅ |
| **S10** | 「注释保持列 0」判据结构化 → 收窄到**语句前导注释** | 176 passed / 0 xfailed | ✅ |
| **S10-b** | 收尾注释改「按所在层级对齐」；`;` 一律顶列 0（只在收尾兜底） | 176 passed | ✅ |
| **S8-a** | 方言层收成**单一真身**（`dialects` 登记表）+ 未知方言报错 + 建 `dialect` topic | 185 passed | ✅ |
| **S8-b** | 方言词表归位（分词层词表也进 `dialects`）+ 补 20 个 Doris 类型名 | 192 passed | ✅ |
| **S8-c** | SQL Server：`GO` 批分隔符、`TOP`、`WITH(NOLOCK)`、`[ ]` 标识符 | 215 passed | ✅ |
| **S8-d** | MySQL：11 个类型名、表选项换行锚点、`ON DUPLICATE KEY UPDATE` 合并、表达式内锚点 guard | 234 passed | ✅ |
| **S11** | DDL 字段列序：约束列查找不得越过 `DEFAULT` | 239 passed | ✅ |
| **S12** | LIMIT 子句：`m, n` 不按列表展开；`SET` 锚点补词边界（不再子串命中 `OFFSET`） | 244 passed | ✅ |
| **S13** | ALTER 多子句换行（本层 ≥2 个动作词时各自成行；单动作保持同行） | 249 passed | ✅ |
| **S14** | 官方判成 `Keyword` 的类型名按方言声明进 DDL 类型列（不改官方词表） | 259 passed | ✅ |
| **S15** | 泛型尖括号：`map<string, int>` 的实参逗号不再是 DDL 字段分隔符 | 264 passed | ✅ |
| **S16** | `ON` 锚点补后缀词边界（`ONLY` / `ONLINE` 不再被当成子句头） | 269 passed | ✅ |
| **E1** | 工程化：入口收进 `sqlfmt_ext/cli.py`、下线根 `sqlfmt.py`、项目与发行名统一为 `sqlfmt_ext`、`-e` 与 wheel 双环境 + 构建/部署脚本 | 269 passed | ✅ |
| **E2** | 工具链切 uv：dev 组取代 `requirements-dev.txt`、`uv.lock`/`.python-version` 入库、构建 `uv build`、部署 `uv tool install`（隔离 tool 环境）、删 `install_to_main.py`、`requires-python` 修正为 `>=3.10` | 269 passed | ✅ |

**E1（工程化）不涉及格式化逻辑**，门槛与 S16 相同（`269 passed`）；它换的是入口与打包形态：
命令入口为 `sqlfmt_ext`（`sqlfmt_ext/cli.py:main`，`python -m sqlfmt_ext.cli` 等价），双环境模型是
「项目 `.venv` 可编辑装源码（调试 / 门禁）+ 主环境 `pythoncore-3.14-64` 装 wheel（日常使用）」，
脚本见 `scripts/build_package.py` / `scripts/install_to_main.py`，VSCode 任务见 `.vscode/tasks.json`。
> **E2 起上面这套双环境模型已废弃**（主环境安装与 `install_to_main.py` 一并下线）——
> 现行口径：开发 `uv sync` 到项目 `.venv`，使用/部署 `uv tool install` 到隔离 tool 环境。

**E2（工具链切 uv）同样不涉及格式化逻辑**，门槛与 E1/S16 相同（`269 passed`）。它把「环境」从
「pip 装到某个解释器」改成「uv 按角色管理三种环境」：开发 `uv sync`（读 `.python-version`）、
构建 `python scripts/build_package.py`（内部 `uv build --wheel --out-dir`）、
部署 `uv tool install --force --reinstall <wheel>`（隔离 tool 环境，命令落 `%USERPROFILE%\.local\bin\sqlfmt_ext.exe`）。
**不再往 py 主解释器装**（主解释器实测本来就没有本项目）。命令与判据见 §3.1 / §3.3，例外登记见 §3.5。

**方言路线（S8-a → S8-d）已走完**：Doris / SelectDB（最优先）与 MySQL 已适配；
SQL Server 已完成并保留、**不回退也不再往前推**（用户口径）；Oracle 未开工。

## §3.3 门禁清单

| 门禁 | 文件 | 判据 |
|---|---|---|
| 用例完整性 | `tests/test_sqlfmt_case_integrity.py` | fixture 与 `TOPIC_META` / `FILE_OPTIONS` 一致 |
| 输出回归 | `tests/test_sqlfmt_output_regression.py` | `format(input) == expected`（fixture 即期望） |
| 幂等性 | `tests/test_sqlfmt_idempotency.py` | `format(format(x)) == format(x)`，input→input 也幂等 |
| 收敛性 | `tests/test_sqlfmt_convergence.py` | 压平输入空白后输出仍等于 canonical |
| 方言开关 | `tests/test_sqlfmt_dialect.py` | 方言真的改变行为，且未知方言报错 |
| 选项行为 | `tests/test_comma_options.py` | `comma_first` / `align_list` 下的输出（fixture 即期望） |
| 布局变体 | `tests/test_layout_variants.py` | 关键布局规则的**内联期望** |
| 构建工具链唯一 | `scripts/build_package.py` | 构建走 `uv build --wheel --out-dir`；`uv` 缺失时报错给指引（**不回落 pip**）；唯一声明例外是 `--with-deps` 的 `python -m pip download` |
| 依赖锁定一致 | `uv.lock`（**已入库**） | `uv lock --check` 退出码 0；`uv sync --frozen` 无变更 |
| 开发环境不含 pip | `.venv`（`uv sync` 生成） | `pyvenv.cfg` 里 `uv = …`、**无 `Scripts\pip.exe`**；`sqlfmt_ext` 为可编辑安装（改代码即时生效） |
| 部署后 tool 自检可信 | `README.md`「构建与发布」 | `uv tool install` 后在**项目目录之外**调用 exe，输出与 fixture 一致（cwd 在仓库内会命中仓库源码 → 假绿） |
| 工具链残留唯一例外 | 全仓（`git grep`） | pip 用法只剩 1 处声明例外（`build_package.py` 的 `pip download`）；入库文档无机器 / 个人专属路径 |

## §3.5 已知边界（登记在案，**都不是缺口**；要动先开新阶段卡）

1. **S11**：写在 `DEFAULT` **之后**的列级约束词（`id int default 0 primary key`）不再进约束列
   —— 判据是「约束列查找止于 `DEFAULT`」；常见形态（`not null` 在 `default` 前、表级 `primary key (id)`）不受影响。
2. **S12 / S16**：`SET`、`ON` 已补词边界；其余纯词锚点（`AND` / `COMMENT` / `OR` / `FROM` …）仍靠
   `re.search` 匹配 —— **实测官方词表里没有含这些子串的关键字**，故无实证缺口，登记待观察。
3. **S13**：ALTER 的 `CONVERT`（MySQL 专有，`alter table t convert to character set utf8`）未纳入动作词。
4. **S15**：`_process_parenthesis` 的 **WHERE 分支**没有做尖括号深度感知（DDL 分支已做）；
   WHERE 内出现泛型实参逗号极罕见，故未改。
5. **S8-c**：批分隔符按**独立 token** 判，**不解析字符串/注释内容**（sqlcmd 同款口径）：
   字符串里独占一行的 `go` 会被切。
6. **S14**：未动分词层 → `json` / `double` 在**非 DDL 上下文**（表达式、列名）仍是 `Keyword`（有意为之）。
7. **S8-d**：Doris 的 `DUPLICATE` 锚点会在 MySQL 的 `on duplicate key update` 里误触发
   （跨方言组合；单独用 `dialect=mysql` 无此问题）。
8. **S8-a**：`LATERAL VIEW` 仍留**通用**词表（generic 下因分词层不合并而天然不生效），未按方言拆分
   —— 暂按「本项目通用增强」处理。
9. **【已知事实】`uv tool install` 不读 `.python-version`** —— 实测（2026-09-16，E2）：工作区 pin 是 3.11，
   `uv sync` 据此把 `.venv` 建在 **3.11.9**；而 `uv tool install <wheel>` 建出的 tool 环境是 **3.14.3**
   （默认发现路径的解释器），**也不跟随项目 `.venv`**。要让两者一致必须显式 `--python`；本次按用户口径
   「交给 uv 自选」不加。影响面：仅「同机 dev 与 tool 解释器版本不同」，对输出无影响（格式化结果与解释器
   版本无关，门槛在 3.11 上仍 `269 passed`）。
10. **【有意保留的行为】`--with-deps` 的依赖抓取仍用 `python -m pip download`** —— 全项目**唯一**保留的 pip
   用法：`uv pip` 子命令**没有 `download`**，离线 ZIP 无 uv 等价物。登记处：`scripts/build_package.py`
   （docstring + `_download_deps`）、`README.md`「构建与发布」、硬约束 C6。不再需要离线 ZIP 时可另开阶段卡移除。
11. **【已知事实】uv 不读 pip 的配置文件** —— 本机 pip 里配的内网源对 uv **无效**，需用户级
   `%APPDATA%\uv\uv.toml` 或 `UV_INDEX_URL`；且 `uv.lock` **记录解析时的源地址**，换源后必须重跑 `uv lock`
   （否则 `uv lock --check` / `uv sync --frozen` 判定不一致）。同款登记见隔壁 py-dolphin_scheduler `§3.5` 第 28 条。
12. **【已修正的声明】`requires-python` 由 `>=3.9` 改为 `>=3.10`** —— 原声明与依赖不自洽（sqlparse 0.6.0 的
   `Requires-Python` 是 `>=3.10`）：pip 只按当前解释器解析，永远碰不到这个矛盾；`uv lock` 做**跨版本解析**时
   立刻报 `No solution found for 3.9.*`。属**修正错误声明**而非放宽支持 —— 3.9 本来就装不上本项目。
