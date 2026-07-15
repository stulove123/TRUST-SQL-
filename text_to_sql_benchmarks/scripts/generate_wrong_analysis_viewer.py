#!/usr/bin/env python3
"""Generate a static HTML viewer for two-stage wrong_analysis markdown files."""

from __future__ import annotations

import argparse
import html
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_OUT_DIR = Path(
    "/root/autodl-tmp/text_to_sql_benchmarks/results/"
    "qwen35-4b-arcwise-plat-twostage-agent-full-latest-s12-s6-round-action-memory"
)

SPACE_RE = re.compile(r"\s+")


def compact(value: Any, limit: int = 220) -> str:
    text = "" if value is None else str(value)
    text = SPACE_RE.sub(" ", text.replace("\r", " ").replace("\n", " ")).strip()
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "..."
    return text


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
    suffix += ", truncated=True" if result.get("truncated") else ", truncated=False"
    if rows and len(rows) > max_rows:
        suffix += f", shown={max_rows}"
    lines.append(suffix)
    return "\n".join(lines)


def projection_match(
    source_rows: list[Any],
    source_col_count: int,
    target_rows: list[Any],
    target_col_count: int,
) -> bool:
    if target_col_count > source_col_count:
        return False
    if source_col_count == target_col_count:
        return {tuple(row if isinstance(row, list) else [row]) for row in source_rows} == {
            tuple(row if isinstance(row, list) else [row]) for row in target_rows
        }
    from itertools import combinations

    target = {tuple(row if isinstance(row, list) else [row]) for row in target_rows}
    for idxs in combinations(range(source_col_count), target_col_count):
        projected = set()
        for row in source_rows:
            row_list = row if isinstance(row, list) else [row]
            if len(row_list) >= source_col_count:
                projected.add(tuple(row_list[i] for i in idxs))
        if projected == target:
            return True
    return False


def add_tag(tags: set[str], condition: bool, tag: str) -> None:
    if condition:
        tags.add(tag)


def classify_error(ep: dict[str, Any], analysis: dict[str, str]) -> tuple[str, list[str]]:
    text = " ".join(
        str(analysis.get(k, ""))
        for k in [
            "root_cause_zh",
            "key_differences_zh",
            "validation_zh",
            "summary_root_cause_zh",
        ]
    ).lower()
    pred_result = ep.get("pred_result") or {}
    gold_result = ep.get("gold_result") or {}
    pred_cols = result_columns(pred_result)
    gold_cols = result_columns(gold_result)
    pred_rows = result_rows(pred_result)
    gold_rows = result_rows(gold_result)

    tags: set[str] = set()
    add_tag(tags, not pred_result.get("ok", False), "pred 执行错误")
    add_tag(tags, not ep.get("terminated"), "未正常终止")
    add_tag(tags, bool(ep.get("used_fallback_sql")), "使用 fallback")
    add_tag(tags, bool(ep.get("auto_stage_transition")), "schema 自动切换")
    add_tag(tags, bool(ep.get("sql_stage_budget_exhausted")), "SQL 预算耗尽")

    gold_subset = (
        pred_result.get("ok")
        and gold_result.get("ok")
        and len(pred_cols) > len(gold_cols)
        and projection_match(pred_rows, len(pred_cols), gold_rows, len(gold_cols))
    )
    pred_subset = (
        pred_result.get("ok")
        and gold_result.get("ok")
        and len(pred_cols) < len(gold_cols)
        and projection_match(gold_rows, len(gold_cols), pred_rows, len(pred_cols))
    )
    add_tag(tags, bool(gold_subset), "gold 是 pred 的列子集")
    add_tag(tags, bool(pred_subset), "pred 是 gold 的列子集")

    shape_words = ["多输出", "额外列", "列形状", "输出列", "列数", "列名", "严格 ex"]
    join_words = ["join", "连接", "外键", "笛卡尔", "路径", "关联"]
    agg_words = ["count", "sum", "avg", "group", "distinct", "聚合", "分组", "去重", "分母", "分子", "重复计数", "平均"]
    filter_words = ["过滤", "条件", "字段值", "取值", "映射", "status", "segment", "rtype", "not null", "like", "日期范围"]
    order_words = ["order", "limit", "offset", "top", "最大", "最小", "排序", "第", "排名"]
    calc_words = ["round", "cast", "百分比", "比例", "除以", "小数", "精度", "单位", "日期", "年份", "月份"]
    schema_words = ["字段", "表", "schema", "列不存在", "错表", "缺少 schema", "未发现"]
    trajectory_words = ["轨迹", "round", "最终", "改坏", "回溯", "记忆", "不一致", "推理"]

    def has(words: list[str]) -> bool:
        return any(w in text for w in words)

    if not pred_result.get("ok", False):
        primary = "SQL 执行/语法错误"
    elif gold_subset or (has(shape_words) and len(pred_cols) > len(gold_cols)):
        primary = "多输出列/结果形状错误"
    elif pred_subset or (has(shape_words) and len(pred_cols) < len(gold_cols)):
        primary = "少输出列/结果形状错误"
    elif has(join_words) and has(agg_words):
        primary = "JOIN 放大导致聚合错误"
    elif has(join_words):
        primary = "JOIN 路径/连接条件错误"
    elif has(agg_words):
        primary = "聚合/分组/去重错误"
    elif has(filter_words):
        primary = "过滤条件/字段值映射错误"
    elif has(order_words):
        primary = "排序/Top-k/Limit 错误"
    elif has(calc_words):
        primary = "数值/日期计算错误"
    elif has(schema_words):
        primary = "表字段选择或 schema 理解错误"
    elif has(trajectory_words) or ep.get("used_fallback_sql") or not ep.get("terminated"):
        primary = "轨迹控制/终止策略错误"
    else:
        primary = "其他语义错误"

    add_tag(tags, primary == "多输出列/结果形状错误", "多输出列")
    add_tag(tags, primary == "少输出列/结果形状错误", "少输出列")
    add_tag(tags, "join" in text or "连接" in text, "JOIN")
    add_tag(tags, has(agg_words), "聚合/去重")
    add_tag(tags, has(filter_words), "过滤/值映射")
    add_tag(tags, has(order_words), "排序/Top-k")
    add_tag(tags, has(calc_words), "计算/日期")

    return primary, sorted(tags)


def load_case_markdown(out_dir: Path) -> dict[str, str]:
    markdown_by_qid: dict[str, str] = {}
    for path in sorted(out_dir.glob("*_wrong_analysis.md")):
        if path.name == "wrong_analysis_index.md":
            continue
        text = path.read_text(encoding="utf-8")
        matches = list(re.finditer(r"^## qid(\d+)\b", text, flags=re.M))
        for idx, match in enumerate(matches):
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            markdown_by_qid[match.group(1)] = text[match.start() : end].strip()
    return markdown_by_qid


def build_records(out_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    wrong_path = out_dir / "wrong_episodes.pretty.json"
    cache_path = out_dir / "detailed_wrong_analysis_cache.json"
    wrong = json.loads(wrong_path.read_text(encoding="utf-8"))
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    markdown_by_qid = load_case_markdown(out_dir)

    records: list[dict[str, Any]] = []
    for ep in sorted(wrong, key=lambda item: (item.get("db_id", ""), int(item.get("question_id", 0)))):
        qid = str(ep["question_id"])
        entry = cache.get("episodes", {}).get(qid, {})
        analysis = ((entry.get("analysis") or {}).get("value") or {})
        translations = ((entry.get("translations") or {}).get("value") or {})
        error_type, tags = classify_error(ep, analysis)

        memory_zh: list[str] = []
        rounds = []
        for rd in ep.get("rounds") or []:
            rno = str(rd.get("round"))
            translated = translations.get(rno, {})
            before = "\n".join(memory_zh)
            delta = translated.get("memory_delta_zh", "")
            if delta:
                memory_zh.append(delta)
            after = "\n".join(memory_zh)
            tool_call = rd.get("tool_call") if isinstance(rd.get("tool_call"), dict) else {}
            rounds.append(
                {
                    "round": rd.get("round"),
                    "stage": rd.get("stage"),
                    "tool": tool_call.get("name"),
                    "tool_call": tool_call,
                    "think_zh": translated.get("think_zh") or rd.get("think") or "",
                    "memory_before_zh": before,
                    "memory_delta_zh": delta,
                    "memory_after_zh": after,
                    "tool_result_text": result_to_text(rd.get("tool_result"), max_rows=20),
                    "compressor_error": rd.get("compressor_error"),
                }
            )

        db_id = ep.get("db_id")
        markdown_file = f"{db_id}_wrong_analysis.md"
        records.append(
            {
                "qid": qid,
                "idx": ep.get("idx"),
                "db_id": db_id,
                "question": ep.get("question") or "",
                "evidence": ep.get("evidence") or "",
                "error_type": error_type,
                "tags": tags,
                "round_count": ep.get("round_count"),
                "schema_rounds_used": ep.get("schema_rounds_used"),
                "sql_rounds_used": ep.get("sql_rounds_used"),
                "returns_used": ep.get("returns_used"),
                "terminated": bool(ep.get("terminated")),
                "used_fallback_sql": bool(ep.get("used_fallback_sql")),
                "auto_stage_transition": bool(ep.get("auto_stage_transition")),
                "pred_error": ep.get("pred_error"),
                "gold_error": ep.get("gold_error"),
                "correct_semantics_zh": analysis.get("correct_semantics_zh") or "",
                "root_cause_zh": analysis.get("root_cause_zh") or "",
                "key_differences_zh": analysis.get("key_differences_zh") or "",
                "validation_zh": analysis.get("validation_zh") or "",
                "summary_root_cause_zh": analysis.get("summary_root_cause_zh") or "",
                "gold_sql": ep.get("gold_sql") or "",
                "pred_sql": ep.get("pred_sql") or "",
                "gold_result_text": result_to_text(ep.get("gold_result"), max_rows=50),
                "pred_result_text": result_to_text(ep.get("pred_result"), max_rows=50),
                "stage_transitions": ep.get("stage_transitions") or [],
                "successful_candidates": ep.get("successful_candidates") or [],
                "schema_evidence": ep.get("schema_evidence"),
                "final_memory": ep.get("final_memory") or "",
                "markdown_file": markdown_file,
                "markdown_href": f"{markdown_file}#qid{qid}",
                "markdown_excerpt": markdown_by_qid.get(qid, ""),
                "rounds": rounds,
            }
        )

    summary = {
        "total": len(records),
        "db_counts": dict(Counter(r["db_id"] for r in records)),
        "error_type_counts": dict(Counter(r["error_type"] for r in records)),
        "source": str(wrong_path),
    }
    return records, summary


def html_shell(data_json: str, summary_json: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Wrong Analysis Viewer</title>
  <style>
    :root {{
      --bg: #f6f7f9;
      --panel: #ffffff;
      --panel-soft: #f1f4f7;
      --text: #14171f;
      --muted: #667085;
      --line: #d7dee8;
      --line-strong: #b9c4d3;
      --accent: #0f6b62;
      --accent-soft: #e7f4f1;
      --warn: #9a3412;
      --warn-soft: #fff3e8;
      --bad: #b42318;
      --code: #111827;
      --code-text: #f9fafb;
      --blue: #2457a6;
      --blue-soft: #e9f0fb;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 14px;
      line-height: 1.5;
    }}
    header.app {{
      padding: 18px 22px 14px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
      position: sticky;
      top: 0;
      z-index: 20;
    }}
    h1 {{ margin: 0; font-size: 22px; font-weight: 700; letter-spacing: 0; }}
    h2 {{ margin: 0 0 8px; font-size: 18px; letter-spacing: 0; }}
    h3 {{ margin: 0 0 8px; font-size: 14px; letter-spacing: 0; }}
    p {{ margin: 0 0 10px; }}
    .subtitle {{ color: var(--muted); margin-top: 4px; }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(5, minmax(120px, 1fr));
      gap: 10px;
      margin-top: 14px;
    }}
    .metric {{
      border: 1px solid var(--line);
      background: var(--panel-soft);
      border-radius: 8px;
      padding: 10px 12px;
      min-height: 70px;
    }}
    .metric strong {{ display: block; font-size: 22px; line-height: 1.1; }}
    .metric span {{ color: var(--muted); font-size: 12px; }}
    .filters {{
      display: grid;
      grid-template-columns: minmax(180px, 1.2fr) minmax(220px, 1.6fr) minmax(120px, .8fr) minmax(240px, 2fr);
      gap: 10px;
      margin-top: 14px;
    }}
    label {{ display: grid; gap: 4px; color: var(--muted); font-size: 12px; font-weight: 600; }}
    select, input {{
      width: 100%;
      border: 1px solid var(--line-strong);
      border-radius: 8px;
      padding: 9px 10px;
      background: var(--panel);
      color: var(--text);
      font: inherit;
      min-height: 38px;
    }}
    main {{
      display: grid;
      grid-template-columns: minmax(320px, 420px) minmax(0, 1fr);
      gap: 16px;
      padding: 16px 22px 28px;
      max-width: 1680px;
      margin: 0 auto;
    }}
    .list-panel, .detail-panel {{
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      overflow: hidden;
    }}
    .panel-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      background: var(--panel-soft);
    }}
    .case-list {{
      max-height: calc(100vh - 236px);
      overflow: auto;
    }}
    .case-item {{
      width: 100%;
      display: block;
      text-align: left;
      border: 0;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
      color: var(--text);
      padding: 12px 14px;
      cursor: pointer;
    }}
    .case-item:hover {{ background: #fafcff; }}
    .case-item.active {{
      background: var(--blue-soft);
      box-shadow: inset 4px 0 0 var(--blue);
    }}
    .case-title {{
      display: flex;
      justify-content: space-between;
      gap: 8px;
      align-items: baseline;
      font-weight: 700;
    }}
    .case-root {{ margin-top: 7px; color: var(--muted); font-size: 12px; }}
    .badge-row {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }}
    .badge {{
      display: inline-flex;
      max-width: 100%;
      align-items: center;
      border-radius: 999px;
      border: 1px solid var(--line);
      padding: 2px 7px;
      color: var(--muted);
      font-size: 12px;
      line-height: 18px;
      white-space: nowrap;
    }}
    .badge.type {{ background: var(--accent-soft); color: var(--accent); border-color: #b7ded8; }}
    .badge.warn {{ background: var(--warn-soft); color: var(--warn); border-color: #f2c19b; }}
    .badge.bad {{ background: #fff1f0; color: var(--bad); border-color: #ffc8c3; }}
    .detail-scroll {{
      max-height: calc(100vh - 236px);
      overflow: auto;
      padding: 16px;
    }}
    .section {{
      border: 1px solid var(--line);
      border-radius: 8px;
      margin-bottom: 12px;
      overflow: hidden;
      background: var(--panel);
    }}
    .section > .section-head {{
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      background: var(--panel-soft);
      font-weight: 700;
    }}
    .section-body {{ padding: 12px; }}
    .grid-2 {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }}
    pre {{
      margin: 0;
      padding: 12px;
      background: var(--code);
      color: var(--code-text);
      border-radius: 6px;
      overflow: auto;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }}
    .text-block {{
      margin: 0;
      color: var(--text);
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }}
    .kv {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
    }}
    .kv div {{ border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px; background: #fbfcfe; }}
    .kv span {{ display: block; color: var(--muted); font-size: 12px; }}
    .kv strong {{ display: block; margin-top: 2px; }}
    details.round {{
      border: 1px solid var(--line);
      border-radius: 8px;
      margin-bottom: 10px;
      overflow: hidden;
    }}
    details.round > summary {{
      cursor: pointer;
      padding: 10px 12px;
      background: var(--panel-soft);
      font-weight: 700;
    }}
    .round-body {{ padding: 12px; }}
    .empty {{
      padding: 28px;
      color: var(--muted);
      text-align: center;
    }}
    .button-row {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }}
    a.button, button.small {{
      border: 1px solid var(--line-strong);
      border-radius: 8px;
      background: var(--panel);
      color: var(--text);
      padding: 7px 9px;
      text-decoration: none;
      font: inherit;
      font-size: 12px;
      cursor: pointer;
    }}
    .source-note {{
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }}
    @media (max-width: 1100px) {{
      main {{ grid-template-columns: 1fr; }}
      .case-list, .detail-scroll {{ max-height: none; }}
      .filters {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .metrics {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
    }}
    @media (max-width: 720px) {{
      header.app {{ position: static; }}
      main {{ padding: 10px; }}
      .filters, .grid-2, .kv, .metrics {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header class="app">
    <h1>Two-stage wrong_analysis viewer</h1>
    <div class="subtitle">按数据库、错误类型、qid 和关键词筛选新版 wrong_analysis；详情来自本地评测结果与详细根因缓存。</div>
    <div class="metrics" id="metrics"></div>
    <div class="filters">
      <label>数据库
        <select id="dbFilter"></select>
      </label>
      <label>错误类型
        <select id="typeFilter"></select>
      </label>
      <label>qid
        <input id="qidFilter" placeholder="如 944">
      </label>
      <label>关键词
        <input id="textFilter" placeholder="搜索问题、根因、SQL、标签">
      </label>
    </div>
  </header>
  <main>
    <section class="list-panel">
      <div class="panel-head">
        <strong>错题列表</strong>
        <span class="source-note" id="visibleCount"></span>
      </div>
      <div class="case-list" id="caseList"></div>
    </section>
    <section class="detail-panel">
      <div class="panel-head">
        <strong>错题详情</strong>
        <span class="source-note" id="detailMeta"></span>
      </div>
      <div class="detail-scroll" id="detail"></div>
    </section>
  </main>
  <script id="viewer-data" type="application/json">{data_json}</script>
  <script id="viewer-summary" type="application/json">{summary_json}</script>
  <script>
    const CASES = JSON.parse(document.getElementById('viewer-data').textContent);
    const SUMMARY = JSON.parse(document.getElementById('viewer-summary').textContent);
    const state = {{ db: '全部', type: '全部', qid: '', text: '', selectedQid: CASES[0]?.qid || null }};

    const els = {{
      metrics: document.getElementById('metrics'),
      dbFilter: document.getElementById('dbFilter'),
      typeFilter: document.getElementById('typeFilter'),
      qidFilter: document.getElementById('qidFilter'),
      textFilter: document.getElementById('textFilter'),
      caseList: document.getElementById('caseList'),
      detail: document.getElementById('detail'),
      visibleCount: document.getElementById('visibleCount'),
      detailMeta: document.getElementById('detailMeta')
    }};

    function escapeHtml(value) {{
      return String(value ?? '').replace(/[&<>"']/g, ch => ({{
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      }}[ch]));
    }}
    function asJson(value) {{ return JSON.stringify(value ?? null, null, 2); }}
    function pre(value) {{ return `<pre>${{escapeHtml(value ?? '')}}</pre>`; }}
    function pill(text, cls='') {{ return `<span class="badge ${{cls}}">${{escapeHtml(text)}}</span>`; }}
    function compact(text, n=150) {{
      const s = String(text ?? '').replace(/\\s+/g, ' ').trim();
      return s.length > n ? s.slice(0, n - 1).trimEnd() + '...' : s;
    }}
    function boolText(value) {{ return value ? '是' : '否'; }}

    function fillSelect(select, values, allLabel='全部') {{
      select.innerHTML = [allLabel, ...values].map(v => `<option value="${{escapeHtml(v)}}">${{escapeHtml(v)}}</option>`).join('');
    }}

    function buildSearchText(item) {{
      return [
        item.qid, item.db_id, item.question, item.evidence, item.error_type,
        item.tags.join(' '), item.root_cause_zh, item.summary_root_cause_zh,
        item.key_differences_zh, item.validation_zh, item.gold_sql, item.pred_sql
      ].join(' ').toLowerCase();
    }}

    function filteredCases() {{
      const text = state.text.trim().toLowerCase();
      const qid = state.qid.trim();
      return CASES.filter(item => {{
        if (state.db !== '全部' && item.db_id !== state.db) return false;
        if (state.type !== '全部' && item.error_type !== state.type) return false;
        if (qid && !item.qid.includes(qid)) return false;
        if (text && !buildSearchText(item).includes(text)) return false;
        return true;
      }});
    }}

    function renderMetrics(list) {{
      const dbSet = new Set(list.map(x => x.db_id));
      const typeSet = new Set(list.map(x => x.error_type));
      const fallback = list.filter(x => x.used_fallback_sql).length;
      const auto = list.filter(x => x.auto_stage_transition).length;
      const avgRounds = list.length ? (list.reduce((s, x) => s + Number(x.round_count || 0), 0) / list.length).toFixed(1) : '0.0';
      els.metrics.innerHTML = [
        ['显示错题', `${{list.length}} / ${{SUMMARY.total}}`],
        ['数据库数', dbSet.size],
        ['错误类型数', typeSet.size],
        ['fallback', fallback],
        ['平均轮数', avgRounds],
        ['schema 自动切换', auto]
      ].map(([label, value]) => `<div class="metric"><strong>${{escapeHtml(value)}}</strong><span>${{escapeHtml(label)}}</span></div>`).join('');
    }}

    function renderList(list) {{
      els.visibleCount.textContent = `${{list.length}} 条`;
      if (!list.length) {{
        els.caseList.innerHTML = '<div class="empty">没有匹配的错题。</div>';
        els.detail.innerHTML = '<div class="empty">调整筛选条件后查看详情。</div>';
        els.detailMeta.textContent = '';
        return;
      }}
      if (!list.some(item => item.qid === state.selectedQid)) state.selectedQid = list[0].qid;
      els.caseList.innerHTML = list.map(item => `
        <button class="case-item ${{item.qid === state.selectedQid ? 'active' : ''}}" data-qid="${{escapeHtml(item.qid)}}">
          <div class="case-title"><span>qid ${{escapeHtml(item.qid)}}</span><span>${{escapeHtml(item.db_id)}}</span></div>
          <div class="badge-row">${{pill(item.error_type, 'type')}}${{item.used_fallback_sql ? pill('fallback', 'warn') : ''}}${{!item.terminated ? pill('未终止', 'bad') : ''}}</div>
          <div class="case-root">${{escapeHtml(compact(item.summary_root_cause_zh || item.root_cause_zh, 170))}}</div>
        </button>
      `).join('');
      els.caseList.querySelectorAll('.case-item').forEach(btn => {{
        btn.addEventListener('click', () => {{
          state.selectedQid = btn.dataset.qid;
          render();
        }});
      }});
      renderDetail(list.find(item => item.qid === state.selectedQid) || list[0]);
    }}

    function renderTextSection(title, text) {{
      return `<section class="section"><div class="section-head">${{escapeHtml(title)}}</div><div class="section-body"><p class="text-block">${{escapeHtml(text || '（空）')}}</p></div></section>`;
    }}

    function renderSqlPair(item) {{
      return `<section class="section">
        <div class="section-head">SQL 对照</div>
        <div class="section-body grid-2">
          <div><h3>gold_sql</h3>${{pre(item.gold_sql)}}</div>
          <div><h3>pred_sql</h3>${{pre(item.pred_sql)}}</div>
        </div>
      </section>`;
    }}

    function renderResultPair(item) {{
      return `<section class="section">
        <div class="section-head">执行结果对照</div>
        <div class="section-body grid-2">
          <div><h3>gold_result</h3>${{pre(item.gold_result_text)}}</div>
          <div><h3>pred_result</h3>${{pre(item.pred_result_text)}}</div>
        </div>
      </section>`;
    }}

    function renderRound(round) {{
      return `<details class="round">
        <summary>Round ${{escapeHtml(round.round)}} · ${{escapeHtml(round.stage)}} · ${{escapeHtml(round.tool || '无工具')}}</summary>
        <div class="round-body">
          <div class="grid-2">
            <div><h3>think 中文完整翻译</h3>${{pre(round.think_zh)}}</div>
            <div><h3>tool_call</h3>${{pre(asJson(round.tool_call))}}</div>
          </div>
          <div class="section" style="margin-top:12px"><div class="section-head">tool_result</div><div class="section-body">${{pre(round.tool_result_text)}}</div></div>
          <div class="grid-2">
            <div><h3>本轮前记忆模块（完整中文翻译）</h3>${{pre(round.memory_before_zh)}}</div>
            <div><h3>本轮新增记忆</h3>${{pre(round.memory_delta_zh)}}</div>
          </div>
          <div style="margin-top:12px"><h3>本轮后记忆模块（程序 append 后的完整中文翻译）</h3>${{pre(round.memory_after_zh)}}</div>
          ${{round.compressor_error ? `<div style="margin-top:12px"><h3>compressor_error</h3>${{pre(round.compressor_error)}}</div>` : ''}}
        </div>
      </details>`;
    }}

    function renderDetail(item) {{
      if (!item) return;
      els.detailMeta.textContent = `qid ${{item.qid}} · ${{item.db_id}}`;
      const tags = [pill(item.error_type, 'type'), ...item.tags.map(t => pill(t, t.includes('fallback') || t.includes('自动') ? 'warn' : ''))].join('');
      els.detail.innerHTML = `
        <section class="section">
          <div class="section-head">qid ${{escapeHtml(item.qid)}} · ${{escapeHtml(item.db_id)}}</div>
          <div class="section-body">
            <div class="badge-row">${{tags}}</div>
            <p style="margin-top:10px"><strong>问题：</strong>${{escapeHtml(item.question)}}</p>
            <p><strong>evidence：</strong>${{escapeHtml(item.evidence || '（空）')}}</p>
            <div class="kv">
              <div><span>总轮数</span><strong>${{escapeHtml(item.round_count)}}</strong></div>
              <div><span>schema/sql</span><strong>${{escapeHtml(item.schema_rounds_used)}} / ${{escapeHtml(item.sql_rounds_used)}}</strong></div>
              <div><span>terminated</span><strong>${{boolText(item.terminated)}}</strong></div>
              <div><span>fallback</span><strong>${{boolText(item.used_fallback_sql)}}</strong></div>
            </div>
            <div class="button-row">
              <a class="button" href="${{escapeHtml(item.markdown_href)}}" target="_blank" rel="noreferrer">打开 markdown</a>
              <button class="small" data-copy="gold">复制 gold_sql</button>
              <button class="small" data-copy="pred">复制 pred_sql</button>
            </div>
          </div>
        </section>
        ${{renderTextSection('正确语义', item.correct_semantics_zh)}}
        ${{renderTextSection('根本错因', item.root_cause_zh)}}
        ${{renderTextSection('关键差异', item.key_differences_zh)}}
        ${{renderTextSection('验证', item.validation_zh)}}
        ${{renderSqlPair(item)}}
        ${{renderResultPair(item)}}
        <section class="section"><div class="section-head">阶段切换 / 成功候选</div><div class="section-body grid-2"><div><h3>stage_transitions</h3>${{pre(asJson(item.stage_transitions))}}</div><div><h3>successful_candidates</h3>${{pre(asJson(item.successful_candidates))}}</div></div></section>
        <section class="section"><div class="section-head">逐轮轨迹</div><div class="section-body">${{item.rounds.map(renderRound).join('')}}</div></section>
      `;
      els.detail.querySelectorAll('button[data-copy]').forEach(btn => {{
        btn.addEventListener('click', async () => {{
          const text = btn.dataset.copy === 'gold' ? item.gold_sql : item.pred_sql;
          try {{
            await navigator.clipboard.writeText(text || '');
            btn.textContent = '已复制';
            setTimeout(() => btn.textContent = btn.dataset.copy === 'gold' ? '复制 gold_sql' : '复制 pred_sql', 900);
          }} catch (err) {{
            btn.textContent = '复制失败';
          }}
        }});
      }});
    }}

    function render() {{
      const list = filteredCases();
      renderMetrics(list);
      renderList(list);
    }}

    function init() {{
      const dbs = [...new Set(CASES.map(x => x.db_id))].sort();
      const types = [...new Set(CASES.map(x => x.error_type))].sort();
      fillSelect(els.dbFilter, dbs);
      fillSelect(els.typeFilter, types);
      els.dbFilter.addEventListener('change', e => {{ state.db = e.target.value; render(); }});
      els.typeFilter.addEventListener('change', e => {{ state.type = e.target.value; render(); }});
      els.qidFilter.addEventListener('input', e => {{ state.qid = e.target.value; render(); }});
      els.textFilter.addEventListener('input', e => {{ state.text = e.target.value; render(); }});
      render();
    }}
    init();
  </script>
</body>
</html>
"""


def generate(out_dir: Path, output: Path) -> None:
    records, summary = build_records(out_dir)
    data_json = json.dumps(records, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    summary_json = json.dumps(summary, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    output.write_text(html_shell(data_json, summary_json), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    out_dir = args.out_dir
    output = args.output or (out_dir / "wrong_analysis_viewer.html")
    generate(out_dir, output)
    print(json.dumps({"output": str(output), "out_dir": str(out_dir)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
