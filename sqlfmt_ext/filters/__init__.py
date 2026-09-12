"""对官方 filter 做「子类化替换」的地方。

这里只允许放「替换官方某个 filter 实例」的子类；纯增量的空白/换行调整放到
``sqlfmt_ext.passes``。
"""

from sqlfmt_ext.filters.operators import SpacesAroundOperatorsFilter

__all__ = ["SpacesAroundOperatorsFilter"]
