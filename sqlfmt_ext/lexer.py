"""方言分词：在官方 ``Lexer`` 之上追加本项目的分词补丁。

做法是**子类化 + 初始化后追加**，不动官方模块的全局单例，也不改写官方已有条目；
因此官方升级分词表后，本项目自动继承，只有补丁条目需要维护。

「要不要打补丁」由 ``dialects`` 声明（本项目的单一真身）—— 本模块不再自己维护方言
白名单（2026-09-13 起，见 `.claude/plan/stages.md` §9.9）。
"""

from sqlparse.lexer import Lexer

from . import dialects, policy


class DialectLexer(Lexer):
    """官方分词表 + 方言补丁。

    ``dialect=None`` 时等同官方 0.6.0 的分词行为。
    """

    def __init__(self, dialect="doris"):
        super().__init__()
        self.dialect = dialect
        self.default_initialization()

    def default_initialization(self):
        super().default_initialization()
        dialect = dialects.get_dialect(self.dialect)
        # 词表：方言关键字 + 类型名（追加查询，不覆盖官方已有键）
        self.add_keywords(dict(dialect.extra_keywords))
        # 字符串转义补丁（U17）：**无条件**打，与方言无关。官方字符串正则不认
        # 「反斜杠 + 反斜杠」，含它的字符串字面量不闭合并吞掉后续整段 SQL
        # （见 `policy.STRING_ESCAPE_REGEX` 的注释）。
        # 锚点找不到时退回 index 0 —— 官方词表里**没有**任何更靠前的规则能吃掉一个
        # 引号（注释 / 空白 / 关键字 / 数字都不匹配 `'`），所以提前匹配是安全的。
        self._insert_rules(policy.compiled(policy.STRING_ESCAPE_REGEX), policy.STRING_ANCHORS, 0)
        if dialect.multiword_patches:
            # 多词关键字：前插到官方多词关键字区块，避免被通用单词规则抢先
            self._insert_rules(policy.compiled(policy.MULTIWORD_REGEX), policy.ANCHOR_PATTERNS, len(self._SQL_REGEX) - 8)
        if dialect.precedence_patches:
            # 优先级补丁：必须早于官方「函数名」正则，否则 over( 会被判成 Name
            self._insert_rules(policy.compiled(policy.PRECEDENCE_REGEX), policy.PRECEDENCE_ANCHORS, 0)
        if dialect.extra_lexer_rules:
            # 方言自己的优先级规则：同样要压过官方「函数名」正则
            self._insert_rules(policy.compiled(dialect.extra_lexer_rules), policy.PRECEDENCE_ANCHORS, 0)

    def _insert_rules(self, entries, anchors, fallback):
        rules = self._SQL_REGEX
        index = self._anchor_index(rules, anchors)
        index = fallback if index is None else index
        rules[index:index] = entries

    @staticmethod
    def _anchor_index(rules, anchors):
        wanted = set(anchors)
        for i, (matcher, _) in enumerate(rules):
            if policy.pattern_of(matcher) in wanted:
                return i
        return None


def build_lexer(dialect="doris"):
    """按方言构造分词器。"""
    return DialectLexer(dialect)
