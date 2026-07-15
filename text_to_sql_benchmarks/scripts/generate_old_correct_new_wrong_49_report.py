#!/usr/bin/env python3
"""Build the audited old-correct/new-wrong 49-case regression report."""

from __future__ import annotations

import argparse
import html
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path("/root/autodl-tmp/text_to_sql_benchmarks")
DEFAULT_OLD = ROOT / "results/qwen35-4b-arcwise-plat-trustsql-full-final-thinking/details.pretty.json"
DEFAULT_NEW = ROOT / (
    "results/qwen35-4b-arcwise-plat-twostage-agent-full-latest-s12-s6-round-action-memory/episodes.pretty.json"
)
DEFAULT_OUT_DIR = DEFAULT_NEW.parent
REPORT_SHELL = Path(
    "/root/.codex/plugins/cache/openai-curated-remote/data-analytics/"
    "0.2.6-d37358633e00/assets/html-report-shell.html"
)


PRIMARY_JOIN = "JOIN / schema 关系错误"
PRIMARY_AGG = "聚合 / 结果粒度错误"
PRIMARY_TIME = "日期 / 排序 / Top-k / 字段语义错误"
PRIMARY_OUTPUT = "输出列 / 结果形状错误"
PRIMARY_FILTER = "过滤条件 / 值映射错误"
PRIMARY_PRECISION = "数值精度错误"
PRIMARY_SYNTAX = "SQL 语法与修复失败"
PRIMARY_CONTROL = "预算 / 终止控制错误"

ORIGIN_SCHEMA = "第一阶段证据错误或不完整"
ORIGIN_SQL = "第二阶段 SQL 语义推导错误"
ORIGIN_OUTPUT = "输出契约未约束"
ORIGIN_RECOVERY = "执行错误修复未收敛"


CASE_ANALYSIS: dict[str, dict[str, str]] = {
    "5": {
        "primary": PRIMARY_AGG,
        "origin": ORIGIN_SQL,
        "exact": "新版按 CDSCode 分组后再 COUNT(DISTINCT CDSCode)，因此返回 4 行 [1]，而不是一个标量 4。应去掉 GROUP BY/HAVING，在行级过滤 AvgScrMath > 400 后直接统计不同学校。",
        "trajectory": "第一阶段已找到正确表、连接、Virtual='F' 和 rtype='S'；偏差始于 SQL 阶段把“平均分”误解为必须按校聚合，执行成功后又把非标量结果当成答案。",
    },
    "17": {
        "primary": PRIMARY_JOIN,
        "origin": ORIGIN_SCHEMA,
        "exact": "新版从 frpm 的 Charter School Number 取编号，而 gold/旧版使用 schools.CharterNum，并遗漏 rtype='S'。恰有两个满足条件的学校（CharterNum 0147、0084）在 frpm 对应字段为 NULL，所以新版只有 48 行，正确结果为 50 行。",
        "trajectory": "第一阶段把 FRPM 的同义字段当成完整替代，没有验证它与 schools.CharterNum 的覆盖一致性；提交的 schema 证据也未保留 rtype 过滤。",
    },
    "26": {
        "primary": PRIMARY_FILTER,
        "origin": ORIGIN_SCHEMA,
        "exact": "新版同时把 County='Monterey' 写成 City='Monterey'，并把真实 School Type 值 High Schools (Public) 猜成 high，结果由 6 行变成 0 行。",
        "trajectory": "第一阶段只看元数据便提交了未经 inspect_value 验证的 City 和 high 两个约束，错误值被结构化 schema 证据固化并传给第二阶段。",
    },
    "28": {
        "primary": PRIMARY_SYNTAX,
        "origin": ORIGIN_RECOVERY,
        "exact": "R13/R14 把差值写成 (Enrollment(K-12) - Enrollment(Ages 5-17) AS diff)，AS 前少一个右括号；R15-R18 又在 AVG(...) 处持续漏右括号。六次 execute_sql 全部失败，最终 pred_sql 为空；而且尝试中输出 DOC，不是题目要求的 DOCType。",
        "trajectory": "模型把明确的括号错误误诊为 SQLite 不支持 CTE/WHERE 子查询，记忆继续保留了错误诊断，导致后续只改查询结构却反复复制同一括号缺失。",
    },
    "87": {
        "primary": PRIMARY_OUTPUT,
        "origin": ORIGIN_OUTPUT,
        "exact": "筛选条件和前两个邮箱值均正确，但新版额外输出 AdmEmail3；该列在命中行中为 NULL。题目明确要求两列，strict EX 因 3 列对 2 列失败。",
        "trajectory": "第二阶段没有在执行前核对投影列数量，看到查询返回目标学校后就立即终止。",
    },
    "207": {
        "primary": PRIMARY_JOIN,
        "origin": ORIGIN_SCHEMA,
        "exact": "新版按 molecule_id 直接连接 bond 与 atom，得到“含双键分子中的所有原子”，返回 17 种元素；正确查询必须经 connected.bond_id/atom_id 只取直接参与双键的原子，返回 5 种元素。",
        "trajectory": "第一阶段没有探索 connected 表，并把 inspect_join_candidate 给出的同名 molecule_id 候选连接当成语义连接。",
    },
    "215": {
        "primary": PRIMARY_JOIN,
        "origin": ORIGIN_SCHEMA,
        "exact": "新版在 atom 与 bond 之间额外强制连接 molecule 表。数据中有 11 个满足单键条件的 molecule_id 不存在于 molecule 表，额外连接因此丢掉 3 个 iodine 原子和 19 个 sulfur 原子，结果从 (6,113) 变成 (3,94)。",
        "trajectory": "schema 阶段耗尽预算且未提交 schema_evidence；SQL 阶段自行补出看似规范、但对该基准实际数据不保真的 molecule 中间连接。",
    },
    "236": {
        "primary": PRIMARY_JOIN,
        "origin": ORIGIN_SQL,
        "exact": "connected 已直接保存 atom_id 与 atom_id2。新版却拆成 UNION 并把每个端点再连接回 atom，最终输出 (TR001_6,TR001_6) 和 (TR001_9,TR001_9)，而正确配对应为 (6,9) 与 (9,6)。",
        "trajectory": "回溯后第一阶段证据已经完整；错误发生在 SQL 阶段过度加工本可直接投影的两个端点字段。",
    },
    "242": {
        "primary": PRIMARY_FILTER,
        "origin": ORIGIN_SCHEMA,
        "exact": "新版最终用 SUBSTR(atom_id,8,1) BETWEEN '2' AND '9'，把目标 21-25 改成单数字 2-9；正确位置是 SQLite 1-based 的 SUBSTR(atom_id,7,2)。结果从 75 个分子扩大到 127 个。",
        "trajectory": "R10/R11 只查看 TR000 的前几个短 atom_id，错误归纳为全库只有一位后缀；R12 保存错误候选，R13 才查到 TR001_21 等真实值，但总预算已耗尽，fallback 仍选择 R12 的旧 SQL。",
    },
    "248": {
        "primary": PRIMARY_JOIN,
        "origin": ORIGIN_SCHEMA,
        "exact": "新版按 molecule_id 连接 atom 与 bond，返回 TR041 的全部 14 个原子；正确查询应通过 connected 找到与三键直接相连的 4 个 atom_id。",
        "trajectory": "第一阶段提交的 schema 证据只保留了 bond-molecule 和 bond-atom 的同名列候选，完全遗漏 connected 桥表。",
    },
    "255": {
        "primary": PRIMARY_PRECISION,
        "origin": ORIGIN_OUTPUT,
        "exact": "比例计算本身正确，但新版未执行 ROUND(...,5)，返回 39.75203409531189；gold/旧版按题意返回 39.75203。strict EX 比较实际数值，因此不是单纯列别名问题。",
        "trajectory": "第二阶段验证了未格式化的执行结果，却没有把“保留五位小数”作为终止前硬约束。",
    },
    "341": {
        "primary": PRIMARY_FILTER,
        "origin": ORIGIN_SQL,
        "exact": "正确条件是 cardKingdomFoilId IS NULL OR cardKingdomId IS NULL；新版写成 AND，要求两个字段同时为空，结果由 72 张缩到 37 张。",
        "trajectory": "schema 证据只分别记录两个 NULL 约束，没有保存二者在自然语言中的析取关系，SQL 阶段默认将条件合取。",
    },
    "366": {
        "primary": PRIMARY_OUTPUT,
        "origin": ORIGIN_OUTPUT,
        "exact": "新版正确找到 Benalish Knight 的规则文本，但额外输出 name；4 行文本值都对，结果从 1 列变成 2 列。",
        "trajectory": "模型把用于确认实体的 name 也保留在最终 SELECT，没有执行只返回 rule/text 的投影检查。",
    },
    "377": {
        "primary": PRIMARY_FILTER,
        "origin": ORIGIN_SCHEMA,
        "exact": "题意和 gold 是 subtypes != 'Angel'，因此 Angel,Spirit 两行与 Angel,Warrior 一行应计入，共 3。新版增加 NOT LIKE '%Angel%'，把所有包含 Angel 的复合 subtype 都排除，返回 0。",
        "trajectory": "inspect_value(pattern='Summon') 实际执行的是不带通配符的 LIKE 'Summon'，错误返回空；模型据此误判原始类型不存在，并在 SQL 阶段擅自强化 subtype 条件。",
    },
    "477": {
        "primary": PRIMARY_JOIN,
        "origin": ORIGIN_SCHEMA,
        "exact": "新版使用 cards.id = sets.id，正确连接是 cards.setCode = sets.code；错误连接使 Coldsnap 中三个候选艺术家返回 0 行，正确有 Chippy 与 Jeremy Jarvis 两行。",
        "trajectory": "inspect_join_candidate 只按同名列推荐双方主键 id=id，并标为 medium；第一阶段将该候选未经数据重叠验证就写入正式 joins。",
    },
    "479": {
        "primary": PRIMARY_JOIN,
        "origin": ORIGIN_SCHEMA,
        "exact": "同样错误使用 cards.id = sets.id 而不是 setCode=code，导致 Coldsnap 条件无匹配，unknown power 计数由 6 变成 0。COUNT 与 SUM(CASE) 的写法差异不是本题根因。",
        "trajectory": "第一阶段直接把同名主键候选升级为确定 join，后续即使执行结果为 0，也没有回溯验证 setCode/code。",
    },
    "530": {
        "primary": PRIMARY_OUTPUT,
        "origin": ORIGIN_OUTPUT,
        "exact": "新版漏掉题目要求的卡片 name，也漏掉 DISTINCT；只输出 frameVersion 和 YES/NO，legalities 的多行关系使结果膨胀到 1031 行，正确是 83 个不同的 frame/name/status 组合。",
        "trajectory": "第一阶段 schema 证据没有把 cards.name 纳入所需列，SQL 阶段也未根据问题中的 cards 复核输出契约。",
    },
    "549": {
        "primary": PRIMARY_JOIN,
        "origin": ORIGIN_SCHEMA,
        "exact": "新版按 tags.Id = posts.Id 连接，取到的是 tag 行同号的普通帖子正文；正确外键是 tags.ExcerptPostId = posts.Id。",
        "trajectory": "inspect_join_candidate 只发现同名主键 Id=Id；模型虽已读取 tags 元数据，却没有把 ExcerptPostId 的业务含义提升为 join 证据。",
    },
    "598": {
        "primary": PRIMARY_AGG,
        "origin": ORIGIN_SQL,
        "exact": "gold 以全部 Student badge 为共同分母，计算 2010 占比减 2011 占比；新版分别用各年份全部 badge 作分母，计算的是“每年 badge 中 Student 的占比差”，结果 -7.2785 而非 -9.5440。",
        "trajectory": "表和字段都正确，偏差来自第二阶段对 percentage difference 的分母口径重定义；执行成功没有提供语义校验信号。",
    },
    "604": {
        "primary": PRIMARY_OUTPUT,
        "origin": ORIGIN_OUTPUT,
        "exact": "前两列平均 UpVotes=182.2833、平均 Age=34.0833 与 gold 完全一致，但新版又添加 overall_average 第三列，strict EX 因结果形状失败。",
        "trajectory": "模型把问题中的两个 average 进一步合成为一个未被要求的总平均，终止前未检查 SELECT 项与问题要求的一一对应。",
    },
    "678": {
        "primary": PRIMARY_CONTROL,
        "origin": ORIGIN_SCHEMA,
        "exact": "最终 pred_sql 仍按 posts.OwnerDisplayName 过滤，返回空；正确路径是 users.DisplayName='Harvey Motulsky' 后通过 users.Id=posts.OwnerUserId 连接。",
        "trajectory": "第一阶段仅探索 posts。SQL 阶段 R8 才确认 users 中存在该用户，R9 已得到 Id=25，但六轮 SQL 预算恰好耗尽，来不及执行正确 join；fallback 选择了 R4 的空结果 SQL。这是已找到修复证据却无法提交修复的纯控制回归。",
    },
    "730": {
        "primary": PRIMARY_JOIN,
        "origin": ORIGIN_SCHEMA,
        "exact": "新版直接用 superhero.id = superpower.id，完全绕过 hero_power(hero_id,power_id)，所以 Marvel + Super Strength 返回 0 行；正确结果有 201 行。",
        "trajectory": "12 轮 schema 探索仍未读取 hero_power 元数据，反复把表名误当列名；SQL 阶段确认 id=id 无结果后直到最后一轮才 return_to_schema_stage，总预算已无剩余。",
    },
    "743": {
        "primary": PRIMARY_AGG,
        "origin": ORIGIN_SQL,
        "exact": "两个标量子查询本应只产生一行，但新版末尾又写 FROM superhero WHERE 1=1，把同一 (28.27,118) 重复 750 行；同时 ROUND(...,2) 还把 gold 的 28.266666... 截成 28.27。",
        "trajectory": "第一阶段关系完整；SQL 阶段没有意识到无关联外层扫描会复制标量结果，执行后只看单行预览便终止。",
    },
    "751": {
        "primary": PRIMARY_JOIN,
        "origin": ORIGIN_SCHEMA,
        "exact": "新版以 superhero.id = superpower.id 直接连接，漏掉 hero_power 桥表，只返回 123 条按碰巧同号匹配的能力；正确结果是男性英雄关联出的 4350 行能力记录。",
        "trajectory": "第一阶段把同名 id 候选写成正式 join，虽然已列出 hero_power 表，却未获取其元数据。",
    },
    "786": {
        "primary": PRIMARY_AGG,
        "origin": ORIGIN_SQL,
        "exact": "新版只过滤 attribute_name='Strength' 后 COUNT(DISTINCT hero_id)，再写 ORDER BY attribute_value DESC LIMIT 1；聚合已把所有记录压成一行，ORDER BY 无法筛出最大值，因此得到全部 623 名而非最大 strength 的 63 名。",
        "trajectory": "schema 证据正确，SQL 阶段把“排序取最大记录”和“统计所有达到最大值者”混成同一个无 GROUP BY 聚合。",
    },
    "792": {
        "primary": PRIMARY_JOIN,
        "origin": ORIGIN_SCHEMA,
        "exact": "新版直接 superhero.id = superpower.id，并额外输出 superhero_name，只得到错误的 Cold Resistance；正确路径经 hero_power 返回 Abomination 的 8 个 power_name。",
        "trajectory": "inspect_join_candidate 的双方主键 id=id 被当作关系证据，第一阶段未探索 hero_power。",
    },
    "825": {
        "primary": PRIMARY_JOIN,
        "origin": ORIGIN_SCHEMA,
        "exact": "提交的 schema_evidence 幻觉出 superhero.hero_power 列；实际能力是多对多 hero_power 表。六次 SQL 在 hero_power/superpower_id/superpower 等不存在列间来回切换，最后 fallback 退化为 SELECT * FROM superhero LIMIT 1，返回首个英雄整行而非 Female。",
        "trajectory": "记忆把 list_table_name 返回的表名 hero_power 误写成 superhero 的列，且错误反馈没有触发回到第一阶段，直到 SQL 预算耗尽。",
    },
    "847": {
        "primary": PRIMARY_TIME,
        "origin": ORIGIN_SQL,
        "exact": "SQLite 升序默认把 NULL 放在最前；新版 ORDER BY q2 ASC LIMIT 1 选到 q2=NULL 的 Fisichella。正确查询需 NULLS LAST 或 q2 IS NOT NULL，结果是 Räikkönen。",
        "trajectory": "字段和 join 都正确，第二阶段遗漏了可空计时字段的排序语义。",
    },
    "892": {
        "primary": PRIMARY_AGG,
        "origin": ORIGIN_SQL,
        "exact": "新版累计 SUM(driverStandings.points)。该表每轮保存累计积分快照，跨轮再求和会重复累计，Hamilton 得到 24509；gold/旧版按 results 的单场 points 求和，正确为 2510。",
        "trajectory": "第一阶段选择了名称更像“车手积分”的 driverStandings，却没有探查一名车手跨 raceId 的重复累计值，SQL 阶段未验证表的记录粒度。",
    },
    "967": {
        "primary": PRIMARY_TIME,
        "origin": ORIGIN_SQL,
        "exact": "新版按出生年份 ASC 取前三，实际选择最老车手；youngest 应按完整 dob DESC。最终 Dutch 计数为 0，正确为 1。",
        "trajectory": "多次 execute_sql 调整了查询结构，却始终没有纠正“日期越大越年轻”的排序方向。",
    },
    "981": {
        "primary": PRIMARY_TIME,
        "origin": ORIGIN_SQL,
        "exact": "新版子查询使用 MIN(dob)，选择最早出生的最老车手，再返回其 1994 年首次排位赛；正确应使用 MAX(dob) 选择最年轻车手，答案是 2017 Australian Grand Prix。",
        "trajectory": "schema 与连接正确，错误完全来自 oldest/youngest 与日期极值方向映射反了；后续子查询验证没有检查所选车手身份。",
    },
    "989": {
        "primary": PRIMARY_TIME,
        "origin": ORIGIN_SQL,
        "exact": "新版 SELECT races.time，返回赛事开始时间 17:00:00；问题问冠军的 finish time，应 SELECT results.time，正确为 1:36:24.227。",
        "trajectory": "两个表都已探索，但同名 time 字段没有做语义消歧，模型选了 race 级赛程时间。",
    },
    "1025": {
        "primary": PRIMARY_OUTPUT,
        "origin": ORIGIN_OUTPUT,
        "exact": "联赛名称 Spain LIGA BBVA 正确，但新版额外输出 total_goals=1043；gold 只要求联赛名，因此 2 列对 1 列失败。",
        "trajectory": "模型把用于 ORDER BY 的聚合指标保留在最终 SELECT，未执行 only-name 投影检查。",
    },
    "1030": {
        "primary": PRIMARY_OUTPUT,
        "origin": ORIGIN_OUTPUT,
        "exact": "联赛名称 France Ligue 1 正确，但新版额外输出 draw_count=108；正确结果只包含 name。",
        "trajectory": "与 qid1025 相同，排序辅助指标被错误暴露为答案列。",
    },
    "1039": {
        "primary": PRIMARY_JOIN,
        "origin": ORIGIN_SCHEMA,
        "exact": "新版用 Player.id = Player_Attributes.id，按两表独立主键碰巧连接，得到 66.0；正确键是 player_api_id（或 player_fifa_api_id），正确平均为 61.57142857。",
        "trajectory": "inspect_join_candidate 同时给出 id=id 和两个真实 API id 候选，模型因主键位置优先选择了第一个，却未做键覆盖/一对多验证。",
    },
    "1048": {
        "primary": PRIMARY_JOIN,
        "origin": ORIGIN_SCHEMA,
        "exact": "最终仍用 Player.id = Player_Attributes.player_api_id，两个不同标识域无法匹配 Gabriel Tamas，返回空；正确连接是两表 player_api_id。",
        "trajectory": "inspect_value 只能在单列上用 pattern，模型拿姓名去过滤数值 id 列当然为空，随后误推断该球员缺少 API id；schema 阶段耗尽后，SQL 阶段虽看到了正确字段名仍未建立正确键。",
    },
    "1080": {
        "primary": PRIMARY_AGG,
        "origin": ORIGIN_SQL,
        "exact": "问题问有至少一条满足条件记录的球员数，应 COUNT(DISTINCT player_api_id)=189；新版 COUNT(*) 统计所有属性快照，得到 1569。额外连接 Player 也没有消除重复。",
        "trajectory": "schema 正确，但第二阶段忽略 at least one record 所要求的实体级去重。",
    },
    "1091": {
        "primary": PRIMARY_FILTER,
        "origin": ORIGIN_SCHEMA,
        "exact": "新版硬编码 league_id=1729（England），而 Belgium Jupiler League 的 id 是 1，因此得到 40 场而非 36 场。",
        "trajectory": "inspect_value 只能分别查看 League.name 和 League.id，无法返回 name-id 配对；模型从 id 列表中无依据选了第二个值 1729，也没有保留 League join 到 SQL 阶段。",
    },
    "1102": {
        "primary": PRIMARY_JOIN,
        "origin": ORIGIN_SCHEMA,
        "exact": "新版既错用 Player_Attributes.player_api_id = Player.id，又把带时间的 date 值直接与 '2016-06-23' 比较，双重条件导致空结果；正确为 player_api_id 对 player_api_id，并用 SUBSTR/DATE/LIKE 匹配日期。",
        "trajectory": "第一阶段把真实 2016 数据误判为不存在，因为 inspect_value(pattern='2016') 没自动补 %；R16 后来查到 '2016-06-23 00:00:00'，但模型只改了 oldest 排序方向，没有修 join 和时间格式。",
    },
    "1148": {
        "primary": PRIMARY_AGG,
        "origin": ORIGIN_SQL,
        "exact": "新版计算“身高<180 的属性记录中 rating>70 的记录占比”40.66%；题目要求“球员中至少一次 rating>70 的球员占比”，应对分子分母都按不同 player 去重，正确为 51.15728564%。",
        "trajectory": "第一阶段关系正确，第二阶段把属性快照作为统计单位，没有把 at least one record 转成条件 DISTINCT player。",
    },
    "1150": {
        "primary": PRIMARY_TIME,
        "origin": ORIGIN_SQL,
        "exact": "Birthday > '1930-01-01' 会把 1930 年 1 月 2 日以后出生者也算入；born after 1930 按 gold 是年份严格大于 1930。新版 94.5259%，正确 94.0371%。",
        "trajectory": "表和值都正确，第二阶段把年份边界错误地转换成日期边界。",
    },
    "1162": {
        "primary": PRIMARY_TIME,
        "origin": ORIGIN_SQL,
        "exact": "First Date 保存完整日期，新版直接写 First Date='1997'，所以返回 0；正确需 STRFTIME('%Y', First Date)='1997'，结果为 61。",
        "trajectory": "第一阶段把要验证的语义值 1997 当成了字段真实存储值，第二阶段未检查日期样例格式。",
    },
    "1225": {
        "primary": PRIMARY_JOIN,
        "origin": ORIGIN_SCHEMA,
        "exact": "第一阶段幻觉出 Laboratory.PatientID，实际连接列是 Laboratory.ID=Patient.ID；SQL 还多次未正确引用带连字符的 \"T-BIL\"。六次执行均报错，最终 pred_sql 为空。",
        "trajectory": "结构化 schema 证据本身写错 join；错误恢复只在 ID 歧义、T-BIL 引号和不存在的 PatientID 之间轮换，没有触发 return_to_schema_stage。",
    },
    "1229": {
        "primary": PRIMARY_TIME,
        "origin": ORIGIN_SQL,
        "exact": "新版写 julianday(now)-julianday(Birthday)>50，把 50 年错成 50 天，得到 114；正确应 date(Birthday,'+50 years')<date('now') 或日差约 50*365.25，结果 107。",
        "trajectory": "schema 正确，错误是年龄单位在 SQL 翻译时丢失。",
    },
    "1238": {
        "primary": PRIMARY_TIME,
        "origin": ORIGIN_SQL,
        "exact": "oldest 应按 Birthday ASC 取最早出生日期；新版 DESC 取到最年轻患者，ID 1673252，而正确是 4792723。",
        "trajectory": "所有过滤和 join 均正确，唯一偏差是年龄与出生日期排序方向反转。",
    },
    "1247": {
        "primary": PRIMARY_AGG,
        "origin": ORIGIN_SQL,
        "exact": "新版 COUNT(*) 统计符合条件的 Laboratory 记录，重复计入同一患者，得到 16；正确是 COUNT(DISTINCT Patient.ID)=6。",
        "trajectory": "第二阶段没有把 how many patients 的统计粒度约束到患者实体。",
    },
    "1322": {
        "primary": PRIMARY_AGG,
        "origin": ORIGIN_SQL,
        "exact": "新版 GROUP BY event_id 后直接 COUNT(*)，返回每个合格会议的出席人数 23、25、30、31 四行；题目问这样的会议有多少，应再套一层 COUNT，正确标量为 4。",
        "trajectory": "SQL 执行成功后，模型把 HAVING 过滤出的分组内计数误当成分组数量。",
    },
    "1387": {
        "primary": PRIMARY_TIME,
        "origin": ORIGIN_SQL,
        "exact": "新版无依据添加 LIMIT 1，只返回 Sacha Harrison；gold 返回 Yearly Kickoff 预算相关的 4 行（按 set EX 为 3 个不同姓名）。",
        "trajectory": "模型按问题单数 Which student 过度收缩结果，而没有用执行结果验证该 event 对应多个 expense member。",
    },
    "1509": {
        "primary": PRIMARY_TIME,
        "origin": ORIGIN_SQL,
        "exact": "Date 按 ISO YYYY-MM-DD 存储，新版与斜杠字面量 '2012/1/1' 做文本比较，返回 0；应使用 DATE(Date) > '2012-01-01'，正确为 933。",
        "trajectory": "第一阶段已看到日期样例，但第二阶段照抄问题中的斜杠格式，没有规范化日期常量。",
    },
}


def load_rows(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON list: {path}")
    return data


def compact(text: Any, limit: int = 180) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def sql_block(sql: Any) -> str:
    text = str(sql or "").strip() or "（空：没有成功的最终 SQL）"
    return f"```sql\n{text}\n```"


def result_summary(result: Any) -> str:
    if not isinstance(result, dict):
        return "无结果对象"
    if not result.get("ok"):
        return f"执行失败：{result.get('error') or 'unknown error'}"
    columns = result.get("columns") or []
    rows = result.get("rows") or []
    count = result.get("row_count", result.get("row_count_preview", len(rows)))
    return f"列={columns}；行数={count}；前3行={rows[:3]}"


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def source_tooltip(value: Any, tooltip_id: str, files: str) -> str:
    return (
        f'<span class="source-tooltip" tabindex="0" aria-describedby="{tooltip_id}">{esc(value)}'
        f'<span class="source-tooltip-content" id="{tooltip_id}" role="tooltip">'
        f"Source: local evaluation artifacts<br>Files: {esc(files)}</span></span>"
    )


def svg_horizontal_bar(rows: list[dict[str, Any]], label_key: str, value_key: str, title: str) -> str:
    width, left, right, top, row_h = 960, 300, 72, 36, 42
    height = max(320, top * 2 + row_h * len(rows))
    maximum = max((float(row[value_key]) for row in rows), default=1.0) or 1.0
    plot_w = width - left - right
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">']
    for idx, row in enumerate(rows):
        y = top + idx * row_h
        value = float(row[value_key])
        bar_w = plot_w * value / maximum
        label = esc(row[label_key])
        rendered = str(int(value)) if value.is_integer() else f"{value:g}"
        parts.append(f'<text x="{left - 12}" y="{y + 20}" text-anchor="end" fill="currentColor" font-size="13">{label}</text>')
        parts.append(f'<rect x="{left}" y="{y + 4}" width="{bar_w:.2f}" height="24" rx="4" fill="#0169cc" opacity="0.86"/>')
        parts.append(f'<text x="{left + bar_w + 8:.2f}" y="{y + 21}" fill="currentColor" font-size="13">{rendered}</text>')
    parts.append("</svg>")
    return "".join(parts)


def chart_card(chart_id: str, title: str, subtitle: str, rows: list[dict[str, Any]], source_id: str) -> str:
    fallback = svg_horizontal_bar(rows, "label", "count", title)
    return f"""
    <figure class="card source-figure chart-card">
      <div class="card-head"><h3>{esc(title)}</h3><p>{esc(subtitle)}</p></div>
      <div class="chart-wrap"><div data-recharts-chart="{chart_id}">
        <div class="chart-fallback" data-recharts-fallback>{fallback}</div>
        <div data-recharts-live aria-hidden="true"></div>
      </div></div>
      <figcaption class="chart-note">横条长度表示题数；所有分类均按同一回归集合逐题复核。</figcaption>
      <button type="button" class="source-tooltip" aria-describedby="{source_id}">Source<span class="source-tooltip-content" id="{source_id}" role="tooltip">Source: local evaluation artifacts<br>Files: details.pretty.json, episodes.pretty.json, old_correct_new_wrong_49_report_data.json</span></button>
    </figure>"""


def chart_payload(chart_id: str, title: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": chart_id,
        "height": max(320, 64 + 42 * len(rows)),
        "type": "bar",
        "settings": {"orientation": "horizontal", "groupMode": "grouped"},
        "dataset": {
            "id": chart_id,
            "title": title,
            "data": rows,
            "chart_spec": {
                "id": chart_id,
                "dataset": chart_id,
                "title": title,
                "type": "bar",
                "encodings": {
                    "x": {"field": "label", "type": "nominal"},
                    "y": {"field": "count", "label": "题数", "type": "quantitative"},
                },
                "xAxisTitle": "",
                "yAxisTitle": "题数",
                "valueFormat": "number",
            },
        },
    }


def build_markdown(cases: list[dict[str, Any]], outcome_counts: Counter[tuple[bool, bool]]) -> str:
    primary_counts = Counter(case["analysis"]["primary"] for case in cases)
    origin_counts = Counter(case["analysis"]["origin"] for case in cases)
    db_counts = Counter(case["new"]["db_id"] for case in cases)
    lines = [
        "# 旧四阶段正确、新两阶段错误的 49 题回归分析",
        "",
        "## 结论",
        "",
        f"- 两版共同正确：{outcome_counts[(True, True)]}；旧错新对：{outcome_counts[(False, True)]}；旧对新错：{outcome_counts[(True, False)]}；两版共同错误：{outcome_counts[(False, False)]}。",
        "- 新版 strict EX 从 260/498（52.21%）提升到 288/498（57.83%），净增 28 题，但过程中新增了 49 个回归。",
        "- 49 题中，首次偏离来自第一阶段证据错误/不完整 20 题、第二阶段 SQL 语义推导 21 题、输出契约 7 题、执行错误修复未收敛 1 题。",
        "- 最突出的框架级问题是：候选 join 被提升为事实、inspect_value 无法返回关联列且 LIKE pattern 不自动补通配符、终止前没有投影/粒度/日期单位校验、预算耗尽时 fallback 固化旧 SQL。",
        "",
        "## 根因分布",
        "",
        "| 最终错法 | 题数 |",
        "|---|---:|",
    ]
    for label, count in primary_counts.most_common():
        lines.append(f"| {label} | {count} |")
    lines += ["", "| 首次偏离位置 | 题数 |", "|---|---:|"]
    for label, count in origin_counts.most_common():
        lines.append(f"| {label} | {count} |")
    lines += ["", "| 数据库 | 回归题数 |", "|---|---:|"]
    for label, count in db_counts.most_common():
        lines.append(f"| `{label}` | {count} |")

    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        grouped[case["new"]["db_id"]].append(case)
    for db_id in sorted(grouped):
        lines += ["", f"## {db_id}", ""]
        for case in sorted(grouped[db_id], key=lambda item: int(item["qid"])):
            qid, old, new, analysis = case["qid"], case["old"], case["new"], case["analysis"]
            lines += [
                f"### qid{qid}",
                "",
                f"- 问题：{new.get('question')}",
                f"- 最终错法：{analysis['primary']}",
                f"- 首次偏离：{analysis['origin']}",
                f"- 具体错误：{analysis['exact']}",
                f"- 轨迹原因：{analysis['trajectory']}",
                f"- 结果对照：gold {result_summary(new.get('gold_result'))}；new {result_summary(new.get('pred_result'))}",
                "",
                "旧版正确 SQL：",
                "",
                sql_block(old.get("pred_sql")),
                "",
                "新版错误 SQL：",
                "",
                sql_block(new.get("pred_sql")),
            ]
    return "\n".join(lines) + "\n"


def build_html(
    cases: list[dict[str, Any]],
    outcome_counts: Counter[tuple[bool, bool]],
    shell: str,
) -> tuple[str, dict[str, Any], str]:
    primary_counts = Counter(case["analysis"]["primary"] for case in cases)
    origin_counts = Counter(case["analysis"]["origin"] for case in cases)
    db_counts = Counter(case["new"]["db_id"] for case in cases)
    primary_rows = [{"label": key, "count": value} for key, value in primary_counts.most_common()]
    origin_rows = [{"label": key, "count": value} for key, value in origin_counts.most_common()]
    db_rows = [{"label": key, "count": value} for key, value in db_counts.most_common()]
    outcome_rows = [
        {"label": "两版共同正确", "count": outcome_counts[(True, True)]},
        {"label": "旧错新对", "count": outcome_counts[(False, True)]},
        {"label": "旧对新错", "count": outcome_counts[(True, False)]},
        {"label": "两版共同错误", "count": outcome_counts[(False, False)]},
    ]

    source_files = "details.pretty.json; episodes.pretty.json"
    metrics = [
        ("新版 strict EX", "288 / 498", f"正确率 {source_tooltip('57.83%', 'metric-note-new-rate', source_files)}，较旧版净增 {source_tooltip('28', 'metric-note-net', source_files)} 题"),
        ("旧版 strict EX", "260 / 498", f"正确率 {source_tooltip('52.21%', 'metric-note-old-rate', source_files)}"),
        ("旧对新错", "49", f"占全量 {source_tooltip('9.84%', 'metric-note-loss-share', source_files)}"),
        ("旧错新对", "77", f"抵消回归后净增 {source_tooltip('28', 'metric-note-net-repeat', source_files)} 题"),
    ]
    metric_html = "".join(
        f'<div class="metric"><div class="metric-label">{esc(label)}</div>'
        f'<div class="metric-value">{source_tooltip(value, f"metric-source-{idx}", source_files)}</div>'
        f'<div class="metric-note">{note}</div></div>'
        for idx, (label, value, note) in enumerate(metrics, start=1)
    )

    charts = "".join(
        [
            chart_card("outcome-state", "两版结果迁移", "按同一 question_id 对齐后的四种正确性状态", outcome_rows, "chart-source-outcome"),
            chart_card("primary-cause", "最终错误类型", "每题只分配一个直接导致 strict EX 失败的主错误", primary_rows, "chart-source-primary"),
            chart_card("first-divergence", "首次偏离发生在哪一层", "根据新版完整轨迹定位最早足以导致最终错误的环节", origin_rows, "chart-source-origin"),
            chart_card("database-concentration", "回归按数据库分布", "11 个 Arcwise-Plat 数据库中的旧对新错题数", db_rows, "chart-source-db"),
        ]
    )

    primary_table_rows = "".join(
        f"<tr><td>{esc(label)}</td><td>{source_tooltip(count, f'cause-source-{idx}', 'old_correct_new_wrong_49_report_data.json')}</td></tr>"
        for idx, (label, count) in enumerate(primary_counts.most_common(), start=1)
    )

    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        grouped[case["new"]["db_id"]].append(case)
    detail_parts: list[str] = []
    for db_id in sorted(grouped):
        detail_parts.append(f'<section class="case-group"><h2>{esc(db_id)}</h2>')
        for case in sorted(grouped[db_id], key=lambda item: int(item["qid"])):
            qid, old, new, analysis = case["qid"], case["old"], case["new"], case["analysis"]
            old_sql = str(old.get("pred_sql") or "（空）")
            new_sql = str(new.get("pred_sql") or "（空：没有成功的最终 SQL）")
            detail_parts.append(
                f"""<details class="case" id="qid{esc(qid)}">
                <summary><span class="qid">qid{esc(qid)}</span><span>{esc(new.get('question'))}</span></summary>
                <div class="case-body">
                  <div class="case-tags"><span>{esc(analysis['primary'])}</span><span>{esc(analysis['origin'])}</span>{source_tooltip('Source', f'case-source-{qid}', 'details.pretty.json; episodes.pretty.json; SQLite execution results')}</div>
                  <h3>新版具体错在哪里</h3><p>{esc(analysis['exact'])}</p>
                  <h3>为什么轨迹会走到这里</h3><p>{esc(analysis['trajectory'])}</p>
                  <div class="result-pair"><div><h3>gold_result</h3><pre>{esc(result_summary(new.get('gold_result')))}</pre></div><div><h3>new pred_result</h3><pre>{esc(result_summary(new.get('pred_result')))}</pre></div></div>
                  <div class="sql-pair"><div><h3>旧版正确 SQL</h3><pre>{esc(old_sql)}</pre></div><div><h3>新版错误 SQL</h3><pre>{esc(new_sql)}</pre></div></div>
                </div></details>"""
            )
        detail_parts.append("</section>")

    main = f"""
    <main data-report-audience="technical">
      <article class="reading">
        <div class="kicker">Text-to-SQL regression audit</div>
        <header data-contract-section="title"><h1>旧四阶段正确、新两阶段错误的 49 题</h1></header>
        <p class="deck">新版总体更准，但新增的 49 个回归主要来自 schema 证据质量、实体级聚合粒度、日期语义和终止前输出契约校验。</p>
        <section class="summary" data-contract-section="technical-summary">
          <div class="summary-label">Technical Summary</div>
          <div class="summary-body">
            <p><strong>净效果仍为正：</strong>新版从 {source_tooltip('260/498', 'summary-old', source_files)} 提升到 {source_tooltip('288/498', 'summary-new', source_files)}；{source_tooltip('77', 'summary-gains', source_files)} 道新增正确题抵消了 {source_tooltip('49', 'summary-losses', source_files)} 道回归，净增 28 题。</p>
            <p><strong>回归不是随机噪声：</strong>{source_tooltip('20', 'summary-origin-schema', 'old_correct_new_wrong_49_report_data.json')} 题最早源于第一阶段错误或不完整证据，{source_tooltip('21', 'summary-origin-sql', 'old_correct_new_wrong_49_report_data.json')} 题源于第二阶段语义推导，{source_tooltip('7', 'summary-origin-output', 'old_correct_new_wrong_49_report_data.json')} 题仅因输出契约，{source_tooltip('1', 'summary-origin-recovery', 'old_correct_new_wrong_49_report_data.json')} 题陷入语法修复循环。</p>
            <p><strong>最值得优先修：</strong>把 inspect_join_candidate 输出降级为待验证假设；让 inspect_value 支持关联列取值与明确 LIKE 语义；终止前增加投影列、实体粒度、日期单位和候选 SQL 新鲜度检查。</p>
          </div>
        </section>
        <section class="metrics">{metric_html}</section>
      </article>

      <section data-contract-section="key-findings">
        <article class="reading narrative"><h2>回归集中在可修复的协议边界</h2><p>错误 join/schema 关系占 {source_tooltip('16', 'finding-join-count', 'old_correct_new_wrong_49_report_data.json')} 题，是最大的直接错法；其中 {source_tooltip('9', 'finding-harmful-candidate', 'episodes.pretty.json; old_correct_new_wrong_49_report_data.json')} 题可直接追溯到同名列/主键候选被当成真实关系。日期/排序/字段语义有 {source_tooltip('10', 'finding-time-count', 'old_correct_new_wrong_49_report_data.json')} 题，聚合粒度有 {source_tooltip('9', 'finding-agg-count', 'old_correct_new_wrong_49_report_data.json')} 题，说明执行成功并不等于答案语义已被验证。</p></article>
        <div class="chart-stack">{charts}</div>
        <article class="reading narrative"><h2>输出契约本身就能挽回 {source_tooltip('7', 'finding-output-count', 'old_correct_new_wrong_49_report_data.json')} 题</h2><p>这些题的核心实体或数值已经正确，只因多输出 name、计数、总进球、第三邮箱，或未按五位小数格式化而失败。终止前对 SELECT 列与问题槽位做一一对应，是低成本且高确定性的改进。</p></article>
        <div class="wide"><section class="card table-card"><div class="card-head"><h3>最终错误类型汇总</h3><p>每题仅计入一个直接导致 strict EX 失败的主错误</p></div><div class="table-scroll"><table><thead><tr><th>错误类型</th><th>题数</th></tr></thead><tbody>{primary_table_rows}</tbody></table></div></section></div>
      </section>

      <article class="reading" data-contract-section="scope-data-and-metric-definitions">
        <section class="narrative"><h2>比较口径与数据范围</h2><p>旧版来源是四阶段 TRUST-SQL runner 的 498 条全量结果，新版来源是 S12/S6 两阶段 runner 的 498 条全量结果。按 question_id 对齐后，只纳入 old.correct=true 且 new.correct=false 的 49 题；正确性沿用 runner 保存的 strict EX，即 set(pred_rows) == set(gold_rows)。</p></section>
      </article>
      <article class="reading" data-contract-section="methodology">
        <section class="narrative"><h2>逐题判因方法</h2><p>每题同时比较 gold SQL、旧版正确 SQL、新版最终 SQL、gold/pred 执行结果、schema_evidence、阶段切换和完整 rounds。直接错法按最终结果唯一归类；首次偏离按轨迹中最早足以导致该错误的环节唯一归类。对 qid17、qid215、qid377 等反常结果另行执行 SQLite 诊断查询验证。</p></section>
      </article>
      <article class="reading" data-contract-section="limitations-uncertainty-and-robustness-checks">
        <section class="caveat"><strong>限制与稳健性。</strong>本报告解释的是这一次确定性全量运行中的 49 个回归，不代表各错误在不同采样种子下的发生概率。某些 gold SQL 体现的是 benchmark 的特定数据口径而非唯一自然语言解释；报告以 strict EX 控制源和实际 SQLite 结果为准。所有 49 个 qid、数据库与 correctness 字段已重新对齐，无缺失或重复。</section>
      </article>
      <article class="reading" data-contract-section="recommended-next-steps">
        <section class="narrative"><h2>优先修复顺序</h2><ol><li>候选 join 必须经过值重叠、基数或桥表验证后才能写入 schema evidence，尤其禁止把双方主键 id=id 自动升级为 medium 可用关系。</li><li>inspect_value 增加 paired lookup（按 name 返回 id）并明确 pattern 是 exact 还是 contains；当前接口导致 qid1091、1102、377 等错误证据。</li><li>terminate_second_stage 前执行 answer-contract validator：投影列数、实体去重、标量/分组形状、日期单位、精度与上一轮成功 SQL 新鲜度。</li><li>预算最后一轮若刚获得反证或修复证据，应保留一次强制 execute_sql，而不是 fallback 到已被后续证据否定的旧候选。</li></ol></section>
      </article>
      <article class="reading" data-contract-section="further-questions">
        <section class="narrative"><h2>下一轮实验应回答的问题</h2><p>最关键的消融是分别加入 join 验证、answer-contract validator 和“保留最终执行轮”预算策略，观察 49 题中各自能挽回多少，同时检查是否伤害现有 77 道新增正确题。</p></section>
      </article>
      <section class="case-details"><div class="reading"><h2>逐题明细</h2><p class="section-intro">展开任一 qid 可查看准确错因、轨迹起点、执行结果与两版 SQL。</p></div>{''.join(detail_parts)}</section>
    </main>
    """

    extra_css = """
    <style>
      .chart-stack { display: grid; gap: 22px; width: min(1040px, calc(100% - 32px)); margin: 22px auto 48px; }
      .chart-card { border-radius: 8px; }
      .chart-card .chart-wrap { padding-left: 28px; }
      .case-details { margin-top: 52px; padding: 44px 48px 60px; border-top: 1px solid var(--border-strong); background: var(--bg); }
      .section-intro { color: var(--secondary); }
      .case-group { width: min(1040px, 100%); margin: 36px auto 0; }
      .case-group > h2 { margin-bottom: 14px; }
      details.case { margin: 8px 0; border: 1px solid var(--border); border-radius: 8px; background: var(--surface); }
      details.case summary { display: grid; grid-template-columns: 84px 1fr; gap: 12px; padding: 14px 16px; cursor: pointer; font-weight: 600; }
      details.case[open] summary { border-bottom: 1px solid var(--border); }
      .qid { color: var(--blue); font-variant-numeric: tabular-nums; }
      .case-body { padding: 18px; }
      .case-body h3 { margin: 18px 0 5px; }
      .case-body p { margin: 0; color: var(--secondary); }
      .case-tags { display: flex; flex-wrap: wrap; gap: 8px; }
      .case-tags span { padding: 3px 8px; border: 1px solid var(--border-strong); border-radius: 999px; color: var(--secondary); font-size: 12px; }
      .sql-pair, .result-pair { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 16px; }
      pre { max-height: 320px; margin: 6px 0 0; padding: 12px; overflow: auto; border-radius: 6px; background: #111827; color: #f7f7f7; font: 12px/1.55 ui-monospace, SFMono-Regular, Menlo, monospace; white-space: pre-wrap; overflow-wrap: anywhere; }
      ol { padding-left: 22px; color: var(--secondary); }
      @media (max-width: 800px) { .case-details { padding: 32px 16px; } .sql-pair, .result-pair { grid-template-columns: 1fr; } details.case summary { grid-template-columns: 68px 1fr; } }
    </style>
    """
    report = shell.replace("<html lang=\"en\">", "<html lang=\"zh-CN\">")
    report = report.replace("{{TITLE}}", "旧四阶段正确、新两阶段错误的 49 题")
    report = report.replace("{{SOURCE_AND_DATE}}", "Arcwise-Plat · 498 questions · 2026-07-10")
    report = report.replace("<main data-report-audience=\"{{REPORT_AUDIENCE}}\">", "<main data-report-audience=\"technical\">")
    start = report.index("    <main data-report-audience=\"technical\">")
    end = report.index("    </main>", start) + len("    </main>")
    report = report[:start] + main + report[end:]
    report = report.replace("</head>", extra_css + "</head>")

    payload = {
        "charts": [
            chart_payload("outcome-state", "两版结果迁移", outcome_rows),
            chart_payload("primary-cause", "最终错误类型", primary_rows),
            chart_payload("first-divergence", "首次偏离发生在哪一层", origin_rows),
            chart_payload("database-concentration", "回归按数据库分布", db_rows),
        ]
    }
    notes = """# Report source notes

- Audience: technical.
- Comparison basis: strict EX fields from the old four-stage and new two-stage 498-question full runs, aligned by `question_id`.
- Primary sources: `details.pretty.json`, `episodes.pretty.json`, SQLite databases under `data/arcwise_plat/dev/dev_databases/`.
- Regression cohort: `old.correct == true && new.correct == false`.
- Chart map:
  - `outcome-state`: comparison bar; four correctness transition states across all 498 qids.
  - `primary-cause`: ranked horizontal bar; one direct strict-EX failure type per regression.
  - `first-divergence`: horizontal bar; earliest sufficient trajectory divergence per regression.
  - `database-concentration`: ranked horizontal bar; regression count by database.
- Palette: single blue root plus neutral text; labels and ordering provide non-color distinction.
- Robustness checks: 498 unique qids on both sides; exactly 49 regressions; CASE_ANALYSIS covers each regression exactly once; selected SQLite spot checks for qid17, qid215, and qid377.
- Limitation: case labels describe this concrete run and are not estimates of stochastic failure rates.
"""
    return report, payload, notes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old", type=Path, default=DEFAULT_OLD)
    parser.add_argument("--new", type=Path, default=DEFAULT_NEW)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--shell", type=Path, default=REPORT_SHELL)
    args = parser.parse_args()

    old_rows = load_rows(args.old)
    new_rows = load_rows(args.new)
    old_by_qid = {str(row["question_id"]): row for row in old_rows}
    new_by_qid = {str(row["question_id"]): row for row in new_rows}
    if len(old_by_qid) != 498 or len(new_by_qid) != 498 or set(old_by_qid) != set(new_by_qid):
        raise ValueError("Expected two aligned 498-qid full runs")

    regression_qids = {
        qid for qid in old_by_qid if bool(old_by_qid[qid].get("correct")) and not bool(new_by_qid[qid].get("correct"))
    }
    if regression_qids != set(CASE_ANALYSIS):
        missing = sorted(regression_qids - set(CASE_ANALYSIS), key=int)
        extra = sorted(set(CASE_ANALYSIS) - regression_qids, key=int)
        raise ValueError(f"CASE_ANALYSIS mismatch: missing={missing}, extra={extra}")

    cases = [
        {"qid": qid, "old": old_by_qid[qid], "new": new_by_qid[qid], "analysis": CASE_ANALYSIS[qid]}
        for qid in sorted(regression_qids, key=int)
    ]
    outcome_counts = Counter(
        (bool(old_by_qid[qid].get("correct")), bool(new_by_qid[qid].get("correct"))) for qid in old_by_qid
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    data_path = args.out_dir / "old_correct_new_wrong_49_report_data.json"
    markdown_path = args.out_dir / "old_correct_new_wrong_49_analysis.md"
    shell_path = args.out_dir / "old_correct_new_wrong_49_report_shell.html"
    payload_path = args.out_dir / "old_correct_new_wrong_49_report_payload.json"
    notes_path = args.out_dir / "old_correct_new_wrong_49_source_notes.md"

    serializable_cases = [
        {
            "question_id": case["qid"],
            "db_id": case["new"]["db_id"],
            "question": case["new"].get("question"),
            "primary_error": case["analysis"]["primary"],
            "first_divergence": case["analysis"]["origin"],
            "exact_error": case["analysis"]["exact"],
            "trajectory_cause": case["analysis"]["trajectory"],
            "old_sql": case["old"].get("pred_sql"),
            "new_sql": case["new"].get("pred_sql"),
            "gold_result": case["new"].get("gold_result"),
            "new_result": case["new"].get("pred_result"),
        }
        for case in cases
    ]
    data_path.write_text(json.dumps(serializable_cases, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(build_markdown(cases, outcome_counts), encoding="utf-8")
    report, payload, notes = build_html(cases, outcome_counts, args.shell.read_text(encoding="utf-8"))
    shell_path.write_text(report, encoding="utf-8")
    payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    notes_path.write_text(notes, encoding="utf-8")

    print(json.dumps({
        "regressions": len(cases),
        "outcome_counts": {f"{old}_{new}": count for (old, new), count in outcome_counts.items()},
        "primary_counts": dict(Counter(case["analysis"]["primary"] for case in cases)),
        "origin_counts": dict(Counter(case["analysis"]["origin"] for case in cases)),
        "markdown": str(markdown_path),
        "html_shell": str(shell_path),
        "payload": str(payload_path),
        "data": str(data_path),
        "notes": str(notes_path),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
