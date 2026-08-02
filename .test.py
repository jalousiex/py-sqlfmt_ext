import argparse
from difflib import unified_diff
from pathlib import Path

from tests.sqlfmt_test_helpers import case_expected, format_with_entry_defaults, selected_cases

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def dump_failed_cases(output_dir="tests/_failed_outputs", only_case=None):
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    failed = 0
    for case in selected_cases():
        if only_case and case.name != only_case:
            continue

        actual = format_with_entry_defaults(case.input_sql)
        expected = case_expected(case)
        if actual == expected:
            continue

        failed += 1
        safe_name = case.name.replace("/", "__")
        (out_dir / f"{safe_name}.input.sql").write_text(case.input_sql, encoding="utf-8")
        (out_dir / f"{safe_name}.expected.sql").write_text(expected, encoding="utf-8")
        (out_dir / f"{safe_name}.actual.sql").write_text(actual, encoding="utf-8")

        diff = "".join(
            unified_diff(
                expected.splitlines(keepends=True),
                actual.splitlines(keepends=True),
                fromfile="expected",
                tofile="actual",
                lineterm="",
            )
        )
        (out_dir / f"{safe_name}.diff.txt").write_text(diff, encoding="utf-8")
        print(f"[FAIL] {case.name}")

    if failed == 0:
        print("[OK] 无失败用例")
    else:
        print(f"[DONE] 失败用例 {failed} 个，已导出到: {out_dir.resolve()}")
    return failed


def dump_all_cases(output_dir="tests/_all_outputs", only_case=None):
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    total = 0
    for case in selected_cases():
        if only_case and case.name != only_case:
            continue

        total += 1
        actual = format_with_entry_defaults(case.input_sql)
        safe_name = case.name.replace("/", "__")
        (out_dir / f"{safe_name}.input.sql").write_text(case.input_sql, encoding="utf-8")
        (out_dir / f"{safe_name}.actual.sql").write_text(actual, encoding="utf-8")

    if total == 0:
        print("[WARN] 没有匹配到任何用例")
    else:
        print(f"[DONE] 已导出 {total} 个用例到: {out_dir.resolve()}")
    return total


def dump_single_case(case_name, output_dir="tests/_case_output"):
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    target = None
    for case in selected_cases():
        if case.name == case_name:
            target = case
            break

    if target is None:
        print(f"[ERROR] 未找到用例: {case_name}")
        return 2

    actual = format_with_entry_defaults(target.input_sql)
    expected = case_expected(target)
    safe_name = target.name.replace("/", "__")

    (out_dir / f"{safe_name}.input.sql").write_text(target.input_sql, encoding="utf-8")
    (out_dir / f"{safe_name}.expected.sql").write_text(expected, encoding="utf-8")
    (out_dir / f"{safe_name}.actual.sql").write_text(actual, encoding="utf-8")

    diff = "".join(
        unified_diff(
            expected.splitlines(keepends=True),
            actual.splitlines(keepends=True),
            fromfile="expected",
            tofile="actual",
            lineterm="",
        )
    )
    (out_dir / f"{safe_name}.diff.txt").write_text(diff, encoding="utf-8")

    if actual == expected:
        print(f"[OK] {target.name} 无差异，结果已导出到: {out_dir.resolve()}")
        return 0

    print(f"[FAIL] {target.name} 存在差异，结果已导出到: {out_dir.resolve()}")
    return 1


def build_parser():
    parser = argparse.ArgumentParser(description="sqlfmt 用例输出工具：导出全部结果、失败结果或指定结果")
    parser.add_argument("-a", "--all", action="store_true", help="导出全部用例格式化结果")
    parser.add_argument("-r", "--failed", action="store_true", help="仅导出失败用例结果")
    parser.add_argument("-c", "--case", dest="case_name", help="仅导出指定用例，例如 dml/sqltest1_s01")
    parser.add_argument("-o", "--outdir", default=None, help="输出目录")
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()

    if args.case_name:
        outdir = args.outdir or str(DEFAULT_OUTPUT_DIR)
        raise SystemExit(dump_single_case(case_name=args.case_name, output_dir=outdir))

    if args.failed:
        outdir = args.outdir or str(DEFAULT_OUTPUT_DIR)
        failed_count = dump_failed_cases(output_dir=outdir)
        raise SystemExit(1 if failed_count else 0)

    if args.all:
        outdir = args.outdir or str(DEFAULT_OUTPUT_DIR)
        exported = dump_all_cases(output_dir=outdir)
        raise SystemExit(0 if exported else 2)

    build_parser().print_help()
    raise SystemExit(2)
