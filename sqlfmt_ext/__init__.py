"""sqlfmt_ext：基于官方 sqlparse 的 SQL 格式化外挂层。

设计原则
--------
1. 不修改、不复制 sqlparse 源码；官方包保持 pristine，仅作依赖。
2. 不 monkey-patch 官方函数。需要替换行为的 filter 一律「子类化 + 在官方
   FilterStack 里换装实例」接入。
3. 官方 filter 负责换行骨架，本项目只在官方之后追加「只改空白」的 pass，
   使输出只取决于 token 流（收敛性），与输入空白无关。
4. 方言差异（Doris/SelectDB 优先，官方缺失按 MySQL 兼容适配；后续 SQL Server）
   只用「追加声明」的方式注册，不修改官方分词表。
"""

import sys
from importlib.metadata import distributions as _iter_distributions

try:
    from sqlfmt_ext.options import DEFAULT_OPTIONS, validate_options
    from sqlfmt_ext.stack import build_stack, format_sql, format_statements
except ModuleNotFoundError as _exc:
    # 依赖缺失时给出「缺什么 / 怎么装」，别让调用方对着裸 ModuleNotFoundError 猜。
    # 护栏只能放在包入口（不是 cli.py）：`sqlfmt_ext` 命令与 `python -m sqlfmt_ext.cli`
    # 都会先导入本包，失败发生在入口代码执行之前。
    if (_exc.name or "").split(".")[0] == "sqlparse":
        raise ModuleNotFoundError(
            "缺少依赖：sqlparse（本项目要求 >=0.6,<0.7）\n"
            "  开发环境：在项目根跑 uv sync（工具链统一 uv，本项目不再走 pip）\n"
            "  使用环境：uv tool install <wheel>（装进隔离 tool 环境，不动 py 主解释器）\n"
            f"  当前解释器：{sys.executable}"
        ) from _exc
    raise

__all__ = [
    "DEFAULT_OPTIONS",
    "validate_options",
    "build_stack",
    "format_sql",
    "format_statements",
]

def _installed_version(name="sqlfmt_ext"):
    """已安装元数据里的版本号；找不到（或只有**没有 ``Version`` 字段**的空 ``*.egg-info``）返回 ``None``。

    不走 ``importlib.metadata.version()``：它会命中仓库根那种**空的 ``sqlfmt_ext.egg-info``**
    （构建残留、无 ``PKG-INFO``），拿回 ``None`` 而不是抛 ``PackageNotFoundError``。
    """
    for dist in _iter_distributions():
        meta = dist.metadata
        if meta and (meta["Name"] or "").lower().replace("-", "_") == name and dist.version:
            return dist.version
    return None


# 版本号**不在源码里手写**：唯一真身是 `pyproject.toml`（构建时进 wheel 元数据），这里在运行期
# 从已安装元数据读回来。手写常量必漂 —— `build_package.py <新版本>` 的 `_bump_version` 只改
# `pyproject.toml`，打包不碰本文件（2026-10-24 实测：pyproject 已是 0.1.1，本文件还写 0.1.0）。
# 未安装（直接从源码目录跑）时给可辨认的占位值，不伪装成发布版本。
__version__ = _installed_version() or "0.0.0+source"
