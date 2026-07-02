#!/usr/bin/env python3
"""Apply hand-written, root-cause-oriented trajectory tables for thrombosis_prediction."""

from __future__ import annotations

import re
from pathlib import Path


TARGET = Path("/root/autodl-tmp/text_to_sql_benchmarks/results/qwen35-4b-arcwise-plat-trustsql-full-final-thinking/thrombosis_prediction_wrong_analysis.md")


TABLES = {
    "1149": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 确认本题主要落在 `Patient`。 |
| Round 2 | explore_schema | 查看 `Patient` 建表 SQL | 找到 `SEX` 和 `Admission`，足够计算男女/住院状态。 |
| Round 3 | generate_sql | 先只输出住院/门诊比例 | 算出 `89/107 = 0.831775...`，但题库 gold 按百分比口径要乘以 100。 |
| Round 4 | generate_sql | 把分子、分母和比例一起输出 | 分子分母对，但仍没乘 100，且多了两列。 |
| Round 5 | confirm_answer | 确认 Round 4 的三列表达 | 最终失败点是“比例尺度 + 输出形状”：gold 只要单列 `83.177...`。 |""",
    "1166": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 找到 `Patient`、`Examination`、`Laboratory`。 |
| Round 2 | explore_schema | 查看 `Patient` | 需要用 `Birthday` 找做过检查的最年轻患者，并取 `Diagnosis`。 |
| Round 3 | explore_schema | 查看 `Examination` | 找到 `Symptoms`，也知道可通过 `ID` 与患者关联。 |
| Round 4 | explore_schema | 查看 `Laboratory` | 与本题不直接相关，探索开始发散。 |
| Round 5 | explore_schema | 一次提交 Patient/Examination/Laboratory 三条查询 | 工具拒绝多语句：`You can only execute one statement at a time.` |
| Round 6 | explore_schema | 查看 `Examination` 外键 | 确认 `Examination.ID -> Patient.ID`，方向是对的。 |
| Round 7 | explore_schema | 一次提交三条 COUNT 查询 | 再次违反单语句限制。 |
| Round 8 | explore_schema | 一次提交三张表按日期排序查询 | 第三次被单语句限制挡住。 |
| Round 9 | explore_schema | 重复 Round 8 的多语句查询 | 没有推进到“按 Birthday DESC 选患者 + 查 Symptoms”。 |
| Round 10 | explore_schema | 再次重复多语句查询 | 轮数耗尽，最终 `pred_sql` 为空；正确答案应是最年轻检查患者 `SJS` 且 Symptoms 为 NULL。 |""",
    "1168": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要 `Patient` 找最老 SJS 患者，`Laboratory` 找最后实验室日期。 |
| Round 2 | explore_schema | 查看 `Patient` | 关键字段是 `Diagnosis`、`Birthday`、带空格的 `First Date`。 |
| Round 3 | explore_schema | 查看 `Laboratory` | 找到实验室日期 `Date`，应按同一患者取最大/最新日期。 |
| Round 4 | explore_schema | 查看 `Examination` | 本题不需要该表，探索有冗余。 |
| Round 5 | null | 输出格式不合协议 | 没有有效工具调用。 |
| Round 6 | explore_schema | 查看 `Laboratory` 外键 | 确认 `Laboratory.ID -> Patient.ID`。 |
| Round 7 | explore_schema | 查看一行 `Patient` 样例 | 暴露 `First Date` 是带空格列名，需要引用。 |
| Round 8 | null | 再次格式不合协议 | 没有有效工具调用。 |
| Round 9 | generate_sql | 用 `WITH patient_info` 组织正确意图 | 工具只允许以 SELECT/PRAGMA/EXPLAIN 开头，拒绝 `WITH`。 |
| Round 10 | generate_sql | 改成 SELECT，但写成 `p.First Date` 并按 `age_at_arrival ASC` | 未引用 `First Date` 导致语法错；语义上也应按 `Birthday ASC` 找最老患者，且 gold 只要日期和年龄两列。 |""",
    "1169": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要 `Patient` 的性别和 `Laboratory` 的 UA。 |
| Round 2 | explore_schema | 查看三张表建表 SQL | 已有 `Patient.ID/SEX` 与 `Laboratory.ID/UA`。 |
| Round 3 | explore_schema | 一次提交三张表样例查询 | 工具拒绝多语句。 |
| Round 4 | explore_schema | 单独查看 `Patient` 样例 | 确认性别编码为 `M/F`。 |
| Round 5 | explore_schema | 单独查看 `Laboratory` 样例 | 确认 UA 存在并且同一患者可有多条实验室记录。 |
| Round 6 | propose_schema | 提出 `Patient` join `Laboratory` | 表路径正确，但没有强调患者级去重。 |
| Round 7 | generate_sql | 用 `SUM(CASE...)` 直接按实验室行计数 | 算成 1807/8786 条记录，而 gold 要 46/250 个 distinct patient；还多输出分子分母。 |
| Round 8 | confirm_answer | 确认行粒度统计 SQL | 最终错在“检验记录粒度”替代“患者粒度”。 |""",
    "1175": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要 `Laboratory.HGB` 与 `Patient.Birthday/Diagnosis`。 |
| Round 2 | explore_schema | 查看三张表建表 SQL | 表路径足够：`Laboratory.ID = Patient.ID`。 |
| Round 3 | propose_schema | schema JSON 格式不合法 | 阶段切换失败，但不影响后续直接生成 SQL。 |
| Round 4 | generate_sql | 按 HGB 降序找最高值并算年龄 | 使用 SQLite 不支持的 `? :` 条件表达式，语法错。 |
| Round 5 | generate_sql | 改成 `CASE WHEN`，定位最高 HGB 患者 | 患者、诊断和年龄都正确，但输出了 `ID/Date/HGB/age` 五列。 |
| Round 6 | confirm_answer | 确认五列 SQL | gold 只要 `(age, Diagnosis)`，这是纯输出形状错误。 |""",
    "1179": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要 `Patient` 通过诊断日期定位患者，`Examination` 取 aCL IgM。 |
| Round 2 | explore_schema | 查看 `Patient` | 找到 `Description` 可对应题目里的诊断日期。 |
| Round 3 | explore_schema | 查看 `Laboratory` | 与本题无关，探索多了一张表。 |
| Round 4 | explore_schema | 查看 `Examination` | 看到真实字段名是带空格的 `aCL IgM` 和 `Examination Date`。 |
| Round 5 | explore_schema | 再看 `Patient` 建表 SQL | 确认 `Description`/`Diagnosis`。 |
| Round 6 | explore_schema | 再看 `Examination` 建表 SQL | 再次暴露 `aCL IgM` 需要引用。 |
| Round 7 | propose_schema | 提出三表候选 | 表包含多余 `Laboratory`，但核心 join 思路可用。 |
| Round 8 | generate_sql | 用 `e.aCL_IgM` 查询 | 字段名写成下划线版本，报 no such column。 |
| Round 9 | generate_sql | 改成 ``e.`aCL IgM``` | 数值 4.1 正确，但把日期、Description、Diagnosis 也输出了。 |
| Round 10 | confirm_answer | 确认四列 SQL | gold 只要 `aCL IgM` 单列，因此 EX 失败。 |""",
    "1185": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要 `Patient.Birthday` 定位患者，`Laboratory.T-CHO/Date` 算 1981 年 11 到 12 月下降率。 |
| Round 2 | explore_schema | 查看 `Patient` | 找到生日字段，但后续 SQL 没有真正 join 回患者。 |
| Round 3 | explore_schema | 查看 `Laboratory` | 看到 `T-CHO` 是带连字符字段，必须引用。 |
| Round 4 | explore_schema | 查看 `Examination` | 与本题无关。 |
| Round 5 | propose_schema | 提出三表 schema | 仍未把计算公式具体落到 `Patient JOIN Laboratory`。 |
| Round 6 | generate_sql | 输出缺少 tool_call | 没有执行任何 SQL。 |
| Round 7 | generate_sql | 尝试用 `T-CHO` 计算下降率 | 未引用 `T-CHO`，SQLite 解析成 `T - CHO`，报 no such column。 |
| Round 8 | generate_sql | 重复同一个未引用 `T-CHO` 的 SQL | 同样报错，没有修复字段引用。 |
| Round 9 | generate_sql | 退回查看 1981-11 的实验室样例 | 已偏离答案计算，只是探索记录。 |
| Round 10 | generate_sql | 把 `SELECT * FROM Laboratory WHERE Date LIKE '1981-11-%' LIMIT 1` 当最终 | 完全没有按生日筛患者，也没有计算 11/12 月 `T-CHO` 下降率。 |""",
    "1187": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 题目实际只需 `Laboratory` 的 `Date/GPT/ALB/ID`。 |
| Round 2 | explore_schema | 查看 `Examination` | 被 “examined between” 误导到医学检查表。 |
| Round 3 | explore_schema | 查看 `Patient` | 本题不需要患者属性。 |
| Round 4 | explore_schema | 查看 `Laboratory` | 已经看到正确日期字段 `Laboratory.Date`。 |
| Round 5 | explore_schema | 查看 `Examination` 外键 | 继续强化了错误的 Examination 路径。 |
| Round 6 | propose_schema | schema 格式缺失 | 没有成功记录候选 schema。 |
| Round 7 | explore_schema | 查看 `Laboratory` 外键 | 知道 `Laboratory` 可 join Patient，但不需要 join Examination。 |
| Round 8 | propose_schema | schema 格式再次缺失 | 仍无有效 schema。 |
| Round 9 | propose_schema | 第三次 schema 格式失败 | 接近轮数上限，被迫生成 SQL。 |
| Round 10 | generate_sql | 同时 join `Examination` 和 `Laboratory`，日期过滤用 `e.\"Examination Date\"` | gold 日期应来自实验室 `l.Date`，错误日期表把 50 个 ID 压成 2 个。 |""",
    "1192": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要门诊患者和 1991-10 的实验室 T-BIL。 |
| Round 2 | explore_schema | 查看 `Patient` | 找到 `Admission`，门诊对应 `'-'`。 |
| Round 3 | explore_schema | 查看 `Laboratory` | 看到总胆红素字段实际名为带连字符的 `T-BIL`。 |
| Round 4 | explore_schema | 查看 `Examination` | 本题不需要。 |
| Round 5 | propose_schema | schema 格式缺失 | 没有有效 schema。 |
| Round 6 | explore_schema | 查看 `Laboratory` 外键 | join 路径清楚。 |
| Round 7 | propose_schema | 提出 `Patient` + `Laboratory` | 表路径正确。 |
| Round 8 | generate_sql | 输出多列并把 `First Date`/`T-BIL` 写成 `First_Date`/`T_BIL` | 先因 `p.First_Date` 报错。 |
| Round 9 | generate_sql | 改成 `p.First Date` 但仍未引用 | 报 `no such column: p.First`。 |
| Round 10 | generate_sql | 引用了 `First Date`，但仍把 `T-BIL` 写成 `l.T_BIL` | 最终报 no such column；即使修字段，也应只输出 distinct ID。 |""",
    "1205": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要患者 57266 的性别和所有 UA 记录。 |
| Round 2 | explore_schema | 查看 `Patient` | 找到 `SEX`，用于男女不同 UA 阈值。 |
| Round 3 | explore_schema | 查看 `Laboratory` | 找到 `UA`，且一名患者有多条 lab 记录。 |
| Round 4 | explore_schema | 查看 `Examination` | 与本题无关。 |
| Round 5 | propose_schema | 提出三表 schema | 多包含了 `Examination`，但后续 SQL 未使用。 |
| Round 6 | generate_sql | 对每条 UA 记录输出 true/false，同时带出 ID/SEX/UA | true/false 序列正确，额外三列导致列数不一致。 |
| Round 7 | confirm_answer | 确认四列 SQL | gold 只要每条 lab result 的 `'true'/'false'` 单列。 |""",
    "1209": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要 GPT 异常患者的诊断，按生日升序。 |
| Round 2 | explore_schema | 查看三张表建表 SQL | 找到 `Laboratory.GPT` 和 `Patient.Birthday/Diagnosis`。 |
| Round 3 | propose_schema | 提出 `Patient` + `Laboratory` | 表选择正确。 |
| Round 4 | generate_sql | 直接输出每条 `GPT >= 60` 的 lab 行 | 同一患者多条异常 GPT 被重复输出，且多了 ID/Birthday/GPT 三列。 |
| Round 5 | confirm_answer | 确认行级 SQL | gold 要先 distinct patient，再只输出 Diagnosis。 |""",
    "1227": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要男性高胆固醇患者的平均年龄。 |
| Round 2 | explore_schema | 查看 `Patient` | 找到 `SEX/Birthday`。 |
| Round 3 | explore_schema | 查看 `Laboratory` | 找到 `T-CHO`，需要引用带连字符字段。 |
| Round 4 | propose_schema | 提出 `Patient` join `Laboratory` | 表路径正确，但没强调 distinct patient 和整数年龄。 |
| Round 5 | generate_sql | 尝试用 `year()`/自造函数算年龄 | SQLite 不支持，执行失败。 |
| Round 6 | generate_sql | 改成平均 `julianday` 天数差 | 返回的是平均天数 27260，不是年龄。 |
| Round 7 | generate_sql | 把天数除以 365.25 | 得到 74.636，但仍按 lab 行重复加权，且不是 gold 的整数年龄后求平均。 |
| Round 8 | confirm_answer | 确认近似年龄 SQL | gold 是 distinct patient 的整岁平均 71.4。 |""",
    "1231": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要出生年份、性别、CPK 异常。 |
| Round 2 | explore_schema | 查看 `Patient` | 找到 `Birthday/SEX`。 |
| Round 3 | explore_schema | 查看 `Laboratory` | 找到 `CPK`。 |
| Round 4 | explore_schema | 查看 `Patient` 建表 SQL | 再次确认 `Birthday` 是完整日期。 |
| Round 5 | explore_schema | 查看 `Laboratory` 外键 | join 路径正确。 |
| Round 6 | propose_schema | 提出 `Patient` + `Laboratory` | 表路径正确。 |
| Round 7 | generate_sql | 首次 join 用错 `l.Patient_ID` | 报 no such column。 |
| Round 8 | generate_sql | 改成 `l.ID`，但写 `p.Birthday BETWEEN '1936' AND '1956'` | 完整日期字符串不会落在年份字符串区间，返回 0；gold 用 `STRFTIME('%Y', Birthday)` 返回 2。 |
| Round 9 | confirm_answer | 确认 0 的 SQL | 最终错在日期年份抽取方式。 |""",
    "1235": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要低 RBC lab 记录对应患者的 Diagnosis/ID/年龄。 |
| Round 2 | explore_schema | 查看 `Patient` | 找到 `Birthday/Diagnosis`。 |
| Round 3 | explore_schema | 查看 `Laboratory` | 找到 `RBC`。 |
| Round 4 | explore_schema | 查看一行 `Laboratory` | 看到 RBC 是数值，低值阈值可直接比较。 |
| Round 5 | explore_schema | 查看一行 `Patient` | 确认诊断和生日在患者表。 |
| Round 6 | generate_sql | 先用 `julianday` 天数差当 age | SQL 可执行，但年龄是天数，且列序为 ID/Diagnosis/Birthday/age。 |
| Round 7 | generate_sql | 尝试使用不存在的 `SUBTRACT` | 执行失败。 |
| Round 8 | generate_sql | 又回到天数差版本 | 仍不是年龄年数。 |
| Round 9 | generate_sql | 改成 `/365.25`，但多写一个右括号 | 语法错误。 |
| Round 10 | generate_sql | 重复带多余右括号的 SQL | 最终执行失败；此外 gold 列序是 Diagnosis, ID, age。 |""",
    "1239": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要找 HCT 超标至少两次的患者并算当前年龄。 |
| Round 2 | explore_schema | 查看 `Patient` | 找到生日字段。 |
| Round 3 | explore_schema | 查看 `Laboratory` | 找到 `HCT`。 |
| Round 4 | explore_schema | 查看 `Examination` | 与本题无关。 |
| Round 5 | generate_sql | 使用 `year()`/`MMDD()` 自造函数 | SQLite 不支持，失败。 |
| Round 6 | generate_sql | 改用 `strftime` 年份差，但没有生日月日扣减 | 三个患者集合正确；ID 3182521 年龄被算成 74，gold 应按生日未到扣 1 得 73。 |
| Round 7 | confirm_answer | 确认年份差 SQL | 最终只差精确年龄计算。 |""",
    "1241": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要异常血小板患者数的低值/高值差。 |
| Round 2 | explore_schema | 查看 `Examination` | 本题不需要该表。 |
| Round 3 | explore_schema | 查看 `Laboratory` | 找到 `PLT`。 |
| Round 4 | explore_schema | 查看 `Patient` | 患者表只用于语义，实际 distinct `Laboratory.ID` 已足够。 |
| Round 5 | explore_schema | 查看 `Laboratory` 样例 | 看到 PLT 数值。 |
| Round 6 | explore_schema | 查看有 PLT 的 distinct ID | 确认需要患者级去重。 |
| Round 7 | propose_schema | 提出 `Patient` + `Laboratory` | 表路径可用。 |
| Round 8 | generate_sql | 计算 lower_count、higher_count 和 difference | 差值 `-46` 正确，但额外输出了两个中间计数列。 |
| Round 9 | confirm_answer | 确认三列 SQL | gold 只要 difference 单列。 |""",
    "1242": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要 1984 lab、PLT 正常、当前未满 50 岁患者。 |
| Round 2 | explore_schema | 查看 `Laboratory` | 找到 `Date/PLT`。 |
| Round 3 | explore_schema | 查看 `Patient` | 找到 `Birthday`。 |
| Round 4 | explore_schema | 查看 `Examination` | 本题不需要。 |
| Round 5 | propose_schema | 提出 `Laboratory` + `Patient` | 表路径正确。 |
| Round 6 | generate_sql | 用 `YEAR(l.Date)` 过滤 1984 | SQLite 不支持 `YEAR()`，执行失败。 |
| Round 7 | generate_sql | 改用 `strftime('%Y', l.Date)` | 患者集合对，但输出每条 lab 记录的 `ID/Birthday/PLT/Date`，不是 distinct ID。 |
| Round 8 | confirm_answer | 确认四列行级结果 | gold 只要 5 个 distinct patient ID。 |""",
    "1243": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要 `Patient` 年龄/性别和 `Laboratory.PT`。 |
| Round 2 | explore_schema | 查看三张表建表 SQL | 找到 `Birthday/SEX/PT`。 |
| Round 3 | explore_schema | 查看 `Patient` 样例 | 知道年龄需由生日和当前日期计算。 |
| Round 4 | explore_schema | 查看 `Patient` 结构 | 再次确认生日字段。 |
| Round 5 | explore_schema | 一次提交 lab 样例和日期范围多条查询 | 工具拒绝多语句。 |
| Round 6 | explore_schema | 单独查看 `Laboratory` 样例 | 找到 `PT`。 |
| Round 7 | explore_schema | 查询实验室最大日期 | 走向用数据最大日期代替 `now` 的错误方向。 |
| Round 8 | explore_schema | 统计 `PT >= 14` 的记录数 | 只得到 lab 行数 183，没有患者去重和女性比例。 |
| Round 9 | explore_schema | 用 `Birthday + 55*...` 做年龄过滤 | 日期表达式错误，仍只统计记录数。 |
| Round 10 | propose_schema | 最后一轮才提交 schema | 没有进入 generate_sql，最终 `pred_sql` 为空。 |""",
    "1252": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要正常 IGG 且有 Symptoms 的患者数。 |
| Round 2 | explore_schema | 查看 `Laboratory` | 找到 `IGG`。 |
| Round 3 | explore_schema | 查看 `Patient` | 本题计患者数，需要患者 ID 去重。 |
| Round 4 | explore_schema | 查看 `Examination` | 找到 `Symptoms`，join 键也是 `ID`。 |
| Round 5 | explore_schema | 查看一行 `Laboratory` | 看到 IGG 列和样例值。 |
| Round 6 | explore_schema | 查看 `Laboratory` 外键 | 明确 `Laboratory.ID -> Patient.ID`。 |
| Round 7 | propose_schema | 提出三表 schema | 表选择正确。 |
| Round 8 | generate_sql | 生成 `L.ID = E.Patient.ID` | join 键写成不存在的 `E.Patient.ID`，执行报错。 |
| Round 9 | explore_schema | 又查看 `Laboratory` 样例 | 已偏离修复 join。 |
| Round 10 | explore_schema | 查看 `Examination` 样例 | 能看到 `E.ID`，但没有回到 generate_sql；最终还是 join 字段错误。 |""",
    "1255": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要异常 IgM 患者的最常见诊断。 |
| Round 2 | explore_schema | 查看 `Laboratory` | 找到 `IGM`。 |
| Round 3 | explore_schema | 查看 `Patient` | 找到 `Diagnosis`。 |
| Round 4 | propose_schema | 提出 `Laboratory` join `Patient` | 表路径正确，但没有患者去重。 |
| Round 5 | generate_sql | 按 lab 行统计诊断出现次数 | 得到 `RA, 36`；gold 要先 distinct patient，再按 Diagnosis 计数，结果是 `SLE`。 |
| Round 6 | confirm_answer | 确认行级 count SQL | 同一患者多条异常 IGM 记录把诊断频次放大。 |""",
    "1256": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要 CRP 异常且 `Patient.Description IS NULL` 的患者数。 |
| Round 2 | explore_schema | 查看三张表建表 SQL | 找到 `CRP` 和 `Description`。 |
| Round 3 | explore_schema | 查看 `Patient` | 确认 `Description` 可以为空。 |
| Round 4 | generate_sql | 使用 `COUNT(*)` 统计 join 后 lab 行 | 返回 208；gold 是 distinct patient，只有 25。 |
| Round 5 | confirm_answer | 确认行数统计 SQL | 错在把多条 CRP 记录当多名患者。 |""",
    "1257": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要 CRE 异常且当前未满 70 岁患者数。 |
| Round 2 | explore_schema | 查看 `Examination` | 本题不需要。 |
| Round 3 | explore_schema | 查看 `Patient` | 找到 `Birthday`。 |
| Round 4 | explore_schema | 查看 `Laboratory` | 找到 `CRE`。 |
| Round 5 | generate_sql | 写成 `date('now', '+70 years') > p.Birthday` 并 `COUNT(*)` | 条件几乎覆盖历史生日，且按 lab 行计数，返回 361；gold 要 `date(Birthday,'+70 years') > date('now')` 和 distinct patient。 |
| Round 6 | confirm_answer | 确认错误年龄方向 SQL | 年龄条件方向和粒度都错。 |""",
    "1265": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要正常 RNP 且住院患者数。 |
| Round 2 | explore_schema | 查看 `Examination` | 本题不需要。 |
| Round 3 | explore_schema | 查看 `Laboratory` | 找到 `RNP`。 |
| Round 4 | explore_schema | 查看 `Patient` | 找到 `Admission`。 |
| Round 5 | propose_schema | schema JSON 格式错误 | 没有成功记录 schema。 |
| Round 6 | explore_schema | 查询 `Admission` 取值 | 看到住院用 `'+'`。 |
| Round 7 | explore_schema | 查询 `RNP` 所有取值 | 关键证据已出现：正常相关取值包括 `'0'` 和 `'negative'`，并没有 `'-'`/`'+-'`。 |
| Round 8 | explore_schema | 只检查 `('-', '+-', 'negative')` | 只查到 `negative`，但模型没有意识到漏掉 `'0'`。 |
| Round 9 | generate_sql | 用 `RNP IN ('-', '+-', 'negative')` 计数 | 返回 7；gold 用 `('negative','0')` 返回 35。 |
| Round 10 | confirm_answer | 确认漏掉 `'0'` 的 SQL | 根因是正常值编码理解错。 |""",
    "1267": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要正常 SM 患者，并判断是否没有 thrombosis。 |
| Round 2 | explore_schema | 查看三张表建表 SQL | 找到 `Laboratory.SM` 和 `Examination.Thrombosis`。 |
| Round 3 | explore_schema | 查看 `Laboratory` | 只确认列存在，没有核查 SM 的真实取值。 |
| Round 4 | propose_schema | 提出三表 schema | 表路径大体正确，但没有解决正常 SM 编码和患者级 no-thrombosis。 |
| Round 5 | confirm_answer | 直接确认 `SM IN ('-', '+-') AND e.Thrombosis = 0` | 正常值应是 `negative/0`；且要按患者聚合确认没有任何 thrombosis，不能只找某一行 `Thrombosis=0`。 |""",
    "1270": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要女性、正常 SC170、且没有任何症状。 |
| Round 2 | explore_schema | 查看 `Patient` | 找到 `SEX`。 |
| Round 3 | explore_schema | 查看 `Laboratory` | 找到 `SC170`。 |
| Round 4 | explore_schema | 查看 `Examination` | 找到 `Symptoms`。 |
| Round 5 | explore_schema | 查看 `Laboratory` 外键 | join 路径清楚。 |
| Round 6 | explore_schema | 查看 `Examination` 外键 | 知道症状记录按患者关联。 |
| Round 7 | propose_schema | schema 格式缺失 | 没有有效 schema。 |
| Round 8 | propose_schema | 提出三表 schema | 表路径正确。 |
| Round 9 | generate_sql | inner join `Examination` 并过滤 `e.Symptoms IS NULL` | 只保留“至少有一条 NULL 症状检查记录”的患者；gold 要 `NOT EXISTS` 任一非空症状，也包括没有检查记录的患者。 |
| Round 10 | confirm_answer | 确认 inner join 版本 | 因 no-symptom 语义错，结果从 19 降为 2。 |""",
    "1281": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要 GOT 异常患者中最年轻者的生日。 |
| Round 2 | explore_schema | 查看 `Laboratory` | 找到 `GOT`。 |
| Round 3 | explore_schema | 查看 `Patient` | 找到 `Birthday`。 |
| Round 4 | explore_schema | 查看 `Laboratory` 结构 | 再次确认 `ID/GOT`。 |
| Round 5 | generate_sql | 用 `MIN(P.Birthday)` 取“youngest” | 日期越小代表越早出生、年龄越大；返回最老患者 `1922-12-01`。 |
| Round 6 | confirm_answer | 确认 `MIN(Birthday)` SQL | gold 应 `ORDER BY Birthday DESC LIMIT 1`，返回 `1987-12-05`。 |""",
}


def replace_table(text: str, qid: str, table: str) -> str:
    header = re.search(rf"^## qid{re.escape(qid)}\b", text, re.M)
    if not header:
        raise SystemExit(f"Missing qid section: {qid}")
    next_section = re.search(r"^## qid\d+\b|^## 错误类型归纳|^## 对后续改进", text[header.end():], re.M)
    section_end = header.end() + next_section.start() if next_section else len(text)
    section = text[header.end():section_end]
    table_start = section.find("### 运行轨迹")
    if table_start == -1:
        raise SystemExit(f"Missing trajectory table: {qid}")
    abs_start = header.end() + table_start
    after = re.search(r"\n(?=## qid\d+\b|## 错误类型归纳|## 对后续改进)", text[abs_start:], re.M)
    abs_end = abs_start + after.start() if after else section_end
    return text[:abs_start] + table.rstrip() + "\n" + text[abs_end:]


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")
    for qid, table in TABLES.items():
        text = replace_table(text, qid, table)
    TARGET.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
