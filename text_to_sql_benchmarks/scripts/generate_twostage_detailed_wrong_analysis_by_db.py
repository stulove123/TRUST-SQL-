#!/usr/bin/env python3
"""Generate detailed Chinese wrong_analysis reports for two-stage episodes.

This script is intentionally heavier than the lightweight structural report
generator.  For each wrong episode it asks the local OpenAI-compatible model to
produce:

- concrete Chinese root-cause analysis;
- Chinese translation of every round's `<think>`;
- Chinese translation of every round's memory delta.

The full per-round memory-before and memory-after blocks are then reconstructed
by program append, matching the two-stage runner's delta-memory design.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import time
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

import httpx


DEFAULT_RESULT_DIR = Path(
    "/root/autodl-tmp/text_to_sql_benchmarks/results/"
    "qwen35-4b-arcwise-plat-twostage-agent-full-latest-s12-s6-round-action-memory"
)
DEFAULT_MODEL = "/root/autodl-tmp/text_to_sql_benchmarks/models/Qwen3___5-4B"
SPACE_RE = re.compile(r"\s+")


def compact(value: Any, limit: int = 180) -> str:
    if value is None:
        return ""
    text = SPACE_RE.sub(" ", str(value).replace("\r", " ").replace("\n", " ")).strip()
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "..."
    return text


def md_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", "<br>")


def fence(value: Any, lang: str = "text") -> str:
    text = "" if value is None else str(value)
    text = text.replace("```", "``\\`")
    return f"```{lang}\n{text}\n```"


def json_fence(value: Any) -> str:
    return fence(json.dumps(value, ensure_ascii=False, indent=2), "json")


def sql_fence(sql: Any) -> str:
    sql_text = "" if sql is None else str(sql).strip()
    return fence(sql_text if sql_text else "（空）", "sql")


def stable_hash(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def load_episodes(path: Path) -> list[dict[str, Any]]:
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON list or JSONL file: {path}")
    return data


def load_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"episodes": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_cache(path: Path, cache: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def strip_think_tags(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    return text


def extract_json(text: str) -> Any:
    raw = strip_think_tags(text)
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", raw, re.S)
    if fence_match:
        raw = fence_match.group(1)
    else:
        start_obj = raw.find("{")
        start_arr = raw.find("[")
        starts = [idx for idx in (start_obj, start_arr) if idx >= 0]
        if starts:
            start = min(starts)
            end_obj = raw.rfind("}")
            end_arr = raw.rfind("]")
            end = max(end_obj, end_arr)
            raw = raw[start : end + 1]
    return json.loads(raw)


def call_model_json(
    client: httpx.Client,
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    retries: int = 2,
) -> Any:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": 0.0,
                    "top_p": 1.0,
                    "max_tokens": max_tokens,
                    "chat_template_kwargs": {"enable_thinking": False},
                },
                timeout=240,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"].get("content") or ""
            return extract_json(content)
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(2 + attempt)
    raise RuntimeError(f"LLM JSON call failed: {last_error}")


def call_model_text(
    client: httpx.Client,
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    retries: int = 2,
) -> str:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": 0.0,
                    "top_p": 1.0,
                    "max_tokens": max_tokens,
                    "chat_template_kwargs": {"enable_thinking": False},
                },
                timeout=240,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"].get("content") or ""
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(2 + attempt)
    raise RuntimeError(f"LLM text call failed: {last_error}")


def result_columns(result: dict[str, Any] | None) -> list[str]:
    return list((result or {}).get("columns") or [])


def result_rows(result: dict[str, Any] | None) -> list[Any]:
    return list((result or {}).get("rows") or [])


def result_row_count(result: dict[str, Any] | None) -> int | None:
    if not isinstance(result, dict):
        return None
    if "row_count" in result:
        return result.get("row_count")
    if "row_count_preview" in result:
        return result.get("row_count_preview")
    return len(result.get("rows") or [])


def rowset(rows: list[Any]) -> set[tuple[Any, ...]]:
    normalized: set[tuple[Any, ...]] = set()
    for row in rows or []:
        if isinstance(row, list):
            normalized.add(tuple(row))
        else:
            normalized.add((row,))
    return normalized


def projection_match(
    source_rows: list[Any],
    source_col_count: int,
    target_rows: list[Any],
    target_col_count: int,
    max_combinations: int = 5000,
) -> tuple[bool, tuple[int, ...] | None]:
    if target_col_count > source_col_count:
        return False, None
    if source_col_count == target_col_count:
        ok = rowset(source_rows) == rowset(target_rows)
        return ok, tuple(range(source_col_count)) if ok else None
    if not source_rows and not target_rows:
        return True, tuple(range(target_col_count))
    if math.comb(source_col_count, target_col_count) > max_combinations:
        return False, None
    target = rowset(target_rows)
    for idxs in combinations(range(source_col_count), target_col_count):
        projected = set()
        for row in source_rows or []:
            if not isinstance(row, list):
                row = [row]
            projected.add(tuple(row[i] for i in idxs))
        if projected == target:
            return True, idxs
    return False, None


def result_to_text(result: dict[str, Any] | None, max_rows: int = 50) -> str:
    if not isinstance(result, dict):
        return "（无结果对象）"
    if not result.get("ok", False):
        return f"ERROR: {result.get('error')}"
    cols = result_columns(result)
    rows = result_rows(result)
    lines: list[str] = []
    if cols:
        lines.append("\t".join(str(c) for c in cols))
    for row in rows[:max_rows]:
        if isinstance(row, list):
            lines.append("\t".join("" if v is None else str(v) for v in row))
        else:
            lines.append("" if row is None else str(row))
    row_count = result_row_count(result)
    suffix = f"rows={row_count if row_count is not None else len(rows)}"
    suffix += ", truncated=True" if result.get("truncated") else ", truncated=False"
    if rows and len(rows) > max_rows:
        suffix += f", shown={max_rows}"
    lines.append(suffix)
    return "\n".join(lines)


def summarize_tool_call_zh(tool_call: dict[str, Any] | None) -> str:
    if not isinstance(tool_call, dict):
        return "模型未给出可解析工具调用"
    name = tool_call.get("name")
    args = tool_call.get("arguments") or {}
    if name == "list_table_name":
        return "列出数据库表名"
    if name == "get_table_metadata":
        return f"查看 `{args.get('table')}` 元数据"
    if name == "inspect_value":
        return f"探查 `{args.get('table')}.{args.get('column')}` 真实取值"
    if name == "inspect_foreign_key":
        table = args.get("table")
        return f"查看 `{table}` 外键关系" if table else "查看全库外键关系"
    if name == "inspect_join_candidate":
        return "探查候选 join 关系"
    if name == "execute_sub_sql":
        return f"执行语义子问题 SQL：{compact(args.get('purpose'), 120)}"
    if name == "execute_sql":
        return f"执行完整候选 SQL：{compact(args.get('sql'), 180)}"
    if name == "return_to_schema_stage":
        return f"回到 schema 阶段补查：{compact(args.get('reason') or args.get('needed_info'), 140)}"
    if name == "terminate_first_stage":
        return "提交第一阶段 schema 证据并进入 SQL 阶段"
    if name == "terminate_second_stage":
        return "提交最终 SQL 并终止"
    return f"{name}({compact(json.dumps(args, ensure_ascii=False), 160)})"


def source_think_text(rd: dict[str, Any]) -> str:
    think = rd.get("think") or ""
    if think.strip():
        return think
    raw_message = (rd.get("debug") or {}).get("raw_message") or ""
    return raw_message.strip()


def tool_result_summary_zh(result: dict[str, Any] | None) -> str:
    if not isinstance(result, dict):
        return "该轮没有结构化工具结果，通常是终止工具或格式反馈。"
    if not result.get("ok", False):
        return f"工具执行失败：{compact(result.get('error'), 180)}"
    cols = result_columns(result)
    row_count = result_row_count(result)
    parts = ["工具执行成功"]
    if cols:
        parts.append("返回列：" + ", ".join(f"`{c}`" for c in cols[:6]))
    if row_count is not None:
        parts.append(f"返回/预览 {row_count} 行")
    if result.get("truncated"):
        parts.append("结果被截断")
    return "；".join(parts) + "。"


def build_case_payload(ep: dict[str, Any], max_rounds_for_analysis: int = 18) -> dict[str, Any]:
    rounds = []
    for rd in (ep.get("rounds") or [])[:max_rounds_for_analysis]:
        rounds.append(
            {
                "round": rd.get("round"),
                "stage": rd.get("stage"),
                "think": source_think_text(rd),
                "tool_call": rd.get("tool_call"),
                "tool_result_summary": tool_result_summary_zh(rd.get("tool_result")),
                "tool_result_preview": result_to_text(rd.get("tool_result"), max_rows=8),
                "memory_delta": rd.get("memory_delta") or "",
            }
        )
    return {
        "question_id": ep.get("question_id"),
        "db_id": ep.get("db_id"),
        "question": ep.get("question"),
        "evidence": ep.get("evidence"),
        "gold_sql": ep.get("gold_sql"),
        "pred_sql": ep.get("pred_sql"),
        "gold_result": result_to_text(ep.get("gold_result"), max_rows=50),
        "pred_result": result_to_text(ep.get("pred_result"), max_rows=50),
        "status": {
            "round_count": ep.get("round_count"),
            "terminated": ep.get("terminated"),
            "used_fallback_sql": ep.get("used_fallback_sql"),
            "auto_stage_transition": ep.get("auto_stage_transition"),
            "sql_stage_budget_exhausted": ep.get("sql_stage_budget_exhausted"),
            "schema_rounds_used": ep.get("schema_rounds_used"),
            "sql_rounds_used": ep.get("sql_rounds_used"),
            "returns_used": ep.get("returns_used"),
            "pred_error": ep.get("pred_error"),
        },
        "stage_transitions": ep.get("stage_transitions") or [],
        "schema_evidence": ep.get("schema_evidence"),
        "successful_candidates": ep.get("successful_candidates") or [],
        "final_memory": ep.get("final_memory") or "",
        "rounds": rounds,
    }


ANALYSIS_SYSTEM_PROMPT = """你是严谨的 Text-to-SQL 错题根因分析员。
你只能依据用户提供的 question/evidence/gold_sql/pred_sql/执行结果/轨迹进行分析，不要编造数据库事实。
请用中文输出，不要 Markdown，不要额外解释。

要求：
1. 根因必须具体到 SQL 语义差异，例如漏了哪个过滤条件、join 错在哪、聚合粒度错在哪、Top-k 排序错在哪、输出列多/少了什么、预算/终止如何导致错误。
2. 不要只写“SQL 语义错误”“行集合不一致”这种空话。
3. 如果 pred 的核心值其实正确但多输出/少输出列，要明确 strict EX 错在列形状，而不是把语义说错。
4. 如果模型中途查到正确信息但最后改坏，要指出是哪一类轨迹错误。
5. 必须严格使用以下标签输出：

<correct_semantics_zh>
...
</correct_semantics_zh>
<root_cause_zh>
...
</root_cause_zh>
<key_differences_zh>
- ...
- ...
</key_differences_zh>
<validation_zh>
...
</validation_zh>
<summary_root_cause_zh>
一句话总览表用根因
</summary_root_cause_zh>
"""


ANALYSIS_SINGLE_FIELD_SYSTEM_PROMPT = """你是严谨的 Text-to-SQL 错题根因分析员。
你只能依据用户提供的 question/evidence/gold_sql/pred_sql/执行结果/轨迹进行分析，不要编造数据库事实。
请用中文回答指定字段。不要 Markdown，不要额外解释。
输出必须严格使用：
<answer>
...
</answer>
"""


TRANSLATION_SYSTEM_PROMPT = """你是技术日志翻译员。请把 Text-to-SQL agent 轨迹中的英文 think 和 memory_delta 完整翻译成中文。
只翻译，不总结，不删减，不新增数据库事实。

严格要求：
1. think 中的英文自然语言必须完整翻译成中文。
2. memory_delta 中的英文自然语言也必须完整翻译成中文，不能原样保留英文句子。
3. 固定标签也要翻译，例如 Action 翻译为“动作”，Useful memory 翻译为“有用记忆”，Available tables 翻译为“可用表”。
4. SQL、表名、字段名、JSON 参数、数字、字符串取值保持原样。
5. 可以保留 Round 1 这样的轮次编号，也可以翻译为“第 1 轮”，但其余解释性英文必须翻译。
输出严格 JSON，不要 Markdown，不要额外解释。

输出格式：
{
  "rounds": [
    {"round": 1, "think_zh": "...", "memory_delta_zh": "..."}
  ]
}
"""


TRANSLATION_ROUND_SYSTEM_PROMPT = """你是技术日志翻译员。请把 Text-to-SQL agent 单轮轨迹中的英文 think 和 memory_delta 完整翻译成中文。
只翻译，不总结，不删减，不新增数据库事实。

严格要求：
1. think 中的英文自然语言必须完整翻译成中文。
2. memory_delta 中的英文自然语言也必须完整翻译成中文，不能原样保留英文句子。
3. 固定标签也要翻译，例如 Action 翻译为“动作”，Useful memory 翻译为“有用记忆”，Available tables 翻译为“可用表”。
4. SQL、表名、字段名、JSON 参数、数字、字符串取值保持原样。
5. 输出必须严格使用以下标签，不要输出 JSON，不要输出 Markdown：

<think_zh>
...
</think_zh>
<memory_delta_zh>
...
</memory_delta_zh>
"""


TRANSLATION_SINGLE_SYSTEM_PROMPT = """你是技术日志翻译员。请把用户提供的一段 Text-to-SQL agent 日志完整翻译成中文。
只翻译，不总结，不删减，不新增数据库事实。
SQL、表名、字段名、JSON 参数、数字、字符串取值保持原样。
英文自然语言和固定标签必须翻译成中文，例如 Action 翻译为“动作”，Useful memory 翻译为“有用记忆”。
只翻译 <<<TEXT 和 TEXT>>> 之间的正文，不要输出“字段”“待翻译文本”或分隔符本身。
输出必须严格使用：
<translation>
...
</translation>
"""


UNTRANSLATED_MARKERS = (
    "Useful memory",
    "Available tables",
    "table contains",
    "contains columns",
    "no explicit",
    "must be",
    "can be",
    "Action:",
)


def looks_untranslated_memory(source: str, translated: str) -> bool:
    if not source.strip():
        return False
    if not translated.strip():
        return True
    lower = translated.lower()
    if any(marker.lower() in lower for marker in UNTRANSLATED_MARKERS):
        return True
    # If the translation is nearly identical to the source, the model copied it.
    src_norm = SPACE_RE.sub(" ", source).strip()
    dst_norm = SPACE_RE.sub(" ", translated).strip()
    return len(src_norm) > 60 and src_norm == dst_norm


def get_analysis(
    client: httpx.Client,
    ep: dict[str, Any],
    *,
    cache_entry: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    payload = build_case_payload(ep)
    key = stable_hash(payload)
    cached = cache_entry.get("analysis")
    if cached and cached.get("hash") == key and not args.force:
        return cached["value"]
    user_prompt = (
        "请分析下面这个 Text-to-SQL 错题，输出指定 JSON。\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    messages = [
        {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    last_error: Exception | None = None
    for max_tokens in (args.analysis_max_tokens, max(args.analysis_max_tokens * 2, 6000)):
        try:
            text = call_model_text(
                client,
                base_url=args.base_url,
                api_key=args.api_key,
                model=args.model,
                messages=messages,
                max_tokens=max_tokens,
                retries=args.llm_retries,
            )
            value = parse_analysis_tags(text)
            break
        except Exception as exc:
            last_error = exc
    else:
        value = get_analysis_by_fields(client, payload, args=args, previous_error=str(last_error))
    cache_entry["analysis"] = {"hash": key, "value": value}
    return value


def parse_answer_tag(text: str) -> str:
    text = strip_think_tags(text)
    match = re.search(r"<answer>\s*(.*?)\s*</answer>", text, re.S)
    if match:
        return match.group(1).strip()
    open_match = re.search(r"<answer>\s*(.*)", text, re.S)
    if open_match:
        return open_match.group(1).strip()
    raise ValueError(f"missing <answer> tag in response: {text[:500]}")


def get_analysis_field(
    client: httpx.Client,
    payload: dict[str, Any],
    *,
    field: str,
    instruction: str,
    args: argparse.Namespace,
    previous_error: str,
) -> str:
    prompt = (
        f"需要生成字段：{field}\n"
        f"字段要求：{instruction}\n"
        f"之前完整标签输出失败的错误：{previous_error}\n\n"
        "错题材料如下：\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    text = call_model_text(
        client,
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model,
        messages=[
            {"role": "system", "content": ANALYSIS_SINGLE_FIELD_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_tokens=max(args.analysis_max_tokens * 2, 6000),
        retries=args.llm_retries,
    )
    return parse_answer_tag(text)


def get_analysis_by_fields(
    client: httpx.Client,
    payload: dict[str, Any],
    *,
    args: argparse.Namespace,
    previous_error: str,
) -> dict[str, Any]:
    correct = get_analysis_field(
        client,
        payload,
        field="correct_semantics_zh",
        instruction="说明 gold SQL 对应的正确语义，具体到应使用哪些表、字段、过滤、join、聚合、排序和输出列。",
        args=args,
        previous_error=previous_error,
    )
    root = get_analysis_field(
        client,
        payload,
        field="root_cause_zh",
        instruction="说明 pred 错在哪里，必须具体到 SQL 差异或轨迹决策错误，不要只写泛泛的 SQL 语义错误。",
        args=args,
        previous_error=previous_error,
    )
    diffs_text = get_analysis_field(
        client,
        payload,
        field="key_differences_zh",
        instruction="输出 3-6 条关键差异，每条单独一行，覆盖输出列、过滤条件、join、聚合粒度、排序/Top-k、终止预算等实际相关点。",
        args=args,
        previous_error=previous_error,
    )
    validation = get_analysis_field(
        client,
        payload,
        field="validation_zh",
        instruction="根据 gold_result 和 pred_result 说明为什么 strict EX 判错；如果核心值正确但列形状错误，也要明确指出。",
        args=args,
        previous_error=previous_error,
    )
    summary = get_analysis_field(
        client,
        payload,
        field="summary_root_cause_zh",
        instruction="用一句话写总览表可放下的根因摘要，要具体，不超过 120 个中文字符。",
        args=args,
        previous_error=previous_error,
    )
    diffs = []
    for line in diffs_text.splitlines():
        item = line.strip().lstrip("-*0123456789.、 ").strip()
        if item:
            diffs.append(item)
    if not diffs and diffs_text.strip():
        diffs = [diffs_text.strip()]
    return {
        "correct_semantics_zh": correct,
        "root_cause_zh": root,
        "key_differences_zh": diffs,
        "validation_zh": validation,
        "summary_root_cause_zh": summary,
    }


def parse_tag(text: str, tag: str) -> str:
    text = strip_think_tags(text)
    match = re.search(rf"<{tag}>\s*(.*?)\s*</{tag}>", text, re.S)
    if not match:
        raise ValueError(f"missing analysis tag <{tag}> in response: {text[:500]}")
    return match.group(1).strip()


def parse_analysis_tags(text: str) -> dict[str, Any]:
    key_diff_text = parse_tag(text, "key_differences_zh")
    diffs: list[str] = []
    for line in key_diff_text.splitlines():
        item = line.strip()
        if not item:
            continue
        item = item.lstrip("-*0123456789.、 ").strip()
        if item:
            diffs.append(item)
    if not diffs and key_diff_text.strip():
        diffs = [key_diff_text.strip()]
    return {
        "correct_semantics_zh": parse_tag(text, "correct_semantics_zh"),
        "root_cause_zh": parse_tag(text, "root_cause_zh"),
        "key_differences_zh": diffs,
        "validation_zh": parse_tag(text, "validation_zh"),
        "summary_root_cause_zh": parse_tag(text, "summary_root_cause_zh"),
    }


def fallback_translate_round(
    client: httpx.Client,
    rd: dict[str, Any],
    *,
    args: argparse.Namespace,
) -> dict[str, Any]:
    payload = {
        "round": rd.get("round"),
        "think": source_think_text(rd),
        "memory_delta": rd.get("memory_delta") or "",
    }
    text = call_model_text(
        client,
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model,
        messages=[
            {"role": "system", "content": TRANSLATION_ROUND_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
        ],
        max_tokens=args.translation_round_max_tokens,
        retries=args.llm_retries,
    )
    text = strip_think_tags(text)
    think_match = re.search(r"<think_zh>\s*(.*?)\s*</think_zh>", text, re.S)
    memory_match = re.search(r"<memory_delta_zh>\s*(.*?)\s*</memory_delta_zh>", text, re.S)
    if not think_match or not memory_match:
        return {
            "round": rd.get("round"),
            "think_zh": translate_single_field(
                client,
                "think",
                source_think_text(rd),
                args=args,
                max_tokens=max(args.translation_round_max_tokens, 4000),
            ),
            "memory_delta_zh": translate_single_field(
                client,
                "memory_delta",
                rd.get("memory_delta") or "",
                args=args,
                max_tokens=max(args.translation_round_max_tokens, 4000),
            ),
        }
    return {
        "round": rd.get("round"),
        "think_zh": think_match.group(1).strip(),
        "memory_delta_zh": memory_match.group(1).strip(),
    }


def translate_single_field(
    client: httpx.Client,
    label: str,
    text: str,
    *,
    args: argparse.Namespace,
    max_tokens: int,
) -> str:
    if not text.strip():
        return "（空）"
    prompt = f"""字段：{label}

待翻译文本：
<<<TEXT
{text}
TEXT>>>
"""
    response = call_model_text(
        client,
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model,
        messages=[
            {"role": "system", "content": TRANSLATION_SINGLE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
        retries=args.llm_retries,
    )
    response = strip_think_tags(response)
    match = re.search(r"<translation>\s*(.*?)\s*</translation>", response, re.S)
    if match:
        translated = match.group(1).strip()
    else:
        open_match = re.search(r"<translation>\s*(.*)", response, re.S)
        if not open_match:
            raise ValueError(f"single-field translation tag missing for {label}: {response[:500]}")
        translated = open_match.group(1).strip()
    text_marker = "<<<TEXT"
    if text_marker in translated:
        translated = translated.split(text_marker, 1)[1]
        if "TEXT>>>" in translated:
            translated = translated.split("TEXT>>>", 1)[0]
        translated = translated.strip()
    translated = re.sub(r"^字段[:：].*?待翻译文本[:：]\s*", "", translated, flags=re.S).strip()
    if translated.startswith("{"):
        try:
            payload = json.loads(translated)
            if isinstance(payload, dict) and isinstance(payload.get("text"), str):
                translated = payload["text"].strip()
        except Exception:
            pass
    return translated


def get_translations(
    client: httpx.Client,
    ep: dict[str, Any],
    *,
    cache_entry: dict[str, Any],
    args: argparse.Namespace,
) -> dict[int, dict[str, str]]:
    rounds_payload = [
        {
            "round": rd.get("round"),
            "think": source_think_text(rd),
            "memory_delta": rd.get("memory_delta") or "",
        }
        for rd in ep.get("rounds") or []
    ]
    key = stable_hash(rounds_payload)
    cached = cache_entry.get("translations")
    if cached and cached.get("hash") == key and not args.force:
        cached_value = {int(k): v for k, v in cached["value"].items()}
        cache_ok = True
        for rd in ep.get("rounds") or []:
            round_no = int(rd.get("round"))
            translated = cached_value.get(round_no, {})
            if looks_untranslated_memory(rd.get("memory_delta") or "", translated.get("memory_delta_zh") or ""):
                cache_ok = False
                break
        if cache_ok:
            return cached_value

    value_by_round: dict[int, dict[str, str]] = {}
    for rd in ep.get("rounds") or []:
        item = fallback_translate_round(client, rd, args=args)
        round_no = int(rd.get("round"))
        translated = {
            "think_zh": str(item.get("think_zh") or ""),
            "memory_delta_zh": str(item.get("memory_delta_zh") or ""),
        }
        if looks_untranslated_memory(rd.get("memory_delta") or "", translated["memory_delta_zh"]):
            translated["memory_delta_zh"] = translate_single_field(
                client,
                "memory_delta",
                rd.get("memory_delta") or "",
                args=args,
                max_tokens=max(args.translation_round_max_tokens, 4000),
            )
            if looks_untranslated_memory(rd.get("memory_delta") or "", translated["memory_delta_zh"]):
                raise ValueError(
                    f"memory_delta translation still appears untranslated for qid={ep.get('question_id')} "
                    f"round={round_no}: {translated['memory_delta_zh'][:200]}"
                )
        value_by_round[round_no] = translated

    cache_entry["translations"] = {
        "hash": key,
        "value": {str(k): v for k, v in sorted(value_by_round.items())},
    }
    return value_by_round


def memory_before_after_zh(
    rounds: list[dict[str, Any]],
    translations: dict[int, dict[str, str]],
) -> dict[int, tuple[str, str, str]]:
    current: list[str] = []
    out: dict[int, tuple[str, str, str]] = {}
    for rd in rounds:
        round_no = int(rd.get("round"))
        before = "\n".join(current) if current else "（空）"
        delta = translations.get(round_no, {}).get("memory_delta_zh") or "（空）"
        if delta != "（空）":
            current.append(delta)
        after = "\n".join(current) if current else "（空）"
        out[round_no] = (before, delta, after)
    return out


def classify_projection_note(ep: dict[str, Any]) -> str:
    pred = ep.get("pred_result") or {}
    gold = ep.get("gold_result") or {}
    if not pred.get("ok") or not gold.get("ok"):
        return ""
    pred_cols, gold_cols = result_columns(pred), result_columns(gold)
    pred_rows, gold_rows = result_rows(pred), result_rows(gold)
    gold_in_pred, pred_idxs = projection_match(pred_rows, len(pred_cols), gold_rows, len(gold_cols))
    pred_in_gold, gold_idxs = projection_match(gold_rows, len(gold_cols), pred_rows, len(pred_cols))
    if len(pred_cols) > len(gold_cols) and gold_in_pred:
        return f"补充判断：gold_result 是 pred_result 的列投影，投影列索引 {pred_idxs}；核心答案可能正确，但 strict EX 因多输出列判错。"
    if len(pred_cols) < len(gold_cols) and pred_in_gold:
        return f"补充判断：pred_result 是 gold_result 的列投影，投影列索引 {gold_idxs}；pred 少输出了 gold 要求的列。"
    return ""


def render_episode(
    ep: dict[str, Any],
    analysis: dict[str, Any],
    translations: dict[int, dict[str, str]],
) -> str:
    mem_zh = memory_before_after_zh(ep.get("rounds") or [], translations)
    lines: list[str] = []
    qid = ep.get("question_id")
    lines.append(f"## qid{qid}")
    lines.append("")
    lines.append(f"问题：{ep.get('question')}")
    lines.append("")
    lines.append(f"evidence：{ep.get('evidence') or '（无）'}")
    lines.append("")
    lines.append("gold：")
    lines.append("")
    lines.append(sql_fence(ep.get("gold_sql")))
    lines.append("")
    lines.append("pred：")
    lines.append("")
    lines.append(sql_fence(ep.get("pred_sql")))
    lines.append("")
    lines.append(f"正确语义：{analysis.get('correct_semantics_zh', '').strip()}")
    lines.append("")
    lines.append(f"根本错因：{analysis.get('root_cause_zh', '').strip()}")
    projection_note = classify_projection_note(ep)
    if projection_note:
        lines.append("")
        lines.append(projection_note)
    lines.append("")
    lines.append("关键差异：")
    lines.append("")
    for item in analysis.get("key_differences_zh") or []:
        lines.append(f"- {item}")
    lines.append("")
    lines.append(f"验证：{analysis.get('validation_zh', '').strip()}")
    lines.append("")
    lines.append(
        "运行状态："
        f"strict EX={int(bool(ep.get('correct')))}；"
        f"rounds={ep.get('round_count')}；"
        f"terminated={ep.get('terminated')}；"
        f"fallback={ep.get('used_fallback_sql')}；"
        f"auto_stage_transition={ep.get('auto_stage_transition')}；"
        f"schema/sql={ep.get('schema_rounds_used')}/{ep.get('sql_rounds_used')}；"
        f"pred_error={ep.get('pred_error')}"
    )
    lines.append("")
    lines.append("gold 返回：")
    lines.append("")
    lines.append(fence(result_to_text(ep.get("gold_result")), "text"))
    lines.append("")
    lines.append("pred 返回：")
    lines.append("")
    lines.append(fence(result_to_text(ep.get("pred_result")), "text"))
    lines.append("")
    lines.append("阶段切换：")
    lines.append("")
    lines.append(json_fence(ep.get("stage_transitions") or []))
    lines.append("")
    if ep.get("schema_evidence") is not None:
        lines.append("第一阶段提交的 schema_evidence：")
        lines.append("")
        lines.append(json_fence(ep.get("schema_evidence")))
        lines.append("")
    if ep.get("successful_candidates"):
        lines.append("成功执行过的候选 SQL：")
        lines.append("")
        for i, cand in enumerate(ep.get("successful_candidates") or [], 1):
            sql = cand.get("sql") if isinstance(cand, dict) else cand
            lines.append(f"{i}. `{compact(sql, 280)}`")
        lines.append("")

    lines.append("### 运行轨迹")
    lines.append("")
    lines.append("概括版表格：")
    lines.append("")
    lines.append("| 轮次 | 阶段 | 做了什么 | 压缩记忆摘要 |")
    lines.append("| --- | --- | --- | --- |")
    for rd in ep.get("rounds") or []:
        round_no = int(rd.get("round"))
        think_zh = translations.get(round_no, {}).get("think_zh") or "（空）"
        _, delta_zh, _ = mem_zh[round_no]
        action_zh = summarize_tool_call_zh(rd.get("tool_call"))
        do_text = f"{action_zh}。think：{compact(think_zh, 220)}"
        lines.append(
            "| "
            + " | ".join(
                [
                    md_escape(f"Round {round_no}"),
                    md_escape(rd.get("stage")),
                    md_escape(do_text),
                    md_escape(compact(delta_zh, 260)),
                ]
            )
            + " |"
        )
    lines.append("")
    lines.append("逐轮完整详情：")
    lines.append("")
    for rd in ep.get("rounds") or []:
        round_no = int(rd.get("round"))
        before_zh, delta_zh, after_zh = mem_zh[round_no]
        think_zh = translations.get(round_no, {}).get("think_zh") or "（空）"
        tool_call = rd.get("tool_call") or {}
        lines.append(f"#### Round {round_no}")
        lines.append("")
        lines.append(f"- 阶段：`{rd.get('stage')}`")
        lines.append("- 本轮前记忆模块（完整中文翻译）：")
        lines.append("")
        lines.append(fence(before_zh, "text"))
        lines.append("")
        lines.append("- think 中文完整翻译：")
        lines.append("")
        lines.append(fence(think_zh, "text"))
        lines.append("")
        lines.append(f"- 工具：`{tool_call.get('name')}`")
        lines.append("- 工具调用参数：")
        lines.append("")
        lines.append(json_fence(tool_call.get("arguments") or {}))
        lines.append("")
        lines.append("- 返回结果：")
        lines.append("")
        lines.append(fence(result_to_text(rd.get("tool_result"), max_rows=30), "text"))
        lines.append("")
        lines.append("- 本轮新增记忆 memory_delta（中文翻译）：")
        lines.append("")
        lines.append(fence(delta_zh, "text"))
        lines.append("")
        lines.append("- 本轮后记忆模块（程序 append 后的完整中文翻译）：")
        lines.append("")
        lines.append(fence(after_zh, "text"))
        lines.append("")
        if rd.get("compressor_error"):
            lines.append("- compressor_error：")
            lines.append("")
            lines.append(fence(rd.get("compressor_error"), "text"))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def sort_key(ep: dict[str, Any]) -> tuple[int, str]:
    qid = str(ep.get("question_id", ""))
    return (int(qid) if qid.isdigit() else 10**9, qid)


def render_db_report(
    db_id: str,
    classified: list[tuple[dict[str, Any], dict[str, Any], dict[int, dict[str, str]]]],
    source_path: Path,
    summary: dict[str, Any] | None,
) -> str:
    type_counter: Counter[str] = Counter()
    for ep, analysis, _ in classified:
        key = analysis.get("summary_root_cause_zh") or analysis.get("root_cause_zh") or "未分类"
        type_counter[compact(key, 80)] += 1

    lines: list[str] = []
    lines.append(f"# {db_id} 新版详细 wrong_analysis")
    lines.append("")
    lines.append("数据来源：")
    lines.append("")
    lines.append(f"- 轨迹：`{source_path}`")
    if summary:
        lines.append(f"- 全量结果：strict EX = {summary.get('correct')}/{summary.get('total')} = {summary.get('execution_accuracy')}")
        lines.append(
            "- 本次参数："
            f"`enable_thinking={summary.get('enable_thinking')}`, "
            f"`memory_compressor={summary.get('memory_compressor')}`, "
            f"`max_rounds={summary.get('max_rounds')}`, "
            f"`schema_max_rounds={summary.get('schema_max_rounds')}`, "
            f"`sql_max_rounds={summary.get('sql_max_rounds')}`。"
        )
    lines.append("- 评测规则：执行结果行集合严格一致；行顺序不敏感，列数、列顺序和值必须一致。")
    lines.append("- 说明：本文件使用本地 LLM 对每个错题逐题生成中文根因，并对每轮 think / memory_delta 做中文翻译；本轮前/后记忆由程序按 delta append 重建。")
    lines.append("")
    lines.append("## 总览")
    lines.append("")
    lines.append("| qid | db_id | correct | terminated | fallback | 根本错因 |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for ep, analysis, _ in classified:
        lines.append(
            "| "
            + " | ".join(
                [
                    md_escape(ep.get("question_id")),
                    f"`{md_escape(ep.get('db_id'))}`",
                    md_escape(int(bool(ep.get("correct")))),
                    md_escape(ep.get("terminated")),
                    md_escape(ep.get("used_fallback_sql")),
                    md_escape(analysis.get("summary_root_cause_zh") or analysis.get("root_cause_zh")),
                ]
            )
            + " |"
        )
    lines.append("")
    lines.append("## 根因类型速览")
    lines.append("")
    lines.append("| 根因摘要 | 数量 |")
    lines.append("| --- | ---: |")
    for label, count in type_counter.most_common():
        lines.append(f"| {md_escape(label)} | {count} |")
    lines.append("")
    for ep, analysis, translations in classified:
        lines.append(render_episode(ep, analysis, translations))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_RESULT_DIR / "wrong_episodes.pretty.json")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_RESULT_DIR)
    parser.add_argument("--summary", type=Path, default=DEFAULT_RESULT_DIR / "summary.json")
    parser.add_argument("--cache", type=Path, default=DEFAULT_RESULT_DIR / "detailed_wrong_analysis_cache.json")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--api-key", default="EMPTY")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--db-id", action="append", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--llm-retries", type=int, default=2)
    parser.add_argument("--analysis-max-tokens", type=int, default=3500)
    parser.add_argument("--translation-max-tokens", type=int, default=9000)
    parser.add_argument("--translation-round-max-tokens", type=int, default=1600)
    args = parser.parse_args()

    episodes = [ep for ep in load_episodes(args.input) if not ep.get("correct")]
    if args.db_id:
        allowed = set(args.db_id)
        episodes = [ep for ep in episodes if ep.get("db_id") in allowed]
    episodes = sorted(episodes, key=lambda ep: (str(ep.get("db_id")), sort_key(ep)))
    if args.limit is not None:
        episodes = episodes[: args.limit]

    summary = json.loads(args.summary.read_text(encoding="utf-8")) if args.summary.exists() else None
    cache = load_cache(args.cache)
    cache.setdefault("episodes", {})
    by_db: dict[str, list[tuple[dict[str, Any], dict[str, Any], dict[int, dict[str, str]]]]] = defaultdict(list)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=300) as client:
        for index, ep in enumerate(episodes, 1):
            qid = str(ep.get("question_id"))
            db_id = str(ep.get("db_id"))
            entry = cache["episodes"].setdefault(qid, {})
            print(f"[{index}/{len(episodes)}] qid={qid} db={db_id} analyzing/translating", flush=True)
            analysis = get_analysis(client, ep, cache_entry=entry, args=args)
            translations = get_translations(client, ep, cache_entry=entry, args=args)
            by_db[db_id].append((ep, analysis, translations))
            save_cache(args.cache, cache)

    index_lines = [
        "# 新版详细 two-stage wrong_analysis 索引",
        "",
        f"来源：`{args.input}`",
        "",
        "| db_id | 错题数 | 文件 |",
        "| --- | ---: | --- |",
    ]
    for db_id in sorted(by_db):
        path = args.out_dir / f"{db_id}_wrong_analysis.detailed.md"
        report = render_db_report(db_id, by_db[db_id], args.input, summary)
        path.write_text(report, encoding="utf-8")
        index_lines.append(f"| `{db_id}` | {len(by_db[db_id])} | `{path.name}` |")

    index_path = args.out_dir / "wrong_analysis_detailed_index.md"
    index_path.write_text("\n".join(index_lines).rstrip() + "\n", encoding="utf-8")
    print(json.dumps({
        "input": str(args.input),
        "out_dir": str(args.out_dir),
        "cache": str(args.cache),
        "processed_wrong": len(episodes),
        "db_count": len(by_db),
        "index": str(index_path),
    }, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
