"""同行空白对齐规则（AlignPass 规则集）。

以 mixin 形式组合进 ``LayoutPass``：断行宽度与列对齐互相依赖（例如 CASE 的
THEN 对齐要先知道条件宽度），拆成独立后置 pass 需要重复遍历、重复计算偏移，
因此这里只做「规则集的物理分离」，执行时机仍紧跟断行。

所有方法只改写同行 ``Whitespace`` token 的宽度，不动 ttype / 顺序 / 非空白 token。
"""

from sqlparse import sql
from sqlparse import tokens as T


class AlignMixin:
    def _set_adjacent_ws(self, container, ref, width, after=False):
        """将 ref 一侧的同行空白替换为固定宽度，而非叠加。"""
        idx = container.token_index(ref)
        adjacent = container.token_next if after else container.token_prev
        ws_idx, ws = adjacent(idx, skip_ws=False)
        if ws and ws.is_whitespace and self.n not in ws.value:
            if width > 0:
                ws.value = self.char * width
            else:
                del container.tokens[ws_idx]
        elif width > 0:
            inserter = container.insert_after if after else container.insert_before
            inserter(ref, sql.Token(T.Whitespace, self.char * width))

    def _identifier_layout(self, token):
        """解析列表项的 AS/别名位置，并折叠 AS 两侧的非必要换行。"""
        alias = as_tk = None
        if token.is_group and not hasattr(token, "M_OPEN"):
            nidx, _ = token.token_next(idx=-1, skip_cm=True)
            # 官方 token_next 在整项只有注释/空白时返回 None，此处需跳过而非往下传
            if nidx is not None:
                _, alias = token.token_next_by(idx=nidx, i=sql.Identifier)
            _, as_tk = token.token_next_by(m=(T.Keyword, "AS"))
            if as_tk and alias is None:
                _, next_tk = token.token_next(token.token_index(as_tk), skip_cm=True)
                if next_tk is not None and next_tk.ttype is T.Keyword:
                    alias = next_tk
            if as_tk:
                self._pull_inline(token, as_tk, after=False)
                self._pull_inline(token, as_tk, after=True)

        if as_tk:
            as_offset = self._get_offset(as_tk)
        elif alias:
            as_offset = self._get_offset(alias)
        else:
            as_offset = self._get_offset(token) + 1 + len(str(token).splitlines()[-1].encode("gbk"))
        return as_offset, as_tk, len(str(alias).encode("gbk")), alias

    def _identifier_layouts(self, tlist):
        """解析列表布局并汇总 AS、别名列的目标宽度。"""
        layouts = []
        as_placehold = 0
        max_as_offset = 0
        max_alias_len = 0
        for token in tlist:
            layout = self._identifier_layout(token)
            as_offset, as_tk, alias_len, alias = layout
            if as_tk:
                as_placehold = 3
            max_as_offset = min(120, max(max_as_offset, as_offset))
            max_alias_len = max(max_alias_len, alias_len if alias else 0)
            layouts.append(layout)
        return layouts, as_placehold, max_as_offset, max_alias_len

    def _apply_identifier_layout(self, token, layout, max_as_offset, max_alias_len, as_placehold, is_last):
        """按已汇总的列宽设置单个列表项的 AS、别名和逗号前空白。"""
        as_offset, as_tk, alias_len, alias = layout
        as_ws = max_as_offset - as_offset
        trailing_extra = 0
        if as_tk:
            self._set_adjacent_ws(token, as_tk, max(1, 1 + as_ws))
        else:
            as_ws += as_placehold
            if alias:
                self._set_adjacent_ws(token, alias, max(1, 1 + as_ws))
            else:
                trailing_extra = max(0, as_ws)

        if not self.comma_first and max_alias_len:
            alias_ws = max_alias_len + (-alias_len if alias else 1)
            if as_offset > max_as_offset:
                alias_ws = max(0, alias_ws - (as_offset - max_as_offset))
            if is_last:
                alias_ws += 1
            alias_ws += trailing_extra
        else:
            alias_ws = trailing_extra

        if not alias_ws:
            return
        if token.is_group:
            self._set_adjacent_ws(token, token[-1], alias_ws, after=True)
        else:
            self._set_adjacent_ws(token.parent, token, alias_ws, after=True)

    def _align_identifierlist(self, tlist):
        """字段列表对齐，逗号对齐"""
        layouts, as_placehold, max_as_offset, max_alias_len = self._identifier_layouts(tlist)
        for token, layout in zip(tlist, layouts):
            self._apply_identifier_layout(
                token,
                layout,
                max_as_offset,
                max_alias_len,
                as_placehold,
                token == tlist[-1],
            )

    @staticmethod
    def _angle_delta(token):
        """泛型尖括号 token 对嵌套深度的贡献（``<`` +1 / ``>`` -1 / ``>>`` -2）。

        只认**全字符同号**的 token：``<=`` / ``>=`` / ``<>`` 这些比较运算符混了其它字符
        → 返回 0，不会被误当尖括号。
        """
        if token.ttype not in T.Operator:
            return 0
        value = token.value
        if value and set(value) == {"<"}:
            return len(value)
        if value and set(value) == {">"}:
            return -len(value)
        return 0

    def _next_field_comma(self, tlist, idx):
        """下一个**不在泛型尖括号内**的逗号（`idx` 之后查找）。

        ``map<string, int>`` / ``struct<a:int, b:string>`` 里的逗号是**类型实参**的分隔符，
        不是 DDL 字段分隔符 —— 按它切段会把一个字段拆成两行（列也随之错位）。
        返回 ``(index, token)``；找不到返回 ``(None, None)``（与 ``token_next_by`` 一致）。
        """
        depth = 0
        while True:
            idx, token = tlist.token_next(idx, skip_ws=False)
            if token is None:
                return None, None
            depth += self._angle_delta(token)
            if depth == 0 and token.match(T.Punctuation, ","):
                return idx, token

    def _create_field_lines(self, tlist):
        """收集 DDL/INSERT 字段定义的名称、类型、约束、默认值、注释和结尾 token。"""
        field_lines = []
        last_field = True
        prev_idx = 0
        end_idx, end_token = self._next_field_comma(tlist, prev_idx)
        while end_idx:
            # 字段内先定位 DEFAULT：**紧跟其后的 `NULL` 是默认值本身**（MySQL 导出的
            # `dept_id int(11) default null`），不能再被约束列取走 —— 取走会让该字段的
            # 约束列落在很右边的 `null` 上，整块字段的对齐基准被抬高（列序错乱）。
            default_idx, _ = tlist.token_next_by(
                idx=prev_idx, end=end_idx, m=(T.Keyword, ["DEFAULT"])
            )
            constraints_end = default_idx if default_idx is not None else end_idx
            field_line = []
            for token_type, col_end in (
                ({}, end_idx),
                # 类型列：`Name.Builtin` / `Function`，外加方言声明的「官方判成 Keyword
                # 的类型名」（`json` / `double` / `time` / `year`，见 `dialects.Dialect.
                # type_name_keywords`）—— 不声明则字段名与类型粘在一起、该列基准被抬高。
                (
                    {
                        "t": T.Name.Builtin,
                        "i": sql.Function,
                        "m": (T.Keyword, self.type_name_keywords, True),
                    },
                    end_idx,
                ),
                ({"m": (T.Keyword, ["NOT NULL", "NULL", "PRIMARY KEY"])}, constraints_end),
                ({"m": (T.Keyword, ["DEFAULT"])}, end_idx),
                ({"m": (T.Keyword, "COMMENT")}, end_idx),
            ):
                if token_type:
                    idx, token = tlist.token_next_by(idx=prev_idx, end=col_end, **token_type)
                else:
                    idx, token = tlist.token_next(idx=prev_idx, skip_cm=True)
                if idx:
                    prev_idx = idx
                field_line.append(token)

            _, _ = self._remove_prev_newline(tlist, end_idx)
            field_line.append(end_token)
            field_lines.append(field_line)

            prev_idx = end_idx
            end_idx, end_token = self._next_field_comma(tlist, prev_idx)
            if not end_idx and last_field:
                end_idx, end_token = len(tlist.tokens) - 1, tlist.tokens[-1]
                last_field = False
        return field_lines

    def _create_column_target(self, field_lines, index, column):
        """计算一个 DDL 字段列的 token 和目标偏移。"""
        tokens = [next((token for token in line[index:] if token), None) for line in field_lines]
        max_offset = max(
            self._get_offset(token) + (0 if line[index] else 1) for line, token in zip(field_lines, tokens)
        )
        if all(not token for token in column):
            max_offset -= 1
        return tokens, max_offset

    def _align_create_columns(self, tlist):
        """Create Insert 语句中字段定义的对齐处理, 列表首位已对齐

        查找, 对字段名、数据类型、约束条件、默认值、注释分别对齐
        例如:
        CREATE TABLE test (
            id          INTEGER     PRIMARY KEY                           comment '注释',
            name        VARCHAR(50) NOT NULL,
            created_at  TIMESTAMP               DEFAULT CURRENT_TIMESTAMP
        )
        """
        field_lines = self._create_field_lines(tlist)
        for index, column in enumerate(zip(*field_lines)):
            tokens, max_offset = self._create_column_target(field_lines, index, column)
            for tk in tokens:
                offset = self._get_offset(tk)
                ws = max_offset - offset
                if ws > 0:
                    tlist.insert_before(tk, sql.Token(T.Whitespace, self.char * ws))
