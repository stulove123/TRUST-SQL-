#!/usr/bin/env python3
"""Apply hand-written, root-cause-oriented trajectory tables for card_games."""

from __future__ import annotations

import re
from pathlib import Path


TARGET = Path("/root/autodl-tmp/text_to_sql_benchmarks/results/qwen35-4b-arcwise-plat-trustsql-full-final-thinking/card_games_wrong_analysis.md")


TABLES = {
    "344": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 找到 `cards` 和 `legalities`，正确表已经出现。 |
| Round 2 | explore_schema | 查看 `cards` 字段 | 看到 `id`、`rarity`、`uuid`，足够表达 mythic print card id。 |
| Round 3 | explore_schema | 查看 `legalities` 字段 | 看到 `format`、`status`、`uuid`，足够表达 gladiator banned。 |
| Round 4 | explore_schema | 重复查看 `legalities` | 没有新增信息；此时应形成 `cards.uuid = legalities.uuid`。 |
| Round 5 | explore_schema | 转去看 `foreign_data` | 与 banned/format/rarity 无关，开始偏离核心路径。 |
| Round 6 | explore_schema | 查看 `foreign_data` 建表 SQL | 确认 `foreign_data.uuid -> cards.uuid`，但这不是本题所需。 |
| Round 7 | explore_schema | 查看 `legalities` 样例 | 看到各 format/status 记录，进一步证明 `legalities` 就是合法性表。 |
| Round 8 | explore_schema | 查 gladiator 样例 | 看到 gladiator 记录，但没有继续筛 `status='Banned'` 并 join cards。 |
| Round 9 | explore_schema | 在 `foreign_data.type` 中查 `legal` | 空结果；把合法性错误地联想到外文 type。 |
| Round 10 | explore_schema | 枚举 `foreign_data.type` | 看到的是外文卡牌类型，彻底偏离；最大轮数耗尽，没有生成 SQL。 |""",
    "347": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `cards` 和 `rulings`。 |
| Round 2 | explore_schema | 查看 `cards` 字段 | 找到 `artist`、`id`、`uuid`、`hasContentWarning`。 |
| Round 3 | explore_schema | 查看 `rulings` 字段 | 找到 `text` 和 `uuid`。 |
| Round 4 | explore_schema | 查看 `rulings` 外键 | 确认 `rulings.uuid -> cards.uuid`。 |
| Round 5 | generate_sql | 用 inner join 查询 Stephen Daniele 的 card id、ruling text、content warning | 只返回 23 行；没有 ruling 的 Stephen Daniele 卡被 join 丢掉。 |
| Round 6 | confirm_answer | 确认 inner join 版本 | gold 要 “Find all cards”，应 `LEFT JOIN rulings`，保留无 ruling 的卡并返回 NULL。 |""",
    "349": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `cards` 和 `rulings`。 |
| Round 2 | explore_schema | 查看 `cards` 字段 | 找到 `name`、`artist`、`isPromo`、`uuid`。 |
| Round 3 | explore_schema | 查看 `rulings` 字段 | 找到 `uuid`，可按卡统计 ruling 数。 |
| Round 4 | explore_schema | 查看 `foreign_data` | 与 ruling count 无关，轻微偏离。 |
| Round 5 | propose_schema | 提出 `cards` + `rulings` 方案 | 表选择正确。 |
| Round 6 | generate_sql | 按 `c.uuid` 统计 ruling 数，`ORDER BY count DESC LIMIT 1` | 找到 Teferi's Protection，但只取一个 printing，漏掉并列最大 ruling 数下的另一个 `isPromo` 状态。 |
| Round 7 | confirm_answer | 把 `isPromo` 转成 Yes/No 并确认 | gold 保留整数 0/1，且返回两个 distinct `(name, artist, isPromo)`；pred 行数和值类型都错。 |""",
    "352": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 同时有 `foreign_data` 和 `set_translations`，需要区分二者语义。 |
| Round 2 | explore_schema | 先查看 `set_translations` | 看到 language/setCode/translation，误以为它表示卡牌语言版本。 |
| Round 3 | explore_schema | 查看 `cards` | 看到 `setCode`，进一步沿 set 级翻译方向走。 |
| Round 4 | explore_schema | 查看 `sets` | 建立了 cards-set-set_translations 路径。 |
| Round 5 | explore_schema | 枚举 `set_translations.language` | 看到 Chinese Simplified，但这是系列名称翻译，不是每张卡的外文数据。 |
| Round 6 | explore_schema | 统计 `cards` 总数 | 分母 56822 正确。 |
| Round 7 | generate_sql | 用 `cards JOIN set_translations` 算 Chinese Simplified 比例 | 得到 10.0，本质是“所在 set 有中文系列翻译”的比例。 |
| Round 8 | confirm_answer | 确认 set 翻译口径 | gold 应 `cards LEFT JOIN foreign_data` 并按 `DISTINCT cards.id` 计算有中文简体外文数据的卡牌占比。 |""",
    "368": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 正确表是 `cards`。 |
| Round 2 | explore_schema | 查看 `cards` 字段 | 找到 `borderColor`。 |
| Round 3 | explore_schema | 一次提交 total 和 borderless 两条 SQL | 工具拒绝：一次只能执行一条语句。 |
| Round 4 | explore_schema | 单独统计总卡数 | 得到 56822。 |
| Round 5 | explore_schema | 单独统计 borderless 卡数 | 得到 241。 |
| Round 6 | generate_sql | 计算 `241 / 56822 * 100`，但用了 `ROUND(...,2)` | 返回 0.42。 |
| Round 7 | confirm_answer | 确认两位小数结果 | gold 是完整精度 0.42413149836331；严格 EX 下四舍五入导致失败。 |""",
    "371": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `cards.isStorySpotlight` 和卡牌级语言表。 |
| Round 2 | explore_schema | 查看 `cards` | 找到 `isStorySpotlight` 和 `setCode`。 |
| Round 3 | explore_schema | 查看 `set_translations` | 把 language 字段误判为卡牌语言来源。 |
| Round 4 | explore_schema | 查看 `set_translations` 建表 SQL | 确认它按 `setCode` 连 `sets`，其实说明它是 set 级翻译。 |
| Round 5 | explore_schema | 再看 `cards` 建表 SQL | 没有转向 `foreign_data`。 |
| Round 6 | propose_schema | 提出 `cards + set_translations` | schema 从这一轮开始锁定错误表。 |
| Round 7 | generate_sql | 对 Story Spotlight 卡 join set_translations，并按 `c.id` group 后 `LIMIT 1` | 得到单个卡/系列翻译行上的 10.0，不是全体 Story Spotlight 卡中有 French 外文数据的比例。 |
| Round 8 | confirm_answer | 确认 10.0 | gold 应 `LEFT JOIN foreign_data`，按 `DISTINCT cards.id` 在 Story Spotlight 分母上算 83.653846...。 |""",
    "383": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `legalities` 和 `cards`。 |
| Round 2 | explore_schema | 查看 `legalities` | 找到 `status`、`uuid`。 |
| Round 3 | explore_schema | 查看 `cards` | 找到 `borderColor`、`uuid`、`id`。 |
| Round 4 | propose_schema | 尝试提交 schema 但 JSON 格式错 | 工具没有接受 schema；不过表关系已经足够。 |
| Round 5 | generate_sql | join 后用 `COUNT(*)` 统计 banned + white border 明细 | 返回 258，统计的是 legalities format 明细行。 |
| Round 6 | confirm_answer | 确认 `COUNT(*)` | gold 问 banned cards，应 `COUNT(DISTINCT cards.id)`；同一张卡在多个 format banned 被重复算。 |""",
    "391": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `cards` 和 `foreign_data`。 |
| Round 2 | explore_schema | 查看 `cards` | 找到 `originalType`、`colors`、`name`、`uuid`。 |
| Round 3 | explore_schema | 查看 `foreign_data` | 找到 `language`、`type`、`uuid`。 |
| Round 4 | explore_schema | 查看 `set_translations` | 本题不需要 set 翻译。 |
| Round 5 | explore_schema | 枚举 `foreign_data.language` | 确认有外文语言数据。 |
| Round 6 | explore_schema | 枚举 `foreign_data.type` | 只是外文类型文本，不影响本题。 |
| Round 7 | explore_schema | 再次确认非英语语言 | 外文存在性已清楚。 |
| Round 8 | propose_schema | 提出 `cards + foreign_data` | 表选择对，但 join 细节危险。 |
| Round 9 | generate_sql | 用 `c.id = fd.uuid` join，并过滤 Artifact/B | 返回空；`id` 是整数，`fd.uuid` 是文本 UUID。 |
| Round 10 | generate_sql | 去掉颜色条件仍用错误 join 检查 Artifact | 继续空结果；正确应 `c.uuid = fd.uuid`，并只输出 `cards.name`。 |""",
    "402": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 正确表是 `cards`。 |
| Round 2 | explore_schema | 查看 `cards` 字段 | 找到 `isStorySpotlight` 和 `isTextless`。 |
| Round 3 | propose_schema | 提出只用 `cards` | 方案正确。 |
| Round 4 | generate_sql | 生成百分比 SQL | 已得到正确标量 0.0，但没有停在这个答案。 |
| Round 5 | generate_sql | 改查匹配条件的 count | 得到 0；这是分子，不是最终百分比输出。 |
| Round 6 | generate_sql | 查看两个布尔字段组合 | 确认没有 `(1,1)`。 |
| Round 7 | generate_sql | 查 Story Spotlight 总数 | 得到 104。 |
| Round 8 | generate_sql | 查 Textless 总数 | 得到 115。 |
| Round 9 | generate_sql | 返回百分比、分子、总数三列 | 值中包含正确 0.0，但输出形状不是 gold 的一列。 |
| Round 10 | generate_sql | 最后改成 `SELECT *` 查符合条件明细 | 由于无匹配行，最终 pred 是空表；题目问 percentage，应始终返回一行 0.0。 |""",
    "407": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要判断 “types” 是英文主表字段还是德语外文字段。 |
| Round 2 | explore_schema | 查看 `cards`、`foreign_data` 等建表 SQL | 已能看到 `cards.subtypes/supertypes` 和 `foreign_data.language`。 |
| Round 3 | explore_schema | 查看 `foreign_data` 字段 | 看到 `type`，开始把目标理解成德语 type 字符串。 |
| Round 4 | explore_schema | 查不存在的 `types` 表 | 没有该表。 |
| Round 5 | explore_schema | 枚举 `foreign_data.language` | 确认 German 存在。 |
| Round 6 | explore_schema | 查看 German 的 `foreign_data.type` 样例 | 看到德语整段类型栏，如 `Kreatur ...`，进一步锁定错误输出字段。 |
| Round 7 | generate_sql | 输出 `DISTINCT foreign_data.type WHERE language='German'` | 返回 2150 个德语类型字符串。 |
| Round 8 | confirm_answer | 确认德语 type 字符串 | gold 要在有 German 外文版本的卡牌上输出英文主表的 `subtypes, supertypes`，不是 `foreign_data.type`。 |""",
    "408": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `cards.power` 和 `rulings.text`。 |
| Round 2 | explore_schema | 查看 `cards` | 找到 `power`。 |
| Round 3 | explore_schema | 查看 `rulings` | 找到 ruling `text` 和 `uuid`，这正是 “triggered ability info” 的目标表。 |
| Round 4 | explore_schema | 查看 `foreign_data` | 转向了外文文本表。 |
| Round 5 | explore_schema | 查看 `cards` 建表 SQL | 重复确认。 |
| Round 6 | explore_schema | 查看 `foreign_data` 建表 SQL | 看到 `foreign_data.text`，误当作 ruling 信息来源。 |
| Round 7 | explore_schema | 统计 unknown power 卡数 | 得到 31053。 |
| Round 8 | explore_schema | 用 `cards JOIN foreign_data` 统计 unknown power 且外文 text 含 triggered ability | 返回 113039，已经异常大；且 SQL 里 `OR/AND` 未加括号。 |
| Round 9 | generate_sql | 确认同一条 `foreign_data` 计数 SQL | 继续返回 113039。 |
| Round 10 | confirm_answer | 确认外文文本明细行计数 | gold 应 `cards JOIN rulings`，用 `(power IS NULL OR power='*')` 加括号，并 `COUNT(DISTINCT cards.id)`。 |""",
    "412": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `cards` 过滤条件和 `foreign_data` 输出 French name。 |
| Round 2 | explore_schema | 查看 `cards` 建表 SQL | 找到 `types`、`layout`、`borderColor`、`artist`、`uuid`。 |
| Round 3 | explore_schema | 查看 `foreign_data` 建表 SQL | 找到 `language`、`name`、`uuid`。 |
| Round 4 | explore_schema | 查看 `foreign_data` 字段 | 进一步确认 French foreign name 所在字段。 |
| Round 5 | explore_schema | 查看 `set_translations` | 与卡牌外文名无关。 |
| Round 6 | explore_schema | 枚举 `cards.type` | 看到整段类型栏，开始犹豫用 `type` 还是 `types`。 |
| Round 7 | explore_schema | 枚举 `layout` | 确认 normal。 |
| Round 8 | explore_schema | 枚举 `types LIKE '%Creature%'` | 看到 `types='Creature'` 是可用过滤。 |
| Round 9 | explore_schema | 枚举 `borderColor` | 确认 black。 |
| Round 10 | explore_schema | 枚举 `foreign_data.language` | 确认 French，但仍未进入 generate_sql；最大轮数耗尽，pred 为空。 |""",
    "415": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `cards` 和 `legalities`。 |
| Round 2 | explore_schema | 查看 `cards` | 找到 `hasContentWarning`、`uuid`。 |
| Round 3 | explore_schema | 查看 `legalities` | 找到 `format`、`status`、`uuid`。 |
| Round 4 | explore_schema | 查 `cards` 外键 | 无外键声明，但 `legalities.uuid` 样例可验证 join。 |
| Round 5 | explore_schema | 查看 `legalities` 样例 | 已看到 status 实际值是 `Legal`，首字母大写。 |
| Round 6 | explore_schema | 查看 `cards` 样例 | `hasContentWarning` 字段存在。 |
| Round 7 | propose_schema | 提出 `cards + legalities` | 表和 join 正确。 |
| Round 8 | generate_sql | 用 `status='legal'` 小写计算百分比并 round | 因大小写不匹配，分母为 0，结果 NULL。 |
| Round 9 | generate_sql | 检查小写 `legal` 的匹配数 | 返回 0，说明状态值大小写错。 |
| Round 10 | explore_schema | 转去看 `cards.uuid` | 没有回到 Round 5 的 `Legal` 样例修正；最终 pred_sql 是小写条件的 count，不是 percentage。 |""",
    "416": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `cards.power` 和卡牌级语言信息。 |
| Round 2 | explore_schema | 查看 `cards` | 找到 `power` 和 `setCode`。 |
| Round 3 | explore_schema | 查看 `set_translations` | 误把 set 级 language 当作卡牌语言。 |
| Round 4 | explore_schema | 查看 `set_translations` 建表 SQL | 其实显示它连 `sets`，不是 `cards.uuid`。 |
| Round 5 | explore_schema | 查看 without power 卡涉及的 setCode | 继续沿 setCode 方向。 |
| Round 6 | explore_schema | 统计 French set_translations 行数 | 这是有 French 系列翻译的 set 数，不是 French card 数。 |
| Round 7 | explore_schema | 统计 without power 卡的 distinct setCode | 仍是 set 粒度。 |
| Round 8 | explore_schema | 统计 without power card 总数 | 分母 31053 是 card 粒度。 |
| Round 9 | explore_schema | left join `set_translations` 看样例 | 同一张卡因多种 set translation 出现多行，暴露了粒度放大风险。 |
| Round 10 | generate_sql | 试图生成最终 SQL 但缺少 `<tool_call>` | 没有 pred_sql；正确应 `LEFT JOIN foreign_data ON uuid`，按 `DISTINCT cards.id` 算 French 占比。 |""",
    "422": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 目标可能在 `cards.multiverseId` 或 `foreign_data.multiverseid`。 |
| Round 2 | explore_schema | 查看 `cards` 建表 SQL | 看到 `cards.multiverseId`，于是只盯住主表。 |
| Round 3 | explore_schema | 查看 `set_translations` | 查 language 方向偏到 set 翻译。 |
| Round 4 | explore_schema | 在 `cards.multiverseId='149934'` 查询 | 返回空。 |
| Round 5 | explore_schema | 用数字 149934 查 `cards.multiverseId` | 仍为空。 |
| Round 6 | explore_schema | 再用字符串查 `cards.multiverseId` | 仍为空。 |
| Round 7 | explore_schema | 查看 `cards.multiverseId` 样例 | 证明该列有值，但没有证明 149934 在 cards。 |
| Round 8 | explore_schema | 又查一次 `cards.multiverseId='149934'` | 仍为空。 |
| Round 9 | explore_schema | 用 LIKE 搜 `cards.multiverseId` | 仍为空。 |
| Round 10 | explore_schema | 转去查看 `sets` 样例 | 没有检查 `foreign_data.multiverseid`；gold 直接从那里返回 language=French。 |""",
    "440": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要判断给定名称是英文卡名还是外文卡名。 |
| Round 2 | explore_schema | 查看 `cards` | 看到主表 `name`，先把 `A Pedra Fellwar` 当英文卡名。 |
| Round 3 | explore_schema | 查看 `set_translations` | 误以为语言来自系列翻译。 |
| Round 4 | explore_schema | 在 `cards.name='A Pedra Fellwar'` 查找 | 返回空；这是外文名不在 cards 的信号。 |
| Round 5 | explore_schema | 查看 `sets` | 无关。 |
| Round 6 | explore_schema | 查看 `foreign_data` 字段 | 已看到 `foreign_data.name/language`，但还没有搜索目标名。 |
| Round 7 | explore_schema | 继续在 `cards.name LIKE '%A Pedra Fellwar%'` 查 | 仍为空。 |
| Round 8 | explore_schema | 在 `cards.name LIKE '%Pedra%'` 查 | 仍为空。 |
| Round 9 | explore_schema | 查看 `foreign_data` 样例 | 终于看到外文 name/language 结构，但没有用 `name='A Pedra Fellwar'` 查询。 |
| Round 10 | explore_schema | 在 `cards` 中搜 Fellwar | 找到英文 `Fellwar Stone`，但没有回到 `foreign_data`；最终没有 SQL。 |""",
    "459": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 正确表是 `cards`。 |
| Round 2 | explore_schema | 查看 `cards` 字段 | 找到 `name` 和 `convertedManaCost`。 |
| Round 3 | generate_sql | 查询两张卡的所有 printing 的 `name, convertedManaCost` | 看出 Serra Angel 5.0、Shrine Keeper 2.0，但返回 46 行且多输出 mana cost。 |
| Round 4 | confirm_answer | 自然语言判断 Serra Angel 更大并确认原 SQL | gold 要 SQL 只返回更大的卡名，需 `ORDER BY convertedManaCost DESC LIMIT 1` 且只选 `name`。 |""",
    "465": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `cards`、`sets`、`set_translations`。 |
| Round 2 | explore_schema | 查看三张表建表 SQL | 找到 `cards.setCode -> sets.code` 和 `set_translations.setCode`。 |
| Round 3 | propose_schema | 提出 cards-set_translations-sets 路径 | 表语义正确：这里问的是 set 是否有 Korean version。 |
| Round 4 | generate_sql | 查询含 `Ancestor's Chosen` 且 set translation 为 Korean 的 set | 找到正确两个 set，但输出 `s.name, s.code` 两列。 |
| Round 5 | confirm_answer | 确认包含 set code 的结果 | gold 只要 set name；多输出 `code` 导致 EX 失败。 |""",
    "469": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `cards` 和 `sets`。 |
| Round 2 | explore_schema | 查看 `cards` | 找到 `name`、`setCode`。 |
| Round 3 | explore_schema | 查看 `sets` | 找到 `code`、`mtgoCode`、`name`。 |
| Round 4 | explore_schema | 重复查看 `sets` | 已确认 MTGO 信息在 set 表。 |
| Round 5 | explore_schema | 查 `cards` 外键 | 没有声明外键，但 `setCode` 与 `sets.code` 可用。 |
| Round 6 | explore_schema | 列出 Angel of Mercy 出现的 setCode | 得到 13 个候选 set。 |
| Round 7 | explore_schema | 查询这些 set 的 `mtgoCode` | 确认 6 个 set 有 mtgoCode。 |
| Round 8 | generate_sql | 返回 `s.name, s.code, s.mtgoCode` | 筛选集合正确，但多输出 code 和 mtgoCode。 |
| Round 9 | confirm_answer | 确认三列版本 | gold 只要 `sets.name`。 |""",
    "473": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `cards` 和 `sets`。 |
| Round 2 | explore_schema | 查看 `cards` | 找到 `name`、`setCode`。 |
| Round 3 | explore_schema | 查看 `foreign_data` | 与 set 是否 foreign-only 无关。 |
| Round 4 | explore_schema | 查看 `legalities` | 无关。 |
| Round 5 | explore_schema | 查看 `sets` | 找到 `isForeignOnly`。 |
| Round 6 | explore_schema | 查 Adarkar Valkyrie 的 setCode | 找到 5 个 set。 |
| Round 7 | explore_schema | 查这 5 个 set 的 `isForeignOnly` | 全部是 0，已可回答 NO。 |
| Round 8 | generate_sql | 直接过滤 `isForeignOnly=1` 输出明细 | 返回空表；yes/no 题不能用空表表达 NO。 |
| Round 9 | confirm_answer | 确认空表 | gold 用 `IIF(SUM(isForeignOnly)>0,'YES','NO')`，始终返回一行 `NO`。 |""",
    "480": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要卡牌名和 Italian flavor text。 |
| Round 2 | explore_schema | 查看 `cards` | 找到英文 `flavorText`、`name`、`setCode`。 |
| Round 3 | explore_schema | 查看 `set_translations` | 把 Italian 语言线索带到 set 翻译表。 |
| Round 4 | explore_schema | 查询 `cards.name='Ancestor''s Chosen'` | 找到多个 printing 及英文/NULL flavorText。 |
| Round 5 | explore_schema | 查看 `set_translations` 建表 SQL | 看到 `translation` 是 setCode 的翻译，不是 card flavor text。 |
| Round 6 | explore_schema | 查看 `sets` | 继续沿 set 路径。 |
| Round 7 | propose_schema | 提出 `cards + set_translations` | 锁定错误表，漏掉 `foreign_data.flavorText`。 |
| Round 8 | generate_sql | 返回 `cards.flavorText` 和 Italian set translation | 得到英文 flavor text、set 名翻译和 NULL，列数也多。 |
| Round 9 | confirm_answer | 确认 set translation 版本 | gold 应 `cards.uuid = foreign_data.uuid` 且 `foreign_data.language='Italian'`，只输出 `foreign_data.flavorText`。 |""",
    "483": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `sets`、`cards`、`foreign_data`，题面中的 ruling 容易误导到 `rulings`。 |
| Round 2 | explore_schema | 查看 `sets` | 找到 set code/name 结构。 |
| Round 3 | explore_schema | 查看 `cards` | 找到 `setCode`、`uuid`。 |
| Round 4 | explore_schema | 查看 `set_translations` | 与 card-level Italian text 无关。 |
| Round 5 | explore_schema | 查看 `rulings` | 受 “text ruling” 表述影响，但 gold 实际用 `foreign_data.text`。 |
| Round 6 | explore_schema | 查 `sets.name='Coldsnap'` | 得到 code `CSP`。 |
| Round 7 | explore_schema | 查看 `foreign_data` | 找到 `language`、`text`、`uuid`，正确目标表出现。 |
| Round 8 | explore_schema | 统计 Coldsnap 中 Italian foreign_data 行 | 得到 155，说明路径可行。 |
| Round 9 | explore_schema | 枚举 Coldsnap 的 foreign_data 语言 | 确认 Italian 存在。 |
| Round 10 | propose_schema | 提出包含 `foreign_data/cards/sets/rulings` 的 schema | 已接近正确，但没有进入 generate_sql；最终 pred 为空。 |""",
    "484": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 Coldsnap set、最高 mana cost、Italian card names。 |
| Round 2 | explore_schema | 查看 `cards` | 找到 `convertedManaCost`、`name`、`setCode`。 |
| Round 3 | explore_schema | 查看 `set_translations` | 误把 Italian card name 映射到 set translation。 |
| Round 4 | explore_schema | 查看 `sets` | 找到 `code`、`name`。 |
| Round 5 | explore_schema | 查看 Italian set_translations 样例 | 看到 `Ondata Glaciale` 等 set 名翻译，进一步误导。 |
| Round 6 | explore_schema | 查 Coldsnap code | 得到 `CSP`。 |
| Round 7 | propose_schema | 提出 cards-set_translations-sets | 漏掉 `foreign_data.name`。 |
| Round 8 | generate_sql | 用 set translation 输出一个最高 mana cost card | 只返回 1 行，且 `italian_name` 是 Coldsnap 的意大利语 set 名。 |
| Round 9 | generate_sql | 单独确认 Coldsnap 最高 convertedManaCost | 得到 7.0，排序/并列意识变好。 |
| Round 10 | generate_sql | 返回所有 CMC=7 的卡，但仍用 `set_translations.translation` 并多输出英文名和 CMC | 行数 12 对了，值和列形状错；gold 要 `foreign_data.name` 的 12 个 Italian card names。 |""",
    "487": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `cards` 和 `sets`。 |
| Round 2 | explore_schema | 查看 `cards` | 找到 `cardKingdomFoilId`、`cardKingdomId`、`setCode`。 |
| Round 3 | explore_schema | 查看 `sets` | 找到 `code`、`name`。 |
| Round 4 | explore_schema | 查 `sets.name='Coldsnap'` | 确认 Coldsnap 是 set，不是 card name。 |
| Round 5 | explore_schema | 查看 `foreign_data` | 本题不需要。 |
| Round 6 | explore_schema | 一次提交多条样例 SQL | 工具拒绝：一次只能执行一条语句。 |
| Round 7 | explore_schema | 再次一次提交多条 SQL | 再次被拒绝，浪费轮次。 |
| Round 8 | explore_schema | 查看 `foreign_data` 字段 | 继续偏离。 |
| Round 9 | explore_schema | 再查 Coldsnap code | 得到 `CSP`。 |
| Round 10 | explore_schema | 重复查 Coldsnap code | 最大轮数耗尽；没有生成 `cards JOIN sets` 后计算 CardKingdom 双 ID 非空比例的 SQL。 |""",
    "518": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `legalities` 统计 format，和 `cards` 输出 name。 |
| Round 2 | explore_schema | 查看 `legalities` 建表 SQL | 找到 `format`、`status`、`uuid`。 |
| Round 3 | explore_schema | 查看 `cards` 建表 SQL | 找到 `name`、`uuid`。 |
| Round 4 | explore_schema | 查看 format/status 样例 | 看到 status 大小写是 `Legal` 等。 |
| Round 5 | explore_schema | 枚举 `status='Banned'` 的 format | 找到多个有 banned 的 format。 |
| Round 6 | propose_schema | 提交 schema 格式错误 | 工具未接受，但思路已经是 legalities-cards。 |
| Round 7 | propose_schema | 修正 schema | schema 被接受。 |
| Round 8 | generate_sql | 用 CTE 先找 banned 数最多 format，再列卡名 | 查询思路接近正确，但工具只接受以 SELECT/PRAGMA/EXPLAIN 开头，拒绝 `WITH`。 |
| Round 9 | generate_sql | 重复同一个 CTE | 再次被工具拒绝。 |
| Round 10 | generate_sql | 改成 `GROUP BY format, name ORDER BY COUNT(*) DESC LIMIT 1` | 变成找出现次数最多的单个 `(format, card)`，返回 `duel/Sol Ring`；正确应先按 format 聚合，再返回最高 format 下所有 banned card names。 |
| 评测补充 | gold 执行 | gold SQL 在本次评测详情里超时 | 因此该题还有评测层异常；即使忽略超时，pred 的聚合层级也错。 |""",
    "529": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要卡牌级翻译差集。 |
| Round 2 | explore_schema | 查看 `cards` | 找到 `name`、`uuid`、`setCode`。 |
| Round 3 | explore_schema | 查看 `set_translations` | 误把 set 级语言当作 card translation。 |
| Round 4 | explore_schema | 查看 `sets` | 继续沿 setCode 路径。 |
| Round 5 | explore_schema | 一次提交两条 SQL | 工具拒绝多语句。 |
| Round 6 | explore_schema | 一次提交三条 SQL | 再次被拒绝；没有真正查看 language 分布。 |
| Round 7 | explore_schema | 输出 explore_schema 但缺 tool_call | 协议格式错误。 |
| Round 8 | explore_schema | 再次缺 tool_call | 继续浪费轮次。 |
| Round 9 | explore_schema | 第三次缺 tool_call | 系统提示快没轮次。 |
| Round 10 | generate_sql | 用 `cards JOIN set_translations`，条件 `language='Korean' AND language NOT LIKE '%Japanese%'` | `Korean NOT LIKE Japanese` 恒真，且是 set 级翻译；返回 15670 个 name。gold 应在 `foreign_data.uuid` 上做 Korean minus Japanese 差集，只得到 `Wastes`。 |""",
}


def replace_table(text: str, qid: str, table: str) -> str:
    start = re.search(rf"^## qid{re.escape(qid)}\b", text, re.M)
    if not start:
        raise SystemExit(f"missing qid section: {qid}")

    next_section = re.search(r"^## qid\d+\b|^## 错误类型归纳", text[start.end():], re.M)
    section_end = start.end() + next_section.start() if next_section else len(text)
    section = text[start.start():section_end]

    marker = "### 运行轨迹\n"
    marker_idx = section.find(marker)
    if marker_idx < 0:
        raise SystemExit(f"missing trajectory marker for qid {qid}")

    before = section[:marker_idx]
    after = section[marker_idx + len(marker):]
    following_heading = re.search(r"\n## |\n### ", after)
    if following_heading:
        tail = after[following_heading.start():]
    else:
        tail = ""

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
