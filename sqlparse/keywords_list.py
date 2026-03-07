# 公共的关键字列表

join_words = (
    r"((LEFT\s+|RIGHT\s+|FULL\s+)?"
    r"(INNER\s+|OUTER\s+|STRAIGHT\s+)?|"
    r"(CROSS\s+|NATURAL\s+)?)?JOIN\b|"
    r"UNION\s+ALL\b"
)
by_words = r"(GROUP|ORDER)\s+BY\b"
split_words = (
    "FROM",
    join_words,
    by_words,
    "WHERE",
    "AND",
    r"\bOR",
    "HAVING",
    "LIMIT",
    "UNION",
    "VALUES",
    "SET",
    "BETWEEN",
    "EXCEPT",
    "COMMENT",
    "ROLLUP",
    "PROPERTIES",
    r"BUILD\s+(IMMEDIATE|DEFERRED)\b",
    r"REFRESH\b",
    r"\bON\s+(MANUAL|SCHEDULE|COMMIT)\b",
    r"(DUPLICATE|UNIQUE|AGGREGATE)\b",
    r"(AUTO\s+)?PARTITION\s+BY\b",
    r"DISTRIBUTED\s+BY\b",
    r"\bON",
)
