"""AlignPass：列对齐（只改同行内空白宽度，绝不改换行位置）。

职责范围（相对官方 AlignedIndentFilter 输出）——待移植：

1. 字段列表对齐（``align_list`` 开启时）。
   把 AS / 别名按列右对齐，逗号前留出对齐宽度。
   参考实现：旧 fork ``aligned_indent.py``
   ``_identifier_layout`` / ``_identifier_layouts`` /
   ``_apply_identifier_layout`` / ``_align_identifierlist`` / ``_set_adjacent_ws``。

2. DDL/INSERT 字段定义对齐（CREATE TABLE 的列块）。
   名称、类型、约束、默认值、注释分列对齐。
   参考实现：旧 fork ``_create_field_lines`` / ``_create_column_target`` /
   ``_align_create_columns``。

3. 注释列对齐（行首注释跟随所属列）。
   参考实现：旧 fork ``_process_comment``。

与旧实现的差异：本 pass 在官方骨架之上运行，因此**不需要**任何
``_remove_prev_newline`` / ``_collapse_newline`` 之类的擦除逻辑——换行已由官方
filter 定死，这里只改同一行内的空白宽度。

当前为占位实现：pipeline 已接通，但尚未改任何东西。
"""


class AlignPass:
    def __init__(self, options=None):
        opts = options or {}
        self.char = opts.get("indent_char", " ")
        self.align_list = opts.get("align_list", True)
        self.comma_first = opts.get("comma_first", False)

    def process(self, stmt):
        return stmt
