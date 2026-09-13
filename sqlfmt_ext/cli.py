#!/usr/bin/python
# -*- coding: UTF-8 -*-
"""CLI 真身：console script ``sqlfmt_ext`` 与 ``python -m sqlfmt_ext.cli`` 共用。

逻辑与已下线的根 ``sqlfmt.py`` 逐行等价（参数集合、目录递归、``--in-place``、
``--encoding``、无路径时的自检输出），只是从脚本顶层收进 ``main()``，
以便 console script 与 ``-m`` 走同一份实现，行为不会分叉。
"""

from __future__ import annotations

import argparse
import os
import sys

from sqlfmt_ext import format_statements

enc = "utf-8"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sqlfmt_ext",
        description="基于官方 sqlparse 0.6 的 SQL 格式化器（Doris/SelectDB 优先）",
    )
    parser.add_argument("path", nargs="?")
    parser.add_argument("--in-place", action="store_true")
    parser.add_argument("-k", "--keywords", dest="keyword_case", choices=["upper", "lower", "capitalize"])
    parser.add_argument("-i", "--identifiers", dest="identifier_case", choices=["upper", "lower", "capitalize"])
    parser.add_argument("-l", "--language", dest="output_format", choices=["python", "php"])
    parser.add_argument("--strip-comments", action="store_true", default=None)
    parser.add_argument("-r", "--reindent", action="store_true", default=None)
    parser.add_argument("--indent_width", type=int)
    parser.add_argument("--indent_after_first", action="store_true", default=None)
    parser.add_argument("--indent_columns", action="store_true", default=None)
    parser.add_argument("-a", "--reindent_aligned", action="store_true", default=None)
    parser.add_argument("-s", "--use_space_around_operators", action="store_true", default=None)
    parser.add_argument("--wrap_after", type=int)
    parser.add_argument("--comma_first", action="store_true", default=None)
    parser.add_argument("--align_list", action="store_true", default=None)
    parser.add_argument("--compact", action="store_true", default=None)
    parser.add_argument("--encoding", default=enc)
    return parser


def main(argv: list[str] | None = None) -> int:
    """返回进程退出码：0 正常（无 path 时打印用法）；1 路径不存在。"""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.path:
        parser.print_help()
        return 0

    pth = args.path
    if not os.path.exists(pth):
        print("路径不存在：" + pth)
        return 1

    # 未显式指定的选项不进入 options：交给 sqlfmt_ext 侧补默认值（与旧脚本一致）。
    options = {
        key: value
        for key, value in vars(args).items()
        if key not in {"path", "in_place"} and value is not None
    }
    paths = (
        (os.path.join(root, filename) for root, _, filenames in os.walk(pth) for filename in filenames)
        if os.path.isdir(pth)
        else [pth]
    )
    for file_path in paths:
        with open(file_path, "r+" if args.in_place else "r", encoding=args.encoding) as fd:
            sql = format_statements(fd.read(), options)
            if args.in_place:
                fd.seek(0)
                fd.truncate()
                fd.write(sql)
            else:
                print(sql, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
