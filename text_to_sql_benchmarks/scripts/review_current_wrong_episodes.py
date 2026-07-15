#!/usr/bin/env python3
"""Independently review current two-stage Text-to-SQL wrong episodes.

Only the current run's wrong_episodes.pretty.json is read. Earlier audits,
error-family maps, and previous predictions are intentionally never loaded.
Each case receives a first evidence-grounded review and an independent critic
pass before its audit record is saved.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import time
from pathlib import Path
from typing import Any

import httpx


DEFAULT_MODEL = "/root/autodl-tmp/text_to_sql_benchmarks/models/Qwen3___5-4B"
DEFAULT_BASE_URL = "http://127.0.0.1:8000/v1"

AUDIT_FIELDS = (
    "精确标签",
    "最早致命轮次",
    "主根因",
    "轨迹溯源",
    "执行证据",
    "伴随问题",
    "最小修复",
)

ERROR_FAMILIES = (
    "JOIN 键、桥表与实体角色错误",
    "JOIN 放大后的重复计数或加权",
    "JOIN 保留性与数据覆盖收缩",
    "表、字段、值与实体层级链接错位",
    "过滤条件、布尔逻辑与 NULL 语义",
    "日期时间、年龄与字符串位置解析",
    "数值公式、类型、尺度与精度",
    "目标实体粒度与聚合单位",
    "分组、子查询与多步查询结构",
    "排序、Top-k、并列与极值方向",
    "输出契约、关系形状与答案编码",
    "记忆、协议、预算与 fallback 失控",
    "SQL 语法、执行或字段引用错误",
    "其他经证据确认的语义错误",
)


def parse_args() -> argparse.Namespace:
    repo = Path(__file__).resolve().parents[1]
    result_dir = repo / "results/qwen35-4b-arcwise-plat-full-default20-10-final-schema-prompt-20260714"
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=result_dir / "wrong_episodes.pretty.json")
    parser.add_argument(
        "--output",
        type=Path,
        default=result_dir / "manual_root_cause_audit_174.review.jsonl",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--api-key", default="EMPTY")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-tokens", type=int, default=1800)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--qid", action="append", default=None)
    return parser.parse_args()


def compact(value: Any, limit: int) -> str:
    text = re.sub(r"\s+", " ", "" if value is None else str(value)).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "..."


def result_to_text(result: dict[str, Any] | None, max_rows: int = 35) -> str:
    if not isinstance(result, dict):
        return "（无结果对象）"
    if not result.get("ok", False):
        return f"ERROR: {result.get('error') or 'unknown error'}"
    columns = list(result.get("columns") or [])
    rows = list(result.get("rows") or [])
    lines: list[str] = []
    if columns:
        lines.append("\t".join(str(column) for column in columns))
    for row in rows[:max_rows]:
        values = row if isinstance(row, list) else [row]
        lines.append("\t".join("" if value is None else str(value) for value in values))
    row_count = result.get("row_count", result.get("row_count_preview", len(rows)))
    suffix = f"rows={row_count}"
    if result.get("truncated"):
        suffix += ", truncated=True"
    lines.append(suffix)
    return "\n".join(lines)


def tool_result_summary(result: dict[str, Any] | None) -> str:
    if not isinstance(result, dict):
        return "无工具结果对象"
    if not result.get("ok", False):
        return f"执行失败：{compact(result.get('error'), 420)}"
    columns = result.get("columns") or []
    rows = result.get("rows") or []
    count = result.get("row_count", result.get("row_count_preview", len(rows)))
    return f"执行成功；columns={columns}；rows={count}；preview={compact(rows[:4], 700)}"


def source_think(round_data: dict[str, Any]) -> str:
    think = round_data.get("think")
    if isinstance(think, str) and think.strip():
        return think.strip()
    raw = ((round_data.get("debug") or {}).get("raw_message") or "")
    match = re.search(r"<think>\s*(.*?)\s*</think>", raw, re.S)
    return match.group(1).strip() if match else ""


def build_case_payload(episode: dict[str, Any]) -> dict[str, Any]:
    rounds: list[dict[str, Any]] = []
    for round_data in episode.get("rounds") or []:
        tool_call = round_data.get("tool_call") if isinstance(round_data.get("tool_call"), dict) else {}
        rounds.append(
            {
                "round": round_data.get("round"),
                "stage": round_data.get("stage"),
                "think": source_think(round_data),
                "tool_call": tool_call,
                "tool_result": tool_result_summary(round_data.get("tool_result")),
                "memory_delta": round_data.get("memory_delta") or "",
                "error": round_data.get("error"),
                "stage_violation": bool(round_data.get("stage_violation")),
            }
        )
    return {
        "question_id": str(episode.get("question_id")),
        "db_id": episode.get("db_id"),
        "question": episode.get("question"),
        "evidence": episode.get("evidence") or "",
        "gold_sql": episode.get("gold_sql") or "",
        "pred_sql": episode.get("pred_sql") or "",
        "gold_result": result_to_text(episode.get("gold_result")),
        "pred_result": result_to_text(episode.get("pred_result")),
        "run_status": {
            "round_count": episode.get("round_count"),
            "terminated": episode.get("terminated"),
            "used_fallback_sql": episode.get("used_fallback_sql"),
            "auto_stage_transition": episode.get("auto_stage_transition"),
            "sql_stage_budget_exhausted": episode.get("sql_stage_budget_exhausted"),
            "schema_rounds_used": episode.get("schema_rounds_used"),
            "sql_rounds_used": episode.get("sql_rounds_used"),
            "returns_used": episode.get("returns_used"),
            "pred_error": episode.get("pred_error"),
            "gold_error": episode.get("gold_error"),
        },
        "stage_transitions": episode.get("stage_transitions") or [],
        "schema_evidence": episode.get("schema_evidence"),
        "successful_candidates": episode.get("successful_candidates") or [],
        "rounds": rounds,
    }


def extract_json(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    start = cleaned.find("{")
    if start < 0:
        raise ValueError(f"JSON object not found: {cleaned[:500]}")
    value, _ = json.JSONDecoder().raw_decode(cleaned[start:])
    if not isinstance(value, dict):
        raise ValueError("Audit response must be a JSON object")
    return value


def normalise_audit(value: dict[str, Any], qid: str) -> dict[str, Any]:
    family = str(value.get("error_family") or "其他经证据确认的语义错误").strip()
    if family not in ERROR_FAMILIES:
        family = "其他经证据确认的语义错误"
    raw_audit = value.get("audit") if isinstance(value.get("audit"), dict) else {}
    audit = {
        field: str(raw_audit.get(field) or "无法根据当前证据确认").strip()
        for field in AUDIT_FIELDS
    }
    return {
        "question_id": qid,
        "error_family": family,
        "audit": audit,
        "confidence": str(value.get("confidence") or "medium").strip().lower(),
        "needs_counterfactual_sql": bool(value.get("needs_counterfactual_sql", False)),
        "counterfactual_reason": str(value.get("counterfactual_reason") or "").strip(),
        "review_notes": str(value.get("review_notes") or "").strip(),
    }


REVIEWER_SYSTEM_PROMPT = f"""你是独立、严谨的 Text-to-SQL 错题审计员。你正在审查一批新的运行结果。
你绝不能使用、推测或引用任何其他 run、旧错误族、旧标签或旧审计结论；只能使用本次提供的 case JSON。

审计原则：
1. 每题仅选一个最能解释最终 pred/gold 执行差异的主机制族；伴随瑕疵必须写在“伴随问题”。
2. “最早致命轮次”必须引用当前轨迹中的具体 Round；若现有轨迹无法证明更早轮次，必须诚实写“无法从当前轨迹定位，最终 pred_sql 已证实错误”。
3. “执行证据”必须以 gold_result/pred_result 或明确的执行报错为依据，不能捏造数据库行或列。
4. 如果 pred SQL 已执行成功但语义仍错，不能笼统归为执行错误。
5. 如果正确答案在中途成功 execute_sql 中出现、但后续终止选择或重写把它改坏，必须把该轨迹事件作为主因或伴随问题。
6. “最小修复”应是能直接消除本题主偏差的最小 SQL/流程变更，而不是泛泛地“改进模型”。

主机制族必须严格从以下列表选择一个：
{json.dumps(ERROR_FAMILIES, ensure_ascii=False)}

只输出合法 JSON，不能输出 Markdown、解释或 think。严格结构：
{{
  "error_family": "...",
  "confidence": "high|medium|low",
  "needs_counterfactual_sql": false,
  "counterfactual_reason": "...",
  "review_notes": "...",
  "audit": {{
    "精确标签": "...",
    "最早致命轮次": "...",
    "主根因": "...",
    "轨迹溯源": "...",
    "执行证据": "...",
    "伴随问题": "...",
    "最小修复": "..."
  }}
}}"""


CRITIC_SYSTEM_PROMPT = f"""你是第二位独立的 Text-to-SQL 根因审计复核员。
你只能使用本次 case JSON 与候选审计 JSON，不得引用其他 run、旧标签、旧错误族或任何未提供的数据库事实。

逐项检查候选审计：
- 主根因是否真正解释 pred/gold 的执行差异；
- 最早致命轮次是否在当前轨迹中有证据；
- 执行证据是否没有编造；
- 伴随问题是否没有抢占主因；
- 最小修复是否确实针对主因。

如果候选有任何不严谨之处，直接改正全部相关字段。若无法确认，应明确写“无法根据当前证据确认”，并把 confidence 降为 low；不可用旧结论补全。
主机制族必须从以下列表选择一个：
{json.dumps(ERROR_FAMILIES, ensure_ascii=False)}

只输出与候选相同结构的合法 JSON，不能输出 Markdown、解释或 think。"""


def chat_json(
    client: httpx.Client,
    *,
    base_url: str,
    api_key: str,
    model: str,
    system: str,
    user: str,
    max_tokens: int,
    retries: int,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0.0,
                    "top_p": 1.0,
                    "max_tokens": max_tokens,
                    "chat_template_kwargs": {"enable_thinking": False},
                },
                timeout=360,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"].get("content") or ""
            return extract_json(content)
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(str(last_error))


def review_case(episode: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    payload = build_case_payload(episode)
    qid = str(episode.get("question_id"))
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    with httpx.Client(timeout=390, trust_env=False) as client:
        first = chat_json(
            client,
            base_url=args.base_url,
            api_key=args.api_key,
            model=args.model,
            system=REVIEWER_SYSTEM_PROMPT,
            user=f"请独立审计以下当前 case：\n{payload_json}",
            max_tokens=args.max_tokens,
            retries=args.retries,
        )
        candidate = normalise_audit(first, qid)
        second = chat_json(
            client,
            base_url=args.base_url,
            api_key=args.api_key,
            model=args.model,
            system=CRITIC_SYSTEM_PROMPT,
            user=(
                "当前 case：\n"
                + payload_json
                + "\n\n候选审计：\n"
                + json.dumps(candidate, ensure_ascii=False, separators=(",", ":"))
            ),
            max_tokens=args.max_tokens,
            retries=args.retries,
        )
    audited = normalise_audit(second, qid)
    audited.update(
        {
            "db_id": episode.get("db_id"),
            "audit_status": "重新独立审查完成",
            "reviewer_passed": True,
            "source": "current wrong_episodes only",
        }
    )
    return audited


def load_completed(path: Path) -> set[str]:
    if not path.exists():
        return set()
    completed: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            completed.add(str(json.loads(line)["question_id"]))
        except Exception:
            continue
    return completed


def main() -> int:
    args = parse_args()
    episodes = json.loads(args.input.read_text(encoding="utf-8"))
    episodes = [episode for episode in episodes if not episode.get("correct")]
    if args.qid:
        wanted = {str(qid) for qid in args.qid}
        episodes = [episode for episode in episodes if str(episode.get("question_id")) in wanted]
    episodes.sort(key=lambda episode: (str(episode.get("db_id")), int(episode.get("question_id"))))
    if args.limit is not None:
        episodes = episodes[: args.limit]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    completed = load_completed(args.output) if args.resume else set()
    pending = [episode for episode in episodes if str(episode.get("question_id")) not in completed]
    print(json.dumps({"total": len(episodes), "completed": len(completed), "pending": len(pending)}, ensure_ascii=False), flush=True)

    mode = "a" if args.resume and args.output.exists() else "w"
    with args.output.open(mode, encoding="utf-8") as output:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            futures = {executor.submit(review_case, episode, args): episode for episode in pending}
            for index, future in enumerate(concurrent.futures.as_completed(futures), start=1):
                episode = futures[future]
                qid = str(episode.get("question_id"))
                try:
                    reviewed = future.result()
                except Exception as exc:
                    reviewed = {
                        "question_id": qid,
                        "db_id": episode.get("db_id"),
                        "audit_status": "重新独立审查失败",
                        "reviewer_passed": False,
                        "error": str(exc),
                        "error_family": "其他经证据确认的语义错误",
                        "confidence": "low",
                        "needs_counterfactual_sql": True,
                        "counterfactual_reason": "审计模型调用失败，需要人工复核。",
                        "review_notes": "",
                        "audit": {field: "审计调用失败，待人工复核" for field in AUDIT_FIELDS},
                        "source": "current wrong_episodes only",
                    }
                output.write(json.dumps(reviewed, ensure_ascii=False) + "\n")
                output.flush()
                print(
                    f"[{index}/{len(pending)}] qid={qid} db={episode.get('db_id')} "
                    f"status={reviewed.get('audit_status')} family={reviewed.get('error_family')}",
                    flush=True,
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
