"""选项层：在官方 validate_options 之上叠加本项目扩展项。

官方 ``validate_options`` 会忽略不认识的键，因此扩展项可以安全共存：
先补齐默认值 → 校验扩展项 → 交给官方校验（顺带补齐官方默认值）。
"""

from sqlparse.exceptions import SQLParseError
from sqlparse.formatter import validate_options as _validate_official

# 本项目默认格式化参数（与旧实现 sqlfmt.py 的 DEFAULT_OPTIONS 对齐）
DEFAULT_OPTIONS = {
    "keyword_case": "lower",
    "indent_width": 4,
    "reindent_aligned": True,
    "wrap_after": 30,
    "use_space_around_operators": True,
    "align_list": True,
}

# 本项目扩展项 → 默认值（官方不认识的键）
EXTENSION_DEFAULTS = {
    "align_list": True,  # 字段列表 AS/别名列对齐
    "dialect": "doris",  # 本项目的目标方言；None = 完全走官方分词
}

_BOOL_EXTENSIONS = ("align_list",)


def validate_options(options=None):
    """返回补齐默认值后的完整选项字典。"""
    opts = dict(EXTENSION_DEFAULTS)
    opts.update(DEFAULT_OPTIONS)
    opts.update(options or {})

    for key in _BOOL_EXTENSIONS:
        if opts[key] not in (True, False):
            raise SQLParseError(f"{key} requires a boolean value")

    opts = _validate_official(opts)

    # 官方只返回它认识的键所在字典（原地修改），这里确保扩展键仍在
    for key, default in EXTENSION_DEFAULTS.items():
        opts.setdefault(key, default)
    return opts
