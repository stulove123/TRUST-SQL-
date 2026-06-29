#!/usr/bin/env python3
"""Apply hand-written, root-cause-oriented trajectory tables for european_football_2."""

from __future__ import annotations

import re
from pathlib import Path


TARGET = Path("/root/autodl-tmp/text_to_sql_benchmarks/results/qwen35-4b-arcwise-plat-trustsql-full-final-thinking/european_football_2_wrong_analysis.md")


TABLES = {
    "1028": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 相关表是 `Match`、`Team`、`League`。 |
| Round 2 | explore_schema | 查看 `Team` 建表 SQL | 找到 `team_api_id` 和 `team_long_name`。 |
| Round 3 | explore_schema | 查看 `Match` 建表 SQL | 找到 `league_id`、`season`、`away_team_api_id`、主客队进球。 |
| Round 4 | explore_schema | 查看 `League` 建表 SQL | 找到 league name。 |
| Round 5 | explore_schema | 查询 Scotland Premier League | 得到 league_id=19694。 |
| Round 6 | generate_sql | 按 away win 数排序，`ORDER BY win_count DESC LIMIT 1` | 找到 `Celtic=11`，但最高 away wins 有 `Celtic` 和 `Rangers` 并列；还多输出 `win_count`。 |
| Round 7 | confirm_answer | 确认 LIMIT 1 版本 | gold 用 max-count 子查询保留所有并列第一，只输出 team name。 |""",
    "1029": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `Team_Attributes`，可选 join `Team`。 |
| Round 2 | explore_schema | 查看 `Team_Attributes` 建表 SQL | 找到 `team_api_id`、`date`、`buildUpPlaySpeed`。 |
| Round 3 | explore_schema | 查看 `Team` 建表 SQL | 用于 team name，但 gold 不需要输出 team。 |
| Round 4 | explore_schema | 查看 `Team_Attributes` 字段 | 确认 latest record 可按每队 `MAX(date)`。 |
| Round 5 | explore_schema | 查看 `Match` | 本题不需要比赛表。 |
| Round 6 | propose_schema | 提出 Team_Attributes + Team | latest-record 思路正确。 |
| Round 7 | generate_sql | 对每队取最新记录，按 `buildUpPlaySpeed` 降序取 4 | 四个 speed 值正确为 80/77/73/71，但额外输出 team name、short name、date。 |
| Round 8 | confirm_answer | 确认四列输出版本 | gold 只要 `buildUpPlaySpeed` 一列；失败来自输出形状。 |""",
    "1031": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `Player` 与 `Player_Attributes`。 |
| Round 2 | explore_schema | 查看两表建表 SQL | 已看到 `birthday`、`sprint_speed`、属性 `date`。 |
| Round 3 | propose_schema | 提出 Player-Attributes join | 表关系正确。 |
| Round 4 | generate_sql | 过滤 2013-2015 且 `sprint_speed>=97`，输出 player/date/速度/年龄 | 命中 23 条都是 Mathis Bolly 的属性记录；未去重，且输出多列。年龄只做年份差，算成 36。 |
| Round 5 | confirm_answer | 确认记录级明细 SQL | gold 只要 distinct 精确年龄；生日 1990-11-14 在当前日期尚未到，年龄应为 35。 |""",
    "1032": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `League` 与 `Match`。 |
| Round 2 | explore_schema | 查看 `League` 建表 SQL | 找到 league name。 |
| Round 3 | explore_schema | 查看 `Match` 建表 SQL | 找到 `league_id`。 |
| Round 4 | propose_schema | 提出 League-Match 计数 | 计数方向正确。 |
| Round 5 | generate_sql | 按 league 计数后 `ORDER BY count DESC LIMIT 1` | 得到 `Spain LIGA BBVA=3040`，但还有 England/France 同为 3040。 |
| Round 6 | confirm_answer | 确认 LIMIT 1 版本 | gold 返回所有并列最高的 3 个 league。 |""",
    "1037": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `Player` 与 `Player_Attributes`。 |
| Round 2 | explore_schema | 查看 `Player` 字段 | 找到 `birthday` 与 player ids。 |
| Round 3 | explore_schema | 查看 `Player_Attributes` 字段 | 找到 `preferred_foot`。 |
| Round 4 | explore_schema | 查看生日样例 | 确认生日格式含时间，可按年份/日期过滤。 |
| Round 5 | explore_schema | 误在 `Player_Attributes` 中直接引用 `birthday` | 报 `no such column: birthday`，随后意识到要 join Player。 |
| Round 6 | generate_sql | 统计 born 1987-1992 且 left 的 distinct players | 得到分子 1237，其实这是正确分子。 |
| Round 7 | generate_sql | 改查 left 属性记录数 | 得到 19272，开始把实体口径混成记录口径。 |
| Round 8 | generate_sql | 统计 born 1987-1992 的 distinct players | 得到分母 4285，这也是正确分母。 |
| Round 9 | generate_sql | 最终却用 `SUM(left records)/COUNT(records)` 并 `ROUND(...,2)` | 得到 24.56；gold 是 distinct player 口径 `1237/4285*100=28.868...`。 |
| Round 10 | null | 输出格式无有效 action | 没有修正最终 SQL。 |""",
    "1040": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `Player` 与 `Player_Attributes`。 |
| Round 2 | explore_schema | 查看 `Player` 字段 | 找到 `height`、`player_name`。 |
| Round 3 | explore_schema | 查看 `Player_Attributes` 字段 | 找到 `heading_accuracy`。 |
| Round 4 | propose_schema | 提出按球员平均 heading accuracy 排序 | 核心逻辑正确。 |
| Round 5 | generate_sql | 过滤身高 >180，按 AVG heading accuracy desc 取 top 10 | top10 球员集合正确，但多输出 `avg_heading_accuracy`。 |
| Round 6 | confirm_answer | 确认两列输出版本 | gold 只返回 player name；EX 因列数不一致失败。 |""",
    "1044": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 只需要 `Player`。 |
| Round 2 | explore_schema | 查看 `Player` 字段 | 找到 `player_name`、`birthday`。 |
| Round 3 | propose_schema | 提出按 birthday 年月过滤 | 过滤方向正确。 |
| Round 4 | generate_sql | 筛 `1970` 年 `10` 月出生的球员 | 四个球员都找对了，但额外输出 `birthday`。 |
| Round 5 | confirm_answer | 确认两列输出版本 | gold 只要 player name。 |""",
    "1076": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `Player` 与 `Player_Attributes`。 |
| Round 2 | explore_schema | 查看 `Player_Attributes` 字段 | 找到 `ball_control`。 |
| Round 3 | explore_schema | 查看 `Player` 字段 | 找到 `player_name` 和 `player_api_id`。 |
| Round 4 | propose_schema | 提出两名球员的平均 ball control 差 | 语义方向正确。 |
| Round 5 | generate_sql | 首次尝试两人平均值差 | 分组/连接写法导致两行差值 0。 |
| Round 6 | generate_sql | 调整分组但仍返回两行中间平均 | 还没有得到单个差值。 |
| Round 7 | generate_sql | 用两个子查询分别算平均，再相减 | 差值 0.8 正确，但输出了 `abdou_avg`、`aaron_avg`、`difference` 三列。 |
| Round 8 | confirm_answer | 确认三列输出版本 | gold 只要最终 difference 一列。 |""",
    "1078": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 只需要 `Player`。 |
| Round 2 | explore_schema | 查看 `Player` 字段 | 找到 `birthday`。 |
| Round 3 | explore_schema | 查询 Aaron Lennon 和 Abdelaziz Barrada 的生日 | 两人生日都查到，但只是列出明细。 |
| Round 4 | confirm_answer | 确认列出两人生日的 SQL | 没有执行“older = birthday 更早”并 `LIMIT 1`；gold 只返回 `Aaron Lennon`。 |""",
    "1079": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 只需要 `Player`。 |
| Round 2 | explore_schema | 查看 `Player` 字段 | 找到 `height` 与 `player_name`。 |
| Round 3 | generate_sql | 按 height desc 取最高 | 正确定位 `Kristof van Hout`，但多输出 height。 |
| Round 4 | confirm_answer | 确认两列输出版本 | gold 只要 player name。 |""",
    "1092": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `League` 与 `Match`。 |
| Round 2 | explore_schema | 查看 `League` 建表 SQL | 找到 league name。 |
| Round 3 | explore_schema | 查看 `Match` 建表 SQL | 找到 `season`、`league_id`。 |
| Round 4 | propose_schema | 提出 2008/2009 按 league 计数 | 计数方向正确。 |
| Round 5 | generate_sql | 按 match_count 降序 `LIMIT 1` | 得到 Spain=380，但 England/France/Italy/Spain 都是 380；还多输出 count。 |
| Round 6 | confirm_answer | 确认 LIMIT 1 版本 | gold 返回所有并列最多的 4 个 league name。 |""",
    "1094": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `Player` 与 `Player_Attributes`。 |
| Round 2 | explore_schema | 查看 `Player_Attributes` 字段 | 找到 `overall_rating` 与 `date`。 |
| Round 3 | explore_schema | 查看 `Player` 字段 | 找到 `player_name` 与 join key。 |
| Round 4 | explore_schema | 查询两名球员最新日期 | 已得到 Ariel=2016-03-24、Paulin=2016-05-12。 |
| Round 5 | generate_sql | 试图按姓名/date 排序取 2 行 | 只取到 Ariel 的两条记录，未分组取每人最新。 |
| Round 6 | generate_sql | 用相关子查询取最新记录 | 写成 `pa2.player_name`，报列不存在。 |
| Round 7 | generate_sql | 用窗口函数取每人最新 rating | 正确拿到 Ariel=68、Paulin=59。 |
| Round 8 | generate_sql | 计算百分比 | SQL 少括号，实际执行为 `68 - 59*100/59 = -32`，而不是 `(68-59)*100/59`。 |
| Round 9 | generate_sql | 尝试 WITH 改写 | 工具拒绝 `WITH` 开头，而且公式仍缺括号。 |
| Round 10 | generate_sql | 回到无 WITH 版本 | 仍是缺括号公式，返回 -32.0；gold 为 15.254237...。 |""",
    "1110": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `Team` 与 `Team_Attributes`。 |
| Round 2 | explore_schema | 查看 `Team` 字段 | 找到 `team_api_id`、`team_long_name`。 |
| Round 3 | explore_schema | 查看 `Team_Attributes` 字段 | 找到 `buildUpPlayPassingClass` 与 `date`。 |
| Round 4 | explore_schema | 又查看 `Match` 字段 | 这里开始把属性日期误导到比赛表。 |
| Round 5 | explore_schema | 查询 FC Lorient 的 team_api_id | 得到 8689，定位正确。 |
| Round 6 | generate_sql | 从 Team_Attributes 查 `2010-02-22%` 的 passing class，但还错误 join Match | 实际已经返回 `Long`，但由于 join/重复行不干净，没有收敛成正确一行。 |
| Round 7 | generate_sql | 转去 Match 表查 FC Lorient 当天比赛 | 返回空，说明路由错表。 |
| Round 8 | generate_sql | 只查 Match 中是否有该日期 | 返回日期 `2010-02-22 00:00:00`，与问题目标无关。 |
| Round 9 | generate_sql | 再查 FC Lorient 当天 Match | 仍为空。 |
| Round 10 | generate_sql | 最终退化成 `SELECT DISTINCT date FROM Match ...` | 返回的是日期，不是 `buildUpPlayPassingClass='Long'`；根因是忽略 Team_Attributes 才是目标表。 |""",
    "1114": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `Player` 与 `Player_Attributes`。 |
| Round 2 | explore_schema | 查看 `Player` 建表 SQL | 找到 player name 与 join key。 |
| Round 3 | explore_schema | 查看 `Player_Attributes` 建表 SQL | 找到 `overall_rating` 与带时间的 `date`。 |
| Round 4 | generate_sql | 直接 `pa.date BETWEEN '2007-02-22' AND '2016-04-21'` | 漏掉 `2016-04-21 00:00:00` 这类结束日记录，平均值变成 75.28125。 |
| Round 5 | confirm_answer | 确认 raw date BETWEEN 版本 | gold 用 `SUBSTR(date,1,10)`，包含结束日，平均为 75.393939...。 |""",
    "1115": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `Player` 与 `Player_Attributes`。 |
| Round 2 | explore_schema | 查看 `Player` 字段 | 找到 player ids。 |
| Round 3 | explore_schema | 查看 `Player_Attributes` 字段 | 已看到 `overall_rating` 和 `date`，其实足够回答。 |
| Round 4 | explore_schema | 查看 `Match` 字段 | 错误把题目日期解释成比赛日期。 |
| Round 5 | explore_schema | 用 `2013/7/12` 查 Match | 查不到。 |
| Round 6 | explore_schema | 查看 Match 日期格式 | 确认是 `YYYY-MM-DD HH:MM:SS`。 |
| Round 7 | explore_schema | 用 `2013-07-12 00:00:00` 查 Match | 仍查不到。 |
| Round 8 | explore_schema | 查 2013 年 7 月附近 Match 日期 | 找到 7/13 等比赛日期，但这与属性评分日期无关。 |
| Round 9 | explore_schema | 再查 2013-07-12 Match | 仍为空。 |
| Round 10 | explore_schema | 回到 Player 查两人 player_api_id | 找到两人，但已耗尽轮数；没有生成用 Player_Attributes.date 的最终 SQL。 |""",
    "1136": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 只需 `Player_Attributes`。 |
| Round 2 | explore_schema | 查看 `Player_Attributes` 字段 | 找到 `crossing`、`preferred_foot`、`player_api_id`。 |
| Round 3 | explore_schema | 查看 `Player` 字段 | 本题不需要姓名，但确认玩家 id 存在。 |
| Round 4 | generate_sql | 统计 left-foot 且 crossing 为 left-foot max 的记录数 | 返回 3；这是属性记录数，不是玩家数。 |
| Round 5 | confirm_answer | 确认 `COUNT(*)` 版本 | gold 要 `COUNT(DISTINCT player_api_id)`，同一玩家多条最高 crossing 记录不能重复计。 |""",
    "1144": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `Player` 与 `Player_Attributes`。 |
| Round 2 | explore_schema | 查看 `Player` 字段 | 找到 `weight` 与 player ids。 |
| Round 3 | explore_schema | 查看 `Player_Attributes` 字段 | 找到 `finishing`、`curve`。 |
| Round 4 | propose_schema | 提出最高体重球员的所有属性记录 | 记录集合方向正确。 |
| Round 5 | generate_sql | 取最高 weight 球员的 finishing/curve，并额外输出 player_name/weight | 38 条记录集合正确，但多了两列。 |
| Round 6 | confirm_answer | 确认四列输出版本 | gold 只要 `(finishing, curve)`。 |""",
    "1145": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `League` 与 `Match`。 |
| Round 2 | explore_schema | 查看 `League` 建表 SQL | 找到 league name。 |
| Round 3 | explore_schema | 查看 `Match` 建表 SQL | 找到 `season` 与 `league_id`。 |
| Round 4 | propose_schema | 提出按 2015/2016 计数 top 4 | 语义方向正确。 |
| Round 5 | generate_sql | 按 league 计数并取 top 4 | 四个 league name 集合正确，但多输出 `game_count=380`。 |
| Round 6 | confirm_answer | 确认两列输出版本 | gold 只返回 league name；行顺序不敏感，失败点是列数。 |""",
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
