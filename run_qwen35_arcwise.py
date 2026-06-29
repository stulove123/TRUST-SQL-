from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

import httpx
from openai import OpenAI


DEFAULT_MODEL = "/root/autodl-tmp/DeepEye-SQL/workspace/models/modelscope/Qwen/Qwen3___5-4B"
DEFAULT_BASE_URL = "http://127.0.0.1:8000/v1"


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def load_column_descriptions(schema_root: Path, db_id: str) -> dict[tuple[str, str], dict[str, str]]:
    desc_dir = schema_root / db_id / "database_description"
    descriptions: dict[tuple[str, str], dict[str, str]] = {}
    if not desc_dir.exists():
        return descriptions
    for csv_path in sorted(desc_dir.glob("*.csv")):
        table = csv_path.stem
        try:
            text = csv_path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            text = csv_path.read_text(encoding="latin-1")
        from io import StringIO

        with StringIO(text) as f:
            reader = csv.DictReader(f)
            for row in reader:
                col = (row.get("original_column_name") or "").strip()
                if not col:
                    continue
                descriptions[(table.lower(), col.lower())] = {
                    "column_name": (row.get("column_name") or "").strip(),
                    "column_description": (row.get("column_description") or "").strip(),
                    "data_format": (row.get("data_format") or "").strip(),
                    "value_description": (row.get("value_description") or "").strip(),
                }
    return descriptions


def get_table_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [row[0] for row in rows]


def get_sample_values(conn: sqlite3.Connection, table: str, column: str, col_type: str, limit: int) -> list[str]:
    if limit <= 0:
        return []
    type_text = (col_type or "").lower()
    if not any(token in type_text for token in ["char", "text", "date", "time", "clob", "varchar"]):
        return []
    try:
        rows = conn.execute(
            f"SELECT DISTINCT {quote_ident(column)} FROM {quote_ident(table)} "
            f"WHERE {quote_ident(column)} IS NOT NULL AND CAST({quote_ident(column)} AS TEXT) != '' "
            f"LIMIT {int(limit)}"
        ).fetchall()
    except sqlite3.Error:
        return []
    values = []
    for (value,) in rows:
        text = str(value)
        if len(text) > 60:
            text = text[:57] + "..."
        values.append(text)
    return values


def build_schema_prompt(db_path: Path, schema_root: Path, db_id: str, sample_values: int) -> str:
    descriptions = load_column_descriptions(schema_root, db_id)
    conn = sqlite3.connect(db_path)
    try:
        lines: list[str] = []
        for table in get_table_names(conn):
            row_count = conn.execute(f"SELECT COUNT(*) FROM {quote_ident(table)}").fetchone()[0]
            lines.append(f"Table {quote_ident(table)} -- rows: {row_count}")
            columns = conn.execute(f"PRAGMA table_info({quote_ident(table)})").fetchall()
            for _, col, col_type, notnull, default_value, pk in columns:
                meta = descriptions.get((table.lower(), col.lower()), {})
                bits = [f"{quote_ident(col)} {col_type or 'UNKNOWN'}"]
                if pk:
                    bits.append("PRIMARY KEY")
                if notnull:
                    bits.append("NOT NULL")
                if default_value is not None:
                    bits.append(f"DEFAULT {default_value}")
                human_name = meta.get("column_name")
                description = meta.get("column_description")
                value_description = meta.get("value_description")
                extras = []
                if human_name:
                    extras.append(f"name: {human_name}")
                if description:
                    extras.append(f"description: {description}")
                if value_description:
                    extras.append(f"values: {value_description}")
                samples = get_sample_values(conn, table, col, col_type or "", sample_values)
                if samples:
                    extras.append("examples: " + ", ".join(repr(v) for v in samples))
                if extras:
                    bits.append("-- " + "; ".join(extras))
                lines.append("  - " + " ".join(bits))
            foreign_keys = conn.execute(f"PRAGMA foreign_key_list({quote_ident(table)})").fetchall()
            for fk in foreign_keys:
                _, _, ref_table, from_col, to_col, *_ = fk
                if not ref_table or not from_col or not to_col:
                    continue
                lines.append(
                    f"  - FOREIGN KEY {quote_ident(from_col)} REFERENCES {quote_ident(ref_table)}({quote_ident(to_col)})"
                )
            lines.append("")
        return "\n".join(lines).strip()
    finally:
        conn.close()


def build_messages(sample: dict[str, Any], schema: str) -> list[dict[str, str]]:
    evidence = (sample.get("evidence") or "").strip()
    evidence_part = f"\nEvidence/hint:\n{evidence}\n" if evidence else ""
    user = f"""Database schema:
{schema}

Question:
{sample["question"]}
{evidence_part}
Generate one SQLite SQL query that answers the question.
Use only tables and columns from the schema.
Return only the SQL query, with no markdown, no explanation, and no comments."""
    return [
        {
            "role": "system",
            "content": (
                "You are a careful Text-to-SQL system. Output exactly one valid SQLite SQL query. "
                "Do not explain. Do not include markdown fences."
            ),
        },
        {"role": "user", "content": user},
    ]


SQL_BLOCK_RE = re.compile(r"```(?:sql)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


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


def execute_sql(
    db_path: Path, sql: str, timeout_s: float
) -> tuple[bool, list[Any] | None, str | None, float]:
    start = time.perf_counter()
    conn = sqlite3.connect(db_path)
    timed_out = False

    def interrupt_on_timeout() -> int:
        nonlocal timed_out
        if time.perf_counter() - start > timeout_s:
            timed_out = True
            return 1
        return 0

    try:
        conn.set_progress_handler(interrupt_on_timeout, 1000)
        conn.execute("BEGIN TRANSACTION;")
        rows = conn.execute(sql).fetchall()
        conn.rollback()
        return True, rows, None, time.perf_counter() - start
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        error = str(exc)
        if timed_out:
            error = f"SQL execution timeout after {timeout_s:.1f}s"
        return False, None, error, time.perf_counter() - start
    finally:
        try:
            conn.set_progress_handler(None, 0)
        except Exception:
            pass
        conn.close()


def evaluate(db_path: Path, pred_sql: str, gold_sql: str, sql_timeout: float) -> dict[str, Any]:
    pred_ok, pred_rows, pred_error, pred_time = execute_sql(db_path, pred_sql, sql_timeout)
    gold_ok, gold_rows, gold_error, gold_time = execute_sql(db_path, gold_sql, sql_timeout)
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
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/arcwise_plat_full_with_diff.json")
    parser.add_argument("--db-root", default="/root/autodl-tmp/DeepEye-SQL/data/bird/dev/dev_databases")
    parser.add_argument("--schema-root", default="data/schemas")
    parser.add_argument("--out-dir", default="results/qwen35-4b-arcwise-plat")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--api-key", default="EMPTY")
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--sample-values", type=int, default=3)
    parser.add_argument("--sql-timeout", type=float, default=60.0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    data_path = Path(args.data)
    db_root = Path(args.db_root)
    schema_root = Path(args.schema_root)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pred_path = out_dir / "predictions.json"
    details_path = out_dir / "details.jsonl"
    summary_path = out_dir / "summary.json"

    data = json.load(data_path.open())
    if args.limit is not None:
        data = data[: args.limit]

    predictions: dict[str, str] = {}
    completed: set[str] = set()
    correct_count = 0
    evaluated_count = 0
    if args.resume and pred_path.exists():
        predictions = json.load(pred_path.open())
        completed = set(predictions)
    if args.resume and details_path.exists():
        completed = set()
        correct_count = 0
        evaluated_count = 0
        with details_path.open(encoding="utf-8") as existing_f:
            for line in existing_f:
                if not line.strip():
                    continue
                record = json.loads(line)
                completed.add(str(record["question_id"]))
                correct_count += int(record.get("correct", 0))
                evaluated_count += 1

    client = OpenAI(
        api_key=args.api_key,
        base_url=args.base_url,
        http_client=httpx.Client(trust_env=False, timeout=180),
    )

    schema_cache: dict[str, str] = {}
    total = len(data)

    details_mode = "a" if args.resume and details_path.exists() else "w"
    with details_path.open(details_mode, encoding="utf-8") as details_f:
        for idx, sample in enumerate(data, start=1):
            qid = str(sample["question_id"])
            db_id = sample["db_id"]
            if qid in completed:
                continue
            db_path = db_root / db_id / f"{db_id}.sqlite"
            if not db_path.exists():
                raise FileNotFoundError(f"Missing database for {db_id}: {db_path}")

            if db_id not in schema_cache:
                schema_cache[db_id] = build_schema_prompt(db_path, schema_root, db_id, args.sample_values)

            if qid in predictions:
                pred_sql = predictions[qid]
                raw = None
                latency = None
            else:
                started = time.perf_counter()
                response = client.chat.completions.create(
                    model=args.model,
                    messages=build_messages(sample, schema_cache[db_id]),
                    max_tokens=args.max_tokens,
                    temperature=args.temperature,
                    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
                )
                latency = time.perf_counter() - started
                raw = response.choices[0].message.content or ""
                pred_sql = extract_sql(raw)
                predictions[qid] = pred_sql
                pred_path.write_text(json.dumps(predictions, indent=2, ensure_ascii=False), encoding="utf-8")

            eval_info = evaluate(db_path, pred_sql, sample["SQL"], args.sql_timeout)
            correct_count += eval_info["correct"]
            evaluated_count += 1
            record = {
                "idx": idx,
                "question_id": qid,
                "db_id": db_id,
                "question": sample["question"],
                "evidence": sample.get("evidence", ""),
                "gold_sql": sample["SQL"],
                "pred_sql": pred_sql,
                "raw_response": raw,
                "llm_latency": latency,
                **eval_info,
            }
            details_f.write(json.dumps(record, ensure_ascii=False) + "\n")
            details_f.flush()
            print(
                f"[{idx}/{total}] qid={qid} db={db_id} correct={eval_info['correct']} "
                f"running_ex={correct_count / evaluated_count:.4f}",
                flush=True,
            )

    summary = {
        "dataset": str(data_path),
        "model": args.model,
        "base_url": args.base_url,
        "total": evaluated_count,
        "correct": correct_count,
        "execution_accuracy": correct_count / evaluated_count if evaluated_count else 0.0,
        "predictions_path": str(pred_path),
        "details_path": str(details_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
