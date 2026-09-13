#!/usr/bin/env python3
"""把打好的 wheel 装进「主环境」（与项目 .venv 隔离的那个解释器）。

用法:
    python scripts/install_to_main.py                    # 装最新构建出的 wheel
    python scripts/install_to_main.py --version 0.1.1    # 装指定版本
    python scripts/install_to_main.py --python <解释器>  # 临时指定主环境解释器

主环境解释器取值优先级：
    1. --python
    2. 环境变量 SQLFMT_MAIN_PYTHON
    3. %LOCALAPPDATA%\\Python\\pythoncore-3.14-64\\python.exe

安装用 `pip install --force-reinstall`（覆盖旧版本），并带 `--find-links <wheelhouse>`：
依赖 wheel 若已被 scripts/build_package.py --with-deps 拉到本地，离线也能装；
联网时照常从源解析依赖。装完打印解释器、命令行程序落点，并做一次 import 自检。
"""

import argparse
import os
import re
import subprocess
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
WHEELHOUSE_ROOT = SCRIPT_DIR / "output" / "wheels" / "wheelhouse"
PYPROJECT = ROOT / "pyproject.toml"
DEFAULT_MAIN_PYTHON = Path(os.environ.get("LOCALAPPDATA", "")) / "Python" / "pythoncore-3.14-64" / "python.exe"


def _run(cmd, cwd=None):
    print("  $ {}".format(" ".join(map(str, cmd))), flush=True)
    return subprocess.run(cmd, cwd=str(cwd or ROOT))


def _capture(cmd, cwd=None):
    """捕获子进程输出；cwd 为 None 时继承当前目录。"""
    return subprocess.run(
        cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )


def _read_pyproject(pattern):
    match = re.search(pattern, PYPROJECT.read_text(encoding="utf-8"), re.MULTILINE)
    if not match:
        raise SystemExit(f"无法从 {PYPROJECT} 解析: {pattern}")
    return match.group(1)


def find_latest_wheel(name, version=None):
    """在 wheelhouse 下定位主包 wheel；不指定版本时取 mtime 最新的那个。"""
    if version:
        candidates = sorted((WHEELHOUSE_ROOT / f"{name}-{version}").glob(f"{name}-{version}-*.whl"))
    else:
        candidates = []
        for package_dir in WHEELHOUSE_ROOT.glob(f"{name}-*"):
            candidates.extend(package_dir.glob(f"{name}-*.whl"))
        candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    if not candidates:
        raise SystemExit(f"没找到 wheel，请先跑 scripts/build_package.py（查找目录：{WHEELHOUSE_ROOT}）")
    return candidates[0]


def main(argv=None):
    parser = argparse.ArgumentParser(description="把 sqlfmt_ext wheel 装进主环境")
    parser.add_argument("--python", help="主环境解释器路径（默认取 SQLFMT_MAIN_PYTHON 或 %%LOCALAPPDATA%% 下的 PythonCore）")
    parser.add_argument("--version", help="指定要安装的版本；省略则用最新构建物")
    parser.add_argument("--no-deps", action="store_true", help="只装主包，不解析依赖")
    args = parser.parse_args(argv)

    name = _read_pyproject(r'^name\s*=\s*"([^"]+)"')
    main_python = Path(args.python or os.environ.get("SQLFMT_MAIN_PYTHON") or DEFAULT_MAIN_PYTHON)
    if not main_python.is_file():
        raise SystemExit(f"主环境解释器不存在：{main_python}（用 --python 指定）")

    wheel = find_latest_wheel(name, args.version)
    print(f"主环境 python: {main_python}")
    print(f"安装 wheel   : {wheel}\n")

    cmd = [str(main_python), "-m", "pip", "install", "--force-reinstall"]
    if args.no_deps:
        cmd.append("--no-deps")
    cmd += ["--find-links", str(wheel.parent), str(wheel)]
    if _run(cmd).returncode != 0:
        raise SystemExit("安装失败")

    scripts_dir = _capture([str(main_python), "-c", "import sysconfig; print(sysconfig.get_path('scripts'))"]).stdout.strip()
    exe = Path(scripts_dir) / (name + (".exe" if os.name == "nt" else ""))
    show = _capture([str(main_python), "-m", "pip", "show", name]).stdout.strip()
    # 自检必须在项目目录之外跑：否则 cwd 会把仓库源码塞进 sys.path，命中的是源码而非安装副本。
    imported = _capture([str(main_python), "-c", f"import {name}; print({name}.__file__)"], cwd=tempfile.gettempdir())
    import_path = imported.stdout.strip() or imported.stderr.strip()
    hit_installed = "site-packages" in import_path

    print(f"\n命令行程序: {exe}  ({'存在' if exe.is_file() else '未找到！'})")
    print(f"包元信息 : {show.splitlines()[1] if len(show.splitlines()) > 1 else show}")
    print(f"import   : {import_path}{'' if hit_installed else '   ← 未命中 site-packages，自检不可信'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
