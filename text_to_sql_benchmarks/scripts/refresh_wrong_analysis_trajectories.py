#!/usr/bin/env python3
"""Refresh summarized trajectory tables in Arcwise wrong-analysis markdown files.

The tables are intentionally interpretive: they summarize each round's action and
the useful signal from the tool result, instead of copying model thoughts.
"""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any


QID_HEADING_RE = re.compile(r"^## qid(\d+)\b.*$", re.M)
LEVEL2_HEADING_RE = re.compile(r"^##\s+", re.M)
SPACE_RE = re.compile(r"\s+")
TABLE_TOKEN_RE = r"(?:`([^`]+)`|\"([^\"]+)\"|\[([^\]]+)\]|([A-Za-z_]\w*))"


def compact(value: Any, limit: int = 120) -> str:
    if value is None:
        return ""
    text = SPACE_RE.sub(" ", str(value).replace("\r", " ").replace("\n", " ")).strip()
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "..."
    return text


def code(value: Any, limit: int = 80) -> str:
    text = compact(value, limit).replace("`", "\\`")
    return f"`{text}`" if text else ""


def md_cell(value: str) -> str:
    escaped = html.escape(str(value), quote=False)
    escaped = escaped.replace("&lt;br&gt;", "<br>")
    return escaped.replace("|", "\\|")


def normalize_sql(sql: str | None) -> str:
    return SPACE_RE.sub(" ", (sql or "").strip()).lower()


def parse_table_name_from_pragma(sql: str) -> str | None:
    match = re.search(r"pragma\s+table_info\s*\(\s*[`\"\[]?([A-Za-z0-9_ ]+)[`\"\]]?\s*\)", sql, re.I)
    return match.group(1).strip() if match else None


def parse_sqlite_master_names(sql: str) -> list[str]:
    names: list[str] = []
    in_match = re.search(r"name\s+in\s*\((.*?)\)", sql, re.I | re.S)
    if in_match:
        names.extend(re.findall(r"['\"]([^'\"]+)['\"]", in_match.group(1)))
    eq_match = re.search(r"name\s*=\s*['\"]([^'\"]+)['\"]", sql, re.I)
    if eq_match:
        names.append(eq_match.group(1))
    return list(dict.fromkeys(names))


def parse_from_tables(sql: str) -> list[str]:
    tables: list[str] = []
    for match in re.finditer(r"\b(?:from|join)\s+" + TABLE_TOKEN_RE, sql, re.I):
        name = next(group for group in match.groups() if group)
        if name and name.lower() not in {"select"}:
            tables.append(name)
    return list(dict.fromkeys(tables))


def parse_create_table(create_sql: str) -> tuple[str | None, list[str]]:
    table_match = re.search(r"create\s+table\s+[`\"\[]?([A-Za-z_][\w ]*)[`\"\]]?", create_sql, re.I)
    table = table_match.group(1).strip() if table_match else None
    cols: list[str] = []
    body_match = re.search(r"\((.*)\)", create_sql, re.S)
    if body_match:
        for raw_line in body_match.group(1).splitlines():
            line = raw_line.strip().rstrip(",")
            if not line:
                continue
            first = line.split()[0].strip("`\"[]")
            if first.lower() in {
                "primary",
                "foreign",
                "unique",
                "constraint",
                "key",
                "references",
                "on",
                "check",
            }:
                continue
            cols.append(first)
    return table, cols


def column_names_from_result(result: dict[str, Any]) -> list[str]:
    cols: list[str] = []
    for row in result.get("rows") or []:
        if isinstance(row, list) and len(row) > 1:
            cols.append(str(row[1]))
    return cols


def sample_values(rows: list[Any], limit: int = 4) -> list[str]:
    values: list[str] = []
    for row in rows[:limit]:
        if isinstance(row, list):
            if len(row) == 1:
                values.append(code(row[0], 50))
            else:
                values.append("(" + ", ".join(code(v, 32) for v in row[:3]) + (", ..." if len(row) > 3 else "") + ")")
        else:
            values.append(code(row, 50))
    return values


def selected_columns(sql: str) -> str:
    match = re.search(r"\bselect\s+(.*?)\s+\bfrom\b", sql, re.I | re.S)
    if not match:
        return ""
    text = compact(match.group(1), 160)
    if text == "*":
        return "所有字段"
    lower = text.lower()
    if len(text) > 70:
        if "/" in text or "round(" in lower or "cast(" in lower:
            return "计算比例/比率"
        if "case when" in lower:
            return "计算条件指标"
        if "count(" in lower:
            return "统计数量"
        if "sum(" in lower:
            return "计算总和/聚合值"
        if "avg(" in lower:
            return "计算平均值"
        if "max(" in lower or "min(" in lower:
            return "计算最大/最小值"
        return "查询多个输出字段"
    return code(text, 120)


def where_clause(sql: str) -> str:
    match = re.search(
        r"\bwhere\s+(.*?)(?:\bgroup\s+by\b|\border\s+by\b|\blimit\b|\boffset\b|;|$)",
        sql,
        re.I | re.S,
    )
    return code(match.group(1), 110) if match else ""


def group_order_limit(sql: str) -> list[str]:
    bits: list[str] = []
    group = re.search(r"\bgroup\s+by\s+(.*?)(?:\border\s+by\b|\blimit\b|;|$)", sql, re.I | re.S)
    order = re.search(r"\border\s+by\s+(.*?)(?:\blimit\b|;|$)", sql, re.I | re.S)
    limit = re.search(r"\blimit\s+(\d+)(?:\s+offset\s+(\d+))?", sql, re.I)
    if group:
        group_text = compact(group.group(1), 160)
        bits.append("分组 " + ("复杂分组字段" if len(group_text) > 70 else code(group_text, 70)))
    if order:
        order_text = compact(order.group(1), 160)
        if len(order_text) > 70 or ("/" in order_text and len(order_text) > 45):
            bits.append("按计算指标排序")
        else:
            bits.append("排序 " + code(order_text, 70))
    if limit:
        text = f"取 {limit.group(1)} 行"
        if limit.group(2):
            text += f"，跳过 {limit.group(2)} 行"
        bits.append(text)
    return bits


def summarize_sql_action(sql: str, action: str) -> str:
    sql_clean = compact(sql, 1000)
    lower = sql_clean.lower()

    if "sqlite_master" in lower and "type='table'" in lower and "select name" in lower:
        return "查询所有表"

    if "sqlite_master" in lower and "select sql" in lower:
        names = parse_sqlite_master_names(sql_clean)
        if names:
            return "查看 " + "、".join(code(name) for name in names) + " 的建表 SQL"
        return "查看建表 SQL"

    pragma_table = parse_table_name_from_pragma(sql_clean)
    if pragma_table:
        return "查看 " + code(pragma_table) + " 字段清单"

    non_trailing_semicolons = [m.start() for m in re.finditer(";", sql_clean.rstrip(";"))]
    if non_trailing_semicolons:
        return "一次提交多条 SQL 语句"

    if lower.startswith("with "):
        tables = parse_from_tables(sql_clean)
        bits = ["生成 CTE/WITH 候选 SQL"]
        if tables:
            bits.append("涉及 " + "、".join(code(table) for table in tables[:5]))
        if "row_number() over" in lower:
            bits.append("使用窗口排序")
        if any(fn in lower for fn in ("count(", "sum(", "avg(", "max(", "min(")):
            bits.append("包含聚合计算")
        return "；".join(bits)

    if "row_number() over" in lower:
        tables = parse_from_tables(sql_clean)
        bits = ["生成窗口排名候选 SQL"]
        if tables:
            bits.append("涉及 " + "、".join(code(table) for table in tables[:5]))
        if any(fn in lower for fn in ("count(", "sum(", "avg(", "max(", "min(")):
            bits.append("包含聚合计算")
        return "；".join(bits)

    star_limit = re.search(r"\bselect\s+\*\s+from\s+" + TABLE_TOKEN_RE + r".*?\blimit\s+(\d+)", sql_clean, re.I)
    if star_limit:
        table = next(group for group in star_limit.groups()[:-1] if group)
        limit = star_limit.groups()[-1]
        return "查看 " + code(table) + f" 前 {limit} 行样例"

    distinct = re.search(r"\bselect\s+distinct\s+(.+?)\s+\bfrom\s+" + TABLE_TOKEN_RE, sql_clean, re.I | re.S)
    if distinct:
        col = compact(distinct.group(1), 80)
        table = next(group for group in distinct.groups()[1:] if group)
        where = where_clause(sql_clean)
        if where:
            return f"查 {code(table)} 中 {code(col)} 的匹配取值"
        return f"查 {code(table)} 中 {code(col)} 的不同取值"

    tables = parse_from_tables(sql_clean)
    select = selected_columns(sql_clean)
    where = where_clause(sql_clean)
    details: list[str] = []
    if tables:
        details.append("用 " + "、".join(code(table) for table in tables))
    if select:
        details.append("查询 " + select)
    if where:
        details.append("过滤 " + where)
    details.extend(group_order_limit(sql_clean))

    prefix = "生成候选 SQL" if action == "generate_sql" else "执行 SQL"
    if action == "confirm_answer":
        prefix = "确认最终 SQL"
    if details:
        return prefix + "：" + "；".join(details)
    return prefix + "：" + code(sql_clean, 160)


def summarize_schema_action(schema: Any) -> str:
    if not isinstance(schema, dict):
        return "提出候选 schema"
    parts: list[str] = []
    for table in schema.get("tables", [])[:8]:
        if not isinstance(table, dict) or not table.get("name"):
            continue
        cols: list[str] = []
        for col in table.get("columns") or []:
            if isinstance(col, dict) and col.get("name"):
                cols.append(str(col["name"]))
            elif isinstance(col, str):
                cols.append(col)
        if cols:
            parts.append(f"{code(table['name'])}({', '.join(code(c, 40) for c in cols[:4])}{', ...' if len(cols) > 4 else ''})")
        else:
            parts.append(code(table["name"]))
    if parts:
        return "提出使用 " + "、".join(parts)
    return "提出候选 schema"


def final_diff(item: dict[str, Any]) -> str:
    pred = item.get("pred_result") or {}
    gold = item.get("gold_result") or {}
    if not pred.get("ok", True):
        return "最终 pred 执行错误：" + code(pred.get("error"), 100)
    if not gold.get("ok", True):
        return "gold 执行异常：" + code(gold.get("error"), 100)
    pred_cols = pred.get("columns") or []
    gold_cols = gold.get("columns") or []
    pred_rows = pred.get("row_count")
    gold_rows = gold.get("row_count")
    issues: list[str] = []
    if pred_rows != gold_rows:
        issues.append(f"行数 pred={pred_rows}、gold={gold_rows}")
    if len(pred_cols) != len(gold_cols):
        issues.append(f"列数 pred={len(pred_cols)}、gold={len(gold_cols)}")
    if not issues:
        issues.append("行数/列数相同但值不一致")
    return "最终 EX 失败：" + "；".join(issues)


def summarize_result(message: dict[str, Any], item: dict[str, Any]) -> str:
    assistant = message.get("assistant") or {}
    action = assistant.get("action") or ""
    result = message.get("tool_result")
    tool_call = assistant.get("tool_call") or {}
    sql = ((tool_call.get("arguments") or {}).get("sql") if isinstance(tool_call, dict) else None) or ""
    is_final_sql = normalize_sql(sql) and normalize_sql(sql) == normalize_sql(item.get("pred_sql"))

    if not result:
        if action == "propose_schema":
            schema = assistant.get("schema")
            if schema:
                return "形成候选 schema；关键是后续 SQL 是否沿用这些表和 join 关系。"
            return "没有工具执行；只是阶段切换。"
        if action == "confirm_answer":
            return "确认了最终 SQL；" + final_diff(item)
        return "没有工具执行。"

    if not isinstance(result, dict):
        return "工具返回：" + compact(result, 160)

    if not result.get("ok", False):
        text = "执行报错：" + code(result.get("error") or result.get("message"), 120)
        if is_final_sql:
            text += "；这是最终失败点。"
        return text

    rows = result.get("rows") or []
    columns = result.get("columns") or []
    lower = sql.lower()

    if "sqlite_master" in lower and "select name" in lower:
        names = [str(row[0]) for row in rows if isinstance(row, list) and row]
        shown = "、".join(code(name) for name in names[:5])
        return f"找到 {shown}{' 等' if len(names) > 5 else ''}，共 {len(names)} 张表。"

    if "sqlite_master" in lower and "select sql" in lower:
        summaries: list[str] = []
        for row in rows[:3]:
            if not isinstance(row, list) or not row:
                continue
            table, cols = parse_create_table(str(row[0]))
            if table:
                summaries.append(f"{code(table)} 有 {len(cols)} 个字段" + (f"，如 {', '.join(code(c, 32) for c in cols[:4])}" if cols else ""))
        return "已拿到结构：" + "；".join(summaries) + "。" if summaries else "已拿到建表 SQL。"

    pragma_table = parse_table_name_from_pragma(sql)
    if pragma_table:
        cols = column_names_from_result(result)
        shown = "、".join(code(c, 32) for c in cols[:6])
        return f"确认 {code(pragma_table)} 有 {len(cols)} 个字段" + (f"，包括 {shown}{' 等' if len(cols) > 6 else ''}。" if cols else "。")

    if not rows:
        text = "返回空结果"
        gold_rows = (item.get("gold_result") or {}).get("row_count")
        if action in {"generate_sql", "confirm_answer"} and gold_rows:
            text += f"；但 gold 有 {gold_rows} 行，说明过滤字段、join 或取值可能错"
        elif "distinct" in lower or "like" in lower:
            text += "；这是字段/取值可能不匹配的信号"
        return text + "。"

    star_limit = re.search(r"\bselect\s+\*\s+from\s+" + TABLE_TOKEN_RE + r".*?\blimit\s+(\d+)", sql, re.I)
    if star_limit:
        bits = [f"看到 {len(rows)} 行样例"]
        if columns:
            display_cols = []
            for name in columns:
                lower_name = str(name).lower()
                if "displayname" in lower_name or lower_name in {"owneruserid", "userid", "id"}:
                    idx = columns.index(name)
                    non_null = sum(1 for row in rows if isinstance(row, list) and idx < len(row) and row[idx] is not None)
                    display_cols.append(f"{code(name)} 非空 {non_null}/{len(rows)}")
            if display_cols:
                bits.append("；".join(display_cols))
            else:
                bits.append("关键字段包括 " + "、".join(code(c, 32) for c in columns[:5]))
        return "；".join(bits) + "。"

    values = sample_values(rows)
    base = f"返回 {len(rows)} 行"
    if result.get("truncated"):
        base += "预览"
    if values:
        base += "：" + "、".join(values)

    if action in {"generate_sql", "confirm_answer"} or is_final_sql:
        return base + "；" + final_diff(item) + "。"
    return base + "。"


def build_table(item: dict[str, Any]) -> str:
    lines = [
        "### 运行轨迹",
        "",
        "| 轮次 | 阶段 | 做了什么 | 结果/问题 |",
        "| --- | --- | --- | --- |",
    ]
    for message in item.get("conversation") or []:
        assistant = message.get("assistant") or {}
        action = assistant.get("action") or "null"
        tool_call = assistant.get("tool_call") or {}
        sql = ((tool_call.get("arguments") or {}).get("sql") if isinstance(tool_call, dict) else None) or ""
        if sql:
            what = summarize_sql_action(sql, action)
        elif assistant.get("schema"):
            what = summarize_schema_action(assistant.get("schema"))
        elif assistant.get("answer_sql"):
            what = summarize_sql_action(assistant.get("answer_sql"), "confirm_answer")
        else:
            what = "未解析出结构化动作"
        problem = summarize_result(message, item)
        lines.append(
            f"| Round {message.get('round', '-')} | {md_cell(action)} | {md_cell(what)} | {md_cell(problem)} |"
        )
    return "\n".join(lines)


def replace_section(section: str, item: dict[str, Any]) -> str:
    marker = "\n### 运行轨迹\n"
    if marker in section:
        section = section[: section.index(marker)].rstrip() + "\n"
    else:
        section = section.rstrip() + "\n"
    return section + "\n" + build_table(item).rstrip() + "\n"


def refresh(result_dir: Path) -> tuple[list[str], list[str]]:
    details_path = result_dir / "wrong_details.pretty.json"
    items = json.loads(details_path.read_text(encoding="utf-8"))
    by_qid = {str(item["question_id"]): item for item in items}
    updated: list[str] = []
    covered: set[str] = set()

    for path in sorted(result_dir.glob("*wrong_analysis.md")):
        text = path.read_text(encoding="utf-8")
        matches = list(QID_HEADING_RE.finditer(text))
        if not matches:
            continue
        pieces: list[str] = []
        last = 0
        changed = False
        for idx, match in enumerate(matches):
            qid = match.group(1)
            section_start = match.start()
            section_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            if idx + 1 == len(matches):
                next_h = LEVEL2_HEADING_RE.search(text, match.end())
                if next_h:
                    section_end = next_h.start()
            pieces.append(text[last:section_start])
            section = text[section_start:section_end]
            item = by_qid.get(qid)
            if item:
                new_section = replace_section(section, item)
                covered.add(qid)
            else:
                new_section = section
            changed = changed or new_section != section
            pieces.append(new_section)
            last = section_end
        pieces.append(text[last:])
        new_text = "".join(pieces)
        if changed and new_text != text:
            path.write_text(new_text, encoding="utf-8")
            updated.append(path.name)

    missing = sorted(set(by_qid) - covered, key=lambda x: int(x))
    return updated, missing


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--result-dir",
        type=Path,
        default=Path("results/qwen35-4b-arcwise-plat-trustsql-full-final-thinking"),
    )
    args = parser.parse_args()
    updated, missing = refresh(args.result_dir)
    print(f"updated files: {len(updated)}")
    for name in updated:
        print(f"- {name}")
    print(f"missing qids without markdown section: {len(missing)}")
    if missing:
        print(", ".join(missing))


if __name__ == "__main__":
    main()
