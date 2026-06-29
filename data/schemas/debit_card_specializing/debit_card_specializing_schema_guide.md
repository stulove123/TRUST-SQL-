# debit_card_specializing Schema Guide

本文件整理 `debit_card_specializing` SQLite 数据库的表结构、字段含义、示例值和 Text-to-SQL 常见 join/过滤注意点。

- 数据库文件：`/root/autodl-tmp/DeepEye-SQL/data/arcwise_plat/dev/dev_databases/debit_card_specializing/debit_card_specializing.sqlite`
- 字段说明来源：`/root/autodl-tmp/text_to_sql_benchmarks/data/schemas/debit_card_specializing/database_description`
- 生成时间：`2026-06-21 22:56:18`
- 生成方式：基于 SQLite schema、database_description CSV、字段样例值以及本次错题根因汇总自动生成。

## 1. 数据库概览

| 表 | 行数 | 字段数 | 作用 |
|---|---:|---:|---|
| `customers` | 32461 | 3 | 客户主表。 |
| `gasstations` | 5716 | 4 | 加油站维表。 |
| `products` | 591 | 2 | 商品/油品维表。 |
| `transactions_1k` | 1000 | 9 | 交易明细样本表。 |
| `yearmonth` | 383282 | 3 | 客户月度消费统计表。 |

## 2. 表关系与 Join 注意点

### 2.1 SQLite 声明的外键

| From | To | 说明 |
|---|---|---|
| `yearmonth.CustomerID` | `customers.CustomerID` | 声明外键 |
| `yearmonth.CustomerID` | `customers.CustomerID` | 声明外键 |

### 2.2 按字段名推断的常用连接

| From | To | 推断依据 |
|---|---|---|
| `customers.CustomerID` | `yearmonth.CustomerID` | 同名字段且目标为 PK |
| `transactions_1k.Date` | `yearmonth.Date` | 同名字段且目标为 PK |
| `transactions_1k.CustomerID` | `customers.CustomerID` | 同名字段且目标为 PK |
| `transactions_1k.CustomerID` | `yearmonth.CustomerID` | 同名字段且目标为 PK |
| `transactions_1k.GasStationID` | `gasstations.GasStationID` | 同名字段且目标为 PK |
| `transactions_1k.ProductID` | `products.ProductID` | 同名字段且目标为 PK |

### 2.3 通用注意点

- 字段名含空格、连字符、括号或大小写敏感时，建议使用双引号，例如 `"Some Column"`。
- 表中 ID 字段通常只是连接键；最终输出是否需要 ID，要以 question/gold 语义为准，避免多输出中间列。
- 做 top/max/min/rank 查询时，先确认是否需要返回所有并列值，而不是默认 `LIMIT 1`。
- `customers.Currency` 表示客户币种；`yearmonth.Consumption` 表示月消费；`transactions_1k.Amount` 与 `products.Price` 需要区分。
- 消费金额常用 `Amount * Price`，不要只求 `SUM(Amount)`。
- 按月/年聚合时注意 `Date` 的字符串位置。

## 3. 字段明细

### 3.1 `customers`

客户主表。 行数：`32461`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `CustomerID` | `INTEGER` | PK, NOT NULL | 客户 ID。 | 3, 5, 6 | 0 | distinct=32461; range=3 - 53314 |
| `Segment` | `TEXT` |  | 客户细分类型。 | SME, LAM, KAM | 0 | distinct=3 |
| `Currency` | `TEXT` |  | 币种。 | CZK, EUR | 0 | distinct=2 |

### 3.2 `gasstations`

加油站维表。 行数：`5716`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `GasStationID` | `INTEGER` | PK, NOT NULL | 加油站 ID。 | 44, 45, 46 | 0 | distinct=5716; range=44 - 5772 |
| `ChainID` | `INTEGER` |  | 连锁品牌 ID。 | 3, 2, 33 | 0 | distinct=233; range=1 - 290 |
| `Country` | `TEXT` |  | 国家。 | CZE, SVK | 0 | distinct=2 |
| `Segment` | `TEXT` |  | 客户细分类型。 | Other, Premium, Noname | 0 | distinct=5 |

### 3.3 `products`

商品/油品维表。 行数：`591`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `ProductID` | `INTEGER` | PK, NOT NULL | 商品/油品 ID。 | 1, 2, 3 | 0 | distinct=591; range=1 - 630 |
| `Description` | `TEXT` |  | 商品描述。 | Ostatni zbozi, Servisní poplatek, Katalyzátor | 0 | distinct=529 |

### 3.4 `transactions_1k`

交易明细样本表。 行数：`1000`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `TransactionID` | `INTEGER` | PK | 交易 ID。 | 1, 2, 3 | 0 | distinct=1000; range=1 - 1000 |
| `Date` | `DATE` |  | 日期。 过滤前注意实际日期格式。 | 2012-08-24, 2012-08-25, 2012-08-26 | 0 | distinct=4 |
| `Time` | `TEXT` |  | 时间。 过滤前注意实际时间格式。 | 08:57:00, 06:17:00, 08:24:00 | 0 | distinct=599 |
| `CustomerID` | `INTEGER` |  | 客户 ID。 | 19182, 31543, 7626 | 0 | distinct=517; range=96 - 49838 |
| `CardID` | `INTEGER` |  | 银行卡 ID。 | 568944, 732572, 199529 | 0 | distinct=902; range=26228 - 775970 |
| `GasStationID` | `INTEGER` |  | 加油站 ID。 | 448, 1155, 48 | 0 | distinct=437; range=48 - 5481 |
| `ProductID` | `INTEGER` |  | 商品/油品 ID。 | 2, 5, 317 | 0 | distinct=28; range=2 - 352 |
| `Amount` | `INTEGER` |  | 交易数量；计算交易金额时通常需要乘以 `Price`。 | 0, 5, 25 | 0 | distinct=83; range=0 - 264 |
| `Price` | `REAL` |  | 商品单价；交易金额通常需要 `Amount * Price`。 | 43.56, 123.91, 53.29 | 0 | distinct=930; range=1.76 - 5762.49 |

### 3.5 `yearmonth`

客户月度消费统计表。 行数：`383282`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `CustomerID` | `INTEGER` | PK, NOT NULL, FK -> customers.CustomerID, customers.CustomerID | 客户 ID。 外键，指向 `customers.CustomerID, customers.CustomerID`。 | 39, 519, 815 | 0 | range=5 - 52353 |
| `Date` | `TEXT` | PK, NOT NULL | 日期。 过滤前注意实际日期格式。 | 201305, 201304, 201306 | 0 |  |
| `Consumption` | `REAL` |  | 消费量/消费额。 | 33.22, 0.75, 683.57 | 0 | range=-582092.86 - 2052187.11 |

## 4. 常用查询模板

### 4.1 `yearmonth` join `customers`

```sql
SELECT *
FROM "yearmonth" AS t1
JOIN "customers" AS t2
  ON t1."CustomerID" = t2."CustomerID";
```

### 4.2 `yearmonth` join `customers`

```sql
SELECT *
FROM "yearmonth" AS t1
JOIN "customers" AS t2
  ON t1."CustomerID" = t2."CustomerID";
```

### 4.3 `customers` join `yearmonth`

```sql
SELECT *
FROM "customers" AS t1
JOIN "yearmonth" AS t2
  ON t1."CustomerID" = t2."CustomerID";
```

### 4.4 `transactions_1k` join `yearmonth`

```sql
SELECT *
FROM "transactions_1k" AS t1
JOIN "yearmonth" AS t2
  ON t1."Date" = t2."Date";
```

### 4.5 `transactions_1k` join `customers`

```sql
SELECT *
FROM "transactions_1k" AS t1
JOIN "customers" AS t2
  ON t1."CustomerID" = t2."CustomerID";
```

### 4.6 `transactions_1k` join `yearmonth`

```sql
SELECT *
FROM "transactions_1k" AS t1
JOIN "yearmonth" AS t2
  ON t1."CustomerID" = t2."CustomerID";
```

### 4.7 `transactions_1k` join `gasstations`

```sql
SELECT *
FROM "transactions_1k" AS t1
JOIN "gasstations" AS t2
  ON t1."GasStationID" = t2."GasStationID";
```

### 4.8 `transactions_1k` join `products`

```sql
SELECT *
FROM "transactions_1k" AS t1
JOIN "products" AS t2
  ON t1."ProductID" = t2."ProductID";
```

## 5. Text-to-SQL 易错点

- 日期/时间相关字段：`transactions_1k.Date`, `transactions_1k.Time`, `yearmonth.Date`。过滤前先查看实际字符串格式。
- 本次评测错题暴露出的典型坑：
  - qid1472（协议/轮数/收敛失败）：把 `LAM` 误找成 gasstations 的 segment/chain，忽略了 `customers.Segment='LAM'`；10 轮内没有生成 SQL。
  - qid1473（聚合/公式/粒度错误）：公式漏除以 12；已算年总消费均值，却没有转成月均。
  - qid1476（协议/轮数/收敛失败）：已找到正确表，但第 10 轮 SQL 输出被截断，`<tool_call>` 未闭合，最终 empty SQL。
  - qid1479（输出形状/答案格式错误）：实际 EX 错在多输出 `TotalConsumption`；同时语义上遗漏 `Currency='CZK'`，只是 top year 碰巧仍是 2013。
  - qid1480（输出形状/答案格式错误）：把“峰值月份总消费”做成“单个客户某月最大消费”；EX 还多输出 Date/Consumption/Segment。月份碰巧同为 04。
  - qid1481（协议/轮数/收敛失败）：复杂 CTE 题在 10 轮内未生成完整 SQL；第 10 轮 `<tool_call>` 未闭合，最终 empty SQL。
  - qid1482（SQL 可执行性错误）：SQL 本身无效，外层引用未投影的 `Year`；还漏 `Currency='EUR'`，输出形状也不符合 gold 的单行三列。
  - qid1486（聚合/公式/粒度错误）：把“CZK 客户比 EUR 客户多多少”误解成交易金额差；gold 实际是客户数量差。
  - qid1490（协议/轮数/收敛失败）：已识别正确表，但停在 `propose_schema`，10 轮内没生成 SQL。
  - qid1498（排序/TopK/Tie/排名错误）：把“最高 monthly consumption”理解为单条客户月记录最大值；gold 是按月份聚合 SUM 后取最大。
  - qid1505（输出形状/答案格式错误）：应在 `yearmonth.Consumption` 上判断月消费 >1000 并 count distinct customer；pred 错用 `transactions_1k.Amount` 且返回明细。
  - qid1524（类型/日期/NULL/值规范错误）：把 548.4 当成 `Amount` 的缩放值 54840；gold 按 `Price=548.4` 查。
  - qid1525（聚合/公式/粒度错误）：分母错：pred 在 `WHERE Currency='EUR'` 后再算比例，导致永远接近/等于 100%；gold 分母是当日全部交易客户。
  - qid1526（协议/轮数/收敛失败）：已在第 9 轮找到 `Price=634.8` 的客户，但继续探索耗尽轮数，最终 empty SQL。
  - qid1528（输出形状/答案格式错误）：正确百分比已算出，但最终多输出 `premium_count` 和 `total_count` 两列，gold 只要百分比。
  - qid1529（聚合/公式/粒度错误）：应计算 `SUM(Amount * Price)`，pred 只算 `SUM(Amount)`；且只输出第一问，漏第二问 August 2012。
  - qid1531（输出形状/答案格式错误）：top spending 应按 `SUM(Amount * Price)` 排序；pred 按 `SUM(Amount)` 排序，平均单价公式也漏乘 Amount，并多输出列。
  - qid1533（输出形状/答案格式错误）：gold 只返回 `Consumption` 且保留重复行；pred 多输出 CustomerID，并用 DISTINCT 去掉重复，行数和值集合都变了。
