#!/usr/bin/python
# -*- coding: UTF-8 -*-
"""`python -m sqlfmt_ext`（含 `py -m sqlfmt_ext`）的入口：转发到 `sqlfmt_ext.cli.main`。

三条调用路径 —— console script `sqlfmt_ext`、`-m sqlfmt_ext`、`-m sqlfmt_ext.cli` ——
因此共享同一份实现，行为不会分叉。
"""

from sqlfmt_ext.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
