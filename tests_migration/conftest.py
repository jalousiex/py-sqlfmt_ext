"""迁移期脚手架：让 .venv 里的官方 sqlparse 优先于仓库内的旧 fork。

仓库根的 ``sqlparse/`` 是旧 fork，会在 sys.path 中遮蔽已安装的官方包。
这里把仓库根挪到 sys.path 末尾，使 site-packages 先被检索到。

迁移完成（删除 fork）后，本文件可直接删除。
"""

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 两个套件不能在同一次 pytest 会话里一起跑：
#   本文件会调整 sys.path 让官方 sqlparse 胜出，这是**进程级**副作用；
#   而 tests/ 依赖仓库内的旧 fork，两者共处一进程必然一方全红。
#   迁移完成（S7 删除 fork 与本文件）后此限制自然消失。
_MIXED = (
    "tests/ 与 tests_migration/ 不能在同一次 pytest 会话里一起运行：\n"
    "  迁移期需要两个不同的 sqlparse（仓库 fork vs 已安装官方包），\n"
    "  同进程只能加载一个。请分别运行：\n"
    "    .venv\\Scripts\\python.exe -m pytest tests/ -q\n"
    "    .venv\\Scripts\\python.exe -m pytest tests_migration/ -q"
)


def pytest_configure(config):
    args = [str(a).replace("\\", "/").rstrip("/") for a in config.args]
    if not args:
        raise pytest.UsageError(_MIXED + "\n  （不传路径会同时收集两个套件）")
    has_main = any(a == "tests" or a.startswith("tests/") for a in args)
    has_migration = any(a == "tests_migration" or a.startswith("tests_migration/") for a in args)
    if has_main and has_migration:
        raise pytest.UsageError(_MIXED)


def _prefer_installed_sqlparse():
    root = os.path.normcase(os.path.abspath(_ROOT))

    def is_root(path):
        return os.path.normcase(os.path.abspath(path or os.getcwd())) == root

    sys.path[:] = [p for p in sys.path if not is_root(p)]
    sys.path.append(_ROOT)


_prefer_installed_sqlparse()

import sqlparse  # noqa: E402

if "site-packages" not in getattr(sqlparse, "__file__", ""):
    raise RuntimeError(
        f"迁移对拍必须使用已安装的官方 sqlparse，实际加载：{sqlparse.__file__}"
    )
