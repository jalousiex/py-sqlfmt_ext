r"""LayoutPass：修正换行骨架（只插入/合并换行，不改同行内宽度）。

职责范围（相对官方 AlignedIndentFilter 输出）——待移植的 3 条规则：

1. CASE 首个 WHEN 是否独占一行。
   官方输出：``case when x then 1``（首个 when 与 case 同行）。
   期望：``case`` 后换行，首个 ``when`` 独占一行。
   参考实现：旧 fork ``aligned_indent.py::_process_case`` L462-472
   （``has_nl and direct_after_case`` 分支），改为无条件规则。

2. 块注释之间保留换行（comma_first 场景）。
   官方 strip 会折叠掉注释之间的换行，期望保留。
   参考用例：``comma/sqltest7_s02``。

3. 多个 LATERAL VIEW 各自独占一行。
   官方输出会把连续的 ``lateral view`` 挤在同一行。
   参考实现：旧 fork ``aligned_indent.py::_split_kwds`` L841
   （把 ``LATERAL\s+VIEW`` 并入 join_words/by_words 的「只取首词缩进」分支）。
   参考用例：``dml/sqltest1_s06``。

当前为占位实现：pipeline 已接通，但尚未改任何东西。
"""


class LayoutPass:
    def __init__(self, options=None):
        opts = options or {}
        self.char = opts.get("indent_char", " ")
        self.comma_first = opts.get("comma_first", False)
        self.wrap_after = opts.get("wrap_after", 0)

    def process(self, stmt):
        return stmt
