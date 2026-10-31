#!/usr/bin/env python3
"""构建 sqlfmt_ext 的 wheel（可选连依赖打成离线 ZIP）。

用法:
    python scripts/build_package.py                # 只出主包 wheel
    python scripts/build_package.py --with-deps    # 连运行依赖一起打 ZIP（离线分发）
    python scripts/build_package.py 0.1.1          # 指定新版本号后再构建

构建工具链（E2 起统一为 **uv**，不再走 pip）：
    uv build --wheel --out-dir <wheelhouse>
产物落在**运行位置**（VS Code 打包任务的 cwd = 工作区根）的 `output/wheels/`（已被 .gitignore 的
`output/` 覆盖，不入库）—— 不挂在脚本所在目录下面，跑在哪就出在哪。

wheelhouse 是**共享池**：`output/wheels/wheelhouse/` 一个平铺目录，主包 whl 与依赖 whl 共存，
**不按版本分子目录**（对齐隔壁 py-dataphin）—— 同名 whl 全仓只存一份，重复打包直接复用。
代价是池里会沉淀历史版本，故 ZIP 的内容**不能**照抄整个池：只放「主包 + 本次依赖闭包」内的 whl
（闭包用 pip 的 `--dry-run --report` 解析，与 `pip download` 同源、不自写元数据解析器）。

与参考项目 py-dolphin_scheduler 的差异：**不做 wheel 内容断言** —— 本项目只有单一顶层命名空间
`sqlfmt_ext/`（由 `[tool.setuptools.packages.find]` 限定），不存在「运行期数据混进包里」的历史问题。

> **`uv` 必须在 PATH 上**。缺它直接报错给指引，**不回落 pip** —— 回落会让「构建到底用哪套工具」
> 变成看环境而定，产物也就说不清是哪个工具链出的。
>
> **`--with-deps` 是全项目唯一保留的 pip 用法**（声明例外）：uv 的 `pip` 子命令没有 `download`，
> 而离线 ZIP 要的是「只取 wheel、不安装」，uv 无等价能力（其 `install --target` 是解包安装）。
> 登记在 `.claude/plan/status.md` §3.5；唯一的运行依赖 sqlparse 是纯 Python（py3-none-any），
> 所以**不传 --platform / --implementation / --abi 那组跨平台限定**，拉到的 wheel 在 Windows / Linux 通用。
>
> pip **不是**用 `sys.executable -m pip` 调的：本脚本由 `uv run python` 启动时 `sys.executable` 就是
> `.venv` 的解释器，而 uv 建的 venv **不带 pip**（实测报 `No module named pip`）。故与隔壁 py-dataphin
> 同口径，用 `uv run --no-project --with pip python -m pip` 由 uv 临时环境注入 pip（源仍是 uv 当前配置 /
> 机器 pip 配置，本项目单依赖纯 Python，无跨源挑选问题）。
"""

import argparse
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
# 产物目录跟**运行位置**走（2026-10-31 用户定）：VS Code 打包任务的 cwd 是工作区根，故落在
# `<仓库根>/output/wheels/`；从别处跑就落在那个 cwd 下。构建本身用 ROOT 绝对定位，不受 cwd 影响。
OUTPUT_DIR = Path.cwd() / "output" / "wheels"
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


def _download_deps(wheelhouse_dir, main_wheel, uv):
    """把主包依赖的 wheel 拉进 wheelhouse（**本脚本唯一保留 pip 的步骤**，声明例外）。

    为什么还用 pip：uv 的 ``pip`` 子命令只有 compile / sync / install / uninstall / freeze /
    list / show / tree / check，**没有 ``download``**；离线 ZIP 要的是「只取 wheel、不安装」，
    uv 无等价能力（``install --target`` 是解包安装，不是 wheel 包）。
    这是**声明例外**，登记在 ``.claude/plan/status.md`` §3.5；改造前先看那条。

    pip 由 ``uv run --no-project --with pip`` 注入（**不用** ``sys.executable -m pip``）：
    uv 建的 venv 不带 pip，``uv run python`` 下的 ``sys.executable`` 就是它，实测直接
    ``No module named pip``（2026-10-31）。与隔壁 py-dataphin 同口径。
    """
    _run(
        [
            uv,
            "run",
            "--no-project",
            "--with",
            "pip",
            "python",
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


def _resolve_closure(wheelhouse_dir, main_wheel, uv):
    """用 pip 的解析器算出主包的依赖闭包，返回文件名列表（含主包）。

    与步骤 3 的 `pip download` 同源解析（同一套环境标记求值），但只在共享池内解析
    （`--no-index --find-links`，不走网络）；`--dry-run` 不安装、`--report` 输出 JSON
    供取闭包文件名。不自写 whl 元数据解析器（对齐隔壁 py-dataphin）。

    共享池里会沉淀历史版本（同名多版本并存），所以 ZIP 内容必须走闭包，不能照抄整个池。
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        report_path = Path(tmp_dir) / "report.json"
        print("  $ uv run --no-project --with pip python -m pip install --dry-run ... (解析依赖闭包)")
        result = subprocess.run(
            [
                uv,
                "run",
                "--no-project",
                "--with",
                "pip",
                "python",
                "-m",
                "pip",
                "install",
                "--dry-run",
                "--ignore-installed",
                "--only-binary=:all:",
                "--no-index",
                "--find-links",
                str(wheelhouse_dir),
                "--target",
                tmp_dir,
                "--report",
                str(report_path),
                str(wheelhouse_dir / main_wheel),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            output = "".join(part for part in (result.stdout, result.stderr) if part)
            raise SystemExit(f"依赖闭包解析失败（退出码 {result.returncode}）:\n{output.rstrip()}")
        report = json.loads(report_path.read_text(encoding="utf-8"))

    names = {main_wheel}
    for item in report.get("install", []):
        url = item.get("download_info", {}).get("url", "")
        filename = Path(unquote(urlparse(url).path)).name
        if filename.endswith(".whl"):
            names.add(filename)
    missing = sorted(name for name in names if not (wheelhouse_dir / name).is_file())
    if missing:
        raise SystemExit(f"闭包解析出的 whl 不在共享池: {', '.join(missing)}")
    return sorted(names)


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
    # 共享池：一个平铺目录，主包与依赖 whl 共存（不按版本分子目录，对齐隔壁 py-dataphin）
    wheelhouse_dir = OUTPUT_DIR / "wheelhouse"

    try:
        wheelhouse_dir.mkdir(parents=True, exist_ok=True)

        # 1. 主包 wheel（构建工具链 = uv；依赖由 --with-deps 单独处理）
        _run([uv, "build", "--wheel", "--out-dir", str(wheelhouse_dir)], cwd=ROOT)

        # 2. 收集主包 wheel（wheel 文件名里的 `-` 会被归一化成 `_`）。
        #    共享池里可能并存旧版本，按「包名-版本-」精确前缀取，避免误收（对齐隔壁 py-dataphin）。
        wheel_prefix = name.replace("-", "_") + f"-{version}-"
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
        #    ZIP 只放「主包 + 本次依赖闭包」内的 whl（闭包解析见 _resolve_closure），
        #    不把共享池里的历史版本卷进去；解包后
        #    `uv tool install sqlfmt_ext --offline --find-links <目录>` 即可。
        if args.with_deps:
            _download_deps(wheelhouse_dir, wheelhouse_dir / main_wheel, uv)
            zip_path = OUTPUT_DIR / f"{name}-{version}-py3-none-any.zip"
            files = _resolve_closure(wheelhouse_dir, main_wheel, uv)
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for fname in files:
                    zf.write(wheelhouse_dir / fname, arcname=fname)
            print(f"离线 ZIP: {zip_path}（{len(files)} 个 whl）")
    finally:
        _clean_artifacts()


if __name__ == "__main__":
    raise SystemExit(main())
