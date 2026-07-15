from __future__ import annotations

import argparse
import json
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx


ALLOWED_SQL_PREFIXES = ("SELECT", "PRAGMA", "EXPLAIN")
SQL_BLOCK_RE = re.compile(r"```(?:sql)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
THINK_RE = re.compile(r"<think>(.*?)</think>", re.IGNORECASE | re.DOTALL)
DEFAULT_MODEL = "/root/autodl-tmp/text_to_sql_benchmarks/models/Qwen3___5-4B"
DEFAULT_BASE_URL = "http://127.0.0.1:8000/v1"


SYSTEM_PROMPT = """# Role
You are an expert SQL assistant working on an unknown SQLite database.
You must never hallucinate tables or columns.
All schema knowledge must come from tool queries.
You must operate strictly through the Action Protocol.

# Action Protocol
Follow this sequence. You may loop back to explore_schema if your schema is incomplete:
1. explore_schema: inspect database metadata.
2. propose_schema: document the verified relevant tables, columns, and joins.
3. generate_sql: generate a candidate SQL query and execute it for validation.
4. confirm_answer: output the final SQL query.

# Actions

## explore_schema
Use this to query database metadata. Prefer:
- SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';
- SELECT sql FROM sqlite_master WHERE type='table' AND name = 'table_name';
- PRAGMA table_info("table_name");
- PRAGMA foreign_key_list("table_name");
Do not solve the user's task in explore_schema.

## propose_schema
Use this to output only schema that you have verified through explore_schema.
Include only relevant tables, columns, and joins.

## generate_sql
Use this to execute a candidate final SQL query based on your proposed schema.
If execution fails or the result shape is clearly wrong, explore or revise before confirming.

## confirm_answer
Use this only after you have generated and checked a candidate SQL query.
Output only the final SQL inside <answer>.

# Output Format
Every assistant response must use exactly one of these formats:

<think>brief reasoning</think>
<action>explore_schema</action>
<tool_call>{"name": "execute_sql_query", "arguments": {"db_id": "DATABASE_ID", "sql": "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"}}</tool_call>

<think>brief reasoning</think>
<action>propose_schema</action>
<schema>{"tables": ["table"], "columns": {"table": ["column"]}, "joins": []}</schema>

<think>brief reasoning</think>
<action>generate_sql</action>
<tool_call>{"name": "execute_sql_query", "arguments": {"db_id": "DATABASE_ID", "sql": "SELECT ...;"}}</tool_call>

<think>brief reasoning</think>
<action>confirm_answer</action>
<answer>```sql
SELECT ...;
```</answer>

# Tool
The only available tool is execute_sql_query. Its JSON arguments are:
{"db_id": "database id", "sql": "SQLite query"}

# Working Memory
When a message titled "Working Memory m_t" is provided, read it before choosing
the next action. Treat it as evidence distilled from prior tool interactions,
not as external domain knowledge. Use its verified facts, joins, value previews,
failed attempts, candidate SQL history, and result-shape notes. Do not repeat
invalid attempts. If a current best candidate SQL exists and still matches the
task, refine or confirm it instead of restarting schema exploration.
"""


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def resolve_path(path: str, base_dir: Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else base_dir / p


def extract_sql(text: str) -> str:
    text = (text or "").strip()
    match = SQL_BLOCK_RE.search(text)
    if match:
        text = match.group(1).strip()
    text = re.sub(r"^\s*(?:SQL\s*:|sqlite\s*:)\s*", "", text, flags=re.IGNORECASE)
    text = text.strip().strip("`").strip()
    if ";" in text:
        text = text.split(";")[0].strip() + ";"
    return text


def build_initial_messages(sample: dict[str, Any]) -> list[dict[str, str]]:
    evidence = (sample.get("evidence") or "").strip()
    evidence_part = f"\n**External Knowledge:** {evidence}" if evidence else ""
    user = f"""**Task Configuration**
**Database Engine:** SQLite
**Database:** {sample["db_id"]}{evidence_part}
**User Question:** {sample["question"]}

Use the action protocol. Do not assume schema names until you verify them with the tool.
"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def strip_sql_comments(sql: str) -> str:
    sql = sql.strip()
    while True:
        if sql.startswith("--"):
            newline = sql.find("\n")
            if newline == -1:
                return ""
            sql = sql[newline + 1 :].strip()
            continue
        if sql.startswith("/*"):
            end = sql.find("*/")
            if end == -1:
                return ""
            sql = sql[end + 2 :].strip()
            continue
        return sql


def is_readonly_sql(sql: str) -> tuple[bool, str | None]:
    cleaned = strip_sql_comments(sql)
    if not cleaned:
        return False, "empty SQL"
    if cleaned.upper().startswith(ALLOWED_SQL_PREFIXES):
        return True, None
    first_word = cleaned.split(maxsplit=1)[0] if cleaned else "EMPTY"
    return False, f"SQL must start with {ALLOWED_SQL_PREFIXES}, got {first_word!r}"


def is_metadata_query(sql: str) -> bool:
    cleaned = strip_sql_comments(sql)
    upper = cleaned.upper()
    if upper.startswith("PRAGMA "):
        return True
    if re.search(r"\bFROM\s+(SQLITE_MASTER|SQLITE_SCHEMA)\b", upper):
        return True
    return False


def normalize_sql_for_memory(sql: str) -> str:
    cleaned = extract_sql(sql or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(";")
    return cleaned.lower()


def summarize_sql(sql: str, max_chars: int = 260) -> str:
    compact = re.sub(r"\s+", " ", (sql or "").strip())
    if len(compact) > max_chars:
        compact = compact[: max_chars - 3] + "..."
    return compact


def parse_pragma_table(sql: str, pragma_name: str) -> str | None:
    pattern = rf"PRAGMA\s+{pragma_name}\s*\(\s*[`\"']?([^`\"')]+)[`\"']?\s*\)"
    match = re.search(pattern, sql or "", re.IGNORECASE)
    return match.group(1).strip() if match else None


def parse_sqlite_master_table_name(sql: str) -> str | None:
    match = re.search(r"\bname\s*=\s*['\"]([^'\"]+)['\"]", sql or "", re.IGNORECASE)
    return match.group(1).strip() if match else None


def parse_distinct_column(sql: str) -> str | None:
    match = re.search(
        r"SELECT\s+DISTINCT\s+(?:[`\"]?(\w[\w\s\-]*)[`\"]?|\w+\.[`\"]?(\w[\w\s\-]*)[`\"]?)\s+FROM\b",
        sql or "",
        re.IGNORECASE,
    )
    if not match:
        return None
    return (match.group(1) or match.group(2) or "").strip()


def is_sample_or_metadata_query(sql: str) -> bool:
    cleaned = strip_sql_comments(sql or "")
    upper = cleaned.upper()
    if is_metadata_query(cleaned):
        return True
    if re.search(r"\bLIMIT\s+(?:1|3|5|10|20)\b", upper) and not re.search(
        r"\b(COUNT|SUM|AVG|MIN|MAX)\s*\(|\bGROUP\s+BY\b|\bORDER\s+BY\b", upper
    ):
        return True
    return False


def preview_rows(rows: list[Any], max_rows: int = 5) -> list[list[Any]]:
    return [[jsonable_cell(value) for value in row] for row in rows[:max_rows]]


def format_result_preview(result: dict[str, Any], max_rows: int = 3) -> str:
    columns = result.get("columns") or []
    rows = result.get("rows") or []
    return json.dumps(
        {"columns": columns, "rows": preview_rows(rows, max_rows), "truncated": result.get("truncated", False)},
        ensure_ascii=False,
    )


@dataclass
class EpisodeMemory:
    max_items: int = 24
    verified_database_facts: list[str] = field(default_factory=list)
    invalid_or_unhelpful_attempts: list[str] = field(default_factory=list)
    failure_reasons: list[str] = field(default_factory=list)
    reusable_conclusions: list[str] = field(default_factory=list)
    current_best_candidate_sql: dict[str, Any] | None = None
    candidate_history: list[dict[str, Any]] = field(default_factory=list)
    seen_sql: dict[str, int] = field(default_factory=dict)

    def add(self, bucket: str, text: str, updates: list[str] | None = None) -> None:
        text = re.sub(r"\s+", " ", (text or "").strip())
        if not text:
            return
        items = getattr(self, bucket)
        if text in items:
            return
        items.append(text)
        if len(items) > self.max_items:
            del items[0 : len(items) - self.max_items]
        if updates is not None:
            updates.append(f"{bucket}: {text}")

    def note_sql_seen(self, sql: str) -> bool:
        key = normalize_sql_for_memory(sql)
        if not key:
            return False
        count = self.seen_sql.get(key, 0)
        self.seen_sql[key] = count + 1
        return count > 0

    def set_best_candidate(self, sql: str, result: dict[str, Any], updates: list[str] | None = None) -> None:
        rows = result.get("rows") or []
        candidate = {
            "sql": summarize_sql(sql, 500),
            "columns": result.get("columns") or [],
            "row_count_preview": len(rows),
            "truncated": result.get("truncated", False),
            "preview": preview_rows(rows, 3),
        }
        previous = self.current_best_candidate_sql
        if previous and normalize_sql_for_memory(str(previous.get("sql", ""))) != normalize_sql_for_memory(sql):
            self.add(
                "reusable_conclusions",
                "A later candidate SQL differs from an earlier successfully executed candidate; compare SQL intent, "
                "columns, row count, and preview before confirming.",
                updates,
            )
            previous_shape = (len(previous.get("columns") or []), previous.get("row_count_preview"))
            current_shape = (len(candidate.get("columns") or []), candidate.get("row_count_preview"))
            if previous_shape != current_shape:
                self.add(
                    "failure_reasons",
                    f"Candidate result shape changed after a successful candidate: {previous_shape} -> {current_shape}. "
                    "Verify this change is required by the question before confirming.",
                    updates,
                )
        self.current_best_candidate_sql = candidate
        self.candidate_history.append(candidate)
        if len(self.candidate_history) > self.max_items:
            del self.candidate_history[0 : len(self.candidate_history) - self.max_items]
        if updates is not None:
            updates.append("current_best_candidate_sql: updated from successful generate_sql")

    def render(self, max_chars: int) -> str:
        sections = [
            ("Verified database facts", self.verified_database_facts),
            ("Invalid or unhelpful attempts", self.invalid_or_unhelpful_attempts),
            ("Failure reasons", self.failure_reasons),
            ("Reusable reasoning conclusions", self.reusable_conclusions),
        ]
        lines = ["# Working Memory m_t", "Use these verified notes before choosing the next action."]
        for title, items in sections:
            lines.append(f"\n## {title}")
            if items:
                lines.extend(f"- {item}" for item in items)
            else:
                lines.append("- None yet.")
        lines.append("\n## Current best candidate SQL")
        if self.current_best_candidate_sql:
            best = self.current_best_candidate_sql
            lines.append(f"- SQL: {best['sql']}")
            lines.append(f"- Columns: {best['columns']}")
            lines.append(f"- Preview rows: {best['preview']}")
            lines.append("- If this candidate fits the task, refine or confirm it instead of restarting exploration.")
        else:
            lines.append("- None yet.")
        text = "\n".join(lines)
        if len(text) > max_chars:
            text = text[: max_chars - 25].rstrip() + "\n... (memory truncated)"
        return text

    def to_dict(self, max_chars: int) -> dict[str, Any]:
        return {
            "text": self.render(max_chars),
            "verified_database_facts": self.verified_database_facts,
            "invalid_or_unhelpful_attempts": self.invalid_or_unhelpful_attempts,
            "failure_reasons": self.failure_reasons,
            "reusable_conclusions": self.reusable_conclusions,
            "current_best_candidate_sql": self.current_best_candidate_sql,
            "candidate_history": self.candidate_history,
        }


def update_memory_from_schema(
    memory: EpisodeMemory,
    schema_json: dict[str, Any] | None,
    updates: list[str],
) -> None:
    if not schema_json:
        return
    tables = schema_json.get("tables", [])
    table_names: list[str] = []
    if isinstance(tables, list):
        for table in tables:
            if isinstance(table, str):
                table_names.append(table)
            elif isinstance(table, dict) and table.get("name"):
                table_names.append(str(table["name"]))
                columns = table.get("columns")
                if isinstance(columns, list):
                    col_names = []
                    for column in columns:
                        if isinstance(column, str):
                            col_names.append(column)
                        elif isinstance(column, dict) and column.get("name"):
                            col_names.append(str(column["name"]))
                    if col_names:
                        memory.add(
                            "verified_database_facts",
                            f"Proposed relevant columns for {table['name']}: {', '.join(col_names)}",
                            updates,
                        )
    columns = schema_json.get("columns")
    if isinstance(columns, dict):
        for table, cols in columns.items():
            if isinstance(cols, list):
                memory.add(
                    "verified_database_facts",
                    f"Proposed relevant columns for {table}: {', '.join(str(col) for col in cols)}",
                    updates,
                )
    if table_names:
        memory.add("verified_database_facts", f"Proposed relevant tables: {', '.join(table_names)}", updates)
    joins = schema_json.get("joins")
    join_count = 0
    if isinstance(joins, list):
        for join in joins:
            if isinstance(join, dict):
                condition = join.get("on") or join.get("join_condition") or join.get("join_column")
                if condition:
                    join_count += 1
                    memory.add("verified_database_facts", f"Proposed join: {condition}", updates)
            elif isinstance(join, str) and join.strip():
                join_count += 1
                memory.add("verified_database_facts", f"Proposed join: {join.strip()}", updates)
    if len(table_names) > 1 and join_count == 0:
        memory.add(
            "failure_reasons",
            "Schema proposal contains multiple tables but no explicit joins; verify join path before generate_sql.",
            updates,
        )


def update_memory_from_tool_result(
    memory: EpisodeMemory,
    *,
    action: str | None,
    sql: str,
    result: dict[str, Any],
    updates: list[str],
) -> None:
    repeated = memory.note_sql_seen(sql)
    compact_sql = summarize_sql(sql)
    if repeated:
        memory.add("invalid_or_unhelpful_attempts", f"Repeated SQL; avoid running again: {compact_sql}", updates)
    if action == "generate_sql" and is_sample_or_metadata_query(sql):
        memory.add(
            "invalid_or_unhelpful_attempts",
            f"Action mismatch risk: generate_sql ran metadata/sample query instead of candidate answer SQL: {compact_sql}",
            updates,
        )

    if not result.get("ok"):
        error = result.get("error", "unknown tool error")
        memory.add("failure_reasons", f"SQL failed: {error}. SQL: {compact_sql}", updates)
        no_col = re.search(r"no such column:\s*([^\s]+)", error, re.IGNORECASE)
        if no_col:
            bad_column = no_col.group(1).strip()
            memory.add(
                "invalid_or_unhelpful_attempts",
                f"Do not reuse invalid column {bad_column}; inspect table_info or DDL for the correct field name.",
                updates,
            )
        return

    rows = result.get("rows") or []
    columns = result.get("columns") or []
    if not rows:
        memory.add(
            "invalid_or_unhelpful_attempts",
            f"Empty result; avoid repeating without changing filters/values: {compact_sql}",
            updates,
        )
        memory.add(
            "failure_reasons",
            "A query returned no rows; verify value spelling/case, date format, or join/filter conditions.",
            updates,
        )
        return

    if action == "generate_sql":
        memory.set_best_candidate(sql, result, updates)

    if 1 <= len(columns) <= 3 and len(rows) <= 12 and not is_metadata_query(sql):
        memory.add(
            "verified_database_facts",
            f"Observed small result/value preview for query {compact_sql}: {format_result_preview(result, 5)}",
            updates,
        )

    lower_columns = [str(col).lower() for col in columns]
    upper_sql = sql.upper()
    if "SQLITE_MASTER" in upper_sql or "SQLITE_SCHEMA" in upper_sql:
        if lower_columns == ["name"]:
            names = [str(row[0]) for row in rows if row]
            if names:
                memory.add("verified_database_facts", f"Discovered tables: {', '.join(names)}", updates)
        if "sql" in lower_columns:
            table_name = parse_sqlite_master_table_name(sql)
            label = f" for {table_name}" if table_name else ""
            memory.add("verified_database_facts", f"Verified DDL{label}: {format_result_preview(result, 1)}", updates)
            ddl_text = "\n".join(str(value) for row in rows for value in row)
            for fk in re.findall(r"foreign key\s*\(([^)]+)\)\s*references\s*([^(]+)\(([^)]+)\)", ddl_text, re.I):
                from_col, ref_table, ref_col = [part.strip().strip("`\"") for part in fk]
                source = table_name or "current table"
                memory.add(
                    "verified_database_facts",
                    f"Verified foreign key: {source}.{from_col} -> {ref_table.strip()}.{ref_col}",
                    updates,
                )

    table_info_table = parse_pragma_table(sql, "table_info")
    if table_info_table and rows:
        col_summaries = []
        for row in rows:
            if len(row) >= 3:
                name = str(row[1])
                col_type = str(row[2] or "")
                pk = " pk" if len(row) >= 6 and row[5] else ""
                col_summaries.append(f"{name} {col_type}{pk}".strip())
                if re.search(r"[\s\-]", name):
                    memory.add(
                        "reusable_conclusions",
                        f"Column {table_info_table}.{name!r} contains space/hyphen; quote it as {quote_ident(name)} in SQL.",
                        updates,
                    )
        if col_summaries:
            memory.add(
                "verified_database_facts",
                f"Verified columns for {table_info_table}: {', '.join(col_summaries)}",
                updates,
            )

    fk_table = parse_pragma_table(sql, "foreign_key_list")
    if fk_table and rows:
        for row in rows:
            if len(row) >= 5:
                ref_table = row[2]
                from_col = row[3]
                ref_col = row[4]
                memory.add(
                    "verified_database_facts",
                    f"Verified foreign key: {fk_table}.{from_col} -> {ref_table}.{ref_col}",
                    updates,
                )

    distinct_col = parse_distinct_column(sql)
    if distinct_col and rows:
        values = [row[0] for row in rows if row]
        rendered = ", ".join("NULL" if value is None else repr(value) for value in values[:12])
        suffix = " ..." if len(values) > 12 or result.get("truncated") else ""
        memory.add("verified_database_facts", f"Distinct values for {distinct_col}: {rendered}{suffix}", updates)


def update_memory_from_error(
    memory: EpisodeMemory,
    *,
    error: str,
    updates: list[str],
) -> None:
    memory.add("failure_reasons", f"Format/action error: {error}", updates)


def find_db_path(db_root: Path, db_id: str) -> Path:
    candidates = [
        db_root / db_id / f"{db_id}.sqlite",
        db_root / f"{db_id}.sqlite",
        db_root if db_root.suffix == ".sqlite" else None,
    ]
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate
    tried = "\n".join(f"  - {p}" for p in candidates if p)
    raise FileNotFoundError(f"Missing database for {db_id}. Tried:\n{tried}")


def execute_tool_sql(
    db_path: Path,
    sql: str,
    *,
    timeout_s: float,
    max_rows: int,
) -> dict[str, Any]:
    ok, reason = is_readonly_sql(sql)
    if not ok:
        return {"ok": False, "error": reason}

    start = time.perf_counter()
    timed_out = False
    conn: sqlite3.Connection | None = None

    def interrupt_on_timeout() -> int:
        nonlocal timed_out
        if time.perf_counter() - start > timeout_s:
            timed_out = True
            return 1
        return 0

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.set_progress_handler(interrupt_on_timeout, 1000)
        cursor = conn.execute(sql)
        rows = cursor.fetchmany(max_rows + 1)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        return {
            "ok": True,
            "columns": columns,
            "rows": rows[:max_rows],
            "truncated": len(rows) > max_rows,
            "elapsed": time.perf_counter() - start,
        }
    except Exception as exc:
        error = str(exc)
        if timed_out:
            error = f"SQL execution timeout after {timeout_s:.1f}s"
        return {"ok": False, "error": error, "elapsed": time.perf_counter() - start}
    finally:
        if conn is not None:
            try:
                conn.set_progress_handler(None, 0)
            except Exception:
                pass
            conn.close()


def format_tool_result(result: dict[str, Any], max_chars: int) -> str:
    if not result.get("ok"):
        text = f"Error: {result.get('error', 'unknown tool error')}"
        return text[:max_chars]

    columns = result.get("columns") or []
    rows = result.get("rows") or []
    if not columns:
        text = "Query executed successfully. No tabular result returned."
    elif not rows:
        text = "\t".join(columns) + "\nQuery executed successfully. No rows returned."
    else:
        lines = ["\t".join(str(c) for c in columns)]
        for row in rows:
            lines.append("\t".join("NULL" if value is None else str(value) for value in row))
        if result.get("truncated"):
            lines.append("... (more rows truncated)")
        text = "\n".join(lines)

    if len(text) > max_chars:
        text = text[:max_chars] + "\n... (observation truncated)"
    return text


def execute_eval_sql(
    db_path: Path,
    sql: str,
    timeout_s: float,
) -> tuple[bool, list[Any] | None, list[str], str | None, float]:
    start = time.perf_counter()
    if not sql.strip():
        return False, None, [], "empty SQL", time.perf_counter() - start

    timed_out = False
    conn = sqlite3.connect(db_path)

    def interrupt_on_timeout() -> int:
        nonlocal timed_out
        if time.perf_counter() - start > timeout_s:
            timed_out = True
            return 1
        return 0

    try:
        conn.set_progress_handler(interrupt_on_timeout, 1000)
        conn.execute("BEGIN TRANSACTION;")
        cursor = conn.execute(sql)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = cursor.fetchall()
        conn.rollback()
        return True, rows, columns, None, time.perf_counter() - start
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        error = str(exc)
        if timed_out:
            error = f"SQL execution timeout after {timeout_s:.1f}s"
        return False, None, [], error, time.perf_counter() - start
    finally:
        try:
            conn.set_progress_handler(None, 0)
        except Exception:
            pass
        conn.close()


def jsonable_cell(value: Any) -> Any:
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.hex()
    return value


def build_eval_result(
    ok: bool,
    rows: list[Any] | None,
    columns: list[str],
    error: str | None,
    max_rows: int,
) -> dict[str, Any]:
    row_count = len(rows) if rows is not None else None
    preview_rows = [[jsonable_cell(value) for value in row] for row in (rows or [])[:max_rows]]
    return {
        "ok": ok,
        "columns": columns,
        "rows": preview_rows,
        "row_count": row_count,
        "truncated": bool(row_count is not None and row_count > max_rows),
        "error": error,
    }


def evaluate(
    db_path: Path,
    pred_sql: str,
    gold_sql: str,
    sql_timeout: float,
    result_max_rows: int = 50,
) -> dict[str, Any]:
    pred_ok, pred_rows, pred_columns, pred_error, pred_time = execute_eval_sql(db_path, pred_sql, sql_timeout)
    gold_ok, gold_rows, gold_columns, gold_error, gold_time = execute_eval_sql(db_path, gold_sql, sql_timeout)
    correct = int(pred_ok and gold_ok and set(pred_rows or []) == set(gold_rows or []))
    return {
        "correct": correct,
        "pred_ok": pred_ok,
        "gold_ok": gold_ok,
        "pred_error": pred_error,
        "gold_error": gold_error,
        "pred_row_count": len(pred_rows) if pred_rows is not None else None,
        "gold_row_count": len(gold_rows) if gold_rows is not None else None,
        "pred_execution_time": pred_time,
        "gold_execution_time": gold_time,
        "pred_result": build_eval_result(pred_ok, pred_rows, pred_columns, pred_error, result_max_rows),
        "gold_result": build_eval_result(gold_ok, gold_rows, gold_columns, gold_error, result_max_rows),
    }


def extract_action(text: str) -> str | None:
    match = re.search(r"<action>(.*?)</action>", text, re.IGNORECASE | re.DOTALL)
    return match.group(1).strip().lower() if match else None


def normalize_think_tags(text: str) -> str:
    text = text or ""
    if "<think>" in text.lower() or "</think>" not in text.lower():
        return text
    end_only = re.search(r"^\s*(.*?)</think>", text, re.IGNORECASE | re.DOTALL)
    if not end_only or not end_only.group(1).strip():
        return text
    think_text = end_only.group(1).strip()
    rest = text[end_only.end() :].lstrip()
    return f"<think>{think_text}</think>\n\n{rest}" if rest else f"<think>{think_text}</think>"


def extract_think(text: str, reasoning_content: str | None = None) -> str:
    parts: list[str] = []
    if reasoning_content and reasoning_content.strip():
        parts.append(reasoning_content.strip())
    matches = [match.strip() for match in THINK_RE.findall(text or "") if match.strip()]
    if matches:
        parts.extend(matches)
    else:
        # Qwen thinking mode may omit the opening tag while still returning a
        # closing </think>; keep that preamble as the visible think trace.
        end_only = re.search(r"^\s*(.*?)</think>", text or "", re.IGNORECASE | re.DOTALL)
        if end_only and end_only.group(1).strip():
            parts.append(end_only.group(1).strip())
    return "\n\n".join(parts)


def extract_answer_sql(text: str) -> str | None:
    match = re.search(r"<answer>(.*?)</answer>", text, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    content = match.group(1).strip()
    block = SQL_BLOCK_RE.search(content)
    if block:
        content = block.group(1).strip()
    return extract_sql(content)


def extract_schema_json(text: str) -> tuple[dict[str, Any] | None, str | None]:
    match = re.search(r"<schema>(.*?)</schema>", text, re.IGNORECASE | re.DOTALL)
    if not match:
        return None, "missing <schema>...</schema>"
    raw = match.group(1).strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"invalid schema JSON: {exc}"
    if not isinstance(parsed, dict):
        return None, "schema must be a JSON object"
    return parsed, None


def extract_tool_call(text: str, default_db_id: str) -> tuple[dict[str, Any] | None, str | None]:
    match = re.search(r"<tool_call>(.*?)</tool_call>", text, re.IGNORECASE | re.DOTALL)
    if not match:
        return None, "missing <tool_call>...</tool_call>"

    raw = match.group(1).strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        sql = extract_sql(raw)
        if sql.upper().startswith(ALLOWED_SQL_PREFIXES):
            return {
                "name": "execute_sql_query",
                "arguments": {"db_id": default_db_id, "sql": sql},
            }, None
        return None, "tool_call must be valid JSON with name and arguments"

    if not isinstance(payload, dict):
        return None, "tool_call must be a JSON object"
    if payload.get("name") != "execute_sql_query":
        return None, "only execute_sql_query is supported"
    args = payload.get("arguments")
    if not isinstance(args, dict):
        return None, "tool_call.arguments must be a JSON object"
    sql = args.get("sql")
    if not isinstance(sql, str) or not sql.strip():
        return None, "tool_call.arguments.sql must be a non-empty string"
    db_id = args.get("db_id") or default_db_id
    if not isinstance(db_id, str):
        return None, "tool_call.arguments.db_id must be a string"
    return {
        "name": "execute_sql_query",
        "arguments": {"db_id": db_id, "sql": sql.strip()},
    }, None


def build_format_feedback(round_idx: int, max_rounds: int, error: str) -> str:
    remaining = max_rounds - round_idx - 1
    urgency = ""
    if remaining <= 1:
        urgency = "You are almost out of turns. Prepare to confirm your best SQL.\n"
    return f"""Invalid action format: {error}
{urgency}
Use exactly one valid action:
<think>brief reasoning</think>
<action>explore_schema</action>
<tool_call>{{"name": "execute_sql_query", "arguments": {{"db_id": "...", "sql": "..."}}}}</tool_call>

or

<think>brief reasoning</think>
<action>propose_schema</action>
<schema>{{"tables": [...], "columns": {{}}, "joins": []}}</schema>

or

<think>brief reasoning</think>
<action>generate_sql</action>
<tool_call>{{"name": "execute_sql_query", "arguments": {{"db_id": "...", "sql": "..."}}}}</tool_call>

or

<think>brief reasoning</think>
<action>confirm_answer</action>
<answer>```sql
SELECT ...;
```</answer>
"""


def call_model_with_metadata(
    client: httpx.Client,
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int | None,
    temperature: float,
    top_p: float,
    llm_retries: int,
    retry_sleep: float,
    enable_thinking: bool,
) -> tuple[str, str | None, float, dict[str, Any]]:
    started = time.perf_counter()
    last_error: Exception | None = None
    for attempt in range(llm_retries + 1):
        try:
            request_payload: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "top_p": top_p,
                "chat_template_kwargs": {"enable_thinking": enable_thinking},
            }
            if max_tokens is not None:
                request_payload["max_tokens"] = max_tokens
            response = client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=request_payload,
            )
            response.raise_for_status()
            payload = response.json()
            choice = payload["choices"][0]
            message = choice["message"]
            reasoning_content = (
                message.get("reasoning_content")
                or message.get("reasoning")
                or message.get("reasoning_text")
            )
            content = normalize_think_tags(message.get("content") or "")
            response_metadata = {
                "finish_reason": choice.get("finish_reason"),
                "usage": payload.get("usage") or {},
            }
            return content, reasoning_content, time.perf_counter() - started, response_metadata
        except Exception as exc:
            last_error = exc
            if attempt < llm_retries:
                time.sleep(retry_sleep)
    raise RuntimeError(f"LLM call failed after {llm_retries + 1} attempt(s): {last_error}") from last_error


def call_model(
    client: httpx.Client,
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int | None,
    temperature: float,
    top_p: float,
    llm_retries: int,
    retry_sleep: float,
    enable_thinking: bool,
) -> tuple[str, str | None, float]:
    content, reasoning_content, latency, _ = call_model_with_metadata(
        client,
        base_url=base_url,
        api_key=api_key,
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        llm_retries=llm_retries,
        retry_sleep=retry_sleep,
        enable_thinking=enable_thinking,
    )
    return content, reasoning_content, latency


def run_trustsql_episode(
    client: httpx.Client,
    sample: dict[str, Any],
    db_root: Path,
    args: argparse.Namespace,
) -> dict[str, Any]:
    db_id = sample["db_id"]
    db_path = find_db_path(db_root, db_id)
    messages = build_initial_messages(sample)
    conversation: list[dict[str, Any]] = []
    schema_proposals: list[dict[str, Any]] = []
    last_generated_sql: str | None = None
    pred_sql: str | None = None
    total_latency = 0.0
    terminated = False
    memory_enabled = bool(getattr(args, "enable_memory", True))
    max_memory_chars = int(getattr(args, "max_memory_chars", 2500))
    memory_debug = bool(getattr(args, "memory_debug", False))
    memory = EpisodeMemory() if memory_enabled else None

    for round_idx in range(args.max_rounds):
        memory_before = memory.render(max_memory_chars) if memory is not None else None
        call_messages = messages
        if memory_before is not None:
            call_messages = messages + [{"role": "user", "content": memory_before}]
        assistant_text, reasoning_content, latency = call_model(
            client,
            base_url=args.base_url,
            api_key=args.api_key,
            model=args.model,
            messages=call_messages,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            top_p=args.top_p,
            llm_retries=args.llm_retries,
            retry_sleep=args.retry_sleep,
            enable_thinking=args.enable_thinking,
        )
        total_latency += latency
        action = extract_action(assistant_text)
        think = extract_think(assistant_text, reasoning_content)
        messages.append({"role": "assistant", "content": assistant_text})
        memory_updates: list[str] = []
        round_record: dict[str, Any] = {
            "round": round_idx + 1,
            "assistant": {
                "assistant_text": assistant_text,
                "think": think,
                "action": action,
                "tool_call": None,
                "schema": None,
                "answer_sql": None,
            },
            "latency": latency,
        }
        if memory_before is not None:
            round_record["memory_before"] = memory_before
        if reasoning_content:
            round_record["reasoning_content"] = reasoning_content

        def finalize_memory_record() -> None:
            if memory is None:
                return
            round_record["memory_after"] = memory.render(max_memory_chars)
            if memory_debug:
                round_record["memory_updates"] = memory_updates

        answer_sql = extract_answer_sql(assistant_text)
        if answer_sql:
            pred_sql = answer_sql
            terminated = True
            round_record["pred_sql"] = pred_sql
            round_record["assistant"]["answer_sql"] = pred_sql
            if memory is not None and memory.current_best_candidate_sql:
                best_sql = str(memory.current_best_candidate_sql.get("sql", ""))
                if normalize_sql_for_memory(pred_sql) != normalize_sql_for_memory(best_sql):
                    memory.add(
                        "failure_reasons",
                        "confirm_answer SQL differs from the current verified best candidate; only change it when the "
                        "candidate result shape or filters were proven wrong.",
                        memory_updates,
                    )
                    memory.add(
                        "reusable_conclusions",
                        "At confirm_answer, prefer reusing the latest successful generate_sql candidate unless there is "
                        "new evidence requiring a revision.",
                        memory_updates,
                    )
            finalize_memory_record()
            conversation.append(round_record)
            break

        if action == "propose_schema":
            schema_json, error = extract_schema_json(assistant_text)
            if error:
                feedback = build_format_feedback(round_idx, args.max_rounds, error)
                round_record["error"] = error
                if memory is not None:
                    update_memory_from_error(memory, error=error, updates=memory_updates)
            else:
                schema_proposals.append(schema_json or {})
                table_count = len((schema_json or {}).get("tables", []))
                columns = (schema_json or {}).get("columns", {})
                column_count = sum(len(cols) for cols in columns.values()) if isinstance(columns, dict) else 0
                feedback = (
                    f"Schema acknowledged: {table_count} table(s), {column_count} column(s). "
                    "Proceed to generate_sql when ready."
                )
                round_record["assistant"]["schema"] = schema_json
                if memory is not None:
                    update_memory_from_schema(memory, schema_json, memory_updates)
            messages.append({"role": "user", "content": feedback})
            round_record["observation"] = feedback
            finalize_memory_record()
            conversation.append(round_record)
            continue

        if action in {"explore_schema", "generate_sql"}:
            tool_call, error = extract_tool_call(assistant_text, db_id)
            if error:
                feedback = build_format_feedback(round_idx, args.max_rounds, error)
                round_record["error"] = error
                if memory is not None:
                    update_memory_from_error(memory, error=error, updates=memory_updates)
            else:
                call_db_id = tool_call["arguments"]["db_id"]
                sql = tool_call["arguments"]["sql"]
                round_record["assistant"]["tool_call"] = tool_call
                if call_db_id != db_id:
                    feedback = f"Error: tool_call db_id must be {db_id!r}, got {call_db_id!r}."
                    if memory is not None:
                        update_memory_from_error(memory, error=feedback, updates=memory_updates)
                elif args.enforce_metadata_only_explore and action == "explore_schema" and not is_metadata_query(sql):
                    feedback = (
                        "Error: explore_schema may only query metadata. Use sqlite_master/sqlite_schema "
                        "or PRAGMA table_info/foreign_key_list."
                    )
                    if memory is not None:
                        update_memory_from_error(memory, error=feedback, updates=memory_updates)
                else:
                    result = execute_tool_sql(
                        db_path,
                        sql,
                        timeout_s=args.sql_timeout,
                        max_rows=args.tool_max_rows,
                    )
                    feedback = format_tool_result(result, args.max_observation_chars)
                    round_record["tool_result"] = result
                    if memory is not None:
                        update_memory_from_tool_result(
                            memory,
                            action=action,
                            sql=sql,
                            result=result,
                            updates=memory_updates,
                        )
                    if action == "generate_sql":
                        last_generated_sql = sql
            messages.append({"role": "user", "content": feedback})
            round_record["observation"] = feedback
            finalize_memory_record()
            conversation.append(round_record)
            continue

        feedback = build_format_feedback(
            round_idx,
            args.max_rounds,
            f"unknown or missing action {action!r}",
        )
        messages.append({"role": "user", "content": feedback})
        round_record["error"] = f"unknown or missing action {action!r}"
        round_record["observation"] = feedback
        if memory is not None:
            update_memory_from_error(memory, error=round_record["error"], updates=memory_updates)
        finalize_memory_record()
        conversation.append(round_record)

    if pred_sql is None and args.fallback_to_last_generated and last_generated_sql:
        pred_sql = extract_sql(last_generated_sql)

    return {
        "pred_sql": pred_sql or "",
        "terminated": terminated,
        "rounds": len(conversation),
        "conversation": conversation,
        "schema_proposals": schema_proposals,
        "total_llm_latency": total_latency,
        "used_fallback_sql": bool(pred_sql and not terminated),
        "memory_enabled": memory_enabled,
        "final_memory": memory.render(max_memory_chars) if memory is not None else "",
    }


def load_completed(details_path: Path) -> tuple[set[str], int, int]:
    completed: set[str] = set()
    correct_count = 0
    evaluated_count = 0
    if not details_path.exists():
        return completed, correct_count, evaluated_count
    with details_path.open(encoding="utf-8") as existing_f:
        for line in existing_f:
            if not line.strip():
                continue
            record = json.loads(line)
            completed.add(str(record["question_id"]))
            correct_count += int(record.get("correct", 0))
            evaluated_count += 1
    return completed, correct_count, evaluated_count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/arcwise_plat_full_with_diff.json")
    parser.add_argument("--db-root", default="data/arcwise_plat/dev/dev_databases")
    parser.add_argument("--out-dir", default="results/qwen35-4b-arcwise-plat-trustsql")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--api-key", default="EMPTY")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--llm-retries", type=int, default=2)
    parser.add_argument("--retry-sleep", type=float, default=2.0)
    parser.add_argument("--max-rounds", type=int, default=10)
    parser.add_argument("--max-observation-chars", type=int, default=6000)
    parser.add_argument("--tool-max-rows", type=int, default=80)
    parser.add_argument("--sql-timeout", type=float, default=60.0)
    parser.add_argument("--eval-result-max-rows", type=int, default=50)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--question-id", action="append", default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--fallback-to-last-generated", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--enforce-metadata-only-explore", action="store_true")
    parser.add_argument("--enable-thinking", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--enable-memory", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--max-memory-chars", type=int, default=2500)
    parser.add_argument("--memory-debug", action="store_true")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    data_path = resolve_path(args.data, script_dir)
    db_root = resolve_path(args.db_root, script_dir)
    out_dir = resolve_path(args.out_dir, script_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pred_path = out_dir / "predictions.json"
    details_path = out_dir / "details.jsonl"
    summary_path = out_dir / "summary.json"

    data = json.load(data_path.open())
    if args.question_id:
        wanted = {str(qid) for qid in args.question_id}
        data = [item for item in data if str(item["question_id"]) in wanted]
    if args.limit is not None:
        data = data[: args.limit]

    predictions: dict[str, str] = {}
    if args.resume and pred_path.exists():
        predictions = json.load(pred_path.open())

    completed: set[str] = set()
    correct_count = 0
    evaluated_count = 0
    if args.resume:
        completed, correct_count, evaluated_count = load_completed(details_path)

    total = len(data)
    details_mode = "a" if args.resume and details_path.exists() else "w"
    with httpx.Client(trust_env=False, timeout=300) as client, details_path.open(
        details_mode, encoding="utf-8"
    ) as details_f:
        for idx, sample in enumerate(data, start=1):
            qid = str(sample["question_id"])
            if qid in completed:
                continue

            db_path = find_db_path(db_root, sample["db_id"])
            if qid in predictions:
                episode = {
                    "pred_sql": predictions[qid],
                    "terminated": None,
                    "rounds": None,
                    "conversation": None,
                    "schema_proposals": None,
                    "total_llm_latency": None,
                    "used_fallback_sql": None,
                    "memory_enabled": args.enable_memory,
                    "final_memory": "",
                }
            else:
                episode = run_trustsql_episode(client, sample, db_root, args)
                predictions[qid] = episode["pred_sql"]
                pred_path.write_text(json.dumps(predictions, indent=2, ensure_ascii=False), encoding="utf-8")

            eval_info = evaluate(
                db_path,
                episode["pred_sql"],
                sample["SQL"],
                args.sql_timeout,
                args.eval_result_max_rows,
            )
            correct_count += eval_info["correct"]
            evaluated_count += 1
            record = {
                "idx": idx,
                "question_id": qid,
                "db_id": sample["db_id"],
                "question": sample["question"],
                "evidence": sample.get("evidence", ""),
                "gold_sql": sample["SQL"],
                **episode,
                **eval_info,
            }
            details_f.write(json.dumps(record, ensure_ascii=False) + "\n")
            details_f.flush()
            print(
                f"[{idx}/{total}] qid={qid} db={sample['db_id']} correct={eval_info['correct']} "
                f"rounds={episode['rounds']} terminated={episode['terminated']} "
                f"running_ex={correct_count / evaluated_count:.4f}",
                flush=True,
            )

    summary = {
        "dataset": str(data_path),
        "db_root": str(db_root),
        "model": args.model,
        "base_url": args.base_url,
        "total": evaluated_count,
        "correct": correct_count,
        "execution_accuracy": correct_count / evaluated_count if evaluated_count else 0.0,
        "max_rounds": args.max_rounds,
        "temperature": args.temperature,
        "top_p": args.top_p,
        "max_tokens": args.max_tokens,
        "eval_result_max_rows": args.eval_result_max_rows,
        "enable_thinking": args.enable_thinking,
        "enable_memory": args.enable_memory,
        "max_memory_chars": args.max_memory_chars,
        "memory_debug": args.memory_debug,
        "enforce_metadata_only_explore": args.enforce_metadata_only_explore,
        "fallback_to_last_generated": args.fallback_to_last_generated,
        "predictions_path": str(pred_path),
        "details_path": str(details_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
