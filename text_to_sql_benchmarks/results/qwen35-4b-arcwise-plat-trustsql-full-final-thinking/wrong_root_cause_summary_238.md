# 238 个错题根因汇总

数据来源：`wrong_details.pretty.json` 以及 12 份逐题错因分析报告。

评测口径：本次脚本按执行结果行集合 EX 判断，行顺序不敏感；列数、列顺序和值必须一致。

说明：下面的“主因类型”是为了全局统计而做的单标签归类；一个样本可能同时有多个问题，逐题明细中的“简短错因”保留了更准确的根因描述。

## 覆盖校验

| 项 | 数量 |
| --- | ---: |
| wrong 样本数 | 238 |
| 汇总记录数 | 238 |
| unique qid 数 | 238 |
| 缺失 qid | 0 |
| 重复 qid | 0 |

## 按数据库统计

| 数据库 | 错题数 |
| --- | ---: |
| `formula_1` | 32 |
| `card_games` | 26 |
| `thrombosis_prediction` | 26 |
| `toxicology` | 24 |
| `california_schools` | 22 |
| `financial` | 21 |
| `codebase_community` | 20 |
| `debit_card_specializing` | 18 |
| `european_football_2` | 18 |
| `superhero` | 16 |
| `student_club` | 15 |

## 按主因类型统计

| 主因类型 | 数量 | 典型问题 |
| --- | ---: | --- |
| 输出形状/答案格式错误 | 81 | 多输出辅助列、姓名拼接成单列、YES/NO 未转换、列顺序不一致 |
| 聚合/公式/粒度错误 | 55 | COUNT/SUM/AVG 粒度错、分母错、百分比公式或整数除法错误 |
| 协议/轮数/收敛失败 | 26 | 10 轮内未生成 SQL、tool_call 截断、探索到答案后未收敛 |
| 类型/日期/NULL/值规范错误 | 23 | NULL/0 缺失值、日期含时间、时间格式、TEXT 数值 CAST、年龄计算 |
| 排序/TopK/Tie/排名错误 | 22 | LIMIT 1 漏并列、RANK/ROW_NUMBER 混用、排序方向或文本排序错误 |
| Schema/字段/Join 选择错误 | 16 | 错表错字段、join key 错、属性日期被路由到比赛日期等 |
| SQL 可执行性错误 | 10 | 语法错误、未定义 alias、SQLite 不支持函数、no such column |
| 筛选条件/业务约束错误 | 4 | 漏过滤条件、错加条件、阈值/范围解释错误 |
| 其他语义错误 | 1 | 不易归入单一主因的语义偏差，主要是评测侧异常 |

## 数据库 x 主因类型矩阵

| 数据库 | 输出形状/答案格式错误 | 聚合/公式/粒度错误 | 协议/轮数/收敛失败 | 类型/日期/NULL/值规范错误 | 排序/TopK/Tie/排名错误 | Schema/字段/Join 选择错误 | SQL 可执行性错误 | 筛选条件/业务约束错误 | 其他语义错误 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `formula_1` | 13 | 1 | 4 | 6 | 1 | 2 | 5 | 0 | 0 |
| `card_games` | 3 | 5 | 5 | 2 | 4 | 6 | 0 | 1 | 0 |
| `thrombosis_prediction` | 5 | 5 | 1 | 5 | 6 | 1 | 3 | 0 | 0 |
| `toxicology` | 9 | 8 | 2 | 1 | 2 | 2 | 0 | 0 | 0 |
| `california_schools` | 5 | 3 | 2 | 3 | 5 | 1 | 1 | 2 | 0 |
| `financial` | 3 | 16 | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| `codebase_community` | 8 | 3 | 1 | 1 | 1 | 4 | 0 | 1 | 1 |
| `debit_card_specializing` | 6 | 4 | 5 | 1 | 1 | 0 | 1 | 0 | 0 |
| `european_football_2` | 11 | 3 | 2 | 1 | 1 | 0 | 0 | 0 | 0 |
| `superhero` | 9 | 4 | 2 | 0 | 1 | 0 | 0 | 0 | 0 |
| `student_club` | 9 | 3 | 1 | 2 | 0 | 0 | 0 | 0 | 0 |

## 对后续 Text-to-SQL RL 改进最有价值的结论

1. **答案投影约束需要单独奖励/惩罚**：大量样本 SQL 找到了正确实体或数值，但多输出中间列，严格 EX 直接失败。
2. **TopK/Tie 应作为独立能力训练**：凡是“最高/最低/最多/最少/rank”类问题，模型常用 `LIMIT 1`，但 gold 经常要求所有并列。
3. **数据库值规范比 schema 名更关键**：日期是否含时间、数值是否 TEXT、缺失值是 `NULL` 还是 `0`，直接决定执行结果。
4. **多轮 agent 需要收敛奖励**：不少轨迹已经探索到正确中间结果，却继续诊断、错表路由，或在第 10 轮没有生成最终 SQL。
5. **聚合粒度应显式验证**：按 row、distinct entity、event/budget、group 后再比较，是本次错题中最常见的深层语义偏差之一。

## 238 条逐题明细

| qid | db | 主因类型 | 简短错因 | 来源 |
| ---: | --- | --- | --- | --- |
| 11 | `california_schools` | 类型/日期/NULL/值规范错误 | 缺 `schools.School IS NOT NULL`，多返回 2 条 district-level / 非学校记录。 | [california_schools_qid11_36_wrong_analysis.md](./california_schools_qid11_36_wrong_analysis.md#qid11) |
| 12 | `california_schools` | SQL 可执行性错误 | 最终 SQL 字段名引号写错导致执行失败；即使只修引号，还会因 SAT excellence rate 整数除法导致结果为空。 | [california_schools_qid11_36_wrong_analysis.md](./california_schools_qid11_36_wrong_analysis.md#qid12) |
| 23 | `california_schools` | 输出形状/答案格式错误 | 缺 `School IS NOT NULL` 多出 3 条非学校记录；同时多输出 City/Zip/State 等列。 | [california_schools_qid11_36_wrong_analysis.md](./california_schools_qid11_36_wrong_analysis.md#qid23) |
| 24 | `california_schools` | 输出形状/答案格式错误 | 缺 `rtype='S'`，混入 district-level SAT 记录；还用 `schools.School` 而非 `frpm."School Name"`，并多输出中间列。 | [california_schools_qid11_36_wrong_analysis.md](./california_schools_qid11_36_wrong_analysis.md#qid24) |
| 25 | `california_schools` | 筛选条件/业务约束错误 | 缺 `rtype='S'`，混入 Riverside County Office of Education 的 district-level 记录。 | [california_schools_qid11_36_wrong_analysis.md](./california_schools_qid11_36_wrong_analysis.md#qid25) |
| 27 | `california_schools` | 类型/日期/NULL/值规范错误 | 日期边界错：`OpenDate > '1991-01-01'` 包含 1991 年内学校；gold 是年份严格大于 1991。 | [california_schools_qid11_36_wrong_analysis.md](./california_schools_qid11_36_wrong_analysis.md#qid27) |
| 31 | `california_schools` | 输出形状/答案格式错误 | `LIMIT 11 OFFSET 9` 应为取 2 行；多输出列，并用 `ROUND(...,4)` 损失精度。 | [california_schools_qid11_36_wrong_analysis.md](./california_schools_qid11_36_wrong_analysis.md#qid31) |
| 32 | `california_schools` | 协议/轮数/收敛失败 | SQL 引号未闭合导致语法错误；修语法后还需只输出 rate 一列，不能输出学校名/计数中间列。 | [california_schools_qid11_36_wrong_analysis.md](./california_schools_qid11_36_wrong_analysis.md#qid32) |
| 36 | `california_schools` | 排序/TopK/Tie/排名错误 | 缺 `rtype='S'`，选到了 district-level SAT 汇总记录的管理员，而不是 school-level 最高记录。 | [california_schools_qid11_36_wrong_analysis.md](./california_schools_qid11_36_wrong_analysis.md#qid36) |
| 37 | `california_schools` | 排序/TopK/Tie/排名错误 | 没过滤 `NumGE1500 IS NOT NULL`，SQLite 升序把 NULL 排到最前；同时没有返回所有最低并列学校。 | [california_schools_qid37plus_wrong_analysis.md](./california_schools_qid37plus_wrong_analysis.md#qid37) |
| 39 | `california_schools` | Schema/字段/Join 选择错误 | 把 “Fresno schools” 误解为 `City='Fresno'`，gold 使用 `County='Fresno'`。 | [california_schools_qid37plus_wrong_analysis.md](./california_schools_qid37plus_wrong_analysis.md#qid39) |
| 40 | `california_schools` | 排序/TopK/Tie/排名错误 | 排序前没过滤 `AvgScrRead IS NOT NULL`，NULL 被排到最低分之前。 | [california_schools_qid37plus_wrong_analysis.md](./california_schools_qid37plus_wrong_analysis.md#qid40) |
| 41 | `california_schools` | 排序/TopK/Tie/排名错误 | 先过滤 virtual 再做 county 内排名，语义变成“各县 virtual 学校前 5”，gold 是“各县所有学校前 5 中的 virtual 学校”。 | [california_schools_qid37plus_wrong_analysis.md](./california_schools_qid37plus_wrong_analysis.md#qid41) |
| 46 | `california_schools` | 输出形状/答案格式错误 | 题目要最高 enrollment 的学校名 1 行，pred 返回所有 state special schools 且多输出列。 | [california_schools_qid37plus_wrong_analysis.md](./california_schools_qid37plus_wrong_analysis.md#qid46) |
| 48 | `california_schools` | 聚合/公式/粒度错误 | 分母范围错：pred 把 Elementary merged 也限制在 Orange County，gold 的分母是全州 merged Elementary 学校。 | [california_schools_qid37plus_wrong_analysis.md](./california_schools_qid37plus_wrong_analysis.md#qid48) |
| 50 | `california_schools` | 类型/日期/NULL/值规范错误 | `LIMIT 7 OFFSET 6` 返回 7 行；且缺 `rtype='S'` / `AvgScrMath IS NOT NULL`，只修 LIMIT 仍不是 gold。 | [california_schools_qid37plus_wrong_analysis.md](./california_schools_qid37plus_wrong_analysis.md#qid50) |
| 62 | `california_schools` | 聚合/公式/粒度错误 | 把 0.18% 当成 0.18 比例阈值；正确阈值等价于存储比例 `< 0.0018`。 | [california_schools_qid37plus_wrong_analysis.md](./california_schools_qid37plus_wrong_analysis.md#qid62) |
| 72 | `california_schools` | 聚合/公式/粒度错误 | 问的是学生数，应该 `SUM("Enrollment (Ages 5-17)")`，pred 用 `COUNT(*)` 数学校/记录。 | [california_schools_qid37plus_wrong_analysis.md](./california_schools_qid37plus_wrong_analysis.md#qid72) |
| 77 | `california_schools` | 协议/轮数/收敛失败 | 10 轮内没有生成/确认 SQL，最终 empty SQL；同时把 “served” 错对到 `GSoffered`，应为 `GSserved`。 | [california_schools_qid37plus_wrong_analysis.md](./california_schools_qid37plus_wrong_analysis.md#qid77) |
| 79 | `california_schools` | 排序/TopK/Tie/排名错误 | 缺 `LIMIT 1`，返回两个县而不是最多的一个县。 | [california_schools_qid37plus_wrong_analysis.md](./california_schools_qid37plus_wrong_analysis.md#qid79) |
| 83 | `california_schools` | 筛选条件/业务约束错误 | 错加了无关条件 `s.Magnet = 1`，把 2 所筛成 1 所。 | [california_schools_qid37plus_wrong_analysis.md](./california_schools_qid37plus_wrong_analysis.md#qid83) |
| 85 | `california_schools` | 输出形状/答案格式错误 | 输出列顺序反了；并且用存储比例 `0.7015`，gold 要百分数 `70.1513`。 | [california_schools_qid37plus_wrong_analysis.md](./california_schools_qid37plus_wrong_analysis.md#qid85) |
| 94 | `financial` | 协议/轮数/收敛失败 | 探索阶段没有收敛到核心 join 路径 `client -> disp -> account -> district`，并且被无关的 `order/trans/loan` 表和保留字表名错误分散，最终没有生成 SQL。 | [financial_wrong_analysis.md](./financial_wrong_analysis.md#qid94) |
| 95 | `financial` | 聚合/公式/粒度错误 | 模型知道 `client.birth_date` 和 `district.A11`，但没有建立 `client.client_id = disp.client_id`、`disp.account_id = account.account_id` 的关系，导致无法输出 account_id。 | [financial_wrong_analysis.md](./financial_wrong_analysis.md#qid95) |
| 98 | `financial` | 聚合/公式/粒度错误 | 自然语言 “approved loan date” 被误解成需要解析 loan status，模型没有直接按 `loan.date` 和 `account.frequency` 生成最终 SQL。 | [financial_wrong_analysis.md](./financial_wrong_analysis.md#qid98) |
| 99 | `financial` | 输出形状/答案格式错误 | 筛选和排序正确，但输出形状错。gold 只要 `account_id`；pred 多输出了 account opening date、loan amount、duration。 | [financial_wrong_analysis.md](./financial_wrong_analysis.md#qid99) |
| 100 | `financial` | 聚合/公式/粒度错误 | pred 用 `client.district_id = account.district_id` 连接，产生 client-account 笛卡尔式放大。gold 只在 `district -> client` 上计客户数，不应按同 district 的所有 account 重复客户。 | [financial_wrong_analysis.md](./financial_wrong_analysis.md#qid100) |
| 115 | `financial` | 类型/日期/NULL/值规范错误 | pred 对人口字段 `A4` 做了字符串排序，没有 `CAST(A4 AS INTEGER)`，选错了 south Bohemia 人口最多的 district；同时还做了 `ROUND(...,2)`。 | [financial_wrong_analysis.md](./financial_wrong_analysis.md#qid115) |
| 116 | `financial` | 聚合/公式/粒度错误 | 多轮推理停在定位 loan/account，没有完成数值计算阶段。正确应对 account 1787 在 `trans.date='1993-03-22'` 和 `1998-12-27` 的 balance 做 `(end-start)/start*100`。 | [financial_wrong_analysis.md](./financial_wrong_analysis.md#qid116) |
| 117 | `financial` | 聚合/公式/粒度错误 | 公式正确，但 pred 使用 `ROUND(...,2)`，gold 不四舍五入。严格 EX 下 `18.02` 不等于完整浮点。 | [financial_wrong_analysis.md](./financial_wrong_analysis.md#qid117) |
| 118 | `financial` | 聚合/公式/粒度错误 | 公式正确，但 pred 使用 `ROUND(...,2)`，gold 不四舍五入。 | [financial_wrong_analysis.md](./financial_wrong_analysis.md#qid118) |
| 125 | `financial` | 输出形状/答案格式错误 | - gold 要每个符合条件 loan 对应 district 的 increment，允许同一 district 因多个 loan 重复出现；pred `GROUP BY district` 去重了。 - pred 还 `ROUND(...,2)` 并多输出了 `district_id`。 - pred 没有显式过滤 `A12 IS NOT NULL AND A12 > 0`，可能引入额外空值/异常组。 | [financial_wrong_analysis.md](./financial_wrong_analysis.md#qid125) |
| 129 | `financial` | 输出形状/答案格式错误 | top ten withdrawals 指 top 10 笔非信用卡取款交易，不是 district 汇总排行。pred 聚合粒度错，并多输出汇总金额。 | [financial_wrong_analysis.md](./financial_wrong_analysis.md#qid129) |
| 136 | `financial` | 聚合/公式/粒度错误 | 与 q98 类似，模型把 “loans were approved” 过度解释成需要 status 映射；gold 只是对 `loan.date BETWEEN ...` 的已批准贷款记录计数，并结合 `account.frequency='POPLATEK MESICNE'` 与 amount 条件。 | [financial_wrong_analysis.md](./financial_wrong_analysis.md#qid136) |
| 137 | `financial` | 聚合/公式/粒度错误 | schema exploration 未进入 generate_sql。正确路径是 `account JOIN loan`，过滤 `account.district_id=1` 和 `loan.status IN ('C','D')` 后 count account。 | [financial_wrong_analysis.md](./financial_wrong_analysis.md#qid137) |
| 145 | `financial` | 聚合/公式/粒度错误 | - “account-holder identification numbers” 应走 `disp.type='OWNER'`，pred 按 district 错连 client。 - “overall average transaction amount in 1998” 是所有 1998 transactions 的平均，不是信用卡交易平均。 - pred 没有 `DISTINCT`，输出大量重复 client_id。 | [financial_wrong_analysis.md](./financial_wrong_analysis.md#qid145) |
| 149 | `financial` | 聚合/公式/粒度错误 | 字段位置识别错。账户资格类型在 `disp.type`，不是 `account` 表，也不是 `card.type`；非 eligible 即 `disp.type <> 'OWNER'`。 | [financial_wrong_analysis.md](./financial_wrong_analysis.md#qid149) |
| 152 | `financial` | 聚合/公式/粒度错误 | district-level 平均被 account 明细行重复加权。应先 `SELECT DISTINCT district_id`，再平均 district.A15。 | [financial_wrong_analysis.md](./financial_wrong_analysis.md#qid152) |
| 169 | `financial` | 聚合/公式/粒度错误 | 工具协议失败叠加未完成聚合。正确路径是 `loan -> account -> disp(type='OWNER') -> client(gender='M')`，按 loan year 1996/1997 分别 SUM(amount) 后计算增长率。 | [financial_wrong_analysis.md](./financial_wrong_analysis.md#qid169) |
| 173 | `financial` | 聚合/公式/粒度错误 | 模型把 “debiting 3539 in total” 误解成 `account_id=3539` 的交易查询；正确应在 `"order"` 表中对 account 3 的 debiting order amount 按 `k_symbol` 求和。 | [financial_wrong_analysis.md](./financial_wrong_analysis.md#qid173) |
| 186 | `financial` | 聚合/公式/粒度错误 | 字段位置错。weekly statements 对应 `account.frequency='POPLATEK TYDNE'`，应通过 `client -> disp -> account` 连接后按 distinct client 计算男性比例。 | [financial_wrong_analysis.md](./financial_wrong_analysis.md#qid186) |
| 189 | `financial` | 聚合/公式/粒度错误 | 与 q95 类似，模型缺少 `client -> disp -> account` join 收敛。正确排序是 `birth_date ASC, district.A11 ASC`，输出 account_id。 | [financial_wrong_analysis.md](./financial_wrong_analysis.md#qid189) |
| 192 | `financial` | 聚合/公式/粒度错误 | 字段位置错。statement issuance mode 是 `account.frequency`，不是 transaction operation；running contract 是 loan `status IN ('C','D')`。 | [financial_wrong_analysis.md](./financial_wrong_analysis.md#qid192) |
| 195 | `toxicology` | 输出形状/答案格式错误 | top bond type 判断正确，但输出形状错。gold 只要 `bond_type`；pred 多输出了 `COUNT(*)`。 | [toxicology_wrong_analysis.md](./toxicology_wrong_analysis.md#qid195) |
| 197 | `toxicology` | 聚合/公式/粒度错误 | 平均值分母错。题目问含单键分子的平均氧原子数，0 氧分子必须计入；pred 只平均了“至少有一个氧”的分子。 | [toxicology_wrong_analysis.md](./toxicology_wrong_analysis.md#qid197) |
| 200 | `toxicology` | 输出形状/答案格式错误 | 筛选正确，但输出形状错。gold 只要 `molecule_id`；pred 多输出了 `label`。 | [toxicology_wrong_analysis.md](./toxicology_wrong_analysis.md#qid200) |
| 201 | `toxicology` | 协议/轮数/收敛失败 | 先是元素值大小写错误，然后修复过程失控，探索 SQL 覆盖最终答案。正确查询应在含双键 molecule 的 atom 集合中计算 `COUNT(DISTINCT carbon atom_id) / COUNT(DISTINCT atom_id) * 100`。 | [toxicology_wrong_analysis.md](./toxicology_wrong_analysis.md#qid201) |
| 208 | `toxicology` | 输出形状/答案格式错误 | label 判断正确，但输出形状错。gold 只要 label；pred 多输出了 count。 | [toxicology_wrong_analysis.md](./toxicology_wrong_analysis.md#qid208) |
| 212 | `toxicology` | 排序/TopK/Tie/排名错误 | - pred `ORDER BY count ASC LIMIT 1` 只取一个最小值，没有处理并列最小元素。 - pred 还额外输出了 `count`。 | [toxicology_wrong_analysis.md](./toxicology_wrong_analysis.md#qid212) |
| 213 | `toxicology` | 协议/轮数/收敛失败 | 多轮修复/确认阶段倒退。模型已经找到答案，但最后用探索 SQL 覆盖了正确 SQL。 | [toxicology_wrong_analysis.md](./toxicology_wrong_analysis.md#qid213) |
| 218 | `toxicology` | 聚合/公式/粒度错误 | - pred 的 `COUNT(DISTINCT CASE WHEN a.element != 'f' THEN m.molecule_id END)` 不是“不含 fluorine”，而是“至少有一个非 fluorine 原子”。几乎所有 molecule 都满足。 - 题目要求 percentage，pred 输出了三个计数字段，没有返回百分比标量。 | [toxicology_wrong_analysis.md](./toxicology_wrong_analysis.md#qid218) |
| 219 | `toxicology` | 聚合/公式/粒度错误 | 分母粒度错。题目问 molecule 百分比，gold 按 distinct molecule_id 计算；pred 按 bond 行计算，而且 join 到 `molecule` 后还改变了分母集合。 | [toxicology_wrong_analysis.md](./toxicology_wrong_analysis.md#qid219) |
| 226 | `toxicology` | 聚合/公式/粒度错误 | 公式正确，但没有按题目要求和 gold SQL `ROUND(..., 5)` 保留五位小数。严格 EX 下完整浮点值不一致。 | [toxicology_wrong_analysis.md](./toxicology_wrong_analysis.md#qid226) |
| 227 | `toxicology` | 聚合/公式/粒度错误 | 公式正确，但没有 `ROUND(..., 3)`。严格 EX 下未四舍五入的浮点值不等于 gold。 | [toxicology_wrong_analysis.md](./toxicology_wrong_analysis.md#qid227) |
| 230 | `toxicology` | 输出形状/答案格式错误 | - gold 用 `DISTINCT element, label`；pred 没有 `DISTINCT`，输出每个 atom 明细行。 - 列顺序也反了：gold 是 `(element, label)`，pred 是 `(label, element)`。 | [toxicology_wrong_analysis.md](./toxicology_wrong_analysis.md#qid230) |
| 231 | `toxicology` | 输出形状/答案格式错误 | top bond type 判断正确，但输出形状错。gold 只要 `bond_type`；pred 多输出了 `bond_count`。 | [toxicology_wrong_analysis.md](./toxicology_wrong_analysis.md#qid231) |
| 234 | `toxicology` | 聚合/公式/粒度错误 | `connected` 表对每条 bond 存了两个方向，pred 用 `COUNT(*)` 把双向记录都算了；gold 用 `COUNT(DISTINCT bond_id)`。 | [toxicology_wrong_analysis.md](./toxicology_wrong_analysis.md#qid234) |
| 239 | `toxicology` | Schema/字段/Join 选择错误 | `connected` 表本身已经包含双向边。gold 只按 `atom_id` 这一方向计连接；pred 同时查 `atom_id` 和 `atom_id2`，把每条连接翻倍。 | [toxicology_wrong_analysis.md](./toxicology_wrong_analysis.md#qid239) |
| 243 | `toxicology` | 输出形状/答案格式错误 | 连接逻辑基本正确，输出形状错。gold 只要 `bond_id`；pred 多输出了 `bond_type`。 | [toxicology_wrong_analysis.md](./toxicology_wrong_analysis.md#qid243) |
| 244 | `toxicology` | 排序/TopK/Tie/排名错误 | - pred 写 `b.bond_type = ' = '`，多了空格；真实值是 `'='`，所以没有命中。 - 即使修正，也需要处理并列最大，gold 返回两个 label；pred 的 `LIMIT 1` 会漏掉 tie。 - pred 还额外输出了 `double_bond_count`。 | [toxicology_wrong_analysis.md](./toxicology_wrong_analysis.md#qid244) |
| 245 | `toxicology` | 聚合/公式/粒度错误 | 子查询里 `connected` 和 `atom` 都有 `atom_id`，pred 的 `SELECT atom_id ... GROUP BY atom_id` 未加表别名，SQLite 报歧义列。正确写法应使用 `atom.atom_id` 或 `connected.atom_id`。核查显示 iodine atom 有 6 个，join 到 connected 的 bond 行也是 6，平均为 1.0。 | [toxicology_wrong_analysis.md](./toxicology_wrong_analysis.md#qid245) |
| 249 | `toxicology` | 输出形状/答案格式错误 | 元素判断正确，但输出形状错。gold 只要 `element`；pred 多输出了 `atom_id`。 | [toxicology_wrong_analysis.md](./toxicology_wrong_analysis.md#qid249) |
| 253 | `toxicology` | Schema/字段/Join 选择错误 | join 路径错。题目问 triple bonds 的端点元素，不是含 triple bond molecule 的所有元素。 | [toxicology_wrong_analysis.md](./toxicology_wrong_analysis.md#qid253) |
| 263 | `toxicology` | 聚合/公式/粒度错误 | 参照集合不同。pred 没有通过 `molecule` 主表限定分子集合，额外纳入了只在 `bond/atom` 中出现的 molecule_id，导致百分比略变。 | [toxicology_wrong_analysis.md](./toxicology_wrong_analysis.md#qid263) |
| 281 | `toxicology` | 类型/日期/NULL/值规范错误 | SQLite `LIKE` 中 `_` 是单字符通配符，不是字面下划线。`LIKE '%_4'` 会匹配所有倒数第二个字符任意、最后为 4 的 atom_id，如 `_14`、`_24` 等。应使用 `substr(atom_id, -2) = '_4'` 或转义 `_`。 | [toxicology_wrong_analysis.md](./toxicology_wrong_analysis.md#qid281) |
| 282 | `toxicology` | 输出形状/答案格式错误 | ratio 数值和 label 都正确，但列顺序错误。gold 是 `(ratio, label)`；pred 是 `(label, hydrogen_ratio)`。 | [toxicology_wrong_analysis.md](./toxicology_wrong_analysis.md#qid282) |
| 327 | `toxicology` | 输出形状/答案格式错误 | 筛选集合正确，但输出形状错。gold 只要 `molecule_id`；pred 多输出了 `label` 和 `atom_count`。 | [toxicology_wrong_analysis.md](./toxicology_wrong_analysis.md#qid327) |
| 344 | `card_games` | 协议/轮数/收敛失败 | 多轮 schema exploration 没有收敛。模型未把 `cards` 和 `legalities` 的 `uuid` 关系转成最终查询，耗尽 10 轮。 | [card_games_wrong_analysis.md](./card_games_wrong_analysis.md#qid344) |
| 347 | `card_games` | 类型/日期/NULL/值规范错误 | 题目要求 “Find all cards”，即使没有 ruling 也要列出卡牌并给 `NULL` ruling；pred 用 inner join 丢掉了没有 ruling 的卡牌。 | [card_games_wrong_analysis.md](./card_games_wrong_analysis.md#qid347) |
| 349 | `card_games` | 输出形状/答案格式错误 | - pred `ORDER BY COUNT(...) DESC LIMIT 1` 只取一个 printing，漏掉同一最大 ruling 数下另一个 `isPromo` 状态。 - pred 把 `isPromo` 从整数 0/1 转成字符串 `Yes/No`，值类型也不匹配。 | [card_games_wrong_analysis.md](./card_games_wrong_analysis.md#qid349) |
| 352 | `card_games` | Schema/字段/Join 选择错误 | 表语义错。`set_translations` 是系列/卡包翻译，不是卡牌外文版本；应该使用 `foreign_data.language`。 | [card_games_wrong_analysis.md](./card_games_wrong_analysis.md#qid352) |
| 368 | `card_games` | 协议/轮数/收敛失败 | 计算公式基本正确，但 pred 使用 `ROUND(..., 2)` 截断精度。严格 EX 比较完整数值，`0.42` 不等于 `0.42413149836331`。 | [card_games_wrong_analysis.md](./card_games_wrong_analysis.md#qid368) |
| 371 | `card_games` | 排序/TopK/Tie/排名错误 | - pred 仍然使用 `set_translations`，把系列翻译当成卡牌语言。 - pred 还 `GROUP BY c.id ... LIMIT 1`，得到的是某一个卡牌/系列的局部比例，不是全体 Story Spotlight 卡牌的总体比例。 | [card_games_wrong_analysis.md](./card_games_wrong_analysis.md#qid371) |
| 383 | `card_games` | 排序/TopK/Tie/排名错误 | `legalities` 中同一张卡可在多个 format 下 banned，题目问 banned cards，应 `COUNT(DISTINCT cards.id)`；pred 用 `COUNT(*)` 统计了 format 明细行。 | [card_games_wrong_analysis.md](./card_games_wrong_analysis.md#qid383) |
| 391 | `card_games` | Schema/字段/Join 选择错误 | - pred join 条件写成 `c.id = fd.uuid`，但 `fd.uuid` 是文本 UUID，应使用 `c.uuid = fd.uuid`。 - pred 没有加 `c.colors = 'B'` 过滤。 - gold 要输出卡牌 `name`，pred 输出的是 `originalType/colors/language/foreign_text`。 | [card_games_wrong_analysis.md](./card_games_wrong_analysis.md#qid391) |
| 402 | `card_games` | 聚合/公式/粒度错误 | 模型把 “没有符合条件的明细行” 当成答案，但题目问 percentage。即使分子为 0，也应返回一个标量百分比 `0.0`，不是空结果集。 | [card_games_wrong_analysis.md](./card_games_wrong_analysis.md#qid402) |
| 407 | `card_games` | 类型/日期/NULL/值规范错误 | pred 误读了 “types” 的目标字段。应从英文主表 `cards` 输出 `subtypes, supertypes`，并只用 `foreign_data` 判断是否有 German 版本；pred 直接输出德语外文 `type` 字符串。 | [card_games_wrong_analysis.md](./card_games_wrong_analysis.md#qid407) |
| 408 | `card_games` | 聚合/公式/粒度错误 | - “ruling contains” 应查 `rulings.text`，不是 `foreign_data.text`。 - 布尔条件缺少括号，SQLite 中 `AND` 优先级高于 `OR`，导致所有 `power IS NULL` 的外文数据行都被计入。 - pred 用 `COUNT(*)`，不是去重卡牌数。 | [card_games_wrong_analysis.md](./card_games_wrong_analysis.md#qid408) |
| 412 | `card_games` | 筛选条件/业务约束错误 | 探索阶段过长，没有收敛到最终 SQL。正确路径是 `cards.uuid = foreign_data.uuid`，在 `cards` 上过滤 `types/layout/borderColor/artist`，在 `foreign_data` 上过滤 `language='French'` 并输出 `foreign_data.name`。 | [card_games_wrong_analysis.md](./card_games_wrong_analysis.md#qid412) |
| 415 | `card_games` | 聚合/公式/粒度错误 | - pred 使用大小写错误的状态值，导致空集合。 - pred 返回的是 `COUNT(*)`，不是 `hasContentWarning = 0` 在 commander Legal 卡中的百分比。 | [card_games_wrong_analysis.md](./card_games_wrong_analysis.md#qid415) |
| 416 | `card_games` | 聚合/公式/粒度错误 | 多轮生成失败；同时 schema 选择方向也错，把 `set_translations` 当成卡牌语言数据。正确应 `cards LEFT JOIN foreign_data ON uuid`，在 `power IS NULL OR power='*'` 人群中按 `DISTINCT cards.id` 算 French 占比。 | [card_games_wrong_analysis.md](./card_games_wrong_analysis.md#qid416) |
| 422 | `card_games` | Schema/字段/Join 选择错误 | 目标字段在 `foreign_data.multiverseid`，不是 `cards.multiverseId`。这里的 multiverse number 指外文数据行的 `multiverseid`，直接查 `foreign_data WHERE multiverseid = 149934` 即可。 | [card_games_wrong_analysis.md](./card_games_wrong_analysis.md#qid422) |
| 440 | `card_games` | 协议/轮数/收敛失败 | `A Pedra Fellwar` 本身是外文卡名，存在于 `foreign_data.name`，不是英文主表 `cards.name`。模型把外文名错当英文卡名，导致找不到目标后耗尽轮次。 | [card_games_wrong_analysis.md](./card_games_wrong_analysis.md#qid440) |
| 459 | `card_games` | 排序/TopK/Tie/排名错误 | pred 没有执行比较逻辑，没有 `ORDER BY convertedManaCost DESC LIMIT 1`，也额外输出了 `convertedManaCost`。 | [card_games_wrong_analysis.md](./card_games_wrong_analysis.md#qid459) |
| 465 | `card_games` | 输出形状/答案格式错误 | 集合本身正确，但输出形状错。gold 只要 set name；pred 多输出了 set code。 | [card_games_wrong_analysis.md](./card_games_wrong_analysis.md#qid465) |
| 469 | `card_games` | 输出形状/答案格式错误 | 筛选逻辑正确，输出形状错误。gold 只要 `sets.name`；pred 多输出了 `code` 和 `mtgoCode`。 | [card_games_wrong_analysis.md](./card_games_wrong_analysis.md#qid469) |
| 473 | `card_games` | 聚合/公式/粒度错误 | yes/no 题应做存在性聚合并始终返回一行，例如 `IIF(SUM(isForeignOnly)>0,'YES','NO')`。pred 直接过滤 `isForeignOnly=1` 输出明细；没有命中时返回空表，而不是 `NO`。 | [card_games_wrong_analysis.md](./card_games_wrong_analysis.md#qid473) |
| 480 | `card_games` | Schema/字段/Join 选择错误 | Italian card-level flavor text 在 `foreign_data.flavorText`，需要 `cards.uuid = foreign_data.uuid` 且 `foreign_data.language='Italian'`。pred 错用 `cards.flavorText` 和 `set_translations`，把英文主表文本和系列翻译混进答案。 | [card_games_wrong_analysis.md](./card_games_wrong_analysis.md#qid480) |
| 483 | `card_games` | 协议/轮数/收敛失败 | 多轮协议未完成最终 SQL。另一个潜在方向错误是模型一度关注 `rulings`；gold 实际使用的是 `foreign_data.text` 中的 Italian 卡牌文本，而不是 `rulings.text`。 | [card_games_wrong_analysis.md](./card_games_wrong_analysis.md#qid483) |
| 484 | `card_games` | Schema/字段/Join 选择错误 | - Italian card names 应来自 `foreign_data.name`，不是 `set_translations.translation`。后者是 set 名 “Coldsnap” 的意大利语翻译，会被重复贴到每张卡上。 - pred 额外输出了英文 `cards.name` 和 `convertedManaCost`。 | [card_games_wrong_analysis.md](./card_games_wrong_analysis.md#qid484) |
| 487 | `card_games` | 协议/轮数/收敛失败 | 工具协议失败和轮数耗尽。正确查询只需 `cards JOIN sets ON setCode=code WHERE sets.name='Coldsnap'` 后做条件百分比。 | [card_games_wrong_analysis.md](./card_games_wrong_analysis.md#qid487) |
| 518 | `card_games` | 排序/TopK/Tie/排名错误 | - 评测层面：gold SQL 超时，导致该样本无法通过 EX。 - 模型层面：pred 用 `GROUP BY l.format, c.name ORDER BY COUNT(*) DESC LIMIT 1`，比较的是单个 `(format, card)` 分组的计数，且只返回一行；应先按 `format` 聚合找 banned 数最多的 format，再列出该 format 下所有 banned 卡名。 | [card_games_wrong_analysis.md](./card_games_wrong_analysis.md#qid518) |
| 529 | `card_games` | Schema/字段/Join 选择错误 | 表语义和集合差集都错。应在 `foreign_data` 的卡牌 `uuid` 级别做 `Korean EXCEPT Japanese`；pred 在 set 翻译表上做了恒真过滤，几乎把所有韩语系列下的卡都输出了。 | [card_games_wrong_analysis.md](./card_games_wrong_analysis.md#qid529) |
| 531 | `codebase_community` | 输出形状/答案格式错误 | pred 只列出两人的 reputation，没有做 `MAX(Reputation)` 筛选；同时多输出了 `Reputation`。正确应只输出 reputation 更高者的 `DisplayName`。 | [codebase_community_wrong_analysis.md](./codebase_community_wrong_analysis.md#qid531) |
| 533 | `codebase_community` | 类型/日期/NULL/值规范错误 | pred 没有按 evidence 使用 `date(LastAccessDate)`，把 2014-09-01 当天但带时间的访问也算进去了。 | [codebase_community_wrong_analysis.md](./codebase_community_wrong_analysis.md#qid533) |
| 565 | `codebase_community` | 输出形状/答案格式错误 | 判断逻辑正确，但输出形状错。gold 只要 `YES/NO` 一列；pred 多输出了 post id、comment date 和 closed date。 | [codebase_community_wrong_analysis.md](./codebase_community_wrong_analysis.md#qid565) |
| 567 | `codebase_community` | 输出形状/答案格式错误 | 计数正确，但输出形状错。gold 只要 count；pred 多输出了 user id。 | [codebase_community_wrong_analysis.md](./codebase_community_wrong_analysis.md#qid567) |
| 571 | `codebase_community` | 聚合/公式/粒度错误 | 两个独立计数被错误 join，产生笛卡尔乘法。应分别聚合 posts 和 votes，再相除。 | [codebase_community_wrong_analysis.md](./codebase_community_wrong_analysis.md#qid571) |
| 581 | `codebase_community` | 输出形状/答案格式错误 | owner 定位正确，但输出形状错。gold 只要 `DisplayName`；pred 多输出了 `OwnerUserId`。 | [codebase_community_wrong_analysis.md](./codebase_community_wrong_analysis.md#qid581) |
| 584 | `codebase_community` | 输出形状/答案格式错误 | 核心 comment 集合正确，`Comment IS NOT NULL` 没有排掉空字符串；失败来自输出形状，pred 多输出了编辑用户和时间。 | [codebase_community_wrong_analysis.md](./codebase_community_wrong_analysis.md#qid584) |
| 586 | `codebase_community` | Schema/字段/Join 选择错误 | pred 把“添加 bounty 的用户”错当成“post owner”，join 到 `posts.OwnerUserId`；正确应使用 `votes.UserId -> users.Id`。 | [codebase_community_wrong_analysis.md](./codebase_community_wrong_analysis.md#qid586) |
| 587 | `codebase_community` | 输出形状/答案格式错误 | tag 匹配口径错。题目/gold 是只要 tag 字符串等于 `<humor>` 的帖子；pred 做了包含匹配，扩大了帖子和评论集合。 | [codebase_community_wrong_analysis.md](./codebase_community_wrong_analysis.md#qid587) |
| 595 | `codebase_community` | 输出形状/答案格式错误 | 用户集合正确，但输出形状错。gold 只要 `UserId`；pred 多输出了 display name、views 和 distinct post history type count。 | [codebase_community_wrong_analysis.md](./codebase_community_wrong_analysis.md#qid595) |
| 634 | `codebase_community` | 筛选条件/业务约束错误 | pred 错用 `posts.OwnerDisplayName` 过滤作者，导致找不到 Harvey Motulsky / Noah Snyder 的帖子。 | [codebase_community_wrong_analysis.md](./codebase_community_wrong_analysis.md#qid634) |
| 637 | `codebase_community` | 协议/轮数/收敛失败 | 同 q634，作者显示名字段位置错。模型没有改用 `users` join，探索耗尽 10 轮。 | [codebase_community_wrong_analysis.md](./codebase_community_wrong_analysis.md#qid637) |
| 639 | `codebase_community` | Schema/字段/Join 选择错误 | pred 同时过滤 `OwnerUserId=18164` 和 `OwnerDisplayName='user1140126'`，只保留了一个 owner display name 被填充的 post；应 join `users` 并仅按 `users.DisplayName` 过滤。 | [codebase_community_wrong_analysis.md](./codebase_community_wrong_analysis.md#qid639) |
| 640 | `codebase_community` | 聚合/公式/粒度错误 | pred 错用 `posts.OwnerDisplayName='Amos'`，该字段为空导致 SUM over empty set 为 NULL；同时没有计算 Mornington - Amos 的差值。 | [codebase_community_wrong_analysis.md](./codebase_community_wrong_analysis.md#qid640) |
| 671 | `codebase_community` | 排序/TopK/Tie/排名错误 | tie 处理错误。pred `ORDER BY b.Date ASC LIMIT 1` 只取一人；gold 要所有 `b.Date = MIN(Date)` 的用户。 | [codebase_community_wrong_analysis.md](./codebase_community_wrong_analysis.md#qid671) |
| 682 | `codebase_community` | Schema/字段/Join 选择错误 | post id 定位正确，但 owner display name 取错字段。注册用户应 join `users`，不能直接用 `posts.OwnerDisplayName`。 | [codebase_community_wrong_analysis.md](./codebase_community_wrong_analysis.md#qid682) |
| 683 | `codebase_community` | 聚合/公式/粒度错误 | - 字段名错：posts 表创建时间列拼作 `CreaionDate`，pred 使用 `CreationDate`，SQLite 解析到了 `users.CreationDate`。 - 分母错：gold 分母是全部 posts，pred join users 后的 `COUNT(*)` 排除了没有 owner user 的 posts。 | [codebase_community_wrong_analysis.md](./codebase_community_wrong_analysis.md#qid683) |
| 694 | `codebase_community` | Schema/字段/Join 选择错误 | 评论文本和排序正确，但 commenter display name 取错字段。注册用户的显示名应 `comments.UserId -> users.Id`，不是 `comments.UserDisplayName`。 | [codebase_community_wrong_analysis.md](./codebase_community_wrong_analysis.md#qid694) |
| 701 | `codebase_community` | 其他语义错误 | - 评测层面：gold SQL 超时，导致该样本不能通过 EX。 - 模型层面：语义基本对，但 pred 进行了 `ROUND(...,2)`；若 gold 可执行，严格 EX 仍会因精度不一致失败。 | [codebase_community_wrong_analysis.md](./codebase_community_wrong_analysis.md#qid701) |
| 707 | `codebase_community` | 输出形状/答案格式错误 | 排序和目标 comment 正确，输出形状错。gold 只要 `Text`；pred 多输出了大量上下文字段。 | [codebase_community_wrong_analysis.md](./codebase_community_wrong_analysis.md#qid707) |
| 723 | `superhero` | 协议/轮数/收敛失败 | 探索效率和阶段收敛失败。模型知道需要 `superhero.eye_colour_id -> colour.id` 和 `hero_power.power_id -> superpower.id`，但在 schema 探索中重复绕路，10 轮内没有组合成最终 count SQL。 | [superhero_wrong_analysis.md](./superhero_wrong_analysis.md#qid723) |
| 726 | `superhero` | 输出形状/答案格式错误 | pred 只过滤 `height_cm IS NOT NULL`，没有按 gold/evidence 排除 `height_cm = 0` 的缺失身高；同时多输出 `height_cm`。 | [superhero_wrong_analysis.md](./superhero_wrong_analysis.md#qid726) |
| 728 | `superhero` | 排序/TopK/Tie/排名错误 | ranking function 错误。题目要“rank”，gold 使用并列同 rank 的 `RANK()`；pred 使用 `ROW_NUMBER()`，把并列颜色强行排成不同名次。 | [superhero_wrong_analysis.md](./superhero_wrong_analysis.md#qid728) |
| 736 | `superhero` | 输出形状/答案格式错误 | 并列最小值处理错误。最低 Intelligence attribute value = 35，有 3 个英雄并列；pred 使用 `ORDER BY attribute_value ASC LIMIT 1` 只返回一人。同时 pred 多输出 `full_name`、attribute name 和 attribute value。 | [superhero_wrong_analysis.md](./superhero_wrong_analysis.md#qid736) |
| 738 | `superhero` | 输出形状/答案格式错误 | 筛选逻辑正确，失败来自输出形状。gold 只要 `superhero_name`；pred 多输出 `full_name` 和 durability value。 | [superhero_wrong_analysis.md](./superhero_wrong_analysis.md#qid738) |
| 744 | `superhero` | 输出形状/答案格式错误 | pred 没有输出“更多的是哪个 publisher”，而是输出两个中间计数；并且差值方向写成 `DC - Marvel`，与本题 gold 的 `Marvel - DC` 相反。 | [superhero_wrong_analysis.md](./superhero_wrong_analysis.md#qid744) |
| 750 | `superhero` | 聚合/公式/粒度错误 | 缺失值过滤错误。gold 使用 `weight_kg > 0` 排除缺失体重；pred 直接 `AVG(weight_kg)`，把 `0` 当真实体重参与平均。 | [superhero_wrong_analysis.md](./superhero_wrong_analysis.md#qid750) |
| 769 | `superhero` | 输出形状/答案格式错误 | 最高 durability 英雄定位正确，失败来自输出形状。gold 只要 superhero name；pred 多输出 max durability。 | [superhero_wrong_analysis.md](./superhero_wrong_analysis.md#qid769) |
| 775 | `superhero` | 聚合/公式/粒度错误 | 百分比精度错误。计算口径正确，但 pred 使用 `ROUND(..., 2)`，gold 保留完整浮点值。 | [superhero_wrong_analysis.md](./superhero_wrong_analysis.md#qid775) |
| 788 | `superhero` | 聚合/公式/粒度错误 | 百分比精度错误。计算口径正确，但 pred 使用 `ROUND(..., 2)`，导致与 gold 浮点结果不完全一致。 | [superhero_wrong_analysis.md](./superhero_wrong_analysis.md#qid788) |
| 791 | `superhero` | 聚合/公式/粒度错误 | 缺失值过滤错误。gold 使用 `height_cm > 0`；pred 直接 `AVG(height_cm)`。 | [superhero_wrong_analysis.md](./superhero_wrong_analysis.md#qid791) |
| 794 | `superhero` | 输出形状/答案格式错误 | 并列最大值处理错误。pred 使用 `ORDER BY attribute_value DESC LIMIT 1`，只返回一个最快英雄；gold 用 max subquery 保留全部 speed 最大者。同时 pred 多输出 attribute value。 | [superhero_wrong_analysis.md](./superhero_wrong_analysis.md#qid794) |
| 798 | `superhero` | 输出形状/答案格式错误 | publisher 判断正确，失败来自输出形状。gold 只要求 publisher name；pred 多输出 superhero name。由于评测按 row tuple 比较，`('DC Comics',)` 和 `('DC Comics', 'Hawkman')` 不相等。 | [superhero_wrong_analysis.md](./superhero_wrong_analysis.md#qid798) |
| 800 | `superhero` | 协议/轮数/收敛失败 | schema 名称归一化失败。数据库实际使用英式拼写 `colour`，pred 持续搜索不存在的 `color` 表，导致探索卡死。 | [superhero_wrong_analysis.md](./superhero_wrong_analysis.md#qid800) |
| 819 | `superhero` | 输出形状/答案格式错误 | 差值计算正确，失败来自输出形状。gold 只要最终 difference；pred 多输出两个中间计数。 | [superhero_wrong_analysis.md](./superhero_wrong_analysis.md#qid819) |
| 829 | `superhero` | 输出形状/答案格式错误 | 差值方向与 gold 一致，但 pred 没有输出“更多的是哪个 publisher”，而是输出了两个中间计数；输出形状不匹配。 | [superhero_wrong_analysis.md](./superhero_wrong_analysis.md#qid829) |
| 854 | `formula_1` | 输出形状/答案格式错误 | 多输出 circuit/race name，且缺 `DISTINCT`，导致同一坐标重复 11 次。 | [formula_1_wrong_analysis.md](./formula_1_wrong_analysis.md#qid854) |
| 861 | `formula_1` | 类型/日期/NULL/值规范错误 | 查到了匹配 Q3 时间，但没有 join `drivers` 返回 `driver.number`，而是返回 q3 时间本身。 | [formula_1_wrong_analysis.md](./formula_1_wrong_analysis.md#qid861) |
| 866 | `formula_1` | 类型/日期/NULL/值规范错误 | 时间格式误读：数据库用 `1:27%`，pred 用 `0:01:27%`，结果为空。 | [formula_1_wrong_analysis.md](./formula_1_wrong_analysis.md#qid866) |
| 872 | `formula_1` | 类型/日期/NULL/值规范错误 | 没按 `q3 LIKE '1:33%'` 过滤并 join drivers，返回了整场 q3 列表。 | [formula_1_wrong_analysis.md](./formula_1_wrong_analysis.md#qid872) |
| 877 | `formula_1` | 输出形状/答案格式错误 | 年龄排序方向反了，`dob ASC` 选到最老；还多输出 dob。 | [formula_1_wrong_analysis.md](./formula_1_wrong_analysis.md#qid877) |
| 879 | `formula_1` | 类型/日期/NULL/值规范错误 | `fastestLapSpeed` 是 TEXT，pred 按字符串排序，未 `CAST(... AS REAL)`。 | [formula_1_wrong_analysis.md](./formula_1_wrong_analysis.md#qid879) |
| 881 | `formula_1` | SQL 可执行性错误 | 未 join `status` 表，却引用 `res.status`，SQL 执行失败。 | [formula_1_wrong_analysis.md](./formula_1_wrong_analysis.md#qid881) |
| 884 | `formula_1` | SQL 可执行性错误 | 最后一轮用了 SQLite 不存在的 `month()` 函数，并多输出 date/year/month；上一轮正确思路被覆盖。 | [formula_1_wrong_analysis.md](./formula_1_wrong_analysis.md#qid884) |
| 897 | `formula_1` | Schema/字段/Join 选择错误 | 用 `results.points` 求和当作最大积分；gold 要 `driverStandings` 中 `MAX(points)`。 | [formula_1_wrong_analysis.md](./formula_1_wrong_analysis.md#qid897) |
| 898 | `formula_1` | 输出形状/答案格式错误 | 年龄计算硬编码 2024，且输出列顺序/形状错；gold 用当前时间。 | [formula_1_wrong_analysis.md](./formula_1_wrong_analysis.md#qid898) |
| 902 | `formula_1` | 输出形状/答案格式错误 | 筛选语义对，但多输出 position 和 raceId；gold 只要 race name。 | [formula_1_wrong_analysis.md](./formula_1_wrong_analysis.md#qid902) |
| 906 | `formula_1` | 输出形状/答案格式错误 | 筛选语义对，但多输出 race date；gold 只要 race name 和 points。 | [formula_1_wrong_analysis.md](./formula_1_wrong_analysis.md#qid906) |
| 909 | `formula_1` | 输出形状/答案格式错误 | 百分比算对但多输出分子/分母，并 `ROUND` 到两位导致精度不一致。 | [formula_1_wrong_analysis.md](./formula_1_wrong_analysis.md#qid909) |
| 915 | `formula_1` | 类型/日期/NULL/值规范错误 | 未过滤 `dob IS NOT NULL`，NULL 被排在最前。 | [formula_1_wrong_analysis.md](./formula_1_wrong_analysis.md#qid915) |
| 930 | `formula_1` | SQL 可执行性错误 | SQL alias 写错，引用未定义的 `r.name/r.year`；修后仍会多输出 year。 | [formula_1_wrong_analysis.md](./formula_1_wrong_analysis.md#qid930) |
| 937 | `formula_1` | 输出形状/答案格式错误 | 找到第二名完赛时间，但多输出 driver forename/surname。 | [formula_1_wrong_analysis.md](./formula_1_wrong_analysis.md#qid937) |
| 944 | `formula_1` | 协议/轮数/收敛失败 | 复杂时间差题 10 轮内没有产出 SQL，最终 empty SQL。 | [formula_1_wrong_analysis.md](./formula_1_wrong_analysis.md#qid944) |
| 948 | `formula_1` | Schema/字段/Join 选择错误 | 用错表：pred 查 `constructorResults.points`，gold 查 `constructorStandings.points`。 | [formula_1_wrong_analysis.md](./formula_1_wrong_analysis.md#qid948) |
| 951 | `formula_1` | 聚合/公式/粒度错误 | 语义基本找到 Kojima，但输出 constructorId/name/race_count/points；gold 只输出计数。 | [formula_1_wrong_analysis.md](./formula_1_wrong_analysis.md#qid951) |
| 954 | `formula_1` | SQL 可执行性错误 | 未 join `status` 表，却引用 `res.status`，SQL 执行失败；分子分母粒度也会错。 | [formula_1_wrong_analysis.md](./formula_1_wrong_analysis.md#qid954) |
| 955 | `formula_1` | SQL 可执行性错误 | 手写时间解析 SQL 语法错误，且误用 `races.time`；gold 直接用 champion `results.milliseconds`。 | [formula_1_wrong_analysis.md](./formula_1_wrong_analysis.md#qid955) |
| 959 | `formula_1` | 输出形状/答案格式错误 | 找到 champion fastestLap，但多输出 raceId 和 race name。 | [formula_1_wrong_analysis.md](./formula_1_wrong_analysis.md#qid959) |
| 960 | `formula_1` | 协议/轮数/收敛失败 | 10 轮内未生成最终 SQL，empty SQL。 | [formula_1_wrong_analysis.md](./formula_1_wrong_analysis.md#qid960) |
| 962 | `formula_1` | 类型/日期/NULL/值规范错误 | 完全跑偏成探索出生年份列表，没有计算 2000-2005 race result percentage。 | [formula_1_wrong_analysis.md](./formula_1_wrong_analysis.md#qid962) |
| 972 | `formula_1` | 输出形状/答案格式错误 | 把“has fastest lap time”误解为每场最快 lapTimes；gold 只要求 `results.fastestLapTime IS NOT NULL`。 | [formula_1_wrong_analysis.md](./formula_1_wrong_analysis.md#qid972) |
| 978 | `formula_1` | 输出形状/答案格式错误 | 多输出 circuit name，且缺 `DISTINCT`，同一 location/coordinate 重复。 | [formula_1_wrong_analysis.md](./formula_1_wrong_analysis.md#qid978) |
| 988 | `formula_1` | 输出形状/答案格式错误 | 排序语义对，但多输出 nationality/dob/avg duration。 | [formula_1_wrong_analysis.md](./formula_1_wrong_analysis.md#qid988) |
| 990 | `formula_1` | 协议/轮数/收敛失败 | 本来已查到 constructor，但最后用诊断 SQL 覆盖最终答案；输出 results 明细而非 constructorRef/url。 | [formula_1_wrong_analysis.md](./formula_1_wrong_analysis.md#qid990) |
| 994 | `formula_1` | 输出形状/答案格式错误 | 算出同一 constructor，但输出列顺序和列数错：多 constructorId，score 在最后。 | [formula_1_wrong_analysis.md](./formula_1_wrong_analysis.md#qid994) |
| 1002 | `formula_1` | 协议/轮数/收敛失败 | 第 9 轮已有正确 SQL，第 10 轮又输出诊断 race list，覆盖最终 SQL。 | [formula_1_wrong_analysis.md](./formula_1_wrong_analysis.md#qid1002) |
| 1011 | `formula_1` | 输出形状/答案格式错误 | 用 TEXT `time` 求 MIN 导致字典序错误；应按 `milliseconds` 最小排序；还把 full name 拼成单列并多输出 lap time。 | [formula_1_wrong_analysis.md](./formula_1_wrong_analysis.md#qid1011) |
| 1014 | `formula_1` | 排序/TopK/Tie/排名错误 | 用 `lapTimes.time` 的 TEXT MIN，且不是 `results.fastestLapTime`；时间字符串字典序导致 `13:29.130` 被当最小。 | [formula_1_wrong_analysis.md](./formula_1_wrong_analysis.md#qid1014) |
| 1028 | `european_football_2` | 输出形状/答案格式错误 | 并列第一处理错误。Scotland Premier League 在 `2009/2010` season 中 away win 最多的队伍有 `Rangers` 和 `Celtic` 两个并列；pred 用 `ORDER BY win_count DESC LIMIT 1` 只保留 `Celtic`。同时 pred 多输出了 `win_count`，输出形状也不匹配。 | [european_football_2_wrong_analysis.md](./european_football_2_wrong_analysis.md#qid1028) |
| 1029 | `european_football_2` | 输出形状/答案格式错误 | latest-record 和排序逻辑正确，失败来自输出形状。gold 只要求 `buildUpPlaySpeed` 一列；pred 多输出了 team name、short name 和 date。 | [european_football_2_wrong_analysis.md](./european_football_2_wrong_analysis.md#qid1029) |
| 1031 | `european_football_2` | 输出形状/答案格式错误 | 年龄计算少了生日月日修正，把 exact age 算成 naive age；同时没有按玩家/年龄去重，并多输出了姓名、速度和日期。 | [european_football_2_wrong_analysis.md](./european_football_2_wrong_analysis.md#qid1031) |
| 1032 | `european_football_2` | 排序/TopK/Tie/排名错误 | 并列第一处理错误。三个 league 的 match count 都是 3040，pred 使用 `ORDER BY ... LIMIT 1` 只返回一条。 | [european_football_2_wrong_analysis.md](./european_football_2_wrong_analysis.md#qid1032) |
| 1037 | `european_football_2` | 聚合/公式/粒度错误 | gold 按出生在 1987-1992 的 distinct players 统计“曾经 preferred_foot = left 的玩家占比”；pred 按 `Player_Attributes` 记录行统计，玩家属性记录越多权重越大。另有 `ROUND(..., 2)` 精度损失，但主因是 entity-level percentage 被写成 record-level percentage。 | [european_football_2_wrong_analysis.md](./european_football_2_wrong_analysis.md#qid1037) |
| 1040 | `european_football_2` | 输出形状/答案格式错误 | 排序和 top 10 逻辑正确，失败来自输出形状。gold 只要 player name；pred 多输出了平均 heading accuracy。 | [european_football_2_wrong_analysis.md](./european_football_2_wrong_analysis.md#qid1040) |
| 1044 | `european_football_2` | 输出形状/答案格式错误 | 筛选逻辑正确，失败来自输出形状。gold 只要求姓名；pred 多输出生日。 | [european_football_2_wrong_analysis.md](./european_football_2_wrong_analysis.md#qid1044) |
| 1076 | `european_football_2` | 输出形状/答案格式错误 | 差值计算正确，失败来自输出形状。gold 只要最终 difference；pred 多输出了两人的中间平均值。 | [european_football_2_wrong_analysis.md](./european_football_2_wrong_analysis.md#qid1076) |
| 1078 | `european_football_2` | 输出形状/答案格式错误 | pred 只列出了两人的生日，没有完成“older”比较并只选择年龄更大者；同时多输出 birthday。 | [european_football_2_wrong_analysis.md](./european_football_2_wrong_analysis.md#qid1078) |
| 1079 | `european_football_2` | 输出形状/答案格式错误 | 最高身高玩家定位正确，失败来自输出形状。gold 只要 player name；pred 多输出 height。 | [european_football_2_wrong_analysis.md](./european_football_2_wrong_analysis.md#qid1079) |
| 1092 | `european_football_2` | 输出形状/答案格式错误 | 并列第一处理错误。2008/2009 season 中四个 league 都有 380 场，pred `LIMIT 1` 只保留一个；同时多输出 match count。 | [european_football_2_wrong_analysis.md](./european_football_2_wrong_analysis.md#qid1092) |
| 1094 | `european_football_2` | 聚合/公式/粒度错误 | 百分比公式缺少括号，把 `(A - B) * 100 / B` 写成了 `A - B * 100 / B`。`ROUND(..., 2)` 也是精度问题，但不是造成符号错误的主因。 | [european_football_2_wrong_analysis.md](./european_football_2_wrong_analysis.md#qid1094) |
| 1110 | `european_football_2` | 协议/轮数/收敛失败 | 探索阶段已经拿到正确答案，但确认/收敛失败；模型把题目中的属性日期错误路由到 `Match` 表，忽略了 `Team_Attributes.date` 才是目标字段所在表。 | [european_football_2_wrong_analysis.md](./european_football_2_wrong_analysis.md#qid1110) |
| 1114 | `european_football_2` | 类型/日期/NULL/值规范错误 | 日期边界处理错误。pred 没有用 `SUBSTR(date,1,10)` 或 `LIKE '2016-04-21%'` 包含结束日，漏掉 2016-04-21 当天记录。 | [european_football_2_wrong_analysis.md](./european_football_2_wrong_analysis.md#qid1114) |
| 1115 | `european_football_2` | 协议/轮数/收敛失败 | 任务语义路由错表。题目问的是玩家属性在某日期的 rating，不需要 match；pred 把日期解释成比赛日期，导致多轮探索耗尽，最终没有 SQL。 | [european_football_2_wrong_analysis.md](./european_football_2_wrong_analysis.md#qid1115) |
| 1136 | `european_football_2` | 聚合/公式/粒度错误 | gold 问的是玩家数，应 `COUNT(DISTINCT player_api_id)`；pred 用 `COUNT(*)` 按属性记录计数，把同一玩家多条属性记录重复计入。 | [european_football_2_wrong_analysis.md](./european_football_2_wrong_analysis.md#qid1136) |
| 1144 | `european_football_2` | 输出形状/答案格式错误 | 目标记录集合正确，失败来自输出形状。gold 只要 finishing 和 curve；pred 多输出玩家名和体重。 | [european_football_2_wrong_analysis.md](./european_football_2_wrong_analysis.md#qid1144) |
| 1145 | `european_football_2` | 输出形状/答案格式错误 | top 4 集合正确，行顺序不影响本评测；失败来自输出形状。gold 只要 league name，pred 多输出 count。 | [european_football_2_wrong_analysis.md](./european_football_2_wrong_analysis.md#qid1145) |
| 1149 | `thrombosis_prediction` | 输出形状/答案格式错误 | 模型算的是比例 fraction，并且额外输出了分子和分母；gold 按百分比口径乘以 100，只输出一个值。这里不是筛选条件错，而是百分比尺度和输出形状错。 | [thrombosis_prediction_wrong_analysis.md](./thrombosis_prediction_wrong_analysis.md#qid1149) |
| 1166 | `thrombosis_prediction` | 协议/轮数/收敛失败 | 多轮工具协议失败。模型已经找到方向，但反复违反单条 SQL 工具约束，耗尽轮数，没有产出最终 SQL。 | [thrombosis_prediction_wrong_analysis.md](./thrombosis_prediction_wrong_analysis.md#qid1166) |
| 1168 | `thrombosis_prediction` | SQL 可执行性错误 | - `First Date` 是带空格字段，pred 写成 `p.First Date`，没有使用 `p."First Date"` 或 `p.\`First Date\``，直接语法错误。 - 题目问“oldest SJS patient”，应按 `Birthday ASC` 找最老患者；pred 却按 `age_at_arrival ASC` 排序，语义变成“入院年龄最小”。 - gold 只要求输出最后一次实验室日期和入院年龄，pred 还额外输出了 `p.ID`。 | [thrombosis_prediction_wrong_analysis.md](./thrombosis_prediction_wrong_analysis.md#qid1168) |
| 1169 | `thrombosis_prediction` | 聚合/公式/粒度错误 | 模型在 `Laboratory` 行粒度上计数，没有按患者 `COUNT(DISTINCT ID)` 去重；同时额外输出了分子分母列。核心错因是患者粒度和实验室记录粒度混淆。 | [thrombosis_prediction_wrong_analysis.md](./thrombosis_prediction_wrong_analysis.md#qid1169) |
| 1175 | `thrombosis_prediction` | 输出形状/答案格式错误 | 查询定位和年龄计算都对了，但输出形状错。gold 只要 `(age, Diagnosis)`，pred 多输出了 `ID`、`Date`、`HGB`，且列顺序也不是 gold 的两列顺序。 | [thrombosis_prediction_wrong_analysis.md](./thrombosis_prediction_wrong_analysis.md#qid1175) |
| 1179 | `thrombosis_prediction` | 输出形状/答案格式错误 | 答案值正确，但额外输出了日期、描述日期和诊断列；严格 EX 下列数不一致。 | [thrombosis_prediction_wrong_analysis.md](./thrombosis_prediction_wrong_analysis.md#qid1179) |
| 1185 | `thrombosis_prediction` | SQL 可执行性错误 | - 模型前面尝试计算 `(Nov sum - Dec sum) / Nov sum`，但把字段 `T-CHO` 写成未引用的 `T-CHO`，SQLite 按减号解析，报 `no such column: T`。 - 后续没有修成 `\`T-CHO\`` 或 `"T-CHO"`，反而退回到探索 1981 年 11 月的样例记录。 - 最后一轮探索 SQL 被当成最终 `pred_sql`，完全没有按患者生日过滤，也没有计算下降率。 | [thrombosis_prediction_wrong_analysis.md](./thrombosis_prediction_wrong_analysis.md#qid1185) |
| 1187 | `thrombosis_prediction` | 类型/日期/NULL/值规范错误 | 题目中的 “examined” 在 evidence 中明确指 `Laboratory.Date`，因为 GPT/ALB 都在 `Laboratory`；模型误把日期条件放到 `Examination` 表，额外 join 缩小了集合。 | [thrombosis_prediction_wrong_analysis.md](./thrombosis_prediction_wrong_analysis.md#qid1187) |
| 1192 | `thrombosis_prediction` | 聚合/公式/粒度错误 | - `T-BIL` 是带连字符字段，必须写成 `l."T-BIL"` 或 `l.\`T-BIL\``；pred 写成 `l.T_BIL`，字段名不存在。 - 即使字段名修正，pred 还额外输出了患者属性和 `l.Date`、`T-BIL`；gold 只输出 `DISTINCT ID`。 | [thrombosis_prediction_wrong_analysis.md](./thrombosis_prediction_wrong_analysis.md#qid1192) |
| 1205 | `thrombosis_prediction` | 输出形状/答案格式错误 | 判断逻辑正确，纯输出形状错误。gold 只要布尔标签列；pred 额外输出了 `ID`、`SEX`、`UA`。 | [thrombosis_prediction_wrong_analysis.md](./thrombosis_prediction_wrong_analysis.md#qid1205) |
| 1209 | `thrombosis_prediction` | 排序/TopK/Tie/排名错误 | gold 先按 `Laboratory` 找 `DISTINCT ID`，再回到 `Patient` 输出患者诊断；pred 直接输出每条异常 GPT 检验记录，导致重复患者大量出现，并额外输出了 ID、生日、GPT。 | [thrombosis_prediction_wrong_analysis.md](./thrombosis_prediction_wrong_analysis.md#qid1209) |
| 1227 | `thrombosis_prediction` | 聚合/公式/粒度错误 | - gold 用 `SELECT DISTINCT ID, age` 后再 `AVG(age)`，按患者平均。 - pred 直接在 join 后的实验室记录上平均，每个患者按高胆固醇记录条数被重复加权。 - pred 还用 `julianday / 365.25` 得到小数年龄；gold 用整岁公式。核心错因仍是未按患者去重。 | [thrombosis_prediction_wrong_analysis.md](./thrombosis_prediction_wrong_analysis.md#qid1227) |
| 1231 | `thrombosis_prediction` | 类型/日期/NULL/值规范错误 | pred 写成 `p.Birthday BETWEEN '1936' AND '1956'`。`Birthday` 是完整日期字符串，不能和年份字符串直接比较；应该用 `STRFTIME('%Y', p.Birthday) BETWEEN '1936' AND '1956'`。这个错误导致本应命中的 1938、1944 年患者没有被正确保留。 | [thrombosis_prediction_wrong_analysis.md](./thrombosis_prediction_wrong_analysis.md#qid1231) |
| 1235 | `thrombosis_prediction` | SQL 可执行性错误 | - 最直接原因是多了一个右括号，SQL 语法错误。 - 早期轮次曾产出可执行 SQL，但年龄是天数 `32957`，后续修复时引入括号错误。 - 即使修掉语法，pred 输出顺序是 `(ID, Diagnosis, age)`，gold 是 `(Diagnosis, ID, age)`，列顺序仍不一致。 | [thrombosis_prediction_wrong_analysis.md](./thrombosis_prediction_wrong_analysis.md#qid1235) |
| 1239 | `thrombosis_prediction` | 类型/日期/NULL/值规范错误 | pred 只做 `当前年份 - 出生年份`，没有按月日比较扣 1；gold 使用 `strftime('%m-%d','now') < strftime('%m-%d', Birthday)` 做整岁修正。 | [thrombosis_prediction_wrong_analysis.md](./thrombosis_prediction_wrong_analysis.md#qid1239) |
| 1241 | `thrombosis_prediction` | 输出形状/答案格式错误 | 差值本身正确，但输出形状错误。gold 只要差值一列；pred 额外输出了两个中间计数。 | [thrombosis_prediction_wrong_analysis.md](./thrombosis_prediction_wrong_analysis.md#qid1241) |
| 1242 | `thrombosis_prediction` | 聚合/公式/粒度错误 | 过滤语义基本命中，但输出粒度错。gold 要的是患者 ID 去重；pred 把每条 1984 年正常血小板实验室记录都输出，并额外带出生日、PLT、日期，导致同一患者多行。 | [thrombosis_prediction_wrong_analysis.md](./thrombosis_prediction_wrong_analysis.md#qid1242) |
| 1243 | `thrombosis_prediction` | 类型/日期/NULL/值规范错误 | 多轮协议没有完成最终阶段。模型没有产出可评测 SQL；并且探索中对年龄条件的表达式也不可靠，应该使用 `date(Birthday, '+55 years') < date('now')`。 | [thrombosis_prediction_wrong_analysis.md](./thrombosis_prediction_wrong_analysis.md#qid1243) |
| 1252 | `thrombosis_prediction` | 排序/TopK/Tie/排名错误 | - `Examination` 没有 `Patient.ID` 这种嵌套字段，正确连接应是 `L.ID = E.ID`，必要时再 join `Patient`。 - pred 用 `COUNT(*)`，即使修正 join，也会得到 4 条记录；gold 要 `COUNT(DISTINCT Patient.ID)`，只有 1 名患者。也就是说这里同时有 join 字段幻觉和患者去重遗漏。 | [thrombosis_prediction_wrong_analysis.md](./thrombosis_prediction_wrong_analysis.md#qid1252) |
| 1255 | `thrombosis_prediction` | 排序/TopK/Tie/排名错误 | 题目问“patients”，gold 先 `SELECT DISTINCT ID, Diagnosis` 再按诊断计数；pred 按异常 IGM 实验室记录数计数，重复记录把 RA 推到第一。同时 pred 额外输出了 `diagnosis_count`。 | [thrombosis_prediction_wrong_analysis.md](./thrombosis_prediction_wrong_analysis.md#qid1255) |
| 1256 | `thrombosis_prediction` | 排序/TopK/Tie/排名错误 | pred 用 `COUNT(*)` 统计检验记录；gold 要统计患者数 `COUNT(DISTINCT Patient.ID)`。 | [thrombosis_prediction_wrong_analysis.md](./thrombosis_prediction_wrong_analysis.md#qid1256) |
| 1257 | `thrombosis_prediction` | 排序/TopK/Tie/排名错误 | - 年龄条件写反了。pred 写 `date('now', '+70 years') > p.Birthday`，这基本筛进所有现实出生日期；正确是患者 70 岁生日在今天之后。 - pred 用 `COUNT(*)` 统计实验室记录；gold 要 `COUNT(DISTINCT Patient.ID)`。 | [thrombosis_prediction_wrong_analysis.md](./thrombosis_prediction_wrong_analysis.md#qid1257) |
| 1265 | `thrombosis_prediction` | Schema/字段/Join 选择错误 | 编码映射错。evidence 说 `'-' means 'negative'`，`'+-' refers to '0'`，真实表中正常值应写 `RNP IN ('negative', '0')`。pred 写成 `RNP IN ('-', '+-', 'negative')`，漏掉了大量真实存储值 `'0'`。 | [thrombosis_prediction_wrong_analysis.md](./thrombosis_prediction_wrong_analysis.md#qid1265) |
| 1267 | `thrombosis_prediction` | 聚合/公式/粒度错误 | - 编码映射错。正常 anti-SM 应按真实存储值 `SM IN ('negative', '0')`，pred 用了 `('-', '+-')`，这两个值在 `SM` 中没有命中，导致 0。 - 语义上 gold 还要求“患者没有 thrombosis”，用 `GROUP BY ID HAVING MAX(COALESCE(Thrombosis,0)) = 0` 排除任何一次血栓记录；pred 只是查某条 examination `Thrombosis = 0`，不是患者级“从未有血栓”。 | [thrombosis_prediction_wrong_analysis.md](./thrombosis_prediction_wrong_analysis.md#qid1267) |
| 1270 | `thrombosis_prediction` | 类型/日期/NULL/值规范错误 | 题目 evidence 明确说“no symptom”包括 `Symptoms IS NULL` 或没有 examination record。gold 用 `NOT EXISTS` 排除有非空症状的患者，因此保留无检查记录患者；pred 用 inner join `Examination`，把没有检查记录的 17 人全部丢掉。 | [thrombosis_prediction_wrong_analysis.md](./thrombosis_prediction_wrong_analysis.md#qid1270) |
| 1281 | `thrombosis_prediction` | 排序/TopK/Tie/排名错误 | 年龄方向反了。题目 evidence 明确 “larger birthday value = younger”，应取 `MAX(Birthday)` 或 `ORDER BY Birthday DESC LIMIT 1`；pred 用了 `MIN(Birthday)`。 | [thrombosis_prediction_wrong_analysis.md](./thrombosis_prediction_wrong_analysis.md#qid1281) |
| 1334 | `student_club` | 输出形状/答案格式错误 | 筛选和 join 正确，失败来自输出形状。虽然题面说 full name，但 gold 使用两列 `first_name, last_name`；pred 拼成单列 `first_name \|\| ' ' \|\| last_name`。 | [student_club_wrong_analysis.md](./student_club_wrong_analysis.md#qid1334) |
| 1338 | `student_club` | 协议/轮数/收敛失败 | 日期精度处理错误导致探索卡死。模型没有把 `event_date` 改成 `LIKE '2019-10-08%'` 或 `SUBSTR(event_date,1,10) = '2019-10-08'`。 | [student_club_wrong_analysis.md](./student_club_wrong_analysis.md#qid1338) |
| 1339 | `student_club` | 聚合/公式/粒度错误 | 聚合单位错误。题目/evidence 中 average spend per event 实际按 distinct budget/event 算；pred 算成了每条 expense 的平均 cost。 | [student_club_wrong_analysis.md](./student_club_wrong_analysis.md#qid1339) |
| 1340 | `student_club` | 输出形状/答案格式错误 | pred 在最终聚合中 `GROUP BY SUBSTR(event_date,1,4)`，把原本应输出一行的条件聚合拆成 2019 和 2020 两行；同时多输出了 `spent_2019`、`spent_2020` 两个中间列。 | [student_club_wrong_analysis.md](./student_club_wrong_analysis.md#qid1340) |
| 1359 | `student_club` | 聚合/公式/粒度错误 | 两个问题叠加：一是没有把分子 cast 成 REAL，触发整数除法；二是外层无意义扫描 `budget`，把标量结果重复输出 15 行。`ROUND(..., 2)` 也会造成精度损失。 | [student_club_wrong_analysis.md](./student_club_wrong_analysis.md#qid1359) |
| 1371 | `student_club` | 类型/日期/NULL/值规范错误 | 字符串字面量没有转义单引号。pred 写成 `e.event_name = 'Women's Soccer'`，SQLite 会在 `Women'` 处结束字符串；正确应写 `e.event_name = 'Women''s Soccer'`。 | [student_club_wrong_analysis.md](./student_club_wrong_analysis.md#qid1371) |
| 1376 | `student_club` | 输出形状/答案格式错误 | 并列最高处理错误。pred 用 `ORDER BY ratio DESC LIMIT 1` 只返回一个事件；gold 用 max ratio subquery 返回全部并列最高事件。同时 pred 多输出 status、spent、amount、ratio。 | [student_club_wrong_analysis.md](./student_club_wrong_analysis.md#qid1376) |
| 1381 | `student_club` | 输出形状/答案格式错误 | 筛选逻辑正确，失败来自输出形状。gold 把 full name 拆成两列；pred 拼成一列。 | [student_club_wrong_analysis.md](./student_club_wrong_analysis.md#qid1381) |
| 1389 | `student_club` | 输出形状/答案格式错误 | 排序和 tie-break 逻辑正确，失败来自输出形状。gold 只要 event name；pred 多输出 total cost。 | [student_club_wrong_analysis.md](./student_club_wrong_analysis.md#qid1389) |
| 1392 | `student_club` | 输出形状/答案格式错误 | top source 计算正确，失败来自输出形状。gold 只要 `source`；pred 多输出 `SUM(amount)`。 | [student_club_wrong_analysis.md](./student_club_wrong_analysis.md#qid1392) |
| 1398 | `student_club` | 输出形状/答案格式错误 | 最高 advertisement spent 的 event 定位正确，失败来自输出形状。gold 只要 event name；pred 多输出 spent。 | [student_club_wrong_analysis.md](./student_club_wrong_analysis.md#qid1398) |
| 1399 | `student_club` | 输出形状/答案格式错误 | 存在性判断语义未转换成题目要求的 YES/NO。pred 的 join 和过滤正确，`COUNT(*) = 1` 表示参加了，但最终输出应该是 `CASE WHEN COUNT(*) > 0 THEN 'YES' ELSE 'NO' END`。 | [student_club_wrong_analysis.md](./student_club_wrong_analysis.md#qid1399) |
| 1410 | `student_club` | 输出形状/答案格式错误 | total cost 正确，失败来自 full name 输出形状。gold 需要 `first_name, last_name, SUM(cost)` 三列；pred 把姓名拼成一列，只输出两列。 | [student_club_wrong_analysis.md](./student_club_wrong_analysis.md#qid1410) |
| 1457 | `student_club` | 聚合/公式/粒度错误 | 题意中的“each expense / cost > AVG(cost)”是单笔 expense 级别过滤；pred 误解为 member total cost 级别过滤，聚合粒度错了。 | [student_club_wrong_analysis.md](./student_club_wrong_analysis.md#qid1457) |
| 1464 | `student_club` | 类型/日期/NULL/值规范错误 | join key 写反且日期格式错误。pred 写成 `m.link_to_member = i.link_to_member`，但 `member` 表没有 `link_to_member` 字段；同时把日期写成 `9/9/2019`，即使修正 join 也查不到 gold 行。 | [student_club_wrong_analysis.md](./student_club_wrong_analysis.md#qid1464) |
| 1472 | `debit_card_specializing` | 协议/轮数/收敛失败 | 把 `LAM` 误找成 gasstations 的 segment/chain，忽略了 `customers.Segment='LAM'`；10 轮内没有生成 SQL。 | [debit_card_specializing_wrong_analysis.md](./debit_card_specializing_wrong_analysis.md#qid1472) |
| 1473 | `debit_card_specializing` | 聚合/公式/粒度错误 | 公式漏除以 12；已算年总消费均值，却没有转成月均。 | [debit_card_specializing_wrong_analysis.md](./debit_card_specializing_wrong_analysis.md#qid1473) |
| 1476 | `debit_card_specializing` | 协议/轮数/收敛失败 | 已找到正确表，但第 10 轮 SQL 输出被截断，`<tool_call>` 未闭合，最终 empty SQL。 | [debit_card_specializing_wrong_analysis.md](./debit_card_specializing_wrong_analysis.md#qid1476) |
| 1479 | `debit_card_specializing` | 输出形状/答案格式错误 | 实际 EX 错在多输出 `TotalConsumption`；同时语义上遗漏 `Currency='CZK'`，只是 top year 碰巧仍是 2013。 | [debit_card_specializing_wrong_analysis.md](./debit_card_specializing_wrong_analysis.md#qid1479) |
| 1480 | `debit_card_specializing` | 输出形状/答案格式错误 | 把“峰值月份总消费”做成“单个客户某月最大消费”；EX 还多输出 Date/Consumption/Segment。月份碰巧同为 04。 | [debit_card_specializing_wrong_analysis.md](./debit_card_specializing_wrong_analysis.md#qid1480) |
| 1481 | `debit_card_specializing` | 协议/轮数/收敛失败 | 复杂 CTE 题在 10 轮内未生成完整 SQL；第 10 轮 `<tool_call>` 未闭合，最终 empty SQL。 | [debit_card_specializing_wrong_analysis.md](./debit_card_specializing_wrong_analysis.md#qid1481) |
| 1482 | `debit_card_specializing` | SQL 可执行性错误 | SQL 本身无效，外层引用未投影的 `Year`；还漏 `Currency='EUR'`，输出形状也不符合 gold 的单行三列。 | [debit_card_specializing_wrong_analysis.md](./debit_card_specializing_wrong_analysis.md#qid1482) |
| 1486 | `debit_card_specializing` | 聚合/公式/粒度错误 | 把“CZK 客户比 EUR 客户多多少”误解成交易金额差；gold 实际是客户数量差。 | [debit_card_specializing_wrong_analysis.md](./debit_card_specializing_wrong_analysis.md#qid1486) |
| 1490 | `debit_card_specializing` | 协议/轮数/收敛失败 | 已识别正确表，但停在 `propose_schema`，10 轮内没生成 SQL。 | [debit_card_specializing_wrong_analysis.md](./debit_card_specializing_wrong_analysis.md#qid1490) |
| 1498 | `debit_card_specializing` | 排序/TopK/Tie/排名错误 | 把“最高 monthly consumption”理解为单条客户月记录最大值；gold 是按月份聚合 SUM 后取最大。 | [debit_card_specializing_wrong_analysis.md](./debit_card_specializing_wrong_analysis.md#qid1498) |
| 1505 | `debit_card_specializing` | 输出形状/答案格式错误 | 应在 `yearmonth.Consumption` 上判断月消费 >1000 并 count distinct customer；pred 错用 `transactions_1k.Amount` 且返回明细。 | [debit_card_specializing_wrong_analysis.md](./debit_card_specializing_wrong_analysis.md#qid1505) |
| 1524 | `debit_card_specializing` | 类型/日期/NULL/值规范错误 | 把 548.4 当成 `Amount` 的缩放值 54840；gold 按 `Price=548.4` 查。 | [debit_card_specializing_wrong_analysis.md](./debit_card_specializing_wrong_analysis.md#qid1524) |
| 1525 | `debit_card_specializing` | 聚合/公式/粒度错误 | 分母错：pred 在 `WHERE Currency='EUR'` 后再算比例，导致永远接近/等于 100%；gold 分母是当日全部交易客户。 | [debit_card_specializing_wrong_analysis.md](./debit_card_specializing_wrong_analysis.md#qid1525) |
| 1526 | `debit_card_specializing` | 协议/轮数/收敛失败 | 已在第 9 轮找到 `Price=634.8` 的客户，但继续探索耗尽轮数，最终 empty SQL。 | [debit_card_specializing_wrong_analysis.md](./debit_card_specializing_wrong_analysis.md#qid1526) |
| 1528 | `debit_card_specializing` | 输出形状/答案格式错误 | 正确百分比已算出，但最终多输出 `premium_count` 和 `total_count` 两列，gold 只要百分比。 | [debit_card_specializing_wrong_analysis.md](./debit_card_specializing_wrong_analysis.md#qid1528) |
| 1529 | `debit_card_specializing` | 聚合/公式/粒度错误 | 应计算 `SUM(Amount * Price)`，pred 只算 `SUM(Amount)`；且只输出第一问，漏第二问 August 2012。 | [debit_card_specializing_wrong_analysis.md](./debit_card_specializing_wrong_analysis.md#qid1529) |
| 1531 | `debit_card_specializing` | 输出形状/答案格式错误 | top spending 应按 `SUM(Amount * Price)` 排序；pred 按 `SUM(Amount)` 排序，平均单价公式也漏乘 Amount，并多输出列。 | [debit_card_specializing_wrong_analysis.md](./debit_card_specializing_wrong_analysis.md#qid1531) |
| 1533 | `debit_card_specializing` | 输出形状/答案格式错误 | gold 只返回 `Consumption` 且保留重复行；pred 多输出 CustomerID，并用 DISTINCT 去掉重复，行数和值集合都变了。 | [debit_card_specializing_wrong_analysis.md](./debit_card_specializing_wrong_analysis.md#qid1533) |
