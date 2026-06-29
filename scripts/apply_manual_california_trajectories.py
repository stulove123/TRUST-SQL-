#!/usr/bin/env python3
"""Apply hand-written, root-cause-oriented trajectory tables for california_schools."""

from __future__ import annotations

import re
from pathlib import Path


RESULT_DIR = Path("/root/autodl-tmp/text_to_sql_benchmarks/results/qwen35-4b-arcwise-plat-trustsql-full-final-thinking")
FILES = [
    RESULT_DIR / "california_schools_qid11_36_wrong_analysis.md",
    RESULT_DIR / "california_schools_qid37plus_wrong_analysis.md",
]


TABLES = {
    "11": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 找到 `schools` 和 `frpm`，方向正确。 |
| Round 2 | explore_schema | 查看 `schools` 字段 | 已看到 `CDSCode` 和 `School`，但没有意识到 `School` 可能为 NULL。 |
| Round 3 | explore_schema | 查看 `frpm` 字段 | 找到两类 enrollment 字段，可计算 total enrollment。 |
| Round 4 | propose_schema | 提出 `schools` join `frpm` | join 和 enrollment 计算方向正确，但 schema proposal 没把“具体学校需 `School IS NOT NULL`”作为约束。 |
| Round 5 | generate_sql | 按两类 enrollment 之和 > 500 输出 `CDSCode` | 主计算正确，但混入 2 条 `School=NULL` 的 district-level 记录。 |
| Round 6 | confirm_answer | 确认缺少 `School IS NOT NULL` 的 SQL | 根因是 school-level 过滤缺失；pred 7806 行，gold 7804 行。 |""",
    "12": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 找到 `satscores`、`frpm`、`schools`。 |
| Round 2 | explore_schema | 查看 `satscores` 建表 SQL | 已看到 `NumGE1500`、`NumTstTakr` 和 `rtype`，可定义 SAT excellence rate。 |
| Round 3 | explore_schema | 查看 `schools` 建表 SQL | 对本题不是主要表，探索完整但不关键。 |
| Round 4 | explore_schema | 查看 `frpm` 建表 SQL | 已看到 `Free Meal Count (Ages 5-17)` 和 `Enrollment (Ages 5-17)`，字段名含括号空格，需要谨慎 quote。 |
| Round 5 | generate_sql | 生成 eligible-free-rate 排序 SQL | 字段 quote 写坏：`Enrollment (Ages 5-17` 少右括号/反引号，直接报错。 |
| Round 6 | generate_sql | 重复同一个坏 quote SQL | 没有根据报错做字段名级修复。 |
| Round 7 | generate_sql | 继续重复坏 SQL | 仍未修 quote，也没处理 `NumGE1500/NumTstTakr` 的整数除法。 |
| Round 8 | generate_sql | 继续重复坏 SQL | 报错信息已经足够明确，但没有触发自修复。 |
| Round 9 | generate_sql | 继续重复坏 SQL | 仍停在同一语法/字段错误。 |
| Round 10 | generate_sql | 最终仍提交坏 SQL | 根因有三层：quote 错、SAT rate 缺 CAST、缺 `rtype='S'` 等稳健过滤。 |""",
    "23": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 定位到 `schools` 和 `frpm`。 |
| Round 2 | explore_schema | 查看 `schools` 字段 | 已看到 `School`、`Street`、`City/Zip/State`，但题目只要学校名和街道。 |
| Round 3 | explore_schema | 查看 `frpm` 字段 | 找到 K-12 与 Ages 5-17 enrollment。 |
| Round 4 | propose_schema | 提出 join 与地址字段 | schema 方向对，但把完整地址拆成多列纳入输出，且没有 `School IS NOT NULL`。 |
| Round 5 | generate_sql | 按 enrollment 差值 > 30 输出学校和完整地址字段 | 差值条件正确；错误是多输出 City/Zip/State，并混入 3 条 `School=NULL` 记录。 |
| Round 6 | confirm_answer | 确认多列且缺非空过滤的 SQL | 根因是 projection + school-level 过滤同时错。 |""",
    "24": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `frpm` 与 `satscores`。 |
| Round 2 | explore_schema | 查看 `schools` 字段 | 提供学校名备选，但 gold 实际取 `frpm."School Name"`。 |
| Round 3 | explore_schema | 查看 `satscores` 字段 | 已看到 `NumGE1500` 和 `rtype`，后续却没有使用 `rtype='S'`。 |
| Round 4 | explore_schema | 查看 `frpm` 字段 | 已看到 free-meal percent 和 school name。 |
| Round 5 | propose_schema | 提出三表 join | 表方向可行，但没有固化 school-level SAT 过滤和最终只输出 school name。 |
| Round 6 | generate_sql | 误把“score >=1500”写成 `NumGE1500 >= 1500` | 返回空结果，说明 `NumGE1500` 是人数而不是分数阈值本身。 |
| Round 7 | generate_sql | 转去查看 free-meal percent 分布 | 发现 percent 有大量取值，但没有解决 `NumGE1500` 和 `rtype` 问题。 |
| Round 8 | generate_sql | 只按 percent 排序查看样例 | 暂时丢掉了 `NumGE1500 > 0` 的核心条件。 |
| Round 9 | generate_sql | 改成 `NumGE1500 >= 1` | 行集合接近，但缺 `rtype='S'`，混入 district-level SAT；还多输出 percent/NumGE1500。 |
| Round 10 | generate_sql | 重复 Round 9 版本 | 根因是少了 `rtype='S'`，学校名来源和输出列也不符合 gold。 |""",
    "25": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `schools` 和 `satscores`。 |
| Round 2 | explore_schema | 查看 `schools` 字段 | 找到 `District`、`FundingType`、`School`。 |
| Round 3 | explore_schema | 查看 `satscores` 字段 | 找到 `AvgScrMath` 和 `rtype`，但后续没用 `rtype='S'`。 |
| Round 4 | explore_schema | 查看 `frpm` 字段 | 本题不需要 FRPM，探索冗余。 |
| Round 5 | explore_schema | 查看 SAT district 名样例 | 确认 Riverside 相关 district 存在。 |
| Round 6 | propose_schema | 提出 `schools` join `satscores` | join 方向正确。 |
| Round 7 | generate_sql | 过滤 `District LIKE 'Riverside%'` 并按学校/FundingType 聚合 math | 逻辑基本对，但没有排除 `rtype='D'`，多出 Riverside County Office of Education 的 district-level 记录。 |
| Round 8 | confirm_answer | 确认缺 `rtype='S'` 的 SQL | 根因是 school-level SAT 过滤缺失。 |""",
    "27": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `schools` 的日期和 `satscores` 的写作分。 |
| Round 2 | explore_schema | 查看 `schools` 建表 SQL | 已看到 `OpenDate`、`ClosedDate`、`Phone`。 |
| Round 3 | explore_schema | 查看 `satscores` 建表 SQL | 已看到 `AvgScrWrite`。 |
| Round 4 | propose_schema | 提出日期字段与 join | 表和字段方向正确。 |
| Round 5 | generate_sql | 用 `OpenDate > '1991-01-01' OR ClosedDate < '2000-01-01'` | 把 1991 年内开办的学校也算作 after 1991；gold 是年份严格大于 1991。 |
| Round 6 | confirm_answer | 确认日期边界版本 | 根因是日期语义错，应比较 `strftime('%Y', OpenDate) > '1991'`。 |""",
    "31": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `frpm` 的 enrollment/free meal 字段。 |
| Round 2 | explore_schema | 查看 `schools` 字段 | 可用于 `School IS NOT NULL`，但后续没使用。 |
| Round 3 | explore_schema | 查看 `frpm` 字段 | 已看到 `Enrollment (K-12)` 和 `Free Meal Count (K-12)`。 |
| Round 4 | explore_schema | 查看 FRPM 样例 | 确认字段有数值，能计算 rate。 |
| Round 5 | propose_schema | 提出只用 `frpm` | 主表基本够用，但缺 school 非空和 answer shape 约束。 |
| Round 6 | generate_sql | 首次生成 top enrollment/rate SQL | 因带空格字段 quote 不当报错。 |
| Round 7 | generate_sql | 尝试修 quote | 仍有 quote 语法错误。 |
| Round 8 | generate_sql | 成功执行，返回 school/enrollment/free count/rounded rate | 关键错因暴露：`LIMIT 11 OFFSET 9` 返回 11 行；题目只要第 10、11 两行，且只要完整精度 rate 一列。 |
| Round 9 | confirm_answer | 确认 11 行 4 列且 round 后的 SQL | 根因是 top-k 范围、输出列和数值精度都错。 |""",
    "32": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `schools` 的 SOC 和 `frpm` 的 FRPM/enrollment。 |
| Round 2 | explore_schema | 查看 `schools` 字段 | 找到 `SOC`。 |
| Round 3 | explore_schema | 查看 `frpm` 字段 | 找到 `FRPM Count (K-12)` 与 `Enrollment (K-12)`。 |
| Round 4 | explore_schema | 验证 `SOC=66` 存在 | 过滤值没问题。 |
| Round 5 | generate_sql | 输出格式/工具调用解析失败 | 没有得到可执行 SQL。 |
| Round 6 | generate_sql | 生成 SOC=66 top FRPM rate SQL | 字段双引号未闭合，`FRPM Count` 处报语法错误。 |
| Round 7 | generate_sql | 重复同一坏 quote SQL | 没有根据报错修复字段名。 |
| Round 8 | generate_sql | 继续重复坏 quote SQL | 仍停在语法错误。 |
| Round 9 | generate_sql | 继续重复坏 quote SQL | 没有进入结果验证。 |
| Round 10 | generate_sql | 最终仍提交坏 SQL | 根因是 quote 自修复失败；即使修语法，还需只输出 rate 一列而不是学校名/中间列。 |""",
    "36": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `satscores` 排 `NumGE1500`，`schools` 输出管理员。 |
| Round 2 | explore_schema | 查看 `schools` 建表 SQL | 已看到多个管理员姓名字段。 |
| Round 3 | explore_schema | 查看 `satscores` 建表 SQL | 已看到 `NumGE1500` 和 `rtype`。 |
| Round 4 | explore_schema | 查看 `frpm` 建表 SQL | 与本题关系不大。 |
| Round 5 | propose_schema | 提出 `schools` + `satscores` | 忽略了 `rtype='S'` 和 gold 要 6 个管理员字段。 |
| Round 6 | generate_sql | 按 `NumGE1500 DESC LIMIT 1` 取管理员 | 选到 district-level 汇总记录 `Michelle King`，不是 school-level 最高学校。 |
| Round 7 | generate_sql | 尝试输出更多管理员字段 | 仍未加 `rtype='S'`，结果还是 district-level。 |
| Round 8 | generate_sql | 继续同一排序逻辑 | 仍选 `Michelle King`。 |
| Round 9 | generate_sql | 继续同一逻辑 | 没有检查 `School=NULL/rtype='D'` 的异常信号。 |
| Round 10 | generate_sql | 最终拼成一个 FullName | 根因是缺 `rtype='S'`，且输出形状从 6 个字段退化为 1 个拼接姓名。 |""",
    "37": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `satscores` 算 excellence rate，`schools` 给地址。 |
| Round 2 | explore_schema | 查看 `schools` 字段 | 找到地址字段。 |
| Round 3 | explore_schema | 查看 `frpm` 字段 | 与本题关系不大。 |
| Round 4 | explore_schema | 查看 `satscores` 字段 | 已看到 `NumGE1500`、`NumTstTakr`、`rtype`。 |
| Round 5 | explore_schema | 只统计 `NumTstTakr > 0` 的行数 | 没检查 `NumGE1500 IS NOT NULL` 和 `rtype='S'`。 |
| Round 6 | explore_schema | 预览最低 rate 排序结果 | 第一批结果已经出现 NULL rate/district-level 异常，但没有处理。 |
| Round 7 | generate_sql | `ORDER BY NumGE1500/NumTstTakr ASC LIMIT 1` | SQLite 把 NULL 排最前，选错一条；还没有返回 13 个最低并列学校。 |
| Round 8 | confirm_answer | 确认 NULL-first + LIMIT 1 版本 | 根因是 NULL 未过滤、`rtype='S'` 缺失、tie 未处理。 |""",
    "39": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `schools` 和 `satscores`。 |
| Round 2 | explore_schema | 查看 `schools` 字段 | 已看到 `City` 和 `County`，这里存在语义选择。 |
| Round 3 | explore_schema | 查看 `satscores` 字段 | 找到 `NumTstTakr`。 |
| Round 4 | explore_schema | 再看 `satscores` 建表 SQL | 字段确认充分。 |
| Round 5 | propose_schema | 选择 `City` 表达 Fresno schools | 这是关键偏差：gold 按 `County='Fresno'`。 |
| Round 6 | generate_sql | 用 `City='Fresno'` 且 1980 open date 算平均 test takers | 得到 `203.8`，只覆盖 Fresno city 的 10 条。 |
| Round 7 | confirm_answer | 确认 city 口径 | 根因是地名粒度错；Fresno schools 在 gold 中指 Fresno County，结果应 `137.888...`。 |""",
    "40": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `schools`、`satscores`。 |
| Round 2 | explore_schema | 查看 `schools` 字段 | 找到 `District`、`Phone`。 |
| Round 3 | explore_schema | 查看 `frpm` 字段 | 与本题无关。 |
| Round 4 | explore_schema | 查看 `satscores` 字段 | 找到 `AvgScrRead` 和 `rtype`。 |
| Round 5 | explore_schema | 验证 Fresno Unified 这个 district 存在 | 过滤值正确。 |
| Round 6 | propose_schema | 提出候选 schema | 没有把 `AvgScrRead IS NOT NULL` 和 `rtype='S'` 固化为排序前条件。 |
| Round 7 | generate_sql | 首次 join 写错字段别名 | 报 `no such column: s.cds`，随后修 join。 |
| Round 8 | generate_sql | 按 `AvgScrRead ASC LIMIT 1` 返回电话 | 因 NULL 升序在前，选到 `Sierra Charter` 的电话 `(559) 490-4290`。 |
| Round 9 | confirm_answer | 确认 NULL-first 版本 | 根因是未过滤 `AvgScrRead IS NOT NULL`；正确最低非空是 McLane High。 |""",
    "41": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `schools`、`satscores`。 |
| Round 2 | explore_schema | 查看 `schools` 字段 | 找到 `County`、`Virtual`、`School`。 |
| Round 3 | explore_schema | 查看 `frpm` 字段 | 与本题不关键。 |
| Round 4 | explore_schema | 查看 `satscores` 字段 | 找到 `AvgScrRead`。 |
| Round 5 | explore_schema | 统计 `Virtual='F'` 学校数 | 提前把注意力放到 virtual 子集。 |
| Round 6 | explore_schema | 查看 county 名 | 确认 county 分区可用。 |
| Round 7 | explore_schema | 查看 virtual 学校样例 | 进一步强化“先筛 virtual”的错误路径。 |
| Round 8 | generate_sql | 写 CTE/WITH，在 virtual 学校内部做 county rank | 工具拒绝 `WITH`，但语义已经是先筛 virtual 后排名。 |
| Round 9 | generate_sql | 再写 CTE/WITH 同一语义 | 仍被工具拒绝，没有修正过滤顺序。 |
| Round 10 | generate_sql | 改成子查询执行成功 | 返回 31 行；根因是应先在所有学校中按 county 排 top5，再筛 virtual，不能先筛 virtual。 |""",
    "46": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `schools` 和 `frpm`。 |
| Round 2 | explore_schema | 查看 `schools` 字段 | 找到 `DOC` 与 `School`。 |
| Round 3 | explore_schema | 查看 `frpm` 字段 | 找到 `Enrollment (K-12)`。 |
| Round 4 | explore_schema | 验证 `DOC=31` | State Special Schools 取值正确。 |
| Round 5 | propose_schema | 提出 join | 方向正确，但没有约束只返回最高 1 所和单列 school。 |
| Round 6 | generate_sql | 按 enrollment 降序列出 DOC=31 学校 | 排序正确，但返回 3 行 3 列。 |
| Round 7 | confirm_answer | 确认缺 `LIMIT 1` 且多列的 SQL | 根因是 answer shape/top-1 没收敛；gold 只要最高 enrollment 学校名。 |""",
    "48": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 只需要 `schools`。 |
| Round 2 | explore_schema | 查看 `schools` 建表 SQL | 已看到 `County`、`DOC`、`StatusType`。 |
| Round 3 | explore_schema | 用 `County='Orange County'` 查 DOC | 返回空，说明 county 存储值可能不是带 County 后缀。 |
| Round 4 | explore_schema | 查看 DOC 取值 | 确认 `52`、`54` 存在。 |
| Round 5 | explore_schema | 查看 `StatusType` 取值 | 确认 `Merged` 存在。 |
| Round 6 | explore_schema | 继续用 `Orange County` 计数 | 返回 0，字段取值仍错。 |
| Round 7 | explore_schema | 查看 county 样例 | 发现 county 取值类似 `Orange`。 |
| Round 8 | explore_schema | 验证 `County LIKE '%Orange%'` | 找到正确 county 值 `Orange`。 |
| Round 9 | explore_schema | 在 Orange 且 Merged 内按 DOC 计数 | 得到 `DOC=54` 为 4、`DOC=52` 为 7；但这只适用于分子，gold 分母是全州 `DOC=52`。 |
| Round 10 | generate_sql | 用同一个 Orange 过滤同时算分子和分母 | 得到 `4/7=0.5714`；根因是分母范围被错误限制到 Orange County。 |""",
    "50": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `schools`、`satscores`。 |
| Round 2 | explore_schema | 查看 `schools` 字段 | 找到 `MailStreet` 和 `School`。 |
| Round 3 | explore_schema | 查看 `frpm` 字段 | 与本题不关键。 |
| Round 4 | explore_schema | 查看 `satscores` 字段 | 找到 `AvgScrMath` 和 `rtype`。 |
| Round 5 | generate_sql | 按 math average 降序 `LIMIT 7 OFFSET 6` | 返回第 7 到第 13 共 7 行；而题目只要第 7 高的 1 行。还缺 `rtype='S'` 与非空过滤。 |
| Round 6 | confirm_answer | 确认 7 行结果 | 根因是 top-k 语义错；只修 LIMIT 后还会因未过滤 district/NULL 选错学校。 |""",
    "62": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `frpm` 和 `schools`。 |
| Round 2 | explore_schema | 查看 `schools` 字段 | 找到 charter/county join 相关字段。 |
| Round 3 | explore_schema | 重复查询表 | 探索冗余。 |
| Round 4 | explore_schema | 查看 `frpm` 字段 | 找到 `Percent (%) Eligible Free (K-12)` 和 count/enrollment 字段。 |
| Round 5 | explore_schema | 查看 FRPM 样例 | 应能看出 percent 字段存的是比例，如 0.7 表示 70%。 |
| Round 6 | propose_schema | 提出用 stored percent 字段 | 没有把题目中的 `0.18%` 转换为存储比例阈值 `0.0018`。 |
| Round 7 | generate_sql | 用 `Percent (%) Eligible Free (K-12) < 0.18` 计数 | 把 0.18 当 18%，返回 `201`。 |
| Round 8 | confirm_answer | 确认比例阈值错误版本 | 根因是百分数单位错；gold 按公式 `<0.18%` 只有 1 所。 |""",
    "72": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `schools` 过滤 State Special School/Fremont，`frpm` 取 enrollment。 |
| Round 2 | explore_schema | 查看 `schools` 字段 | 找到 `EdOpsCode` 和 `City`。 |
| Round 3 | explore_schema | 查看 `frpm` 字段 | 已看到 `Enrollment (Ages 5-17)` 和 `Academic Year`。 |
| Round 4 | propose_schema | 提出 join 与条件 | 字段方向对，但没有明确学生数要 SUM enrollment。 |
| Round 5 | generate_sql | 按条件执行 `COUNT(*) as student_count` | 返回 `2`，这是符合条件的记录/学校数，不是学生人数。 |
| Round 6 | confirm_answer | 确认 COUNT 版本 | 根因是聚合含义错；应 `SUM("Enrollment (Ages 5-17)") = 375`。 |""",
    "77": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `schools` 与 `frpm`。 |
| Round 2 | explore_schema | 查看 `schools` 字段 | 同时存在 `GSoffered` 和 `GSserved`，后续选错。 |
| Round 3 | explore_schema | 查看 `frpm` 字段 | 找到 `FRPM Count (Ages 5-17)` 与 `Enrollment (Ages 5-17)`。 |
| Round 4 | explore_schema | 查看 `GSoffered` 取值 | 题目说 served grade span，但模型从 offered 字段开始探索。 |
| Round 5 | explore_schema | 一次提交两条 SQL | 工具报 “only one statement”，浪费一轮。 |
| Round 6 | explore_schema | 查看 `schools.County` 取值 | county 路径正常。 |
| Round 7 | explore_schema | 查看 `frpm."County Name"` 取值 | county 路径正常。 |
| Round 8 | explore_schema | 验证 `Los Angeles` | county 值确认。 |
| Round 9 | explore_schema | 查 `GSoffered` 中 K-9 | 找到 `K-9`，但这是 offered，不是 gold 使用的 `GSserved`。 |
| Round 10 | propose_schema | 只提出 schema，没有生成 SQL | 双重失败：10 轮耗尽导致 `pred_sql` 为空；语义上也已把 `served` 错对到 `GSoffered`。 |""",
    "79": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 只需要 `schools`。 |
| Round 2 | explore_schema | 查看 `schools` 字段 | 找到 `County` 和 `Virtual`。 |
| Round 3 | explore_schema | 验证 San Diego/Santa Barbara county 值 | 两个 county 都存在。 |
| Round 4 | generate_sql | 分组计数并 `ORDER BY ... LIMIT 1` | 这一轮其实已经得到 gold 形状：`San Diego, 8`。 |
| Round 5 | generate_sql | 改成分组计数但去掉 `LIMIT 1` | 退化为返回两个 county。 |
| Round 6 | confirm_answer | confirm 阶段没有有效结构化 SQL | 没能锁住 Round 4 的正确版本。 |
| Round 7 | confirm_answer | 最终确认无 `LIMIT 1` 的 SQL | 根因是自我修正反而删掉 top-1 约束；最终多返回 Santa Barbara。 |""",
    "83": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `schools` 和 `frpm`。 |
| Round 2 | explore_schema | 查看 `schools` 字段 | 找到 `City`、`Magnet`，但 magnet 不是题目条件。 |
| Round 3 | explore_schema | 查看 `frpm` 字段 | 找到 `Low Grade`、`High Grade`、`NSLP Provision Status`。 |
| Round 4 | propose_schema | 把 `Magnet` 纳入候选 schema | 受 evidence 干扰，把无关条件提前放进计划。 |
| Round 5 | generate_sql | 首次用 `Low Grade/High Grade` 未 quote | 字段含空格导致语法错误。 |
| Round 6 | generate_sql | 修好 quote，但保留 `s.Magnet=1` | 返回 `Adelanto, 1`；正确不加 magnet 应为 `Adelanto, 2`。 |
| Round 7 | confirm_answer | 确认 magnet 过滤版本 | 根因是多加无关条件，不是 grade span 字段本身。 |""",
    "85": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `schools` 找管理员，`frpm` 输出 district/rate。 |
| Round 2 | explore_schema | 查看 `schools` 字段 | 找到 `AdmFName1`。 |
| Round 3 | explore_schema | 查看 `frpm` 字段 | 找到 `District Code`、stored percent、free count/enrollment。 |
| Round 4 | generate_sql | 先用不存在的 `DistrictCode` | 报 `no such column`，字段名需要带空格。 |
| Round 5 | generate_sql | 改用 `"District Code"` 并输出 stored percent | 能找到学校，但列顺序是 `(District Code, stored ratio)`，gold 要 `(computed percent, District Code)`。 |
| Round 6 | confirm_answer | 确认列顺序/单位错误版本 | 根因是输出顺序反了，且 `0.7015` 没乘 100 成 `70.1513`。 |""",
}


def replace_table(section: str, table: str) -> str:
    marker = "\n### 运行轨迹\n"
    if marker not in section:
        return section.rstrip() + "\n\n" + table.rstrip() + "\n"
    return section[: section.index(marker)].rstrip() + "\n\n" + table.rstrip() + "\n"


def main() -> None:
    changed = []
    for path in FILES:
        text = path.read_text(encoding="utf-8")
        matches = list(re.finditer(r"^## qid(\d+)\b.*$", text, re.M))
        pieces = []
        last = 0
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
        path.write_text("".join(pieces), encoding="utf-8")
    print(f"updated {len(changed)} qids:", ", ".join(changed))


if __name__ == "__main__":
    main()
