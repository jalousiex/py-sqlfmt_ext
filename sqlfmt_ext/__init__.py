"""py-sqlfmt：基于官方 sqlparse 的 SQL 格式化外挂层。

设计原则
--------
1. 不修改、不复制 sqlparse 源码；官方包保持 pristine，仅作依赖。
2. 不 monkey-patch 官方函数。需要替换行为的 filter 一律「子类化 + 在官方
   FilterStack 里换装实例」接入。
3. 官方 filter 负责换行骨架，本项目只在官方之后追加「只改空白」的 pass，
   使输出只取决于 token 流（收敛性），与输入空白无关。
4. 方言差异（Doris/SelectDB 优先，官方缺失按 MySQL 兼容适配；后续 SQL Server）
   只用「追加声明」的方式注册，不修改官方分词表。
"""

from sqlfmt_ext.options import DEFAULT_OPTIONS, validate_options
from sqlfmt_ext.stack import build_stack, format_sql, format_statements

__all__ = [
    "DEFAULT_OPTIONS",
    "validate_options",
    "build_stack",
    "format_sql",
    "format_statements",
]

__version__ = "0.1.0"
