# superhero Schema Guide

本文件整理 `superhero` SQLite 数据库的表结构、字段含义、示例值和 Text-to-SQL 常见 join/过滤注意点。

- 数据库文件：`/root/autodl-tmp/DeepEye-SQL/data/arcwise_plat/dev/dev_databases/superhero/superhero.sqlite`
- 字段说明来源：`/root/autodl-tmp/text_to_sql_benchmarks/data/schemas/superhero/database_description`
- 生成时间：`2026-06-21 22:56:18`
- 生成方式：基于 SQLite schema、database_description CSV、字段样例值以及本次错题根因汇总自动生成。

## 1. 数据库概览

| 表 | 行数 | 字段数 | 作用 |
|---|---:|---:|---|
| `alignment` | 4 | 2 | 关系/映射表。 |
| `attribute` | 6 | 2 | 关系/映射表。 |
| `colour` | 35 | 2 | 关系/映射表。 |
| `gender` | 3 | 2 | 关系/映射表。 |
| `hero_attribute` | 3738 | 3 | 英雄属性数值表，连接 superhero 与 attribute。 |
| `hero_power` | 5825 | 2 | 英雄超能力关系表，连接 superhero 与 superpower。 |
| `publisher` | 25 | 2 | 关系/映射表。 |
| `race` | 61 | 2 | 关系/映射表。 |
| `superhero` | 750 | 12 | 超级英雄主实体表。 |
| `superpower` | 167 | 2 | 关系/映射表。 |

## 2. 表关系与 Join 注意点

### 2.1 SQLite 声明的外键

| From | To | 说明 |
|---|---|---|
| `hero_attribute.hero_id` | `superhero.id` | 声明外键 |
| `hero_attribute.attribute_id` | `attribute.id` | 声明外键 |
| `hero_power.power_id` | `superpower.id` | 声明外键 |
| `hero_power.hero_id` | `superhero.id` | 声明外键 |
| `superhero.skin_colour_id` | `colour.id` | 声明外键 |
| `superhero.race_id` | `race.id` | 声明外键 |
| `superhero.publisher_id` | `publisher.id` | 声明外键 |
| `superhero.hair_colour_id` | `colour.id` | 声明外键 |
| `superhero.gender_id` | `gender.id` | 声明外键 |
| `superhero.eye_colour_id` | `colour.id` | 声明外键 |
| `superhero.alignment_id` | `alignment.id` | 声明外键 |


### 2.3 通用注意点

- 字段名含空格、连字符、括号或大小写敏感时，建议使用双引号，例如 `"Some Column"`。
- 表中 ID 字段通常只是连接键；最终输出是否需要 ID，要以 question/gold 语义为准，避免多输出中间列。
- 做 top/max/min/rank 查询时，先确认是否需要返回所有并列值，而不是默认 `LIMIT 1`。
- `height_cm`、`weight_kg` 中 `0` 和 `NULL` 都常表示缺失，求平均/排序时通常要过滤 `> 0`。
- 最高/最低属性值常有并列，不能机械 `LIMIT 1`。
- 数据库表名使用英式拼写 `colour`，不是 `color`。

## 3. 字段明细

### 3.1 `alignment`

关系/映射表。 行数：`4`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `id` | `INTEGER` | PK, NOT NULL | 阵营的唯一标识符。 | 1, 2, 3 | 0 | distinct=4; range=1 - 4 |
| `alignment` | `TEXT` |  | 阵营。 | Bad, Good, N/A | 0 | distinct=4 |

### 3.2 `attribute`

关系/映射表。 行数：`6`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `id` | `INTEGER` | PK, NOT NULL | 属性的唯一标识符。 | 1, 2, 3 | 0 | distinct=6; range=1 - 6 |
| `attribute_name` | `TEXT` |  | 属性名称。 | Combat, Durability, Intelligence | 0 | distinct=6 |

### 3.3 `colour`

关系/映射表。 行数：`35`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `id` | `INTEGER` | PK, NOT NULL | 颜色的唯一标识符。 | 1, 2, 3 | 0 | distinct=35; range=1 - 35 |
| `colour` | `TEXT` |  | 颜色。 | Amber, Auburn, Black | 0 | distinct=35 |

### 3.4 `gender`

关系/映射表。 行数：`3`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `id` | `INTEGER` | PK, NOT NULL | 性别的唯一标识符。 | 1, 2, 3 | 0 | distinct=3; range=1 - 3 |
| `gender` | `TEXT` |  | 性别。 | Female, Male, N/A | 0 | distinct=3 |

### 3.5 `hero_attribute`

英雄属性数值表，连接 superhero 与 attribute。 行数：`3738`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `hero_id` | `INTEGER` | FK -> superhero.id | 超级英雄 ID。 外键，指向 `superhero.id`。 | 1, 2, 3 | 0 | distinct=623; range=1 - 756 |
| `attribute_id` | `INTEGER` | FK -> attribute.id | 属性 ID。 外键，指向 `attribute.id`。 | 1, 2, 3 | 0 | distinct=6; range=1 - 6 |
| `attribute_value` | `INTEGER` |  | 属性数值。 | 35, 25, 85 | 0 | distinct=20; range=5 - 100 |

### 3.6 `hero_power`

英雄超能力关系表，连接 superhero 与 superpower。 行数：`5825`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `hero_id` | `INTEGER` | FK -> superhero.id | 超级英雄 ID。 外键，指向 `superhero.id`。 | 637, 21, 424 | 0 | distinct=652; range=1 - 756 |
| `power_id` | `INTEGER` | FK -> superpower.id | 超能力 ID。 外键，指向 `superpower.id`。 | 18, 26, 6 | 0 | distinct=167; range=1 - 167 |

### 3.7 `publisher`

关系/映射表。 行数：`25`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `id` | `INTEGER` | PK, NOT NULL | 出版商的唯一标识符。 | 1, 2, 3 | 0 | distinct=25; range=1 - 25 |
| `publisher_name` | `TEXT` |  | 出版商名称。 | , ABC Studios, DC Comics | 0 | distinct=25 |

### 3.8 `race`

关系/映射表。 行数：`61`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `id` | `INTEGER` | PK, NOT NULL | 种族的唯一标识符。 | 1, 2, 3 | 0 | distinct=61; range=1 - 61 |
| `race` | `TEXT` |  | 比赛/种族。 | -, Alien, Alpha | 0 | distinct=61 |

### 3.9 `superhero`

超级英雄主实体表。 行数：`750`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `id` | `INTEGER` | PK, NOT NULL | 超级英雄的唯一标识符。 | 1, 2, 3 | 0 | distinct=750; range=1 - 756 |
| `superhero_name` | `TEXT` |  | 超级英雄名称。 | Atlas, Angel, Ares | 0 | distinct=743 |
| `full_name` | `TEXT` |  | 完整姓名。 | -, Bartholomew Allen II, Richard John Grayson | 122 | distinct=483 |
| `gender_id` | `INTEGER` | FK -> gender.id | 性别 ID。 外键，指向 `gender.id`。 | 1, 2, 3 | 0 | distinct=3; range=1 - 3 |
| `eye_colour_id` | `INTEGER` | FK -> colour.id | 眼睛颜色 ID。 外键，指向 `colour.id`。 | 7, 1, 9 | 0 | distinct=21; range=1 - 35 |
| `hair_colour_id` | `INTEGER` | FK -> colour.id | 头发颜色 ID。 外键，指向 `colour.id`。 | 1, 4, 6 | 0 | distinct=26; range=1 - 33 |
| `skin_colour_id` | `INTEGER` | FK -> colour.id | 皮肤颜色 ID。 外键，指向 `colour.id`。 | 1, 14, 7 | 0 | distinct=16; range=1 - 33 |
| `race_id` | `INTEGER` | FK -> race.id | 种族 ID。 外键，指向 `race.id`。 | 1, 24, 42 | 4 | distinct=61; range=1 - 61 |
| `publisher_id` | `INTEGER` | FK -> publisher.id | 出版商 ID。 外键，指向 `publisher.id`。 | 13, 4, 3 | 3 | distinct=25; range=1 - 25 |
| `alignment_id` | `INTEGER` | FK -> alignment.id | 阵营 ID。 外键，指向 `alignment.id`。 | 1, 2, 3 | 6 | distinct=3; range=1 - 3 |
| `height_cm` | `INTEGER` |  | 超级英雄身高，单位厘米；0 或 NULL 通常表示缺失。 | 0, 183, 188 | 58 | distinct=55; range=0 - 30480 |
| `weight_kg` | `INTEGER` |  | 超级英雄体重，单位千克；0 或 NULL 通常表示缺失。 | 0, 79, 54 | 64 | distinct=140; range=0 - 90000000 |

### 3.10 `superpower`

关系/映射表。 行数：`167`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `id` | `INTEGER` | PK, NOT NULL | 超能力的唯一标识符。 | 1, 2, 3 | 0 | distinct=167; range=1 - 167 |
| `power_name` | `TEXT` |  | 超能力名称。 | Accelerated Healing, Adaptation, Agility | 0 | distinct=167 |

## 4. 常用查询模板

### 4.1 `hero_attribute` join `superhero`

```sql
SELECT *
FROM "hero_attribute" AS t1
JOIN "superhero" AS t2
  ON t1."hero_id" = t2."id";
```

### 4.2 `hero_attribute` join `attribute`

```sql
SELECT *
FROM "hero_attribute" AS t1
JOIN "attribute" AS t2
  ON t1."attribute_id" = t2."id";
```

### 4.3 `hero_power` join `superpower`

```sql
SELECT *
FROM "hero_power" AS t1
JOIN "superpower" AS t2
  ON t1."power_id" = t2."id";
```

### 4.4 `hero_power` join `superhero`

```sql
SELECT *
FROM "hero_power" AS t1
JOIN "superhero" AS t2
  ON t1."hero_id" = t2."id";
```

### 4.5 `superhero` join `colour`

```sql
SELECT *
FROM "superhero" AS t1
JOIN "colour" AS t2
  ON t1."skin_colour_id" = t2."id";
```

### 4.6 `superhero` join `race`

```sql
SELECT *
FROM "superhero" AS t1
JOIN "race" AS t2
  ON t1."race_id" = t2."id";
```

### 4.7 `superhero` join `publisher`

```sql
SELECT *
FROM "superhero" AS t1
JOIN "publisher" AS t2
  ON t1."publisher_id" = t2."id";
```

### 4.8 `superhero` join `colour`

```sql
SELECT *
FROM "superhero" AS t1
JOIN "colour" AS t2
  ON t1."hair_colour_id" = t2."id";
```

## 5. Text-to-SQL 易错点

- 本次评测错题暴露出的典型坑：
  - qid723（协议/轮数/收敛失败）：探索效率和阶段收敛失败。模型知道需要 `superhero.eye_colour_id -> colour.id` 和 `hero_power.power_id -> superpower.id`，但在 schema 探索中重复绕路，10 轮内没有组合成最终 count SQL。
  - qid726（输出形状/答案格式错误）：pred 只过滤 `height_cm IS NOT NULL`，没有按 gold/evidence 排除 `height_cm = 0` 的缺失身高；同时多输出 `height_cm`。
  - qid728（排序/TopK/Tie/排名错误）：ranking function 错误。题目要“rank”，gold 使用并列同 rank 的 `RANK()`；pred 使用 `ROW_NUMBER()`，把并列颜色强行排成不同名次。
  - qid736（输出形状/答案格式错误）：并列最小值处理错误。最低 Intelligence attribute value = 35，有 3 个英雄并列；pred 使用 `ORDER BY attribute_value ASC LIMIT 1` 只返回一人。同时 pred 多输出 `full_name`、attribute name 和 attribute value。
  - qid738（输出形状/答案格式错误）：筛选逻辑正确，失败来自输出形状。gold 只要 `superhero_name`；pred 多输出 `full_name` 和 durability value。
  - qid744（输出形状/答案格式错误）：pred 没有输出“更多的是哪个 publisher”，而是输出两个中间计数；并且差值方向写成 `DC - Marvel`，与本题 gold 的 `Marvel - DC` 相反。
  - qid750（聚合/公式/粒度错误）：缺失值过滤错误。gold 使用 `weight_kg > 0` 排除缺失体重；pred 直接 `AVG(weight_kg)`，把 `0` 当真实体重参与平均。
  - qid769（输出形状/答案格式错误）：最高 durability 英雄定位正确，失败来自输出形状。gold 只要 superhero name；pred 多输出 max durability。
  - qid775（聚合/公式/粒度错误）：百分比精度错误。计算口径正确，但 pred 使用 `ROUND(..., 2)`，gold 保留完整浮点值。
  - qid788（聚合/公式/粒度错误）：百分比精度错误。计算口径正确，但 pred 使用 `ROUND(..., 2)`，导致与 gold 浮点结果不完全一致。
  - qid791（聚合/公式/粒度错误）：缺失值过滤错误。gold 使用 `height_cm > 0`；pred 直接 `AVG(height_cm)`。
  - qid794（输出形状/答案格式错误）：并列最大值处理错误。pred 使用 `ORDER BY attribute_value DESC LIMIT 1`，只返回一个最快英雄；gold 用 max subquery 保留全部 speed 最大者。同时 pred 多输出 attribute value。
  - qid798（输出形状/答案格式错误）：publisher 判断正确，失败来自输出形状。gold 只要求 publisher name；pred 多输出 superhero name。由于评测按 row tuple 比较，`('DC Comics',)` 和 `('DC Comics', 'Hawkman')` 不相等。
  - qid800（协议/轮数/收敛失败）：schema 名称归一化失败。数据库实际使用英式拼写 `colour`，pred 持续搜索不存在的 `color` 表，导致探索卡死。
  - qid819（输出形状/答案格式错误）：差值计算正确，失败来自输出形状。gold 只要最终 difference；pred 多输出两个中间计数。
  - qid829（输出形状/答案格式错误）：差值方向与 gold 一致，但 pred 没有输出“更多的是哪个 publisher”，而是输出了两个中间计数；输出形状不匹配。
