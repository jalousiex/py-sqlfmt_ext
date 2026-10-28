# AGENTS.md — sqlfmt_ext AI 指令

官方 `sqlparse` 之上的小侵入**外挂层**（不改官方源码）。
**唯一目的：格式化结果更美观、符合个人习惯** —— 外挂层 / 收敛性 / 幂等性都是手段。
门槛：`uv run pytest -q`（**当前数字见 `.claude/plan/status.md` §3.1**，别处不重复写数字）。

## 阶段推进协议（每阶段开工 / 收工都照此执行）

本项目按**阶段**推进，长会话里上下文会被压缩，所以**不依赖记忆**：每阶段的输入、验收、落地都写在文件里。

- **开工**：先读 `.claude/plan/stages.md` 的**断点卡「下一步开工点」**，**本阶段只做这一件事**；四者矛盾时以断点卡为准。
- **收工**：刷新断点卡（`stages.md`）+ 状态表（`status.md` §3.2）→ 沉淀长期事实 → 追加当日记录 → **交付提示** → 提交。
- **完整四步 / 六步清单见 `.claude/rules/stage-protocol-阶段推进协议.md`；开工即读，别省。**
- **汇报格式（固定）**：`缺口 → 原因 → 改动 → 证据 → 验收（数字） → 残留 / 下一步`。
- **交付提示（固定，别漏）**：只要动了 `sqlfmt_ext/` 的行为，汇报末尾必须写明
  「**全局工具仍是旧版本 → 需重新安装 + 需要重新分发**」，命令见下节。

## 改完必带的交付提示（源码改动 ≠ 全局工具已更新）

`uv tool install` 装的是**隔离 tool 环境里的一份拷贝**，改仓库源码对它**没有影响**
（只有开发用 `.venv` 的可编辑安装才即时生效）。所以**跑绿 `pytest` 不等于命令行已是新逻辑**：

1. **重新安装全局工具**（命令行 / DBeaver 用的就是这份）：
   ```powershell
   uv tool install --force --reinstall .
   ```
   同版本**必须**带 `--reinstall` —— 不带 flag 时 uv 只重写 exe、**不重装包**（见 `status.md` §9.20 证据 8）。
2. **需要重新分发**（有下游机器 / 他人使用时）：
   ```powershell
   uv run python scripts/build_package.py            # 出 wheel；断网机加 --with-deps 出离线 ZIP
   ```
   升版本时同步 `.vscode/tasks.json` 与 `README.md`「构建与发布」里写死的 wheel 路径（含版本号）。

**不用动的情况**：只改 `.claude/plan/`、`tests/`、文档或指令文件（工具行为没变）。

## 硬约束（违反即为错误方案）

- **C1** 不改、不复制官方 `sqlparse` 源码（它只是 pip 依赖）
- **C2** 不 monkey-patch；只「子类化 + 换装实例」
- **C3** 不复制官方 `build_filter_stack` 的装配逻辑
- **C4** 不用「改官方 strip 让它保留换行」的魔改；**输出不得依赖输入空白**
- **C5** pass 只允许改写 `Whitespace` token（不改 ttype、不重排、不删非空白 token）
- **C6** 工具链唯一 **uv**（开发 `uv sync` / 构建 `uv build` / 部署 `uv tool install`）：**不回落 pip**、
  不往 py 主解释器装；唯一声明例外是 `--with-deps` 的 `pip download`（登记见 `.claude/plan/status.md` §3.5）

> 违反 C4 / C5 的方案**直接否掉**，哪怕它能让当前用例通过。理由与目标全文见 `.claude/plan/PLAN.md` §1。

## 懒加载索引（细节不在本文件，要动手就按需查）

| 要查什么 | 去哪里 |
|---|---|
| 目标 / 非目标 / 架构 / 测试策略 | `.claude/plan/PLAN.md` §1 / §2 / §6 |
| **门槛数字** / 阶段状态表 / 门禁清单 / 已知边界 | `.claude/plan/status.md` §3 |
| **下一步开工点** / 各阶段卡（缺口·原因·证据·残留） | `.claude/plan/stages.md` §9 |
| U1–U17 语义差异、规则总表、每处补偿的落点与**调用时序** | `.claude/plan/diffs.md` §3.4 / §4 |
| 架构管线、代码地图、测试约定、默认参数、命令用法 | `README.md`「AI 指引」 |
| **安装 / 构建 / 部署（uv tool）/ uv 源与 lock** | `README.md`「安装」「构建与发布」 |
| 迁移期历史与变更记录（追溯用） | `.claude/plan/history.md` |
| 长期口径决策、协作约定（多代理 / worktree） | `.codebuddy/memory/MEMORY.md` |
| **诊断与改法**（元规则一~七、工作流、坑位） | 技能 `sqlfmt-parity`（`.claude/skills/sqlfmt-parity/`，真源入库；`.codebuddy/skills/sqlfmt-parity/SKILL.md` 是脚本生成的指针）：`SKILL.md` + `references/` |

**排查差异 / 改代码之前，先加载上表最后一行的技能** —— 元规则一「列对齐错乱先怀疑分组」、
元规则七「`_process` 按组类名分发」等全部诊断手法与坑位都在那里。**本文件不重复其内容。**
