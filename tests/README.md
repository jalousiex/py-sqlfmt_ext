# 自动化测试

本测试套件由 `tests/fixtures/sql_cases.py` 中的标准化用例驱动。
不依赖 `.test.py`。
格式化校验使用 `sqlfmt.py` 入口函数的默认行为。
测试点以独立 SQL 文件维护在 `tests/fixtures/cases/` 目录中，并按主题子目录分层。

## 运行测试

```bash
python -m unittest discover -s tests -p "test_*.py"
```

当前 unittest 结构拆分为三类检查：
1. 用例完整性：结构、唯一性、字段非空。
2. 输出回归：格式化输出与期望 SQL 一致。
3. 幂等性：第二次格式化结果不再变化。

用例命名规则：
1. `主题目录/sqltestX_sNN.sql`：细粒度语句级测试点文件。
2. `debug/sqldebug_s01.sql`：最小调试样例文件。

测试文件拆分如下：
1. `tests/test_sqlfmt_case_integrity.py`
2. `tests/test_sqlfmt_output_regression.py`
3. `tests/test_sqlfmt_idempotency.py`

## 按标签运行（可选）

使用环境变量 `SQLFMT_CASE_TAGS` 可只运行部分用例。
多个标签用英文逗号分隔，按 AND 语义匹配（即必须同时满足所有标签）。
如果筛选后没有命中任何用例，完整性测试会报错提示“筛选后无可用 SQL 用例”。

当前内置常用标签：
1. `ddl` `dml` `cte` `case` `nested` `window` `aggregate` `debug`
2. `split` `short` `long`

PowerShell 示例：

```powershell
$env:SQLFMT_CASE_TAGS = "case"
python -m unittest discover -s tests -p "test_*.py"

$env:SQLFMT_CASE_TAGS = "window,long"
python -m unittest discover -s tests -p "test_*.py"

Remove-Item Env:SQLFMT_CASE_TAGS
```

## 新增或维护用例

1. 将细粒度 SQL 用例文件放在 `tests/fixtures/cases/<topic>/*.sql`。
2. 用例会由 `tests/fixtures/sql_cases.py` 自动扫描加载，无需手工注册。
3. 对单文件用例，建议 `input_sql` 与 `expected_sql` 保持一致；
   这是约定建议，不是强制断言。
