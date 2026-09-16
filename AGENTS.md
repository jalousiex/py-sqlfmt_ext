# AGENTS.md — sqlfmt_ext AI 指令

官方 `sqlparse` 之上的小侵入**外挂层**（不改官方源码）。
**唯一目的：格式化结果更美观、符合个人习惯** —— 外挂层 / 收敛性 / 幂等性都是手段。
门槛：`.venv\Scripts\python.exe -m pytest -q`（**当前数字见 `.claude/plan/status.md` §3.1**，别处不重复写数字）。

## 阶段推进协议（每阶段开工 / 收工都照此执行）

本项目按**阶段**推进，长会话里上下文会被压缩，所以**不依赖记忆**：每阶段的输入、验收、落地都写在文件里。

- **开工**：先读 `.claude/plan/stages.md` 的**断点卡「下一步开工点」**，**本阶段只做这一件事**；四者矛盾时以断点卡为准。
- **收工**：刷新断点卡（`stages.md`）+ 状态表（`status.md` §3.2）→ 沉淀长期事实 → 追加当日记录 → 提交。
- **完整四步 / 六步清单见 `.claude/rules/stage-protocol-阶段推进协议.md`；开工即读，别省。**
- **汇报格式（固定）**：`靶子 → 根因 → 改动 → 证据 → 验收（门槛数字）→ 残留 / 下一步`。

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
| **下一步开工点** / 各阶段卡（靶子·根因·证据·残留） | `.claude/plan/stages.md` §9 |
| U1–U16 语义差异、规则总表、每处补偿的落点与**调用时序** | `.claude/plan/diffs.md` §3.4 / §4 |
| 架构管线、代码地图、测试约定、默认参数、命令用法 | `README.md`「AI 指引」 |
| **安装 / 构建 / 部署（uv tool）/ uv 源与 lock** | `README.md`「安装」「构建与发布」 |
| 迁移期历史与变更记录（追溯用） | `.claude/plan/history.md` |
| 长期口径决策、协作约定（多代理 / worktree） | `.codebuddy/memory/MEMORY.md` |
| **诊断与改法**（元规则一~七、工作流、坑位） | 技能 `sqlfmt-parity`（`.codebuddy/skills/sqlfmt-parity/`）：`SKILL.md` + `references/` |

**排查差异 / 改代码之前，先加载上表最后一行的技能** —— 元规则一「列对齐错乱先怀疑分组」、
元规则七「`_process` 按组类名分发」等全部诊断手法与坑位都在那里。**本文件不重复其内容。**
