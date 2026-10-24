#!/usr/bin/env python3
"""构建 sqlfmt_ext 的 wheel（可选连依赖打成离线 ZIP）。

用法:
    python scripts/build_package.py                # 只出主包 wheel
    python scripts/build_package.py --with-deps    # 连运行依赖一起打 ZIP（离线分发）
    python scripts/build_package.py 0.1.1          # 指定新版本号后再构建

构建工具链（E2 起统一为 **uv**，不再走 pip）：
    uv build --wheel --out-dir <wheelhouse>
产物落在 scripts/output/wheels/（已被 .gitignore 的 `output/` 覆盖，不入库）。

与参考项目 py-dolphin_scheduler 的差异：**不做 wheel 内容断言** —— 本项目只有单一顶层命名空间
`sqlfmt_ext/`（由 `[tool.setuptools.packages.find]` 限定），不存在「运行期数据混进包里」的历史问题。

> **`uv` 必须在 PATH 上**。缺它直接报错给指引，**不回落 pip** —— 回落会让「构建到底用哪套工具」
> 变成看环境而定，产物也就说不清是哪个工具链出的。
>
> **`--with-deps` 是全项目唯一保留的 pip 用法**（声明例外）：uv 的 `pip` 子命令没有 `download`，
> 而离线 ZIP 要的是「只取 wheel、不安装」，uv 无等价能力（其 `install --target` 是解包安装）。
> 登记在 `.claude/plan/status.md` §3.5；唯一的运行依赖 sqlparse 是纯 Python（py3-none-any），
> 所以**不传 --platform / --implementation / --abi 那组跨平台限定**，拉到的 wheel 在 Windows / Linux 通用。
"""

import argparse
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
OUTPUT_DIR = SCRIPT_DIR / "output" / "wheels"
PYPROJECT = ROOT / "pyproject.toml"


def _run(cmd, cwd):
    print("  $ {}".format(" ".join(map(str, cmd))))
    subprocess.check_call(cmd, cwd=cwd)


def _require_uv():
    """取 uv 可执行文件路径；不在 PATH 上就报错给指引（**不回落 pip**，理由见模块 docstring）。"""
    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit(
            "未找到 uv：本项目自 E2 起以 uv 为唯一工具链，不回落 pip。\n"
            "  安装：winget install --id astral-sh.uv\n"
            "  装好后确认 `uv --version` 可用，再重跑本脚本。"
        )
    return uv


def _download_deps(wheelhouse_dir, main_wheel):
    """把主包依赖的 wheel 拉进 wheelhouse（**本脚本唯一保留 pip 的步骤**，声明例外）。

    为什么还用 pip：uv 的 ``pip`` 子命令只有 compile / sync / install / uninstall / freeze /
    list / show / tree / check，**没有 ``download``**；离线 ZIP 要的是「只取 wheel、不安装」，
    uv 无等价能力（``install --target`` 是解包安装，不是 wheel 包）。
    这是**声明例外**，登记在 ``.claude/plan/status.md`` §3.5；改造前先看那条。
    """
    _run(
        [
            sys.executable,
            "-m",
            "pip",
            "download",
            "--only-binary=:all:",
            "--dest",
            str(wheelhouse_dir),
            str(main_wheel),
        ],
        cwd=ROOT,
    )


def _read_pyproject(pattern):
    match = re.search(pattern, PYPROJECT.read_text(encoding="utf-8"), re.MULTILINE)
    if not match:
        raise SystemExit(f"无法从 {PYPROJECT} 解析: {pattern}")
    return match.group(1)


def _bump_version(new_version):
    old_version = _read_pyproject(r'^version\s*=\s*"([^"]+)"')
    if new_version and new_version != old_version:
        content = PYPROJECT.read_text(encoding="utf-8")
        PYPROJECT.write_text(
            re.sub(r'^(version\s*=\s*)"[^"]+"', rf'\1"{new_version}"', content, flags=re.MULTILINE),
            encoding="utf-8",
        )
        print(f"版本升级: {old_version} → {new_version}")
        # 版本号唯一真身是 pyproject.toml：`sqlfmt_ext.__version__` 运行期从元数据读回，无需同步；
        # 但 uv.lock 里记的还是旧版本，`uv lock --check` 会判定不一致 —— 只提示，不代跑（离线机可能需要网络）。
        print("提示: uv.lock 记录的版本已过期，请跑一次 uv lock（或 uv sync，会顺带更新）")
        return new_version
    print(f"当前版本: {old_version} (未变更)")
    return old_version


def _clean_artifacts():
    """清掉构建在仓库根留下的中间物（对齐隔壁的收尾动作）。"""
    for name in ("build", "dist"):
        shutil.rmtree(ROOT / name, ignore_errors=True)
    for egg_info in ROOT.glob("*.egg-info"):
        shutil.rmtree(egg_info, ignore_errors=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="构建 sqlfmt_ext wheel（可选离线 ZIP）")
    parser.add_argument("version", nargs="?", help="新版本号，省略则沿用 pyproject.toml 里的")
    parser.add_argument("--with-deps", action="store_true", help="把运行依赖 wheel 一起打进 ZIP")
    args = parser.parse_args(argv)

    name = _read_pyproject(r'^name\s*=\s*"([^"]+)"')
    uv = _require_uv()
    version = _bump_version(args.version)
    wheelhouse_dir = OUTPUT_DIR / "wheelhouse" / f"{name}-{version}"

    try:
        wheelhouse_dir.mkdir(parents=True, exist_ok=True)

        # 1. 主包 wheel（构建工具链 = uv；依赖由 --with-deps 单独处理）
        _run([uv, "build", "--wheel", "--out-dir", str(wheelhouse_dir)], cwd=ROOT)

        # 2. 收集主包 wheel（wheel 文件名里的 `-` 会被归一化成 `_`）
        wheel_prefix = name.replace("-", "_") + "-"
        main_wheels = [
            path.name
            for path in wheelhouse_dir.iterdir()
            if path.name.startswith(wheel_prefix) and path.name.endswith(".whl")
        ]
        if len(main_wheels) != 1:
            raise SystemExit(f"主包 wheel 数量异常（期望 1 个）: {main_wheels}")
        main_wheel = main_wheels[0]
        print(f"\n主包 wheel: {wheelhouse_dir / main_wheel}")

        # 3. 可选：拉依赖并打离线 ZIP（依赖为纯 Python，跨平台通用；pip 为声明例外）
        if args.with_deps:
            _download_deps(wheelhouse_dir, wheelhouse_dir / main_wheel)
            zip_path = OUTPUT_DIR / f"{name}-{version}-py3-none-any.zip"
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for path in sorted(wheelhouse_dir.iterdir()):
                    zf.write(path, arcname=path.name)
            print(f"离线 ZIP: {zip_path}")
    finally:
        _clean_artifacts()


if __name__ == "__main__":
    raise SystemExit(main())
