from __future__ import annotations

import argparse
from datetime import datetime, timezone
import html
import json
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from run_qwen35_arcwise_trustsql import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    build_eval_result,
    call_model,
    execute_eval_sql,
    extract_sql,
    extract_think,
    find_db_path,
    format_tool_result,
    is_metadata_query,
    jsonable_cell,
    quote_ident,
    resolve_path,
)


SCHEMA_STAGE = "schema_exploration"
SQL_STAGE = "sql_generation"
DONE_STAGE = "done"

SCHEMA_TOOLS = {
    "list_table_name",
    "get_table_metadata",
    "inspect_value",
    "inspect_rows",
    "inspect_foreign_key",
    "inspect_join_candidate",
    "terminate_first_stage",
}
SQL_TOOLS = {
    "execute_sub_sql",
    "execute_sql",
    "return_to_schema_stage",
    "terminate_second_stage",
}
TOOL_CALL_RE = re.compile(r"<tool_call>(.*?)</tool_call>", re.IGNORECASE | re.DOTALL)
THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
TWOSTAGE_ALLOWED_SQL_PREFIXES = ("SELECT", "WITH", "PRAGMA", "EXPLAIN")
INSPECT_ROWS_ALIAS_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
INSPECT_ROWS_BINARY_OPERATORS = {"=", "!=", "<", "<=", ">", ">=", "LIKE"}
INSPECT_ROWS_NULL_OPERATORS = {"IS NULL", "IS NOT NULL"}
INSPECT_ROWS_MAX_COLUMNS = 8
INSPECT_ROWS_MAX_FILTERS = 6
INSPECT_ROWS_MAX_ORDER_BY = 2
INSPECT_ROWS_MAX_IN_VALUES = 50
INSPECT_ROWS_MAX_ROWS = 50
JOIN_CANDIDATE_MAX_WORK_SECONDS = 7.0
JOIN_CANDIDATE_STATS_TIMEOUT_SECONDS = 1.0
JOIN_CANDIDATE_FULL_TIMEOUT_SECONDS = 4.0
JOIN_CANDIDATE_SAMPLE_TIMEOUT_SECONDS = 2.0
JOIN_CANDIDATE_SAMPLE_DISTINCT_KEYS = 2_000
PROJECTION_RELAXED_MAX_MAPPING_NODES = 100_000


AGENT_COMMON_PROMPT = """# Role
You are a tool-using Text-to-SQL agent working with an unknown SQLite database.
You must solve the task by autonomously calling the available tool for the
current stage. Never hallucinate tables, columns, joins, or values. Treat the
working memory as compressed evidence from prior tool interactions.

You do not output an <action> tag. The tool name is the action.

# Output Format
Every assistant response must use exactly this format:
<think>brief reasoning</think>
<tool_call>{"name": "TOOL_NAME", "arguments": {...}}</tool_call>

Both the opening <tool_call> tag and the closing </tool_call> tag are mandatory.
Never output bare JSON, and never omit the closing tag.
Do not include markdown outside JSON values. Do not call tools outside the
current stage's allowed tool list.
"""


SCHEMA_AGENT_SYSTEM_PROMPT = AGENT_COMMON_PROMPT + """

# Current Stage: schema_exploration
Goal: discover the verified schema evidence needed for the question. Use only
the tools listed in this prompt.

# Available Tools
Use these tools only to gather schema evidence. You cannot write free-form SQL
in this stage.

## list_table_name
Example:
<think>I need to see which tables exist before choosing relevant schema.</think>
<tool_call>{"name": "list_table_name", "arguments": {"db_id": "..."}}</tool_call>
Purpose: list all user tables in the current database.
Use when: you do not yet know which tables exist, or you need to reset your
candidate table set.
Returns: raw non-system table names, one name per line.
Do not use for: checking columns, values, joins, or solving the question.

## get_table_metadata
Example:
<think>I need exact columns, types, keys, and declared constraints for this table.</think>
<tool_call>{"name": "get_table_metadata", "arguments": {"db_id": "...", "table": "..."}}</tool_call>
Purpose: inspect one table's complete SQLite CREATE TABLE DDL.
Use when: a table may be relevant and you need to know its exact column names,
types, keys, or declared constraints.
Returns: the complete raw CREATE TABLE DDL. Use inspect_foreign_key for
normalized foreign-key evidence.
Do not use for: sampling real values from a column; use inspect_value instead.

## inspect_value
Example:
<think>I need to verify the real stored values for this column.</think>
<tool_call>{"name": "inspect_value", "arguments": {"db_id": "...", "table": "...", "column": "...", "pattern": null, "limit": 50}}</tool_call>
Purpose: inspect real distinct values stored in one verified column.
Use when: the question mentions a literal value, category, status, label, date
format, code, abbreviation, or natural-language condition that must be mapped
to database values.
Returns: up to limit raw distinct values, one per line, optionally LIKE-filtered.
Do not use for: retrieving another field from the same row, looking up an ID
from a name, applying a condition on one field while returning another field,
joins, aggregation, or final answers. Use inspect_rows for bounded row lookup.

## inspect_rows
Example (single table):
<think>I need the user ID and reputation from the same row as the verified display name.</think>
<tool_call>{"name": "inspect_rows", "arguments": {"db_id": "...", "table": "users", "alias": "u", "columns": ["u.Id", "u.DisplayName", "u.Reputation"], "filters": [{"column": "u.DisplayName", "op": "=", "value": "Harlan"}], "join": null, "order_by": [{"column": "u.Id", "direction": "ASC"}], "limit": 20}}</tool_call>
Example (one verified join):
<think>I need the race ID from the row whose name and year match the target race.</think>
<tool_call>{"name": "inspect_rows", "arguments": {"db_id": "...", "table": "races", "alias": "r", "columns": ["r.raceId", "r.name", "r.year"], "filters": [{"column": "r.name", "op": "=", "value": "Spanish Grand Prix"}, {"column": "r.year", "op": "=", "value": 2009}], "join": null, "order_by": [{"column": "r.raceId", "direction": "ASC"}], "limit": 20}}</tool_call>
Purpose: retrieve bounded real rows containing multiple related fields.
Use when: you need a name-to-ID mapping, associated fields, a conditionally
matched key, or a bounded lookup across one verified relationship.
Arguments:
- table and alias: the base table and a simple SQL alias.
- columns: 1-8 qualified fields, for example ["u.Id", "u.Reputation"].
- filters: 1-6 AND-connected predicates. Supported operators are =, !=, <,
  <=, >, >=, LIKE, IN, IS NULL, and IS NOT NULL.
- join: null, or one object with table, alias, type (INNER or LEFT), and
  on: {"left": "base_or_join_alias.column", "right": "..."}.
- order_by: optional 0-2 qualified fields with ASC or DESC.
- limit: optional, capped at 50.
The environment constructs read-only SQL. No expressions, aggregates,
subqueries, or second join are allowed. A join must be a declared foreign key or
a high/medium-confidence inspect_join_candidate pair from this episode.
Returns: compact tab-separated fields and rows; SQL NULL is rendered as NULL.
Do not use for: final answer execution, aggregation, unrestricted table scans,
or exploring a single column's value vocabulary; use inspect_value for the
latter.

## inspect_foreign_key
Example:
<think>I need to inspect declared foreign keys to verify possible join paths.</think>
<tool_call>{"name": "inspect_foreign_key", "arguments": {"db_id": "...", "table": null}}</tool_call>
Purpose: inspect declared SQLite foreign keys.
Use when: the question needs multiple tables, or you need to verify join paths.
Set table to a table name to inspect one table, or null to inspect all tables.
Returns: one child_table.child_column -> parent_table.parent_column relationship
per line, or NO DECLARED FOREIGN KEYS.
Important: it returns only declared foreign keys. If the database did not
declare a foreign key, this tool may return no join even when a logical join
exists.
Do not use for: inferring joins from similar column names; this tool does not
perform heuristic join guessing.

## inspect_join_candidate
Example:
<think>The declared foreign keys are incomplete. I hypothesize these two fields may join, so I need value-overlap evidence.</think>
<tool_call>{"name": "inspect_join_candidate", "arguments": {"db_id": "...", "left_table": "table1", "left_column": "column1", "right_table": "table2", "right_column": "column2"}}</tool_call>
Purpose: verify one model-proposed join pair using key and value-overlap evidence.
Use when: inspect_foreign_key returns no useful join or the declared FK path is
unclear, but you have a specific pair of columns that may connect two tables.
Arguments: exactly left_table, left_column, right_table, and right_column.
Prerequisite: inspect_foreign_key must first show that this exact pair is not a
declared foreign key. Use a declared pair directly; do not verify it again.
Returns: tested child-to-parent direction, status, relationship, confidence,
parent key type, value containment, row match rate, recommended join, and
cautions. Status is one of
verified_full, verified_metadata, verified_sampled, unverified_low_confidence,
or unverified_timeout.
How to interpret:
- Accept only high/medium confidence; containment is child-to-parent directional.
- Same names are not evidence; different names can form a valid pair.
- If both sides are non-unique, the pair may be a many-to-many/shared-domain
  overlap and may multiply rows; look for a bridge table or another key.
- For bridge tables, call this tool separately for each edge, such as
  A.id = bridge.a_id and bridge.b_id = B.id.
- Do not repeat an unverified_timeout pair or submit a low-confidence pair.
Prefer declared foreign keys; this tool does not create a declared constraint.
Do not use for: checking real values or final SQL execution.

## terminate_first_stage
Example:
<think>I have enough verified schema evidence to move to SQL generation.</think>
<tool_call>{"name": "terminate_first_stage", "arguments": {
    "tables": ["table1", "table2"],
    "columns": {
      "table1": ["column1", "column2"],
      "table2": ["column1"]
    },
    "joins": [
      {"left": "table1.column1", "right": "table2.column1"}
    ],
    "value_constraints": [
      {"table": "table1", "column": "column2", "values": ["verified_value"]}
    ],
    "unresolved": []
  }}</tool_call>
Purpose: end schema_exploration and submit the verified schema evidence needed
for SQL generation.
Use when: verified tables, columns, values, and joins are sufficient for SQL.
Returns: no database rows; the environment moves to sql_generation.
Use the exact flat example shape: table-name array, table-keyed column arrays,
verified left/right join pairs, and verified question literals. Use empty arrays
when no join or literal is needed. Do not include types. Put any non-critical
remaining uncertainty in unresolved; otherwise output "unresolved": [].

# Important Rules
- Do not write or execute complete SQL in this stage.
- Do not submit a final answer in this stage.
- Use terminate_first_stage only after the required schema evidence is verified.
- Submit only declared or high/medium-confidence verified joins.
- You must call terminate_first_stage before the schema stage budget is
  exhausted. Do not wait for the environment to move stages automatically.
- If the remaining rounds for current stage is 1, call terminate_first_stage
  with the best verified schema evidence instead of doing another low-value
  exploration step.
- Prefer using verified memory over repeating low-value exploration.
"""


FINAL_SCHEMA_TERMINATION_SYSTEM_PROMPT = AGENT_COMMON_PROMPT + """

# Forced Final Schema Submission
This is the final available schema_exploration round. Schema exploration is
over now: submit the best verified evidence already available in the working
memory.

# Sole Available Tool
## terminate_first_stage
Example:
<think>I will submit only the verified schema evidence gathered so far.</think>
<tool_call>{"name": "terminate_first_stage", "arguments": {
    "tables": ["table1", "table2"],
    "columns": {
      "table1": ["column1", "column2"],
      "table2": ["column1"]
    },
    "joins": [
      {"left": "table1.column1", "right": "table2.column1"}
    ],
    "value_constraints": [
      {"table": "table1", "column": "column2", "values": ["verified_value"]}
    ],
    "unresolved": []
  }}</tool_call>
Purpose: submit the schema evidence required for SQL generation and end the
schema_exploration stage.

# Required Behavior
- The only valid tool call in this response is terminate_first_stage.
- Output exactly one terminate_first_stage call using the required JSON shape.
- Reuse verified memory; do not invent schema facts.
- Include all required tables, columns, verified joins, and verified literals.
  Follow the flat example exactly. Do not include types. Always include
  unresolved; use an empty array when no non-critical uncertainty remains.
- Omit uncertain guesses. Do not delay submission for more exploration: no
  further schema round is available.
"""


SQL_AGENT_SYSTEM_PROMPT = AGENT_COMMON_PROMPT + """

# Current Stage: sql_generation
Goal: generate, execute, validate, and submit the final SQL answer. Use only the
tools listed in this prompt.

# Available Tools
In this stage you may write read-only SQL.

## execute_sub_sql
Example:
<think>I need to solve a sub-question first: find the last driver who completed all laps in the 1988 Australian Grand Prix.</think>
<tool_call>{"name": "execute_sub_sql", "arguments": {"db_id": "...", "sql": "SELECT ...", "purpose": "answer sub-question: last full-lap finisher in the target race"}}</tool_call>
Purpose: execute SQL for a semantic sub-question that is needed to solve the
full natural-language question.
Use when: the question is complex and should be decomposed into intermediate
SQL-answerable sub-problems, such as finding an entity, a count, a date range,
a filtered subset, an intermediate aggregate, or a comparison operand before
writing the final candidate.
Returns: only the raw tabular result (column names followed by rows) or one SQL
error line. The response does not repeat the SQL, purpose, timing, or other
execution metadata.
Do not use for: submitting the final answer candidate. A SQL run by this tool
cannot be used as the final answer.
Do not use for: schema discovery, PRAGMA/table_info queries, sqlite_master
queries, or checking what tables/columns exist. Schema evidence belongs to the
schema_exploration stage. If schema is insufficient, use return_to_schema_stage.

## execute_sql
Example:
<think>This complete SQL should answer the question, so I need to execute it as a final candidate.</think>
<tool_call>{"name": "execute_sql", "arguments": {"db_id": "...", "sql": "SELECT ..."}}</tool_call>
Purpose: execute a complete candidate final SQL query.
Use when: you believe the SQL fully answers the natural-language question and
you want to validate it against the database.
Returns: only the raw tabular result (column names followed by rows) or one SQL
error line. The response does not repeat the SQL, timing, or other execution
metadata. Successful execute_sql calls are stored as final-answer candidates.
Do not use for: schema discovery or small unrelated probes; use execute_sub_sql
for semantic sub-questions that directly support the final answer.

## return_to_schema_stage
Example:
<think>The SQL feedback shows missing schema evidence, so I need to return to schema exploration.</think>
<tool_call>{"name": "return_to_schema_stage", "arguments": {"reason": "...", "needed_info": "..."}}</tool_call>
Purpose: ask the environment to go back to the schema exploration stage when SQL
execution shows missing, conflicting, or uncertain schema evidence.
Use when: you discover an unknown column, unclear join, wrong value mapping, or
missing table that cannot be fixed confidently in sql_generation.
Returns: no database rows; the environment moves back to schema_exploration if
return budget remains.
Do not use for: ordinary SQL syntax fixes or minor filter revisions that can be
handled in this stage.

## terminate_second_stage
Example:
<think>The previously executed candidate SQL succeeded and matches the question.</think>
<tool_call>{"name": "terminate_second_stage", "arguments": {"evidence": "..."}}</tool_call>
Purpose: end the episode and submit the SQL from the immediately previous
successful execute_sql call as the final answer.
Use when: the immediately previous model round called execute_sql, that SQL
executed successfully, and its result satisfies the question.
Returns: final acceptance or an error if the previous round was not a successful
execute_sql call.
Do not use for: submitting or editing SQL. If you need a different SQL, run
execute_sql first; then call terminate_second_stage in the next round.

# Important Rules
- Execute candidate final answers with execute_sql before submitting them.
- terminate_second_stage does not accept a SQL string. The environment will
  automatically select the SQL from the immediately previous successful
  execute_sql call.
- You must call terminate_second_stage before the SQL stage or total budget is
  exhausted. Do not keep running sub-question queries until the environment
  stops the episode.
- If only 1 or 2 total model rounds remain, stop optional sub-question queries. If a
  previous execute_sql call succeeded and satisfies the question, call
  terminate_second_stage. If no successful candidate exists, run execute_sql
  with your best complete SQL candidate.
- If schema evidence is insufficient, use return_to_schema_stage. Do not try to
  inspect schema directly in this stage.
- In sql_generation, use execute_sub_sql only for problem-solving subqueries,
  not for schema inspection.
- Prefer using verified memory over repeating low-value exploration.
"""


FINAL_SQL_TERMINATION_SYSTEM_PROMPT = AGENT_COMMON_PROMPT + """

# Forced Final SQL Submission
This is the final available sql_generation round. SQL generation and validation
are over now. Submit the SQL from the immediately previous successful
execute_sql call.

# Sole Available Tool
## terminate_second_stage
Example:
<think>The immediately previous final candidate executed successfully, so I will submit it now.</think>
<tool_call>{"name": "terminate_second_stage", "arguments": {"evidence": "The immediately previous execute_sql result satisfies the question."}}</tool_call>
Purpose: end the episode and submit the SQL from the immediately previous
successful execute_sql call. The environment selects that SQL automatically.

# Required Behavior
- The only valid tool call in this response is terminate_second_stage.
- Output exactly one terminate_second_stage call using the example shape.
- Do not include, rewrite, edit, or regenerate SQL in the arguments.
- Use concise evidence explaining why the immediately previous execution result
  satisfies the question.
- Do not delay termination: no further sql_generation round is available.
"""


MEMORY_SYSTEM_PROMPT = """You are the working-memory compressor for a Text-to-SQL agent.
Your task is to produce only the new memory delta for the latest tool
interaction. The caller will append your delta to the existing memory.

Strict requirements:
1. Output exactly one new memory item for this latest round. Do not repeat, rewrite,
   summarize, delete, reorder, or renumber any existing memory item.
2. Output only the memory delta text. Do not output explanations, headings,
   Markdown code fences, XML tags, or JSON wrappers.
3. The new item must start with the exact next ordered number and explicit round
   marker, for example:
   "7. Round 7 | Action: inspect_value({\"db_id\":\"...\",\"table\":\"...\",\"column\":\"...\",\"pattern\":null,\"limit\":50}) | Useful memory: ..."
4. Do not copy the full raw tool-call history. Keep only information that may
   help produce the final correct SQL.
5. Do not invent database facts. Only use the previous memory and the latest
   tool observation as database evidence. The assistant <think> text may explain
   intent, assumptions, or why an action was taken, but it is not database
   evidence unless confirmed by the observation.
6. Preserve information that helps avoid repeated mistakes, such as invalid
   columns, empty results, wrong joins, value-mapping evidence, and successful
   candidate SQL queries.
7. Use the assistant <think> text to understand the reason for the chosen action
   and compress memory accordingly. The memory delta should be targeted to the
   action's purpose, not a casual or arbitrary summary of every returned detail.
8. The memory item must explicitly include the action name and complete action
   arguments. Do not omit parameters, abbreviate SQL, or replace arguments with
   placeholders.
9. For inspect_join_candidate observations, use this short field guide:
   - tested_direction is child/source -> parent/target.
   - status says whether verification was full, metadata-based, sampled, low
     confidence, or timed out; relationship is only a cardinality hypothesis.
   - confidence controls acceptance: only high/medium is verified evidence.
   - parent_key describes the target key kind; DATA_UNIQUE is observed data
     uniqueness, not a declared constraint.
   - value_containment is the matched fraction of distinct non-NULL source
     values; row_match_rate is the matched fraction of non-NULL source rows.
   - recommended_join is usable only for high/medium confidence. not_computed
     does not mean zero, and caution tags must be preserved.
   When compressing this tool, retain exact status, confidence, match rates, and
   cautions. Never write that a pair is verified when status is unverified,
   confidence is low, or value_containment is 0, even if relationship says
   many-to-one or one-to-one.
10. For inspect_foreign_key, retain the inspection scope and every returned
    declared child -> parent edge (or the explicit no-foreign-keys result). This
    evidence is required before the agent may infer an undeclared pair with
    inspect_join_candidate; never claim a declaration is absent if the relevant
    table scope was not checked.
"""


def normalize_sql_key(sql: str) -> str:
    return re.sub(r"\s+", " ", extract_sql(sql or "")).strip().rstrip(";").lower()


def compact_json(value: Any, max_chars: int = 5000) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) > max_chars:
        return text[:max_chars] + "...(truncated)"
    return text


def rows_to_jsonable(rows: list[Any]) -> list[list[Any]]:
    return [[jsonable_cell(value) for value in row] for row in rows]


def tool_result(
    *,
    ok: bool,
    columns: list[str] | None = None,
    rows: list[Any] | None = None,
    error: str | None = None,
    truncated: bool = False,
    elapsed: float | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "ok": ok,
        "columns": columns or [],
        "rows": rows_to_jsonable(rows or []),
        "row_count_preview": len(rows or []),
        "truncated": truncated,
        "error": error,
    }
    if elapsed is not None:
        result["elapsed"] = elapsed
    if extra:
        result.update(extra)
    return result


def sqlite_readonly_connection(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def strip_leading_sql_comments(sql: str) -> str:
    cleaned = sql.strip()
    while True:
        if cleaned.startswith("--"):
            newline = cleaned.find("\n")
            if newline == -1:
                return ""
            cleaned = cleaned[newline + 1 :].strip()
            continue
        if cleaned.startswith("/*"):
            end = cleaned.find("*/")
            if end == -1:
                return ""
            cleaned = cleaned[end + 2 :].strip()
            continue
        return cleaned


def is_twostage_readonly_sql(sql: str) -> tuple[bool, str | None]:
    cleaned = strip_leading_sql_comments(sql)
    if not cleaned:
        return False, "empty SQL"
    upper = cleaned.upper()
    if upper.startswith(TWOSTAGE_ALLOWED_SQL_PREFIXES):
        return True, None
    first_word = cleaned.split(maxsplit=1)[0] if cleaned else "EMPTY"
    return False, f"SQL must start with {TWOSTAGE_ALLOWED_SQL_PREFIXES}, got {first_word!r}"


def execute_twostage_sql(db_path: Path, sql: str, *, timeout_s: float, max_rows: int) -> dict[str, Any]:
    ok, reason = is_twostage_readonly_sql(sql)
    if not ok:
        return tool_result(ok=False, error=reason)

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
        conn = sqlite_readonly_connection(db_path)
        conn.set_progress_handler(interrupt_on_timeout, 1000)
        cursor = conn.execute(sql)
        rows = cursor.fetchmany(max_rows + 1)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        return tool_result(
            ok=True,
            columns=columns,
            rows=rows[:max_rows],
            truncated=len(rows) > max_rows,
            elapsed=time.perf_counter() - start,
        )
    except Exception as exc:
        error = str(exc)
        if timed_out:
            error = f"SQL execution timeout after {timeout_s:.1f}s"
        return tool_result(ok=False, error=error, elapsed=time.perf_counter() - start)
    finally:
        if conn is not None:
            try:
                conn.set_progress_handler(None, 0)
            except Exception:
                pass
            conn.close()


def projection_relaxed_match(pred_rows: list[Any], gold_rows: list[Any]) -> dict[str, Any]:
    """Check whether gold rows equal a projection of prediction rows.

    Row order and duplicate rows are ignored, matching the legacy strict EX
    evaluator's set semantics. A matching projection may drop arbitrary extra
    predicted columns and reorder the retained columns.
    """
    pred_set = {tuple(row) for row in pred_rows}
    gold_set = {tuple(row) for row in gold_rows}
    if not gold_set:
        return {
            "matched": not pred_set,
            "gold_to_pred_column_indices": [] if not pred_set else None,
            "mapping_search_nodes": 0,
            "mapping_search_truncated": False,
            "reason": "both results are empty" if not pred_set else "gold is empty but prediction has rows",
        }
    if not pred_set:
        return {
            "matched": False,
            "gold_to_pred_column_indices": None,
            "mapping_search_nodes": 0,
            "mapping_search_truncated": False,
            "reason": "prediction is empty but gold has rows",
        }

    gold_width = len(next(iter(gold_set)))
    pred_width = len(next(iter(pred_set)))
    if any(len(row) != gold_width for row in gold_set) or any(len(row) != pred_width for row in pred_set):
        return {
            "matched": False,
            "gold_to_pred_column_indices": None,
            "mapping_search_nodes": 0,
            "mapping_search_truncated": False,
            "reason": "inconsistent result row widths",
        }
    if pred_width < gold_width:
        return {
            "matched": False,
            "gold_to_pred_column_indices": None,
            "mapping_search_nodes": 0,
            "mapping_search_truncated": False,
            "reason": "prediction has fewer columns than gold",
        }

    gold_domains = [{row[index] for row in gold_set} for index in range(gold_width)]
    pred_domains = [{row[index] for row in pred_set} for index in range(pred_width)]
    candidates = [
        [pred_index for pred_index, domain in enumerate(pred_domains) if domain == gold_domains[gold_index]]
        for gold_index in range(gold_width)
    ]
    if any(not options for options in candidates):
        return {
            "matched": False,
            "gold_to_pred_column_indices": None,
            "mapping_search_nodes": 0,
            "mapping_search_truncated": False,
            "reason": "at least one gold column has no value-compatible predicted column",
            "candidate_counts": [len(options) for options in candidates],
        }

    search_order = sorted(range(gold_width), key=lambda index: (len(candidates[index]), index))
    mapping: list[int | None] = [None] * gold_width
    nodes = 0
    truncated = False

    def search(depth: int, used_pred_indices: set[int]) -> list[int] | None:
        nonlocal nodes, truncated
        nodes += 1
        if nodes > PROJECTION_RELAXED_MAX_MAPPING_NODES:
            truncated = True
            return None
        if depth == len(search_order):
            projection = {
                tuple(row[mapping[gold_index]] for gold_index in range(gold_width))
                for row in pred_set
            }
            if projection == gold_set:
                return [int(index) for index in mapping if index is not None]
            return None

        gold_index = search_order[depth]
        for pred_index in candidates[gold_index]:
            if pred_index in used_pred_indices:
                continue
            mapping[gold_index] = pred_index
            found = search(depth + 1, used_pred_indices | {pred_index})
            if found is not None:
                return found
            if truncated:
                return None
            mapping[gold_index] = None
        return None

    found_mapping = search(0, set())
    return {
        "matched": found_mapping is not None,
        "gold_to_pred_column_indices": found_mapping,
        "mapping_search_nodes": nodes,
        "mapping_search_truncated": truncated,
        "reason": "projection matches gold" if found_mapping is not None else "no matching projected column assignment",
        "candidate_counts": [len(options) for options in candidates],
    }


def evaluate_with_projection_mode(
    db_path: Path,
    pred_sql: str,
    gold_sql: str,
    sql_timeout: float,
    result_max_rows: int,
    evaluation_mode: str,
) -> dict[str, Any]:
    pred_ok, pred_rows, pred_columns, pred_error, pred_time = execute_eval_sql(db_path, pred_sql, sql_timeout)
    gold_ok, gold_rows, gold_columns, gold_error, gold_time = execute_eval_sql(db_path, gold_sql, sql_timeout)
    strict_correct = int(pred_ok and gold_ok and set(pred_rows or []) == set(gold_rows or []))

    projection_details: dict[str, Any]
    if pred_ok and gold_ok:
        projection_details = projection_relaxed_match(pred_rows or [], gold_rows or [])
        projection_relaxed_correct = int(projection_details["matched"])
    else:
        projection_relaxed_correct = 0
        projection_details = {
            "matched": False,
            "gold_to_pred_column_indices": None,
            "mapping_search_nodes": 0,
            "mapping_search_truncated": False,
            "reason": "prediction or gold SQL did not execute",
        }

    mapping_indices = projection_details.get("gold_to_pred_column_indices")
    if isinstance(mapping_indices, list):
        projection_details["gold_to_pred_columns"] = [
            {
                "gold_index": gold_index,
                "gold_column": gold_columns[gold_index] if gold_index < len(gold_columns) else None,
                "pred_index": pred_index,
                "pred_column": pred_columns[pred_index] if pred_index < len(pred_columns) else None,
            }
            for gold_index, pred_index in enumerate(mapping_indices)
        ]
    else:
        projection_details["gold_to_pred_columns"] = None

    if evaluation_mode == "strict":
        correct = strict_correct
    elif evaluation_mode == "projection_relaxed":
        correct = projection_relaxed_correct
    else:
        raise ValueError(f"unsupported evaluation mode: {evaluation_mode}")

    return {
        "correct": correct,
        "evaluation_mode": evaluation_mode,
        "strict_correct": strict_correct,
        "projection_relaxed_correct": projection_relaxed_correct,
        "projection_relaxed": projection_details,
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


def get_table_names(db_path: Path) -> list[str]:
    conn = sqlite_readonly_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return [str(row[0]) for row in rows]
    finally:
        conn.close()


def table_exists(db_path: Path, table: str) -> bool:
    conn = sqlite_readonly_connection(db_path)
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
            (table,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def column_exists(db_path: Path, table: str, column: str) -> bool:
    conn = sqlite_readonly_connection(db_path)
    try:
        rows = conn.execute(f"PRAGMA table_info({quote_ident(table)})").fetchall()
        return any(str(row[1]) == column for row in rows)
    finally:
        conn.close()


def run_list_table_name(db_path: Path, args: dict[str, Any]) -> dict[str, Any]:
    del args
    names = get_table_names(db_path)
    return {"ok": True, "tables": names}


def run_get_table_metadata(db_path: Path, args: dict[str, Any]) -> dict[str, Any]:
    table = args.get("table")
    if not isinstance(table, str) or not table.strip():
        return tool_result(ok=False, error="get_table_metadata requires a non-empty table string")
    table = table.strip()
    started = time.perf_counter()
    conn = sqlite_readonly_connection(db_path)
    try:
        ddl_row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name = ?",
            (table,),
        ).fetchone()
        if ddl_row is None:
            return tool_result(ok=False, error=f"no such table: {table}", elapsed=time.perf_counter() - started)
        ddl = str(ddl_row[0])
        return {"ok": True, "ddl": ddl}
    except Exception as exc:
        return tool_result(ok=False, error=str(exc), elapsed=time.perf_counter() - started)
    finally:
        conn.close()


def run_inspect_value(db_path: Path, args: dict[str, Any], max_rows: int) -> dict[str, Any]:
    table = args.get("table")
    column = args.get("column")
    pattern = args.get("pattern")
    limit_raw = args.get("limit", max_rows)
    if not isinstance(table, str) or not table.strip():
        return tool_result(ok=False, error="inspect_value requires a non-empty table string")
    if not isinstance(column, str) or not column.strip():
        return tool_result(ok=False, error="inspect_value requires a non-empty column string")
    try:
        limit = int(limit_raw)
    except (TypeError, ValueError):
        limit = max_rows
    limit = max(1, min(limit, max_rows))
    table = table.strip()
    column = column.strip()
    if not table_exists(db_path, table):
        return tool_result(ok=False, error=f"no such table: {table}")
    if not column_exists(db_path, table, column):
        return tool_result(ok=False, error=f"no such column: {table}.{column}")

    where = ""
    params: list[Any] = []
    if pattern is not None and str(pattern).strip():
        where = f" WHERE CAST({quote_ident(column)} AS TEXT) LIKE ?"
        params.append(str(pattern))
    sql = (
        f"SELECT DISTINCT {quote_ident(column)} FROM {quote_ident(table)} "
        f"{where} ORDER BY {quote_ident(column)} LIMIT {limit + 1}"
    )
    started = time.perf_counter()
    conn = sqlite_readonly_connection(db_path)
    try:
        rows = conn.execute(sql, params).fetchall()
        return {"ok": True, "values": [row[0] for row in rows[:limit]]}
    except Exception as exc:
        return tool_result(ok=False, error=str(exc), elapsed=time.perf_counter() - started, extra={"generated_sql": sql})
    finally:
        conn.close()


def canonical_join_pair(
    left_table: str,
    left_column: str,
    right_table: str,
    right_column: str,
) -> tuple[tuple[str, str], tuple[str, str]]:
    """Return an orientation-independent key for one concrete join pair."""
    return tuple(sorted(((left_table, left_column), (right_table, right_column))))


def run_inspect_rows(
    db_path: Path,
    args: dict[str, Any],
    max_rows: int,
    verified_join_pairs: set[tuple[tuple[str, str], tuple[str, str]]] | None = None,
) -> dict[str, Any]:
    """Run a bounded, declarative row lookup for schema-linking evidence."""

    def required_string(name: str) -> str | None:
        value = args.get(name)
        return value.strip() if isinstance(value, str) and value.strip() else None

    def valid_alias(value: str | None, argument_name: str) -> tuple[str | None, str | None]:
        if value is None:
            return None, f"inspect_rows requires a non-empty {argument_name} string"
        if not INSPECT_ROWS_ALIAS_RE.fullmatch(value):
            return None, (
                f"inspect_rows {argument_name} must match "
                "[A-Za-z_][A-Za-z0-9_]*"
            )
        return value, None

    base_table = required_string("table")
    base_alias, error = valid_alias(required_string("alias"), "alias")
    if base_table is None:
        return tool_result(ok=False, error="inspect_rows requires a non-empty table string")
    if error:
        return tool_result(ok=False, error=error)

    raw_columns = args.get("columns")
    if not isinstance(raw_columns, list) or not raw_columns:
        return tool_result(ok=False, error="inspect_rows requires a non-empty columns list")
    if len(raw_columns) > INSPECT_ROWS_MAX_COLUMNS:
        return tool_result(
            ok=False,
            error=f"inspect_rows supports at most {INSPECT_ROWS_MAX_COLUMNS} selected columns",
        )
    if not all(isinstance(column, str) and column.strip() for column in raw_columns):
        return tool_result(ok=False, error="inspect_rows columns must be non-empty qualified strings")

    raw_filters = args.get("filters")
    if not isinstance(raw_filters, list) or not raw_filters:
        return tool_result(
            ok=False,
            error="inspect_rows requires at least one filter; use inspect_value for unfiltered vocabularies",
        )
    if len(raw_filters) > INSPECT_ROWS_MAX_FILTERS:
        return tool_result(
            ok=False,
            error=f"inspect_rows supports at most {INSPECT_ROWS_MAX_FILTERS} filters",
        )

    raw_order_by = args.get("order_by", [])
    if raw_order_by is None:
        raw_order_by = []
    if not isinstance(raw_order_by, list):
        return tool_result(ok=False, error="inspect_rows order_by must be a list or null")
    if len(raw_order_by) > INSPECT_ROWS_MAX_ORDER_BY:
        return tool_result(
            ok=False,
            error=f"inspect_rows supports at most {INSPECT_ROWS_MAX_ORDER_BY} order_by fields",
        )

    try:
        requested_limit = int(args.get("limit", max_rows))
    except (TypeError, ValueError):
        requested_limit = max_rows
    limit_cap = max(1, min(int(max_rows), INSPECT_ROWS_MAX_ROWS))
    limit = max(1, min(requested_limit, limit_cap))

    raw_join = args.get("join")
    if raw_join is not None and not isinstance(raw_join, dict):
        return tool_result(ok=False, error="inspect_rows join must be null or an object")

    started = time.perf_counter()
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite_readonly_connection(db_path)
        table_names = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        if base_table not in table_names:
            return tool_result(ok=False, error=f"no such table: {base_table}", elapsed=time.perf_counter() - started)

        columns_by_table: dict[str, set[str]] = {}

        def table_columns(table_name: str) -> set[str]:
            if table_name not in columns_by_table:
                columns_by_table[table_name] = {
                    str(row[1])
                    for row in conn.execute(f"PRAGMA table_info({quote_ident(table_name)})").fetchall()
                }
            return columns_by_table[table_name]

        aliases: dict[str, str] = {str(base_alias): base_table}
        join_sql = ""
        join_validation: dict[str, Any] | None = None

        def parse_field_ref(raw: Any, *, argument_name: str) -> tuple[str, str] | None:
            if not isinstance(raw, str) or raw.count(".") != 1:
                return None
            alias, column = (part.strip() for part in raw.split(".", 1))
            if not alias or not column or alias not in aliases:
                return None
            table_name = aliases[alias]
            if column not in table_columns(table_name):
                return None
            return alias, column

        def field_sql(field: tuple[str, str]) -> str:
            return f"{quote_ident(field[0])}.{quote_ident(field[1])}"

        def declared_foreign_key(left: tuple[str, str], right: tuple[str, str]) -> bool:
            left_table = aliases[left[0]]
            right_table = aliases[right[0]]
            for child_table, child_column, parent_table, parent_column in (
                (left_table, left[1], right_table, right[1]),
                (right_table, right[1], left_table, left[1]),
            ):
                parent_info = conn.execute(
                    f"PRAGMA table_info({quote_ident(parent_table)})"
                ).fetchall()
                parent_primary_key = [
                    str(row[1])
                    for row in sorted(parent_info, key=lambda row: int(row[5] or 0))
                    if bool(row[5])
                ]
                foreign_keys = conn.execute(
                    f"PRAGMA foreign_key_list({quote_ident(child_table)})"
                ).fetchall()
                if any(
                    str(row[2]) == parent_table
                    and str(row[3]) == child_column
                    and (
                        str(row[4]) == parent_column
                        # SQLite represents REFERENCES parent_table without an
                        # explicit target column as NULL in PRAGMA output. It
                        # semantically references the parent's primary key.
                        or (
                            row[4] is None
                            and len(parent_primary_key) == 1
                            and parent_primary_key[0] == parent_column
                        )
                    )
                    for row in foreign_keys
                ):
                    return True
            return False

        if raw_join is not None:
            join_table = raw_join.get("table")
            join_alias_raw = raw_join.get("alias")
            if not isinstance(join_table, str) or not join_table.strip():
                return tool_result(ok=False, error="inspect_rows join requires a non-empty table string")
            join_table = join_table.strip()
            join_alias, join_alias_error = valid_alias(
                join_alias_raw.strip() if isinstance(join_alias_raw, str) else None,
                "join.alias",
            )
            if join_alias_error:
                return tool_result(ok=False, error=join_alias_error)
            if join_table not in table_names:
                return tool_result(ok=False, error=f"no such join table: {join_table}")
            if join_alias in aliases:
                return tool_result(ok=False, error="inspect_rows base and join aliases must differ")

            join_type = str(raw_join.get("type", "INNER")).upper().strip()
            if join_type not in {"INNER", "LEFT"}:
                return tool_result(ok=False, error="inspect_rows join.type must be INNER or LEFT")
            raw_on = raw_join.get("on")
            if not isinstance(raw_on, dict):
                return tool_result(ok=False, error="inspect_rows join requires on.left and on.right")

            aliases[str(join_alias)] = join_table
            left_ref = parse_field_ref(raw_on.get("left"), argument_name="join.on.left")
            right_ref = parse_field_ref(raw_on.get("right"), argument_name="join.on.right")
            if left_ref is None or right_ref is None:
                return tool_result(
                    ok=False,
                    error=(
                        "inspect_rows join.on fields must be existing qualified columns from the "
                        "base and join aliases"
                    ),
                )
            if {left_ref[0], right_ref[0]} != {str(base_alias), str(join_alias)}:
                return tool_result(
                    ok=False,
                    error="inspect_rows join.on must connect the base alias and the join alias",
                )

            join_pair = canonical_join_pair(
                aliases[left_ref[0]], left_ref[1], aliases[right_ref[0]], right_ref[1]
            )
            is_declared_fk = declared_foreign_key(left_ref, right_ref)
            is_candidate_verified = join_pair in (verified_join_pairs or set())
            if not is_declared_fk and not is_candidate_verified:
                return tool_result(
                    ok=False,
                    error=(
                        "inspect_rows join is not a declared foreign key and has not been verified by a "
                        "high/medium-confidence inspect_join_candidate call in this episode"
                    ),
                )
            join_sql = (
                f" {join_type} JOIN {quote_ident(join_table)} AS {quote_ident(str(join_alias))} "
                f"ON {field_sql(left_ref)} = {field_sql(right_ref)}"
            )
            join_validation = {
                "left": f"{aliases[left_ref[0]]}.{left_ref[1]}",
                "right": f"{aliases[right_ref[0]]}.{right_ref[1]}",
                "validation": "declared_foreign_key" if is_declared_fk else "verified_join_candidate",
            }

        selected_fields: list[dict[str, str]] = []
        select_sql_parts: list[str] = []
        seen_fields: set[tuple[str, str]] = set()
        for raw_column in raw_columns:
            field = parse_field_ref(raw_column, argument_name="columns")
            if field is None:
                return tool_result(
                    ok=False,
                    error=(
                        f"inspect_rows selected column {raw_column!r} must be an existing qualified field "
                        "such as u.Id"
                    ),
                )
            if field in seen_fields:
                return tool_result(ok=False, error=f"inspect_rows selected column {raw_column!r} is duplicated")
            seen_fields.add(field)
            output_name = f"{field[0]}__{field[1]}"
            select_sql_parts.append(f"{field_sql(field)} AS {quote_ident(output_name)}")
            selected_fields.append(
                {
                    "field": f"{field[0]}.{field[1]}",
                    "table": aliases[field[0]],
                    "column": field[1],
                    "output": output_name,
                }
            )

        where_parts: list[str] = []
        params: list[Any] = []
        normalized_filters: list[dict[str, Any]] = []
        for raw_filter in raw_filters:
            if not isinstance(raw_filter, dict):
                return tool_result(ok=False, error="inspect_rows each filter must be an object")
            field = parse_field_ref(raw_filter.get("column"), argument_name="filters.column")
            if field is None:
                return tool_result(
                    ok=False,
                    error="inspect_rows filters must use existing qualified columns such as u.DisplayName",
                )
            op = str(raw_filter.get("op", "")).upper().strip()
            if op in INSPECT_ROWS_NULL_OPERATORS:
                where_parts.append(f"{field_sql(field)} {op}")
                normalized_filters.append({"column": f"{field[0]}.{field[1]}", "op": op})
                continue
            if op == "IN":
                values = raw_filter.get("value")
                if (
                    not isinstance(values, list)
                    or not values
                    or len(values) > INSPECT_ROWS_MAX_IN_VALUES
                    or any(isinstance(value, (dict, list)) or value is None for value in values)
                ):
                    return tool_result(
                        ok=False,
                        error=(
                            "inspect_rows IN filters require a non-empty scalar value list with at most "
                            f"{INSPECT_ROWS_MAX_IN_VALUES} items"
                        ),
                    )
                placeholders = ", ".join("?" for _ in values)
                where_parts.append(f"{field_sql(field)} IN ({placeholders})")
                params.extend(values)
                normalized_filters.append(
                    {"column": f"{field[0]}.{field[1]}", "op": op, "value": values}
                )
                continue
            if op not in INSPECT_ROWS_BINARY_OPERATORS:
                return tool_result(
                    ok=False,
                    error=(
                        "inspect_rows filter op must be one of =, !=, <, <=, >, >=, LIKE, IN, "
                        "IS NULL, IS NOT NULL"
                    ),
                )
            value = raw_filter.get("value")
            if value is None or isinstance(value, (dict, list)):
                return tool_result(
                    ok=False,
                    error=f"inspect_rows {op} filters require one non-null scalar value",
                )
            where_parts.append(f"{field_sql(field)} {op} ?")
            params.append(value)
            normalized_filters.append(
                {"column": f"{field[0]}.{field[1]}", "op": op, "value": value}
            )

        order_sql_parts: list[str] = []
        normalized_order_by: list[dict[str, str]] = []
        for raw_order in raw_order_by:
            if not isinstance(raw_order, dict):
                return tool_result(ok=False, error="inspect_rows each order_by item must be an object")
            field = parse_field_ref(raw_order.get("column"), argument_name="order_by.column")
            if field is None:
                return tool_result(
                    ok=False,
                    error="inspect_rows order_by must use existing qualified columns such as u.Id",
                )
            direction = str(raw_order.get("direction", "ASC")).upper().strip()
            if direction not in {"ASC", "DESC"}:
                return tool_result(ok=False, error="inspect_rows order_by direction must be ASC or DESC")
            order_sql_parts.append(f"{field_sql(field)} {direction}")
            normalized_order_by.append({"column": f"{field[0]}.{field[1]}", "direction": direction})

        sql = (
            f"SELECT {', '.join(select_sql_parts)} "
            f"FROM {quote_ident(base_table)} AS {quote_ident(str(base_alias))}"
            f"{join_sql} WHERE {' AND '.join(where_parts)}"
        )
        if order_sql_parts:
            sql += f" ORDER BY {', '.join(order_sql_parts)}"
        sql += f" LIMIT {limit + 1}"

        rows = conn.execute(sql, params).fetchall()
        result_columns = [field["field"] for field in selected_fields]
        return {"ok": True, "columns": result_columns, "rows": rows[:limit]}
    except Exception as exc:
        return tool_result(ok=False, error=str(exc), elapsed=time.perf_counter() - started)
    finally:
        if conn is not None:
            conn.close()


def run_inspect_foreign_key(db_path: Path, args: dict[str, Any]) -> dict[str, Any]:
    table = args.get("table")
    if table is not None and (not isinstance(table, str) or not table.strip()):
        return tool_result(ok=False, error="inspect_foreign_key table must be a string or null")
    tables = [table.strip()] if isinstance(table, str) and table.strip() else get_table_names(db_path)
    started = time.perf_counter()
    conn = sqlite_readonly_connection(db_path)
    try:
        foreign_keys: list[tuple[str, str, str, str]] = []
        for table_name in tables:
            if not table_exists(db_path, table_name):
                return tool_result(ok=False, error=f"no such table: {table_name}", elapsed=time.perf_counter() - started)
            for fk in conn.execute(f"PRAGMA foreign_key_list({quote_ident(table_name)})").fetchall():
                _, seq, ref_table, from_col, to_col, _, _, _ = fk
                if to_col is None:
                    parent_pk = sorted(
                        (
                            (int(row[5]), str(row[1]))
                            for row in conn.execute(
                                f"PRAGMA table_info({quote_ident(str(ref_table))})"
                            ).fetchall()
                            if int(row[5]) > 0
                        ),
                        key=lambda item: item[0],
                    )
                    to_col = parent_pk[int(seq)][1] if int(seq) < len(parent_pk) else "<PRIMARY_KEY>"
                foreign_keys.append(
                    (str(table_name), str(from_col), str(ref_table), str(to_col))
                )
        return {"ok": True, "foreign_keys": foreign_keys}
    except Exception as exc:
        return tool_result(ok=False, error=str(exc), elapsed=time.perf_counter() - started)
    finally:
        conn.close()


def run_inspect_join_candidate(
    db_path: Path,
    args: dict[str, Any],
    max_rows: int,
    timeout_s: float,
) -> dict[str, Any]:
    del max_rows  # Pair verification returns one structured result, not a candidate list.

    def read_required_string(name: str) -> str | None:
        value = args.get(name)
        if not isinstance(value, str) or not value.strip():
            return None
        return value.strip()

    left_table = read_required_string("left_table")
    left_column = read_required_string("left_column")
    right_table = read_required_string("right_table")
    right_column = read_required_string("right_column")
    missing = [
        name
        for name, value in (
            ("left_table", left_table),
            ("left_column", left_column),
            ("right_table", right_table),
            ("right_column", right_column),
        )
        if value is None
    ]
    if missing:
        return tool_result(
            ok=False,
            error=(
                "inspect_join_candidate now verifies one explicit column pair. "
                f"Missing required argument(s): {', '.join(missing)}. "
                "Use left_table, left_column, right_table, right_column."
            ),
        )
    if left_table == right_table and left_column == right_column:
        return tool_result(ok=False, error="left and right columns must not be the same column")

    def type_affinity(declared_type: str) -> str:
        upper = (declared_type or "").upper()
        if "INT" in upper:
            return "INTEGER"
        if any(token in upper for token in ("CHAR", "CLOB", "TEXT")):
            return "TEXT"
        if any(token in upper for token in ("REAL", "FLOA", "DOUB")):
            return "REAL"
        if "BLOB" in upper or not upper:
            return "BLOB"
        return "NUMERIC"

    def types_compatible(left: str, right: str) -> bool:
        if "BLOB" in {left, right}:
            return False
        numeric = {"INTEGER", "REAL", "NUMERIC"}
        return left == right or (left in numeric and right in numeric)

    def normalized_identifier(value: str) -> str:
        return re.sub(r"[^a-z0-9]", "", value.lower())

    def semantic_role_support(source: dict[str, Any], target: dict[str, Any]) -> tuple[int, str]:
        source_name = normalized_identifier(str(source["column"]))
        target_name = normalized_identifier(str(target["column"]))
        target_table = normalized_identifier(str(target["table"]))
        target_singular = target_table[:-1] if target_table.endswith("s") else target_table
        if source_name == target_name:
            return 3, "same normalized column role"
        source_base = source_name[: -len(target_name)] if target_name and source_name.endswith(target_name) else source_name
        if target_singular and (
            target_singular in source_base
            or (len(source_base) >= 3 and source_base in target_singular)
        ):
            return 2, "source column role references the target table"
        return 0, "no column/table role support; verify semantics carefully"

    started = time.perf_counter()
    work_budget_seconds = min(max(float(timeout_s), 0.1), JOIN_CANDIDATE_MAX_WORK_SECONDS)
    deadline = started + work_budget_seconds
    conn = sqlite_readonly_connection(db_path)
    try:
        all_tables = set(get_table_names(db_path))
        for table in (left_table, right_table):
            if table not in all_tables:
                return tool_result(ok=False, error=f"no such table: {table}", elapsed=time.perf_counter() - started)

        def remaining_seconds() -> float:
            return max(0.0, deadline - time.perf_counter())

        def query_one_with_budget(
            sql: str,
            parameters: tuple[Any, ...] = (),
            requested_seconds: float = JOIN_CANDIDATE_FULL_TIMEOUT_SECONDS,
        ) -> tuple[tuple[Any, ...] | None, bool]:
            """Run one bounded SQLite statement and report timeout separately."""
            budget_seconds = min(requested_seconds, remaining_seconds())
            if budget_seconds <= 0:
                return None, True

            query_started = time.perf_counter()
            query_timed_out = False

            def interrupt_on_timeout() -> int:
                nonlocal query_timed_out
                if time.perf_counter() - query_started > budget_seconds:
                    query_timed_out = True
                    return 1
                return 0

            try:
                conn.set_progress_handler(interrupt_on_timeout, 1000)
                return conn.execute(sql, parameters).fetchone(), False
            except sqlite3.OperationalError as exc:
                if query_timed_out or "interrupted" in str(exc).lower():
                    return None, True
                raise
            finally:
                conn.set_progress_handler(None, 0)

        def column_profile(table: str, column: str) -> dict[str, Any]:
            info_rows = conn.execute(f"PRAGMA table_info({quote_ident(table)})").fetchall()
            column_row = next((row for row in info_rows if str(row[1]) == column), None)
            if column_row is None:
                raise ValueError(f"no such column: {table}.{column}")

            primary_key_columns = [
                str(row[1])
                for row in sorted(info_rows, key=lambda row: int(row[5] or 0))
                if bool(row[5])
            ]
            indexes: list[dict[str, Any]] = []
            for index_row in conn.execute(f"PRAGMA index_list({quote_ident(table)})").fetchall():
                index_name = str(index_row[1])
                indexed = conn.execute(f"PRAGMA index_info({quote_ident(index_name)})").fetchall()
                index_columns = [str(row[2]) for row in indexed if row[2] is not None]
                if not index_columns:
                    continue
                indexes.append(
                    {
                        "name": index_name,
                        "columns": index_columns,
                        "unique": bool(index_row[2]),
                        "origin": str(index_row[3]) if len(index_row) > 3 else "",
                        "partial": bool(index_row[4]) if len(index_row) > 4 else False,
                    }
                )

            declared_type = str(column_row[2] or "")
            is_primary_key = len(primary_key_columns) == 1 and primary_key_columns[0] == column
            unique_indexes = [
                item["name"]
                for item in indexes
                if item["unique"] and len(item["columns"]) == 1 and item["columns"][0] == column
            ]
            lookup_indexes = [item["name"] for item in indexes if item["columns"][0] == column]
            if is_primary_key and not lookup_indexes:
                # INTEGER PRIMARY KEY can be backed directly by SQLite rowid and
                # therefore may not appear in PRAGMA index_list.
                lookup_indexes = ["rowid_primary_key"]
            return {
                "table": table,
                "column": column,
                "declared_type": declared_type,
                "affinity": type_affinity(declared_type),
                "primary_key_columns": primary_key_columns,
                "is_primary_key": is_primary_key,
                "is_unique": is_primary_key or bool(unique_indexes),
                "unique_indexes": unique_indexes,
                "lookup_indexed": bool(lookup_indexes),
                "lookup_indexes": lookup_indexes,
                "is_data_unique": None,
                "non_null_rows": None,
                "distinct_values": None,
                "statistics_status": "not_computed",
            }

        left = column_profile(left_table, left_column)
        right = column_profile(right_table, right_column)
        type_compatible = types_compatible(str(left["affinity"]), str(right["affinity"]))

        warnings: list[str] = []
        if not type_compatible:
            warnings.append("column type affinities differ; SQLite may coerce values during equality comparison")

        def collect_column_statistics(profile: dict[str, Any]) -> None:
            row, statistics_timed_out = query_one_with_budget(
                f"SELECT COUNT({quote_ident(str(profile['column']))}), "
                f"COUNT(DISTINCT {quote_ident(str(profile['column']))}) "
                f"FROM {quote_ident(str(profile['table']))}",
                requested_seconds=JOIN_CANDIDATE_STATS_TIMEOUT_SECONDS,
            )
            if statistics_timed_out:
                profile["statistics_status"] = "timed_out"
                warnings.append(
                    f"statistics for {profile['table']}.{profile['column']} timed out; "
                    "key direction uses declared metadata only"
                )
                return
            non_null_rows = int((row or (0, 0))[0] or 0)
            distinct_values = int((row or (0, 0))[1] or 0)
            profile["non_null_rows"] = non_null_rows
            profile["distinct_values"] = distinct_values
            profile["is_data_unique"] = non_null_rows > 0 and non_null_rows == distinct_values
            profile["statistics_status"] = "full"

        collect_column_statistics(left)
        collect_column_statistics(right)

        def key_kind(profile: dict[str, Any]) -> str:
            if profile["is_primary_key"]:
                return "PRIMARY KEY"
            if profile["is_unique"]:
                return "UNIQUE"
            if profile["is_data_unique"]:
                return "DATA_UNIQUE"
            return "NON_UNIQUE"

        def foreign_key_evidence(source: dict[str, Any], target: dict[str, Any]) -> dict[str, Any] | None:
            foreign_keys = conn.execute(
                f"PRAGMA foreign_key_list({quote_ident(str(source['table']))})"
            ).fetchall()
            for row in foreign_keys:
                if str(row[2]) != str(target["table"]) or str(row[3]) != str(source["column"]):
                    continue
                referenced_column = row[4]
                if referenced_column is not None and str(referenced_column) == str(target["column"]):
                    return {"kind": "declared_foreign_key", "implicit_parent_primary_key": False}
                if (
                    referenced_column is None
                    and target["primary_key_columns"] == [target["column"]]
                ):
                    return {"kind": "declared_foreign_key", "implicit_parent_primary_key": True}
            return None

        def build_direction(
            source: dict[str, Any],
            target: dict[str, Any],
            direction: str,
        ) -> dict[str, Any]:
            semantic_score, semantic_support = semantic_role_support(source, target)
            target_key = key_kind(target)
            source_key = key_kind(source)
            return {
                "direction": direction,
                "source": f"{source['table']}.{source['column']}",
                "target": f"{target['table']}.{target['column']}",
                "source_key": source_key,
                "target_key": target_key,
                "target_is_unique": target_key != "NON_UNIQUE",
                "target_lookup_indexed": bool(target["lookup_indexed"]),
                "target_lookup_indexes": target["lookup_indexes"],
                "semantic_score": semantic_score,
                "semantic_support": semantic_support,
                "foreign_key_evidence": foreign_key_evidence(source, target),
                "relationship": "one-to-one" if source_key != "NON_UNIQUE" else "many-to-one",
            }

        direction_candidates = [
            build_direction(left, right, "left_to_right"),
            build_direction(right, left, "right_to_left"),
        ]
        key_rank = {"PRIMARY KEY": 0, "UNIQUE": 1, "DATA_UNIQUE": 2, "NON_UNIQUE": 3}
        viable_directions = [
            item
            for item in direction_candidates
            if item["foreign_key_evidence"] is not None or item["target_is_unique"]
        ]
        if viable_directions:
            viable_directions.sort(
                key=lambda item: (
                    0 if item["foreign_key_evidence"] is not None else 1,
                    key_rank[str(item["target_key"])],
                    0 if item["target_lookup_indexed"] else 1,
                    -int(item["semantic_score"]),
                    0 if item["direction"] == "left_to_right" else 1,
                )
            )
            best_direction = viable_directions[0]
        else:
            direction_candidates.sort(
                key=lambda item: (
                    0 if item["target_lookup_indexed"] else 1,
                    -int(item["semantic_score"]),
                    0 if item["direction"] == "left_to_right" else 1,
                )
            )
            best_direction = direction_candidates[0]
            warnings.append(
                "neither side is a declared or observed unique key; this may be a many-to-many/shared-domain overlap"
            )

        source_table, source_column = best_direction["source"].split(".", 1)
        target_table, target_column = best_direction["target"].split(".", 1)
        source_profile = left if best_direction["direction"] == "left_to_right" else right
        plan_rows = conn.execute(
            f"EXPLAIN QUERY PLAN SELECT 1 FROM {quote_ident(source_table)} AS s "
            f"WHERE s.{quote_ident(source_column)} IS NOT NULL AND EXISTS ("
            f"SELECT 1 FROM {quote_ident(target_table)} AS t "
            f"WHERE t.{quote_ident(target_column)} = s.{quote_ident(source_column)}) LIMIT 1"
        ).fetchall()
        plan_details = [str(row[3]) for row in plan_rows]
        target_lookup_uses_search = any("SEARCH t" in detail for detail in plan_details)
        target_lookup_scans = any("SCAN t" in detail for detail in plan_details)
        index_strategy = {
            "selected_direction": best_direction["direction"],
            "target_lookup_indexed": best_direction["target_lookup_indexed"],
            "target_lookup_uses_search": target_lookup_uses_search,
            "target_lookup_scans": target_lookup_scans,
            "query_plan": plan_details,
            "full_check_allowed": bool(
                best_direction["target_is_unique"]
                and best_direction["target_lookup_indexed"]
                and target_lookup_uses_search
                and not target_lookup_scans
            ),
        }

        metrics: dict[str, Any] = {
            "source_non_null_rows": source_profile["non_null_rows"],
            "source_distinct_values": source_profile["distinct_values"],
            "matched_rows": None,
            "matched_distinct_values": None,
            "source_value_containment": None,
            "source_row_match_rate": None,
            "parent_coverage": None,
            "parent_coverage_status": "not_computed_directional_not_required",
        }
        full_check: dict[str, Any] = {"attempted": False, "completed": False, "timed_out": False}
        sample_check: dict[str, Any] = {"attempted": False, "completed": False, "timed_out": False}
        verification_status = "unverified_low_confidence"
        confidence = "low"

        if index_strategy["full_check_allowed"]:
            full_check["attempted"] = True
            row, full_timed_out = query_one_with_budget(
                f"SELECT COUNT(s.{quote_ident(source_column)}), "
                f"COUNT(DISTINCT s.{quote_ident(source_column)}), "
                f"SUM(CASE WHEN t.{quote_ident(target_column)} IS NOT NULL THEN 1 ELSE 0 END), "
                f"COUNT(DISTINCT CASE WHEN t.{quote_ident(target_column)} IS NOT NULL "
                f"THEN s.{quote_ident(source_column)} END) "
                f"FROM {quote_ident(source_table)} AS s "
                f"LEFT JOIN {quote_ident(target_table)} AS t "
                f"ON t.{quote_ident(target_column)} = s.{quote_ident(source_column)} "
                f"WHERE s.{quote_ident(source_column)} IS NOT NULL",
                requested_seconds=JOIN_CANDIDATE_FULL_TIMEOUT_SECONDS,
            )
            full_check["timed_out"] = full_timed_out
            if not full_timed_out and row is not None:
                source_rows = int(row[0] or 0)
                source_distinct = int(row[1] or 0)
                matched_rows = int(row[2] or 0)
                matched_distinct = int(row[3] or 0)
                metrics.update(
                    {
                        "source_non_null_rows": source_rows,
                        "source_distinct_values": source_distinct,
                        "matched_rows": matched_rows,
                        "matched_distinct_values": matched_distinct,
                        "source_value_containment": round(
                            matched_distinct / source_distinct if source_distinct else 0.0,
                            6,
                        ),
                        "source_row_match_rate": round(
                            matched_rows / source_rows if source_rows else 0.0,
                            6,
                        ),
                    }
                )
                full_check["completed"] = True
                exact = source_distinct > 0 and matched_distinct == source_distinct and matched_rows == source_rows
                near = (
                    source_distinct > 0
                    and matched_distinct / source_distinct >= 0.95
                    and (matched_rows / source_rows if source_rows else 0.0) >= 0.95
                )
                if exact and type_compatible:
                    verification_status = "verified_full"
                    confidence = "high" if best_direction["target_key"] in {"PRIMARY KEY", "UNIQUE"} else "medium"
                elif near and type_compatible:
                    verification_status = "verified_full"
                    confidence = "medium"
                    warnings.append("some source values/rows do not find a counterpart on the selected parent key")
                elif source_rows == 0:
                    warnings.append("selected child column has no non-null rows; it cannot verify a join")
                else:
                    warnings.append("selected child values are not sufficiently contained in the proposed parent key")
            else:
                warnings.append(
                    f"full child-to-parent verification timed out after at most "
                    f"{min(JOIN_CANDIDATE_FULL_TIMEOUT_SECONDS, work_budget_seconds):.1f}s"
                )
        else:
            warnings.append(
                "full verification skipped because the selected parent lookup is not an indexed unique-key search"
            )

        should_sample = (
            not full_check["completed"]
            and best_direction["foreign_key_evidence"] is None
            and remaining_seconds() > 0
        )
        if should_sample:
            sample_check["attempted"] = True
            row, sample_timed_out = query_one_with_budget(
                f"WITH sample_keys AS ("
                f"SELECT DISTINCT s.{quote_ident(source_column)} AS value "
                f"FROM {quote_ident(source_table)} AS s "
                f"WHERE s.{quote_ident(source_column)} IS NOT NULL "
                f"LIMIT ?"
                f") "
                f"SELECT COUNT(*), SUM(CASE WHEN EXISTS ("
                f"SELECT 1 FROM {quote_ident(target_table)} AS t "
                f"WHERE t.{quote_ident(target_column)} = sample_keys.value"
                f") THEN 1 ELSE 0 END) FROM sample_keys",
                parameters=(JOIN_CANDIDATE_SAMPLE_DISTINCT_KEYS,),
                requested_seconds=JOIN_CANDIDATE_SAMPLE_TIMEOUT_SECONDS,
            )
            sample_check["timed_out"] = sample_timed_out
            sample_check["sample_limit"] = JOIN_CANDIDATE_SAMPLE_DISTINCT_KEYS
            if not sample_timed_out and row is not None:
                sample_distinct = int(row[0] or 0)
                sample_matched = int(row[1] or 0)
                sample_check.update(
                    {
                        "completed": True,
                        "sample_distinct_values": sample_distinct,
                        "sample_matched_values": sample_matched,
                        "sample_value_containment": round(
                            sample_matched / sample_distinct if sample_distinct else 0.0,
                            6,
                        ),
                    }
                )
                if (
                    sample_distinct >= 10
                    and sample_matched == sample_distinct
                    and best_direction["target_is_unique"]
                    and type_compatible
                    and int(best_direction["semantic_score"]) >= 2
                ):
                    verification_status = "verified_sampled"
                    confidence = "medium"
                    warnings.append(
                        "only a bounded sample was checked; use this join with more caution than verified_full"
                    )
                else:
                    warnings.append("bounded sample does not provide sufficient directional join evidence")
            else:
                warnings.append(
                    f"bounded sampled verification timed out after at most "
                    f"{min(JOIN_CANDIDATE_SAMPLE_TIMEOUT_SECONDS, work_budget_seconds):.1f}s"
                )

        if (
            best_direction["foreign_key_evidence"] is not None
            and not full_check["completed"]
            and type_compatible
        ):
            verification_status = "verified_metadata"
            confidence = "high"
            if best_direction["foreign_key_evidence"].get("implicit_parent_primary_key"):
                warnings.append(
                    "SQLite foreign-key metadata omits the parent column; resolved it to the parent's single primary key"
                )

        low_cardinality = min(
            value
            for value in (left["distinct_values"], right["distinct_values"])
            if isinstance(value, int)
        ) if all(isinstance(value, int) for value in (left["distinct_values"], right["distinct_values"])) else None
        if low_cardinality is not None and low_cardinality <= 5:
            warnings.append("low-cardinality overlap may be categorical coincidence")
            if confidence == "high" and best_direction["foreign_key_evidence"] is None:
                confidence = "medium"
        if not type_compatible:
            confidence = "low"
            if verification_status.startswith("verified_"):
                verification_status = "unverified_low_confidence"

        if full_check["timed_out"] and not sample_check["completed"] and best_direction["foreign_key_evidence"] is None:
            verification_status = "unverified_timeout"
        if confidence not in {"high", "medium"} and verification_status == "verified_full":
            verification_status = "unverified_low_confidence"

        join_condition = (
            f"{quote_ident(left_table)}.{quote_ident(left_column)} = "
            f"{quote_ident(right_table)}.{quote_ident(right_column)}"
        )
        verification = {
            "join_pair": f"{left_table}.{left_column} = {right_table}.{right_column}",
            "left": left,
            "right": right,
            "type_compatible": type_compatible,
            "verification_status": verification_status,
            "verification_budget_seconds": round(work_budget_seconds, 3),
            "metrics": metrics,
            "direction_candidates": direction_candidates,
            "best_direction": best_direction,
            "index_strategy": index_strategy,
            "full_check": full_check,
            "sample_check": sample_check,
            "inferred_relationship": (
                f"{best_direction['relationship']}: {best_direction['source']} -> {best_direction['target']}"
                if best_direction["target_is_unique"] or best_direction["foreign_key_evidence"] is not None
                else "no reliable key direction inferred"
            ),
            "confidence": confidence,
            "recommended_join_condition": join_condition if confidence in {"high", "medium"} else None,
            "join_condition": join_condition,
            "sample_common_values": [],
            "warnings": warnings,
        }
        rows = [
            ("join_pair", verification["join_pair"]),
            ("verification_status", verification_status),
            ("confidence", confidence),
            ("inferred_relationship", verification["inferred_relationship"]),
            ("selected_direction", best_direction["direction"]),
            ("index_strategy", "indexed_parent_lookup" if index_strategy["full_check_allowed"] else "bounded_fallback"),
            ("source_value_containment", metrics["source_value_containment"]),
            ("source_row_match_rate", metrics["source_row_match_rate"]),
            ("recommended_join_condition", verification["recommended_join_condition"]),
        ]
        return tool_result(
            ok=True,
            columns=["metric", "value"],
            rows=rows,
            elapsed=time.perf_counter() - started,
            extra={"join_verification": verification},
        )
    except Exception as exc:
        return tool_result(ok=False, error=str(exc), elapsed=time.perf_counter() - started)
    finally:
        try:
            conn.set_progress_handler(None, 0)
        except Exception:
            pass
        conn.close()


def format_join_candidate_observation(result: dict[str, Any], max_chars: int) -> str:
    """Return only the join evidence needed for the model's next decision."""
    del max_chars  # The fixed compact fields are already bounded.
    if not result.get("ok"):
        return f"Error: {result.get('error', 'unknown tool error')}"

    verification = result.get("join_verification") or {}
    best_direction = verification.get("best_direction") or {}
    metrics = verification.get("metrics") or {}
    sample_check = verification.get("sample_check") or {}
    confidence = str(verification.get("confidence") or "low")
    relationship = (
        best_direction.get("relationship")
        if confidence in {"high", "medium"}
        else "unknown"
    )
    value_containment = metrics.get("source_value_containment")
    if value_containment is None:
        value_containment = sample_check.get("sample_value_containment")

    def display(value: Any) -> str:
        if value is None:
            return "not_computed"
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    lines = [
        f"tested_direction={display(best_direction.get('source'))} -> {display(best_direction.get('target'))}",
        f"status={display(verification.get('verification_status'))}",
        f"relationship={display(relationship)}",
        f"confidence={confidence}",
        f"parent_key={display(best_direction.get('target_key'))}",
        f"value_containment={display(value_containment)}",
        f"row_match_rate={display(metrics.get('source_row_match_rate'))}",
        f"recommended_join={display(verification.get('recommended_join_condition'))}",
    ]
    warnings = " ".join(str(item).lower() for item in verification.get("warnings") or [])
    cautions: list[str] = []
    status = str(verification.get("verification_status") or "")
    if status == "verified_sampled":
        cautions.append("sample_only")
    if status == "unverified_timeout":
        cautions.append("timeout")
    if not verification.get("type_compatible", True):
        cautions.append("type_mismatch")
    if "low-cardinality" in warnings:
        cautions.append("low_cardinality_overlap")
    if "some source values/rows" in warnings:
        cautions.append("partial_containment")
    if confidence == "low" and status != "unverified_timeout":
        cautions.append("insufficient_evidence")
    if cautions:
        lines.append(f"caution={','.join(dict.fromkeys(cautions))}")
    return "\n".join(lines)


def format_inspect_rows_observation(result: dict[str, Any], max_chars: int) -> str:
    """Return compact tab-separated fields and raw matching rows."""
    del max_chars  # inspect_rows already enforces row and column limits.
    if not result.get("ok"):
        return f"Error: {result.get('error', 'unknown tool error')}"

    lines = ["\t".join(str(column) for column in result.get("columns") or [])]
    for row in rows_to_jsonable(result.get("rows") or []):
        lines.append("\t".join("NULL" if value is None else str(value) for value in row))
    return "\n".join(lines)


def format_table_name_observation(result: dict[str, Any], max_chars: int) -> str:
    """Return exactly the raw SQLite table names, one per line."""
    del max_chars  # The complete table list is an explicit tool contract.
    if not result.get("ok"):
        return f"Error: {result.get('error', 'unknown tool error')}"
    return "\n".join(str(table) for table in result.get("tables") or [])


def format_table_metadata_observation(result: dict[str, Any], max_chars: int) -> str:
    """Return exactly the raw CREATE TABLE DDL stored by SQLite."""
    del max_chars  # Complete DDL is an explicit contract and must not be truncated.
    if not result.get("ok"):
        return f"Error: {result.get('error', 'unknown tool error')}"
    return str(result.get("ddl") or "")


def format_inspect_value_observation(result: dict[str, Any], max_chars: int) -> str:
    """Return exactly the selected distinct values, one per line."""
    del max_chars  # The SQL-level limit already bounds this tool's result.
    if not result.get("ok"):
        return f"Error: {result.get('error', 'unknown tool error')}"
    values = rows_to_jsonable([(value,) for value in result.get("values") or []])
    return "\n".join("NULL" if row[0] is None else str(row[0]) for row in values)


def format_foreign_key_observation(result: dict[str, Any], max_chars: int) -> str:
    """Return only concise child-to-parent join relationships."""
    del max_chars  # Declared relationships should be returned completely.
    if not result.get("ok"):
        return f"Error: {result.get('error', 'unknown tool error')}"
    foreign_keys = result.get("foreign_keys") or []
    if not foreign_keys:
        return "NO DECLARED FOREIGN KEYS"
    return "\n".join(
        f"{child_table}.{child_column} -> {parent_table}.{parent_column}"
        for child_table, child_column, parent_table, parent_column in foreign_keys
    )


def format_sql_execution_observation(result: dict[str, Any], max_chars: int) -> str:
    """Return only the SQL error or the raw tabular result needed by the agent."""
    if not result.get("ok"):
        text = f"Error: {result.get('error', 'unknown SQL execution error')}"
        return text[:max_chars]

    columns = [str(column) for column in result.get("columns") or []]
    rows = rows_to_jsonable(result.get("rows") or [])
    if not columns:
        text = "OK"
    else:
        lines = ["\t".join(columns)]
        lines.extend(
            "\t".join("NULL" if value is None else str(value) for value in row)
            for row in rows
        )
        if not rows:
            lines.append("NO ROWS")
        if result.get("truncated"):
            lines.append("...")
        text = "\n".join(lines)
    if len(text) > max_chars:
        return text[:max_chars] + "\n..."
    return text


def parse_tool_call(text: str) -> tuple[dict[str, Any] | None, str | None]:
    match = TOOL_CALL_RE.search(text or "")
    if not match:
        return None, "missing <tool_call>...</tool_call>"
    raw = match.group(1).strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"tool_call must be valid JSON: {exc}"
    if not isinstance(payload, dict):
        return None, "tool_call must be a JSON object"
    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        return None, "tool_call.name must be a non-empty string"
    arguments = payload.get("arguments")
    if not isinstance(arguments, dict):
        return None, "tool_call.arguments must be a JSON object"
    return {"name": name.strip(), "arguments": arguments}, None


def validate_db_id(tool_call: dict[str, Any], db_id: str) -> str | None:
    args = tool_call.get("arguments") or {}
    call_db_id = args.get("db_id", db_id)
    if call_db_id != db_id:
        return f"tool_call db_id must be {db_id!r}, got {call_db_id!r}"
    args["db_id"] = db_id
    tool_call["arguments"] = args
    return None


def validate_schema_termination(payload: dict[str, Any]) -> str | None:
    required = {
        "tables": list,
        "columns": dict,
        "joins": list,
        "value_constraints": list,
        "unresolved": list,
    }
    for key, typ in required.items():
        if key not in payload:
            return f"terminate_first_stage missing key {key!r}"
        if not isinstance(payload[key], typ):
            return f"terminate_first_stage key {key!r} must be {typ.__name__}"
    if not payload["tables"]:
        return "terminate_first_stage tables must be non-empty list"

    table_names: set[str] = set()
    submitted_columns: dict[str, set[str]] = {}
    for table_index, table in enumerate(payload["tables"]):
        if not isinstance(table, str) or not table.strip():
            return f"terminate_first_stage tables[{table_index}] must be non-empty string"
        table_name = table.strip()
        if table_name in table_names:
            return f"terminate_first_stage contains duplicate table {table_name!r}"
        table_names.add(table_name)

    unknown_column_tables = set(payload["columns"]) - table_names
    if unknown_column_tables:
        unknown = sorted(unknown_column_tables)[0]
        return f"terminate_first_stage columns references unsubmitted table {unknown!r}"

    for table_name in table_names:
        columns = payload["columns"].get(table_name)
        if not isinstance(columns, list) or not columns:
            return f"terminate_first_stage columns[{table_name!r}] must be non-empty list"

        column_names: set[str] = set()
        for column_index, column in enumerate(columns):
            path = f"columns[{table_name!r}][{column_index}]"
            if not isinstance(column, str) or not column.strip():
                return f"terminate_first_stage {path} must be non-empty string"
            column_name = column.strip()
            if column_name in column_names:
                return f"terminate_first_stage contains duplicate column {table_name}.{column_name}"
            column_names.add(column_name)
        submitted_columns[table_name] = column_names

    for join_index, join in enumerate(payload["joins"]):
        path = f"joins[{join_index}]"
        if not isinstance(join, dict):
            return f"terminate_first_stage {path} must be object"
        for key in ("left", "right"):
            value = join.get(key)
            if not isinstance(value, str) or not value.strip():
                return f"terminate_first_stage {path}.{key} must be non-empty string"
            qualified_column = value.strip()
            if "." not in qualified_column:
                return f"terminate_first_stage {path}.{key} must be table.column"
            table_name, column_name = qualified_column.rsplit(".", 1)
            if table_name not in table_names:
                return f"terminate_first_stage {path}.{key} references unsubmitted table {table_name!r}"
            if column_name not in submitted_columns[table_name]:
                return (
                    f"terminate_first_stage {path}.{key} references unsubmitted column "
                    f"{table_name}.{column_name}"
                )

    for constraint_index, constraint in enumerate(payload["value_constraints"]):
        path = f"value_constraints[{constraint_index}]"
        if not isinstance(constraint, dict):
            return f"terminate_first_stage {path} must be object"
        table_name = constraint.get("table")
        column_name = constraint.get("column")
        values = constraint.get("values")
        if not isinstance(table_name, str) or not table_name.strip():
            return f"terminate_first_stage {path}.table must be non-empty string"
        if not isinstance(column_name, str) or not column_name.strip():
            return f"terminate_first_stage {path}.column must be non-empty string"
        table_name = table_name.strip()
        column_name = column_name.strip()
        if table_name not in table_names:
            return f"terminate_first_stage {path}.table references unsubmitted table {table_name!r}"
        if column_name not in submitted_columns[table_name]:
            return (
                f"terminate_first_stage {path}.column references unsubmitted column "
                f"{table_name}.{column_name}"
            )
        if not isinstance(values, list) or not values:
            return f"terminate_first_stage {path}.values must be non-empty list"
    return None


def normalize_schema_termination(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep only the canonical stage-one schema submission fields."""
    return {
        "tables": [table.strip() for table in payload["tables"]],
        "columns": {
            table.strip(): [column.strip() for column in payload["columns"][table.strip()]]
            for table in payload["tables"]
        },
        "joins": [
            {
                "left": join["left"].strip(),
                "right": join["right"].strip(),
            }
            for join in payload["joins"]
        ],
        "value_constraints": [
            {
                "table": constraint["table"].strip(),
                "column": constraint["column"].strip(),
                "values": constraint["values"],
            }
            for constraint in payload["value_constraints"]
        ],
        "unresolved": payload["unresolved"],
    }


def allowed_tools_for_stage(stage: str, stage_remaining: int | None = None) -> set[str]:
    if stage == SCHEMA_STAGE and stage_remaining == 1:
        return {"terminate_first_stage"}
    if stage == SQL_STAGE and stage_remaining == 1:
        return {"terminate_second_stage"}
    if stage == SCHEMA_STAGE:
        return SCHEMA_TOOLS
    if stage == SQL_STAGE:
        return SQL_TOOLS
    return set()


def build_invalid_feedback(stage: str, error: str) -> str:
    return build_invalid_feedback_with_allowed(
        stage,
        error,
        sorted(allowed_tools_for_stage(stage)),
    )


def build_invalid_feedback_with_allowed(stage: str, error: str, allowed: list[str]) -> str:
    return (
        f"Invalid tool call: {error}\n"
        f"Current stage: {stage}\n"
        f"Allowed tools: {', '.join(allowed)}\n"
        "Respond again using exactly:\n"
        '<think>brief reasoning</think>\n'
        '<tool_call>{"name": "TOOL_NAME", "arguments": {...}}</tool_call>'
    )


def build_legacy_terminate_feedback(stage: str) -> str:
    if stage == SCHEMA_STAGE:
        expected = "terminate_first_stage"
    elif stage == SQL_STAGE:
        expected = "terminate_second_stage"
    else:
        expected = "the current stage's termination tool"
    return (
        "Invalid tool call: terminate_stage is no longer supported.\n"
        f"Current stage: {stage}\n"
        f"Use {expected} for this stage.\n"
        "Respond again using exactly:\n"
        "<think>brief reasoning</think>\n"
        f'<tool_call>{{"name": "{expected}", "arguments": {{...}}}}</tool_call>'
    )


def strip_memory_response(text: str) -> str:
    text = THINK_TAG_RE.sub("", text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:text|markdown)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


MEMORY_ITEM_RE = re.compile(r"(?m)^\s*(\d+)\.\s+")


def memory_item_numbers(text: str) -> list[int]:
    return [int(match.group(1)) for match in MEMORY_ITEM_RE.finditer(text or "")]


def next_memory_number(memory: str) -> int:
    numbers = memory_item_numbers(memory)
    return numbers[-1] + 1 if numbers else 1


def validate_memory_delta(text: str, expected_start: int, round_number: int) -> str | None:
    if not text.strip():
        return "memory compressor returned empty delta"
    numbers = memory_item_numbers(text)
    if not numbers:
        return "memory compressor delta must contain numbered items like '7. ...'"
    if len(numbers) != 1:
        return "memory compressor must output exactly one numbered item for the latest round"
    if numbers[0] != expected_start:
        return (
            f"memory compressor delta must start at {expected_start}, "
            f"but started at {numbers[0]}"
        )
    first_line = text.strip().splitlines()[0]
    if not re.match(rf"^\s*{expected_start}\.\s*Round\s+{round_number}\b", first_line, flags=re.IGNORECASE):
        return f"memory item must explicitly start with '{expected_start}. Round {round_number}'"
    if " | Action: " not in first_line:
        return "memory item must include ' | Action: ' followed by the full action call"
    if " | Useful memory: " not in first_line:
        return "memory item must include ' | Useful memory: ' followed by compressed useful information"
    return None


def append_memory_delta(memory_before: str, memory_delta: str) -> str:
    memory_before = (memory_before or "").rstrip()
    memory_delta = memory_delta.strip()
    if not memory_before:
        return memory_delta
    return f"{memory_before}\n{memory_delta}"


def build_memory_prompt(
    *,
    sample: dict[str, Any],
    stage: str,
    round_number: int,
    memory_before: str,
    think: str,
    tool_call: dict[str, Any] | None,
    observation: str,
) -> str:
    action_name = tool_call["name"] if tool_call else "system_feedback"
    action_args = tool_call.get("arguments", {}) if tool_call else {}
    action_repr = f"{action_name}({json.dumps(action_args, ensure_ascii=False, default=str)})"
    next_number = next_memory_number(memory_before)
    expected_format = (
        f'{next_number}. Round {round_number} | Action: {action_repr} | '
        "Useful memory: ..."
    )
    return f"""You are solving a Text-to-SQL task. Based on the current question,
external evidence, existing working memory, the latest assistant reasoning, the
latest tool call, and the tool observation, summarize only the new useful
information obtained in this round.

The goal of this memory delta is to preserve information that may help generate
the final correct SQL query while removing irrelevant details.

Use the latest assistant <think> reasoning to understand why this action was
executed and what question, hypothesis, or uncertainty it was meant to resolve.
Then compress the memory around that purpose: keep the observation details that
answer the action's reason, record failed assumptions when the observation
contradicts the reasoning, and omit details that are unrelated to the action's
purpose. Do not summarize casually.

Important:
- Existing memory is immutable. Do not repeat it, rewrite it, delete it, or
  renumber it.
- Output exactly one new memory item for this latest round.
- The item must explicitly include the current round marker: Round {round_number}.
- The item must include the executed action with complete arguments copied from
  the latest tool call. Do not omit parameters, abbreviate SQL, or use "...".
- The item must then include compressed useful information targeted to why this
  action was executed.
- The item must follow this exact shape:
  {expected_format}

Current natural-language question:
{sample.get("question", "")}

External evidence:
{sample.get("evidence", "")}

Current stage:
{stage}

Current round:
Round {round_number}

Existing memory:
{memory_before or "Empty"}

Latest assistant <think> reasoning:
{think or "Empty"}

Latest tool call:
{action_repr}

Tool observation:
{observation}

Output only the single new memory delta item:"""


def compress_memory(
    client: httpx.Client,
    *,
    sample: dict[str, Any],
    stage: str,
    round_number: int,
    memory_before: str,
    think: str,
    tool_call: dict[str, Any] | None,
    observation: str,
    args: argparse.Namespace,
) -> tuple[str, str | None, float, str]:
    expected_start = next_memory_number(memory_before)
    messages = [
        {"role": "system", "content": MEMORY_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": build_memory_prompt(
                sample=sample,
                stage=stage,
                round_number=round_number,
                memory_before=memory_before,
                think=think,
                tool_call=tool_call,
                observation=observation,
            ),
        },
    ]
    last_error: str | None = None
    total_latency = 0.0
    for attempt in range(args.memory_retries + 1):
        try:
            content, _, latency = call_model(
                client,
                base_url=args.base_url,
                api_key=args.api_key,
                model=args.model,
                messages=messages,
                max_tokens=args.memory_max_tokens,
                temperature=args.memory_temperature,
                top_p=args.memory_top_p,
                llm_retries=0,
                retry_sleep=args.retry_sleep,
                enable_thinking=args.memory_enable_thinking,
            )
            total_latency += latency
            memory_delta = strip_memory_response(content)
            error = validate_memory_delta(memory_delta, expected_start, round_number)
            if error:
                raise ValueError(error)
            memory_after = append_memory_delta(memory_before, memory_delta)
            return memory_after, None, total_latency, memory_delta
        except Exception as exc:
            last_error = str(exc)
            if attempt < args.memory_retries:
                messages.append(
                    {
                        "role": "assistant",
                        "content": strip_memory_response(locals().get("content", "")),
                    }
                )
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Invalid memory delta: {last_error}\n"
                            f"Output exactly one memory item starting with '{expected_start}. Round {round_number}'. "
                            "Include ' | Action: ' with the complete action arguments and ' | Useful memory: '. "
                            "Do not repeat existing memory."
                        ),
                    }
                )
                time.sleep(args.retry_sleep)
    return memory_before, last_error, total_latency, ""


def build_agent_user_message(
    *,
    sample: dict[str, Any],
    stage: str,
    memory: str,
    last_observation: str,
    format_error_feedback: str,
    sql_execution_error_feedback: str,
    total_remaining: int,
    stage_remaining: int,
    returns_remaining: int,
    schema_evidence: dict[str, Any] | None,
    successful_candidates: list[dict[str, Any]],
) -> str:
    allowed = sorted(allowed_tools_for_stage(stage, stage_remaining))
    evidence = (sample.get("evidence") or "").strip()
    schema_text = json.dumps(schema_evidence or {}, ensure_ascii=False, indent=2, default=str)
    final_schema_round_note = ""
    if stage == SCHEMA_STAGE and stage_remaining == 1:
        final_schema_round_note = (
            "\n# Final Schema Round Constraint\n"
            "This is the last available schema_exploration round. The only "
            "allowed tool is terminate_first_stage. Submit the best verified "
            "schema evidence now and omit uncertain guesses.\n"
        )
    final_sql_round_note = ""
    if stage == SQL_STAGE and stage_remaining == 1:
        final_sql_round_note = (
            "\n# Final SQL Round Constraint\n"
            "This is the last available sql_generation round. The only allowed "
            "tool is terminate_second_stage. Submit the immediately previous "
            "successful execute_sql candidate now without rewriting SQL.\n"
        )
    elif stage == SQL_STAGE and stage_remaining == 2:
        final_sql_round_note = (
            "\n# Penultimate SQL Round Constraint\n"
            "This is the last round in which you can execute a final SQL candidate. "
            "If the immediately previous execute_sql already succeeded and satisfies "
            "the question, call terminate_second_stage now. Otherwise call execute_sql "
            "with your best complete final SQL now, because the next and final round "
            "will allow only terminate_second_stage.\n"
        )
    format_error_note = ""
    if format_error_feedback:
        format_error_note = (
            "\n# Previous Round Format Error\n"
            "The previous response could not be parsed. Use the exact error feedback below to "
            "correct the response format in this round:\n"
            f"{format_error_feedback}\n"
        )
    sql_execution_error_note = ""
    if sql_execution_error_feedback:
        sql_execution_error_note = (
            "\n# Previous SQL Execution Error\n"
            "The SQL tool call in the previous round failed. Use the exact database error below "
            "to correct the next SQL attempt:\n"
            f"{sql_execution_error_feedback}\n"
        )
    return f"""# Task
Database: {sample["db_id"]}
Question: {sample["question"]}
External evidence: {evidence or "None"}

# Current State
Current stage: {stage}
Allowed tools in this stage: {", ".join(allowed)}
Remaining total model rounds: {total_remaining}
Remaining rounds for current stage: {stage_remaining}
Remaining schema return budget: {returns_remaining}

# Schema Evidence Submitted By Stage 1
{schema_text}
{final_schema_round_note}
{final_sql_round_note}

# Working Memory m_t
{memory or "空"}
{format_error_note}
{sql_execution_error_note}

Now choose exactly one allowed tool for the current stage."""


def build_agent_messages(**kwargs: Any) -> list[dict[str, str]]:
    stage = kwargs.get("stage")
    stage_remaining = kwargs.get("stage_remaining")
    if stage == SCHEMA_STAGE and stage_remaining == 1:
        system_prompt = FINAL_SCHEMA_TERMINATION_SYSTEM_PROMPT
    elif stage == SCHEMA_STAGE:
        system_prompt = SCHEMA_AGENT_SYSTEM_PROMPT
    elif stage == SQL_STAGE and stage_remaining == 1:
        system_prompt = FINAL_SQL_TERMINATION_SYSTEM_PROMPT
    elif stage == SQL_STAGE:
        system_prompt = SQL_AGENT_SYSTEM_PROMPT
    else:
        raise ValueError(f"unsupported agent stage for prompt selection: {stage!r}")
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": build_agent_user_message(**kwargs)},
    ]


def execute_twostage_tool(
    *,
    db_path: Path,
    db_id: str,
    stage: str,
    tool_call: dict[str, Any],
    args: argparse.Namespace,
    successful_candidates: list[dict[str, Any]],
    verified_join_pairs: set[tuple[tuple[str, str], tuple[str, str]]],
) -> tuple[dict[str, Any] | None, str, dict[str, Any] | None]:
    error = validate_db_id(tool_call, db_id)
    if error:
        result = tool_result(ok=False, error=error)
        return result, f"Error: {error}", None

    name = tool_call["name"]
    tool_args = tool_call["arguments"]
    executed_sql: str | None = None
    verified_join_pair_event: dict[str, str] | None = None
    try:
        if name == "list_table_name":
            result = run_list_table_name(db_path, tool_args)
        elif name == "get_table_metadata":
            result = run_get_table_metadata(db_path, tool_args)
        elif name == "inspect_value":
            result = run_inspect_value(db_path, tool_args, args.tool_max_rows)
        elif name == "inspect_rows":
            result = run_inspect_rows(
                db_path,
                tool_args,
                args.tool_max_rows,
                verified_join_pairs,
            )
        elif name == "inspect_foreign_key":
            result = run_inspect_foreign_key(db_path, tool_args)
        elif name == "inspect_join_candidate":
            result = run_inspect_join_candidate(db_path, tool_args, args.tool_max_rows, args.sql_timeout)
            verification = result.get("join_verification") or {}
            if result.get("ok") and verification.get("confidence") in {"high", "medium"}:
                left_table = tool_args.get("left_table")
                left_column = tool_args.get("left_column")
                right_table = tool_args.get("right_table")
                right_column = tool_args.get("right_column")
                if all(
                    isinstance(value, str) and value.strip()
                    for value in (left_table, left_column, right_table, right_column)
                ):
                    join_pair = canonical_join_pair(
                        left_table.strip(),
                        left_column.strip(),
                        right_table.strip(),
                        right_column.strip(),
                    )
                    verified_join_pairs.add(join_pair)
                    verified_join_pair_event = {
                        "left": f"{left_table.strip()}.{left_column.strip()}",
                        "right": f"{right_table.strip()}.{right_column.strip()}",
                        "confidence": str(verification.get("confidence")),
                    }
        elif name == "execute_sub_sql":
            sql = extract_sql(str(tool_args.get("sql", "")))
            if not sql:
                result = tool_result(ok=False, error="execute_sub_sql requires a non-empty sql string")
            elif is_metadata_query(sql):
                result = tool_result(
                    ok=False,
                    error=(
                        "execute_sub_sql is for semantic sub-questions, not schema inspection. "
                        "Do not use PRAGMA, table_info, sqlite_master, or sqlite_schema in sql_generation. "
                        "Use return_to_schema_stage if schema evidence is insufficient."
                    ),
                )
            else:
                result = execute_twostage_sql(db_path, sql, timeout_s=args.sql_timeout, max_rows=args.tool_max_rows)
                executed_sql = sql
        elif name == "execute_sql":
            sql = extract_sql(str(tool_args.get("sql", "")))
            if not sql:
                result = tool_result(ok=False, error="execute_sql requires a non-empty sql string")
            else:
                result = execute_twostage_sql(db_path, sql, timeout_s=args.sql_timeout, max_rows=args.tool_max_rows)
                executed_sql = sql
                if result.get("ok"):
                    candidate = {
                        "sql": sql,
                        "sql_key": normalize_sql_key(sql),
                        "columns": result.get("columns") or [],
                        "rows_preview": result.get("rows") or [],
                        "truncated": result.get("truncated", False),
                    }
                    successful_candidates.append(candidate)
        else:
            result = tool_result(ok=False, error=f"unsupported tool: {name}")
    except Exception as exc:
        result = tool_result(ok=False, error=str(exc))

    if name == "list_table_name":
        observation = format_table_name_observation(result, args.max_observation_chars)
    elif name == "get_table_metadata":
        observation = format_table_metadata_observation(result, args.max_observation_chars)
    elif name == "inspect_value":
        observation = format_inspect_value_observation(result, args.max_observation_chars)
    elif name == "inspect_rows":
        observation = format_inspect_rows_observation(result, args.max_observation_chars)
    elif name == "inspect_foreign_key":
        observation = format_foreign_key_observation(result, args.max_observation_chars)
    elif name == "inspect_join_candidate":
        observation = format_join_candidate_observation(result, args.max_observation_chars)
    elif name in {"execute_sub_sql", "execute_sql"}:
        observation = format_sql_execution_observation(result, args.max_observation_chars)
    else:
        observation = format_tool_result(result, args.max_observation_chars)
    structured_event: dict[str, Any] | None = None
    if name == "execute_sql" and result.get("ok"):
        structured_event = {"candidate_sql": executed_sql}
    elif verified_join_pair_event:
        structured_event = {"verified_join_pair": verified_join_pair_event}
    return result, observation, structured_event


def previous_round_successful_execute_sql(rounds: list[dict[str, Any]]) -> str | None:
    if not rounds:
        return None
    previous = rounds[-1]
    tool_call = previous.get("tool_call") or {}
    if tool_call.get("name") != "execute_sql":
        return None
    return extract_sql(str(previous.get("candidate_sql") or "")) or None


def stage_limit(stage: str, schema_limit: int, args: argparse.Namespace) -> int:
    return schema_limit if stage == SCHEMA_STAGE else args.sql_max_rounds


def stage_used(stage: str, schema_rounds_used: int, sql_rounds_used: int) -> int:
    return schema_rounds_used if stage == SCHEMA_STAGE else sql_rounds_used


def extend_total_budget_for_schema_return(
    current_total_budget: int,
    total_budget_cap: int,
    requested_schema_rounds: int,
) -> tuple[int, int]:
    """Grant schema-return rounds without taking them from the SQL-stage budget."""
    available = max(0, total_budget_cap - current_total_budget)
    granted = min(max(0, requested_schema_rounds), available)
    return current_total_budget + granted, granted


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def git_capture(repo_dir: Path, git_args: list[str], *, timeout: float = 30.0) -> dict[str, Any]:
    command = ["git", "-C", str(repo_dir), *git_args]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    except Exception as exc:
        return {"command": command, "returncode": None, "stdout": "", "stderr": str(exc)}


def artifact_path(out_dir: Path, filename: str, timestamp: str) -> Path:
    path = out_dir / filename
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    return out_dir / f"{stem}.{timestamp}{suffix}"


def save_reproducibility_artifacts(out_dir: Path, script_path: Path, repo_dir: Path) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    source_path = artifact_path(out_dir, "runner_source_snapshot.py", timestamp)
    git_status_path = artifact_path(out_dir, "git_status.txt", timestamp)
    git_head_path = artifact_path(out_dir, "git_head.txt", timestamp)
    git_diff_path = artifact_path(out_dir, "git_diff.patch", timestamp)
    manifest_path = artifact_path(out_dir, "run_repro_manifest.json", timestamp)

    source_path.write_text(script_path.read_text(encoding="utf-8"), encoding="utf-8")

    status = git_capture(repo_dir, ["status", "--short", "--branch", "--untracked-files=normal"])
    head = git_capture(repo_dir, ["rev-parse", "HEAD"])
    branch = git_capture(repo_dir, ["branch", "--show-current"])
    diff = git_capture(repo_dir, ["diff", "--", "."])
    cached_diff = git_capture(repo_dir, ["diff", "--cached", "--", "."])

    git_status_path.write_text(
        "$ git status --short --branch --untracked-files=normal\n"
        + status["stdout"]
        + ("\n# stderr\n" + status["stderr"] if status["stderr"] else ""),
        encoding="utf-8",
    )
    git_head_path.write_text(
        "$ git rev-parse HEAD\n"
        + head["stdout"]
        + ("\n# stderr\n" + head["stderr"] if head["stderr"] else "")
        + "\n$ git branch --show-current\n"
        + branch["stdout"]
        + ("\n# stderr\n" + branch["stderr"] if branch["stderr"] else ""),
        encoding="utf-8",
    )
    git_diff_path.write_text(
        "# git diff -- .\n"
        + diff["stdout"]
        + ("\n# stderr\n" + diff["stderr"] if diff["stderr"] else "")
        + "\n\n# git diff --cached -- .\n"
        + cached_diff["stdout"]
        + ("\n# stderr\n" + cached_diff["stderr"] if cached_diff["stderr"] else ""),
        encoding="utf-8",
    )

    manifest = {
        "created_at_utc": timestamp,
        "argv": sys.argv,
        "script_path": str(script_path),
        "repo_dir": str(repo_dir),
        "runner_source_snapshot_path": str(source_path),
        "git_status_path": str(git_status_path),
        "git_head_path": str(git_head_path),
        "git_diff_path": str(git_diff_path),
        "git_status_returncode": status["returncode"],
        "git_head_returncode": head["returncode"],
        "git_diff_returncode": diff["returncode"],
        "git_cached_diff_returncode": cached_diff["returncode"],
        "note": (
            "Untracked files are listed in git_status.txt and preserved via "
            "runner_source_snapshot.py; git diff does not include untracked file contents."
        ),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def load_completed(episodes_path: Path, evaluation_mode: str) -> tuple[set[str], int, int]:
    completed: set[str] = set()
    correct = 0
    total = 0
    if not episodes_path.exists():
        return completed, correct, total
    with episodes_path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            record = json.loads(line)
            qid = str(record["question_id"])
            completed.add(qid)
            if evaluation_mode == "strict":
                correct += int(record.get("strict_correct", record.get("correct", 0)))
            else:
                correct += int(record.get("projection_relaxed_correct", record.get("correct", 0)))
            total += 1
    return completed, correct, total


def load_episodes(episodes_path: Path) -> list[dict[str, Any]]:
    if not episodes_path.exists():
        return []
    episodes = []
    with episodes_path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                episodes.append(json.loads(line))
    return episodes


def run_twostage_episode(
    client: httpx.Client,
    sample: dict[str, Any],
    db_root: Path,
    args: argparse.Namespace,
) -> dict[str, Any]:
    db_id = sample["db_id"]
    db_path = find_db_path(db_root, db_id)
    stage = SCHEMA_STAGE
    schema_limit_current = args.schema_max_rounds
    effective_max_rounds = args.max_rounds
    total_budget_extensions: list[dict[str, Any]] = []
    schema_rounds_used = 0
    sql_rounds_used = 0
    returns_used = 0
    memory = ""
    last_observation = ""
    last_format_error_feedback = ""
    last_sql_execution_error_feedback = ""
    schema_evidence: dict[str, Any] | None = None
    successful_candidates: list[dict[str, Any]] = []
    verified_join_pairs: set[tuple[tuple[str, str], tuple[str, str]]] = set()
    stage_transitions: list[dict[str, Any]] = []
    rounds: list[dict[str, Any]] = []
    pred_sql = ""
    terminated = False
    used_fallback_sql = False
    auto_stage_transition = False
    sql_stage_budget_exhausted = False
    total_agent_latency = 0.0
    total_memory_latency = 0.0

    round_idx = 0
    while round_idx < effective_max_rounds and stage != DONE_STAGE:
        if stage == SCHEMA_STAGE and schema_rounds_used >= schema_limit_current:
            previous = stage
            stage = SQL_STAGE
            auto_stage_transition = True
            event = {
                "from": previous,
                "to": stage,
                "round_before": round_idx + 1,
                "reason": "schema stage budget exhausted",
                "auto_stage_transition": True,
            }
            stage_transitions.append(event)
            last_observation = (
                "Schema stage budget exhausted. The environment automatically moved to sql_generation. "
                "Use the working memory and any submitted schema evidence to produce and validate SQL."
            )
        if stage == SQL_STAGE and sql_rounds_used >= args.sql_max_rounds:
            sql_stage_budget_exhausted = True
            last_observation = (
                "SQL stage budget exhausted. The environment stopped model interaction and will use fallback "
                "to the latest successful execute_sql candidate if available."
            )
            break

        current_stage_used = stage_used(stage, schema_rounds_used, sql_rounds_used)
        current_stage_limit = stage_limit(stage, schema_limit_current, args)
        stage_remaining = max(0, current_stage_limit - current_stage_used)
        round_allowed_tools = sorted(allowed_tools_for_stage(stage, stage_remaining))
        schema_final_round_only_terminate = (
            stage == SCHEMA_STAGE and round_allowed_tools == ["terminate_first_stage"]
        )
        sql_final_round_only_terminate = (
            stage == SQL_STAGE and round_allowed_tools == ["terminate_second_stage"]
        )
        messages = build_agent_messages(
            sample=sample,
            stage=stage,
            memory=memory,
            last_observation=last_observation,
            format_error_feedback=last_format_error_feedback,
            sql_execution_error_feedback=last_sql_execution_error_feedback,
            total_remaining=effective_max_rounds - round_idx,
            stage_remaining=stage_remaining,
            returns_remaining=max(0, args.max_stage_returns - returns_used),
            schema_evidence=schema_evidence,
            successful_candidates=successful_candidates,
        )

        assistant_text, reasoning_content, latency = call_model(
            client,
            base_url=args.base_url,
            api_key=args.api_key,
            model=args.model,
            messages=messages,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            top_p=args.top_p,
            llm_retries=args.llm_retries,
            retry_sleep=args.retry_sleep,
            enable_thinking=args.enable_thinking,
        )
        total_agent_latency += latency
        round_idx += 1
        if stage == SCHEMA_STAGE:
            schema_rounds_used += 1
        elif stage == SQL_STAGE:
            sql_rounds_used += 1

        memory_before = memory
        think = extract_think(assistant_text, reasoning_content)
        tool_call, parse_error = parse_tool_call(assistant_text)
        round_record: dict[str, Any] = {
            "round": round_idx,
            "stage": stage,
            "think": think,
            "tool_call": tool_call,
            "observation": None,
            "tool_result": None,
            "memory_before": memory_before,
            "memory_delta": None,
            "memory_after": None,
            "compressor_error": None,
            "format_error_feedback": last_format_error_feedback or None,
            "sql_execution_error_feedback": last_sql_execution_error_feedback or None,
            "allowed_tools": round_allowed_tools,
            "schema_final_round_only_terminate": schema_final_round_only_terminate,
            "sql_final_round_only_terminate": sql_final_round_only_terminate,
            "debug": {"raw_message": assistant_text},
            "latency": latency,
        }
        if reasoning_content:
            round_record["debug"]["reasoning_content"] = reasoning_content

        observation: str
        active_tool_call: dict[str, Any] | None = tool_call
        tool_result_obj: dict[str, Any] | None = None
        if parse_error:
            observation = build_invalid_feedback_with_allowed(stage, parse_error, round_allowed_tools)
            round_record["error"] = parse_error
            active_tool_call = {"name": "format_error", "arguments": {"error": parse_error}}
        elif tool_call is None:
            observation = build_invalid_feedback_with_allowed(stage, "missing tool_call", round_allowed_tools)
            round_record["error"] = "missing tool_call"
            active_tool_call = {"name": "format_error", "arguments": {"error": "missing tool_call"}}
        else:
            tool_name = tool_call["name"]
            if tool_name == "terminate_stage":
                observation = build_legacy_terminate_feedback(stage)
                round_record["error"] = "legacy_terminate_stage_not_supported"
                round_record["stage_violation"] = True
                active_tool_call = {
                    "name": "legacy_terminate_stage",
                    "arguments": {"requested_tool": tool_name, "stage": stage},
                }
            elif tool_name not in round_allowed_tools:
                observation = build_invalid_feedback_with_allowed(
                    stage,
                    f"tool {tool_name!r} is not allowed in stage {stage}",
                    round_allowed_tools,
                )
                round_record["stage_violation"] = True
                active_tool_call = {
                    "name": "stage_violation",
                    "arguments": {"requested_tool": tool_name, "stage": stage},
                }
            elif tool_name == "terminate_first_stage" and stage == SCHEMA_STAGE:
                payload = tool_call["arguments"]
                validation_error = validate_schema_termination(payload)
                if validation_error:
                    observation = build_invalid_feedback_with_allowed(
                        stage,
                        validation_error,
                        round_allowed_tools,
                    )
                    round_record["error"] = validation_error
                else:
                    schema_evidence = normalize_schema_termination(payload)
                    tool_call["arguments"] = schema_evidence
                    round_record["tool_call"] = tool_call
                    active_tool_call = tool_call
                    previous = stage
                    stage = SQL_STAGE
                    transition = {
                        "from": previous,
                        "to": stage,
                        "round": round_idx,
                        "reason": "terminate_first_stage",
                        "auto_stage_transition": False,
                    }
                    stage_transitions.append(transition)
                    observation = (
                        "Schema evidence accepted. The environment moved to sql_generation. "
                        "Now generate and validate candidate SQL with execute_sql before final termination."
                    )
                    round_record["stage_transition"] = transition
            elif tool_name == "terminate_second_stage" and stage == SQL_STAGE:
                final_sql = previous_round_successful_execute_sql(rounds)
                if not final_sql:
                    observation = (
                        "Error: terminate_second_stage requires the immediately previous round to be a "
                        "successful execute_sql call. Run the intended final SQL with execute_sql, then call "
                        "terminate_second_stage in the next round without rewriting SQL."
                    )
                    round_record["error"] = "previous_round_not_successful_execute_sql"
                else:
                    pred_sql = final_sql
                    terminated = True
                    stage = DONE_STAGE
                    observation = "Final SQL accepted. Episode terminated."
                    round_record["pred_sql"] = pred_sql
                    round_record["final_sql_source"] = "previous_round_successful_execute_sql"
            elif tool_name == "return_to_schema_stage":
                if returns_used >= args.max_stage_returns:
                    observation = (
                        "Error: return_to_schema_stage budget exhausted. Continue in sql_generation using "
                        "the existing memory and candidates."
                    )
                    round_record["error"] = "return_to_schema_stage budget exhausted"
                else:
                    total_budget_before = effective_max_rounds
                    effective_max_rounds, granted_extra_rounds = (
                        extend_total_budget_for_schema_return(
                            effective_max_rounds,
                            args.max_total_rounds_cap,
                            args.schema_return_extra_rounds,
                        )
                    )
                    if granted_extra_rounds <= 0:
                        observation = (
                            "Error: the dynamic total-round cap has been reached. Continue in "
                            "sql_generation using the existing schema evidence and working memory."
                        )
                        round_record["error"] = "dynamic total-round cap exhausted"
                    else:
                        returns_used += 1
                        schema_limit_current += granted_extra_rounds
                        previous = stage
                        stage = SCHEMA_STAGE
                        budget_extension = {
                            "round": round_idx,
                            "requested_extra_schema_rounds": args.schema_return_extra_rounds,
                            "granted_extra_schema_rounds": granted_extra_rounds,
                            "total_budget_before": total_budget_before,
                            "total_budget_after": effective_max_rounds,
                            "total_budget_cap": args.max_total_rounds_cap,
                        }
                        total_budget_extensions.append(budget_extension)
                        transition = {
                            "from": previous,
                            "to": stage,
                            "round": round_idx,
                            "reason": tool_call["arguments"].get("reason", ""),
                            "needed_info": tool_call["arguments"].get("needed_info", ""),
                            "extra_schema_rounds": granted_extra_rounds,
                            "total_budget_before": total_budget_before,
                            "total_budget_after": effective_max_rounds,
                            "total_budget_cap": args.max_total_rounds_cap,
                            "auto_stage_transition": False,
                        }
                        stage_transitions.append(transition)
                        observation = (
                            "Returned to schema_exploration. You received "
                            f"{granted_extra_rounds} extra schema round(s). The total interaction budget "
                            f"was extended from {total_budget_before} to {effective_max_rounds}, with a hard "
                            f"cap of {args.max_total_rounds_cap}, so these schema rounds do not consume the "
                            "SQL-stage allowance."
                        )
                        round_record["budget_extension"] = budget_extension
                        round_record["stage_transition"] = transition
            else:
                tool_result_obj, observation, structured_event = execute_twostage_tool(
                    db_path=db_path,
                    db_id=db_id,
                    stage=stage,
                    tool_call=tool_call,
                    args=args,
                    successful_candidates=successful_candidates,
                    verified_join_pairs=verified_join_pairs,
                )
                if tool_name in {"execute_sub_sql", "execute_sql"}:
                    round_record["tool_result"] = observation
                elif tool_name in {
                    "list_table_name",
                    "get_table_metadata",
                    "inspect_value",
                    "inspect_rows",
                    "inspect_foreign_key",
                    "inspect_join_candidate",
                } and tool_result_obj.get("ok"):
                    round_record["tool_result"] = observation
                else:
                    round_record["tool_result"] = tool_result_obj
                if structured_event:
                    round_record.update(structured_event)

        memory, compressor_error, memory_latency, memory_delta = compress_memory(
            client,
            sample=sample,
            stage=round_record["stage"],
            round_number=round_idx,
            memory_before=memory_before,
            think=think,
            tool_call=active_tool_call,
            observation=observation,
            args=args,
        )
        total_memory_latency += memory_latency
        round_record["observation"] = observation
        round_record["memory_delta"] = memory_delta
        round_record["memory_after"] = memory
        round_record["compressor_error"] = compressor_error
        if parse_error or tool_call is None:
            last_format_error_feedback = observation
        else:
            last_format_error_feedback = ""
        if (
            tool_call is not None
            and tool_call.get("name") in {"execute_sub_sql", "execute_sql"}
            and tool_result_obj is not None
            and not tool_result_obj.get("ok")
        ):
            last_sql_execution_error_feedback = observation
        else:
            last_sql_execution_error_feedback = ""
        last_observation = observation
        rounds.append(round_record)

    if not terminated and args.fallback_to_last_successful_sql and successful_candidates:
        pred_sql = successful_candidates[-1]["sql"]
        used_fallback_sql = True

    return {
        "pred_sql": pred_sql,
        "terminated": terminated,
        "used_fallback_sql": used_fallback_sql,
        "auto_stage_transition": auto_stage_transition,
        "sql_stage_budget_exhausted": sql_stage_budget_exhausted,
        "rounds": rounds,
        "round_count": len(rounds),
        "stage_transitions": stage_transitions,
        "schema_evidence": schema_evidence,
        "successful_candidates": successful_candidates,
        "verified_join_pairs": [
            {"left": f"{left_table}.{left_column}", "right": f"{right_table}.{right_column}"}
            for (left_table, left_column), (right_table, right_column) in sorted(verified_join_pairs)
        ],
        "final_memory": memory,
        "schema_rounds_used": schema_rounds_used,
        "sql_rounds_used": sql_rounds_used,
        "returns_used": returns_used,
        "initial_max_rounds": args.max_rounds,
        "effective_max_rounds": effective_max_rounds,
        "max_total_rounds_cap": args.max_total_rounds_cap,
        "total_budget_added": effective_max_rounds - args.max_rounds,
        "total_budget_extensions": total_budget_extensions,
        "total_agent_latency": total_agent_latency,
        "total_memory_latency": total_memory_latency,
    }


def compute_summary(records: list[dict[str, Any]], args: argparse.Namespace, data_path: Path, db_root: Path) -> dict[str, Any]:
    total = len(records)
    correct = sum(int(record.get("correct", 0)) for record in records)
    strict_correct = sum(int(record.get("strict_correct", record.get("correct", 0))) for record in records)
    projection_relaxed_correct = sum(
        int(record.get("projection_relaxed_correct", record.get("correct", 0)))
        for record in records
    )
    round_counts = [int(record.get("round_count") or len(record.get("rounds") or [])) for record in records]
    compressor_errors = 0
    stage_violations = 0
    format_errors = 0
    for record in records:
        for round_record in record.get("rounds") or []:
            if round_record.get("compressor_error"):
                compressor_errors += 1
            if round_record.get("stage_violation"):
                stage_violations += 1
            error = str(round_record.get("error") or "")
            if "tool_call" in error or "format" in error or "missing" in error:
                format_errors += 1
    return {
        "dataset": str(data_path),
        "db_root": str(db_root),
        "model": args.model,
        "base_url": args.base_url,
        "total": total,
        "correct": correct,
        "execution_accuracy": correct / total if total else 0.0,
        "evaluation_mode": args.evaluation_mode,
        "primary_correct": correct,
        "primary_accuracy": correct / total if total else 0.0,
        "strict_correct": strict_correct,
        "strict_execution_accuracy": strict_correct / total if total else 0.0,
        "projection_relaxed_correct": projection_relaxed_correct,
        "projection_relaxed_accuracy": projection_relaxed_correct / total if total else 0.0,
        "avg_rounds": sum(round_counts) / len(round_counts) if round_counts else 0.0,
        "max_rounds": args.max_rounds,
        "max_total_rounds_cap": args.max_total_rounds_cap,
        "schema_max_rounds": args.schema_max_rounds,
        "sql_max_rounds": args.sql_max_rounds,
        "max_stage_returns": args.max_stage_returns,
        "schema_return_extra_rounds": args.schema_return_extra_rounds,
        "enable_thinking": args.enable_thinking,
        "max_tokens": args.max_tokens,
        "memory_compressor": "llm_delta_program_append",
        "memory_max_tokens": args.memory_max_tokens,
        "max_memory_chars": args.max_memory_chars,
        "memory_temperature": args.memory_temperature,
        "memory_enable_thinking": args.memory_enable_thinking,
        "compressor_error_count": compressor_errors,
        "stage_violation_count": stage_violations,
        "format_error_count": format_errors,
        "used_fallback_sql_count": sum(1 for record in records if record.get("used_fallback_sql")),
        "auto_stage_transition_count": sum(1 for record in records if record.get("auto_stage_transition")),
        "sql_stage_budget_exhausted_count": sum(1 for record in records if record.get("sql_stage_budget_exhausted")),
        "return_to_schema_count": sum(int(record.get("returns_used") or 0) for record in records),
        "total_dynamic_budget_added": sum(
            int(record.get("total_budget_added") or 0) for record in records
        ),
        "dynamic_budget_extended_episode_count": sum(
            1 for record in records if int(record.get("total_budget_added") or 0) > 0
        ),
    }


def render_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)
    return str(value)


def render_table(result: Any) -> str:
    if not result:
        return "<div class='muted'>None</div>"
    if isinstance(result, str):
        return f"<pre>{html.escape(result)}</pre>"
    if not isinstance(result, dict):
        return f"<pre>{html.escape(render_value(result))}</pre>"
    if not result.get("ok"):
        return f"<pre class='error'>{html.escape(str(result.get('error') or 'unknown error'))}</pre>"
    columns = result.get("columns") or []
    rows = result.get("rows") or []
    if not columns:
        return "<div class='muted'>No tabular result.</div>"
    head = "".join(f"<th>{html.escape(str(col))}</th>" for col in columns)
    body_rows = []
    for row in rows:
        body_rows.append("<tr>" + "".join(f"<td>{html.escape(str(cell))}</td>" for cell in row) + "</tr>")
    truncated = "<div class='pill'>truncated</div>" if result.get("truncated") else ""
    return f"{truncated}<table><thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"


def write_viewer(path: Path, records: list[dict[str, Any]], title: str) -> None:
    correct = sum(int(record.get("correct", 0)) for record in records)
    strict_correct = sum(int(record.get("strict_correct", record.get("correct", 0))) for record in records)
    projection_relaxed_correct = sum(
        int(record.get("projection_relaxed_correct", record.get("correct", 0)))
        for record in records
    )
    evaluation_mode = next(
        (str(record.get("evaluation_mode")) for record in records if record.get("evaluation_mode")),
        "strict",
    )
    cards = f"""
    <div class="card"><strong>{len(records)}</strong><span>samples</span></div>
    <div class="card"><strong>{correct}</strong><span>correct</span></div>
    <div class="card"><strong>{(correct / len(records)) if records else 0:.4f}</strong><span>{html.escape(evaluation_mode)}</span></div>
    <div class="card"><strong>{(strict_correct / len(records)) if records else 0:.4f}</strong><span>strict EX</span></div>
    <div class="card"><strong>{(projection_relaxed_correct / len(records)) if records else 0:.4f}</strong><span>projection relaxed</span></div>
    """
    items = []
    for record in records:
        badge = "ok" if record.get("correct") else "wrong"
        rounds_html = []
        for rr in record.get("rounds") or []:
            raw = ((rr.get("debug") or {}).get("raw_message") or "")
            rounds_html.append(
                f"""
                <details class="round">
                  <summary>Round {rr.get('round')} · {html.escape(str(rr.get('stage')))} · {html.escape(str((rr.get('tool_call') or {}).get('name', 'format_error')))}</summary>
                  <div class="grid">
                    <section><h4>think</h4><pre>{html.escape(render_value(rr.get('think')))}</pre></section>
                    <section><h4>tool_call</h4><pre>{html.escape(render_value(rr.get('tool_call')))}</pre></section>
                  </div>
                  <section><h4>observation</h4><pre>{html.escape(render_value(rr.get('observation')))}</pre></section>
                  <section><h4>tool_result</h4>{render_table(rr.get('tool_result'))}</section>
                  <div class="grid">
                    <section><h4>memory_before</h4><pre>{html.escape(render_value(rr.get('memory_before')))}</pre></section>
                    <section><h4>memory_delta</h4><pre>{html.escape(render_value(rr.get('memory_delta')))}</pre></section>
                    <section><h4>memory_after</h4><pre>{html.escape(render_value(rr.get('memory_after')))}</pre></section>
                  </div>
                  <section><h4>compressor_error</h4><pre>{html.escape(render_value(rr.get('compressor_error')))}</pre></section>
                  <details><summary>debug.raw_message</summary><pre>{html.escape(raw)}</pre></details>
                </details>
                """
            )
        evaluation_payload = {
            "evaluation_mode": record.get("evaluation_mode", "strict"),
            "correct": record.get("correct"),
            "strict_correct": record.get("strict_correct", record.get("correct")),
            "projection_relaxed_correct": record.get("projection_relaxed_correct", record.get("correct")),
            "projection_relaxed": record.get("projection_relaxed"),
        }
        items.append(
            f"""
            <article class="episode {badge}">
              <header>
                <h2>qid {html.escape(str(record.get('question_id')))} · {html.escape(str(record.get('db_id')))}</h2>
                <span class="badge {badge}">{badge}</span>
              </header>
              <p>{html.escape(str(record.get('question') or ''))}</p>
              <div class="grid">
                <section><h3>gold_sql</h3><pre>{html.escape(str(record.get('gold_sql') or ''))}</pre></section>
                <section><h3>pred_sql</h3><pre>{html.escape(str(record.get('pred_sql') or ''))}</pre></section>
              </div>
              <div class="grid">
                <section><h3>gold_result</h3>{render_table(record.get('gold_result'))}</section>
                <section><h3>pred_result</h3>{render_table(record.get('pred_result'))}</section>
              </div>
              <section><h3>evaluation</h3><pre>{html.escape(render_value(evaluation_payload))}</pre></section>
              <section><h3>stage_transitions</h3><pre>{html.escape(render_value(record.get('stage_transitions')))}</pre></section>
              <section><h3>rounds</h3>{''.join(rounds_html)}</section>
            </article>
            """
        )
    doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f7fa;
      --panel: #ffffff;
      --line: #d8e0ea;
      --text: #15202b;
      --muted: #64748b;
      --code: #0f172a;
      --ok: #0f8a5f;
      --bad: #b42318;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); }}
    main {{ max-width: 1440px; margin: 0 auto; padding: 24px; }}
    h1 {{ margin: 0 0 16px; font-size: 24px; }}
    h2 {{ margin: 0; font-size: 18px; }}
    h3, h4 {{ margin: 0 0 8px; font-size: 14px; }}
    pre {{ white-space: pre-wrap; overflow-wrap: anywhere; margin: 0; padding: 12px; background: var(--code); color: #f8fafc; border-radius: 6px; line-height: 1.45; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
    th, td {{ border: 1px solid var(--line); padding: 6px 8px; text-align: left; vertical-align: top; }}
    th {{ background: #eef3f8; }}
    .cards {{ display: flex; gap: 12px; margin-bottom: 18px; flex-wrap: wrap; }}
    .card {{ min-width: 150px; padding: 14px 16px; border: 1px solid var(--line); background: var(--panel); border-radius: 8px; }}
    .card strong {{ display: block; font-size: 22px; }}
    .card span, .muted {{ color: var(--muted); }}
    .episode {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 16px; margin-bottom: 16px; }}
    .episode > header {{ display: flex; justify-content: space-between; gap: 12px; align-items: center; margin-bottom: 10px; }}
    .badge {{ border-radius: 999px; padding: 4px 10px; font-size: 12px; color: white; }}
    .badge.ok {{ background: var(--ok); }}
    .badge.wrong {{ background: var(--bad); }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin: 12px 0; }}
    .round {{ border: 1px solid var(--line); border-radius: 8px; padding: 10px; margin: 10px 0; background: #fbfdff; }}
    .round summary {{ cursor: pointer; font-weight: 700; }}
    .error {{ background: #7f1d1d; }}
    .pill {{ display: inline-block; margin-bottom: 6px; border: 1px solid var(--line); border-radius: 999px; padding: 2px 8px; color: var(--muted); font-size: 12px; }}
    @media (max-width: 900px) {{ .grid {{ grid-template-columns: 1fr; }} main {{ padding: 12px; }} }}
  </style>
</head>
<body>
  <main>
    <h1>{html.escape(title)}</h1>
    <div class="cards">{cards}</div>
    {''.join(items)}
  </main>
</body>
</html>
"""
    path.write_text(doc, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/arcwise_plat_full_with_diff.json")
    parser.add_argument("--db-root", default="data/arcwise_plat/dev/dev_databases")
    parser.add_argument("--out-dir", default="results/qwen35-4b-arcwise-plat-twostage-agent")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--api-key", default="EMPTY")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=8196,
        help="Agent completion-token cap shared by reasoning and tool call (default: 8196)",
    )
    parser.add_argument("--llm-retries", type=int, default=2)
    parser.add_argument("--retry-sleep", type=float, default=2.0)
    parser.add_argument("--max-rounds", type=int, default=30)
    parser.add_argument(
        "--max-total-rounds-cap",
        type=int,
        default=40,
        help=(
            "hard cap for the dynamic total interaction budget; each accepted schema return "
            "extends --max-rounds by the granted schema-return rounds up to this cap"
        ),
    )
    parser.add_argument("--schema-max-rounds", type=int, default=20)
    parser.add_argument("--sql-max-rounds", type=int, default=10)
    parser.add_argument("--max-stage-returns", type=int, default=2)
    parser.add_argument("--schema-return-extra-rounds", type=int, default=2)
    parser.add_argument("--max-observation-chars", type=int, default=6000)
    parser.add_argument("--tool-max-rows", type=int, default=50)
    parser.add_argument("--sql-timeout", type=float, default=60.0)
    parser.add_argument("--eval-result-max-rows", type=int, default=50)
    parser.add_argument(
        "--evaluation-mode",
        choices=("projection_relaxed", "strict"),
        default="projection_relaxed",
        help="projection_relaxed ignores predicted extra columns and column order while preserving exact projected row sets",
    )
    parser.add_argument(
        "--memory-max-tokens",
        type=int,
        default=1024,
        help="memory-compressor completion-token cap (default: 1024)",
    )
    parser.add_argument("--max-memory-chars", type=int, default=2500)
    parser.add_argument("--memory-temperature", type=float, default=0.0)
    parser.add_argument("--memory-top-p", type=float, default=1.0)
    parser.add_argument("--memory-retries", type=int, default=1)
    parser.add_argument("--memory-enable-thinking", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--question-id", action="append", default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--skip-internal-eval", action="store_true")
    parser.add_argument("--fallback-to-last-successful-sql", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--enable-thinking", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()

    if args.max_rounds <= 0:
        parser.error("--max-rounds must be positive")
    if args.max_total_rounds_cap < args.max_rounds:
        parser.error("--max-total-rounds-cap must be greater than or equal to --max-rounds")
    if args.schema_return_extra_rounds < 0:
        parser.error("--schema-return-extra-rounds must be non-negative")

    script_dir = Path(__file__).resolve().parent
    data_path = resolve_path(args.data, script_dir)
    db_root = resolve_path(args.db_root, script_dir)
    out_dir = resolve_path(args.out_dir, script_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    repro_artifacts = save_reproducibility_artifacts(out_dir, Path(__file__).resolve(), script_dir)

    episodes_path = out_dir / "episodes.jsonl"
    pretty_path = out_dir / "episodes.pretty.json"
    wrong_pretty_path = out_dir / "wrong_episodes.pretty.json"
    viewer_path = out_dir / "viewer.html"
    wrong_viewer_path = out_dir / "wrong_viewer.html"
    summary_path = out_dir / "summary.json"

    data = json.load(data_path.open(encoding="utf-8"))
    if args.question_id:
        wanted = {str(qid) for qid in args.question_id}
        data = [item for item in data if str(item["question_id"]) in wanted]
    if args.limit is not None:
        data = data[: args.limit]

    completed: set[str] = set()
    correct_count = 0
    evaluated_count = 0
    if args.resume:
        completed, correct_count, evaluated_count = load_completed(episodes_path, args.evaluation_mode)

    total = len(data)
    mode = "a" if args.resume and episodes_path.exists() else "w"
    with httpx.Client(trust_env=False, timeout=300) as client, episodes_path.open(mode, encoding="utf-8") as episodes_f:
        for idx, sample in enumerate(data, start=1):
            qid = str(sample["question_id"])
            if qid in completed:
                continue
            db_path = find_db_path(db_root, sample["db_id"])
            episode = run_twostage_episode(client, sample, db_root, args)
            if args.skip_internal_eval:
                eval_info = {
                    "correct": 0,
                    "evaluation_mode": args.evaluation_mode,
                    "strict_correct": 0,
                    "projection_relaxed_correct": 0,
                    "projection_relaxed": None,
                    "pred_ok": None,
                    "gold_ok": None,
                    "pred_error": None,
                    "gold_error": None,
                    "pred_row_count": None,
                    "gold_row_count": None,
                    "pred_execution_time": None,
                    "gold_execution_time": None,
                    "pred_result": None,
                    "gold_result": None,
                    "internal_eval_skipped": True,
                }
            else:
                eval_info = evaluate_with_projection_mode(
                    db_path,
                    episode["pred_sql"],
                    sample["SQL"],
                    args.sql_timeout,
                    args.eval_result_max_rows,
                    args.evaluation_mode,
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
            episodes_f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            episodes_f.flush()
            print(
                f"[{idx}/{total}] qid={qid} db={sample['db_id']} correct={eval_info['correct']} "
                f"rounds={record['round_count']} terminated={record['terminated']} "
                f"running_{args.evaluation_mode}={correct_count / evaluated_count:.4f}",
                flush=True,
            )

    records = load_episodes(episodes_path)
    wrong_records = [record for record in records if not record.get("correct")]
    write_json(pretty_path, records)
    write_json(wrong_pretty_path, wrong_records)
    write_viewer(viewer_path, records, "Two-Stage Text-to-SQL Agent Episodes")
    write_viewer(wrong_viewer_path, wrong_records, "Two-Stage Text-to-SQL Agent Wrong Episodes")
    summary = compute_summary(records, args, data_path, db_root)
    summary.update(
        {
            "episodes_path": str(episodes_path),
            "episodes_pretty_path": str(pretty_path),
            "wrong_episodes_pretty_path": str(wrong_pretty_path),
            "viewer_path": str(viewer_path),
            "wrong_viewer_path": str(wrong_viewer_path),
            "reproducibility_artifacts": repro_artifacts,
        }
    )
    write_json(summary_path, summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
