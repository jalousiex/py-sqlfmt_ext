"""方言层验收：证明「方言」是真开关，而不是装饰性声明（`PLAN §9.9`）。

三条断言对应 `PLAN §9.9` 的三个验收点：
1. Doris/SelectDB 声明的锚点词会让 `duplicate key` / `distributed by` / `properties` 各自成行；
2. `dialect=None`（官方基线）**不**触发这些换行 —— 开关真的在起作用；
3. 未知方言直接报错，不再静默降级到通用路径。
"""

import pytest
from sqlparse.exceptions import SQLParseError

from tests.sqlfmt_test_helpers import format_with_options

# 一条含 Doris 建表模型定义的最小 DDL
DORIS_DDL = (
    "create table t (id int, name varchar(10)) "
    "duplicate key(id) distributed by hash(id) properties (1);"
)

DORIS_EXPECTED = (
    "create table t (\n"
    "       id   int        ,\n"
    "       name varchar(10)\n"
    ")\n"
    "duplicate key(id)\n"
    "distributed by hash(id)\n"
    "properties (1);"
)


def test_doris_dialect_breaks_before_model_keywords():
    assert format_with_options(DORIS_DDL, dialect="doris") == DORIS_EXPECTED


def test_selectdb_shares_doris_declarations():
    """SelectDB 与 Doris 同族，共用同一份声明。"""
    assert format_with_options(DORIS_DDL, dialect="selectdb") == DORIS_EXPECTED


def test_generic_dialect_does_not_apply_doris_keywords():
    """`dialect=None` 走官方基线：Doris 专属关键字不触发换行。"""
    generic = format_with_options(DORIS_DDL, dialect=None)
    assert generic == DORIS_DDL
    assert generic != format_with_options(DORIS_DDL, dialect="doris")


def test_unknown_dialect_raises():
    with pytest.raises(SQLParseError, match="unknown dialect"):
        format_with_options(DORIS_DDL, dialect="typo")
