#!/usr/bin/env python3
"""Build the clause-level plus agent-cause audit for the current 174 errors.

The source is the independently reviewed per-case evidence from the current
498-example run. Legacy family names and codes are deliberately omitted from
the generated records. Every qid is assigned exactly one SQL-surface primary
label and exactly one agent-root primary label.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_RESULTS = Path(
    "/root/autodl-tmp/text_to_sql_benchmarks/results/"
    "qwen35-4b-arcwise-plat-full-default20-10-final-schema-prompt-20260714"
)


SQL_SURFACE_SPECS: dict[str, dict[str, Any]] = {
    "SEL_INCORRECT_PROJECTION": {
        "family": "SELECT",
        "subtype": "输出字段或实体投影错误",
        "qids": [24, 28, 45, 46, 236, 465, 530, 694, 937],
    },
    "SEL_INCORRECT_EXPRESSION": {
        "family": "SELECT",
        "subtype": "派生表达式、类型、尺度或值编码错误",
        "qids": [62, 77, 85, 115, 116, 118, 169, 230, 637, 716, 743, 879, 880, 954, 962, 1094, 1149, 1185, 1410, 1529, 1531],
    },
    "SEL_INCORRECT_AGGREGATION": {
        "family": "SELECT",
        "subtype": "聚合函数、计数实体或度量定义错误",
        "qids": [100, 117, 197, 219, 383, 665, 963, 1037, 1169, 1241, 1243, 1247, 1252, 1255, 1267, 1362],
    },
    "SEL_MISSING_OUTPUT_COMPONENT": {
        "family": "SELECT",
        "subtype": "复合答案输出成分缺失",
        "qids": [173, 744, 829],
    },
    "FROM_WRONG_TABLE": {
        "family": "FROM / JOIN",
        "subtype": "事实表、数据源或实体层级错误",
        "qids": [39, 347, 352, 371, 416, 483, 529, 875, 897, 948, 1486, 1490, 1524],
    },
    "FROM_MISSING_RELATION": {
        "family": "FROM / JOIN",
        "subtype": "缺少必要表、桥表或关系路径",
        "qids": [95, 189, 207, 253, 408, 640, 685, 824],
    },
    "FROM_WRONG_JOIN_KEY": {
        "family": "FROM / JOIN",
        "subtype": "JOIN 键或关系角色错误",
        "qids": [125, 587, 775, 1028, 1036, 1102, 1146],
    },
    "FROM_EXCESS_JOIN": {
        "family": "FROM / JOIN",
        "subtype": "多余 JOIN 导致事实记录删失",
        "qids": [215, 788, 1189],
    },
    "FROM_JOIN_MULTIPLICATION": {
        "family": "FROM / JOIN",
        "subtype": "JOIN 放大导致聚合重复加权",
        "qids": [152, 201, 263, 683, 1227, 1339],
    },
    "WHERE_MISSING_CONDITION": {
        "family": "WHERE",
        "subtype": "必要过滤条件缺失",
        "qids": [11, 23, 25, 36, 48, 750, 977],
    },
    "WHERE_NULL_SEMANTICS": {
        "family": "WHERE",
        "subtype": "NULL、哨兵值或有效域处理错误",
        "qids": [40, 726, 791, 990],
    },
    "WHERE_WRONG_VALUE": {
        "family": "WHERE",
        "subtype": "枚举、实体名称、内部 ID 或字面值链接错误",
        "qids": [26, 83, 93, 136, 137, 466, 469, 989, 1115, 1265],
    },
    "WHERE_SCOPE_OR_BOOLEAN": {
        "family": "WHERE",
        "subtype": "过滤作用域、布尔组合或存在性语义错误",
        "qids": [145, 192, 409, 896, 1001, 1136, 1187, 1270],
    },
    "WHERE_EXCESS_CONDITION": {
        "family": "WHERE",
        "subtype": "无依据附加过滤条件",
        "qids": [414, 972, 1387],
    },
    "WHERE_DATE_ARITHMETIC": {
        "family": "WHERE",
        "subtype": "日期格式、时间区间或年龄条件错误",
        "qids": [533, 861, 866, 872, 955, 1031, 1171, 1229, 1257, 1482, 1509],
    },
    "GROUP_AGGREGATION_LAYER": {
        "family": "GROUP BY / HAVING",
        "subtype": "聚合层缺失、顺序错误或子查询层级错误",
        "qids": [281, 592, 604, 1322, 1472, 1481, 1498],
    },
    "GROUP_WRONG_KEY_OR_GRAIN": {
        "family": "GROUP BY / HAVING",
        "subtype": "分组键或答案粒度错误",
        "qids": [27, 881, 1476],
    },
    "ORDER_TIE_SEMANTICS": {
        "family": "ORDER BY / LIMIT",
        "subtype": "并列排名或并列极值被错误截断",
        "qids": [17, 212, 349, 728, 736, 794, 1092, 1376],
    },
    "ORDER_WRONG_DIRECTION": {
        "family": "ORDER BY / LIMIT",
        "subtype": "排序方向或极值方向错误",
        "qids": [82, 877, 967, 1168, 1238, 1281],
    },
    "ORDER_LIMIT_OFFSET": {
        "family": "ORDER BY / LIMIT",
        "subtype": "LIMIT、OFFSET 或 Top-k 数量错误",
        "qids": [50, 129, 412, 459, 480, 1078, 1357],
    },
    "ORDER_SAMPLE_AS_GLOBAL": {
        "family": "ORDER BY / LIMIT",
        "subtype": "抽样值或局部候选误作全局极值",
        "qids": [37, 1032, 1144],
    },
    "ORDER_WRONG_POST_AGG_SELECTION": {
        "family": "ORDER BY / LIMIT",
        "subtype": "聚合后排序键或关联记录选择错误",
        "qids": [671, 1011],
    },
    "LOGICAL_NEGATION_OR_SET": {
        "family": "Logical equivalence",
        "subtype": "否定、交集或集合等价改写错误",
        "qids": [41, 341],
    },
    "EXEC_NO_FINAL_SQL": {
        "family": "Execution / protocol",
        "subtype": "预算耗尽且没有最终 SQL",
        "qids": [149, 407, 944],
    },
    "EXEC_SYNTAX_IDENTIFIER": {
        "family": "Execution / protocol",
        "subtype": "标识符、函数调用或 SQL 语法恢复失败",
        "qids": [1014, 1192],
    },
    "EVAL_GOLD_TIMEOUT": {
        "family": "Evaluation / gold",
        "subtype": "Gold 执行超时造成假阴性",
        "qids": [518, 701],
    },
}


AGENT_ROOT_SPECS: dict[str, dict[str, Any]] = {
    "A_OUTPUT_CONTRACT": {
        "label": "输出契约理解错误",
        "qids": [28, 45, 46, 173, 230, 236, 465, 530, 637, 694, 744, 829, 1362, 1410],
    },
    "A_CALCULATION": {
        "label": "数值、类型或时间计算推理错误",
        "qids": [62, 77, 85, 115, 116, 117, 118, 169, 533, 665, 716, 861, 866, 872, 879, 880, 954, 955, 962, 1031, 1094, 1149, 1171, 1185, 1229, 1257, 1482, 1509, 1529, 1531],
    },
    "A_AGGREGATION": {
        "label": "聚合对象、粒度或层级推理错误",
        "qids": [27, 100, 197, 219, 281, 383, 592, 604, 881, 963, 1037, 1169, 1241, 1243, 1247, 1252, 1255, 1267, 1322, 1472, 1476, 1481, 1498],
    },
    "A_JOIN_EVIDENCE": {
        "label": "关系路径或 JOIN 证据判断错误",
        "qids": [95, 125, 149, 189, 207, 253, 408, 587, 685, 775, 824, 1028, 1036, 1102, 1146],
    },
    "A_JOIN_CARDINALITY": {
        "label": "JOIN 基数与实体重复性推理错误",
        "qids": [152, 201, 215, 263, 683, 788, 1189, 1227, 1339],
    },
    "A_SCHEMA_UTILIZATION": {
        "label": "Schema 证据选择或利用失败",
        "qids": [24, 39, 347, 352, 371, 416, 483, 529, 640, 875, 897, 937, 948, 1187, 1486, 1490, 1524],
    },
    "A_VALUE_LINKING": {
        "label": "值、实体名称或内部 ID 链接错误",
        "qids": [26, 83, 93, 136, 137, 466, 469, 989, 1115, 1265],
    },
    "A_SEMANTIC_REASONING": {
        "label": "问题语义、过滤或排序逻辑推理错误",
        "qids": [11, 17, 23, 25, 36, 37, 40, 41, 48, 50, 82, 129, 145, 192, 212, 341, 349, 407, 409, 412, 414, 459, 480, 671, 726, 728, 736, 743, 750, 791, 794, 877, 896, 967, 972, 977, 990, 1001, 1011, 1032, 1078, 1092, 1136, 1144, 1168, 1238, 1270, 1281, 1357, 1376, 1387],
    },
    "A_MEMORY_UTILIZATION": {
        "label": "已获得的纠正证据未被后续决策利用",
        "qids": [944],
    },
    "A_ACTION_GROUNDING": {
        "label": "正确意图未落地为合法 SQL 或工具参数",
        "qids": [1014, 1192],
    },
    "A_EVALUATION_GOLD": {
        "label": "评测或 Gold 执行问题",
        "qids": [518, 701],
    },
}


TRACE_EVENT_LABELS = {
    "format_error": "出现工具调用格式错误",
    "stage_violation": "出现阶段工具违规",
    "auto_stage_transition": "Schema 阶段自动切换",
    "non_termination": "未正常调用终止工具",
    "fallback_sql": "使用 fallback SQL",
    "sql_budget_exhausted": "SQL 阶段预算耗尽",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    return parser.parse_args()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def invert_specs(specs: dict[str, dict[str, Any]], expected: set[int], name: str) -> dict[int, tuple[str, dict[str, Any]]]:
    output: dict[int, tuple[str, dict[str, Any]]] = {}
    for code, spec in specs.items():
        for raw_qid in spec["qids"]:
            qid = int(raw_qid)
            if qid in output:
                raise ValueError(f"{name}: duplicate qid {qid}: {output[qid][0]} and {code}")
            output[qid] = (code, spec)
    missing = expected - set(output)
    extra = set(output) - expected
    if missing or extra:
        raise ValueError(f"{name}: missing={sorted(missing)}, extra={sorted(extra)}")
    return output


def trace_events(record: dict[str, Any]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for round_record in record.get("rounds") or []:
        tool_call = round_record.get("tool_call")
        if tool_call is None:
            counts["format_error"] += 1
        tool_name = (tool_call or {}).get("name")
        allowed_tools = set(round_record.get("allowed_tools") or [])
        if tool_name and allowed_tools and tool_name not in allowed_tools:
            counts["stage_violation"] += 1
    if any(
        transition.get("auto_stage_transition")
        for transition in record.get("stage_transitions") or []
    ):
        counts["auto_stage_transition"] += 1
    if not record.get("terminated"):
        counts["non_termination"] += 1
    if record.get("used_fallback_sql"):
        counts["fallback_sql"] += 1
    if record.get("sql_stage_budget_exhausted"):
        counts["sql_budget_exhausted"] += 1
    return [
        {"code": code, "label": TRACE_EVENT_LABELS[code], "count": count}
        for code, count in counts.items()
    ]


def build_taxonomy() -> dict[str, Any]:
    sql_families: dict[str, list[dict[str, str]]] = {}
    for code, spec in SQL_SURFACE_SPECS.items():
        sql_families.setdefault(spec["family"], []).append({"code": code, "label": spec["subtype"]})
    return {
        "version": 1,
        "name": "Text-to-SQL 双层错误 taxonomy",
        "principles": [
            "每题恰好一个 SQL 表层主标签，用于互斥统计。",
            "每题恰好一个 Agent 主根因，指向最早导致最终失败的决策机制。",
            "格式错误、阶段违规、fallback 和未终止是轨迹事件，不自动替代主根因。",
            "纯额外输出列和纯行顺序差异在 projection-relaxed 评测下不作为错误。",
            "没有最终 SQL 的题归入 Execution / protocol，而不是强行归入某个 SQL 子句。",
        ],
        "sql_surface_families": sql_families,
        "agent_root_causes": [
            {"code": code, "label": spec["label"]} for code, spec in AGENT_ROOT_SPECS.items()
        ],
        "trace_events": [{"code": code, "label": label} for code, label in TRACE_EVENT_LABELS.items()],
    }


def summary_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# 174 道错题双层 Taxonomy 重新审计",
        "",
        "本审计针对 `qwen35-4b-arcwise-plat-full-default20-10-final-schema-prompt-20260714` 的 174 道错题。",
        "每题重新赋予一个 SQL 表层主标签和一个 Agent 主根因；旧错误族名称与代码不进入新记录。",
        "",
        "## SQL 表层错误",
        "",
        "| 一级错误族 | 数量 | 比例 |",
        "|---|---:|---:|",
    ]
    total = summary["total"]
    for label, count in summary["sql_surface_families"].items():
        lines.append(f"| {label} | {count} | {count / total:.2%} |")
    lines.extend(["", "## SQL 细粒度子类", "", "| 代码 | 子类 | 数量 | 比例 |", "|---|---|---:|---:|"])
    for code, item in summary["sql_surface_subtypes"].items():
        lines.append(f"| `{code}` | {item['label']} | {item['count']} | {item['count'] / total:.2%} |")
    lines.extend(["", "## Agent 主根因", "", "| 代码 | 根因 | 数量 | 比例 |", "|---|---|---:|---:|"])
    for code, item in summary["agent_root_causes"].items():
        lines.append(f"| `{code}` | {item['label']} | {item['count']} | {item['count'] / total:.2%} |")
    lines.extend(["", "## 轨迹事件", "", "| 事件 | 涉及样本数 |", "|---|---:|"])
    for label, count in summary["trace_event_episode_counts"].items():
        lines.append(f"| {label} | {count} |")
    lines.extend(
        [
            "",
            "## 说明",
            "",
            "- SQL 主标签描述最终答案在关系查询结构上的首要偏差。",
            "- Agent 主根因描述最早产生该偏差的推理、证据利用或动作落地机制。",
            "- `Execution / protocol` 用于没有最终 SQL 或始终无法形成合法 SQL 的样本。",
            "- `Evaluation / gold` 用于预测语义正确但 Gold 无法执行完成的假阴性。",
        ]
    )
    return "\n".join(lines) + "\n"


def taxonomy_markdown(taxonomy: dict[str, Any]) -> str:
    lines = ["# Text-to-SQL 双层错误 Taxonomy v1", "", "## 判定原则", ""]
    lines.extend(f"- {item}" for item in taxonomy["principles"])
    lines.extend(["", "## 第一层：SQL 表层错误", ""])
    for family, subtypes in taxonomy["sql_surface_families"].items():
        lines.append(f"### {family}")
        lines.append("")
        lines.extend(f"- `{item['code']}`：{item['label']}" for item in subtypes)
        lines.append("")
    lines.extend(["## 第二层：Agent 主根因", ""])
    lines.extend(f"- `{item['code']}`：{item['label']}" for item in taxonomy["agent_root_causes"])
    lines.extend(["", "## 独立轨迹事件", ""])
    lines.extend(f"- `{item['code']}`：{item['label']}" for item in taxonomy["trace_events"])
    return "\n".join(lines) + "\n"


def per_case_markdown(records: list[dict[str, Any]]) -> str:
    lines = [
        "# 174 道错题逐题双层 Taxonomy 人工审计",
        "",
        "每题仅保留一个 SQL 表层主标签和一个 Agent 主根因；轨迹事件独立列示。",
        "逐轮 think、工作记忆、工具参数与返回结果请在配套 HTML viewer 中查看。",
        "",
    ]
    for record in records:
        classification = record["classification"]
        sql_surface = classification["sql_surface"]
        agent_root = classification["agent_root_cause"]
        events = classification["trace_events"]
        event_text = "；".join(
            f"{event['label']} x {event['count']}" for event in events
        ) or "无"
        lines.extend(
            [
                f"## qid{record['question_id']} · {record['db_id']}",
                "",
                f"- **SQL 表层主标签**：`{sql_surface['code']}` · {sql_surface['family']} / {sql_surface['subtype']}",
                f"- **Agent 主根因**：`{agent_root['code']}` · {agent_root['label']}",
                f"- **最早致命轮次**：{classification['earliest_fatal_round'] or '未定位'}",
                f"- **首错阶段**：{classification['failure_stage']}",
                f"- **轨迹事件**：{event_text}",
                "",
                f"**问题**：{record['question']}",
                "",
                f"**主根因**：{classification['root_cause']}",
                "",
                f"**轨迹溯源**：{classification['trajectory_evidence']}",
                "",
                f"**执行证据**：{classification['execution_evidence']}",
                "",
                f"**最小修复**：{classification['minimal_fix']}",
                "",
            ]
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    source_path = args.results_dir / "manual_root_cause_audit.reviewed.index.json"
    source_records = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(source_records, list) or len(source_records) != 174:
        raise ValueError(f"expected 174 source records, got {len(source_records)}")
    expected = {int(record["question_id"]) for record in source_records}
    sql_by_qid = invert_specs(SQL_SURFACE_SPECS, expected, "SQL taxonomy")
    agent_by_qid = invert_specs(AGENT_ROOT_SPECS, expected, "Agent taxonomy")

    output_records: list[dict[str, Any]] = []
    compact_records: list[dict[str, Any]] = []
    for source in source_records:
        qid = int(source["question_id"])
        sql_code, sql_spec = sql_by_qid[qid]
        agent_code, agent_spec = agent_by_qid[qid]
        audit = source.get("audit") or {}
        classification = {
            "sql_surface": {
                "family": sql_spec["family"],
                "code": sql_code,
                "subtype": sql_spec["subtype"],
                "secondary": [],
            },
            "agent_root_cause": {
                "code": agent_code,
                "label": agent_spec["label"],
            },
            "failure_stage": source.get("failure_stage"),
            "earliest_fatal_round": audit.get("最早致命轮次"),
            "root_cause": audit.get("主根因"),
            "trajectory_evidence": audit.get("轨迹溯源"),
            "execution_evidence": audit.get("执行证据"),
            "minimal_fix": audit.get("最小修复"),
            "confidence": audit.get("置信度"),
            "trace_events": trace_events(source),
        }
        record = {
            "question_id": str(qid),
            "db_id": source.get("db_id"),
            "classification": classification,
            "audit_method": "基于当前 episode 原始轨迹与逐题独立审计证据重新赋予双层标签；旧 taxonomy 标签不进入新记录",
            "question": source.get("question"),
            "evidence": source.get("evidence"),
            "gold_sql": source.get("gold_sql"),
            "pred_sql": source.get("pred_sql"),
            "gold_result": source.get("gold_result"),
            "pred_result": source.get("pred_result"),
            "audit": {
                key: audit.get(key)
                for key in ("最早致命轮次", "主根因", "轨迹溯源", "执行证据", "伴随问题", "最小修复", "置信度", "需补充验证")
            },
            "round_count": source.get("round_count"),
            "schema_rounds": source.get("schema_rounds"),
            "sql_rounds": source.get("sql_rounds"),
            "returns_used": source.get("returns_used"),
            "stage_transitions": source.get("stage_transitions"),
            "used_fallback_sql": source.get("used_fallback_sql"),
            "terminated": source.get("terminated"),
            "evaluation_mode": source.get("evaluation_mode"),
            "rounds": source.get("rounds") or [],
        }
        output_records.append(record)
        compact_records.append({key: value for key, value in record.items() if key != "rounds"})

    output_records.sort(key=lambda row: int(row["question_id"]))
    compact_records.sort(key=lambda row: int(row["question_id"]))
    sql_family_counts = Counter(row["classification"]["sql_surface"]["family"] for row in output_records)
    sql_subtype_counts = Counter(row["classification"]["sql_surface"]["code"] for row in output_records)
    agent_counts = Counter(row["classification"]["agent_root_cause"]["code"] for row in output_records)
    event_counts = Counter(
        event["label"] for row in output_records for event in row["classification"]["trace_events"]
    )
    summary = {
        "source_run": args.results_dir.name,
        "total": len(output_records),
        "taxonomy_version": 1,
        "old_taxonomy_fields_in_output": False,
        "sql_surface_families": dict(sql_family_counts.most_common()),
        "sql_surface_subtypes": {
            code: {"label": SQL_SURFACE_SPECS[code]["subtype"], "count": count}
            for code, count in sql_subtype_counts.most_common()
        },
        "agent_root_causes": {
            code: {"label": AGENT_ROOT_SPECS[code]["label"], "count": count}
            for code, count in agent_counts.most_common()
        },
        "trace_event_episode_counts": dict(event_counts.most_common()),
        "databases": dict(Counter(row["db_id"] for row in output_records).most_common()),
        "failure_stages": dict(
            Counter(row["classification"]["failure_stage"] for row in output_records).most_common()
        ),
    }
    taxonomy = build_taxonomy()

    write_json(args.results_dir / "dual_taxonomy.v1.json", taxonomy)
    (args.results_dir / "dual_taxonomy.v1.md").write_text(taxonomy_markdown(taxonomy), encoding="utf-8")
    write_json(args.results_dir / "dual_taxonomy_audit_174.index.json", output_records)
    write_json(args.results_dir / "dual_taxonomy_audit_174.compact.json", compact_records)
    with (args.results_dir / "dual_taxonomy_audit_174.jsonl").open("w", encoding="utf-8") as handle:
        for record in compact_records:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    write_json(args.results_dir / "dual_taxonomy_audit_174.summary.json", summary)
    (args.results_dir / "dual_taxonomy_audit_174.md").write_text(summary_markdown(summary), encoding="utf-8")
    (args.results_dir / "dual_taxonomy_audit_174.per_case.md").write_text(
        per_case_markdown(output_records), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
