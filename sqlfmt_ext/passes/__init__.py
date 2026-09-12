"""本项目自己的 pass：换行骨架 + 同行空白对齐。

约定
----
- 所有 pass 都是 ``stmtprocess`` 阶段的 filter，接口为 ``process(stmt) -> stmt``。
- pass 只允许改写 ``Whitespace`` token 的 ``value``，或插入/删除空白 token。
- pass 不允许删除、重排非空白 token，也不允许改变 token 的 ``ttype``。

分工
----
- ``layout.LayoutPass``：断行位置 + 缩进宽度（唯一的换行决策处）。
- ``align.AlignMixin``：同行空白宽度（列对齐规则集，由 ``LayoutPass`` 组合）。

两者不做成前后两个独立 pass，是因为断行宽度与列对齐互相依赖（例如 CASE 的
THEN 对齐要先知道条件宽度），强行拆开会需要重复遍历并重复计算偏移。
"""

from sqlfmt_ext.passes.align import AlignMixin
from sqlfmt_ext.passes.layout import LayoutPass

__all__ = ["AlignMixin", "LayoutPass"]
