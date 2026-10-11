# 进度与当前缺口（指针）

> 本文件**不再保存进度快照**（快照永远过期）。权威出处：

| 要查什么 | 去哪里 |
|---|---|
| 门槛数字（唯一真身）、阶段状态表、门禁清单、已知边界 | `.claude/plan/status.md` §3 |
| **下一步开工点**、各阶段卡（缺口 / 原因 / 证据 / 残留） | `.claude/plan/stages.md` §9 |
| 迁移期（S0–S7）的过程取证 | `.claude/plan/history.md`；`.codebuddy/memory/2026-09-1*.md` |

一键门禁：`python .claude\skills\sqlfmt-parity\scripts\run_gates.py`
（跑唯一套件 `tests/`，断言摘要等于期望且无 xfail；`--expect` 默认值即当前门槛）。
