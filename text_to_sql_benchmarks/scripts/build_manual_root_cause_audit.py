#!/usr/bin/env python3
"""Build browseable artifacts from the manually authored 210-case audit.

This script only validates and restructures human-authored fields. It does not
infer, classify, or rewrite any root-cause conclusion.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


AUDIT_FIELDS = (
    "精确标签",
    "最早致命轮次",
    "主根因",
    "轨迹溯源",
    "执行证据",
    "伴随问题",
    "最小修复",
)


def parse_args() -> argparse.Namespace:
    repo = Path(__file__).resolve().parents[1]
    default_results = repo / (
        "results/qwen35-4b-arcwise-plat-twostage-agent-full-latest-"
        "s12-s6-round-action-memory"
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, default=default_results)
    return parser.parse_args()


def parse_audit_file(path: Path) -> dict[str, dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    starts = list(re.finditer(r"^## qid(\d+)\s*$", text, re.MULTILINE))
    parsed: dict[str, dict[str, str]] = {}
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        block = text[match.end() : end]
        qid = match.group(1)
        fields: dict[str, str] = {}
        for field in AUDIT_FIELDS:
            field_match = re.search(
                rf"^- \*\*{re.escape(field)}\*\*：(.*)$", block, re.MULTILINE
            )
            if not field_match:
                raise ValueError(f"{path.name} qid{qid} missing field: {field}")
            fields[field] = field_match.group(1).strip()
        parsed[qid] = fields
    return parsed


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


def result_to_text(result: dict[str, Any] | None, max_rows: int = 20) -> str:
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
            lines.append("\t".join("" if value is None else str(value) for value in row))
        else:
            lines.append("" if row is None else str(row))
    row_count = result_row_count(result)
    suffix = f"rows={row_count if row_count is not None else len(rows)}"
    suffix += ", truncated=True" if result.get("truncated") else ", truncated=False"
    if rows and len(rows) > max_rows:
        suffix += f", shown={max_rows}"
    lines.append(suffix)
    return "\n".join(lines)


def load_translation_cache(results_dir: Path) -> dict[str, dict[str, dict[str, str]]]:
    cache_path = results_dir / "detailed_wrong_analysis_cache.json"
    if not cache_path.exists():
        return {}
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    translations_by_qid: dict[str, dict[str, dict[str, str]]] = {}
    for qid, entry in (cache.get("episodes") or {}).items():
        translations = ((entry.get("translations") or {}).get("value") or {})
        if isinstance(translations, dict):
            translations_by_qid[str(qid)] = translations
    return translations_by_qid


def build_round_records(
    episode: dict[str, Any], translations: dict[str, dict[str, str]]
) -> list[dict[str, Any]]:
    memory_zh: list[str] = []
    records: list[dict[str, Any]] = []
    for round_data in episode.get("rounds") or []:
        round_no = str(round_data.get("round"))
        translated = translations.get(round_no, {})
        memory_before = "\n".join(memory_zh)
        memory_delta = (
            translated.get("memory_delta_zh") or round_data.get("memory_delta") or ""
        )
        if memory_delta:
            memory_zh.append(memory_delta)
        memory_after = "\n".join(memory_zh)
        tool_call = (
            round_data.get("tool_call") if isinstance(round_data.get("tool_call"), dict) else {}
        )
        records.append(
            {
                "round": round_data.get("round"),
                "stage": round_data.get("stage"),
                "tool": tool_call.get("name"),
                "think_zh": translated.get("think_zh") or round_data.get("think") or "",
                "tool_call": tool_call,
                "tool_result_text": result_to_text(round_data.get("tool_result")),
                "memory_before_zh": memory_before,
                "memory_delta_zh": memory_delta,
                "memory_after_zh": memory_after,
                "compressor_error": round_data.get("compressor_error"),
            }
        )
    return records


def build_index(results_dir: Path) -> tuple[list[dict], list[str]]:
    source_path = results_dir / "wrong_episodes.pretty.json"
    audit_dir = results_dir / "manual_root_cause_audit"
    episodes = json.loads(source_path.read_text(encoding="utf-8"))
    db_order = sorted({episode["db_id"] for episode in episodes})
    authored: dict[tuple[str, str], dict[str, str]] = {}
    translations_by_qid = load_translation_cache(results_dir)

    family_source = json.loads(
        (audit_dir / "manual_error_families.json").read_text(encoding="utf-8")
    )
    family_by_qid: dict[int, str] = {}
    for family in family_source["families"]:
        for qid in family["qids"]:
            if qid in family_by_qid:
                raise ValueError(
                    f"qid{qid} assigned to two families: "
                    f"{family_by_qid[qid]} / {family['name']}"
                )
            family_by_qid[qid] = family["name"]

    for db_id in db_order:
        path = audit_dir / f"{db_id}.md"
        if not path.exists():
            raise ValueError(f"missing audit file: {path}")
        for qid, fields in parse_audit_file(path).items():
            authored[(db_id, qid)] = fields

    expected = {(episode["db_id"], str(episode["question_id"])) for episode in episodes}
    actual = set(authored)
    if expected != actual:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(f"qid coverage mismatch; missing={missing}, extra={extra}")
    expected_qids = {int(qid) for _, qid in expected}
    if expected_qids != set(family_by_qid):
        missing = sorted(expected_qids - set(family_by_qid))
        extra = sorted(set(family_by_qid) - expected_qids)
        raise ValueError(f"family coverage mismatch; missing={missing}, extra={extra}")

    index: list[dict] = []
    for episode in episodes:
        db_id = episode["db_id"]
        qid = str(episode["question_id"])
        fields = authored[(db_id, qid)]
        rounds = episode.get("rounds", [])
        round_records = build_round_records(episode, translations_by_qid.get(qid, {}))
        index.append(
            {
                "question_id": int(qid),
                "db_id": db_id,
                "error_family": family_by_qid[int(qid)],
                "question": episode.get("question"),
                "evidence": episode.get("evidence"),
                "gold_sql": episode.get("gold_sql"),
                "pred_sql": episode.get("pred_sql"),
                "gold_result": episode.get("gold_result"),
                "pred_result": episode.get("pred_result"),
                "round_count": len(rounds),
                "schema_rounds": sum(
                    row.get("stage") == "schema_exploration" for row in rounds
                ),
                "sql_rounds": sum(row.get("stage") == "sql_generation" for row in rounds),
                "stage_transitions": episode.get("stage_transitions", []),
                "used_fallback_sql": episode.get("used_fallback_sql", False),
                "terminated": episode.get("terminated", False),
                "audit": fields,
                "audit_markdown": f"manual_root_cause_audit/{db_id}.md#qid{qid}",
                "rounds": round_records,
            }
        )
    index.sort(key=lambda row: (row["db_id"], row["question_id"]))
    return index, db_order


def write_combined_markdown(results_dir: Path, db_order: list[str]) -> Path:
    audit_dir = results_dir / "manual_root_cause_audit"
    chunks = [
        "# 210 道错题逐题人工根因审计\n",
        "本文件由各数据库人工审计文件机械合并，不包含自动分类结论。\n",
        (audit_dir / "join_amplification_audit.md").read_text(encoding="utf-8"),
    ]
    for db_id in db_order:
        chunks.append((audit_dir / f"{db_id}.md").read_text(encoding="utf-8"))
    output = results_dir / "manual_root_cause_audit_210.md"
    output.write_text("\n\n---\n\n".join(chunks).rstrip() + "\n", encoding="utf-8")
    return output


def json_for_script(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace(
        "</", "<\\/"
    )


def build_viewer(index: list[dict]) -> str:
    data = json_for_script(index)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>210 道错题人工根因审计</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f4f7fb;
      --bg-accent: #e9f3f0;
      --surface: #ffffff;
      --surface-2: #f7f9fc;
      --surface-3: #eef4f7;
      --line: #d4dde8;
      --line-soft: #e8edf3;
      --text: #17202a;
      --muted: #647182;
      --accent: #0f766e;
      --accent-2: #2f6fb4;
      --accent-3: #b35c18;
      --accent-soft: #e3f3ef;
      --danger: #b42318;
      --danger-soft: #fff0ee;
      --code: #111827;
      --code-text: #f7fafc;
      --shadow: 0 12px 28px rgba(30, 43, 60, 0.08);
      --shadow-soft: 0 5px 18px rgba(30, 43, 60, 0.06);
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: linear-gradient(180deg, #f7fafc 0, var(--bg) 320px); color: var(--text); font: 14px/1.55 system-ui, sans-serif; letter-spacing: 0; }}
    button, input, select {{ font: inherit; letter-spacing: 0; }}
    .topbar {{ position: sticky; top: 0; z-index: 5; background: rgba(255,255,255,0.94); border-bottom: 1px solid var(--line); box-shadow: 0 8px 22px rgba(27, 39, 54, 0.06); backdrop-filter: blur(10px); }}
    .topbar::before {{ content: ""; display: block; height: 4px; background: linear-gradient(90deg, #0f766e, #2f6fb4, #b35c18, #9b4d96); }}
    .topbar-inner {{ max-width: 1680px; margin: 0 auto; padding: 14px 18px 16px; display: grid; grid-template-columns: minmax(260px, 1fr) auto; gap: 16px; align-items: center; }}
    h1 {{ margin: 0; font-size: 21px; line-height: 1.25; font-weight: 800; }}
    .summary {{ color: var(--muted); margin-top: 4px; }}
    .filters {{ display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }}
    input, select {{ min-height: 38px; border: 1px solid var(--line); border-radius: 7px; background: var(--surface); color: var(--text); padding: 7px 10px; box-shadow: inset 0 1px 0 rgba(255,255,255,0.8); }}
    input:focus, select:focus {{ outline: 2px solid rgba(15,118,110,0.18); border-color: #57a397; }}
    #search {{ width: min(340px, 40vw); }}
    .layout {{ max-width: 1680px; min-height: calc(100vh - 78px); margin: 0 auto; display: grid; grid-template-columns: 330px minmax(0, 1fr); }}
    .sidebar {{ border-right: 1px solid var(--line); background: rgba(255,255,255,0.86); min-height: inherit; box-shadow: var(--shadow-soft); }}
    .list-head {{ padding: 11px 14px; border-bottom: 1px solid var(--line); color: var(--muted); background: var(--surface-2); font-weight: 700; }}
    .episode-list {{ max-height: calc(100vh - 126px); overflow: auto; }}
    .episode-button {{ width: 100%; position: relative; display: grid; grid-template-columns: 66px minmax(0,1fr); gap: 10px; border: 0; border-bottom: 1px solid var(--line-soft); border-radius: 0; background: var(--surface); padding: 12px 14px 12px 18px; text-align: left; cursor: pointer; color: var(--text); transition: background .15s ease, box-shadow .15s ease; }}
    .episode-button::before {{ content: ""; position: absolute; left: 0; top: 10px; bottom: 10px; width: 4px; border-radius: 0 5px 5px 0; background: var(--tone, var(--accent)); opacity: .65; }}
    .episode-button:hover {{ background: #fbfdff; box-shadow: inset 0 0 0 1px rgba(47,111,180,0.09); }}
    .episode-button.active {{ background: color-mix(in srgb, var(--tone, var(--accent)) 12%, #ffffff); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--tone, var(--accent)) 28%, transparent); }}
    .episode-button.active::before {{ opacity: 1; width: 5px; }}
    .qid {{ font-weight: 800; font-variant-numeric: tabular-nums; color: #223247; }}
    .label-preview {{ color: var(--muted); overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }}
    main {{ min-width: 0; padding: 18px; }}
    .empty {{ padding: 56px 20px; text-align: center; color: var(--muted); }}
    .case-head {{ display: grid; grid-template-columns: minmax(0,1fr) auto; gap: 16px; align-items: start; padding: 16px; border: 1px solid var(--line); border-radius: 8px; background: linear-gradient(135deg, #ffffff 0%, #f8fbff 62%, #f1f7f4 100%); box-shadow: var(--shadow); }}
    .case-head h2 {{ margin: 0; font-size: 21px; font-weight: 800; }}
    .badges {{ display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }}
    .badge {{ border: 1px solid var(--line); border-radius: 999px; padding: 3px 9px; background: var(--surface); color: var(--muted); white-space: nowrap; font-weight: 650; }}
    .badge.family {{ color: color-mix(in srgb, var(--tone, var(--accent)) 78%, #111827); border-color: color-mix(in srgb, var(--tone, var(--accent)) 34%, var(--line)); background: color-mix(in srgb, var(--tone, var(--accent)) 12%, #ffffff); }}
    .badge.warn {{ color: var(--danger); border-color: #efb5af; background: var(--danger-soft); }}
    section {{ margin-top: 14px; padding: 0; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; background: rgba(255,255,255,0.94); box-shadow: var(--shadow-soft); }}
    section h3 {{ margin: 0; padding: 10px 12px; font-size: 15px; background: var(--surface-2); border-bottom: 1px solid var(--line); }}
    section > p, section > .audit-grid, section > .sql-grid, section > .result-grid, section > div:not(.audit-grid):not(.sql-grid):not(.result-grid) {{ margin: 12px; }}
    .question {{ font-size: 16px; margin: 12px 12px 8px; font-weight: 650; }}
    .evidence {{ margin: 0 12px 12px; color: var(--muted); white-space: pre-wrap; }}
    .audit-grid {{ display: grid; grid-template-columns: 160px minmax(0,1fr); border: 1px solid var(--line); border-radius: 7px; overflow: hidden; background: var(--surface); }}
    .audit-key, .audit-value {{ padding: 10px 12px; border-bottom: 1px solid var(--line); }}
    .audit-key {{ font-weight: 800; background: #f0f5f6; border-right: 1px solid var(--line); color: #263947; }}
    .audit-value {{ white-space: pre-wrap; overflow-wrap: anywhere; }}
    .audit-grid > :nth-last-child(-n+2) {{ border-bottom: 0; }}
    .sql-grid, .result-grid {{ display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 12px; }}
    .pane {{ min-width: 0; border: 1px solid var(--line); border-radius: 7px; overflow: hidden; background: var(--surface); box-shadow: 0 3px 12px rgba(30,43,60,0.04); }}
    .pane-title {{ padding: 8px 10px; background: linear-gradient(90deg, #f4f8fb, #eef6f1); border-bottom: 1px solid var(--line); font-weight: 800; color: #24364a; }}
    pre {{ margin: 0; padding: 12px; background: var(--code); color: var(--code-text); overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; font: 13px/1.55 ui-monospace, monospace; letter-spacing: 0; }}
    .result-meta {{ display: flex; gap: 7px; flex-wrap: wrap; padding: 8px 10px; border-bottom: 1px solid var(--line); color: var(--muted); }}
    .table-wrap {{ max-height: 420px; overflow: auto; }}
    table {{ width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }}
    th, td {{ padding: 7px 9px; border-right: 1px solid var(--line); border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; white-space: pre-wrap; overflow-wrap: anywhere; }}
    th {{ position: sticky; top: 0; background: #edf4f8; z-index: 1; color: #253a4e; }}
    tr:nth-child(even) td {{ background: #fbfcfe; }}
    th:last-child, td:last-child {{ border-right: 0; }}
    .error {{ color: var(--danger); padding: 12px; white-space: pre-wrap; }}
    details.round {{ border: 1px solid var(--line); border-radius: 8px; margin: 0 12px 10px; overflow: hidden; background: var(--surface); box-shadow: 0 4px 14px rgba(30,43,60,0.05); }}
    details.round > summary {{ cursor: pointer; padding: 10px 12px; background: linear-gradient(90deg, color-mix(in srgb, var(--stage, var(--accent)) 13%, #ffffff), #f8fafc); font-weight: 800; border-left: 5px solid var(--stage, var(--accent)); }}
    details.round[open] > summary {{ border-bottom: 1px solid var(--line); }}
    details.round.schema_exploration {{ --stage: #0f766e; }}
    details.round.sql_generation {{ --stage: #2f6fb4; }}
    .round-body {{ padding: 12px; background: #fcfdff; }}
    .round-grid {{ display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 12px; margin-bottom: 12px; }}
    .round-block {{ min-width: 0; margin-bottom: 12px; }}
    .round-block h4 {{ margin: 0 0 6px; font-size: 13px; color: #384b5d; }}
    .tone-0 {{ --tone: #0f766e; }}
    .tone-1 {{ --tone: #2f6fb4; }}
    .tone-2 {{ --tone: #b35c18; }}
    .tone-3 {{ --tone: #8b5a9f; }}
    .tone-4 {{ --tone: #2f7d4f; }}
    .tone-5 {{ --tone: #9b3f54; }}
    @media (max-width: 900px) {{
      .topbar-inner {{ grid-template-columns: 1fr; }}
      .filters {{ justify-content: flex-start; }}
      #search {{ width: 100%; }}
      .layout {{ grid-template-columns: 1fr; }}
      .sidebar {{ border-right: 0; border-bottom: 1px solid var(--line); min-height: 0; }}
      .episode-list {{ max-height: 280px; }}
      .sql-grid, .result-grid {{ grid-template-columns: 1fr; }}
      .round-grid {{ grid-template-columns: 1fr; }}
      .audit-grid {{ grid-template-columns: 118px minmax(0,1fr); }}
      main {{ padding: 14px; }}
    }}
  </style>
</head>
<body>
  <header class="topbar">
    <div class="topbar-inner">
      <div><h1>210 道错题人工根因审计</h1><div class="summary" id="summary"></div></div>
      <div class="filters">
        <select id="db-filter" aria-label="数据库筛选"></select>
        <select id="family-filter" aria-label="错误类型筛选"></select>
        <input id="qid-filter" inputmode="numeric" placeholder="qid" aria-label="qid筛选">
        <input id="search" placeholder="搜索问题、标签、根因、SQL" aria-label="全文搜索">
      </div>
    </div>
  </header>
  <div class="layout">
    <aside class="sidebar">
      <div class="list-head" id="list-head"></div>
      <div class="episode-list" id="episode-list"></div>
    </aside>
    <main id="detail"><div class="empty">请选择一条样本。</div></main>
  </div>
  <script>
    const DATA = {data};
    const FIELDS = {json_for_script(list(AUDIT_FIELDS))};
    const state = {{ filtered: DATA, selected: null }};
    const dbFilter = document.querySelector('#db-filter');
    const familyFilter = document.querySelector('#family-filter');
    const qidFilter = document.querySelector('#qid-filter');
    const search = document.querySelector('#search');
    const list = document.querySelector('#episode-list');
    const detail = document.querySelector('#detail');

    function el(tag, className, text) {{
      const node = document.createElement(tag);
      if (className) node.className = className;
      if (text !== undefined && text !== null) node.textContent = String(text);
      return node;
    }}
    function append(parent, ...children) {{ children.forEach(child => parent.appendChild(child)); return parent; }}
    function stable(value) {{
      if (value === null) return 'null';
      if (value === undefined) return '';
      if (typeof value === 'string') return value;
      return JSON.stringify(value, null, 2);
    }}
    function toneClass(value) {{
      const text = String(value || '');
      let hash = 0;
      for (let i = 0; i < text.length; i += 1) hash = (hash * 31 + text.charCodeAt(i)) >>> 0;
      return `tone-${{hash % 6}}`;
    }}
    function renderPreBlock(title, value) {{
      const block = el('div','round-block');
      block.appendChild(el('h4','',title));
      block.appendChild(el('pre','',stable(value || '（空）')));
      return block;
    }}
    function searchable(row) {{
      return [row.question_id,row.db_id,row.error_family,row.question,row.evidence,row.gold_sql,row.pred_sql,...Object.values(row.audit),JSON.stringify(row.rounds || [])].join(' ').toLowerCase();
    }}
    function applyFilters() {{
      const db = dbFilter.value;
      const family = familyFilter.value;
      const qid = qidFilter.value.trim();
      const query = search.value.trim().toLowerCase();
      state.filtered = DATA.filter(row => (!db || row.db_id === db) && (!family || row.error_family === family) && (!qid || String(row.question_id).includes(qid)) && (!query || searchable(row).includes(query)));
      if (!state.filtered.some(row => row.question_id === state.selected?.question_id)) state.selected = state.filtered[0] || null;
      renderList();
      renderDetail();
    }}
    function renderList() {{
      document.querySelector('#list-head').textContent = `当前 ${{state.filtered.length}} / ${{DATA.length}} 条`;
      list.replaceChildren();
      state.filtered.forEach(row => {{
        const button = el('button','episode-button ' + toneClass(row.error_family) + (row.question_id === state.selected?.question_id ? ' active' : ''));
        button.type = 'button';
        append(button, el('div','qid',`qid${{row.question_id}}`), el('div','label-preview',row.audit['精确标签']));
        button.addEventListener('click', () => {{ state.selected = row; renderList(); renderDetail(); }});
        list.appendChild(button);
      }});
    }}
    function renderResult(result, title) {{
      const pane = el('div','pane');
      pane.appendChild(el('div','pane-title',title));
      if (!result) {{ pane.appendChild(el('div','error','无结果记录')); return pane; }}
      const meta = el('div','result-meta');
      append(meta, el('span','badge',result.ok ? 'ok' : 'failed'), el('span','badge',`rows ${{result.row_count ?? 'unknown'}}`), el('span','badge',result.truncated ? 'truncated' : 'not truncated'));
      pane.appendChild(meta);
      if (result.error) {{ pane.appendChild(el('div','error',result.error)); return pane; }}
      const wrap = el('div','table-wrap');
      const table = el('table');
      const head = el('thead');
      const hr = el('tr');
      (result.columns || []).forEach(column => hr.appendChild(el('th','',column)));
      head.appendChild(hr); table.appendChild(head);
      const body = el('tbody');
      (result.rows || []).forEach(row => {{
        const tr = el('tr');
        row.forEach(value => tr.appendChild(el('td','',stable(value))));
        body.appendChild(tr);
      }});
      table.appendChild(body); wrap.appendChild(table); pane.appendChild(wrap); return pane;
    }}
    function renderRound(round) {{
      const details = el('details','round ' + (round.stage || ''));
      const tool = round.tool || '无工具';
      details.appendChild(el('summary','',`Round ${{round.round}} · ${{round.stage}} · ${{tool}}`));
      const body = el('div','round-body');

      body.appendChild(renderPreBlock('本轮前记忆模块（完整中文翻译）', round.memory_before_zh));

      const top = el('div','round-grid');
      append(top, renderPreBlock('think 中文完整翻译', round.think_zh), renderPreBlock('tool_call', round.tool_call));
      body.appendChild(top);

      body.appendChild(renderPreBlock('tool_result', round.tool_result_text));
      body.appendChild(renderPreBlock('本轮新增记忆', round.memory_delta_zh));
      body.appendChild(renderPreBlock('本轮后记忆模块（程序 append 后的完整中文翻译）', round.memory_after_zh));
      if (round.compressor_error) body.appendChild(renderPreBlock('compressor_error', round.compressor_error));
      details.appendChild(body);
      return details;
    }}
    function renderDetail() {{
      const row = state.selected;
      detail.replaceChildren();
      if (!row) {{ detail.appendChild(el('div','empty','没有符合筛选条件的样本。')); return; }}
      const head = el('div','case-head');
      const title = el('div'); append(title, el('h2','',`qid${{row.question_id}} · ${{row.db_id}}`));
      const badges = el('div','badges');
      append(badges, el('span','badge family ' + toneClass(row.error_family),row.error_family), el('span','badge',`${{row.round_count}} rounds`), el('span','badge',`schema ${{row.schema_rounds}}`), el('span','badge',`sql ${{row.sql_rounds}}`));
      if (row.used_fallback_sql) badges.appendChild(el('span','badge warn','fallback'));
      if (!row.terminated) badges.appendChild(el('span','badge warn','not terminated'));
      append(head,title,badges); detail.appendChild(head);

      const context = el('section'); context.appendChild(el('h3','','问题与 evidence')); context.appendChild(el('p','question',row.question)); context.appendChild(el('p','evidence',row.evidence || '无')); detail.appendChild(context);
      const audit = el('section'); audit.appendChild(el('h3','','人工根因审计'));
      const grid = el('div','audit-grid');
      FIELDS.forEach(field => append(grid,el('div','audit-key',field),el('div','audit-value',row.audit[field])));
      audit.appendChild(grid); detail.appendChild(audit);

      const sqlSection = el('section'); sqlSection.appendChild(el('h3','','SQL 对照'));
      const sqlGrid = el('div','sql-grid');
      [['gold_sql',row.gold_sql],['pred_sql',row.pred_sql]].forEach(([name,sql]) => {{ const pane=el('div','pane'); pane.appendChild(el('div','pane-title',name)); pane.appendChild(el('pre','',sql || 'null')); sqlGrid.appendChild(pane); }});
      sqlSection.appendChild(sqlGrid); detail.appendChild(sqlSection);

      const resultSection = el('section'); resultSection.appendChild(el('h3','','执行结果对照'));
      const resultGrid = el('div','result-grid'); append(resultGrid,renderResult(row.gold_result,'gold_result'),renderResult(row.pred_result,'pred_result'));
      resultSection.appendChild(resultGrid); detail.appendChild(resultSection);

      const traceSection = el('section'); traceSection.appendChild(el('h3','','逐轮轨迹'));
      const rounds = row.rounds || [];
      if (!rounds.length) {{
        traceSection.appendChild(el('div','empty','没有逐轮轨迹记录。'));
      }} else {{
        const traceBody = el('div','');
        rounds.forEach(round => traceBody.appendChild(renderRound(round)));
        traceSection.appendChild(traceBody);
      }}
      detail.appendChild(traceSection);
    }}
    function init() {{
      const dbs = [...new Set(DATA.map(row => row.db_id))].sort();
      const families = [...new Set(DATA.map(row => row.error_family))].sort();
      dbFilter.appendChild(el('option','','全部数据库')); dbFilter.firstChild.value='';
      dbs.forEach(db => {{ const option=el('option','',db); option.value=db; dbFilter.appendChild(option); }});
      familyFilter.appendChild(el('option','','全部错误类型')); familyFilter.firstChild.value='';
      families.forEach(family => {{ const option=el('option','',family); option.value=family; familyFilter.appendChild(option); }});
      document.querySelector('#summary').textContent = `${{DATA.length}} 条 · ${{dbs.length}} 个数据库 · 结论全部来自逐题人工复核`;
      [dbFilter,familyFilter,qidFilter,search].forEach(node => node.addEventListener('input',applyFilters));
      state.selected = DATA[0] || null; applyFilters();
    }}
    init();
  </script>
</body>
</html>
"""


def main() -> None:
    args = parse_args()
    results_dir = args.results_dir.resolve()
    index, db_order = build_index(results_dir)

    index_path = results_dir / "manual_root_cause_audit.index.json"
    index_path.write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    markdown_path = write_combined_markdown(results_dir, db_order)
    viewer_html = build_viewer(index)
    viewer_path = results_dir / "manual_root_cause_audit.viewer.html"
    viewer_v2_path = results_dir / "manual_root_cause_audit.viewer.v2.html"
    viewer_path.write_text(viewer_html, encoding="utf-8")
    viewer_v2_path.write_text(viewer_html, encoding="utf-8")

    print(f"validated episodes: {len(index)}")
    print(f"index: {index_path}")
    print(f"markdown: {markdown_path}")
    print(f"viewer: {viewer_path}")
    print(f"viewer v2: {viewer_v2_path}")


if __name__ == "__main__":
    main()
