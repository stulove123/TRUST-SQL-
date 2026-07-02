from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import httpx

from run_qwen35_arcwise_trustsql import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    build_format_feedback,
    build_initial_messages,
    evaluate,
    execute_tool_sql,
    extract_action,
    extract_answer_sql,
    extract_schema_json,
    extract_sql,
    extract_think,
    extract_tool_call,
    find_db_path,
    format_tool_result,
    is_metadata_query,
    normalize_think_tags,
    resolve_path,
)


def call_model_raw(
    client: httpx.Client,
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    temperature: float,
    top_p: float,
    enable_thinking: bool,
) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
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
    raw_message = payload["choices"][0]["message"]
    return raw_message, time.perf_counter() - started


def run_episode_raw(
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
    terminated = False
    total_latency = 0.0

    for round_idx in range(args.max_rounds):
        raw_message, latency = call_model_raw(
            client,
            base_url=args.base_url,
            api_key=args.api_key,
            model=args.model,
            messages=messages,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            top_p=args.top_p,
            enable_thinking=args.enable_thinking,
        )
        total_latency += latency

        assistant_text = normalize_think_tags(raw_message.get("content") or "")
        reasoning_content = (
            raw_message.get("reasoning_content")
            or raw_message.get("reasoning")
            or raw_message.get("reasoning_text")
        )
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
            "raw_message": raw_message,
            "latency": latency,
        }

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

    episode = {
        "pred_sql": pred_sql or "",
        "terminated": terminated,
        "rounds": len(conversation),
        "conversation": conversation,
        "schema_proposals": schema_proposals,
        "total_llm_latency": total_latency,
        "used_fallback_sql": bool(pred_sql and not terminated),
    }

    episode.update(evaluate(db_path, pred_sql or "", sample["SQL"], args.sql_timeout, args.eval_result_max_rows))
    return episode


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/arcwise_plat_full_with_diff.json")
    parser.add_argument("--db-root", default="/root/autodl-tmp/DeepEye-SQL/data/arcwise_plat/dev/dev_databases")
    parser.add_argument("--out-dir", default="results/tmp-qwen35-raw-message-3")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--api-key", default="EMPTY")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--max-rounds", type=int, default=10)
    parser.add_argument("--max-observation-chars", type=int, default=6000)
    parser.add_argument("--tool-max-rows", type=int, default=80)
    parser.add_argument("--sql-timeout", type=float, default=60.0)
    parser.add_argument("--eval-result-max-rows", type=int, default=50)
    parser.add_argument("--fallback-to-last-generated", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--enforce-metadata-only-explore", action="store_true")
    parser.add_argument("--enable-thinking", action=argparse.BooleanOptionalAction, default=False)
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    data_path = resolve_path(args.data, script_dir)
    db_root = resolve_path(args.db_root, script_dir)
    out_dir = resolve_path(args.out_dir, script_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    details_path = out_dir / "details_raw_message.jsonl"
    summary_path = out_dir / "summary.json"

    data = json.load(data_path.open(encoding="utf-8"))[: args.limit]
    correct_count = 0

    with httpx.Client(trust_env=False, timeout=300) as client, details_path.open("w", encoding="utf-8") as details_f:
        for idx, sample in enumerate(data, start=1):
            episode = run_episode_raw(client, sample, db_root, args)
            correct_count += int(episode.get("correct", 0))
            record = {
                "idx": idx,
                "question_id": str(sample["question_id"]),
                "db_id": sample["db_id"],
                "question": sample["question"],
                "evidence": sample.get("evidence"),
                "gold_sql": sample["SQL"],
                **episode,
            }
            details_f.write(json.dumps(record, ensure_ascii=False) + "\n")
            details_f.flush()
            print(
                f"[{idx}/{len(data)}] qid={sample['question_id']} "
                f"correct={record['correct']} rounds={record['rounds']} "
                f"terminated={record['terminated']}"
            )

    summary = {
        "data": str(data_path),
        "db_root": str(db_root),
        "model": args.model,
        "base_url": args.base_url,
        "total": len(data),
        "correct": correct_count,
        "execution_accuracy": correct_count / len(data) if data else 0.0,
        "eval_result_max_rows": args.eval_result_max_rows,
        "enable_thinking": args.enable_thinking,
        "saved_raw_message": True,
        "details_path": str(details_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
