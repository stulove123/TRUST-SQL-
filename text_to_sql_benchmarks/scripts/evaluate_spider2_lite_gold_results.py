#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sqlite3
import time
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


def load_eval_standards(path: Path) -> dict[str, dict[str, Any]]:
    return {record["instance_id"]: record for record in read_jsonl(path)}


def load_spider2_metadata(path: Path) -> dict[str, dict[str, Any]]:
    return {record["instance_id"]: record for record in read_jsonl(path)}


def load_csv_table(path: Path) -> dict[str, Any]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if not rows:
        return {"columns": [], "rows": []}
    return {"columns": rows[0], "rows": rows[1:]}


def resolve_gold_paths(instance_id: str, gold_result_dir: Path) -> tuple[list[Path], bool]:
    base_path = gold_result_dir / f"{instance_id}.csv"
    if base_path.exists():
        return [base_path], True
    pattern = re.compile(rf"^{re.escape(instance_id)}(_[a-z])?\.csv$")
    csv_files = sorted(path for path in gold_result_dir.iterdir() if pattern.match(path.name))
    return csv_files, False


def normalize_cell(value: Any) -> Any:
    if value is None:
        return 0
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "" or stripped.lower() in {"nan", "none", "null"}:
            return 0
        return stripped
    return value


def parse_number(value: Any) -> float | None:
    value = normalize_cell(value)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if math.isnan(float(value)):
            return 0.0
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def cells_match(left: Any, right: Any, tolerance: float = 1e-2) -> bool:
    left_norm = normalize_cell(left)
    right_norm = normalize_cell(right)
    left_num = parse_number(left_norm)
    right_num = parse_number(right_norm)
    if left_num is not None and right_num is not None:
        return math.isclose(left_num, right_num, abs_tol=tolerance)
    return left_norm == right_norm


def sort_key(value: Any) -> tuple[bool, str, bool]:
    return (value is None, str(value), isinstance(value, (int, float)))


def vectors_match(
    gold_vector: list[Any],
    pred_vector: list[Any],
    *,
    ignore_order: bool,
    tolerance: float = 1e-2,
) -> bool:
    gold_values = [normalize_cell(value) for value in gold_vector]
    pred_values = [normalize_cell(value) for value in pred_vector]
    if ignore_order:
        gold_values = sorted(gold_values, key=sort_key)
        pred_values = sorted(pred_values, key=sort_key)
    if len(gold_values) != len(pred_values):
        return False
    return all(cells_match(gold, pred, tolerance) for gold, pred in zip(gold_values, pred_values))


def transpose_rows(rows: list[list[Any]], width: int) -> list[list[Any]]:
    vectors: list[list[Any]] = []
    for col_idx in range(width):
        vectors.append([
            row[col_idx] if col_idx < len(row) else None
            for row in rows
        ])
    return vectors


def select_gold_columns(gold_table: dict[str, Any], condition_cols: Any) -> tuple[list[str], list[list[Any]]]:
    columns = list(gold_table["columns"])
    rows = list(gold_table["rows"])
    if condition_cols:
        if not isinstance(condition_cols, (list, tuple)):
            condition_cols = [condition_cols]
        selected_indices = [int(idx) for idx in condition_cols]
        selected_columns = [columns[idx] if idx < len(columns) else f"column_{idx}" for idx in selected_indices]
        selected_rows = [
            [row[idx] if idx < len(row) else None for idx in selected_indices]
            for row in rows
        ]
        return selected_columns, selected_rows
    return columns, rows


def compare_table(
    pred_table: dict[str, Any],
    gold_table: dict[str, Any],
    condition_cols: Any = None,
    ignore_order: bool = False,
) -> int:
    gold_columns, gold_rows = select_gold_columns(gold_table, condition_cols)
    pred_columns = list(pred_table["columns"])
    pred_rows = list(pred_table["rows"])
    gold_vectors = transpose_rows(gold_rows, len(gold_columns))
    pred_vectors = transpose_rows(pred_rows, len(pred_columns))
    for gold_vector in gold_vectors:
        if not any(vectors_match(gold_vector, pred_vector, ignore_order=ignore_order) for pred_vector in pred_vectors):
            return 0
    return 1


def normalize_multi_condition_cols(condition_cols: Any, num_gold: int) -> list[Any]:
    if condition_cols in (None, [], [[]], [None]):
        return [[] for _ in range(num_gold)]
    if num_gold > 1 and not all(isinstance(item, list) for item in condition_cols):
        return [condition_cols for _ in range(num_gold)]
    return list(condition_cols)


def compare_multi_table(
    pred_table: dict[str, Any],
    gold_tables: list[dict[str, Any]],
    condition_cols: Any,
    ignore_order: bool,
) -> tuple[int, int | None]:
    if not gold_tables:
        return 0, None
    condition_by_gold = normalize_multi_condition_cols(condition_cols, len(gold_tables))
    for idx, gold_table in enumerate(gold_tables):
        if compare_table(pred_table, gold_table, condition_by_gold[idx], ignore_order):
            return 1, idx
    return 0, None


def sqlite_readonly_connection(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def execute_sqlite_to_table(db_path: Path, sql: str, timeout_s: float) -> tuple[bool, dict[str, Any] | None, str | None, float]:
    started = time.perf_counter()
    timed_out = False

    def progress_handler() -> int:
        nonlocal timed_out
        if time.perf_counter() - started > timeout_s:
            timed_out = True
            return 1
        return 0

    conn = sqlite_readonly_connection(db_path)
    try:
        conn.set_progress_handler(progress_handler, 1000)
        cur = conn.execute(sql)
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description or []]
        table = {
            "columns": [str(column) for column in columns],
            "rows": [[cell for cell in row] for row in rows],
        }
        return True, table, None, time.perf_counter() - started
    except Exception as exc:
        if timed_out:
            return False, None, f"timeout after {timeout_s:.1f}s", time.perf_counter() - started
        return False, None, str(exc), time.perf_counter() - started
    finally:
        try:
            conn.set_progress_handler(None, 0)
        except Exception:
            pass
        conn.close()


def preview_table(table: dict[str, Any] | None, max_rows: int) -> dict[str, Any] | None:
    if table is None:
        return None
    rows = table.get("rows") or []
    return {
        "columns": table.get("columns") or [],
        "rows": rows[:max_rows],
        "row_count": len(rows),
        "truncated": len(rows) > max_rows,
    }


def evaluate_episode(
    episode: dict[str, Any],
    metadata: dict[str, dict[str, Any]],
    standards: dict[str, dict[str, Any]],
    gold_result_dir: Path,
    sqlite_db_dir: Path,
    timeout_s: float,
    preview_rows: int,
) -> dict[str, Any]:
    qid = str(episode["question_id"])
    pred_sql = (episode.get("pred_sql") or "").strip()
    standard = standards.get(qid, {})
    gold_paths, is_single_gold = resolve_gold_paths(qid, gold_result_dir)
    result: dict[str, Any] = {
        "question_id": qid,
        "db_id": episode.get("db_id"),
        "score": 0,
        "status": "unknown",
        "pred_sql": pred_sql,
        "condition_cols": standard.get("condition_cols"),
        "ignore_order": standard.get("ignore_order", False),
        "gold_files": [str(path) for path in gold_paths],
        "matched_gold_index": None,
        "pred_row_count": None,
        "pred_column_count": None,
        "execution_time": None,
        "error": None,
        "pred_result_preview": None,
        "gold_result_preview": None,
    }
    if not pred_sql:
        result["status"] = "no_pred_sql"
        result["error"] = "episode has no pred_sql"
        return result
    if not gold_paths:
        result["status"] = "no_gold_result"
        result["error"] = "no official gold exec_result csv found"
        return result
    db_name = (metadata.get(qid) or {}).get("db") or episode.get("db_id")
    db_path = sqlite_db_dir / f"{db_name}.sqlite"
    if not db_path.exists():
        result["status"] = "missing_sqlite_db"
        result["error"] = f"sqlite database not found: {db_path}"
        return result

    ok, pred_table, error, elapsed = execute_sqlite_to_table(db_path, pred_sql, timeout_s)
    result["execution_time"] = elapsed
    if not ok or pred_table is None:
        result["status"] = "pred_execution_error"
        result["error"] = error
        return result

    result["pred_row_count"] = len(pred_table["rows"])
    result["pred_column_count"] = len(pred_table["columns"])
    result["pred_result_preview"] = preview_table(pred_table, preview_rows)

    try:
        gold_tables = [load_csv_table(path) for path in gold_paths]
        result["gold_result_preview"] = preview_table(gold_tables[0] if gold_tables else None, preview_rows)
        if is_single_gold:
            score = compare_table(
                pred_table,
                gold_tables[0],
                standard.get("condition_cols"),
                bool(standard.get("ignore_order", False)),
            )
            matched_idx = 0 if score else None
        else:
            score, matched_idx = compare_multi_table(
                pred_table,
                gold_tables,
                standard.get("condition_cols"),
                bool(standard.get("ignore_order", False)),
            )
        result["score"] = int(score)
        result["matched_gold_index"] = matched_idx
        result["status"] = "correct" if score else "wrong_result"
        if not score:
            result["error"] = "Result Error"
    except Exception as exc:
        result["status"] = "compare_error"
        result["error"] = str(exc)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Spider2-Lite local episodes against official gold execution CSVs.")
    parser.add_argument("--episodes", required=True, help="Path to episodes.jsonl produced by the two-stage runner.")
    parser.add_argument("--spider2-lite-root", default="/root/autodl-tmp/Spider2/spider2-lite")
    parser.add_argument("--sqlite-db-dir", default=None, help="Directory containing Spider2 local SQLite databases.")
    parser.add_argument("--out", default=None, help="Output JSON path. Defaults beside episodes file.")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--preview-rows", type=int, default=20)
    args = parser.parse_args()

    episodes_path = Path(args.episodes).expanduser().resolve()
    spider2_root = Path(args.spider2_lite_root).expanduser().resolve()
    sqlite_db_dir = Path(args.sqlite_db_dir).expanduser().resolve() if args.sqlite_db_dir else spider2_root / "resource" / "databases" / "spider2-localdb"
    gold_dir = spider2_root / "evaluation_suite" / "gold"
    gold_result_dir = gold_dir / "exec_result"
    standards_path = gold_dir / "spider2lite_eval.jsonl"
    metadata_path = spider2_root / "spider2-lite.jsonl"
    out_path = Path(args.out).expanduser().resolve() if args.out else episodes_path.with_name("spider2_lite_gold_result_eval.json")

    episodes = read_jsonl(episodes_path)
    standards = load_eval_standards(standards_path)
    metadata = load_spider2_metadata(metadata_path)
    results = [
        evaluate_episode(
            episode,
            metadata,
            standards,
            gold_result_dir,
            sqlite_db_dir,
            args.timeout,
            args.preview_rows,
        )
        for episode in episodes
    ]
    total = len(results)
    correct = sum(item["score"] for item in results)
    executable = sum(1 for item in results if item["status"] in {"correct", "wrong_result"})
    has_pred = sum(1 for item in results if item["pred_sql"].strip())
    summary = {
        "episodes_path": str(episodes_path),
        "spider2_lite_root": str(spider2_root),
        "sqlite_db_dir": str(sqlite_db_dir),
        "gold_result_dir": str(gold_result_dir),
        "total": total,
        "correct": correct,
        "official_gold_result_accuracy": correct / total if total else 0.0,
        "executable_total": executable,
        "executable_accuracy": correct / executable if executable else 0.0,
        "has_pred_sql": has_pred,
        "no_pred_sql": sum(1 for item in results if item["status"] == "no_pred_sql"),
        "status_counts": {},
    }
    for item in results:
        summary["status_counts"][item["status"]] = summary["status_counts"].get(item["status"], 0) + 1
    payload = {"summary": summary, "results": results}
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"wrote {out_path}")
    for item in results:
        print(
            "\t".join(
                str(value)
                for value in (
                    item["question_id"],
                    item["db_id"],
                    item["score"],
                    item["status"],
                    item["pred_row_count"],
                    item["pred_column_count"],
                    item["error"],
                )
            )
        )


if __name__ == "__main__":
    main()
