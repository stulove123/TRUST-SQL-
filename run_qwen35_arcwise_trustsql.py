from __future__ import annotations

import argparse
import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

import httpx


ALLOWED_SQL_PREFIXES = ("SELECT", "PRAGMA", "EXPLAIN")
SQL_BLOCK_RE = re.compile(r"```(?:sql)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
THINK_RE = re.compile(r"<think>(.*?)</think>", re.IGNORECASE | re.DOTALL)
DEFAULT_MODEL = "/root/autodl-tmp/DeepEye-SQL/workspace/models/modelscope/Qwen/Qwen3___5-4B"
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


def call_model(
    client: httpx.Client,
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    temperature: float,
    top_p: float,
    llm_retries: int,
    retry_sleep: float,
    enable_thinking: bool,
) -> tuple[str, str | None, float]:
    started = time.perf_counter()
    last_error: Exception | None = None
    for attempt in range(llm_retries + 1):
        try:
            response = client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "top_p": top_p,
                    "chat_template_kwargs": {"enable_thinking": enable_thinking},
                },
            )
            response.raise_for_status()
            payload = response.json()
            message = payload["choices"][0]["message"]
            reasoning_content = (
                message.get("reasoning_content")
                or message.get("reasoning")
                or message.get("reasoning_text")
            )
            content = normalize_think_tags(message.get("content") or "")
            return content, reasoning_content, time.perf_counter() - started
        except Exception as exc:
            last_error = exc
            if attempt < llm_retries:
                time.sleep(retry_sleep)
    raise RuntimeError(f"LLM call failed after {llm_retries + 1} attempt(s): {last_error}") from last_error


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

    for round_idx in range(args.max_rounds):
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
        total_latency += latency
        action = extract_action(assistant_text)
        think = extract_think(assistant_text, reasoning_content)
        messages.append({"role": "assistant", "content": assistant_text})
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
        if reasoning_content:
            round_record["reasoning_content"] = reasoning_content

        answer_sql = extract_answer_sql(assistant_text)
        if answer_sql:
            pred_sql = answer_sql
            terminated = True
            round_record["pred_sql"] = pred_sql
            round_record["assistant"]["answer_sql"] = pred_sql
            conversation.append(round_record)
            break

        if action == "propose_schema":
            schema_json, error = extract_schema_json(assistant_text)
            if error:
                feedback = build_format_feedback(round_idx, args.max_rounds, error)
                round_record["error"] = error
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
            messages.append({"role": "user", "content": feedback})
            round_record["observation"] = feedback
            conversation.append(round_record)
            continue

        if action in {"explore_schema", "generate_sql"}:
            tool_call, error = extract_tool_call(assistant_text, db_id)
            if error:
                feedback = build_format_feedback(round_idx, args.max_rounds, error)
                round_record["error"] = error
            else:
                call_db_id = tool_call["arguments"]["db_id"]
                sql = tool_call["arguments"]["sql"]
                round_record["assistant"]["tool_call"] = tool_call
                if call_db_id != db_id:
                    feedback = f"Error: tool_call db_id must be {db_id!r}, got {call_db_id!r}."
                elif args.enforce_metadata_only_explore and action == "explore_schema" and not is_metadata_query(sql):
                    feedback = (
                        "Error: explore_schema may only query metadata. Use sqlite_master/sqlite_schema "
                        "or PRAGMA table_info/foreign_key_list."
                    )
                else:
                    result = execute_tool_sql(
                        db_path,
                        sql,
                        timeout_s=args.sql_timeout,
                        max_rows=args.tool_max_rows,
                    )
                    feedback = format_tool_result(result, args.max_observation_chars)
                    round_record["tool_result"] = result
                    if action == "generate_sql":
                        last_generated_sql = sql
            messages.append({"role": "user", "content": feedback})
            round_record["observation"] = feedback
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
    parser.add_argument("--db-root", default="/root/autodl-tmp/DeepEye-SQL/data/arcwise_plat/dev/dev_databases")
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
        "enforce_metadata_only_explore": args.enforce_metadata_only_explore,
        "fallback_to_last_generated": args.fallback_to_last_generated,
        "predictions_path": str(pred_path),
        "details_path": str(details_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
