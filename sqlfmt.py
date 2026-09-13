#!/usr/bin/python
# -*- coding: UTF-8 -*-
"""
原始用法 python -m sqlparse ${file} --keywords="lower" --reindent_aligned --indent_width=4 --wrap_after=100 --use_space_around_operators
                    sqlformat.exe ${file} -k lower -a --indent_width 4 -s --wrap_after 100 --encoding utf-8-sig
本项目用法
python.exe _DBeaverData/sqlfmt.py ${file} -k lower -a --indent_width 4 -s --wrap_after 100
"""

import argparse
import os

# 入口已切到新实现（官方 sqlparse 0.6.0 + 本项目补偿层 `sqlfmt_ext`）。
# 旧 fork `sqlparse/` 在 S7-c 删除，之后本文件只剩「默认选项 + CLI」，成为纯薄壳。
from sqlfmt_ext import format_sql as _format_sql
from sqlfmt_ext import format_statements as _format_statements

enc = "utf-8"


DEFAULT_OPTIONS = {
    "keyword_case": "lower",
    "indent_width": 4,
    "reindent_aligned": True,
    "wrap_after": 30,
    "use_space_around_operators": True,
    "align_list": True,
}


def sqlfmt(sql, **options):
    """格式化**单条** SQL（与旧实现同义：不 strip、不拆分）。"""
    return _format_sql(sql, {**DEFAULT_OPTIONS, **options})


def sqlfilefmt(sql, **options):
    """按 ``;`` 拆分逐条格式化后以空行拼接（与旧实现同义）。"""
    return _format_statements(sql, {**DEFAULT_OPTIONS, **options})


if __name__ == "__main__":
    # print(__name__); print(sys.path); print(sys.argv)
    # sys.argv.append(r'C:\_GitRoot\dwm\backup\dwm_doris\3view_ddl')
    # sys.argv += '-k lower -a --indent_width 4 -s --wrap_after 100 --encoding utf-8'.split()

    parser = argparse.ArgumentParser()
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
    args = parser.parse_args()

    if args.path:
        pth = args.path
        if not os.path.exists(pth):
            print("路径不存在：" + pth)
        else:
            paths = (
                (os.path.join(root, filename) for root, _, filenames in os.walk(pth) for filename in filenames)
                if os.path.isdir(pth)
                else [pth]
            )
            for file_path in paths:
                with open(file_path, "r+" if args.in_place else "r", encoding=args.encoding) as fd:
                    options = {
                        key: value
                        for key, value in vars(args).items()
                        if key not in {"path", "in_place"} and value is not None
                    }
                    sql = sqlfilefmt(fd.read(), **options)
                    if args.in_place:
                        fd.seek(0)
                        fd.truncate()
                        fd.write(sql)
                    else:
                        print(sql, end="")
    else:
        print("=" * 15 + "\n" + sqlfilefmt("select * from tab t where 1=1 and t.a = 1;"))
