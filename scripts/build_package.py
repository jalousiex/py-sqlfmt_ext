#!/usr/bin/env python3
"""构建 sqlfmt_ext 的 wheel（可选连依赖打成离线 ZIP）。

用法:
    python scripts/build_package.py                # 只出主包 wheel
    python scripts/build_package.py --with-deps    # 连运行依赖一起打 ZIP（离线分发）
    python scripts/build_package.py 0.1.1          # 指定新版本号后再构建

做法对齐隔壁 py-dataphin/scripts/build_package.py：
    pip wheel <仓库根> --no-deps --wheel-dir <wheelhouse>
产物落在 scripts/output/wheels/（已被 .gitignore 的 `output/` 覆盖，不入库）。

与隔壁的差异：本项目唯一的运行依赖 sqlparse 是纯 Python（py3-none-any），
所以**不传 --platform / --implementation / --abi 那组跨平台限定** ——
那是为隔壁的 Linux 计算任务准备的，这里下载到的 wheel 在 Windows / Linux 通用。
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
    version = _bump_version(args.version)
    wheelhouse_dir = OUTPUT_DIR / "wheelhouse" / f"{name}-{version}"

    try:
        wheelhouse_dir.mkdir(parents=True, exist_ok=True)

        # 1. 主包 wheel（--no-deps：依赖单独处理）
        _run(
            [sys.executable, "-m", "pip", "wheel", ROOT, "--no-deps", "--wheel-dir", wheelhouse_dir],
            cwd=ROOT,
        )

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

        # 3. 可选：拉依赖并打离线 ZIP（依赖为纯 Python，跨平台通用）
        if args.with_deps:
            _run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "download",
                    "--only-binary=:all:",
                    "--dest",
                    wheelhouse_dir,
                    wheelhouse_dir / main_wheel,
                ],
                cwd=ROOT,
            )
            zip_path = OUTPUT_DIR / f"{name}-{version}-py3-none-any.zip"
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for path in sorted(wheelhouse_dir.iterdir()):
                    zf.write(path, arcname=path.name)
            print(f"离线 ZIP: {zip_path}")
    finally:
        _clean_artifacts()


if __name__ == "__main__":
    raise SystemExit(main())
