#!/usr/bin/env python3
"""Extract errors caused by failure to follow supplied external evidence."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


RESULTS_DIR = Path(
    "/root/autodl-tmp/text_to_sql_benchmarks/results/"
    "qwen35-4b-arcwise-plat-full-default20-10-final-schema-prompt-20260714"
)


DIRECT_CONTRADICTION = {
    62, 77, 82, 85, 95, 117, 137, 149, 173, 192, 197, 236, 341, 407,
    466, 483, 533, 665, 716, 743, 744, 775, 829, 861, 866, 872, 877,
    881, 896, 897, 944, 963, 967, 972, 977, 1001, 1031, 1037, 1102,
    1115, 1144, 1168, 1171, 1229, 1238, 1247, 1257, 1265, 1270, 1281,
    1410, 1481, 1486, 1490, 1498, 1524,
}


FAILED_OPERATIONALIZATION = {
    116, 145, 169, 219, 352, 371, 408, 416, 469, 529, 587, 604, 683,
    788, 875, 937, 955, 1136, 1185, 1187, 1227, 1243, 1476,
}


METHODS = {
    "direct_contradiction": {
        "label": "明确违背 evidence",
        "definition": (
            "Evidence 已足以确定关键公式、取值、排序方向、输出字段或过滤条件，"
            "但最终 SQL 直接漏写、反写或改写了该信息。"
        ),
    },
    "failed_operationalization": {
        "label": "引用了 evidence 但落地失败",
        "definition": (
            "模型表面采用了 evidence，但把它落在错误表、错误作用域、错误实体粒度，"
            "或因整数除法、日期解析等 SQL 实现问题使 evidence 没有真正生效。"
        ),
    },
}


def main() -> None:
    source_path = RESULTS_DIR / "dual_taxonomy_audit_174.compact.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    by_qid = {int(row["question_id"]): row for row in source}
    selected = DIRECT_CONTRADICTION | FAILED_OPERATIONALIZATION
    if len(source) != 174 or not selected <= set(by_qid):
        raise ValueError("source run or qid selection does not match the 174-case audit")
    if DIRECT_CONTRADICTION & FAILED_OPERATIONALIZATION:
        raise ValueError("evidence categories must be mutually exclusive")

    records = []
    for qid in sorted(selected):
        source_row = by_qid[qid]
        category = (
            "direct_contradiction"
            if qid in DIRECT_CONTRADICTION
            else "failed_operationalization"
        )
        records.append(
            {
                "question_id": str(qid),
                "db_id": source_row["db_id"],
                "category": category,
                "category_label": METHODS[category]["label"],
                "question": source_row["question"],
                "external_evidence": source_row["evidence"],
                "pred_sql": source_row["pred_sql"],
                "gold_sql": source_row["gold_sql"],
                "root_cause": source_row["classification"]["root_cause"],
                "earliest_fatal_round": source_row["classification"]["earliest_fatal_round"],
                "sql_surface": source_row["classification"]["sql_surface"],
                "agent_root_cause": source_row["classification"]["agent_root_cause"],
            }
        )

    category_counts = Counter(row["category"] for row in records)
    database_counts = Counter(row["db_id"] for row in records)
    summary = {
        "source_wrong_cases": len(source),
        "evidence_noncompliance_total": len(records),
        "share_of_wrong_cases": len(records) / len(source),
        "categories": {
            key: {
                **METHODS[key],
                "count": category_counts[key],
                "qids": [
                    int(row["question_id"])
                    for row in records
                    if row["category"] == key
                ],
            }
            for key in METHODS
        },
        "database_counts": dict(database_counts.most_common()),
        "exclusion_rule": (
            "Evidence 与最终错误无直接因果关系，或模型只是额外使用了无关 evidence，"
            "不计入“不遵循 evidence”。"
        ),
    }

    (RESULTS_DIR / "external_evidence_noncompliance_174.json").write_text(
        json.dumps({"summary": summary, "records": records}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# 174 道错题中的外部 Evidence 不遵循审计",
        "",
        f"共识别 **{len(records)} / {len(source)}（{len(records) / len(source):.2%}）** 道。",
        "",
        "## 判定口径",
        "",
    ]
    for key, method in METHODS.items():
        lines.append(
            f"- **{method['label']}**：{method['definition']}共 {category_counts[key]} 道。"
        )
    lines.extend(
        [
            "- Evidence 与错误无直接因果关系，或模型只是过度使用无关 evidence，不计入。",
            "",
            "## 按数据库统计",
            "",
            "| 数据库 | 数量 |",
            "|---|---:|",
        ]
    )
    for db_id, count in database_counts.most_common():
        lines.append(f"| {db_id} | {count} |")
    for key, method in METHODS.items():
        category_rows = [row for row in records if row["category"] == key]
        lines.extend(
            [
                "",
                f"## {method['label']}（{len(category_rows)} 道）",
                "",
            ]
        )
        for row in category_rows:
            lines.extend(
                [
                    f"### qid{row['question_id']} · {row['db_id']}",
                    "",
                    f"- **External evidence**：{row['external_evidence']}",
                    f"- **最早致命轮次**：{row['earliest_fatal_round'] or '未定位'}",
                    f"- **根因**：{row['root_cause']}",
                    f"- **SQL 表层错误**：`{row['sql_surface']['code']}` · {row['sql_surface']['subtype']}",
                    "",
                ]
            )
    (RESULTS_DIR / "external_evidence_noncompliance_174.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
