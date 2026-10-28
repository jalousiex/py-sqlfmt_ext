#!/usr/bin/env python
"""sqlfmt_ext 门禁（`python scripts/run_gates.py`）。

`tests/` 是**唯一**测试套件（迁移期的对拍套件随旧 fork 在 S7 一起删除，见
`.claude/plan/history.md` §9.4），它同时覆盖：**用例完整性 / 输出回归 / 幂等 / 收敛**
（`tests/fixtures/cases/<topic>/*.sql` 即期望输出；方言开关另有 `test_sqlfmt_dialect.py`）。

门槛（默认值即当前口径，数字以 `.claude/plan/status.md` §3.1 为准，那是唯一真身）：

- 通过数**严格等于** `--expect`（默认 `291 passed`）；
- 不得出现 `failed` / `error`；
- 不得出现 `xfailed` / `xpassed` —— 收敛门禁的 `KNOWN_DIVERGENT` 已清空，出现 xfail 就是
  新登记的已知发散，必须有人解释（`xfail(strict=True)` 会在修好时主动报错）。

退出码：0 门禁通过；1 门禁未过；2 环境问题（找不到仓库根）。
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

TAG_RE = re.compile(r"(\d+)\s+(passed|failed|error|errors|xfailed|xpassed|skipped)\b")

COUNTERS = ("passed", "failed", "error", "xfailed", "xpassed", "skipped")


def find_root(explicit: str | None) -> Path | None:
    if explicit:
        p = Path(explicit).expanduser().resolve()
        return p if (p / "sqlfmt_ext").is_dir() else None
    env = os.environ.get("SQLFMT_ROOT")
    if env:
        p = Path(env).expanduser().resolve()
        if (p / "sqlfmt_ext").is_dir():
            return p
    for base in (Path.cwd(), Path(__file__).resolve().parent):
        for cand in [base, *base.parents]:
            if (cand / "sqlfmt_ext" / "grouping.py").is_file():
                return cand
    return None


def find_python(root: Path) -> str:
    for rel in ("Scripts/python.exe", "bin/python"):
        cand = root / ".venv" / rel
        if cand.is_file():
            return str(cand)
    print("[warn] 未找到 .venv 解释器，退回当前解释器", file=sys.stderr)
    return sys.executable


def parse_summary(output: str) -> dict[str, int]:
    """从 pytest 尾部的摘要行解析计数（正则**不锚定行首**：一行里可能有多个计数）。"""
    counts = dict.fromkeys(COUNTERS, 0)
    for line in reversed([ln.strip() for ln in output.splitlines() if ln.strip()]):
        if "====" in line or not TAG_RE.search(line):
            continue
        for num, word in TAG_RE.findall(line):
            key = "error" if word == "errors" else word
            if key in counts:
                counts[key] += int(num)
        break
    return counts


def collect_problems(output: str) -> list[str]:
    return [
        line.strip()
        for line in output.splitlines()
        if line.strip().startswith(("FAILED ", "ERROR "))
    ]


def fmt(counts: dict[str, int]) -> str:
    return ", ".join(f"{counts[k]} {k}" for k in COUNTERS if counts.get(k))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="sqlfmt_ext 门禁（唯一套件 tests/）")
    ap.add_argument("--root", help="仓库根（默认按 cwd 向上查找 sqlfmt_ext/grouping.py）")
    ap.add_argument("--expect", default="291 passed", help="期望摘要（改门槛时同步 .claude/plan/status.md §3.1）")
    ap.add_argument("--filter", metavar="TAGS", help="用例标签过滤（设置 SQLFMT_CASE_TAGS）")
    args = ap.parse_args(argv)

    root = find_root(args.root)
    if root is None:
        print("[error] 找不到仓库根（未发现 sqlfmt_ext/grouping.py），用 --root 指定", file=sys.stderr)
        return 2
    python = find_python(root)
    print(f"[info] root={root}\n[info] python={python}")

    env_backup = os.environ.get("SQLFMT_CASE_TAGS")
    if args.filter:
        os.environ["SQLFMT_CASE_TAGS"] = args.filter
    cmd = [python, "-m", "pytest", "tests/", "-q", "--tb=no", "-p", "no:cacheprovider"]
    print(f"\n=== tests/ : {' '.join(cmd[1:])} ===", flush=True)
    try:
        proc = subprocess.run(
            cmd, cwd=str(root), capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
    finally:
        if args.filter:
            if env_backup is None:
                os.environ.pop("SQLFMT_CASE_TAGS", None)
            else:
                os.environ["SQLFMT_CASE_TAGS"] = env_backup

    output = (proc.stdout or "") + (proc.stderr or "")
    print(output.rstrip(), flush=True)

    counts = parse_summary(output)
    got = fmt(counts)
    print(f"\n[tests] {got}")

    failures: list[str] = []
    problems = collect_problems(output)
    if problems:
        failures.append(f"有 {len(problems)} 个失败/错误：{problems[:5]}")
    if counts["xfailed"] or counts["xpassed"]:
        failures.append(f"出现 xfail 项（xfailed={counts['xfailed']}, xpassed={counts['xpassed']}）—— 需要解释")
    if got != args.expect:
        failures.append(f"摘要与期望不符：期望 `{args.expect}`，实得 `{got}`（若确为进展，同步 .claude/plan/status.md §3.1）")

    print()
    if failures:
        for item in failures:
            print(f"[FAIL] {item}")
        return 1
    print("[OK] 门禁通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
