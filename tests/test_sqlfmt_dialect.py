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


# --- S8-b：方言类型名（官方 0.6.0 词表缺失，S8-b 补齐）---------------------------

DORIS_TYPES_DDL = (
    "create table dw.t (id int64, name varchar(20), v1 string, v2 datev2, v3 datetimev2(3), "
    "v4 decimalv3(10, 2), v5 largeint, v6 bitmap, v7 jsonb);"
)

DORIS_TYPES_EXPECTED = (
    "create table dw.t (\n"
    "       id       int64           ,\n"
    "       name     varchar(20)     ,\n"
    "       v1       string          ,\n"
    "       v2       datev2          ,\n"
    "       v3       datetimev2(3)   ,\n"
    "       v4       decimalv3(10, 2),\n"
    "       v5       largeint        ,\n"
    "       v6       bitmap          ,\n"
    "       v7 jsonb\n"
    ");"
)


def test_doris_type_names_keep_ddl_columns_aligned():
    """Doris 类型名（int64 / datev2 / datetimev2 / decimalv3 / largeint / bitmap）必须与字段名分开。

    官方 0.6.0 词表缺这些词 → 落成普通 ``Name`` → 被 ``group_identifier`` 与字段名粘成一个
    ``Identifier`` → ``_create_field_lines`` 的类型列取不到 token → 整条 DDL 的列基准错
    （U16 的机理，当时只补了 ``DATETIME``）。
    """
    assert format_with_options(DORIS_TYPES_DDL, dialect="doris") == DORIS_TYPES_EXPECTED


def test_generic_dialect_keeps_doris_type_names_as_plain_names():
    """`dialect=None` 不补词表：字段名与类型名仍被粘在一起（开关只在 doris/selectdb 生效）。"""
    generic = format_with_options(DORIS_TYPES_DDL, dialect=None)
    assert "id int64" in generic
    assert generic != format_with_options(DORIS_TYPES_DDL, dialect="doris")


# --- S8-c：SQL Server 适配（GO / TOP / WITH(NOLOCK)；`[ ]` 官方已支持）-------------

SQLSERVER_TOP = "select top 10 id, name from dbo.t;"
SQLSERVER_TOP_EXPECTED = "select top 10 id  ,\n              name\n  from dbo.t;"


def test_sqlserver_top_does_not_break_field_columns():
    """`TOP <n>` 必须留在字段列表之外，列基准得按真实字段名算。

    `dialect=None` 时 `top` 落普通 `Name` → 紧跟的数字被 `group_identifier_list` 的
    extend 收进**第一个列表项** → 基准取到数字上：`id` 被右顶、`name` 退回 DML 列。
    """
    assert format_with_options(SQLSERVER_TOP, dialect="sqlserver") == SQLSERVER_TOP_EXPECTED
    generic = format_with_options(SQLSERVER_TOP, dialect=None)
    assert generic != SQLSERVER_TOP_EXPECTED
    assert "top 10   id," in generic


SQLSERVER_HINT = "select id from dbo.t with (nolock);"
SQLSERVER_HINT_EXPECTED = "select id\n  from dbo.t with (nolock);"


def test_sqlserver_table_hint_does_not_break_line():
    """`WITH (NOLOCK)` 表提示不能让 `WITH` 被当成 CTE 而独占一行。"""
    assert format_with_options(SQLSERVER_HINT, dialect="sqlserver") == SQLSERVER_HINT_EXPECTED
    # `dialect=None` 认 `T.CTE` → `with (nolock)` 换行成独占一行（开关真起作用）
    assert format_with_options(SQLSERVER_HINT, dialect=None) != SQLSERVER_HINT_EXPECTED


def test_sqlserver_splits_batches_on_go():
    """`GO` 独占一个 token 时切批；输出恒用声明字面量 `GO`（与输入大小写/空白无关）。"""
    assert format_with_options("select 1\nGO\nselect 2", dialect="sqlserver") == "select 1\nGO\n\nselect 2"
    # 小写 `go` 同样切批，输出仍是声明里的 `GO`（满足 C4：不依赖输入空白/大小写）
    assert format_with_options("select 1; go\nselect 2;", dialect="sqlserver") == "select 1;\nGO\n\nselect 2;"
    # `dialect=None` 没有批概念 → `go` 被当成普通词胶进上一句
    assert format_with_options("select 1\nGO\nselect 2", dialect=None) == "select 1 go\n\nselect 2"


# --- S8-d：MySQL 方言（类型名 / 表选项 / ON DUPLICATE KEY UPDATE）-----------------

MYSQL_TYPES_DDL = "create table t (id bigint, content mediumtext, data longblob, created_at datetime);"

MYSQL_TYPES_EXPECTED = (
    "create table t (\n"
    "       id         bigint    ,\n"
    "       content    mediumtext,\n"
    "       data       longblob  ,\n"
    "       created_at datetime\n"
    ");"
)


def test_mysql_type_names_keep_ddl_columns_aligned():
    """MySQL 类型名必须与字段名分开，否则 DDL 的类型列取不到 token（U16 同机理）。

    `mediumtext` / `longblob` / `datetime` 都不在官方词表里 → 落普通 `Name`，被
    `group_identifier` 与字段名粘成一个 `Identifier`：`content mediumtext` 挤进同一列。
    """
    assert format_with_options(MYSQL_TYPES_DDL, dialect="mysql") == MYSQL_TYPES_EXPECTED
    generic = format_with_options(MYSQL_TYPES_DDL, dialect=None)
    assert generic != MYSQL_TYPES_EXPECTED
    assert "content mediumtext" in generic


MYSQL_OPTIONS_DDL = "create table t (id int) engine=innodb default charset=utf8mb4 comment='表';"

MYSQL_OPTIONS_EXPECTED = (
    "create table t (id int)\n"
    "engine = innodb\n"
    "default charset = utf8mb4\n"
    "comment = '表';"
)


def test_mysql_table_options_each_start_a_line():
    """`)` 之后的表选项各自成行（与 Doris 的 `duplicated by` / `properties` 同形）。

    `dialect=None` 下它们全挤在 `)` 之后，换行只是 `wrap_after` 撞出来的。
    """
    assert format_with_options(MYSQL_OPTIONS_DDL, dialect="mysql") == MYSQL_OPTIONS_EXPECTED
    assert format_with_options(MYSQL_OPTIONS_DDL, dialect=None) != MYSQL_OPTIONS_EXPECTED


MYSQL_UPSERT = "insert into t (a, b) values (1, 2) on duplicate key update b = values(b);"


def test_mysql_on_duplicate_key_update_stays_inline():
    """`ON DUPLICATE KEY UPDATE` 必须并成一个多词关键字，且 `b = values(b)` 不被拆行。

    `values` 是**通用**换行锚点，不看邻接就会把赋值右值甩到下一行 → `_split_kwds` 用
    「锚点紧跟 `=` 时不换行」这条结构性判据兜住（与本方言无关）。
    """
    mysql = format_with_options(MYSQL_UPSERT, dialect="mysql")
    assert "on duplicate key update b = values(b);" in mysql
    generic = format_with_options(MYSQL_UPSERT, dialect=None)
    # 未合并时 `duplicate` 落 `Name`，整段被切成两行
    assert "on duplicate key\n" in generic
    assert "on duplicate key update" not in generic


def test_straight_join_right_after_select_is_a_modifier():
    """`SELECT` 后紧跟的锚点词是 select 修饰符，不换行（结构性判据，与方言无关）。

    `straight_join` 同时是 join 关键字（`policy._join_words` 就是靠 `JOIN\\b` 命中它的），
    仅看词表分不出「修饰符」与「join 运算符」两种用法，只能看它前面是不是 `SELECT`。
    """
    sql = "select straight_join a.id, a.name from t1 a where a.st = 1;"
    expected = "select straight_join a.id  ,\n                     a.name\n  from t1 a\n where a.st = 1;"
    assert format_with_options(sql, dialect="mysql") == expected
    assert format_with_options(sql, dialect=None) == expected
