from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple


def normalize_sql(text: str) -> str:
    return text.replace("\r\n", "\n").strip("\n")


@dataclass(frozen=True)
class SqlCase:
    name: str
    input_sql: str
    expected_sql: str
    note: str
    tags: Tuple[str, ...] = ()
    options: Dict = field(default_factory=dict)


def _read_fixture(filename: str) -> str:
    base_dir = Path(__file__).resolve().parent
    return (base_dir / filename).read_text(encoding="utf-8")


TOPIC_META = {
    "ddl": {"label": "DDL", "tags": ("ddl", "long", "split")},
    "dml": {"label": "DML", "tags": ("dml", "long", "split")},
    "cte": {"label": "CTE", "tags": ("cte", "long", "split")},
    "nested": {"label": "嵌套查询", "tags": ("nested", "long", "split")},
    "case": {"label": "CASE", "tags": ("case", "long", "split")},
    "aggregate": {"label": "聚合", "tags": ("aggregate", "split")},
    "window": {"label": "窗口函数", "tags": ("window", "long", "split")},
    "debug": {"label": "调试", "tags": ("debug", "short", "split")},
    "comma": {"label": "逗号选项", "tags": ("comma", "short", "split")},
    "generic": {"label": "泛型类型", "tags": ("generic", "short", "split")},
    # 方言用例：topic 级 options 让整组跑在指定方言上（`_build_case` 支持 topic 级 options）
    "dialect": {"label": "方言", "tags": ("dialect", "short", "split"), "options": {"dialect": "doris"}},
    "sqlserver": {"label": "方言（SQL Server）", "tags": ("sqlserver", "short", "split"), "options": {"dialect": "sqlserver"}},
}


def _discover_case_files() -> List[Path]:
    base_dir = Path(__file__).resolve().parent / "cases"
    # 收集所有 .sql 文件，排除 .input.sql（它们配对到同名 .sql）
    files = [p for p in base_dir.glob("*/*.sql") if p.is_file() and not p.name.endswith(".input.sql")]
    return sorted(files, key=lambda p: p.as_posix())


# 文件名后缀 → 额外选项覆盖（用于同 topic 下不同选项的用例）
FILE_OPTIONS = {
    "sqltest7_s01": {"align_list": False},
    "sqltest7_s02": {"comma_first": True},
}


def _build_case(case_file: Path) -> SqlCase:
    topic = case_file.parent.name
    rel_path = case_file.relative_to(Path(__file__).resolve().parent / "cases").as_posix()
    case_name = rel_path.replace(".sql", "")

    meta = TOPIC_META.get(topic, {"label": topic.upper(), "tags": (topic, "split")})
    note = f"{meta['label']} 用例：{case_file.stem}"

    # 如果存在 {name}.input.sql，用它作为 input；否则 .sql 即 input 也是 expected
    input_file = case_file.with_name(case_file.stem + ".input.sql")
    if input_file.exists():
        input_sql = normalize_sql(_read_fixture(f"cases/{topic}/{input_file.name}"))
        expected_sql = normalize_sql(_read_fixture(f"cases/{rel_path}"))
    else:
        sql_text = normalize_sql(_read_fixture(f"cases/{rel_path}"))
        input_sql = sql_text
        expected_sql = sql_text

    options = {**meta.get("options", {}), **FILE_OPTIONS.get(case_file.stem, {})}

    return SqlCase(
        name=case_name,
        input_sql=input_sql,
        expected_sql=expected_sql,
        note=note,
        tags=meta["tags"],
        options=options,
    )


SQL_CASES: List[SqlCase] = [_build_case(p) for p in _discover_case_files()]
