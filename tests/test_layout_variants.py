import pytest

from sqlfmt_ext import format_sql, format_statements
from tests.sqlfmt_test_helpers import format_with_entry_defaults


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "select a as schema_name, b as ordinary_name, c as 'caption' from t",
            """select a as schema_name  ,
       b as ordinary_name,
       c as 'caption'
  from t""",
        ),
        (
            "select *\nfrom t",
            "select * from t",
        ),
        (
            "select a\nfrom t\njoin u\non t.id = u.id\nwhere t.id = 1\norder by t.id",
            """select a
  from t
  join u
    on t.id = u.id
 where t.id = 1
 order by t.id""",
        ),
        (
            "select a, case\nwhen b = 'NUMBER'\nthen b || '(' ||\nnvl(c, '38') || ')'\nend as type_name from t",
            """select a               ,
       case when b = 'NUMBER' then b || '(' || nvl(c, '38') || ')'
       end as type_name
  from t""",
        ),
        (
            "select a\n  as\n  name, b as other from t",
            "select a as name ,\n       b as other\n  from t",
        ),
        (
            "select a, case -- note\nwhen b = 1\nthen b || '(' ||\nc || ')'\nend as result from t",
            "select a            ,\n       case -- note\n            when b = 1 then b || '(' || c || ')'\n       end as result\n  from t",
        ),
        (
            "select a\nfrom -- source\nt\nwhere a = 1",
            "select a\n  from -- source\n       t\n where a = 1",
        ),
        (
            "create table t (id int primary key, display_name varchar(50) not null default '', created_at timestamp comment 'created')",
            """create table t (
       id           int         primary key                             ,
       display_name varchar(50) not null    default ''                  ,
       created_at   timestamp                          comment 'created'
)""",
        ),
        (
            """select a
from t
where 1 = 1
and
a = 1""",
            """select a
  from t
 where 1 = 1
   and a = 1""",
        ),
        (
            "select a from t where a between\n1 and 2",
            "select a\n  from t\n where a between 1 and 2",
        ),
        (
            "select a from t union all\nselect b from u",
            """select a
  from t
 union all
select b
  from u""",
        ),
        (
            "create table t (id int comment\n'x', name varchar(10) comment 'y')",
            """create table t (
       id   int         comment 'x',
       name varchar(10) comment 'y'
)""",
        ),
        (
            "create table t (id int not\nnull, name varchar(10))",
            """create table t (
       id   int         not null,
       name varchar(10)
)""",
        ),
        (
            "select\n*\nfrom\nt",
            "select * from t",
        ),
        (
            "select a from t where exists\n(select 1)",
            "select a\n  from t\n where exists (select 1)",
        ),
        (
            "select a from t where b not\nlike 'x%' and c not\nin (1, 2)",
            "select a\n  from t\n where b not like 'x%'\n   and c not in (1, 2)",
        ),
    ],
    ids=(
        "keyword-alias",
        "simple-select-star",
        "keyword-right-hand-side",
        "case-operation",
        "as-inline-fold",
        "case-comment-boundary",
        "keyword-comment-boundary",
        "ddl-column-layout",
        "and-newline-fold",
        "between-newline-fold",
        "union-all-newline-fold",
        "ddl-column-comment-newline-fold",
        "ddl-column-multiword-keyword-newline-fold",
        "select-star-multiline-fold",
        "exists-newline-fold",
        "multiword-operator-newline-fold",
    ),
)
def test_layout_variants(source, expected):
    assert format_with_entry_defaults(source) == expected


@pytest.mark.parametrize(
    "formatter",
    [format_sql, format_statements],
    ids=("format-sql", "format-statements"),
)
def test_standalone_at_lines_are_preserved(formatter):
    directive = "  @custom value  "
    comment = "-- AI账单用户标识回退：先更新用量明细，再更新额度快照。"
    source = (
        "select  a from t\n"
        f"{directive}\n"
        f"{comment}\n"
        "@DWS.OA_AI_CREDIT_USAGE_F.sql\n"
        "@DWS.OA_AI_CREDIT_QUOTA_F.sql\n"
        "select  b from u"
    )
    expected = (
        "select a\n"
        "  from t\n"
        f"{directive}\n"
        f"{comment}\n"
        "@DWS.OA_AI_CREDIT_USAGE_F.sql\n"
        "@DWS.OA_AI_CREDIT_QUOTA_F.sql\n"
        "select b\n"
        "  from u"
    )
    assert formatter(source) == expected
