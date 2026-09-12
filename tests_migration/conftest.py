"""迁移期脚手架：让 .venv 里的官方 sqlparse 优先于仓库内的旧 fork。

仓库根的 ``sqlparse/`` 是旧 fork，会在 sys.path 中遮蔽已安装的官方包。
这里把仓库根挪到 sys.path 末尾，使 site-packages 先被检索到。

迁移完成（删除 fork）后，本文件可直接删除。
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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
