#!/usr/bin/env python3
"""Build the reviewed 174-case audit and viewer from the current run only."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
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
    "建议错误族",
    "置信度",
    "需补充验证",
)

# A fixed, reusable taxonomy assigned after reviewing every qid. The exact
# per-case label remains in ``instance_label``; these families deliberately
# avoid free-form labels so their counts can support analysis and ablations.
ERROR_FAMILY_SPECS = {
    "AG1": {
        "mechanism": "Agent 状态管理与错误恢复",
        "family": "错误状态或假设固化，恢复未收敛",
        "qids": {149, 944, 1014, 1192},
    },
    "AG2": {
        "mechanism": "Agent 状态管理与错误恢复",
        "family": "任务过度分解并耗尽交互预算",
        "qids": {407},
    },
    "J1": {
        "mechanism": "关系路径与 JOIN",
        "family": "必要桥表或关系路径遗漏",
        "qids": {95, 189, 207, 253, 408, 685, 824},
    },
    "J2": {
        "mechanism": "关系路径与 JOIN",
        "family": "JOIN 键或关系角色选择错误",
        "qids": {125, 587, 775, 1028, 1036, 1102, 1146},
    },
    "J3": {
        "mechanism": "关系路径与 JOIN",
        "family": "多余 INNER JOIN 导致事实记录删失",
        "qids": {215, 788, 1189},
    },
    "S1": {
        "mechanism": "Schema 与实体落地",
        "family": "错误事实表或数据源选择",
        "qids": {347, 352, 371, 416, 483, 529, 875, 897, 948, 1486, 1490, 1524},
    },
    "S2": {
        "mechanism": "Schema 与实体落地",
        "family": "字段语义或角色映射错误",
        "qids": {24, 39, 640, 937, 1187},
    },
    "S3": {
        "mechanism": "Schema 与实体落地",
        "family": "实体值、名称或内部 ID 链接错误",
        "qids": {26, 466, 469, 989, 1115},
    },
    "R1": {
        "mechanism": "排序、排名与极值选择",
        "family": "排名函数或并列结果保留错误",
        "qids": {17, 212, 349, 728, 736, 794, 1092, 1376},
    },
    "R2": {
        "mechanism": "排序、排名与极值选择",
        "family": "排序方向或极值方向错误",
        "qids": {82, 877, 967, 1168, 1238, 1281},
    },
    "R3": {
        "mechanism": "排序、排名与极值选择",
        "family": "Top-k 数量、偏移或无依据截断错误",
        "qids": {50, 129, 412, 459, 480, 1078, 1357},
    },
    "R4": {
        "mechanism": "排序、排名与极值选择",
        "family": "抽样或无效候选误作全局极值",
        "qids": {37, 1032, 1144},
    },
    "R5": {
        "mechanism": "排序、排名与极值选择",
        "family": "聚合后排序或关联记录选择错误",
        "qids": {671, 1011},
    },
    "N1": {
        "mechanism": "数值、类型与时间计算",
        "family": "比例与百分比尺度换算错误",
        "qids": {62, 77, 85, 716, 1149},
    },
    "N2": {
        "mechanism": "数值、类型与时间计算",
        "family": "数值类型转换或整数除法错误",
        "qids": {115, 116, 169, 879, 1185},
    },
    "N3": {
        "mechanism": "数值、类型与时间计算",
        "family": "非请求舍入或精度变换",
        "qids": {118, 880, 954, 962, 1094},
    },
    "N4": {
        "mechanism": "数值、类型与时间计算",
        "family": "日期或时间格式解析及条件构造错误",
        "qids": {533, 861, 866, 872, 955, 1031, 1482, 1509},
    },
    "N5": {
        "mechanism": "数值、类型与时间计算",
        "family": "年龄或日期区间算术错误",
        "qids": {1171, 1229, 1257},
    },
    "N6": {
        "mechanism": "数值、类型与时间计算",
        "family": "派生指标算术公式错误",
        "qids": {1529, 1531},
    },
    "G1": {
        "mechanism": "聚合、粒度与基数",
        "family": "实体数误计为一对多记录数",
        "qids": {100, 219, 383, 963, 1037, 1169, 1241, 1243, 1247, 1252, 1255, 1267},
    },
    "G2": {
        "mechanism": "聚合、粒度与基数",
        "family": "一对多 JOIN 导致加权聚合",
        "qids": {152, 201, 263, 683, 1227, 1339},
    },
    "G3": {
        "mechanism": "聚合、粒度与基数",
        "family": "聚合层缺失或嵌套顺序错误",
        "qids": {281, 592, 604, 1322, 1472, 1481, 1498},
    },
    "G4": {
        "mechanism": "聚合、粒度与基数",
        "family": "GROUP BY 维度或答案粒度错误",
        "qids": {27, 881, 1476},
    },
    "G5": {
        "mechanism": "聚合、粒度与基数",
        "family": "聚合度量单位或分子分母定义错误",
        "qids": {117, 197, 665},
    },
    "C1": {
        "mechanism": "过滤、值域与集合条件",
        "family": "必要过滤条件遗漏",
        "qids": {11, 23, 25, 36, 48, 750, 977},
    },
    "C2": {
        "mechanism": "过滤、值域与集合条件",
        "family": "NULL 或哨兵值有效域处理错误",
        "qids": {40, 726, 791, 990},
    },
    "C3": {
        "mechanism": "过滤、值域与集合条件",
        "family": "枚举、状态或值格式映射错误",
        "qids": {83, 93, 136, 137, 1265},
    },
    "C4": {
        "mechanism": "过滤、值域与集合条件",
        "family": "过滤作用域、谓词边界或条件组合错误",
        "qids": {145, 192, 409, 896, 1136, 1270},
    },
    "O1": {
        "mechanism": "输出契约与任务完成",
        "family": "输出字段或实体标识错误",
        "qids": {28, 45, 46, 236, 465, 530, 694},
    },
    "O2": {
        "mechanism": "输出契约与任务完成",
        "family": "结果行列结构或值编码错误",
        "qids": {230, 637, 1410},
    },
    "O3": {
        "mechanism": "输出契约与任务完成",
        "family": "复合子目标或最终答案合成遗漏",
        "qids": {173, 744, 829, 1362},
    },
    "M1": {
        "mechanism": "问题语义与约束推理",
        "family": "集合运算顺序或否定逻辑错误",
        "qids": {41, 341},
    },
    "M2": {
        "mechanism": "问题语义与约束推理",
        "family": "无证据推断或擅自附加约束",
        "qids": {414, 1387},
    },
    "M3": {
        "mechanism": "问题语义与约束推理",
        "family": "任务概念、比例方向或字段含义误解",
        "qids": {743, 972, 1001},
    },
    "E1": {
        "mechanism": "评测执行与数据基准",
        "family": "Gold 执行超时造成评测假阴性",
        "qids": {518, 701},
    },
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def classify_error(episode: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    qid = int(episode["question_id"])
    matches = [
        (code, spec) for code, spec in ERROR_FAMILY_SPECS.items() if qid in spec["qids"]
    ]
    if len(matches) != 1:
        raise ValueError(f"qid {qid} must belong to exactly one error family: {matches}")
    return matches[0]


def infer_failure_stage(audit: dict[str, Any], episode: dict[str, Any]) -> str:
    marker = str(audit.get("最早致命轮次", ""))
    lowered = marker.lower()
    if "评测" in marker or "evaluation" in lowered:
        return "evaluation"
    match = re.search(r"(?:round\s*)?(\d+)", lowered)
    if match:
        round_no = int(match.group(1))
        for record in episode.get("rounds", []):
            if record.get("round") == round_no:
                return str(record.get("stage") or "unknown")
    if "schema" in lowered or "探索" in marker:
        return "schema_exploration"
    return "sql_generation"

def compact_round(
    round_record: dict[str, Any],
    translation: dict[str, Any],
    memory_before_zh: str,
    memory_after_zh: str,
) -> dict[str, Any]:
    return {
        "round": round_record.get("round"),
        "stage": round_record.get("stage"),
        "think": round_record.get("think"),
        "think_zh": translation.get("think_zh") or "（空）",
        "tool_call": round_record.get("tool_call"),
        "tool_result": round_record.get("tool_result"),
        "memory_before": round_record.get("memory_before"),
        "memory_before_zh": memory_before_zh,
        "memory_delta": round_record.get("memory_delta"),
        "memory_delta_zh": translation.get("memory_delta_zh") or "（空）",
        "memory_after": round_record.get("memory_after"),
        "memory_after_zh": memory_after_zh,
        "compressor_error": round_record.get("compressor_error"),
        "allowed_tools": round_record.get("allowed_tools"),
        "schema_final_round_only_terminate": round_record.get(
            "schema_final_round_only_terminate"
        ),
        "latency": round_record.get("latency"),
    }


def compact_rounds(
    episode: dict[str, Any], translations: dict[str, Any]
) -> list[dict[str, Any]]:
    current_memory: list[str] = []
    rows: list[dict[str, Any]] = []
    for record in episode.get("rounds", []):
        round_no = str(record.get("round"))
        translated = translations.get(round_no)
        if translated is None:
            raise ValueError(
                f"Missing Chinese translation for qid={episode['question_id']} round={round_no}"
            )
        before = "\n".join(current_memory) if current_memory else "（空）"
        delta = str(translated.get("memory_delta_zh") or "（空）")
        if delta != "（空）":
            current_memory.append(delta)
        after = "\n".join(current_memory) if current_memory else "（空）"
        rows.append(compact_round(record, translated, before, after))
    return rows


def build(root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    wrong = load_json(root / "wrong_episodes.pretty.json")
    translation_cache = load_json(
        root / "manual_root_cause_audit.translation_zh.cache.json"
    ).get("episodes", {})
    draft_cache = load_json(root / "manual_root_cause_audit.draft.cache.json")["episodes"]
    expected_qids = {str(row["question_id"]) for row in wrong}
    decisions: dict[str, dict[str, Any]] = {}
    sources: dict[str, str] = {}

    for review_path in sorted((root / "manual_root_cause_audit_review").glob("*.json")):
        review = load_json(review_path)
        if review.get("legacy_audit_used") is not False:
            raise ValueError(f"Legacy audit use is not explicitly disabled: {review_path}")
        for qid, decision in review["decisions"].items():
            if qid in decisions:
                raise ValueError(f"Duplicate review for qid {qid}")
            decisions[qid] = decision
            sources[qid] = review_path.name

    if set(decisions) != expected_qids:
        missing = sorted(expected_qids - set(decisions), key=int)
        extra = sorted(set(decisions) - expected_qids, key=int)
        raise ValueError(f"Review coverage mismatch: missing={missing}, extra={extra}")

    rows: list[dict[str, Any]] = []
    decision_counts: Counter[str] = Counter()
    for episode in sorted(wrong, key=lambda row: int(row["question_id"])):
        qid = str(episode["question_id"])
        decision = decisions[qid]
        decision_counts[decision["decision"]] += 1
        if decision["decision"] == "corrected":
            audit = decision["audit"]
        elif decision["decision"] == "accepted":
            audit = draft_cache[qid]["audit"]
        else:
            raise ValueError(f"Unknown decision for qid {qid}: {decision['decision']}")
        absent = [field for field in AUDIT_FIELDS if field not in audit]
        if absent:
            raise ValueError(f"Missing audit fields for qid {qid}: {absent}")

        family_code, family_spec = classify_error(episode)
        episode_translations = translation_cache.get(qid, {}).get("rounds", {})
        rows.append(
            {
                "question_id": episode["question_id"],
                "db_id": episode["db_id"],
                "mechanism_family": family_spec["mechanism"],
                "error_family_code": family_code,
                "error_family": family_spec["family"],
                "instance_label": audit["精确标签"],
                "fine_grained_family": audit["建议错误族"],
                "failure_stage": infer_failure_stage(audit, episode),
                "review_decision": decision["decision"],
                "review_source": sources[qid],
                "question": episode.get("question"),
                "evidence": episode.get("evidence"),
                "gold_sql": episode.get("gold_sql"),
                "pred_sql": episode.get("pred_sql"),
                "gold_result": episode.get("gold_result"),
                "pred_result": episode.get("pred_result"),
                "audit": audit,
                "round_count": episode.get("round_count"),
                "schema_rounds": episode.get("schema_rounds_used"),
                "sql_rounds": episode.get("sql_rounds_used"),
                "returns_used": episode.get("returns_used"),
                "stage_transitions": episode.get("stage_transitions"),
                "used_fallback_sql": episode.get("used_fallback_sql"),
                "terminated": episode.get("terminated"),
                "evaluation_mode": episode.get("evaluation_mode"),
                "rounds": compact_rounds(episode, episode_translations),
            }
        )

    mechanism_counts = Counter(row["mechanism_family"] for row in rows)
    family_counts = Counter(
        f'{row["error_family_code"]} {row["error_family"]}' for row in rows
    )
    stage_counts = Counter(row["failure_stage"] for row in rows)
    db_counts = Counter(row["db_id"] for row in rows)
    summary = {
        "source_run": root.name,
        "total": len(rows),
        "taxonomy_version": 3,
        "taxonomy_levels": ["mechanism_family", "error_family", "instance_label"],
        "legacy_audit_used": False,
        "review_decisions": dict(sorted(decision_counts.items())),
        "mechanism_families": dict(
            sorted(mechanism_counts.items(), key=lambda pair: (-pair[1], pair[0]))
        ),
        "error_families": dict(sorted(family_counts.items(), key=lambda pair: (-pair[1], pair[0]))),
        "failure_stages": dict(
            sorted(stage_counts.items(), key=lambda pair: (-pair[1], pair[0]))
        ),
        "databases": dict(sorted(db_counts.items(), key=lambda pair: (-pair[1], pair[0]))),
    }
    return rows, summary


def taxonomy_artifacts(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    counts = Counter(row["error_family_code"] for row in rows)
    taxonomy: list[dict[str, Any]] = []
    for code, spec in ERROR_FAMILY_SPECS.items():
        taxonomy.append(
            {
                "code": code,
                "mechanism_family": spec["mechanism"],
                "error_family": spec["family"],
                "count": counts[code],
                "qids": sorted(spec["qids"]),
            }
        )

    lines = [
        "# 174 道错题细粒度错误分类（Taxonomy v3）",
        "",
        "本分类来自当前 174 道错题的逐题人工根因审计，不沿用旧运行的错误族。",
        "分类采用固定三层结构：`失败机制 -> 可复用错误族 -> 逐题实例标签`。",
        "前两层用于统计与实验分析，实例标签用于保留每道题的具体根因。",
        "",
    ]
    mechanisms: dict[str, list[dict[str, Any]]] = {}
    for item in taxonomy:
        mechanisms.setdefault(item["mechanism_family"], []).append(item)
    for index, (mechanism, items) in enumerate(mechanisms.items(), start=1):
        mechanism_count = sum(item["count"] for item in items)
        lines.extend(
            [
                f"## {index}. {mechanism}（{mechanism_count} 题）",
                "",
                "| 编码 | 细粒度错误族 | 数量 | qid |",
                "| --- | --- | ---: | --- |",
            ]
        )
        for item in items:
            qids = ", ".join(str(qid) for qid in item["qids"])
            lines.append(
                f"| {item['code']} | {item['error_family']} | {item['count']} | {qids} |"
            )
        lines.append("")
    return taxonomy, "\n".join(lines).rstrip() + "\n"


VIEWER_HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>174 道错题细粒度根因审计</title>
  <style>
    :root{color-scheme:light;--bg:#eef3f8;--surface:#fff;--surface2:#f5f8fb;--line:#d5dee8;--text:#17212b;--muted:#637184;--teal:#0d766e;--blue:#286aa6;--amber:#ad5c16;--rose:#9c3e59;--violet:#7654a6;--green:#347756;--code:#111827;--danger:#b42318;--shadow:0 10px 26px rgba(29,43,59,.08)}
    *{box-sizing:border-box}body{margin:0;background:linear-gradient(180deg,#f8fbfd 0,#eef3f8 300px);color:var(--text);font:14px/1.55 system-ui,sans-serif;letter-spacing:0}button,input,select{font:inherit;letter-spacing:0}
    .top{position:sticky;top:0;z-index:5;background:rgba(255,255,255,.95);border-bottom:1px solid var(--line);box-shadow:0 7px 20px rgba(30,45,62,.07);backdrop-filter:blur(10px)}.top:before{content:"";display:block;height:4px;background:linear-gradient(90deg,var(--teal),var(--blue),var(--amber),var(--rose),var(--violet))}
    .topin{max-width:1720px;margin:auto;padding:13px 18px 15px;display:grid;grid-template-columns:minmax(280px,1fr) auto;gap:14px;align-items:center}h1{font-size:21px;line-height:1.25;margin:0}.summary{color:var(--muted);margin-top:3px}.filters{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}select,input{min-height:38px;border:1px solid var(--line);border-radius:7px;background:#fff;padding:7px 10px;color:var(--text)}select:focus,input:focus{outline:2px solid rgba(13,118,110,.18);border-color:#56a298}#search{width:min(350px,38vw)}
    .layout{max-width:1720px;margin:auto;display:grid;grid-template-columns:338px minmax(0,1fr);min-height:calc(100vh - 78px)}aside{border-right:1px solid var(--line);background:rgba(255,255,255,.88)}.listhead{padding:11px 14px;border-bottom:1px solid var(--line);background:var(--surface2);font-weight:750;color:var(--muted)}#list{max-height:calc(100vh - 126px);overflow:auto}.casebtn{width:100%;position:relative;display:grid;grid-template-columns:67px minmax(0,1fr);gap:9px;border:0;border-bottom:1px solid #e8edf3;border-radius:0;background:#fff;padding:12px 13px 12px 18px;text-align:left;cursor:pointer;color:var(--text)}.casebtn:before{content:"";position:absolute;left:0;top:9px;bottom:9px;width:4px;background:var(--tone);border-radius:0 5px 5px 0}.casebtn:hover{background:#f9fcfe}.casebtn.active{background:color-mix(in srgb,var(--tone) 12%,#fff);box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--tone) 25%,transparent)}.qid{font-weight:850}.preview{color:var(--muted);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
    main{min-width:0;padding:18px}.empty{padding:60px 20px;text-align:center;color:var(--muted)}.head{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:15px;align-items:start;padding:16px;border:1px solid var(--line);border-radius:8px;background:linear-gradient(135deg,#fff,#f5faff 60%,#eef8f4);box-shadow:var(--shadow)}.head h2{font-size:21px;margin:0}.badges{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}.badge{border:1px solid var(--line);border-radius:999px;padding:3px 9px;background:#fff;color:var(--muted);white-space:nowrap;font-weight:650}.badge.family{color:color-mix(in srgb,var(--tone) 82%,#111);background:color-mix(in srgb,var(--tone) 11%,#fff);border-color:color-mix(in srgb,var(--tone) 35%,var(--line))}.warn{color:var(--danger)}
    section{margin-top:14px;border:1px solid var(--line);border-radius:8px;overflow:hidden;background:rgba(255,255,255,.96);box-shadow:0 5px 16px rgba(30,45,62,.05)}section h3{margin:0;padding:10px 12px;font-size:15px;background:var(--surface2);border-bottom:1px solid var(--line)}.question{font-size:16px;font-weight:650;margin:12px 12px 7px}.evidence{white-space:pre-wrap;color:var(--muted);margin:0 12px 12px}.audit{display:grid;grid-template-columns:170px minmax(0,1fr);margin:12px;border:1px solid var(--line);border-radius:7px;overflow:hidden}.ak,.av{padding:10px 12px;border-bottom:1px solid var(--line)}.ak{font-weight:800;background:#edf5f4;border-right:1px solid var(--line)}.av{white-space:pre-wrap;overflow-wrap:anywhere}.audit>:nth-last-child(-n+2){border-bottom:0}
    .grid2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:12px}.pane{min-width:0;border:1px solid var(--line);border-radius:7px;overflow:hidden;background:#fff}.pt{padding:8px 10px;font-weight:800;background:linear-gradient(90deg,#edf5fa,#eef7f2);border-bottom:1px solid var(--line)}pre{margin:0;padding:12px;background:var(--code);color:#f7fafc;white-space:pre-wrap;overflow-wrap:anywhere;overflow:auto;font:13px/1.55 ui-monospace,monospace;letter-spacing:0}.meta{display:flex;gap:6px;flex-wrap:wrap;padding:8px 10px;border-bottom:1px solid var(--line)}.tablewrap{max-height:430px;overflow:auto}table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}th,td{padding:7px 9px;border-right:1px solid var(--line);border-bottom:1px solid var(--line);text-align:left;vertical-align:top;white-space:pre-wrap;overflow-wrap:anywhere}th{position:sticky;top:0;background:#eaf2f7;z-index:1}tr:nth-child(even) td{background:#fbfcfe}.error{padding:12px;color:var(--danger);white-space:pre-wrap}
    details.round{margin:0 12px 10px;border:1px solid var(--line);border-radius:8px;overflow:hidden;background:#fff}details.round>summary{cursor:pointer;padding:10px 12px;font-weight:800;border-left:5px solid var(--stage);background:linear-gradient(90deg,color-mix(in srgb,var(--stage) 13%,#fff),#f8fafc)}details.round[open]>summary{border-bottom:1px solid var(--line)}.schema_exploration{--stage:var(--teal)}.sql_generation{--stage:var(--blue)}.roundbody{padding:12px;background:#fcfdff}.roundgrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.block{min-width:0;margin-bottom:12px}.block h4{font-size:13px;margin:0 0 6px;color:#3a4d60}.original{margin:0 0 12px;border:1px dashed #bcc8d4;border-radius:7px;overflow:hidden;background:#f6f8fa}.original>summary{cursor:pointer;padding:8px 10px;color:var(--muted);font-weight:700}.original pre{background:#273142;color:#e7edf4}.transitions{margin:12px}.tone0{--tone:var(--teal)}.tone1{--tone:var(--blue)}.tone2{--tone:var(--amber)}.tone3{--tone:var(--rose)}.tone4{--tone:var(--violet)}.tone5{--tone:var(--green)}
    @media(max-width:900px){.topin{grid-template-columns:1fr}.filters{justify-content:flex-start}#search{width:100%}.layout{grid-template-columns:1fr}aside{border-right:0;border-bottom:1px solid var(--line)}#list{max-height:280px}.grid2,.roundgrid{grid-template-columns:1fr}.audit{grid-template-columns:120px minmax(0,1fr)}main{padding:13px}}
  </style>
</head>
<body>
  <header class="top"><div class="topin"><div><h1>174 道错题细粒度根因审计</h1><div id="summary" class="summary">正在加载固定三层错误 taxonomy…</div></div><div class="filters"><select id="db"></select><select id="mechanism"></select><select id="family"></select><select id="stage"></select><input id="qid" inputmode="numeric" placeholder="qid"><input id="search" placeholder="搜索问题、标签、根因、SQL、轨迹"></div></div></header>
  <div class="layout"><aside><div id="listhead" class="listhead"></div><div id="list"></div></aside><main id="detail"><div class="empty">正在加载审计数据…</div></main></div>
  <script>
  const FIELDS=["精确标签","最早致命轮次","主根因","轨迹溯源","执行证据","伴随问题","最小修复","建议错误族","置信度","需补充验证"];
  const state={data:[],filtered:[],selected:null}; const $=s=>document.querySelector(s);
  const stable=v=>v===null?'null':v===undefined?'':typeof v==='string'?v:JSON.stringify(v,null,2);
  function node(tag,cls,text){const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined&&text!==null)n.textContent=String(text);return n}
  function add(p,...cs){cs.forEach(c=>p.appendChild(c));return p} function tone(v){let h=0;for(const c of String(v||''))h=(h*31+c.charCodeAt(0))>>>0;return `tone${h%6}`}
  function block(title,value){const b=node('div','block');add(b,node('h4','',title),node('pre','',stable(value||'（空）')));return b}
  function searchText(r){return [r.question_id,r.db_id,r.mechanism_family,r.error_family_code,r.error_family,r.instance_label,r.fine_grained_family,r.failure_stage,r.question,r.evidence,r.gold_sql,r.pred_sql,...Object.values(r.audit||{}),JSON.stringify(r.rounds||[])].join(' ').toLowerCase()}
  function options(el,values,label){el.replaceChildren();const all=node('option','',label);all.value='';el.appendChild(all);values.forEach(v=>{const o=node('option','',v);o.value=v;el.appendChild(o)})}
  function filter(){const db=$('#db').value,m=$('#mechanism').value,f=$('#family').value,st=$('#stage').value,q=$('#qid').value.trim(),s=$('#search').value.trim().toLowerCase();state.filtered=state.data.filter(r=>(!db||r.db_id===db)&&(!m||r.mechanism_family===m)&&(!f||r.error_family_code===f)&&(!st||r.failure_stage===st)&&(!q||String(r.question_id).includes(q))&&(!s||searchText(r).includes(s)));if(!state.filtered.some(r=>r.question_id===state.selected?.question_id))state.selected=state.filtered[0]||null;renderList();renderDetail()}
  function renderList(){$('#listhead').textContent=`当前 ${state.filtered.length} / ${state.data.length} 条`;const list=$('#list');list.replaceChildren();state.filtered.forEach(r=>{const b=node('button',`casebtn ${tone(r.mechanism_family)} ${r.question_id===state.selected?.question_id?'active':''}`);b.type='button';add(b,node('div','qid',`qid${r.question_id}`),node('div','preview',`${r.error_family_code} · ${r.instance_label}`));b.onclick=()=>{state.selected=r;renderList();renderDetail()};list.appendChild(b)})}
  function resultPane(v,title){const p=node('div','pane');p.appendChild(node('div','pt',title));if(!v){p.appendChild(node('div','error','无结果记录'));return p}const m=node('div','meta');add(m,node('span','badge',v.ok?'ok':'failed'),node('span','badge',`rows ${v.row_count??'unknown'}`),node('span','badge',v.truncated?'truncated':'not truncated'));p.appendChild(m);if(v.error){p.appendChild(node('div','error',v.error));return p}const w=node('div','tablewrap'),t=node('table'),thead=node('thead'),hr=node('tr');(v.columns||[]).forEach(c=>hr.appendChild(node('th','',c)));thead.appendChild(hr);t.appendChild(thead);const tb=node('tbody');(v.rows||[]).forEach(row=>{const tr=node('tr');row.forEach(x=>tr.appendChild(node('td','',stable(x))));tb.appendChild(tr)});t.appendChild(tb);w.appendChild(t);p.appendChild(w);return p}
  function original(title,value){const d=node('details','original');d.appendChild(node('summary','',title));d.appendChild(node('pre','',stable(value||'（空）')));return d}
  function roundView(r){const d=node('details',`round ${r.stage||''}`);d.appendChild(node('summary','',`Round ${r.round} · ${r.stage} · ${r.tool_call?.name||'无工具'}`));const body=node('div','roundbody');body.appendChild(block('本轮前记忆模块（完整中文翻译）',r.memory_before_zh));body.appendChild(original('展开查看本轮前记忆英文原文',r.memory_before));const g=node('div','roundgrid');add(g,block('think（完整中文翻译）',r.think_zh),block('tool_call',r.tool_call));body.appendChild(g);body.appendChild(original('展开查看 think 英文原文',r.think));body.appendChild(block('tool_result',r.tool_result));body.appendChild(block('本轮新增记忆（完整中文翻译）',r.memory_delta_zh));body.appendChild(original('展开查看本轮新增记忆英文原文',r.memory_delta));body.appendChild(block('本轮后记忆模块（程序 append 后的完整中文翻译）',r.memory_after_zh));body.appendChild(original('展开查看本轮后记忆英文原文',r.memory_after));if(r.compressor_error)body.appendChild(block('compressor_error',r.compressor_error));d.appendChild(body);return d}
  function renderDetail(){const r=state.selected,d=$('#detail');d.replaceChildren();if(!r){d.appendChild(node('div','empty','没有符合筛选条件的样本。'));return}const h=node('div','head'),title=node('div'),badges=node('div','badges');title.appendChild(node('h2','',`qid${r.question_id} · ${r.db_id}`));add(badges,node('span',`badge family ${tone(r.mechanism_family)}`,r.mechanism_family),node('span','badge',`${r.error_family_code} · ${r.error_family}`),node('span','badge',r.instance_label),node('span','badge',`首错阶段 ${r.failure_stage}`),node('span','badge',`${r.round_count} rounds`),node('span','badge',`schema ${r.schema_rounds}`),node('span','badge',`sql ${r.sql_rounds}`),node('span','badge',r.review_decision==='corrected'?'人工重写':'人工核验'));if(!r.terminated)badges.appendChild(node('span','badge warn','未正常终止'));add(h,title,badges);d.appendChild(h);
    const task=node('section');task.appendChild(node('h3','','问题与外部 Evidence'));task.appendChild(node('div','question',r.question));task.appendChild(node('div','evidence',r.evidence||'（无）'));d.appendChild(task);
    const audit=node('section');audit.appendChild(node('h3','','当前运行逐题人工根因结论'));const ag=node('div','audit');FIELDS.forEach(k=>add(ag,node('div','ak',k),node('div','av',r.audit[k]??'')));audit.appendChild(ag);d.appendChild(audit);
    const sql=node('section');sql.appendChild(node('h3','','SQL 对照'));const sg=node('div','grid2');add(sg,add(node('div','pane'),node('div','pt','gold_sql'),node('pre','',r.gold_sql||'（空）')),add(node('div','pane'),node('div','pt','pred_sql'),node('pre','',r.pred_sql||'（空）')));sql.appendChild(sg);d.appendChild(sql);
    const rs=node('section');rs.appendChild(node('h3','','执行结果对照'));const rg=node('div','grid2');add(rg,resultPane(r.gold_result,'gold_result'),resultPane(r.pred_result,'pred_result'));rs.appendChild(rg);d.appendChild(rs);
    const tr=node('section');tr.appendChild(node('h3','','阶段切换'));tr.appendChild(add(node('div','transitions'),node('pre','',stable(r.stage_transitions||[]))));d.appendChild(tr);
    const rounds=node('section');rounds.appendChild(node('h3','',`逐轮轨迹（${r.rounds.length} 轮）`));r.rounds.forEach(x=>rounds.appendChild(roundView(x)));d.appendChild(rounds);window.scrollTo({top:0,behavior:'instant'})}
  async function init(){try{const res=await fetch('manual_root_cause_audit.reviewed.index.json',{cache:'no-store'});if(!res.ok)throw new Error(`${res.status} ${res.statusText}`);state.data=await res.json();state.filtered=state.data;state.selected=state.data[0]||null;options($('#db'),[...new Set(state.data.map(r=>r.db_id))].sort(),'全部数据库');options($('#mechanism'),[...new Set(state.data.map(r=>r.mechanism_family))].sort(),'全部失败机制');options($('#family'),[...new Set(state.data.map(r=>r.error_family_code))].sort().map(code=>{const r=state.data.find(x=>x.error_family_code===code);return code}),'全部细粒度错误族');[...$('#family').options].slice(1).forEach(o=>{const r=state.data.find(x=>x.error_family_code===o.value);o.textContent=`${o.value} · ${r.error_family}`});options($('#stage'),[...new Set(state.data.map(r=>r.failure_stage))].sort(),'全部首错阶段');['#db','#mechanism','#family','#stage','#qid','#search'].forEach(s=>$(s).addEventListener(s.startsWith('#q')||s==='#search'?'input':'change',filter));$('#summary').textContent=`${state.data.length} 条 · 10 类失败机制 · 35 个固定错误族 · 逐题实例标签 · 可按首错阶段筛选`;renderList();renderDetail()}catch(e){$('#detail').innerHTML=`<div class="error">审计数据加载失败：${String(e)}<br>请通过 HTTP 服务打开本页面。</div>`}}
  init();
  </script>
</body></html>
'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("result_dir", type=Path)
    args = parser.parse_args()
    root = args.result_dir.resolve()
    rows, summary = build(root)
    taxonomy, taxonomy_markdown = taxonomy_artifacts(rows)
    (root / "manual_root_cause_audit.reviewed.index.json").write_text(
        json.dumps(rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    (root / "manual_root_cause_audit.reviewed.summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (root / "manual_root_cause_taxonomy.v3.json").write_text(
        json.dumps(taxonomy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (root / "manual_root_cause_taxonomy.v3.md").write_text(
        taxonomy_markdown, encoding="utf-8"
    )
    (root / "manual_root_cause_audit.viewer.v2.html").write_text(
        VIEWER_HTML, encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
