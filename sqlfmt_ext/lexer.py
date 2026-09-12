"""方言分词：在官方 ``Lexer`` 之上追加本项目的分词补丁。

做法是**子类化 + 初始化后追加**，不动官方模块的全局单例，也不改写官方已有条目；
因此官方升级分词表后，本项目自动继承，只有补丁条目需要维护。
"""

from sqlparse.lexer import Lexer

from . import policy

SUPPORTED_DIALECTS = ("doris", "selectdb")


class DialectLexer(Lexer):
    """官方分词表 + Doris/SelectDB 补丁。

    ``dialect=None`` 时等同官方 0.6.0 的分词行为。
    """

    def __init__(self, dialect="doris"):
        super().__init__()
        self.dialect = dialect
        self.default_initialization()

    def default_initialization(self):
        super().default_initialization()
        if self.dialect not in SUPPORTED_DIALECTS:
            return
        # 词表：追加查询（命中即返回），不覆盖官方已有键
        self.add_keywords(policy.KEYWORDS_DORIS)
        # 多词关键字：前插到官方多词关键字区块，避免被通用单词规则抢先
        self._insert_multiword(policy.compiled(policy.MULTIWORD_REGEX))

    def _insert_multiword(self, entries):
        rules = self._SQL_REGEX
        index = self._multiword_anchor(rules)
        rules[index:index] = entries

    @staticmethod
    def _multiword_anchor(rules):
        wanted = set(policy.ANCHOR_PATTERNS)
        for i, (matcher, _) in enumerate(rules):
            if policy.pattern_of(matcher) in wanted:
                return i
        return len(rules) - 8


def build_lexer(dialect="doris"):
    """按方言构造分词器。"""
    return DialectLexer(dialect)
