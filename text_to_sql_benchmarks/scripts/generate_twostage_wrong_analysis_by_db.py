#!/usr/bin/env python3
"""Generate per-database wrong_analysis markdown files for two-stage episodes.

The input is the two-stage runner's full `episodes.jsonl` or
`wrong_episodes.pretty.json`.  The output is one markdown file per database,
containing a technical, auditable wrong-case report with SQL/result comparison
and round-level trajectory details.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any


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


def load_episodes(path: Path) -> list[dict[str, Any]]:
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON list or JSONL file: {path}")
    return data


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
    """Return whether target rows equal a projection of source rows."""
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
        projected: set[tuple[Any, ...]] = set()
        for row in source_rows or []:
            if not isinstance(row, list):
                row = [row]
            if len(row) < source_col_count:
                continue
            projected.add(tuple(row[i] for i in idxs))
        if projected == target:
            return True, idxs
    return False, None


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
    if result.get("truncated"):
        suffix += ", truncated=True"
    else:
        suffix += ", truncated=False"
    if rows and len(rows) > max_rows:
        suffix += f", shown={max_rows}"
    lines.append(suffix)
    return "\n".join(lines)


def summarize_tool_result(result: dict[str, Any] | None) -> str:
    if not isinstance(result, dict):
        return "无工具结果。"
    if not result.get("ok", False):
        return f"执行失败：{compact(result.get('error'), 220)}"
    cols = result_columns(result)
    row_count = result_row_count(result)
    bits: list[str] = ["执行成功"]
    if cols:
        bits.append("列：" + ", ".join(f"`{c}`" for c in cols[:8]))
        if len(cols) > 8:
            bits.append(f"另有 {len(cols) - 8} 列")
    if row_count is not None:
        bits.append(f"行数/预览行数：{row_count}")
    if result.get("truncated"):
        bits.append("结果被截断")
    if result.get("generated_sql"):
        bits.append("环境生成 SQL：" + f"`{compact(result.get('generated_sql'), 160)}`")
    return "；".join(bits) + "。"


def summarize_tool_call(tool_call: dict[str, Any] | None) -> str:
    if not isinstance(tool_call, dict):
        return "模型未给出可解析工具调用"
    name = tool_call.get("name")
    args = tool_call.get("arguments") or {}
    if name in {"execute_sql", "execute_sub_sql"}:
        sql = compact(args.get("sql"), 220)
        if name == "execute_sub_sql":
            purpose = compact(args.get("purpose"), 120)
            return f"{name}：{purpose}；SQL=`{sql}`"
        return f"{name}：SQL=`{sql}`"
    if name in {"terminate_first_stage", "terminate_second_stage"}:
        return f"{name}：提交阶段终止信息"
    if name == "return_to_schema_stage":
        return f"{name}：{compact(args.get('reason') or args.get('needed_info'), 180)}"
    return f"{name}({compact(json.dumps(args, ensure_ascii=False), 220)})"


def classify_case(ep: dict[str, Any]) -> tuple[str, list[str]]:
    pred_result = ep.get("pred_result") or {}
    gold_result = ep.get("gold_result") or {}
    pred_cols = result_columns(pred_result)
    gold_cols = result_columns(gold_result)
    pred_rows = result_rows(pred_result)
    gold_rows = result_rows(gold_result)
    pred_ok = bool(pred_result.get("ok"))
    gold_ok = bool(gold_result.get("ok"))
    pred_row_count = result_row_count(pred_result)
    gold_row_count = result_row_count(gold_result)

    reasons: list[str] = []
    if not (ep.get("pred_sql") or "").strip():
        reasons.append("未生成最终 SQL，`pred_sql` 为空。")
    if not ep.get("terminated"):
        reasons.append("episode 未正常 `terminate_second_stage`，存在预算/终止策略问题。")
    if ep.get("used_fallback_sql"):
        reasons.append("使用了 fallback SQL，说明最终终止前没有被接受的明确最终答案。")
    if ep.get("auto_stage_transition"):
        reasons.append("schema 阶段预算耗尽后自动进入 SQL 阶段，第一阶段 schema 证据可能不完整。")
    if ep.get("sql_stage_budget_exhausted"):
        reasons.append("SQL 阶段预算耗尽，可能没有完成候选 SQL 修正或终止。")
    if not pred_ok:
        reasons.append(f"pred SQL 执行失败：{compact(pred_result.get('error'), 220)}")
    if not gold_ok:
        reasons.append(f"gold SQL 执行失败：{compact(gold_result.get('error'), 220)}")

    if pred_ok and gold_ok:
        gold_in_pred, pred_idxs = projection_match(pred_rows, len(pred_cols), gold_rows, len(gold_cols))
        pred_in_gold, gold_idxs = projection_match(gold_rows, len(gold_cols), pred_rows, len(pred_cols))
        if len(pred_cols) > len(gold_cols) and gold_in_pred:
            reasons.append(
                "pred 多输出了额外列；按 gold 是 pred 的列子集口径核心答案可能正确，"
                f"投影列索引={pred_idxs}。严格 EX 因列形状不一致判错。"
            )
        elif len(pred_cols) < len(gold_cols) and pred_in_gold:
            reasons.append(
                "pred 少输出了 gold 需要的列；按 pred 是 gold 的列子集口径可能部分正确，"
                f"投影列索引={gold_idxs}。严格 EX 因缺列判错。"
            )
        elif len(pred_cols) != len(gold_cols):
            reasons.append(f"输出列数不一致：pred {len(pred_cols)} 列，gold {len(gold_cols)} 列。")

        if pred_row_count != gold_row_count:
            reasons.append(f"返回行数不一致：pred {pred_row_count} 行，gold {gold_row_count} 行。")
        elif len(pred_cols) == len(gold_cols) and rowset(pred_rows) != rowset(gold_rows):
            reasons.append("列数和行数接近，但返回值集合不一致，主要是 SQL 语义/过滤/聚合/排序取 Top-k 错误。")
        elif not reasons:
            reasons.append("保存结果未暴露明显形状差异，需要结合 SQL 和完整执行结果进一步人工检查。")

    if not reasons:
        reasons.append("需要结合轨迹进一步人工判定。")

    if not pred_ok or not (ep.get("pred_sql") or "").strip():
        label = "执行失败/无最终 SQL"
    elif any("多输出" in r for r in reasons):
        label = "多输出中间列"
    elif any("少输出" in r for r in reasons):
        label = "少输出答案列"
    elif pred_ok and gold_ok and pred_row_count != gold_row_count:
        label = "行集合不一致"
    elif len(pred_cols) != len(gold_cols):
        label = "列形状不一致"
    elif not ep.get("terminated") or ep.get("used_fallback_sql"):
        label = "终止/预算问题"
    else:
        label = "SQL 语义错误"
    return label, reasons


def sort_key(ep: dict[str, Any]) -> tuple[int, str]:
    qid = str(ep.get("question_id", ""))
    return (int(qid) if qid.isdigit() else 10**9, qid)


def render_episode(ep: dict[str, Any], label: str, reasons: list[str]) -> str:
    lines: list[str] = []
    qid = ep.get("question_id")
    lines.append(f"## qid{qid}")
    lines.append("")
    lines.append(f"问题：{ep.get('question')}")
    lines.append("")
    evidence = ep.get("evidence") or "（无）"
    lines.append(f"evidence：{evidence}")
    lines.append("")
    lines.append(f"错误类型初判：**{label}**")
    lines.append("")
    lines.append("根因信号：")
    lines.append("")
    for reason in reasons:
        lines.append(f"- {reason}")
    lines.append("")
    lines.append(
        "运行状态："
        f"rounds={ep.get('round_count')}; "
        f"schema_rounds={ep.get('schema_rounds_used')}; "
        f"sql_rounds={ep.get('sql_rounds_used')}; "
        f"terminated={ep.get('terminated')}; "
        f"fallback={ep.get('used_fallback_sql')}; "
        f"auto_stage_transition={ep.get('auto_stage_transition')}; "
        f"return_to_schema={ep.get('returns_used')}; "
        f"pred_error={ep.get('pred_error')}"
    )
    lines.append("")
    lines.append("gold：")
    lines.append("")
    lines.append(sql_fence(ep.get("gold_sql")))
    lines.append("")
    lines.append("pred：")
    lines.append("")
    lines.append(sql_fence(ep.get("pred_sql")))
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
            lines.append(f"{i}. `{compact(sql, 260)}`")
        lines.append("")

    lines.append("### 运行轨迹")
    lines.append("")
    lines.append("概括版表格：")
    lines.append("")
    lines.append("| 轮次 | 阶段 | 工具调用 | 工具返回摘要 | memory_delta |")
    lines.append("| --- | --- | --- | --- | --- |")
    for rd in ep.get("rounds") or []:
        tc = rd.get("tool_call") or {}
        tool_summary = summarize_tool_call(tc)
        result_summary = summarize_tool_result(rd.get("tool_result"))
        memory_delta = compact(rd.get("memory_delta"), 220)
        lines.append(
            "| "
            + " | ".join(
                [
                    md_escape(f"Round {rd.get('round')}"),
                    md_escape(rd.get("stage")),
                    md_escape(tool_summary),
                    md_escape(result_summary),
                    md_escape(memory_delta),
                ]
            )
            + " |"
        )
    lines.append("")
    lines.append("逐轮完整详情：")
    lines.append("")
    for rd in ep.get("rounds") or []:
        round_no = rd.get("round")
        lines.append(f"#### Round {round_no}")
        lines.append("")
        lines.append(f"- 阶段：`{rd.get('stage')}`")
        lines.append(f"- 工具：`{(rd.get('tool_call') or {}).get('name')}`")
        lines.append("- 工具调用参数：")
        lines.append("")
        lines.append(json_fence((rd.get("tool_call") or {}).get("arguments") or {}))
        lines.append("")
        lines.append("- think 原文：")
        lines.append("")
        lines.append(fence(rd.get("think") or "（空）", "text"))
        lines.append("")
        lines.append("- 工具返回预览：")
        lines.append("")
        lines.append(fence(result_to_text(rd.get("tool_result"), max_rows=20), "text"))
        lines.append("")
        lines.append("- 本轮前 memory：")
        lines.append("")
        lines.append(fence(rd.get("memory_before") or "（空）", "text"))
        lines.append("")
        lines.append("- 本轮新增 memory_delta：")
        lines.append("")
        lines.append(fence(rd.get("memory_delta") or "（空）", "text"))
        lines.append("")
        lines.append("- 本轮后 memory_after：")
        lines.append("")
        lines.append(fence(rd.get("memory_after") or "（空）", "text"))
        lines.append("")
        if rd.get("compressor_error"):
            lines.append("- compressor_error：")
            lines.append("")
            lines.append(fence(rd.get("compressor_error"), "text"))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_db_report(
    db_id: str,
    episodes: list[dict[str, Any]],
    source_path: Path,
    summary: dict[str, Any] | None,
) -> str:
    classified: list[tuple[dict[str, Any], str, list[str]]] = []
    for ep in sorted(episodes, key=sort_key):
        label, reasons = classify_case(ep)
        classified.append((ep, label, reasons))
    type_counts = Counter(label for _, label, _ in classified)

    lines: list[str] = []
    lines.append(f"# {db_id} 新版 wrong_analysis")
    lines.append("")
    lines.append("## 技术摘要")
    lines.append("")
    lines.append(
        f"本文件覆盖最新两阶段 Text-to-SQL Agent 全量评测中 `{db_id}` 数据库的 "
        f"{len(episodes)} 个 strict EX 错题。每道题均保留 gold/pred SQL、执行结果预览、"
        "阶段切换、候选 SQL 和逐轮工具轨迹，便于后续人工复核根因。"
    )
    lines.append("")
    lines.append("## 数据与评测口径")
    lines.append("")
    lines.append(f"- 来源文件：`{source_path}`")
    if summary:
        lines.append(f"- 全量结果：{summary.get('correct')}/{summary.get('total')}，strict EX={summary.get('execution_accuracy')}")
        lines.append(
            "- 本次参数："
            f"`max_rounds={summary.get('max_rounds')}`, "
            f"`schema_max_rounds={summary.get('schema_max_rounds')}`, "
            f"`sql_max_rounds={summary.get('sql_max_rounds')}`, "
            f"`enable_thinking={summary.get('enable_thinking')}`, "
            f"`memory_compressor={summary.get('memory_compressor')}`"
        )
    lines.append("- 评测规则：执行结果行集合严格一致；行顺序不敏感，但列数、列顺序和值必须一致。")
    lines.append("- 说明：`错误类型初判/根因信号` 为程序基于 SQL 执行状态、列形状、行数、阶段终止状态和投影匹配生成的自动初判；复杂语义错因仍应结合逐轮轨迹人工复核。")
    lines.append("")
    lines.append("## 错误类型概览")
    lines.append("")
    lines.append("| 错误类型初判 | 数量 |")
    lines.append("| --- | ---: |")
    for label, count in type_counts.most_common():
        lines.append(f"| {md_escape(label)} | {count} |")
    lines.append("")
    lines.append("## 总览")
    lines.append("")
    lines.append("| qid | rounds | terminated | fallback | schema/sql | 错误类型初判 | 关键根因信号 |")
    lines.append("| --- | ---: | --- | --- | --- | --- | --- |")
    for ep, label, reasons in classified:
        first_reason = compact(reasons[0] if reasons else "", 180)
        lines.append(
            "| "
            + " | ".join(
                [
                    md_escape(ep.get("question_id")),
                    md_escape(ep.get("round_count")),
                    md_escape(ep.get("terminated")),
                    md_escape(ep.get("used_fallback_sql")),
                    md_escape(f"{ep.get('schema_rounds_used')}/{ep.get('sql_rounds_used')}"),
                    md_escape(label),
                    md_escape(first_reason),
                ]
            )
            + " |"
        )
    lines.append("")
    for ep, label, reasons in classified:
        lines.append(render_episode(ep, label, reasons))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(
            "/root/autodl-tmp/text_to_sql_benchmarks/results/"
            "qwen35-4b-arcwise-plat-twostage-agent-full-latest-s12-s6-round-action-memory/"
            "wrong_episodes.pretty.json"
        ),
        help="Path to wrong_episodes.pretty.json or episodes.jsonl.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(
            "/root/autodl-tmp/text_to_sql_benchmarks/results/"
            "qwen35-4b-arcwise-plat-twostage-agent-full-latest-s12-s6-round-action-memory"
        ),
        help="Directory where <db_id>_wrong_analysis.md files are written.",
    )
    parser.add_argument("--summary", type=Path, default=None, help="Optional summary.json path.")
    args = parser.parse_args()

    episodes = [ep for ep in load_episodes(args.input) if not ep.get("correct")]
    by_db: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ep in episodes:
        by_db[str(ep.get("db_id"))].append(ep)

    summary_path = args.summary or args.out_dir / "summary.json"
    summary = None
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))

    args.out_dir.mkdir(parents=True, exist_ok=True)
    index_lines: list[str] = []
    index_lines.append("# 新版 two-stage wrong_analysis 索引")
    index_lines.append("")
    index_lines.append(f"来源：`{args.input}`")
    index_lines.append("")
    index_lines.append("| db_id | 错题数 | 文件 |")
    index_lines.append("| --- | ---: | --- |")

    for db_id in sorted(by_db):
        output = args.out_dir / f"{db_id}_wrong_analysis.md"
        report = render_db_report(db_id, by_db[db_id], args.input, summary)
        output.write_text(report, encoding="utf-8")
        index_lines.append(f"| `{db_id}` | {len(by_db[db_id])} | `{output.name}` |")

    index_path = args.out_dir / "wrong_analysis_index.md"
    index_path.write_text("\n".join(index_lines).rstrip() + "\n", encoding="utf-8")

    print(json.dumps({
        "input": str(args.input),
        "out_dir": str(args.out_dir),
        "total_wrong": len(episodes),
        "db_count": len(by_db),
        "files": {db: f"{db}_wrong_analysis.md" for db in sorted(by_db)},
        "index": str(index_path),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
