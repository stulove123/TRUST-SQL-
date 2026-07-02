#!/usr/bin/env python3
"""Apply hand-written, root-cause-oriented trajectory tables for superhero."""

from __future__ import annotations

import re
from pathlib import Path


TARGET = Path("/root/autodl-tmp/text_to_sql_benchmarks/results/qwen35-4b-arcwise-plat-trustsql-full-final-thinking/superhero_wrong_analysis.md")


TABLES = {
    "723": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 找到 `superhero`、`colour`、`superpower`、`hero_power`，这些已经覆盖本题。 |
| Round 2 | explore_schema | 查看 `superhero` 字段 | 已看到 `eye_colour_id`，蓝眼睛应从这里 join `colour`。 |
| Round 3 | explore_schema | 查看 `colour` 字段 | 确认颜色表是 `colour(id, colour)`。 |
| Round 4 | explore_schema | 查看 `superpower` 字段 | 确认超能力名在 `superpower.power_name`。 |
| Round 5 | explore_schema | 转去查 `hero_attribute` | 开始偏离：`Agility` 是 superpower，不是 attribute 数值。 |
| Round 6 | explore_schema | 重复查 `hero_attribute` | 没有新增信息，浪费一轮。 |
| Round 7 | explore_schema | 再次重复查 `hero_attribute` | 仍未使用已经看到的 `hero_power` 表。 |
| Round 8 | explore_schema | 查看 `attribute` 字段 | 继续沿 attribute 方向绕路，与本题无关。 |
| Round 9 | explore_schema | 终于查看 `hero_power` 字段 | 此时正确链路已齐：`superhero -> hero_power -> superpower` 和 `superhero -> colour`。 |
| Round 10 | explore_schema | 只查询 `colour='Blue'` 的 id | 查到 Blue id=7，但已耗尽最大轮数；没有生成 count SQL。 |""",
    "726": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 相关表是 `superhero` 和 `publisher`。 |
| Round 2 | explore_schema | 查看 `superhero` 建表 SQL | 已看到 `publisher_id` 和 `height_cm`。 |
| Round 3 | explore_schema | 查看 `publisher` 建表 SQL | 已看到 `publisher_name`。 |
| Round 4 | propose_schema | 提出 join `superhero.publisher_id = publisher.id` | join 方向正确。 |
| Round 5 | generate_sql | 生成 Marvel 英雄按 `height_cm DESC` 排序 SQL | 漏掉 `height_cm != 0`，把 39 个缺失身高的 0 也算入；还多输出了 `height_cm`。 |
| Round 6 | confirm_answer | 确认 Round 5 SQL | 根因没有被修正：gold 只输出 `superhero_name`，并要求排除 `NULL` 和 `0` 两类缺失身高。 |""",
    "728": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `superhero`、`colour`、`publisher`。 |
| Round 2 | explore_schema | 查看 `superhero` 建表 SQL | 已看到 `eye_colour_id` 与 `publisher_id`。 |
| Round 3 | explore_schema | 查看 `colour` 建表 SQL | 确认 eye color 名称来自 `colour.colour`。 |
| Round 4 | explore_schema | 查看 `publisher` 建表 SQL | 确认可按 `publisher_name='Marvel Comics'` 过滤。 |
| Round 5 | propose_schema | 提出三表 join 和按眼睛颜色聚合 | schema 与聚合方向正确。 |
| Round 6 | generate_sql | 按颜色 count，并用 `ROW_NUMBER()` 排名 | count 全对，但排名函数错；并列 count=2 的 `Purple/Gold` 被排成 11/12。 |
| Round 7 | confirm_answer | 确认 `ROW_NUMBER()` 版本 | gold 要 `RANK()`：并列同名次，后续名次跳号；因此值不一致。 |""",
    "736": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 题目外部知识已提示 dumbest = 最低 `Intelligence`。 |
| Round 2 | explore_schema | 查看 `hero_attribute` 字段 | 找到 `hero_id`、`attribute_id`、`attribute_value`。 |
| Round 3 | explore_schema | 查看 `hero_attribute` 建表 SQL | 确认它连接 hero 和 attribute。 |
| Round 4 | explore_schema | 查看 `attribute` 建表 SQL | 确认属性名在 `attribute_name`。 |
| Round 5 | explore_schema | 查看 `superhero` 字段 | 找到 `superhero_name`。 |
| Round 6 | explore_schema | 查询 `attribute_name='Intelligence'` | 找到 Intelligence id=1。 |
| Round 7 | propose_schema | 提出 `superhero`、`hero_attribute`、`attribute` 三表方案 | 关系正确，但尚未处理并列最低值。 |
| Round 8 | confirm_answer | 确认按 Intelligence 升序 `LIMIT 1` 的 SQL | 只返回 `Ammo`，漏掉同为最低 35 的 `Ando Masahashi`、`Jack-Jack`；还多输出 full_name/attribute/value。 |""",
    "738": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `superhero`、`hero_attribute`、`attribute`。 |
| Round 2 | explore_schema | 查看 `superhero` 字段 | 找到 `id`、`superhero_name`、`full_name`。 |
| Round 3 | explore_schema | 查看 `hero_attribute` 字段 | 找到 `hero_id`、`attribute_id`、`attribute_value`。 |
| Round 4 | explore_schema | 查看 `hero_attribute` 建表 SQL | 确认外键关系。 |
| Round 5 | explore_schema | 查看 `attribute` 建表 SQL | 确认属性名表。 |
| Round 6 | explore_schema | 查询 `attribute_name='Durability'` | 找到 Durability id=4。 |
| Round 7 | propose_schema | 提出三表 join 并过滤 durability < 50 | 语义方向正确。 |
| Round 8 | generate_sql | 生成 SQL，返回 `superhero_name, full_name, attribute_value` | 371 个英雄集合正确，但 gold 只要 `superhero_name`。 |
| Round 9 | confirm_answer | 确认多列输出版本 | 根因是输出形状错，不是筛选错。 |""",
    "744": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `superhero` 与 `publisher`。 |
| Round 2 | explore_schema | 查看 `publisher` 建表 SQL | 确认 `publisher_name`。 |
| Round 3 | explore_schema | 查看 `superhero` 建表 SQL | 确认 `publisher_id` 外键。 |
| Round 4 | explore_schema | 查询 DC/Marvel 的 publisher id | 得到 DC=4、Marvel=13。 |
| Round 5 | generate_sql | 一行中输出 DC count、Marvel count、`DC-Marvel` | 算出 224 和 387，但差值方向是 `-163`，且没有输出“更多的是 Marvel Comics”。 |
| Round 6 | confirm_answer | 文本里意识到 Marvel 更多，但最终仍确认原 SQL | gold 要 `(Marvel Comics, 163)`；pred 输出三个中间计数列且差值符号相反。 |""",
    "750": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `superhero` 与 `gender`。 |
| Round 2 | explore_schema | 查看 `superhero` 字段 | 已看到 `gender_id` 和 `weight_kg`。 |
| Round 3 | explore_schema | 查看 `gender` 字段 | 确认可用 `gender='Female'`。 |
| Round 4 | generate_sql | 直接对 female 的 `weight_kg` 求 AVG | 得到 60.78；错误是把 `weight_kg=0` 当成真实体重。 |
| Round 5 | confirm_answer | 确认未过滤缺失体重的 SQL | gold 使用 `weight_kg > 0`，排除 `0` 和 NULL 后平均为 78.5069。 |""",
    "769": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `superhero`、`publisher`、`hero_attribute`、`attribute`。 |
| Round 2 | explore_schema | 查看 `superhero` 建表 SQL | 找到 `superhero_name` 和 `publisher_id`。 |
| Round 3 | explore_schema | 查看 `hero_attribute` 建表 SQL | 找到属性值表。 |
| Round 4 | explore_schema | 查看 `attribute` 建表 SQL | 找到 `attribute_name`。 |
| Round 5 | explore_schema | 查看 `publisher` 建表 SQL | 确认可按 `Dark Horse Comics` 过滤。 |
| Round 6 | explore_schema | 用小写 `attribute_name='durability'` 查询 | 返回空，暴露大小写问题。 |
| Round 7 | explore_schema | 查询全部 attribute | 找到正确值 `Durability`。 |
| Round 8 | propose_schema | 提出四表 join、按 Durability 降序取最高 | 语义方向正确。 |
| Round 9 | generate_sql | 找到 `Dash`，但输出 `superhero_name, max_durability` | 目标英雄正确，额外输出 95。 |
| Round 10 | confirm_answer | 确认带 `max_durability` 的 SQL | gold 只要英雄名；本题失败是输出形状。 |""",
    "775": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `superhero`、`gender`、`colour`。 |
| Round 2 | explore_schema | 查看 `gender` 建表 SQL | 确认 gender 映射表。 |
| Round 3 | explore_schema | 查看 `colour` 建表 SQL | 确认颜色映射表。 |
| Round 4 | explore_schema | 查看 `superhero` 建表 SQL | 关键字段是 `gender_id` 与 `skin_colour_id`，不是 eye colour。 |
| Round 5 | explore_schema | 查询 gender 值 | 确认 Female id=2。 |
| Round 6 | explore_schema | 查询 colour 值 | 确认 Blue id=7。 |
| Round 7 | propose_schema | 提出 female 总数作分母、blue skin female 作分子 | 语义口径正确。 |
| Round 8 | generate_sql | 生成百分比 SQL，但用了 `ROUND(..., 2)` | 返回 2.46；gold 保留 SQLite 原始浮点 2.4630541871921183。 |
| Round 9 | confirm_answer | 确认四舍五入版本 | 本题不是 join 错，而是数值精度不该 round。 |""",
    "788": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `superhero`、`gender`、`publisher`。 |
| Round 2 | explore_schema | 查看 `superhero` 字段 | 找到 `gender_id` 与 `publisher_id`。 |
| Round 3 | explore_schema | 查看 `gender` 建表 SQL | 确认 gender 表。 |
| Round 4 | explore_schema | 查看 `publisher` 建表 SQL | 确认 publisher 表。 |
| Round 5 | explore_schema | 查看 gender 样例 | 确认 Female id=2。 |
| Round 6 | explore_schema | 查看 publisher 样例 | 还没有看到 Marvel，但确认字段。 |
| Round 7 | explore_schema | 搜索 Marvel publisher | 找到 `Marvel Comics` id=13。 |
| Round 8 | propose_schema | 提出 female Marvel 数 / all female 数 | 语义口径正确。 |
| Round 9 | generate_sql | 生成百分比 SQL，但用了 `ROUND(..., 2)` | 返回 54.68；gold 是 54.679802955665025。 |
| Round 10 | confirm_answer | 确认四舍五入版本 | 失败来自精度处理：Arcwise EX 要值完全一致，不能主动保留两位。 |""",
    "791": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 相关表只有 `superhero`。 |
| Round 2 | explore_schema | 查看 `superhero` 字段 | 找到 `height_cm`，但没有检查缺失值编码。 |
| Round 3 | propose_schema | 提出直接 `AVG(height_cm)` | 缺少 `height_cm > 0` 的缺失值过滤。 |
| Round 4 | generate_sql | 执行 `SELECT AVG(height_cm) FROM superhero` | 得到 267.75，被大量 `height_cm=0` 缺失值拉低。 |
| Round 5 | confirm_answer | 确认未过滤版本 | gold 排除 `height_cm <= 0`，正确平均为 345.03538175046555。 |""",
    "794": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `superhero`、`hero_attribute`、`attribute`。 |
| Round 2 | explore_schema | 查看 `superhero` 字段 | 找到 `superhero_name`。 |
| Round 3 | explore_schema | 查看 `hero_attribute` 字段 | 找到 `attribute_value`。 |
| Round 4 | explore_schema | 确认存在 `attribute` 表 | 继续定位 Speed 属性。 |
| Round 5 | explore_schema | 查看 `attribute` 字段 | 找到 `attribute_name`。 |
| Round 6 | explore_schema | 查看 attribute 样例 | 确认 `Speed` 存在，id=3。 |
| Round 7 | generate_sql | 按 Speed 降序 `LIMIT 1`，并输出 attribute value | 返回 `Air-Walker, 100`，但最高 Speed=100 有 40 个英雄并列。 |
| Round 8 | confirm_answer | 确认 `LIMIT 1` 版本 | gold 返回所有并列最快英雄，且只要 `superhero_name`；pred 漏行并多输出数值列。 |""",
    "798": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `superhero` 与 `publisher`。 |
| Round 2 | explore_schema | 查看两表建表 SQL | 已看到 `superhero.publisher_id -> publisher.id`。 |
| Round 3 | propose_schema | 提出按三个 hero name join publisher | join 和过滤正确。 |
| Round 4 | generate_sql | 查询 `publisher_name, superhero_name` | 三个 publisher 都是 `DC Comics`，答案值对，但多输出了 hero name。 |
| Round 5 | confirm_answer | 确认两列输出版本 | gold 只返回三行 `publisher_name`；EX 要列数一致。 |""",
    "800": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 列表里已经显示正确表名是英式 `colour`。 |
| Round 2 | explore_schema | 查看 `superhero` 字段 | 已看到 `eye_colour_id`。 |
| Round 3 | explore_schema | 错去看 `hero_attribute` | 与眼睛颜色无关。 |
| Round 4 | explore_schema | 查看 `attribute` 建表 SQL | 继续把颜色误当 attribute。 |
| Round 5 | explore_schema | 在 `attribute` 里查 `Blue` | 返回空，这是错误方向。 |
| Round 6 | explore_schema | 查询不存在的 `color` 表 | 因使用美式拼写，返回空。 |
| Round 7 | explore_schema | 再次确认 `color` 表是否存在 | 仍然没有。 |
| Round 8 | explore_schema | 第三次查 `color` 建表 SQL | 重复空结果。 |
| Round 9 | explore_schema | 第四次查 `color` 建表 SQL | 仍未回到已列出的 `colour`。 |
| Round 10 | explore_schema | 第五次查不存在的 `color` 表 | 最大轮数耗尽；没有生成百分比 SQL。 |""",
    "819": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `superhero` 与 `colour`。 |
| Round 2 | explore_schema | 查看 `superhero/colour` 等建表 SQL | 已看到 `weight_kg` 和 `eye_colour_id`。 |
| Round 3 | explore_schema | 查询 `colour` id 1 与 7 | 确认 `No Colour=1`、`Blue=7`。 |
| Round 4 | generate_sql | 在缺失体重中过滤 `weight_kg=0 OR IS NULL`，计算 blue/no-color/difference | difference `-122` 正确，但多输出了 `blue_eyes`、`no_eye_color` 两个中间列。 |
| Round 5 | confirm_answer | 确认三列输出版本 | gold 只要一列 difference；失败来自输出形状。 |""",
    "829": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `superhero` 与 `publisher`。 |
| Round 2 | explore_schema | 查看 `publisher` 建表 SQL | 确认 `publisher_name`。 |
| Round 3 | explore_schema | 查看 `superhero` 建表 SQL | 确认 `publisher_id` 外键。 |
| Round 4 | propose_schema | 提出按 DC/Marvel 计数并求差 | 方向正确。 |
| Round 5 | generate_sql | 先按 publisher 分组计数 | 得到 Marvel=387、DC=224，已经知道 Marvel 更多。 |
| Round 6 | generate_sql | 尝试一条 SQL 同时输出分组计数和差值 | 因 `GROUP BY publisher_name`，每行差值只在当前组内计算，结果不适合作最终答案。 |
| Round 7 | generate_sql | 改成一行条件聚合，输出 DC count、Marvel count、difference | 差值 `DC-Marvel=-163` 与本题 gold 一致，但仍没输出“Marvel Comics”这个 winner。 |
| Round 8 | confirm_answer | 确认中间计数列版本 | gold 要 `(Marvel Comics, -163)` 两列；pred 是 `(224, 387, -163)` 三列。 |""",
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
