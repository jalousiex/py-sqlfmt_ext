import sys

sys.path.insert(0, ".")

import sqlparse
from sqlparse import lexer
from sqlparse import tokens as T

SNIPPETS = [
    "order by x",
    "order\n by x",
    "group\tby x",
    "partition\nby x",
    "not\nnull",
    "not\nlike",
    "left\njoin",
    "on\ncommit",
]

for s in SNIPPETS:
    print("=" * 60)
    print(repr(s))
    for ttype, value in lexer.tokenize(s):
        print(f"    {str(ttype):28} {value!r}  is_keyword={ttype in T.Keyword}")
    flat = [str(t) for t in sqlparse.parse(s)[0].flatten()]
    print("    parsed flatten:", flat)
