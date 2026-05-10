from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple


def normalize_sql(text: str) -> str:
    return text.replace("\r\n", "\n").strip("\n")


@dataclass(frozen=True)
class SqlCase:
    name: str
    input_sql: str
    expected_sql: str
    note: str
    tags: Tuple[str, ...] = ()


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
}


def _discover_case_files() -> List[Path]:
    base_dir = Path(__file__).resolve().parent / "cases"
    files = [p for p in base_dir.glob("*/*.sql") if p.is_file()]
    return sorted(files, key=lambda p: p.as_posix())


def _build_case(case_file: Path) -> SqlCase:
    topic = case_file.parent.name
    rel_path = case_file.relative_to(Path(__file__).resolve().parent / "cases").as_posix()
    case_name = rel_path.replace(".sql", "")

    meta = TOPIC_META.get(topic, {"label": topic.upper(), "tags": (topic, "split")})
    note = f"{meta['label']} 用例：{case_file.stem}"
    sql_text = normalize_sql(_read_fixture(f"cases/{rel_path}"))

    return SqlCase(
        name=case_name,
        input_sql=sql_text,
        expected_sql=sql_text,
        note=note,
        tags=meta["tags"],
    )


SQL_CASES: List[SqlCase] = [_build_case(p) for p in _discover_case_files()]
