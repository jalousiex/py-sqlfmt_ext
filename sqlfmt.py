#!/usr/bin/python
# -*- coding: UTF-8 -*-
"""
原始用法 python -m sqlparse ${file} --keywords="lower" --reindent_aligned --indent_width=4 --wrap_after=100 --use_space_around_operators
                    sqlformat.exe ${file} -k lower -a --indent_width 4 -s --wrap_after 100 --encoding utf-8-sig
本项目用法
python.exe _DBeaverData/sqlfmt.py ${file} -k lower -a --indent_width 4 -s --wrap_after 100
"""

import io
import os
import sys

# 先把当前脚本目录放到 sys.path 最前面
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

enc = "utf-8"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding=enc)  # 设置标准输出

import sqlparse as sp
from sqlparse.cli import main


def sqlfmt(sql):
    return sp.format(
        sql,
        encoding=enc,
        keyword_case="lower",  # -k
        # identifier_case="", # -i
        # truncate_char='\\',
        # indent_columns=True,  # 是否固定缩进对齐, 否则关键字长度对齐
        indent_width=4,
        # reindent=True, # -r 字段尽量一行, 与下面互斥？
        # indent_after_first=True, # 首行后缩进？只对-r生效
        reindent_aligned=True,  # -a 字段单独一行
        wrap_after=30,
        use_space_around_operators=True,  # -s
    )


def sqlfilefmt(sql):
    rst = []
    for s in sp.split(sql):
        # print(sqlfmt(s))
        rst.append(sqlfmt(s))
    return "\n\n".join(rst)


if __name__ == "__main__":
    # print(__name__); print(sys.path); print(sys.argv)
    # sys.argv.append(r'C:\_GitRoot\dwm\backup\dwm_doris\3view_ddl')
    # sys.argv += '-k lower -a --indent_width 4 -s --wrap_after 100 --encoding utf-8'.split()

    if len(sys.argv) > 1:
        # sys.exit(main(sys.argv[1:])) # 转发参数, 只支持文件

        pth = sys.argv[1]
        if not os.path.exists(pth):
            print("路径不存在：" + pth)
        elif os.path.isdir(pth):  # 目录遍历, 回写原文件？
            for root, _, files in os.walk(pth):  # root,dirs,files
                for f in files:
                    with open(os.path.join(root, f), "r+", encoding=enc) as fd:
                        sql = sqlfilefmt(fd.read())
                        # 将文件指针回到开头
                        fd.seek(0)
                        # 截断文件到当前指针位置（即清空文件）
                        fd.truncate()
                        # 写入新内容
                        fd.write(sql)
        elif os.path.isfile(pth):  # 文件标准输出
            with open(pth, "r", encoding=enc) as fd:
                sql = sqlfilefmt(fd)
            print(sql, end="")
    else:
        print("=" * 15 + "\n" + sqlfilefmt("select * from tab t where 1=1 and t.a = 1;"))
