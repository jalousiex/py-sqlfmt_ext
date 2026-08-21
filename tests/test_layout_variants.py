import pytest

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
       case
            when b = 'NUMBER' then b || '(' || nvl(c, '38') || ')'
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
    ],
    ids=(
        "keyword-alias",
        "simple-select-star",
        "keyword-right-hand-side",
        "case-operation",
        "as-inline-fold",
        "case-comment-boundary",
        "keyword-comment-boundary",
    ),
)
def test_layout_variants(source, expected):
    assert format_with_entry_defaults(source) == expected
