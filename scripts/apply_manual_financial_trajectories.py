#!/usr/bin/env python3
"""Apply hand-written, root-cause-oriented trajectory tables for financial."""

from __future__ import annotations

import re
from pathlib import Path


TARGET = Path("/root/autodl-tmp/text_to_sql_benchmarks/results/qwen35-4b-arcwise-plat-trustsql-full-final-thinking/financial_wrong_analysis.md")


TABLES = {
    "94": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 找到 `client`、`disp`、`account`、`district`，正确表其实都在。 |
| Round 2 | explore_schema | 查看 `client` | 已看到 `gender`、`birth_date`，可找最老女性。 |
| Round 3 | explore_schema | 查看 `account` | 已看到 `account_id`、`district_id`。 |
| Round 4 | explore_schema | 查看 `card` | 与本题无关。 |
| Round 5 | explore_schema | 查看 `disp` | 已看到 `client_id -> account_id` 的关键桥表。 |
| Round 6 | explore_schema | 查看 `loan` | 与本题无关。 |
| Round 7 | explore_schema | 查看 `trans` | 与平均工资差无关。 |
| Round 8 | explore_schema | 查 `trans.operation` | 继续偏离；平均工资在 `district.A11`。 |
| Round 9 | explore_schema | 查 `order` 表字段 | 因 `order` 是保留字报语法错。 |
| Round 10 | explore_schema | 查看 `order` 建表 SQL | 仍停在无关表探索；没有生成 `client -> disp -> account` 与 `MAX(A11)-MIN(A11)` 的 SQL。 |""",
    "95": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `client`、`disp`、`account`、`district`。 |
| Round 2 | explore_schema | 查看 `client` | 找到 `birth_date` 和 `district_id`。 |
| Round 3 | explore_schema | 查看 `district` | 找到 `A11` 平均工资。 |
| Round 4 | explore_schema | 查看 `account` | 找到 `account_id`，但没有 `client_id`。 |
| Round 5 | explore_schema | 查看 `account` 建表 SQL | 重复确认 account，仍未查 `disp`。 |
| Round 6 | explore_schema | 再查 `account` 建表 SQL | 重复探索。 |
| Round 7 | explore_schema | 第三次查 `account` 建表 SQL | 仍没解决 client-account 关系。 |
| Round 8 | explore_schema | 再看 `account` 字段 | 重复。 |
| Round 9 | explore_schema | 查看 `client` 样例 | 能看到生日，但不能直接得到 account。 |
| Round 10 | explore_schema | 继续查 `account` 建表 SQL | 最大轮数耗尽；根因是没有使用 `disp.client_id/account_id` 桥表。 |""",
    "98": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `loan` 与 `account`。 |
| Round 2 | explore_schema | 查看 `account` 建表 SQL | 已看到 `frequency`，weekly statement 在这里。 |
| Round 3 | explore_schema | 查看 `loan` 建表 SQL | 已看到 `date`、`amount`、`account_id`。 |
| Round 4 | explore_schema | 查看 `disp` | 本题不需要。 |
| Round 5 | explore_schema | 查询 `loan.status` | 开始把 “approved loan date” 误解为 status 映射。 |
| Round 6 | explore_schema | 重复查询 status | 仍未生成 SQL。 |
| Round 7 | explore_schema | 查询 `account.frequency` | 已确认 `POPLATEK TYDNE`，足够生成。 |
| Round 8 | explore_schema | 统计 loan status 分布 | 继续纠结 approved/status。 |
| Round 9 | explore_schema | 再查 status 取值 | 没有新增信息。 |
| Round 10 | explore_schema | 查 status='A' | 最大轮数耗尽；gold 根本不需要 status，只需 `loan.date` 的 1997 和 weekly frequency。 |""",
    "99": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `account` 与 `loan`。 |
| Round 2 | explore_schema | 查看 `account` 字段 | 找到 opening `date`。 |
| Round 3 | explore_schema | 查看 `loan` 字段 | 找到 `duration`、`amount`。 |
| Round 4 | explore_schema | 查看 `client` | 无关。 |
| Round 5 | explore_schema | 查看 account 样例 | 确认日期格式。 |
| Round 6 | explore_schema | 查看 loan 样例 | 确认 amount/duration 数据。 |
| Round 7 | propose_schema | 提出 account-loan 方案 | 过滤和排序方向正确。 |
| Round 8 | generate_sql | 筛 1993 开户、duration>12，按 amount desc 取 1 | 定位 account `10451` 正确，但额外输出 `date, amount, duration`。 |
| Round 9 | confirm_answer | 确认四列输出版本 | gold 只要 `account_id`。 |""",
    "100": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `client` 与 `district`。 |
| Round 2 | explore_schema | 查看 `client` | 找到 `gender`、`birth_date`、`district_id`。 |
| Round 3 | explore_schema | 查看 `district` | 找到 district name `A2`。 |
| Round 4 | explore_schema | 查看 `account` | 题目说 account opened，但 gold 实际不需要 account 表。 |
| Round 5 | explore_schema | 查看 account 建表 SQL | 引入了会导致重复的 account 维度。 |
| Round 6 | explore_schema | 查 `district.A2='Sokolov'` | 找到 Sokolov district。 |
| Round 7 | generate_sql | 将 client、account、district 按 `district_id` 全部 join 后 count | 同一 district 的 8 个客户被 38 个 account 放大成 304。 |
| Round 8 | confirm_answer | 确认放大后的 count | gold 是 district-client 口径，只数符合条件 client，结果 8。 |""",
    "115": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `district` 和 `client`。 |
| Round 2 | explore_schema | 查看 client/disp/district/account 结构 | 已知道 `district.A3` 是区域、`A4` 是人口、client 有 gender。 |
| Round 3 | explore_schema | 查询 `district.A3` 取值 | 确认 south Bohemia。 |
| Round 4 | explore_schema | 列出 south Bohemia 的 `A4` | 看到了 `177686`、`93931` 等人口值。 |
| Round 5 | explore_schema | 按 `A4 DESC` 取最大 | 因 `A4` 是 TEXT，字符串排序错选 `93931`。 |
| Round 6 | explore_schema | 取该错误 district_id=16 | 锁定了错误分支。 |
| Round 7 | generate_sql | 对 district 16 计算男性比例并 round | 得到 44.26。 |
| Round 8 | confirm_answer | 确认字符串排序版本 | gold 应 `CAST(A4 AS INTEGER)` 选人口 177686 的 district，比例 40.0。 |""",
    "116": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `loan`、`account`、`trans`。 |
| Round 2 | explore_schema | 查看 `client` | 不关键，贷款已能定位 account。 |
| Round 3 | explore_schema | 查看 `loan` | 找到 `date`、`account_id`。 |
| Round 4 | explore_schema | 查看 `account` | 找到 account 连接。 |
| Round 5 | explore_schema | 查看 `trans` | 找到 `balance` 和 `date`。 |
| Round 6 | explore_schema | 查 `loan` 样例/目标日期 | 已能定位 1993-07-05 的贷款 account。 |
| Round 7 | explore_schema | 继续查看 loan 样例 | 重复定位，没有转去 trans 两个日期。 |
| Round 8 | explore_schema | 查询 loan status | 无关。 |
| Round 9 | explore_schema | 再查目标 loan 样例 | 仍停留在 loan。 |
| Round 10 | explore_schema | 继续查 loan | 没有生成 `(balance_1998 - balance_1993)/balance_1993*100`，最终 empty SQL。 |""",
    "117": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 只需要 `loan`。 |
| Round 2 | explore_schema | 查看 `loan` 字段 | 找到 `status` 和 `amount`。 |
| Round 3 | explore_schema | 查看 `account` | 不需要。 |
| Round 4 | generate_sql | 计算 status='A' 的 amount 占总 amount 百分比 | 公式正确，但用了 `ROUND(...,2)`，返回 18.02。 |
| Round 5 | confirm_answer | 确认四舍五入版本 | gold 是完整浮点 18.01559415907576。 |""",
    "118": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 只需要 `loan`。 |
| Round 2 | explore_schema | 查看 `account` | 不关键。 |
| Round 3 | explore_schema | 查看 `loan` | 找到 `amount`、`status`。 |
| Round 4 | explore_schema | 查询 status 取值 | 看到 A/B/C/D。 |
| Round 5 | explore_schema | 再查 status 取值 | 重复。 |
| Round 6 | explore_schema | 统计 amount<100000 的贷款总数和金额 | 得到分母相关信息。 |
| Round 7 | explore_schema | 按 status 统计 amount<100000 | 确认 status C 数量。 |
| Round 8 | generate_sql | 写百分比 SQL，但 FROM loan 导致同一个标量结果重复多行，且 round 到 46.89 | 第一次生成形态不干净。 |
| Round 9 | generate_sql | 去掉外层重复，返回一行 46.89 | 公式口径正确，但仍四舍五入。 |
| Round 10 | confirm_answer | 确认 round 版本 | gold 是完整浮点 46.885245901639344。 |""",
    "125": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `loan -> account -> district`。 |
| Round 2 | explore_schema | 查看 `loan` | 找到 status。 |
| Round 3 | explore_schema | 查看 `district` | 找到 `A12`、`A13` 失业率字段。 |
| Round 4 | explore_schema | 查看 `client` | 不需要。 |
| Round 5 | explore_schema | 查看 `account` | 找到 district 连接。 |
| Round 6 | propose_schema | 提出 loan-account-district | 表关系正确。 |
| Round 7 | confirm_answer | 直接确认按 district group by 的 SQL | gold 要每个符合条件 loan 行的 district increment，允许同 district 重复；pred 按 district 去重成 30 行，还多输出 district_id 并 round。 |""",
    "136": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `loan` 与 `account`。 |
| Round 2 | explore_schema | 查看 `loan` 建表 SQL | 找到 `date`、`amount`、`account_id`。 |
| Round 3 | explore_schema | 查看 `account` 建表 SQL | 找到 `frequency`。 |
| Round 4 | explore_schema | 查询 loan status | 开始把 approved 误解成 status。 |
| Round 5 | explore_schema | 再查 status | 重复。 |
| Round 6 | explore_schema | 查询 account frequency | 已看到 monthly=`POPLATEK MESICNE`。 |
| Round 7 | explore_schema | 查看 status='A' 的 loan 样例 | 继续纠结 approved status。 |
| Round 8 | explore_schema | 按 status 计数 | 无法推进最终查询。 |
| Round 9 | explore_schema | 再查 status 取值 | 重复。 |
| Round 10 | explore_schema | 再查 status 取值 | 最大轮数耗尽；gold 只需 loan date 范围、amount>=250000、monthly frequency。 |""",
    "137": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `account` 与 `loan`。 |
| Round 2 | explore_schema | 查看 `account` | 找到 `district_id`。 |
| Round 3 | explore_schema | 查看 `district` | branch location 可对应 district_id。 |
| Round 4 | explore_schema | 查看 `client` | 不需要。 |
| Round 5 | explore_schema | 查看 `loan` | 找到 status 和 account_id。 |
| Round 6 | explore_schema | 查看 district 样例 | 确认 district_id=1 存在。 |
| Round 7 | explore_schema | 查询 account frequency | 无关。 |
| Round 8 | explore_schema | 查看 `disp` | 不需要。 |
| Round 9 | explore_schema | 查看 district_id=1 样例 | 已能确定 branch location 1。 |
| Round 10 | explore_schema | 查询 loan status 取值 | 已知道 running 是 C/D，但没有生成 count SQL，最终 empty SQL。 |""",
    "129": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `trans -> account -> district`。 |
| Round 2 | explore_schema | 查看 `trans` | 找到 `type`、`operation`、`amount`。 |
| Round 3 | explore_schema | 查看 `district` | 找到 district name `A2`。 |
| Round 4 | explore_schema | 查看 `trans` 建表 SQL | 字段确认。 |
| Round 5 | explore_schema | 查看 `account` 建表 SQL | 找到 district 连接。 |
| Round 6 | propose_schema | 提出三表 join | 表关系正确，但没有明确 top10 是交易粒度。 |
| Round 7 | generate_sql | 按 district 分组，`SUM(t.amount)` 排 top 10 | 变成 district 总提现额排行，还多输出 total_amount。 |
| Round 8 | confirm_answer | 确认 district 汇总版本 | gold 是 1996-01 top 10 笔非信用卡取款交易对应的 district name，不能 group by district。 |""",
    "145": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `trans` 和 `disp`。 |
| Round 2 | explore_schema | 查看 `trans` | 找到 credit card withdrawal 操作和 amount/date。 |
| Round 3 | explore_schema | 查看 `client` | 找到 client_id，但不是正确连接入口。 |
| Round 4 | explore_schema | 查看 `account` | 找到 account_id/district_id。 |
| Round 5 | explore_schema | 查看 client 样例 | 继续沿 client district 方向。 |
| Round 6 | explore_schema | 查询 `trans.operation` | 确认 `VYBER KARTOU`。 |
| Round 7 | explore_schema | 查看 trans 样例 | 字段足够。 |
| Round 8 | explore_schema | 计算 1998 年信用卡交易平均金额 | 错把 overall average 限定为 credit card average；gold 是所有 1998 trans 的平均。 |
| Round 9 | propose_schema | 提出 trans/account/client | 漏掉关键桥表 `disp(type='OWNER')`。 |
| Round 10 | generate_sql | 用 `account.district_id = client.district_id` 找 client_id | 产生海量重复和错误客户；gold 应 `trans.account_id -> disp.account_id` 且 `disp.type='OWNER'`，并 DISTINCT。 |""",
    "149": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 正确表应是 `district`、`account`、`disp`。 |
| Round 2 | explore_schema | 查看 `account` | 找到 district_id，但没有账户资格类型。 |
| Round 3 | explore_schema | 查看 `district` | 找到 `A11` 平均收入。 |
| Round 4 | explore_schema | 查看 `client` | 不需要。 |
| Round 5 | explore_schema | 查看 `loan` | 题目“not eligible for loans”不是 loan 表过滤。 |
| Round 6 | explore_schema | 再看 account 字段 | 仍找不到 type。 |
| Round 7 | explore_schema | 再看 client 字段 | 无关。 |
| Round 8 | explore_schema | 再看 loan 字段 | 继续偏离。 |
| Round 9 | explore_schema | 再看 district 字段 | 收入字段已确认。 |
| Round 10 | explore_schema | 查看 `card.type` | 错把 card type 当账户资格类型；没有检查 `disp.type`，最终 empty SQL。 |""",
    "152": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `district` 和 `account`。 |
| Round 2 | explore_schema | 查看 `district` 建表 SQL | 找到 `A15` 1995 crime count。 |
| Round 3 | explore_schema | 查看 `account` 建表 SQL | 找到 opening `date` 和 district_id。 |
| Round 4 | propose_schema | 提出 district-account 方案 | 方向正确，但要注意 district 去重。 |
| Round 5 | generate_sql | 按 district_id group by 后输出每区 AVG(A15) | 产生 26 行，不是最终一行平均。 |
| Round 6 | generate_sql | 去掉 group by，直接 join 后 AVG(A15) | district 被 account 行重复加权，得到 29670.45。 |
| Round 7 | confirm_answer | 确认重复加权版本 | gold 先取 distinct district，再对 district.A15 求平均，结果 9675.038。 |""",
    "169": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `loan -> account -> disp -> client`。 |
| Round 2 | explore_schema | 查看 `client` | 找到 gender。 |
| Round 3 | explore_schema | 查看 `loan` | 找到 amount/date/account_id。 |
| Round 4 | explore_schema | 查看 `account` | 找到 account_id。 |
| Round 5 | explore_schema | 重复查看 account | 无新增。 |
| Round 6 | explore_schema | 查看 `district` | 不需要。 |
| Round 7 | explore_schema | 查看 `disp` | 找到 client-account 桥表和 OWNER type。 |
| Round 8 | explore_schema | 一次提交多条 SQL | 工具拒绝：一次只能执行一条语句。 |
| Round 9 | explore_schema | 查看 1996 loan 日期样例 | 只确认年份数据。 |
| Round 10 | explore_schema | 查看 1997 loan 日期样例 | 没有生成按 male owner 聚合 1996/1997 loan amount 的增长率 SQL，最终 empty SQL。 |""",
    "173": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `account` 和保留字表 `"order"`。 |
| Round 2 | explore_schema | 查看 `account` | 找到 `frequency`。 |
| Round 3 | explore_schema | 查看 `card` | 无关。 |
| Round 4 | explore_schema | 查看 `client` | 无关。 |
| Round 5 | explore_schema | 查看 `disp` | 不关键。 |
| Round 6 | explore_schema | 查看 `trans` | 被“debiting”带向交易流水。 |
| Round 7 | explore_schema | 查看 account 3 样例 | 已可得到 frequency。 |
| Round 8 | propose_schema | 提出 account + trans | 错过 `"order"` 表中常设扣款目的 `k_symbol`。 |
| Round 9 | generate_sql | 查询 account 3 的 frequency | 得到 `POPLATEK MESICNE`，只答了第一问。 |
| Round 10 | generate_sql | 错把 3539 当成 account_id，查询 `trans WHERE account_id=3539` | gold 要 account 3 在 `"order"` 中按 `k_symbol` 汇总 amount=3539 的目的 `POJISTNE`。 |""",
    "186": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `client -> disp -> account`。 |
| Round 2 | explore_schema | 查看 `client` | 找到 gender。 |
| Round 3 | explore_schema | 查 `order` 字段未转义 | 因保留字报错。 |
| Round 4 | explore_schema | 正确查看 `"order"` | 但 order 与 statement frequency 无关。 |
| Round 5 | explore_schema | 查看 `disp` | 找到 client-account 桥表。 |
| Round 6 | explore_schema | 查询 `disp.type` | 只有 OWNER/DISPONENT。 |
| Round 7 | explore_schema | 查看 disp 建表 SQL | 重复确认。 |
| Round 8 | explore_schema | 在 `disp.type` 中找 `TYDNE` | 返回空；weekly 不在 disp。 |
| Round 9 | explore_schema | 再查 `disp.type` | 仍只有 OWNER/DISPONENT。 |
| Round 10 | explore_schema | 继续查看 disp | 没有转到 `account.frequency='POPLATEK TYDNE'`，最终 empty SQL。 |""",
    "189": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `client`、`district`、`disp`、`account`。 |
| Round 2 | explore_schema | 查看 `client` | 找到 gender 和 birth_date。 |
| Round 3 | explore_schema | 查看 `district` | 找到 `A11`。 |
| Round 4 | explore_schema | 查看 `account` | 找到 account_id，但没有 client_id。 |
| Round 5 | explore_schema | 再看 account | 重复。 |
| Round 6 | explore_schema | 查看 account 建表 SQL | 仍未发现 client-account 需要 disp。 |
| Round 7 | explore_schema | 查看 district 样例 | A11 信息足够。 |
| Round 8 | explore_schema | 再查 account 建表 SQL | 重复。 |
| Round 9 | explore_schema | 查询最老女性 client 列表 | 已找到 client_id=2115 等候选。 |
| Round 10 | explore_schema | 查看 `card` 字段 | 错过 `disp` 桥表，无法把 client 2115 映射到账户 1743，最终 empty SQL。 |""",
    "192": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `loan` 与 `account`。 |
| Round 2 | explore_schema | 查看 `loan` | 找到 status 和 amount。 |
| Round 3 | explore_schema | 查看 `trans` | 错把 statement issuance 当 transaction operation。 |
| Round 4 | explore_schema | 查看 trans 建表 SQL | 继续在错误表。 |
| Round 5 | explore_schema | 查看 loan 建表 SQL | loan 字段足够。 |
| Round 6 | explore_schema | 查 trans operation 取值 | 没有 `POPLATEK PO OBRATU`。 |
| Round 7 | explore_schema | 再查 operation | 仍没有。 |
| Round 8 | explore_schema | 查 operation='POPLATEK PO OBRATU' | 返回空；这是字段位置错的信号。 |
| Round 9 | explore_schema | 查 loan status | 看到 C/D。 |
| Round 10 | explore_schema | 再在 trans.operation 中搜 OBRATU | 仍为空；没有转到 `account.frequency`，最终 empty SQL。 |""",
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
