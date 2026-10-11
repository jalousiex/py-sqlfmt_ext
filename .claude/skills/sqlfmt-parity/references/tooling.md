# 诊断工具与坑位

**诊断脚本一律现场写、用完即删**（仓库根 `_tmp_*.py`，`.gitignore` 的 `_tmp_*` 已覆盖）。
迁移期的固定探针在 S7 随旧 fork 一起删除，且其中的 `--fork` 侧已无处可跑 → **照下面的模板现写**。
**不要往源码里塞 `print`**；真塞了必须当轮删掉。

> 关键前提：`FilterStack.run(sql)` 返回**生成器**，不消费等于没跑 → 用 `list(stack.run(sql))`，
> 或者直接在 `LayoutPass.process` 上 patch 后再调 `format_statements`。

## 探针模板（按要看的东西选）

| 要看什么 | 怎么写 |
|---|---|
| 语句层 token（类型 / 值 / 空白） | patch `sqlfmt_ext.stack.LayoutPass.process`，打 `type(tk).__name__` / `repr(tk.value)` / `tk.ttype` |
| **语句层兄弟序列**（查「列表被切成几张表」） | 同上，但把空白折叠成 `ws(n)` —— 看形态问题最快 |
| token 树（分组形状） | `sqlparse.parse(sql)[0]` → `sqlfmt_ext.grouping.group(stmt)` → 递归打 `type(...)` / `value` / `ttype` |
| 该不该换行 | 语句层每个 token 对 `LayoutPass.split_words` 的命中（`tk.match(T.Keyword, words, regex=True)`） |
| 列对齐中间量 | patch `AlignMixin._identifier_layouts`：打 `max_as_offset` / `max_alias_len` / 每项 `as_offset` |
| DDL 字段列 | patch `AlignMixin._create_field_lines`：打 `field_lines` / 每列 `max_offset` / 每 token 的 offset |
| 空白改动前后 | patch `LayoutPass.process`，before / after 各打一遍语句层序列 |
| 收敛性 | 用 `tests/fixtures/whitespace.py::flatten_whitespace` 压平输入再比 —— **这才是门禁口径**（随机打乱只作参考） |

**探针必须打真实 fixture**（`@tests/fixtures/cases/...`，自己写个 `@相对路径` 的读法），
别拿抽出来的一行 SQL 下结论（元规则三）。

## 坑位（每条都真踩过）

1. **`FilterStack.run(sql)` 返回生成器**。不消费等于没跑 —— 自建探针必须 `list(stack.run(sql))`；
   曾因此误判「探针没触发 = 现象不存在」。
2. 官方 `Lexer.get_tokens()` 产出 `(ttype, value)` **元组**，不是 Token 对象。
3. **比对不能只比「非空白 token 序列」**（格式化不重排 token，恒等）。要比**行内容**才能分离换行位置
   差异；统计行内容差异时先把「标点前对齐空格」归一化（`a ,` vs `a,`），否则整批用例会被误判为骨架差异。
4. **「关掉它做对照」是验证元凶的硬手段**：把可疑改动换成 no-op（或提前 `return`）再跑一次，现象若不变
   说明找错了地方（元规则六）。两次输出用 `Compare-Object` 对比。
5. **临时探针用运行时 patch 写进 `_tmp_*.py`**，用完即删。
6. **探针一次把「要看的两侧 / 多种模式」+ `@相对路径` 补齐**，少了就得来回跑好几轮。
7. **首个差异常是假象**：差异簇里第一条可见差异未必是根因（可能只是列宽被抬高后的连带平移）。
   先用「是否只是空白宽度」做粗分类，再决定查分组还是查对齐。
8. **行数错位时 `diff` 的行配对会整体平移**，计数会误报 → 目视复核比计数可靠。

## 官方代码对照

官方 sqlparse 0.6.0 在 `C:\_Dev\python\venv-vsc\Lib\site-packages\sqlparse`（工作区 `.venv` 内亦有一份）。

跑官方版**避免本地包遮蔽**：

```powershell
cd C:\_Dev; $env:PYTHONPATH="C:\_Dev\python\venv-vsc\Lib\site-packages"; python -c "exec(open(r'<脚本绝对路径>', encoding='utf-8').read())"
```

必须用 `-c exec(open(...))` 形式，不要直接 `python <脚本路径>`。

（`sqlparse.__version__` 是**过期的 0.5.5**，判版本用 `importlib.metadata.version`。）
