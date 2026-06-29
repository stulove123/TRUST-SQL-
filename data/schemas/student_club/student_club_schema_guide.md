# student_club Schema Guide

本文件整理 `student_club` SQLite 数据库的表结构、字段含义、示例值和 Text-to-SQL 常见 join/过滤注意点。

- 数据库文件：`/root/autodl-tmp/DeepEye-SQL/data/arcwise_plat/dev/dev_databases/student_club/student_club.sqlite`
- 字段说明来源：`/root/autodl-tmp/text_to_sql_benchmarks/data/schemas/student_club/database_description`
- 生成时间：`2026-06-21 22:56:18`
- 生成方式：基于 SQLite schema、database_description CSV、字段样例值以及本次错题根因汇总自动生成。

## 1. 数据库概览

| 表 | 行数 | 字段数 | 作用 |
|---|---:|---:|---|
| `attendance` | 326 | 2 | 成员参加活动的关系表。 |
| `budget` | 52 | 7 | 活动预算表。 |
| `event` | 42 | 7 | 社团活动/会议/比赛主表。 |
| `expense` | 32 | 7 | 支出明细表。 |
| `income` | 36 | 6 | 收入/资金来源表。 |
| `major` | 113 | 4 | 主实体/维表，被其他表引用。 |
| `member` | 33 | 9 | 学生社团成员主表。 |
| `zip_code` | 41877 | 6 | 主实体/维表，被其他表引用。 |

## 2. 表关系与 Join 注意点

### 2.1 SQLite 声明的外键

| From | To | 说明 |
|---|---|---|
| `attendance.link_to_member` | `member.member_id` | 声明外键 |
| `attendance.link_to_event` | `event.event_id` | 声明外键 |
| `budget.link_to_event` | `event.event_id` | 声明外键 |
| `expense.link_to_member` | `member.member_id` | 声明外键 |
| `expense.link_to_budget` | `budget.budget_id` | 声明外键 |
| `income.link_to_member` | `member.member_id` | 声明外键 |
| `member.zip` | `zip_code.zip_code` | 声明外键 |
| `member.link_to_major` | `major.major_id` | 声明外键 |

### 2.2 按字段名推断的常用连接

| From | To | 推断依据 |
|---|---|---|
| `budget.link_to_event` | `attendance.link_to_event` | 同名字段且目标为 PK |
| `expense.link_to_member` | `attendance.link_to_member` | 同名字段且目标为 PK |
| `income.link_to_member` | `attendance.link_to_member` | 同名字段且目标为 PK |

### 2.3 通用注意点

- 字段名含空格、连字符、括号或大小写敏感时，建议使用双引号，例如 `"Some Column"`。
- 表中 ID 字段通常只是连接键；最终输出是否需要 ID，要以 question/gold 语义为准，避免多输出中间列。
- 做 top/max/min/rank 查询时，先确认是否需要返回所有并列值，而不是默认 `LIMIT 1`。
- `event.event_date` 形如 `YYYY-MM-DDTHH:MM:SS`，按日期过滤建议 `LIKE 'YYYY-MM-DD%'` 或 `SUBSTR(event_date,1,10)`。
- `income.date_received`、`expense.expense_date` 是 `YYYY-MM-DD`，不要用 `M/D/YYYY`。
- 题目说 full name 时，gold 可能仍要求 `first_name, last_name` 两列，不一定拼成一列。

## 3. 字段明细

### 3.1 `attendance`

成员参加活动的关系表。 行数：`326`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `link_to_event` | `TEXT` | PK, FK -> event.event_id | 关联活动 ID。外键，指向 `event.event_id`。 | recLKj8BbTNqxFbTb, recykdvf4LgsyA3wZ, recEVTik3MlqbvLFi | 0 | distinct=17 |
| `link_to_member` | `TEXT` | PK, FK -> member.member_id | 关联成员 ID。外键，指向 `member.member_id`。 | recD078PnS3x2doBe, recro8T1MPMwRadVH, rec4BLdZHS2Blfp4v | 0 | distinct=30 |

### 3.2 `budget`

活动预算表。 行数：`52`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `budget_id` | `TEXT` | PK | 预算 ID。 | rec0QmEc3cSQFQ6V2, rec1bG6HSft7XIvTP, rec1z6ISJU2HdIsVm | 0 | distinct=52 |
| `category` | `TEXT` |  | 类别。 | Food, Advertisement, Parking | 0 | distinct=5 |
| `spent` | `REAL` |  | 已花费。 | 0.0, 6.0, 20.2 | 0 | distinct=17; range=0.0 - 327.07 |
| `remaining` | `REAL` |  | 剩余。 | 150.0, 10.0, 20.0 | 0 | distinct=22; range=-24.25 - 150.0 |
| `amount` | `INTEGER` |  | 金额。 | 150, 10, 20 | 0 | distinct=9; range=10 - 350 |
| `event_status` | `TEXT` |  | 活动状态。 | Open, Closed, Planning | 0 | distinct=3 |
| `link_to_event` | `TEXT` | FK -> event.event_id | 关联活动 ID。外键，指向 `event.event_id`。 | rec2mJrCofveboaz6, recAlAwtBZ0Fqbr5K, recEVTik3MlqbvLFi | 0 | distinct=23 |

### 3.3 `event`

社团活动/会议/比赛主表。 行数：`42`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `event_id` | `TEXT` | PK | 活动 ID。 | rec0Si5cQ4rJRVzd6, rec0akZnLLpGUloLH, rec0dZPcWXF0QjNnE | 0 | distinct=42 |
| `event_name` | `TEXT` |  | 活动名称。 | Community Theater, Football game, Laugh Out Loud | 0 | distinct=39 |
| `event_date` | `TEXT` |  | 活动日期时间；格式形如 `YYYY-MM-DDTHH:MM:SS`。 | 2020-03-10T12:00:00, 2019-09-01T07:00:00, 2019-09-03T12:00:00 | 0 | distinct=41 |
| `type` | `TEXT` |  | 类型。 | Meeting, Guest Speaker, Game | 0 | distinct=8 |
| `notes` | `TEXT` |  | 备注。 | All active members can vote for new officers between 4pm-8pm., Attend school football game as a group., Members and alumni can attend a community theater play at a reduced price. Active membership required. | 22 | distinct=15 |
| `location` | `TEXT` |  | 地点。 | MU 215, Campus Soccer/Lacrosse stadium, 100 W. Main Street | 6 | distinct=12 |
| `status` | `TEXT` |  | 合法性状态。 | Closed, Open, Planning | 0 | distinct=3 |

### 3.4 `expense`

支出明细表。 行数：`32`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `expense_id` | `TEXT` | PK | 支出 ID。 | rec017x6R3hQqkLAo, rec1nIjoZKTYayqZ6, rec1oMgNFt7Y0G40x | 0 | distinct=32 |
| `expense_description` | `TEXT` |  | 支出描述。 | Pizza, Posters, Water, chips, cookies | 0 | distinct=12 |
| `expense_date` | `TEXT` |  | 支出日期；格式为 `YYYY-MM-DD`。 | 2019-09-03, 2019-09-10, 2019-09-24 | 0 | distinct=17 |
| `cost` | `REAL` |  | 费用。 | 6.0, 20.2, 54.25 | 0 | distinct=21; range=6.0 - 295.12 |
| `approved` | `TEXT` |  | 是否批准。 | true | 1 | distinct=1 |
| `link_to_member` | `TEXT` | FK -> member.member_id | 关联成员 ID。外键，指向 `member.member_id`。 | rec4BLdZHS2Blfp4v, recD078PnS3x2doBe, recro8T1MPMwRadVH | 0 | distinct=3 |
| `link_to_budget` | `TEXT` | FK -> budget.budget_id | 关联预算 ID。外键，指向 `budget.budget_id`。 | recca5tkvdQgoLKZz, rec1bG6HSft7XIvTP, rec5V70sIuIgpOzDT | 0 | distinct=24 |

### 3.5 `income`

收入/资金来源表。 行数：`36`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `income_id` | `TEXT` | PK | 收入 ID。 | rec0s9ZrO15zhzUeE, rec7f5XMQZexgtQJo, rec8BUJa8GXUjiglg | 0 | distinct=36 |
| `date_received` | `TEXT` |  | 收款日期；格式为 `YYYY-MM-DD`。 | 2019-09-25, 2019-10-31, 2019-09-09 | 0 | distinct=29 |
| `amount` | `INTEGER` |  | 金额。 | 50, 200, 1000 | 0 | distinct=4; range=50 - 3000 |
| `source` | `TEXT` |  | 来源。 | Dues, Fundraising, School Appropration | 0 | distinct=4 |
| `notes` | `TEXT` |  | 备注。 | Ad revenue for use on flyers used to advertise upcoming events., Annual funding from Student Government., Secured donations to help pay for speaker gifts. | 33 | distinct=3 |
| `link_to_member` | `TEXT` | FK -> member.member_id | 关联成员 ID。外键，指向 `member.member_id`。 | rec3pH4DxMcWHMRB7, rec4BLdZHS2Blfp4v, rec1x5zBFIqoOuPW8 | 3 | distinct=31 |

### 3.6 `major`

主实体/维表，被其他表引用。 行数：`113`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `major_id` | `TEXT` | PK | 专业 ID。 | rec06DF6vZ1CyPKpc, rec09LedkREyskCNv, rec0Eanv576RhQllI | 0 | distinct=113 |
| `major_name` | `TEXT` |  | 专业名称。 | Accounting, Aerospace Studies, Agribusiness | 0 | distinct=113 |
| `department` | `TEXT` |  | 院系/部门。 | School of Applied Sciences, Technology and Education, Languages, Philosophy and Communication Studies Department, Plants, Soils, and Climate Department | 0 | distinct=47 |
| `college` | `TEXT` |  | 学院。 | College of Agriculture and Applied Sciences, College of Humanities and Social Sciences, College of Education & Human Services | 0 | distinct=8 |

### 3.7 `member`

学生社团成员主表。 行数：`33`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `member_id` | `TEXT` | PK | 成员 ID。 | rec1x5zBFIqoOuPW8, rec280Sk7o31iG0Tx, rec28ORZgcm1dtqBZ | 0 | distinct=33 |
| `first_name` | `TEXT` |  | 名。 | Adela, Adele, Amy | 0 | distinct=33 |
| `last_name` | `TEXT` |  | 姓。 | Allen, Balentine, Cullen | 0 | distinct=33 |
| `email` | `TEXT` |  | 邮箱。 | adela.o'gallagher@lpu.edu, adele.deleon@lpu.edu, amy.firth@lpu.edu | 0 | distinct=33 |
| `position` | `TEXT` |  | 职务/职位。 | Member, Inactive, President | 0 | distinct=6 |
| `t_shirt_size` | `TEXT` |  | T 恤尺码。 | Large, Medium, X-Large | 0 | distinct=4 |
| `phone` | `TEXT` |  | 联系电话。 | (651) 928-4507, (701) 932-1903, 109-555-7016 | 0 | distinct=33 |
| `zip` | `INTEGER` | FK -> zip_code.zip_code | 邮编。外键，指向 `zip_code.zip_code`。 | 1020, 7002, 7080 | 0 | distinct=33; range=1020 - 98290 |
| `link_to_major` | `TEXT` | FK -> major.major_id | 关联专业 ID。外键，指向 `major.major_id`。 | recKJHO1P6ZC5m567, recObV24Ass2ouQHK, recdIBgeU38UbV2sy | 1 | distinct=26 |

### 3.8 `zip_code`

主实体/维表，被其他表引用。 行数：`41877`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `zip_code` | `INTEGER` | PK | 邮编。 | 501, 544, 601 | 0 | distinct=41877; range=501 - 99950 |
| `type` | `TEXT` |  | 类型。 | Standard, PO Box, Unique | 0 | distinct=3 |
| `city` | `TEXT` |  | 城市。 | Washington, Houston, New York | 0 | distinct=18729 |
| `county` | `TEXT` |  | 县。 | Los Angeles County, Jefferson County, Washington County | 88 | distinct=2010 |
| `state` | `TEXT` |  | 州。 | Texas, California, Pennsylvania | 0 | distinct=52 |
| `short_state` | `TEXT` |  | 州缩写。 | TX, CA, PA | 0 | distinct=52 |

## 4. 常用查询模板

### 4.1 `attendance` join `member`

```sql
SELECT *
FROM "attendance" AS t1
JOIN "member" AS t2
  ON t1."link_to_member" = t2."member_id";
```

### 4.2 `attendance` join `event`

```sql
SELECT *
FROM "attendance" AS t1
JOIN "event" AS t2
  ON t1."link_to_event" = t2."event_id";
```

### 4.3 `budget` join `event`

```sql
SELECT *
FROM "budget" AS t1
JOIN "event" AS t2
  ON t1."link_to_event" = t2."event_id";
```

### 4.4 `expense` join `member`

```sql
SELECT *
FROM "expense" AS t1
JOIN "member" AS t2
  ON t1."link_to_member" = t2."member_id";
```

### 4.5 `expense` join `budget`

```sql
SELECT *
FROM "expense" AS t1
JOIN "budget" AS t2
  ON t1."link_to_budget" = t2."budget_id";
```

### 4.6 `income` join `member`

```sql
SELECT *
FROM "income" AS t1
JOIN "member" AS t2
  ON t1."link_to_member" = t2."member_id";
```

### 4.7 `member` join `zip_code`

```sql
SELECT *
FROM "member" AS t1
JOIN "zip_code" AS t2
  ON t1."zip" = t2."zip_code";
```

### 4.8 `member` join `major`

```sql
SELECT *
FROM "member" AS t1
JOIN "major" AS t2
  ON t1."link_to_major" = t2."major_id";
```

## 5. Text-to-SQL 易错点

- 日期/时间相关字段：`event.event_date`, `expense.expense_date`, `income.date_received`。过滤前先查看实际字符串格式。
- 本次评测错题暴露出的典型坑：
  - qid1334（输出形状/答案格式错误）：筛选和 join 正确，失败来自输出形状。虽然题面说 full name，但 gold 使用两列 `first_name, last_name`；pred 拼成单列 `first_name \|\| ' ' \|\| last_name`。
  - qid1338（协议/轮数/收敛失败）：日期精度处理错误导致探索卡死。模型没有把 `event_date` 改成 `LIKE '2019-10-08%'` 或 `SUBSTR(event_date,1,10) = '2019-10-08'`。
  - qid1339（聚合/公式/粒度错误）：聚合单位错误。题目/evidence 中 average spend per event 实际按 distinct budget/event 算；pred 算成了每条 expense 的平均 cost。
  - qid1340（输出形状/答案格式错误）：pred 在最终聚合中 `GROUP BY SUBSTR(event_date,1,4)`，把原本应输出一行的条件聚合拆成 2019 和 2020 两行；同时多输出了 `spent_2019`、`spent_2020` 两个中间列。
  - qid1359（聚合/公式/粒度错误）：两个问题叠加：一是没有把分子 cast 成 REAL，触发整数除法；二是外层无意义扫描 `budget`，把标量结果重复输出 15 行。`ROUND(..., 2)` 也会造成精度损失。
  - qid1371（类型/日期/NULL/值规范错误）：字符串字面量没有转义单引号。pred 写成 `e.event_name = 'Women's Soccer'`，SQLite 会在 `Women'` 处结束字符串；正确应写 `e.event_name = 'Women''s Soccer'`。
  - qid1376（输出形状/答案格式错误）：并列最高处理错误。pred 用 `ORDER BY ratio DESC LIMIT 1` 只返回一个事件；gold 用 max ratio subquery 返回全部并列最高事件。同时 pred 多输出 status、spent、amount、ratio。
  - qid1381（输出形状/答案格式错误）：筛选逻辑正确，失败来自输出形状。gold 把 full name 拆成两列；pred 拼成一列。
  - qid1389（输出形状/答案格式错误）：排序和 tie-break 逻辑正确，失败来自输出形状。gold 只要 event name；pred 多输出 total cost。
  - qid1392（输出形状/答案格式错误）：top source 计算正确，失败来自输出形状。gold 只要 `source`；pred 多输出 `SUM(amount)`。
  - qid1398（输出形状/答案格式错误）：最高 advertisement spent 的 event 定位正确，失败来自输出形状。gold 只要 event name；pred 多输出 spent。
  - qid1399（输出形状/答案格式错误）：存在性判断语义未转换成题目要求的 YES/NO。pred 的 join 和过滤正确，`COUNT(*) = 1` 表示参加了，但最终输出应该是 `CASE WHEN COUNT(*) > 0 THEN 'YES' ELSE 'NO' END`。
  - qid1410（输出形状/答案格式错误）：total cost 正确，失败来自 full name 输出形状。gold 需要 `first_name, last_name, SUM(cost)` 三列；pred 把姓名拼成一列，只输出两列。
  - qid1457（聚合/公式/粒度错误）：题意中的“each expense / cost > AVG(cost)”是单笔 expense 级别过滤；pred 误解为 member total cost 级别过滤，聚合粒度错了。
  - qid1464（类型/日期/NULL/值规范错误）：join key 写反且日期格式错误。pred 写成 `m.link_to_member = i.link_to_member`，但 `member` 表没有 `link_to_member` 字段；同时把日期写成 `9/9/2019`，即使修正 join 也查不到 gold 行。
