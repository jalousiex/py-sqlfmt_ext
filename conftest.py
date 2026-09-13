"""仓库根 conftest：**守卫**「必须用 pip 装的官方 sqlparse」。

历史：仓库内曾 vendored 一份旧 fork（``sqlparse/``），它会遮蔽 site-packages 里的官方包；
迁移期靠把仓库根挪到 ``sys.path`` 末尾来让官方包胜出（S7-b 起提到根级）。
S7-c 已把那份 fork 删除，于是这段 sys.path 调整变成幂等的无操作 —— 但**校验保留**下来
当守卫：万一将来又有人把 sqlparse 拷进仓库，pytest 会立刻在这里报错，
而不是让整条测试链悄悄跑在另一个实现上。
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
