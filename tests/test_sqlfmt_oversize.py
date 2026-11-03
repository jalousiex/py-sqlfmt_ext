"""超长语句（越过官方 ``MAX_GROUPING_TOKENS``）的分组放行与优雅降级。

覆盖两类真因：

1. **> 10000 token 的单条语句**：官方 ``_group`` 会抛
   ``SQLParseError: Maximum number of tokens exceeded``。分组层按语句临时抬高闸门，
   格式化必须照常成功，且幂等、语句条数/分隔符不变。
2. **异常路径**：超过自设安全上限（或任何 ``SQLParseError``）时，库层逐条降级为
   「原样保留 + WARN（含语句序号与 token 规模）」，CLI 不抛 traceback、不改文件。

真实用例都**真的越过** 10000 token；降级用例把官方闸门调小，走同一条代码路径，
避免把门禁拖到分钟级。
"""

import logging

import pytest
from sqlparse.engine import grouping as official
from sqlparse.exceptions import SQLParseError

from sqlfmt_ext import cli
from sqlfmt_ext import grouping as grouping_module
from sqlfmt_ext import format_statements
from sqlfmt_ext.lexer import build_lexer

_TOKEN = build_lexer(None).get_tokens


@pytest.fixture(autouse=True)
def _restore_package_logger():
    """CLI 会把 ``sqlfmt_ext`` logger 的 propagate 关掉并挂 handler，测完还原，避免串味。"""
    logger = logging.getLogger("sqlfmt_ext")
    propagate = logger.propagate
    handlers = list(logger.handlers)
    try:
        yield
    finally:
        logger.propagate = propagate
        for handler in logger.handlers:
            if handler not in handlers:
                logger.removeHandler(handler)
        for handler in handlers:
            if handler not in logger.handlers:
                logger.addHandler(handler)


def _token_count(sql):
    return sum(1 for _ in _TOKEN(sql))


def _wide_columns(count):
    return "select " + ", ".join(f"c{i}" for i in range(count)) + " from t;"


def _union_branches(count):
    branch = "select {} as a, {} as b from t"
    return " union all ".join(branch.format(i, i) for i in range(count)) + ";"


def test_wide_column_list_beyond_token_limit():
    sql = _wide_columns(3400)
    assert _token_count(sql) > 10_000  # 真因：单条语句越过官方闸门

    out = format_statements(sql)

    assert out.count(",") == 3399
    assert "c0" in out and "c3399" in out
    assert out.count(";") == 1
    assert format_statements(out) == out  # 幂等


def test_union_all_beyond_token_limit():
    sql = _union_branches(520)
    assert _token_count(sql) > 10_000

    out = format_statements(sql)

    assert out.count("union all") == 519
    assert out.count(";") == 1
    assert format_statements(out) == out  # 幂等


def test_parse_error_keeps_original_statement_and_warns(monkeypatch, caplog):
    # 把闸门与安全上限都调小：第二条语句越过上限 → 走「原样保留 + WARN」。
    monkeypatch.setattr(official, "MAX_GROUPING_TOKENS", 10)
    monkeypatch.setattr(grouping_module, "_ABSOLUTE_TOKEN_CEILING", 20)
    sql = "select a from t;\nselect " + ", ".join(f"c{i}" for i in range(10)) + " from t;"

    with caplog.at_level(logging.WARNING):
        out = format_statements(sql)

    assert out.split("\n\n")[-1] == sql.split(";\n", 1)[1].strip()
    assert "第 2 条语句" in caplog.text
    assert "token" in caplog.text


def test_cli_keeps_file_and_does_not_traceback(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(official, "MAX_GROUPING_TOKENS", 10)
    monkeypatch.setattr(grouping_module, "_ABSOLUTE_TOKEN_CEILING", 20)
    sql = "select " + ", ".join(f"c{i}" for i in range(10)) + " from t;\n"
    path = tmp_path / "oversize.sql"
    path.write_text(sql, encoding="utf-8")

    assert cli.main([str(path), "--in-place"]) == 0

    captured = capsys.readouterr()
    assert "第 1 条语句" in captured.err and "token" in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""
    # 逐条降级只做 strip（入口既有口径），不截断、不留半格式化的语句
    assert path.read_text(encoding="utf-8").strip() == sql.strip()


def test_cli_reports_file_level_failure_without_traceback(tmp_path, monkeypatch, capsys):
    def boom(*_args, **_kwargs):
        raise SQLParseError("模拟的分组失败")

    monkeypatch.setattr(cli, "format_statements", boom)
    sql = "select a from t;\n"
    path = tmp_path / "broken.sql"
    path.write_text(sql, encoding="utf-8")

    assert cli.main([str(path), "--in-place"]) == 1

    captured = capsys.readouterr()
    assert "格式化失败" in captured.err and "Traceback" not in captured.err
    assert path.read_text(encoding="utf-8") == sql


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
