"""仓库根 conftest：让**已安装的官方** ``sqlparse`` 优先于仓库内的旧 fork。

背景：仓库根的 ``sqlparse/`` 是旧 fork，会遮蔽 site-packages 里的官方包。
新实现（``sqlfmt_ext``）写在官方 0.6.0 之上，入口 `sqlfmt.py` 已切到它，
因此任何一次 pytest 都必须拿到官方包 —— 这里把仓库根挪到 ``sys.path`` 末尾，
使 site-packages 先被检索到（与迁移期 `tests_migration/conftest.py` 里的
sys.path 调整同义，S7-b 起提到根级，两套件共用）。

S7-c 删除 vendored fork 之后本文件即可删除；留着也是幂等的无操作。
"""

import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))


def _prefer_installed_sqlparse():
    root = os.path.normcase(_ROOT)

    def is_root(path):
        return os.path.normcase(os.path.abspath(path or os.getcwd())) == root

    sys.path[:] = [p for p in sys.path if not is_root(p)]
    sys.path.append(_ROOT)


_prefer_installed_sqlparse()

import sqlparse  # noqa: E402

if "site-packages" not in getattr(sqlparse, "__file__", ""):
    raise RuntimeError(
        f"必须使用已安装的官方 sqlparse，实际加载：{sqlparse.__file__}"
    )
