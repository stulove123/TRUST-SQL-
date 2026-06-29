#!/usr/bin/env python3
"""Apply hand-written, root-cause-oriented trajectory tables for debit_card_specializing."""

from __future__ import annotations

import re
from pathlib import Path


TARGET = Path("/root/autodl-tmp/text_to_sql_benchmarks/results/qwen35-4b-arcwise-plat-trustsql-full-final-thinking/debit_card_specializing_wrong_analysis.md")


TABLES = {
    "1472": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 找到 `customers`、`yearmonth`、`gasstations` 等。 |
| Round 2 | explore_schema | 查看 `transactions_1k` | 与本题年/月总消费不是主表，开始有些偏。 |
| Round 3 | explore_schema | 查看 `gasstations` | 被 `Segment` 字段吸引，但这里的 segment 是加油站档次，不是客户 LAM。 |
| Round 4 | explore_schema | 查看 `yearmonth` | 已看到正确消费表：`CustomerID, Date, Consumption`。 |
| Round 5 | explore_schema | 在 `gasstations.Segment='LAM'` 中查询 | 返回空；这是关键误判，LAM 应该是 `customers.Segment`。 |
| Round 6 | explore_schema | 查 `gasstations.Segment` 取值 | 发现只有 Premium/Other 等，仍未转回 `customers`。 |
| Round 7 | explore_schema | 查 `gasstations.ChainID` | 进一步沿错误表探索。 |
| Round 8 | explore_schema | 查看 `yearmonth` 样例 | 能看到 `2012xx` 和 consumption，但还缺客户 segment join。 |
| Round 9 | explore_schema | 查 `gasstations.ChainID=13` | 与 LAM 客户无关。 |
| Round 10 | explore_schema | 继续查 gas station chain | 最大轮数耗尽，没有生成 SQL；根因是把客户段 `LAM` 错当成加油站属性。 |""",
    "1473": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 相关表是 `customers` 与 `yearmonth`。 |
| Round 2 | explore_schema | 查看 `customers` 字段 | 找到 `Segment`。 |
| Round 3 | explore_schema | 查看 `transactions_1k` | 本题不需要交易明细。 |
| Round 4 | explore_schema | 查看 `yearmonth` 字段 | 找到 `Date` 与 `Consumption`。 |
| Round 5 | explore_schema | 查询客户 segment 取值 | 确认存在 `SME`。 |
| Round 6 | propose_schema | 提出 `customers` join `yearmonth` | 表和过滤方向正确。 |
| Round 7 | generate_sql | 试图直接写 `AVG(SUM(Consumption))/12` | SQLite 报 aggregate misuse，说明需要先按客户聚合。 |
| Round 8 | generate_sql | 改成子查询按客户求年消费后 `AVG(customer_total)` | 年消费均值算对，但漏掉 `/12`，得到 44191.73。 |
| Round 9 | confirm_answer | 确认漏 `/12` 的 SQL | gold 是月均：`44191.73222815839 / 12 = 3682.6443523465327`。 |""",
    "1476": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `customers` 和 `yearmonth`。 |
| Round 2 | explore_schema | 查看 `customers` 字段 | 已看到 `Currency`，可区分 CZK/EUR。 |
| Round 3 | explore_schema | 查看 `gasstations` | 与客户币种消费差无关。 |
| Round 4 | explore_schema | 查看 `transactions_1k` | 不是 gold 的消费口径。 |
| Round 5 | explore_schema | 查看 `yearmonth` 字段 | 已看到 `Date` 与 `Consumption`，正确事实表已找到。 |
| Round 6 | explore_schema | 查看 `products` | 无关探索。 |
| Round 7 | explore_schema | 查看 product 样例 | 继续无关。 |
| Round 8 | explore_schema | 查询 `customers.Currency` 取值 | 确认只有 `EUR`、`CZK`。 |
| Round 9 | explore_schema | 查看 `yearmonth` 样例 | 确认 `Date` 是 `YYYYMM`。 |
| Round 10 | generate_sql | 准备生成 CZK/EUR 条件聚合 SQL | 输出格式缺少完整 `<tool_call>`，解析器拿不到 SQL；这是协议/收敛失败，不是 schema 不足。 |""",
    "1479": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 应使用 `customers.Currency` 和 `yearmonth.Consumption`。 |
| Round 2 | explore_schema | 查看 `yearmonth` 建表 SQL | 找到 `Date`、`Consumption`。 |
| Round 3 | explore_schema | 查看 `transactions_1k` | 与 gold 口径无关。 |
| Round 4 | explore_schema | 查看 `products` | 无关。 |
| Round 5 | explore_schema | 查看 product 样例 | 继续无关探索。 |
| Round 6 | explore_schema | 查看 `yearmonth` 样例 | 确认按 `SUBSTR(Date,1,4)` 可取年份。 |
| Round 7 | generate_sql | 只在 `yearmonth` 按年求总消费并输出 `Year, TotalConsumption` | 漏了 `customers.Currency='CZK'`；年份碰巧仍是 2013，但多输出了消费总额。 |
| Round 8 | confirm_answer | 确认两列输出版本 | EX 直接失败在列数：gold 只要年份一列。 |""",
    "1480": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 相关表是 `customers` 与 `yearmonth`。 |
| Round 2 | explore_schema | 查看 `customers` | 找到 `Segment`。 |
| Round 3 | explore_schema | 查看 `yearmonth` | 找到 `Date`、`Consumption`。 |
| Round 4 | explore_schema | 再看 `yearmonth` 字段 | 字段已足够。 |
| Round 5 | explore_schema | 查询 segment 取值 | 确认 `SME`。 |
| Round 6 | explore_schema | 查询 `yearmonth.Date` 取值 | 确认月份编码是 `YYYYMM`。 |
| Round 7 | propose_schema | 提出候选 schema | 方向正确，但没有明确“按月份聚合所有 SME 客户”。 |
| Round 8 | generate_sql | 按单条 `ym.Consumption DESC LIMIT 1` 找最大记录 | 找到 `201304` 的某个客户记录；月份碰巧对，但语义是单条最大，不是月总和最大，且多输出 3 列。 |
| Round 9 | confirm_answer | 确认单条记录最大版本 | gold 要 `GROUP BY SUBSTR(Date,5,2)` 后只返回月份 `04`。 |""",
    "1481": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `customers` 与 `yearmonth`，题目本身是多层聚合。 |
| Round 2 | explore_schema | 查看 `customers` 建表 SQL | 找到 `Segment`、`Currency`。 |
| Round 3 | explore_schema | 查看 `transactions_1k` | 与 annual consumption 主口径无关。 |
| Round 4 | explore_schema | 查看 `yearmonth` 建表 SQL | 找到 `Consumption` 与 `Date`。 |
| Round 5 | explore_schema | 查看 `yearmonth` 字段 | 确认字段。 |
| Round 6 | explore_schema | 查询 segment 取值 | 确认 SME/LAM/KAM。 |
| Round 7 | explore_schema | 查询 `yearmonth.Date` 样例 | 确认 `YYYYMM`。 |
| Round 8 | explore_schema | 统计 2013 年 yearmonth 行数 | 只是规模检查，没有推进核心 CTE 逻辑。 |
| Round 9 | propose_schema | 提出 schema | 已经很晚才进入 propose。 |
| Round 10 | generate_sql | 试图生成最低客户与差值 SQL | 输出格式缺少完整 `<tool_call>`，没有 SQL 被执行；复杂逻辑未在 10 轮内落地。 |""",
    "1482": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `customers`、`yearmonth`。 |
| Round 2 | explore_schema | 查看 `yearmonth` 建表 SQL | 找到 `Date`、`Consumption`。 |
| Round 3 | explore_schema | 查看 `customers` 建表 SQL | 找到 `Segment`、`Currency`。 |
| Round 4 | explore_schema | 查看 `yearmonth` 字段 | 字段确认。 |
| Round 5 | explore_schema | 查看 `customers` 字段 | 字段确认。 |
| Round 6 | explore_schema | 查询 SME/LAM/KAM 是否存在 | 三个 segment 均存在。 |
| Round 7 | explore_schema | 用 `LEFT(Date,4)` 查年份 | SQLite 不支持 `LEFT`，报错。 |
| Round 8 | explore_schema | 改用 `SUBSTR(Date,1,4)` | 确认有 2012 和 2013。 |
| Round 9 | propose_schema | 提出按 segment/year 聚合 | 方向大致正确，但仍未强调 `Currency='EUR'` 和单行三列输出。 |
| Round 10 | generate_sql | 生成 CTE/WITH 版本 | 工具拒绝 `WITH` 开头；保存的最终 SQL 还漏 `Currency='EUR'`、外层引用未投影的 `Year`，且输出多行多列，不符合 gold。 |""",
    "1486": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 本题其实只需要 `customers`。 |
| Round 2 | explore_schema | 查看 `customers` 字段 | `Segment` 和 `Currency` 已足够。 |
| Round 3 | explore_schema | 查看 `transactions_1k` | 引入了不必要的交易金额表。 |
| Round 4 | explore_schema | 查询 segment 取值 | 确认 `SME`。 |
| Round 5 | explore_schema | 查看 `customers` 建表 SQL | 再次确认字段。 |
| Round 6 | generate_sql | join `transactions_1k`，计算 CZK/EUR 的交易 `Amount` 差 | 把“SMEs pay in CZK than in euros”理解成交易数量/金额差，得到 3843。 |
| Round 7 | confirm_answer | 确认交易口径 SQL | gold 是 SME 客户币种数量差：`COUNT(CZK)-COUNT(EUR)=23505`，不需要交易表。 |""",
    "1490": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `customers` 与 `yearmonth`。 |
| Round 2 | explore_schema | 查看 `customers` 字段 | 找到 `Segment`。 |
| Round 3 | explore_schema | 查看 `transactions_1k` | 一度偏向交易表。 |
| Round 4 | explore_schema | 查询 segment 取值 | 确认 `LAM`。 |
| Round 5 | explore_schema | 查看 `yearmonth` 字段 | 找到 `Consumption`，这是正确字段。 |
| Round 6 | explore_schema | 统计 `yearmonth` 行数 | 只是规模检查。 |
| Round 7 | explore_schema | 查看 `yearmonth.CustomerID` 样例 | 确认可 join 客户。 |
| Round 8 | explore_schema | 统计 LAM distinct customers | 得到分母 3658。 |
| Round 9 | explore_schema | 查看较大的 `Consumption` 值 | 确认阈值比较字段可用。 |
| Round 10 | propose_schema | 提出 `customers` + `yearmonth` 方案 | 已经接近正确 SQL，但未进入 generate/confirm，最终 empty SQL。 |""",
    "1498": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 只需要 `yearmonth`。 |
| Round 2 | explore_schema | 查看 `yearmonth` 建表 SQL | 找到 `Date` 和 `Consumption`。 |
| Round 3 | explore_schema | 查看 `transactions_1k` | 与 monthly aggregate 无关。 |
| Round 4 | explore_schema | 查看 `yearmonth` 字段 | 字段已充分。 |
| Round 5 | explore_schema | 查看 `customers` | 无关。 |
| Round 6 | explore_schema | 查看 `yearmonth` 样例 | 看到每行是 customer-month 记录，不是全月总和。 |
| Round 7 | generate_sql | 直接 `MAX(Consumption)` 过滤 2012 | 得到单个客户月记录最大值 445279.69。 |
| Round 8 | generate_sql | 重复 `MAX(Consumption)` | 没有改为按月份 `SUM`。 |
| Round 9 | generate_sql | 列出 2012 最大的单条记录 | 继续验证了错误粒度。 |
| Round 10 | confirm_answer | 确认单条最大值 SQL | gold 是按 `SUBSTR(Date,5,2)` 分组后取最高月总和 51787161.74。 |""",
    "1505": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 应使用 `customers` 和 `yearmonth`。 |
| Round 2 | explore_schema | 查看 `customers` 字段 | 找到 `Currency`。 |
| Round 3 | explore_schema | 查看 `transactions_1k` 字段 | 偏向交易明细。 |
| Round 4 | explore_schema | 查看 customers 样例 | 确认 EUR/CZK。 |
| Round 5 | explore_schema | 查 `transactions_1k` 的年月 | 发现样本只有 2012-08，这与题目“at least one month consumption”不匹配。 |
| Round 6 | propose_schema | 提出 customers + transactions 方案 | 用错事实表，没采用 `yearmonth.Consumption`。 |
| Round 7 | generate_sql | 按客户交易 `SUM(t.Amount)>1000` 计数 | 返回空；因为 `Amount` 不是月消费。 |
| Round 8 | generate_sql | 改成按交易月份分组后 `SUM(t.Amount)>1000` | 仍为空，继续沿错误表。 |
| Round 9 | generate_sql | 调试交易聚合明细 | 仍没有回到 `yearmonth`。 |
| Round 10 | generate_sql | 退成返回 EUR 交易明细 Top 20 | 最终输出 20 行 3 列；gold 要 `COUNT(DISTINCT CustomerID)=391`。 |""",
    "1524": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `transactions_1k` 与 `customers`。 |
| Round 2 | explore_schema | 查看 `customers` 建表 SQL | 找到 `Segment`。 |
| Round 3 | explore_schema | 查看 `transactions_1k` 建表 SQL | 已看到 `Amount` 和 `Price` 两个数值字段。 |
| Round 4 | propose_schema | 提出 join customers/transactions | 表关系正确。 |
| Round 5 | generate_sql | 用 `SUM(t.Amount)=548.4` 查 | 返回空；把单笔 price 误当 amount 聚合。 |
| Round 6 | generate_sql | 查看当天按 Amount 排序的客户 | 仍在 Amount 方向探索。 |
| Round 7 | generate_sql | 查看交易样例 | 样例中其实能看到 `Price` 是小数。 |
| Round 8 | generate_sql | 改成 `t.Amount=54840` | 错把 548.4 缩放成整数 amount，返回空。 |
| Round 9 | generate_sql | 重复 `Amount=54840` | 没有尝试 `Price=548.4`。 |
| Round 10 | generate_sql | 再次重复错误 amount 查询 | 最终空结果；gold 用 `Price=548.4` 可得到 `KAM`。 |""",
    "1525": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `transactions_1k` 与 `customers`。 |
| Round 2 | explore_schema | 查看 `customers` 字段 | 找到 `Currency`。 |
| Round 3 | explore_schema | 查看 `transactions_1k` 字段 | 找到 `Date`、`CustomerID`。 |
| Round 4 | explore_schema | 查看 `transactions_1k` 建表 SQL | join 路径确认。 |
| Round 5 | explore_schema | 查看 `customers` 建表 SQL | 字段确认。 |
| Round 6 | propose_schema | 提出按当天交易客户算 EUR 占比 | 语义方向正确，但 numerator/denominator 需要分开。 |
| Round 7 | generate_sql | 在 `WHERE` 中先过滤 `Currency='EUR'` 再算比例 | 分母被缩成 EUR 子集，所以结果变成 100.0。 |
| Round 8 | confirm_answer | 确认错误分母 SQL | gold 分母是当天全部 distinct customers，分子才是 EUR customers。 |""",
    "1526": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要先从 `transactions_1k` 找客户，再到 `yearmonth` 算年消费。 |
| Round 2 | explore_schema | 查看 `customers` 字段 | 可用于客户信息，但本题客户由交易定位。 |
| Round 3 | explore_schema | 查看 `transactions_1k` 字段 | 已看到 `Amount` 与 `Price`。 |
| Round 4 | explore_schema | 查看 `yearmonth` 字段 | 找到 `Date`、`Consumption`。 |
| Round 5 | explore_schema | 用 `Amount=634.8` 查当天交易 | 返回空；字段误用。 |
| Round 6 | explore_schema | 查看当天 `Amount` 取值 | 发现 Amount 是整数。 |
| Round 7 | explore_schema | 查看 8 月 `Amount` 取值 | 继续确认 634.8 不在 Amount。 |
| Round 8 | explore_schema | 查看 2012-08-25 交易样例 | 样例里有大量小数 `Price`。 |
| Round 9 | explore_schema | 改用 `Price=634.8` 查询 | 找到正确 CustomerID=6718。 |
| Round 10 | explore_schema | 查看该客户 `yearmonth` 记录 | 已具备计算 decrease rate 的数据，但最大轮数耗尽，没有生成最终 SQL。 |""",
    "1528": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 相关表是 `gasstations`。 |
| Round 2 | explore_schema | 查看 `customers` | 无关。 |
| Round 3 | explore_schema | 查看 `gasstations` 字段 | 找到 `Country`、`Segment`。 |
| Round 4 | explore_schema | 查看 `yearmonth` | 无关。 |
| Round 5 | explore_schema | 查看 `gasstations` 建表 SQL | 字段确认。 |
| Round 6 | explore_schema | 查看 `gasstations` 样例 | 确认国家与 segment 数据。 |
| Round 7 | explore_schema | 查询 `Country='SVK'` | 确认 SVK 存在。 |
| Round 8 | explore_schema | 统计 SVK 加油站总数 | 得到分母 880。 |
| Round 9 | generate_sql | 计算 Premium 占比 | 百分比 35.681818... 已正确，但输出包含中间列。 |
| Round 10 | generate_sql | 最终输出 `premium_count,total_count,premium_percentage` | 计算值正确，EX 失败在列数；gold 只要 percentage 一列。 |""",
    "1529": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `transactions_1k`。 |
| Round 2 | explore_schema | 查看 `customers` | 不关键。 |
| Round 3 | explore_schema | 查看 `transactions_1k` 建表 SQL | 已看到 `Amount` 与 `Price`。 |
| Round 4 | explore_schema | 查看 `gasstations` | 不需要 join，交易表已有 gas station 交易记录。 |
| Round 5 | propose_schema | 提出 transactions/gasstations 方案 | 多引入 gasstations，但不是主要问题。 |
| Round 6 | generate_sql | 对 customer 38508 求 `SUM(Amount)` 和交易数 | 得到 148，这是数量，不是花费。 |
| Round 7 | generate_sql | 只查 2012-08 的 `SUM(Amount)` | 仍然是 148，并且只回答第二问的一部分。 |
| Round 8 | confirm_answer | 确认只输出总 `SUM(Amount)` 的 SQL | gold 要两列 `SUM(Amount*Price)` 与 August 2012 spend；pred 漏乘 Price 且漏一列。 |""",
    "1531": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `transactions_1k` 与 `customers`。 |
| Round 2 | explore_schema | 查看 `customers` 字段 | 找到 `Currency`。 |
| Round 3 | explore_schema | 查看 `transactions_1k` 字段 | 已看到 `Amount` 与 `Price`。 |
| Round 4 | propose_schema | 先进入 propose 但未形成有效动作 | 阶段推进有些混乱。 |
| Round 5 | propose_schema | 提出 customers + transactions | 表正确，但没有明确 spending = `Amount*Price`。 |
| Round 6 | generate_sql | 按 `SUM(Amount)` 排 top customer，并算 `SUM(Price)/SUM(Amount)` | 选出 CustomerID=16358，错误；top spending 应按金额 `SUM(Amount*Price)`。 |
| Round 7 | generate_sql | 重复/微调同一错误公式 | 仍按购买数量排序，平均单价也不是加权平均。 |
| Round 8 | confirm_answer | 确认 5 列输出版本 | gold 要 `(CustomerID, SUM(Price*Amount)/SUM(Amount), Currency)`；pred 多列、错客户、错公式。 |""",
    "1533": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `transactions_1k` 与 `yearmonth`。 |
| Round 2 | explore_schema | 查看 `customers` | 不关键。 |
| Round 3 | explore_schema | 查看 `gasstations` | 不关键。 |
| Round 4 | explore_schema | 查看 `products` | 可确认 product id，但题目已给 No.5。 |
| Round 5 | explore_schema | 查看 `transactions_1k` 字段 | 找到 `ProductID`、`Price`、`Amount`、`CustomerID`。 |
| Round 6 | explore_schema | 查看 `yearmonth` 字段 | 找到 `Date`、`Consumption`。 |
| Round 7 | generate_sql | 生成 join SQL，但 `SELECT DISTINCT CustomerID, Consumption` | 过滤条件基本正确，但多输出 CustomerID，且 DISTINCT 去掉了重复 consumption。 |
| Round 8 | confirm_answer | 确认 DISTINCT 两列版本 | gold 只要 `Consumption` 并保留重复行；pred 少了一个重复 `126157.7`。 |""",
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
