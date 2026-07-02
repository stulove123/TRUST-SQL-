"""
SQL Execution and Scoring Module with Schema Linking Support

Scoring:
- Turn-level format score:  0.1  (correct format per turn)
- Schema Linking score:     0.0–1.0  (table 0.4 + column 0.6)
  Supported modes: f1 / precision / recall / totalmatch /
                   recall_then_precision_strict / recall_then_precision
- SQL execution score:      0.0–1.0  (correct=1.0, executable=0.2, extracted=0.0)
"""

import asyncio
import json
import os
import random
import re
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np


# ============================================================================
# Configuration
# ============================================================================
SCORE_CONFIG = {
    "turn_format":        0.1,
    "correct_execution":  1.0,
    "executable_sql":     0.2,
    "extracted_answer":   0.0,
    "schema_scoring_mode": "totalmatch",
    "schema_table_weight":  0.4,
    "schema_column_weight": 0.6,
}

SECURITY_CONFIG = {
    "max_rows":               30,
    "max_retries":             3,
    "base_delay":              1.0,
    "max_concurrent_queries": 40,
}

ALLOWED_SQL_PREFIXES = ('SELECT', 'PRAGMA', 'EXPLAIN')

_reward_thread_pool: Optional[ThreadPoolExecutor] = None


# ============================================================================
# Thread Pool Management
# ============================================================================
def set_thread_pool(pool: ThreadPoolExecutor) -> None:
    """Set the external thread pool used for async SQL execution."""
    global _reward_thread_pool
    _reward_thread_pool = pool


def _get_thread_pool() -> ThreadPoolExecutor:
    """Return the active thread pool, creating a default one if needed."""
    global _reward_thread_pool
    if _reward_thread_pool is None:
        print("[WARNING] No external thread pool set, creating default pool")
        _reward_thread_pool = ThreadPoolExecutor(
            max_workers=SECURITY_CONFIG["max_concurrent_queries"]
        )
    return _reward_thread_pool


# ============================================================================
# Utility Functions
# ============================================================================
def _ensure_string(value: Any) -> str:
    """Convert any value to a plain Python string."""
    if isinstance(value, str):
        return value
    if isinstance(value, np.ndarray):
        return str(value.item()) if value.size == 1 else str(value)
    if isinstance(value, (np.int64, np.int32, np.float64, np.float32, np.str_)):
        return str(value.item()) if hasattr(value, 'item') else str(value)
    if value is None:
        return ""
    return str(value)


def normalize_ground_truth(ground_truth: Union[Dict, List[Dict]]) -> Union[Dict, List[Dict]]:
    """Recursively normalize all keys and leaf values in ground_truth to plain strings."""
    def _normalize_dict(gt: Dict) -> Dict:
        if not isinstance(gt, dict):
            return gt
        result = {}
        for key, value in gt.items():
            k = _ensure_string(key)
            if isinstance(value, dict):
                result[k] = _normalize_dict(value)
            elif isinstance(value, list):
                result[k] = [
                    _normalize_dict(item) if isinstance(item, dict) else _ensure_string(item)
                    for item in value
                ]
            elif isinstance(value, (str, np.ndarray, np.str_, np.int64, np.int32, np.float64, np.float32)):
                result[k] = _ensure_string(value)
            else:
                result[k] = value
        return result

    if isinstance(ground_truth, list):
        return [_normalize_dict(item) for item in ground_truth]
    return _normalize_dict(ground_truth)


# ============================================================================
# SQL Security Check
# ============================================================================
def is_sql_readonly(sql: str) -> Tuple[bool, Optional[str]]:
    """Return (True, None) if sql is a read-only query, else (False, reason)."""
    sql_stripped = sql.strip()

    while sql_stripped.startswith(('--', '/*')):
        if sql_stripped.startswith('--'):
            newline_pos = sql_stripped.find('\n')
            if newline_pos == -1:
                return False, "SQL contains only comments"
            sql_stripped = sql_stripped[newline_pos + 1:].strip()
        else:
            end_pos = sql_stripped.find('*/')
            if end_pos == -1:
                return False, "Unclosed comment"
            sql_stripped = sql_stripped[end_pos + 2:].strip()

    if not sql_stripped:
        return False, "Empty SQL query"

    if sql_stripped.upper().startswith(ALLOWED_SQL_PREFIXES):
        return True, None

    first_word = sql_stripped.split()[0] if sql_stripped else "EMPTY"
    return False, f"SQL must start with {ALLOWED_SQL_PREFIXES}, got: {first_word}"


# ============================================================================
# SQL Extraction
# ============================================================================
def extract_final_answer_sql(solution_str: str) -> Optional[str]:
    """Extract the last SQL query from an <answer> tag in solution_str."""
    search_context = solution_str[-20000:] if len(solution_str) > 20000 else solution_str

    matches = list(re.finditer(r"<answer>(.*?)</answer>", search_context, re.DOTALL))
    if not matches:
        return None

    answer_content = matches[-1].group(1).strip()
    if not answer_content:
        return None

    for pattern in (r"'''sql\s+(.*?)\s+'''", r"```sql\s+(.*?)\s+```"):
        m = re.search(pattern, answer_content, re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1).strip()

    return answer_content.strip()


# ============================================================================
# Schema Linking Evaluation
# ============================================================================
def _compute_prf(predicted: set, ground_truth: set) -> Tuple[float, float, float]:
    """
    Compute precision, recall, and F1 between two sets.
    Both-empty case returns (1.0, 1.0, 1.0).
    """
    if not predicted and not ground_truth:
        return 1.0, 1.0, 1.0
    if not predicted or not ground_truth:
        return 0.0, 0.0, 0.0

    intersection = predicted & ground_truth
    precision = len(intersection) / len(predicted)
    recall    = len(intersection) / len(ground_truth)
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return precision, recall, f1


def _extract_columns(schema: Dict) -> set:
    """
    Extract a set of 'table.column' strings from a schema dict.
    Supports both string-list and dict-list column formats.
    """
    columns = set()
    for table, cols in schema.get("columns", {}).items():
        if not cols:
            continue
        for col in cols:
            if isinstance(col, str):
                columns.add(f"{table.lower()}.{col.lower()}")
            elif isinstance(col, dict):
                col_name = col.get("name") or col.get("column_name") or col.get("column")
                if col_name:
                    columns.add(f"{table.lower()}.{col_name.lower()}")
            else:
                try:
                    columns.add(f"{table.lower()}.{str(col).lower()}")
                except Exception:
                    print(f"[WARNING] Cannot process column: {col} (type: {type(col)})")
    return columns


def compute_schema_linking_score(
    predicted_schema: Dict,
    ground_truth_schema: Dict,
    mode: Optional[str] = None,
) -> Dict[str, float]:
    """
    Compute schema linking score between predicted and ground-truth schemas.

    Supported modes:
        f1                        – harmonic mean of precision and recall
        precision                 – prediction accuracy only
        recall                    – coverage only
        totalmatch                – 1.0 only if both tables and columns match exactly
        recall_then_precision_strict – recall=1 required; precision bucketed into [0.1, 1.0]
        recall_then_precision     – recall=1 required; reward = weighted precision directly

    Returns a dict with per-metric scores and 'total_score'.
    """
    if mode is None:
        mode = SCORE_CONFIG["schema_scoring_mode"]

    # Normalize aliases
    if mode in ('truematch', 'allmatch'):
        mode = 'totalmatch'

    weights = {
        "table":  SCORE_CONFIG["schema_table_weight"],
        "column": SCORE_CONFIG["schema_column_weight"],
    }

    pred_tables = set(t.lower() for t in predicted_schema.get("tables", []))
    gt_tables   = set(t.lower() for t in ground_truth_schema.get("tables", []))
    pred_cols   = _extract_columns(predicted_schema)
    gt_cols     = _extract_columns(ground_truth_schema)

    tp, tr, tf = _compute_prf(pred_tables, gt_tables)
    cp, cr, cf = _compute_prf(pred_cols,   gt_cols)

    if mode == "precision":
        table_metric  = tp
        column_metric = cp

    elif mode == "recall":
        table_metric  = tr
        column_metric = cr

    elif mode == "f1":
        table_metric  = tf
        column_metric = cf

    elif mode == "totalmatch":
        full_match = (tp == 1.0 and tr == 1.0 and cp == 1.0 and cr == 1.0)
        table_metric  = 1.0 if full_match else 0.0
        column_metric = 1.0 if full_match else 0.0

    elif mode == "recall_then_precision_strict":
        if tr < 1.0 or cr < 1.0:
            table_metric = column_metric = 0.0
        else:
            combined_precision = weights["table"] * tp + weights["column"] * cp
            if   combined_precision >= 1.0: reward = 1.0
            elif combined_precision >= 0.9: reward = 0.8
            elif combined_precision >= 0.8: reward = 0.6
            elif combined_precision >= 0.7: reward = 0.4
            elif combined_precision >= 0.6: reward = 0.2
            else:                           reward = 0.1
            table_metric = column_metric = reward

    elif mode == "recall_then_precision":
        if tr < 1.0 or cr < 1.0:
            table_metric = column_metric = 0.0
        else:
            combined_precision = weights["table"] * tp + weights["column"] * cp
            table_metric = column_metric = combined_precision

    else:  # fallback to f1
        table_metric  = tf
        column_metric = cf

    table_score  = weights["table"]  * table_metric
    column_score = weights["column"] * column_metric

    return {
        "table_precision":  tp,
        "table_recall":     tr,
        "table_f1":         tf,
        "column_precision": cp,
        "column_recall":    cr,
        "column_f1":        cf,
        "table_score":      table_score,
        "column_score":     column_score,
        "total_score":      table_score + column_score,
        "mode":             mode,
    }


# ============================================================================
# Format Validation
# ============================================================================
def check_single_turn_format(turn_content: str) -> Dict[str, Any]:
    """
    Validate the format of a single assistant turn.

    Returns:
        {
            "is_valid":      bool,
            "format_score":  float,   # 0.0 or 0.1
            "error_message": Optional[str]
        }
    """
    result: Dict[str, Any] = {"is_valid": False, "format_score": 0.0, "error_message": None}

    # Validate <think> tags
    if re.findall(r"<think>", turn_content).__len__() != 1 or \
       re.findall(r"</think>", turn_content).__len__() != 1:
        n_open  = len(re.findall(r"<think>",  turn_content))
        n_close = len(re.findall(r"</think>", turn_content))
        result["error_message"] = f"Invalid <think> tags: {n_open} opening, {n_close} closing"
        return result

    # Validate <action> tag
    action_matches = re.findall(r"<action>(.*?)</action>", turn_content, re.DOTALL)
    if len(action_matches) != 1:
        result["error_message"] = f"Expected exactly 1 <action> tag, found {len(action_matches)}"
        return result

    action_type = action_matches[0].strip()

    action_requirements = {
        "explore_schema":  ("<tool_call>", "tool_call"),
        "propose_schema":  ("<schema>",    "schema"),
        "generate_sql":    ("<tool_call>", "tool_call"),
        "confirm_answer":  ("<answer>",    "answer"),
    }

    if action_type not in action_requirements:
        result["error_message"] = f"Unknown action type: {action_type}"
        return result

    tag_open, tag_name = action_requirements[action_type]
    if len(re.findall(re.escape(tag_open), turn_content)) < 1:
        result["error_message"] = f"{action_type} requires <{tag_name}>"
        return result

    result["is_valid"]     = True
    result["format_score"] = SCORE_CONFIG["turn_format"]
    return result


# ============================================================================
# SQL Execution
# ============================================================================
def execute_sql_safe(
    sql: str,
    db_path: str,
    timeout: float = 30.0,
) -> Tuple[bool, Optional[list]]:
    """Execute a read-only SQL query synchronously with timeout and retry logic."""
    sql = _ensure_string(sql)

    is_readonly, _ = is_sql_readonly(sql)
    if not is_readonly or not os.path.exists(db_path):
        return False, None

    for attempt in range(SECURITY_CONFIG["max_retries"]):
        conn  = None
        timer = None
        try:
            conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True, check_same_thread=False)

            def _interrupt():
                if conn:
                    conn.interrupt()

            timer = threading.Timer(timeout, _interrupt)
            timer.start()

            cursor = conn.cursor()
            cursor.execute(sql)
            results = cursor.fetchmany(SECURITY_CONFIG["max_rows"])
            return True, results

        except sqlite3.OperationalError as e:
            if "interrupted" in str(e) and attempt < SECURITY_CONFIG["max_retries"] - 1:
                time.sleep(SECURITY_CONFIG["base_delay"] * (2 ** attempt))
                continue
            return False, None

        except Exception:
            return False, None

        finally:
            if timer:
                timer.cancel()
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    return False, None


async def execute_sql_safe_async(
    sql: str,
    db_path: str,
    timeout: float = 30.0,
    thread_pool: Optional[ThreadPoolExecutor] = None,
) -> Tuple[bool, Optional[list]]:
    """Async wrapper around execute_sql_safe."""
    pool = thread_pool if thread_pool is not None else _get_thread_pool()
    try:
        return await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(pool, execute_sql_safe, sql, db_path, timeout),
            timeout=timeout + 5.0,
        )
    except (asyncio.TimeoutError, Exception):
        return False, None


async def evaluate_sql_execution_async(
    predicted_sql: str,
    ground_truth_sql: str,
    db_path: str,
    timeout: float = 30.0,
    thread_pool: Optional[ThreadPoolExecutor] = None,
) -> Dict[str, Any]:
    """Execute predicted and ground-truth SQL in parallel and compare results."""
    (pred_ok, pred_rows), (gt_ok, gt_rows) = await asyncio.gather(
        execute_sql_safe_async(predicted_sql,   db_path, timeout, thread_pool),
        execute_sql_safe_async(ground_truth_sql, db_path, timeout, thread_pool),
    )

    result = {"is_executable": pred_ok, "is_correct": False}

    if not pred_ok or not gt_ok:
        return result

    try:
        result["is_correct"] = set(pred_rows) == set(gt_rows)
    except TypeError:
        try:
            result["is_correct"] = sorted(pred_rows) == sorted(gt_rows)
        except Exception:
            result["is_correct"] = False

    return result


# ============================================================================
# Main Scoring Function
# ============================================================================
async def compute_score_sql_async(
    solution_str: str,
    ground_truth: dict,
    db_root_path: str = None,
    timeout: float = 30.0,
    include_schema_score: bool = False,
    thread_pool: Optional[ThreadPoolExecutor] = None,
    **kwargs,
) -> float:
    """
    Compute SQL execution score (async).

    Returns:
        1.0  – correct result
        0.2  – executable but wrong result
        0.0  – not executable or not extracted
    """
    try:
        ground_truth = normalize_ground_truth(ground_truth)
        gt_target    = ground_truth.get("ground_truth", {})
        gt_sql_raw   = gt_target.get("target", "")
        gt_sql       = gt_sql_raw[0] if isinstance(gt_sql_raw, list) else gt_sql_raw

        db_id   = ground_truth.get("data_source", "")
        db_path = os.path.join(db_root_path, db_id, f"{db_id}.sqlite") if db_root_path and db_id else None

        predicted_sql = extract_final_answer_sql(solution_str)
        if not predicted_sql or not db_path:
            return 0.0

        eval_result = await evaluate_sql_execution_async(predicted_sql, gt_sql, db_path, timeout, thread_pool)

        if eval_result["is_correct"]:
            return SCORE_CONFIG["correct_execution"]
        if eval_result["is_executable"]:
            return SCORE_CONFIG["executable_sql"]
        return SCORE_CONFIG["extracted_answer"]

    except Exception as e:
        if random.randint(1, 100) == 1:
            print(f"[ERROR] compute_score_sql_async failed: {e}")
        return 0.0


# ============================================================================
# Cleanup
# ============================================================================
def cleanup() -> None:
    """Shut down the global thread pool."""
    global _reward_thread_pool
    if _reward_thread_pool is not None:
        _reward_thread_pool.shutdown(wait=True)
        _reward_thread_pool = None