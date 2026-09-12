"""增量 pass：在官方 filter 产出换行骨架之后，只做「改空白」的修饰。

约定
----
- 所有 pass 都是 ``stmtprocess`` 阶段的 filter，接口为 ``process(stmt) -> stmt``。
- pass 只允许改写 ``Whitespace`` token 的 ``value``，或插入/删除空白 token。
- pass 不允许删除、重排非空白 token，也不允许改变 token 的 ``ttype``。
- pass 的顺序固定：``LayoutPass``（换行位置）→ ``AlignPass``（同行内宽度）。
"""

from sqlfmt_ext.passes.align import AlignPass
from sqlfmt_ext.passes.layout import LayoutPass

__all__ = ["AlignPass", "LayoutPass"]
