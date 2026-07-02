#!/usr/bin/env python3
"""Apply hand-written, root-cause-oriented trajectory tables for formula_1."""

from __future__ import annotations

import re
from pathlib import Path


TARGET = Path("/root/autodl-tmp/text_to_sql_benchmarks/results/qwen35-4b-arcwise-plat-trustsql-full-final-thinking/formula_1_wrong_analysis.md")


TABLES = {
    "854": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 找到 `circuits` 和 `races`。 |
| Round 2 | explore_schema | 查看 `circuits` | 找到坐标字段 `lat/lng` 和 `circuitId`。 |
| Round 3 | explore_schema | 查看 `races` | 找到 `name` 和 `circuitId`。 |
| Round 4 | propose_schema | 提出 `circuits JOIN races` | join 路径正确。 |
| Round 5 | confirm_answer | 直接确认包含 `lat,lng,circuit_name,race_name` 的 SQL | 坐标正确，但多输出两列且无 `DISTINCT`，Australian GP 多年重复成 11 行。 |""",
    "861": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `qualifying` 和 `drivers`。 |
| Round 2 | explore_schema | 查看 `qualifying` | 找到 `raceId/driverId/q3`。 |
| Round 3 | explore_schema | 查看 `drivers` | 找到 `driverId/number`。 |
| Round 4 | generate_sql | join drivers，但按 `q3 LIKE '0:01:54%'` 查 | 空结果；数据库 q3 格式不是 `0:MM:SS`。 |
| Round 5 | explore_schema | 确认 raceId 903 | 知道是 Chinese Grand Prix。 |
| Round 6 | explore_schema | 查看 raceId 903 的 q3 样例 | 看到 `1:54.455`、`1:54.960`，格式应为 `1:54%`。 |
| Round 7 | generate_sql | 改用 `q3 LIKE '1:54%'` | 找到两行，但只返回 q3 时间。 |
| Round 8 | generate_sql | 重复返回 q3 | 没有 join 回 `drivers`。 |
| Round 9 | generate_sql | 第三次重复 q3 查询 | 仍未返回 driver number。 |
| Round 10 | generate_sql | 第四次重复 q3 查询 | gold 要 `drivers.number`，pred 返回的是时间本身。 |""",
    "866": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `lapTimes` 和 `drivers`。 |
| Round 2 | explore_schema | 查看 `drivers` | 找到 `forename/surname/url/driverId`。 |
| Round 3 | explore_schema | 查看 `lapTimes` | 找到 `raceId/driverId/time`。 |
| Round 4 | explore_schema | 查看 `races` | 可确认 raceId。 |
| Round 5 | propose_schema | 提出三表方案 | 表选择正确。 |
| Round 6 | generate_sql | 用 `lt.time LIKE '0:01:27%'` join drivers | 返回空；时间格式错。 |
| Round 7 | explore_schema | 确认 raceId 161 | 是 British Grand Prix。 |
| Round 8 | explore_schema | 查看 raceId 161 的 lap time 样例 | 看到 `1:30.xxx` 等 `M:SS.mmm` 格式。 |
| Round 9 | explore_schema | 检查 `0:01:27%` | 为空，证明前缀错误。 |
| Round 10 | explore_schema | 排序查看最小时间 | 看到大量 `1:27.xxx`，但没有回到 generate_sql 用 `1:27%`；最终 pred 仍为空。 |""",
    "872": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `qualifying` 和 `drivers`。 |
| Round 2 | explore_schema | 查看 `races` | 找到 raceId 字段。 |
| Round 3 | explore_schema | 查看 `qualifying` | 找到 `q3/driverId/raceId`。 |
| Round 4 | explore_schema | 查看 `drivers` | 找到 `code`。 |
| Round 5 | propose_schema | 提出 races-qualifying-drivers | join 方向正确。 |
| Round 6 | generate_sql | 用 `q3 LIKE '0:01:33%'` 查 driver code | 空结果，时间格式错。 |
| Round 7 | generate_sql | 用 `q3='0:01:33'` 精确匹配 | 仍为空。 |
| Round 8 | generate_sql | 改查 race 45 的 q3 列表 | 看到 `1:33.833`，已经暴露正确模式。 |
| Round 9 | generate_sql | 排序 q3 列表 | NULL 在前，仍只是看 q3 明细。 |
| Round 10 | generate_sql | 输出 race 45 全部 q3 | 没有过滤 `1:33%`，也没有 join drivers 返回 `code`；gold 只要 `HAM`。 |""",
    "877": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `drivers/results/status`。 |
| Round 2 | explore_schema | 查看 `drivers/races/results` | 找到 `dob`、`raceId`、`statusId/laps`。 |
| Round 3 | explore_schema | 查看 `status` | 找到 finished 状态文本。 |
| Round 4 | generate_sql | 过滤 race 872 finished，并按 `dob ASC` 取 1 | 选出 Michael Schumacher；`dob ASC` 是最老，不是最年轻。 |
| Round 5 | confirm_answer | 确认并多输出 `dob` | gold 用 `ORDER BY dob DESC` 选 Sergio Pérez，且只输出 forename/surname。 |""",
    "879": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `results.fastestLapSpeed` 和 `drivers.nationality`。 |
| Round 2 | explore_schema | 查看 `drivers` | 找到 nationality。 |
| Round 3 | explore_schema | 查看 `lapTimes` | 被 lapTimes 干扰；fastestLapSpeed 不在此表。 |
| Round 4 | explore_schema | 查看 `races` | 不关键。 |
| Round 5 | explore_schema | 查看 `results` | 找到 `fastestLapSpeed`。 |
| Round 6 | propose_schema | schema JSON 格式错 | 没有成功记录 schema。 |
| Round 7 | generate_sql | join drivers/results，按 `r.fastestLapSpeed DESC` 排序 | 返回 Italian；这是 TEXT 字符串排序。 |
| Round 8 | confirm_answer | 确认字符串排序结果 | gold 需要 `CAST(fastestLapSpeed AS REAL) DESC`，返回 Brazilian。 |""",
    "881": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `races/results/status`。 |
| Round 2 | explore_schema | 查看 `drivers` | 不关键，题目算全体参赛车手 completion rate。 |
| Round 3 | explore_schema | 查看 `races` | 找到 `date`。 |
| Round 4 | explore_schema | 查看 `results` | 找到 `statusId`。 |
| Round 5 | explore_schema | 查看 `status` | 找到 status 文本表。 |
| Round 6 | explore_schema | 查看 status 样例 | 看到 `Finished`、`+1 Lap` 等完成口径。 |
| Round 7 | explore_schema | 查 1983-07-16 的 race | 得到 raceId 460。 |
| Round 8 | propose_schema | 提出 races-results-status | 表路径正确。 |
| Round 9 | generate_sql | 引用 `r.statusId/r.status` | `r` 是 races，报 no such column。 |
| Round 10 | generate_sql | 改成引用 `res.status` | `results` 只有 `statusId`，未 join `status`，继续执行失败。 |""",
    "884": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 只需要 `races`。 |
| Round 2 | explore_schema | 查看 `races` 建表 SQL | 找到 `date/year/name`。 |
| Round 3 | explore_schema | 查看 `races` 字段 | 确认日期字段。 |
| Round 4 | explore_schema | 查询最早日期 | 得到 `1950-05-13`，需要 year=1950 且 month=05。 |
| Round 5 | generate_sql | 使用 SQLite 不存在的 `month()` | 报函数不存在。 |
| Round 6 | generate_sql | 改用 `strftime('%m')` 但取全库最小 month | 返回空；应该取最早日期的 month，而非所有年份的最小 month。 |
| Round 7 | generate_sql | 只取最早一场 | 得到 British GP，但漏掉同年同月另外两场。 |
| Round 8 | generate_sql | 列出 1950 所有比赛 | 看到 5 月有三场。 |
| Round 9 | generate_sql | 正确筛 `year=1950 AND month=05` | 得到三场正确 race name。 |
| Round 10 | generate_sql | 又改成 `month(date)` 并多输出列 | 最终 SQL 执行失败，覆盖了 Round 9 的正确思路。 |""",
    "897": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 drivers 和积分/获胜记录。 |
| Round 2 | explore_schema | 查看 `drivers` | 找到姓名和 nationality。 |
| Round 3 | explore_schema | 查看 `results` | 找到每场 results points/position。 |
| Round 4 | propose_schema | 提出 drivers-results | 漏掉 `driverStandings`。 |
| Round 5 | generate_sql | 用 CTE 统计获胜次数 | 工具拒绝 `WITH`。 |
| Round 6 | generate_sql | 用 results `position=1` 统计 wins | 找到 Michael Schumacher 和 91 wins，winner 判断可接受。 |
| Round 7 | generate_sql | 对 Schumacher 的 `results.points` 求 SUM | 得到 1566.0；gold 要 `driverStandings.MAX(points)=148.0`。 |
| Round 8 | confirm_answer | 确认 results 累计积分 | 最终人对了，但积分口径表错。 |""",
    "898": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 正确表是 `drivers`。 |
| Round 2 | explore_schema | 查看 `drivers` | 找到 `dob/nationality/forename/surname`。 |
| Round 3 | propose_schema | 提出只用 drivers | 表正确。 |
| Round 4 | generate_sql | 尝试用 `SUBTRACT/MMDD/year` 算年龄 | SQLite 不支持这些函数。 |
| Round 5 | generate_sql | 继续使用 `SUBTRACT` | 仍执行失败。 |
| Round 6 | generate_sql | 改掉 SUBTRACT 但仍用 `year()` | 继续执行失败。 |
| Round 7 | generate_sql | 用 `strftime` 成功计算，但硬编码日期 `2024-01-01`，并输出 name/dob/age | 得到 Kamui Kobayashi 但年龄 37，列形状也错。 |
| Round 8 | confirm_answer | 确认硬编码 2024 的结果 | gold 用当前时间计算年龄，且输出 `age, forename, surname`。 |""",
    "902": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `drivers/driverStandings/races`。 |
| Round 2 | explore_schema | 查看相关建表 SQL | 找到 driverStandings 的 `position/raceId/driverId`。 |
| Round 3 | explore_schema | 查 Alex Yoong driverId | 得到 `62`。 |
| Round 4 | explore_schema | 查看 races 样例 | race name 可取。 |
| Round 5 | generate_sql | 筛 driverId=62 且 position<20 | 返回的 race 集合正确，但多输出 `position/raceId`。 |
| Round 6 | confirm_answer | 确认三列版本 | gold 只要 `races.name`。 |""",
    "906": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `drivers/results/races`。 |
| Round 2 | explore_schema | 查看 `drivers` | 找到 Lewis Hamilton。 |
| Round 3 | explore_schema | 查看 `races` | 找到 date/name。 |
| Round 4 | explore_schema | 查看 `results` | 找到 points/raceId/driverId。 |
| Round 5 | explore_schema | 查 Hamilton driverId | 得到 1。 |
| Round 6 | generate_sql | 按 race date 最早取 Hamilton 的 race name/date/points | 找到 Australian GP 和 6 分，但多输出 race_date。 |
| Round 7 | confirm_answer | 确认三列版本 | gold 只要 race name 和 points。 |""",
    "909": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `races/circuits`。 |
| Round 2 | explore_schema | 查看 `races` | 找到 race name 和 circuitId。 |
| Round 3 | explore_schema | 查看 `circuits` | 找到 country。 |
| Round 4 | explore_schema | 枚举 Grand Prix 名称 | 确认 European Grand Prix。 |
| Round 5 | explore_schema | 查看 European GP 对应国家 | 看到 23 场，其中 Germany 12 场。 |
| Round 6 | generate_sql | 计算 total、Germany count、rounded percentage 三列 | 百分比方向对，但输出多列且 round 到 52.17。 |
| Round 7 | confirm_answer | 确认三列两位小数版本 | gold 只返回完整精度百分比 52.17391304347826。 |""",
    "915": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 正确表是 `drivers`。 |
| Round 2 | explore_schema | 查看 `drivers` | 找到 `dob/nationality`。 |
| Round 3 | generate_sql | `ORDER BY dob ASC LIMIT 1` | SQLite 将 NULL dob 排在最前，返回 South African。 |
| Round 4 | confirm_answer | 确认未过滤 NULL 的结果 | gold 先 `dob IS NOT NULL`，最老有生日记录的 driver nationality 是 French。 |""",
    "930": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `drivers/results/races`。 |
| Round 2 | explore_schema | 查看 drivers 样例 | 确认 Lewis Hamilton 存在。 |
| Round 3 | explore_schema | 查看 races 样例 | 找到 race name/year。 |
| Round 4 | explore_schema | 查看 results 样例 | 找到 `positionOrder`。 |
| Round 5 | propose_schema | 提出三表方案 | 方向正确。 |
| Round 6 | generate_sql | 把 `results` alias 为 `r`，却用 `r.name/r.positionOrder` | `r` 是 results，没有 name，报错。 |
| Round 7 | explore_schema | 查看 races 字段 | 证明 name/year 在 races。 |
| Round 8 | generate_sql | 重复错误 alias SQL | 继续报 `r.name` 不存在。 |
| Round 9 | generate_sql | 用完整表名修正 alias | 返回 Hamilton wins，但多输出 year、forename/surname、best_position/race_count。 |
| Round 10 | generate_sql | 又改成 `SELECT DISTINCT r.name, r.year` 但没有定义 alias r | 最终执行失败；修正后也会多输出 year。 |""",
    "937": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `races/results`，drivers 仅用于解释。 |
| Round 2 | explore_schema | 查看 races/results/drivers | 找到 `position/time/driverId`。 |
| Round 3 | explore_schema | 查 2008 Chinese GP | 得到 raceId 34。 |
| Round 4 | explore_schema | 查 raceId 34 的 position=2 | 已直接看到 `time='+14.925'`。 |
| Round 5 | explore_schema | 查看 race 34 全部排序 | 确认第二名记录。 |
| Round 6 | explore_schema | 查 driverId 13 | 得到 Felipe Massa，但题目没要求姓名。 |
| Round 7 | 格式错误 | assistant 未给有效 action | 浪费一轮。 |
| Round 8 | generate_sql | 返回 `time, forename, surname` | 时间正确，但多输出 driver 姓名。 |
| Round 9 | 格式错误 | 未给有效 action | 没有修正输出形状。 |
| Round 10 | 格式错误 | 未给有效 action | 最终保留三列 SQL；gold 只要 `time`。 |""",
    "944": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `races/results/status`。 |
| Round 2 | explore_schema | 查看 `races` | 找到 year/name/raceId。 |
| Round 3 | explore_schema | 查看 `results` | 找到 `positionOrder/milliseconds/statusId`。 |
| Round 4 | explore_schema | 查看 `status` | 可识别 finished all laps。 |
| Round 5 | explore_schema | 查看 `drivers` | 本题不需要 driver 信息。 |
| Round 6 | explore_schema | 查看 `lapTimes` | 与最终百分比不直接相关。 |
| Round 7 | explore_schema | 查看 `seasons` | 无关。 |
| Round 8 | explore_schema | 重复查看 `status` | 信息已足够。 |
| Round 9 | explore_schema | 查 1988 Australian GP，但 WHERE 缺括号 | `year=1988` 只作用于第一项，`OR name LIKE` 拉出大量 Australian GP 年份。 |
| Round 10 | explore_schema | 查 raceId 387 的 results 明细 | 仍停在探索；没有构造 champion vs last finished driver milliseconds 差值百分比，pred 为空。 |""",
    "948": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 相关表有 `constructorResults` 和 `constructorStandings`。 |
| Round 2 | explore_schema | 查看 `constructors` | 找到 nationality。 |
| Round 3 | explore_schema | 查看 `constructorResults` | 看到 points，于是选了比赛结果表。 |
| Round 4 | generate_sql | 对 British constructors 的 `constructorResults.points` 求 MAX | 返回 66.0。 |
| Round 5 | confirm_answer | 确认结果表口径 | gold 要 standings 积分峰值 `constructorStandings.points`，最大为 497.0。 |""",
    "951": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `constructors/constructorResults`。 |
| Round 2 | explore_schema | 查看 `constructors` | 找到 nationality/name。 |
| Round 3 | explore_schema | 查看 `races` | 不关键。 |
| Round 4 | explore_schema | 查看 `constructorResults` | 找到 raceId、constructorId、points。 |
| Round 5 | generate_sql | 找 Japanese constructor，HAVING 两场且总积分 0 | 定位到 Kojima 正确，但输出 constructorId/name/race_count/total_points。 |
| Round 6 | confirm_answer | 确认明细行 | gold 只输出数量 1，不要 constructor 明细。 |""",
    "954": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `drivers/results/races/status`。 |
| Round 2 | explore_schema | 查看 `drivers` | 找到 nationality。 |
| Round 3 | explore_schema | 查看 `races` | 找到 year。 |
| Round 4 | explore_schema | 查看 `results` | 找到 driverId/raceId/statusId。 |
| Round 5 | explore_schema | 查看 `status` 建表 SQL | 找到 status 文本表。 |
| Round 6 | explore_schema | 查看所有 status | 看到 `Finished` 和 `+n Laps`。 |
| Round 7 | explore_schema | 枚举 nationality | 确认 Japanese。 |
| Round 8 | propose_schema | 提出四表方案 | 表路径正确。 |
| Round 9 | generate_sql | 错把 `races` 当有 `status` 字段，并用 distinct driver 分母 | 报 no such column；即使修正，粒度也是 driver 不是 race result。 |
| Round 10 | generate_sql | 改引用 `res.status` | results 没有 status 文本，仍未 join `status`，执行失败。 |""",
    "955": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `races/results`。 |
| Round 2 | explore_schema | 查看相关建表 SQL | 已看到 `results.time/milliseconds/position`。 |
| Round 3 | explore_schema | 一次提交多条 SQL | 工具拒绝多语句。 |
| Round 4 | explore_schema | 查看 1975 前 races 样例 | 得到 raceId/year。 |
| Round 5 | explore_schema | 查看这些 race 的 champion results | 已看到 champion `time` 和 `milliseconds`。 |
| Round 6 | explore_schema | 直接在 results 查 `year` | 报 no such column，year 在 races。 |
| Round 7 | explore_schema | join races/results 查看 champion 时间 | 明确 `milliseconds` 已可直接用于秒数。 |
| Round 8 | explore_schema | 枚举年份 | 无新增。 |
| Round 9 | explore_schema | 再看 champion 时间样例 | 仍显示可用 `pos.milliseconds`。 |
| Round 10 | generate_sql | 手写复杂字符串解析且误用 `r.time` | SQL 语法错误；gold 直接 `AVG(results.milliseconds/1000.0)` 按 year 聚合。 |""",
    "959": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `races/results`。 |
| Round 2 | explore_schema | 查看 races/results 等 | 找到 `fastestLap` 和 year。 |
| Round 3 | explore_schema | 查看 `driverStandings` | 不需要。 |
| Round 4 | propose_schema | 提出 races-results | 表正确。 |
| Round 5 | generate_sql | 查 2009 position=1 的 raceId/name/fastestLap | fastestLap 集合正确，但多输出 raceId/name。 |
| Round 6 | confirm_answer | 确认三列版本 | gold 只要 champion 的 `fastestLap` 一列。 |""",
    "960": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `races/results`。 |
| Round 2 | explore_schema | 查看 `races` | 找到 year/name/raceId。 |
| Round 3 | explore_schema | 查看 `lapTimes` | 被 lapTimes 引走；fastestLapSpeed 在 results。 |
| Round 4 | explore_schema | 查看 `races` 建表 SQL | 重复。 |
| Round 5 | explore_schema | 再看 `lapTimes` 字段 | 仍未转到 results fastestLapSpeed。 |
| Round 6 | explore_schema | 查看 `lapTimes` 建表 SQL | 无新增。 |
| Round 7 | explore_schema | 查看 `results` 建表 SQL | 已看到 `fastestLapSpeed`，足够生成。 |
| Round 8 | explore_schema | 查 2009 Spanish GP raceId | 得到 raceId 5。 |
| Round 9 | explore_schema | 重复查 raceId 5 | 无新增。 |
| Round 10 | explore_schema | 第三次重复 raceId 查询 | 最大轮数耗尽；没有生成 `AVG(results.fastestLapSpeed)` SQL。 |""",
    "962": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `results/races/drivers`。 |
| Round 2 | explore_schema | 查看 `drivers` | 找到 `dob`。 |
| Round 3 | explore_schema | 查看 `races` | 找到 year。 |
| Round 4 | explore_schema | 查看 `results` | 找到 laps/driverId/raceId。 |
| Round 5 | propose_schema | 提出三表方案 | 表正确。 |
| Round 6 | generate_sql | 用 SQLite 不支持的 `year(dob)` | 执行失败。 |
| Round 7 | generate_sql | 改用 `strftime`，但和数值 1985 比较导致结果 NULL | 没有得到百分比。 |
| Round 8 | generate_sql | 单独查分子 count | 返回 0，说明年份比较/过滤仍错。 |
| Round 9 | generate_sql | 查 `strftime('%Y', dob) < 1985` 的出生年份 | 返回空，继续暴露比较类型错误。 |
| Round 10 | generate_sql | 改成列出所有 birth_year | 完全偏离百分比任务；最终 pred 是年份列表。 |""",
    "972": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `drivers` 和 fastest lap 相关表。 |
| Round 2 | explore_schema | 查看 `drivers` | 找到 dob/code。 |
| Round 3 | explore_schema | 查看 `lapTimes` | 模型把 “fastest lap time” 理解成每场 lapTimes 最小圈速。 |
| Round 4 | explore_schema | 查看 `races` | 不关键。 |
| Round 5 | explore_schema | 列出 1971 出生司机 | 得到多个候选。 |
| Round 6 | explore_schema | 查看 lapTimes 最小毫秒样例 | 继续沿每场最快圈路径。 |
| Round 7 | generate_sql | 找 1971 司机中每场最小 lapTimes 的记录 | 返回大量重复 driver 行。 |
| Round 8 | generate_sql | 加 DISTINCT 去重 | 返回 3 个 driver。 |
| Round 9 | confirm_answer | 确认每场最快 lapTimes 口径 | gold 只要求 `results.fastestLapTime IS NOT NULL`，应返回 4 个 1971 出生 driver。 |""",
    "978": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 正确表是 `circuits`。 |
| Round 2 | explore_schema | 查看 `circuits` | 找到 `country/location/lat/lng/name`。 |
| Round 3 | propose_schema | 提出 circuits | 表正确。 |
| Round 4 | generate_sql | 查 Austria 的 `name, location, lat, lng` | 多输出 circuit name，且同一 location/坐标因 A1-Ring 和 Red Bull Ring 重复。 |
| Round 5 | confirm_answer | 确认四列版本 | gold 要 `DISTINCT location, lat, lng`。 |""",
    "988": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `drivers/pitStops`。 |
| Round 2 | explore_schema | 查看 `drivers` | 找到 nationality/dob/name。 |
| Round 3 | explore_schema | 查看 `pitStops` | 找到 duration/driverId。 |
| Round 4 | propose_schema | 提出 drivers-pitStops | 表正确。 |
| Round 5 | generate_sql | 用 nationality='Germany' | 返回空；值应为 German。 |
| Round 6 | explore_schema | 枚举 nationality | 看到 `German`。 |
| Round 7 | generate_sql | 改为 `German` 并按 AVG(duration) 排 top3 | 排序结果正确，但多输出 nationality、dob、avg duration。 |
| Round 8 | confirm_answer | 确认五列版本 | gold 只要 forename/surname。 |""",
    "990": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `races/results/constructors`。 |
| Round 2 | explore_schema | 查看 `races` | 找到 year/name/raceId。 |
| Round 3 | explore_schema | 查看 `constructors` | 找到 constructorRef/url。 |
| Round 4 | explore_schema | 查看 `results` | 找到 constructorId、time、position。 |
| Round 5 | explore_schema | 查看 `status` | 不关键。 |
| Round 6 | explore_schema | 查 2009 Singapore GP | 确认目标 race。 |
| Round 7 | explore_schema | 试图查 results 并带 `name` | results 没有 name，报错。 |
| Round 8 | generate_sql | 查 race 的 position 最前 results 明细 | 因 NULL position 排前，拿到 constructorId=5，但这不是 champion。 |
| Round 9 | explore_schema | 查 constructorId=5 | 得到 Toro Rosso，已经是错误线索。 |
| Round 10 | generate_sql | 输出 race 14 前 10 条 results 明细 | 最终被诊断 SQL 覆盖；gold 要 champion constructorRef/url，应用 time 格式或 position=1 取 McLaren。 |""",
    "994": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `constructorResults/constructors/races`。 |
| Round 2 | explore_schema | 查看 `races` | 找到 name/year。 |
| Round 3 | explore_schema | 查看 `constructorResults` | 找到 points/constructorId/raceId。 |
| Round 4 | explore_schema | 查看 `constructors` | 找到 name/nationality。 |
| Round 5 | explore_schema | 查看 Monaco GP 样例 | 确认筛选条件。 |
| Round 6 | explore_schema | 列出 1980-2010 Monaco raceId | 得到目标 race 集。 |
| Round 7 | generate_sql | 汇总 constructor points 并 top1 | 找到 McLaren 218.5，但列顺序为 constructorId,name,nationality,total_points。 |
| Round 8 | generate_sql | 查看完整排序 | 逻辑仍正确，用于确认。 |
| Round 9 | confirm_answer | 确认多列/错序版本 | gold 输出 `score, name, nationality`，不能多 constructorId，score 也应在第一列。 |""",
    "1002": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `drivers/results/races`。 |
| Round 2 | explore_schema | 查看 `drivers` | 找到 dob/name/nationality。 |
| Round 3 | explore_schema | 查看 `races` | 找到 race name/year/round。 |
| Round 4 | explore_schema | 查看 `results` | 找到 driverId/raceId。 |
| Round 5 | explore_schema | 按 dob DESC 查看最年轻司机 | 找到 Lance Stroll。 |
| Round 6 | explore_schema | 单独确认最年轻 driverId=840 | 信息正确。 |
| Round 7 | explore_schema | 查看最早 races | 只是全局 races，不是 Stroll 参赛。 |
| Round 8 | explore_schema | 查看 results driverId 样例 | 不关键。 |
| Round 9 | generate_sql | 查询最年轻司机的姓名、国籍、最早参赛 race | 返回 gold 需要的一行。 |
| Round 10 | generate_sql | 又改成只列 driverId=840 的前 5 场 race | 最终 SQL 覆盖正确答案，只剩 race name/year/round，缺姓名和国籍。 |""",
    "1011": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `drivers/lapTimes`。 |
| Round 2 | explore_schema | 查看 `drivers` | 找到 forename/surname。 |
| Round 3 | explore_schema | 查看 `lapTimes` | 同时看到 `time` 文本和 `milliseconds` 数值。 |
| Round 4 | explore_schema | 查看 `races` | 不需要。 |
| Round 5 | generate_sql | 按 `MIN(l.time)` 文本排序并拼接 full_name | 字典序使 `10:32.179` 排在 `1:xx` 前；且输出一列 full_name 加 lap time。 |
| Round 6 | confirm_answer | 确认文本时间排序版本 | gold 应按 `MIN(milliseconds)` 排序，并输出 forename、surname 两列。 |""",
    "1014": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 Italy circuits 和 lap record 来源。 |
| Round 2 | explore_schema | 查看 `circuits` | 找到 country/circuitId。 |
| Round 3 | explore_schema | 查看 `lapTimes` | 被 lapTimes 的 `time` 吸引。 |
| Round 4 | explore_schema | 查看 `races` | 找到 circuitId/raceId。 |
| Round 5 | explore_schema | 枚举 circuit country | 确认 Italy 存在。 |
| Round 6 | explore_schema | 查 Italy circuitId 对应 races | 找到 14/21/65。 |
| Round 7 | explore_schema | 查看 Italy race 样例 | 确认 join。 |
| Round 8 | propose_schema | 提出 circuits-races-lapTimes | 表路径选择了 lapTimes。 |
| Round 9 | generate_sql | `MIN(lapTimes.time)` 求 Italy lap record | 返回 `13:29.130`，是文本字典序最小，不是最快。 |
| Round 10 | confirm_answer | 确认 lapTimes 文本 MIN | gold 使用 `results.fastestLapTime` 并解析成秒后取最小，答案 `1:20.411`。 |""",
}


def replace_table(text: str, qid: str, table: str) -> str:
    start = re.search(rf"^## qid{re.escape(qid)}\b", text, re.M)
    if not start:
        raise SystemExit(f"missing qid section: {qid}")

    next_section = re.search(r"^## qid\d+\b|^## 错误类型归纳|^## 对后续改进", text[start.end():], re.M)
    section_end = start.end() + next_section.start() if next_section else len(text)
    section = text[start.start():section_end]

    marker = "### 运行轨迹\n"
    marker_idx = section.find(marker)
    if marker_idx < 0:
        raise SystemExit(f"missing trajectory marker for qid {qid}")

    before = section[:marker_idx]
    after = section[marker_idx + len(marker):]
    following_heading = re.search(r"\n## |\n### ", after)
    tail = after[following_heading.start():] if following_heading else ""

    new_section = before + table.rstrip() + "\n" + tail
    return text[:start.start()] + new_section + text[section_end:]


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")
    for qid, table in TABLES.items():
        text = replace_table(text, qid, table)
    TARGET.write_text(text, encoding="utf-8")
    print(f"updated {len(TABLES)} qids: {', '.join(TABLES)}")


if __name__ == "__main__":
    main()
