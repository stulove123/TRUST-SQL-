#!/usr/bin/env python3
"""Apply hand-written, root-cause-oriented trajectory tables for student_club."""

from __future__ import annotations

import re
from pathlib import Path


TARGET = Path("/root/autodl-tmp/text_to_sql_benchmarks/results/qwen35-4b-arcwise-plat-trustsql-full-final-thinking/student_club_wrong_analysis.md")


TABLES = {
    "1334": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 找到 `member`、`zip_code`，足够回答成长州问题。 |
| Round 2 | explore_schema | 查看 `member` 字段 | 已看到 `first_name`、`last_name`、`zip`。 |
| Round 3 | explore_schema | 查看 `major` | 与本题无关，探索有些分散。 |
| Round 4 | explore_schema | 查看 `event` | 与本题无关。 |
| Round 5 | explore_schema | 查看 `zip_code` | 已看到 `state`，可通过 zip 过滤 Illinois。 |
| Round 6 | propose_schema | 提出 `member` join `zip_code` | join 与过滤方向正确。 |
| Round 7 | generate_sql | 筛 Illinois 成员并拼接 full name | 三个人都找对了，但输出成单列 `Trent Smith`；gold 要 `first_name, last_name` 两列。 |
| Round 8 | confirm_answer | 确认单列 full name SQL | 根因是 full name 的评测形状与题面直觉不同：不能拼接成一列。 |""",
    "1338": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 相关表是 `event`、`budget`、`expense`。 |
| Round 2 | explore_schema | 查看 `expense` 建表 SQL | 已看到 `expense_date`、`approved`、`link_to_budget`。 |
| Round 3 | explore_schema | 查看 `event` 建表 SQL | 已看到 `event_name`、`event_date`，但真实日期带 `T12:00:00`。 |
| Round 4 | explore_schema | 查看 `attendance` | 本题不需要 attendance。 |
| Round 5 | explore_schema | 查看 `budget` | 找到 expense 到 event 的中间表。 |
| Round 6 | explore_schema | 用 `event_date='2019-10-08'` 查 October Meeting | 返回空，关键问题是 event_date 有时间后缀。 |
| Round 7 | explore_schema | 查看 event 样例 | 已能看到 `2019-10-08T12:00:00` 这种格式，但没有转成 LIKE/SUBSTR。 |
| Round 8 | explore_schema | 查 2019 年 10 月 events | 找到 October 月份事件，说明日期前缀匹配可行。 |
| Round 9 | explore_schema | 查 `expense_date='2019-10-08'` | 已找到 3 条 expense，且这就是 gold 的三条 approved。 |
| Round 10 | explore_schema | 又用 `ev.event_date='2019-10-08'` join 回 event | 再次空结果，耗尽轮数；根因是没把 event_date 改成 `LIKE '2019-10-08%'`，最终没有 SQL。 |""",
    "1339": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `member` 定位 Elijah，`expense` 算花费。 |
| Round 2 | explore_schema | 查看 `member/event/expense` 结构 | 已看到 `expense.cost`、`expense_date`、`link_to_budget`。 |
| Round 3 | explore_schema | 查 Elijah Allen | 找到对应 member id。 |
| Round 4 | generate_sql | 对 9/10 月 expense 直接 `AVG(cost)` | 得到 `74.0775`，这是 8 笔 expense 的平均；gold 是总 cost 除以 distinct event/budget 数。 |
| Round 5 | confirm_answer | 确认 `AVG(cost)` 版本 | 根因是聚合单位错：应 `SUM(cost) / COUNT(DISTINCT link_to_budget)=84.66`。 |""",
    "1340": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `event` 年份和 `budget.spent`。 |
| Round 2 | explore_schema | 查看 `event` | 已看到 `event_date`。 |
| Round 3 | explore_schema | 查看 `expense` | 不是主要口径，题目是 all events spent。 |
| Round 4 | explore_schema | 查看 `budget` | 已看到 `spent` 与 `link_to_event`。 |
| Round 5 | explore_schema | 查看 event 样例 | 确认年份可由 `SUBSTR(event_date,1,4)` 取得。 |
| Round 6 | explore_schema | 查看 expense 样例 | 探索冗余。 |
| Round 7 | explore_schema | 查看 budget 样例 | 确认 spent 有值。 |
| Round 8 | explore_schema | 查看带 event link 的 budget 样例 | join 路径明确。 |
| Round 9 | propose_schema | 提出 `budget` join `event` | 语义方向正确。 |
| Round 10 | generate_sql | 按年份 group by，同时输出 2019 spent、2020 spent、difference | 条件聚合公式对，但 `GROUP BY year` 把应为一行的结果拆成两行，还多输出两个中间列。 |""",
    "1359": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `budget` 与 `event`。 |
| Round 2 | explore_schema | 一次查看全部表结构 | 已看到 `budget.category/amount/link_to_event` 和 `event.event_name`。 |
| Round 3 | explore_schema | 查看 event_name 列表 | 确认 `Yearly Kickoff`、`October Meeting` 存在。 |
| Round 4 | explore_schema | 查看 Advertisement budget 记录 | 确认 Advertisement 有多条预算记录。 |
| Round 5 | explore_schema | 查两个目标 event id | 找到两个 event，join 路径明确。 |
| Round 6 | propose_schema | 提出候选 schema | 方向正确，但没有明确分子分母应分别按 event 条件聚合。 |
| Round 7 | generate_sql | 在同一行里把 SUM(amount) 同时当分子和分母 | 得到 1，说明没有按 event 区分 Yearly Kickoff 与 October Meeting。 |
| Round 8 | generate_sql | 按 event_name 列 Advertisement 总预算 | 返回 15 个 event，只是在探索分组结果。 |
| Round 9 | generate_sql | 只过滤 Yearly Kickoff，却仍把同一 SUM 当分子分母 | 仍得到 1，没有纳入 October Meeting。 |
| Round 10 | generate_sql | 用两个子查询算比例，但外层 `FROM budget` 导致重复 15 行，且整数除法/round 变成 2.0 | 根因是标量查询外层重复 + 未 CAST REAL + 不该 round；正确是 `150/55=2.727...`。 |""",
    "1371": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `event` 与 `attendance`。 |
| Round 2 | explore_schema | 查看 `event/attendance/member` 结构 | 已看到 `event_name` 和 `attendance.link_to_event`。 |
| Round 3 | propose_schema | 提出 attendance join event | join 方向正确。 |
| Round 4 | confirm_answer | 直接确认 `event_name = 'Women's Soccer'` 的 SQL | SQL 字符串没有转义单引号，SQLite 在 `Women'` 处截断，最终语法错误；应写 `Women''s Soccer`。 |""",
    "1376": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `event` 和 `budget`。 |
| Round 2 | explore_schema | 查看 `event` | 找到 `status`、`event_name`。 |
| Round 3 | explore_schema | 查看 `major` | 与本题无关。 |
| Round 4 | explore_schema | 查看 `zip_code` | 与本题无关。 |
| Round 5 | explore_schema | 查看 `attendance` | 与本题无关。 |
| Round 6 | explore_schema | 查看 `budget` | 找到 `spent`、`amount`、`link_to_event`。 |
| Round 7 | explore_schema | 查看 `expense` | 与 spend-to-budget 主口径不直接相关。 |
| Round 8 | explore_schema | 查看 `member` | 与本题无关。 |
| Round 9 | propose_schema | 提出 `event` join `budget` | 语义方向正确。 |
| Round 10 | generate_sql | 对 closed events 算 spend/amount ratio 并 `ORDER BY ratio DESC LIMIT 1` | 找到一个最高并列事件，但 gold 要全部 3 个并列最高；还多输出 status/spent/amount/ratio。 |""",
    "1381": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `member` 与 `attendance`。 |
| Round 2 | explore_schema | 查看 `member` 字段 | 已看到 `first_name`、`last_name`、`member_id`。 |
| Round 3 | explore_schema | 查看 `event` 字段 | 本题只需要 attendance count，event 内容不关键。 |
| Round 4 | explore_schema | 查看 `attendance` 字段 | 找到 `link_to_member` 和 `link_to_event`。 |
| Round 5 | propose_schema | 提出 member-attendance 方案 | 过滤逻辑正确。 |
| Round 6 | generate_sql | 分组找参加超过 7 次的 members，并拼接姓名 | 29 人集合正确，但输出成单列 full name。 |
| Round 7 | confirm_answer | 确认单列 full name SQL | 根因是输出形状错；gold 要 `first_name, last_name` 两列。 |""",
    "1389": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `expense -> budget -> event`。 |
| Round 2 | explore_schema | 查看 `event` | 找到 `event_name`。 |
| Round 3 | explore_schema | 查看 `major` | 无关。 |
| Round 4 | explore_schema | 查看 `attendance` | 无关。 |
| Round 5 | explore_schema | 查看 `budget` | 找到 `link_to_event`。 |
| Round 6 | explore_schema | 查看 `expense` | 找到 `cost` 和 `link_to_budget`。 |
| Round 7 | explore_schema | 查看 `member` | 无关。 |
| Round 8 | propose_schema | 提出 expense-budget-event 链路 | 方向正确。 |
| Round 9 | generate_sql | 首次聚合时误写 `e.event_name` | `event_name` 不在 expense 表，报错。 |
| Round 10 | generate_sql | 修成 `ev.event_name`，按 total cost desc/name asc 取第一 | event 定位正确为 `Yearly Kickoff`，但多输出 `total_cost`。 |""",
    "1392": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `income`。 |
| Round 2 | explore_schema | 查看 `income` 建表 SQL | 已看到 `date_received`、`amount`、`source`。 |
| Round 3 | explore_schema | 查看 `income` 字段 | 字段确认充分。 |
| Round 4 | generate_sql | 按 2019-09 日期范围聚合 source，按 amount 降序取 1 | 找到正确 source `School Appropration`，但多输出了 `SUM(amount)=3000`。 |
| Round 5 | confirm_answer | 确认多列 SQL | 根因是输出形状错；gold 只要 source。 |""",
    "1398": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `event` 与 `budget`。 |
| Round 2 | explore_schema | 一次查看所有表结构 | 已看到 `budget.category/spent/link_to_event` 和 `event.event_name`。 |
| Round 3 | propose_schema | 提出 event-budget 链路 | 方向正确。 |
| Round 4 | confirm_answer | 直接确认按 Advertisement spent desc 取 1 的 SQL | 找到正确 event `Yearly Kickoff`，但多输出了 `spent=122.06`；gold 只要 event name。 |""",
    "1399": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `member`、`attendance`、`event`。 |
| Round 2 | explore_schema | 查看三表结构 | join 路径完整。 |
| Round 3 | propose_schema | 提出 member-attendance-event 链路 | 方向正确。 |
| Round 4 | generate_sql | 用未转义的 `Women's Soccer` 查询 | 先因单引号报语法错。 |
| Round 5 | generate_sql | 修正为 `Women''s Soccer` 后计数 | 返回 `1`，说明 Maya 参加了，但题目要求 YES/NO。 |
| Round 6 | confirm_answer | 确认 count 版本 | 根因是存在性结果没有映射成 `YES`。 |""",
    "1410": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `member` 与 `expense`。 |
| Round 2 | explore_schema | 查看 `member` 字段 | 已看到 `first_name`、`last_name`、`member_id`。 |
| Round 3 | explore_schema | 查看 `expense` 字段 | 已看到 `cost` 和 `link_to_member`。 |
| Round 4 | generate_sql | 对指定 member_id 求 `SUM(cost)`，并拼接 full name | 总花费 `866.25` 正确，但姓名拼成一列，输出只有 2 列。 |
| Round 5 | confirm_answer | 确认拼接姓名版本 | 根因是输出形状错；gold 要 `first_name, last_name, total_cost` 三列。 |""",
    "1457": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `member` 与 `expense`。 |
| Round 2 | explore_schema | 查看 `expense/member` 结构 | 已看到单笔 `expense.cost` 和成员联系方式。 |
| Round 3 | propose_schema | 提出 member-expense 链路 | 缺少关键粒度判断：比较对象是单笔 expense，不是会员总花费。 |
| Round 4 | generate_sql | 先按 member 汇总总花费，再和总花费平均比较 | 只反复返回 Sacha，且由于 join 写法出现重复行。 |
| Round 5 | generate_sql | 修掉重复，但仍比较 member total cost | 最终只剩 Sacha；gold 需要有任一单笔 expense 超过全体平均单笔 cost 的 3 人。 |
| Round 6 | confirm_answer | 确认 member-total 粒度 SQL | 根因是聚合粒度错：应在 expense 行级过滤 `cost > AVG(cost)`。 |""",
    "1464": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `income` 与 `member`。 |
| Round 2 | explore_schema | 查看 `member` 字段 | 已看到主键是 `member_id`，没有 `link_to_member`。 |
| Round 3 | explore_schema | 查看 `income` 字段 | 已看到 `date_received`、`amount`、`link_to_member`。 |
| Round 4 | propose_schema | 提出候选 schema | join 方向应是 `income.link_to_member = member.member_id`。 |
| Round 5 | confirm_answer | 确认错误 join/date SQL | 写成 `m.link_to_member = i.link_to_member` 导致列不存在；日期也写成 `9/9/2019`，而库里是 `2019-09-09`。 |""",
}


def replace_table(section: str, table: str) -> str:
    marker = "\n### 运行轨迹\n"
    if marker not in section:
        return section.rstrip() + "\n\n" + table.rstrip() + "\n"
    return section[: section.index(marker)].rstrip() + "\n\n" + table.rstrip() + "\n"


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")
    matches = list(re.finditer(r"^## qid(\d+)\b.*$", text, re.M))
    pieces = []
    last = 0
    changed = []
    for idx, match in enumerate(matches):
        qid = match.group(1)
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        if idx + 1 == len(matches):
            next_h = re.search(r"^##\s+", text[match.end():], re.M)
            if next_h:
                end = match.end() + next_h.start()
        pieces.append(text[last:start])
        section = text[start:end]
        if qid in TABLES:
            section = replace_table(section, TABLES[qid])
            changed.append(qid)
        pieces.append(section)
        last = end
    pieces.append(text[last:])
    TARGET.write_text("".join(pieces), encoding="utf-8")
    print(f"updated {len(changed)} qids:", ", ".join(changed))


if __name__ == "__main__":
    main()
