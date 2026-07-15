#!/usr/bin/env python3
"""Draft independent root-cause audits for the current two-stage wrong episodes.

The script intentionally accepts only the current run's episode file. It does
not read any legacy audit, error-family mapping, or previous wrong-analysis
artifact. Each episode is diagnosed from its own question, SQL, execution
results, schema evidence, and trajectory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import httpx


DEFAULT_RESULTS = Path(
    "/root/autodl-tmp/text_to_sql_benchmarks/results/"
    "qwen35-4b-arcwise-plat-full-default20-10-final-schema-prompt-20260714"
)
DEFAULT_MODEL = "/root/autodl-tmp/text_to_sql_benchmarks/models/Qwen3___5-4B"
AUDIT_FIELDS = (
    "精确标签",
    "最早致命轮次",
    "主根因",
    "轨迹溯源",
    "执行证据",
    "伴随问题",
    "最小修复",
    "建议错误族",
    "置信度",
    "需补充验证",
)
PRINT_LOCK = threading.Lock()
AUDIT_JSON_SCHEMA = {
    "name": "current_episode_root_cause_audit",
    "schema": {
        "type": "object",
        "properties": {field: {"type": "string"} for field in AUDIT_FIELDS},
        "required": list(AUDIT_FIELDS),
        "additionalProperties": False,
    },
}


SYSTEM_PROMPT = """You are independently auditing a failed Text-to-SQL agent episode.

Use only the evidence supplied for this one current episode. Do not rely on any
previous audit, previous error taxonomy, qid memory, or assumed benchmark
pattern. Work from the question, evidence, gold SQL, predicted SQL, execution
results, schema evidence, and complete round trajectory.

Your task is forensic, not cosmetic:
1. Identify the earliest decision that made the final answer wrong.
2. Separate the primary root cause from later consequences and side issues.
3. Ground the diagnosis in concrete SQL/result/trajectory evidence.
4. If gold appears invalid or evaluation is a false negative, say so explicitly.
5. Do not call a JOIN an amplification error unless the joined multiplicity
   actually changes the relevant aggregation.
6. Do not infer a cause merely from SQL text difference when results establish
   semantic equivalence.

Return exactly one JSON object with these Chinese string keys:
精确标签, 最早致命轮次, 主根因, 轨迹溯源, 执行证据, 伴随问题, 最小修复,
建议错误族, 置信度, 需补充验证.

All values must be complete Chinese prose. “最早致命轮次” must name a concrete
round when supported, otherwise state that the fatal error is only observable in
the final SQL. “建议错误族” must be derived from this episode's mechanism; do
not choose from or imitate a legacy taxonomy. “需补充验证” must be “无” when
the supplied evidence is sufficient, otherwise list the exact SQLite check that
would resolve uncertainty. Output JSON only."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_RESULTS / "wrong_episodes.pretty.json")
    parser.add_argument("--output", type=Path, default=DEFAULT_RESULTS / "manual_root_cause_audit.draft.json")
    parser.add_argument("--cache", type=Path, default=DEFAULT_RESULTS / "manual_root_cause_audit.draft.cache.json")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--api-key", default="EMPTY")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-tokens", type=int, default=2200)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--question-id", action="append")
    parser.add_argument("--db-id", action="append")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compact_result(result: dict[str, Any] | None, max_rows: int = 20) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    rows = list(result.get("rows") or [])
    return {
        "ok": result.get("ok"),
        "error": result.get("error"),
        "columns": result.get("columns") or [],
        "rows": rows[:max_rows],
        "row_count": result.get("row_count", result.get("row_count_preview", len(rows))),
        "truncated": result.get("truncated", False),
    }


def compact_tool_result(result: dict[str, Any] | None) -> Any:
    if not isinstance(result, dict):
        return result
    if "rows" in result or "columns" in result:
        return compact_result(result, max_rows=10)
    return result


def compact_text(value: Any, limit: int) -> Any:
    if not isinstance(value, str) or len(value) <= limit:
        return value
    return value[:limit].rstrip() + f"\n...[truncated {len(value) - limit} chars]"


def build_dossier(episode: dict[str, Any]) -> dict[str, Any]:
    rounds: list[dict[str, Any]] = []
    for row in episode.get("rounds") or []:
        tool_call = row.get("tool_call") if isinstance(row.get("tool_call"), dict) else None
        rounds.append(
            {
                "round": row.get("round"),
                "stage": row.get("stage"),
                "think": compact_text(row.get("think"), 3000),
                "tool_call": tool_call,
                "tool_result": compact_tool_result(row.get("tool_result")),
                "memory_delta": compact_text(row.get("memory_delta"), 4000),
                "error": row.get("error"),
                "stage_violation": row.get("stage_violation"),
                "compressor_error": row.get("compressor_error"),
            }
        )
    successful_candidates = []
    for candidate in episode.get("successful_candidates") or []:
        if not isinstance(candidate, dict):
            continue
        successful_candidates.append(
            {
                "round": candidate.get("round"),
                "sql": candidate.get("sql"),
                "result": compact_result(candidate.get("result"), max_rows=10),
            }
        )
    return {
        "question_id": str(episode.get("question_id")),
        "db_id": episode.get("db_id"),
        "question": episode.get("question"),
        "external_evidence": episode.get("evidence"),
        "gold_sql": episode.get("gold_sql"),
        "pred_sql": episode.get("pred_sql"),
        "gold_result": compact_result(episode.get("gold_result"), max_rows=20),
        "pred_result": compact_result(episode.get("pred_result"), max_rows=20),
        "strict_correct": episode.get("strict_correct"),
        "projection_relaxed_correct": episode.get("projection_relaxed_correct"),
        "pred_error": episode.get("pred_error"),
        "gold_error": episode.get("gold_error"),
        "terminated": episode.get("terminated"),
        "used_fallback_sql": episode.get("used_fallback_sql"),
        "auto_stage_transition": episode.get("auto_stage_transition"),
        "sql_stage_budget_exhausted": episode.get("sql_stage_budget_exhausted"),
        "stage_transitions": episode.get("stage_transitions") or [],
        "schema_evidence": episode.get("schema_evidence"),
        "successful_candidates": successful_candidates,
        "verified_join_pairs": episode.get("verified_join_pairs") or [],
        "rounds": rounds,
    }


def strip_thinking(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()


def extract_json(text: str) -> dict[str, Any]:
    raw = strip_thinking(text)
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, flags=re.S)
    if fenced:
        raw = fenced.group(1)
    else:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start : end + 1]
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("audit response is not a JSON object")
    missing = [field for field in AUDIT_FIELDS if not str(value.get(field) or "").strip()]
    if missing:
        raise ValueError(f"audit response missing fields: {missing}")
    return {field: str(value[field]).strip() for field in AUDIT_FIELDS}


def call_auditor(
    client: httpx.Client,
    episode: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    dossier = build_dossier(episode)
    user_prompt = (
        "Independently audit this current episode. The JSON below is the complete "
        "evidence package available for the judgment.\n\n"
        + json.dumps(dossier, ensure_ascii=False, indent=2, default=str)
    )
    last_error: Exception | None = None
    for attempt in range(args.retries + 1):
        try:
            response = client.post(
                f"{args.base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {args.api_key}"},
                json={
                    "model": args.model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.0,
                    "top_p": 1.0,
                    "max_tokens": args.max_tokens,
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": AUDIT_JSON_SCHEMA,
                    },
                    "chat_template_kwargs": {"enable_thinking": False},
                },
                timeout=300,
            )
            response.raise_for_status()
            message = response.json()["choices"][0]["message"]
            raw = message.get("content") or ""
            reasoning = message.get("reasoning_content") or ""
            return {
                "audit": extract_json(raw),
                "raw_message": raw,
                "reasoning_content": reasoning,
                "dossier_hash": stable_hash(dossier),
            }
        except Exception as exc:
            last_error = exc
            if attempt < args.retries:
                time.sleep(2 + attempt)
    raise RuntimeError(f"audit generation failed: {last_error}")


def load_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"episodes": {}}
    value = json.loads(path.read_text(encoding="utf-8"))
    value.setdefault("episodes", {})
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    temp.replace(path)


def select_episodes(episodes: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    selected = episodes
    if args.question_id:
        qids = {str(qid) for qid in args.question_id}
        selected = [episode for episode in selected if str(episode.get("question_id")) in qids]
    if args.db_id:
        db_ids = set(args.db_id)
        selected = [episode for episode in selected if episode.get("db_id") in db_ids]
    selected = sorted(selected, key=lambda row: (str(row.get("db_id")), int(row.get("question_id") or 0)))
    if args.limit is not None:
        selected = selected[: args.limit]
    return selected


def main() -> int:
    args = parse_args()
    episodes = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(episodes, list):
        raise ValueError(f"Expected JSON list: {args.input}")
    selected = select_episodes(episodes, args)
    cache = load_cache(args.cache)

    pending: list[dict[str, Any]] = []
    for episode in selected:
        qid = str(episode.get("question_id"))
        dossier_hash = stable_hash(build_dossier(episode))
        cached = cache["episodes"].get(qid)
        if not args.force and cached and cached.get("dossier_hash") == dossier_hash and cached.get("audit"):
            continue
        pending.append(episode)

    print(
        json.dumps(
            {
                "input": str(args.input),
                "selected": len(selected),
                "cached": len(selected) - len(pending),
                "pending": len(pending),
                "workers": args.workers,
                "legacy_audit_inputs": [],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    cache_lock = threading.Lock()
    completed = 0
    failed: dict[str, str] = {}
    with httpx.Client(trust_env=False, timeout=300) as client:
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            futures = {executor.submit(call_auditor, client, episode, args): episode for episode in pending}
            for future in as_completed(futures):
                episode = futures[future]
                qid = str(episode.get("question_id"))
                try:
                    result = future.result()
                except Exception as exc:
                    failed[qid] = str(exc)
                    with PRINT_LOCK:
                        print(
                            f"[ERROR] qid={qid} db={episode.get('db_id')} error={exc}",
                            flush=True,
                        )
                    continue
                result.update({"question_id": qid, "db_id": episode.get("db_id")})
                with cache_lock:
                    cache["episodes"][qid] = result
                    write_json(args.cache, cache)
                completed += 1
                with PRINT_LOCK:
                    print(
                        f"[{completed}/{len(pending)}] qid={qid} db={episode.get('db_id')} "
                        f"family={result['audit']['建议错误族']}",
                        flush=True,
                    )

    output_records: list[dict[str, Any]] = []
    missing_qids: list[str] = []
    for episode in selected:
        qid = str(episode.get("question_id"))
        cached = cache["episodes"].get(qid)
        if not cached or not cached.get("audit"):
            missing_qids.append(qid)
            continue
        output_records.append(
            {
                "question_id": qid,
                "db_id": episode.get("db_id"),
                "audit": cached["audit"],
                "dossier_hash": cached.get("dossier_hash"),
                "source": "current_episode_independent_review_draft",
            }
        )
    write_json(args.output, output_records)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "records": len(output_records),
                "failed": failed,
                "missing_qids": missing_qids,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 1 if missing_qids else 0


if __name__ == "__main__":
    raise SystemExit(main())
