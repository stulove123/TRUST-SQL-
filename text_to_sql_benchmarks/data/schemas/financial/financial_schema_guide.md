# financial Schema Guide

本文件整理 `financial` SQLite 数据库的表结构、字段含义、示例值和 Text-to-SQL 常见 join/过滤注意点。

- 数据库文件：`/root/autodl-tmp/DeepEye-SQL/data/arcwise_plat/dev/dev_databases/financial/financial.sqlite`
- 字段说明来源：`/root/autodl-tmp/text_to_sql_benchmarks/data/schemas/financial/database_description`
- 生成时间：`2026-06-21 22:56:18`
- 生成方式：基于 SQLite schema、database_description CSV、字段样例值以及本次错题根因汇总自动生成。

## 1. 数据库概览

| 表 | 行数 | 字段数 | 作用 |
|---|---:|---:|---|
| `account` | 4500 | 4 | 账户主表。 |
| `card` | 892 | 4 | 事实/明细表，通常需要 join 维表解释 ID。 |
| `client` | 5369 | 4 | 客户主表。 |
| `disp` | 5369 | 4 | 客户到账户关系表。 |
| `district` | 77 | 16 | 地区统计维表。 |
| `loan` | 682 | 7 | 贷款表。 |
| `order` | 6471 | 6 | 事实/明细表，通常需要 join 维表解释 ID。 |
| `trans` | 1056320 | 10 | 交易流水表。 |

## 2. 表关系与 Join 注意点

### 2.1 SQLite 声明的外键

| From | To | 说明 |
|---|---|---|
| `account.district_id` | `district.district_id` | 声明外键 |
| `card.disp_id` | `disp.disp_id` | 声明外键 |
| `client.district_id` | `district.district_id` | 声明外键 |
| `disp.client_id` | `client.client_id` | 声明外键 |
| `disp.account_id` | `account.account_id` | 声明外键 |
| `loan.account_id` | `account.account_id` | 声明外键 |
| `order.account_id` | `account.account_id` | 声明外键 |
| `trans.account_id` | `account.account_id` | 声明外键 |

### 2.3 通用注意点

- 字段名含空格、连字符、括号或大小写敏感时，建议使用双引号，例如 `"Some Column"`。
- 表中 ID 字段通常只是连接键；最终输出是否需要 ID，要以 question/gold 语义为准，避免多输出中间列。
- 做 top/max/min/rank 查询时，先确认是否需要返回所有并列值，而不是默认 `LIMIT 1`。
- Czech financial 库中不少日期是 compact numeric/text 格式，先确认实际存储再比较。
- `loan.status` 的 A/B/C/D 含义很关键，D 表示 running contract 且 client in debt。
- district 表有很多 `Axx` 字段，做比例/差值前要确认字段年份和单位。

## 3. 字段明细

### 3.1 `account`

账户主表。 行数：`4500`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `account_id` | `INTEGER` | PK, NOT NULL | 账户ID。 | 1, 2, 3 | 0 | distinct=4500; range=1 - 11382 |
| `district_id` | `INTEGER` | NOT NULL, FK -> district.district_id | 地区/学区ID。 外键，指向 `district.district_id`。 | 1, 70, 74 | 0 | distinct=77; range=1 - 77 |
| `frequency` | `TEXT` | NOT NULL | 频率。 | POPLATEK MESICNE, POPLATEK TYDNE, POPLATEK PO OBRATU | 0 | distinct=3 |
| `date` | `DATE` | NOT NULL | 日期。 过滤前注意实际日期格式。 | 1993-02-08, 1993-10-08, 1996-06-25 | 0 | distinct=1535 |

### 3.2 `card`

事实/明细表，通常需要 join 维表解释 ID。 行数：`892`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `card_id` | `INTEGER` | PK, NOT NULL | 卡牌ID。 | 1, 2, 3 | 0 | distinct=892; range=1 - 1247 |
| `disp_id` | `INTEGER` | NOT NULL, FK -> disp.disp_id | dispID。 外键，指向 `disp.disp_id`。 | 9, 19, 41 | 0 | distinct=892; range=9 - 13660 |
| `type` | `TEXT` | NOT NULL | 类型。 | classic, junior, gold | 0 | distinct=3 |
| `issued` | `DATE` | NOT NULL | 银行卡签发日期。 | 1998-09-29, 1997-05-17, 1997-12-13 | 0 | distinct=607 |

### 3.3 `client`

客户主表。 行数：`5369`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `client_id` | `INTEGER` | PK, NOT NULL | 客户ID。 | 1, 2, 3 | 0 | distinct=5369; range=1 - 13998 |
| `gender` | `TEXT` | NOT NULL | 性别。 | M, F | 0 | distinct=2 |
| `birth_date` | `DATE` | NOT NULL | birth日期。 过滤前注意实际日期格式。 | 1947-07-13, 1952-08-26, 1965-07-25 | 0 | distinct=4738 |
| `district_id` | `INTEGER` | NOT NULL, FK -> district.district_id | 地区/学区ID。 外键，指向 `district.district_id`。 | 1, 74, 70 | 0 | distinct=77; range=1 - 77 |

### 3.4 `disp`

客户到账户关系表。 行数：`5369`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `disp_id` | `INTEGER` | PK, NOT NULL | 账户客户关系 ID。 | 1, 2, 3 | 0 | distinct=5369; range=1 - 13690 |
| `client_id` | `INTEGER` | NOT NULL, FK -> client.client_id | 客户ID。 外键，指向 `client.client_id`。 | 1, 2, 3 | 0 | distinct=5369; range=1 - 13998 |
| `account_id` | `INTEGER` | NOT NULL, FK -> account.account_id | 账户ID。 外键，指向 `account.account_id`。 | 2, 3, 8 | 0 | distinct=4500; range=1 - 11382 |
| `type` | `TEXT` | NOT NULL | 类型。 | OWNER, DISPONENT | 0 | distinct=2 |

### 3.5 `district`

地区统计维表。 行数：`77`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `district_id` | `INTEGER` | PK, NOT NULL | 地区/学区ID。 | 1, 2, 3 | 0 | distinct=77; range=1 - 77 |
| `A2` | `TEXT` | NOT NULL | 地区名称。 | Benesov, Beroun, Blansko | 0 | distinct=77 |
| `A3` | `TEXT` | NOT NULL | 区域名称。 | south Moravia, central Bohemia, east Bohemia | 0 | distinct=8 |
| `A4` | `TEXT` | NOT NULL | 居民数。 | 102609, 103347, 105058 | 0 | distinct=77 |
| `A5` | `TEXT` | NOT NULL | 小城市数量。 | 0, 38, 60 | 0 | distinct=53 |
| `A6` | `TEXT` | NOT NULL | 中小城市数量。 | 26, 41, 16 | 0 | distinct=36 |
| `A7` | `TEXT` | NOT NULL | 中等城市数量。 | 4, 6, 7 | 0 | distinct=17 |
| `A8` | `INTEGER` | NOT NULL | 大城市数量。 | 1, 2, 3 | 0 | distinct=6; range=0 - 5 |
| `A9` | `INTEGER` | NOT NULL | 城市数量。 | 6, 4, 7 | 0 | distinct=11; range=1 - 11 |
| `A10` | `REAL` | NOT NULL | 城市人口比例。 | 100.0, 46.7, 51.9 | 0 | distinct=70; range=33.9 - 100.0 |
| `A11` | `INTEGER` | NOT NULL | 平均工资。 | 8369, 8110, 8114 | 0 | distinct=76; range=8110 - 12541 |
| `A12` | `REAL` |  | 1995 年失业率。 | 3.3, 1.6, 1.7 | 1 | distinct=41; range=0.2 - 7.3 |
| `A13` | `REAL` | NOT NULL | 1996 年失业率。 | 2.01, 2.31, 3.6 | 0 | distinct=73; range=0.43 - 9.4 |
| `A14` | `INTEGER` | NOT NULL | 每千人企业家数量。 | 100, 131, 102 | 0 | distinct=44; range=81 - 167 |
| `A15` | `INTEGER` |  | 1995 年犯罪数。 | 2854, 818, 999 | 1 | distinct=75; range=818 - 85677 |
| `A16` | `INTEGER` | NOT NULL | 1996 年犯罪数。 | 4505, 888, 1099 | 0 | distinct=76; range=888 - 99107 |

### 3.6 `loan`

贷款表。 行数：`682`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `loan_id` | `INTEGER` | PK, NOT NULL | 贷款ID。 | 4959, 4961, 4962 | 0 | distinct=682; range=4959 - 7308 |
| `account_id` | `INTEGER` | NOT NULL, FK -> account.account_id | 账户ID。 外键，指向 `account.account_id`。 | 2, 19, 25 | 0 | distinct=682; range=2 - 11362 |
| `date` | `DATE` | NOT NULL | 日期。 过滤前注意实际日期格式。 | 1997-12-28, 1998-04-19, 1998-07-12 | 0 | distinct=559 |
| `amount` | `INTEGER` | NOT NULL | 金额。 | 30276, 86184, 39576 | 0 | distinct=645; range=4980 - 590820 |
| `duration` | `INTEGER` | NOT NULL | 持续时间。 | 60, 24, 48 | 0 | distinct=5; range=12 - 60 |
| `payments` | `REAL` | NOT NULL | 还款额。 | 2523.0, 3151.0, 2307.0 | 0 | distinct=577; range=304.0 - 9910.0 |
| `status` | `TEXT` | NOT NULL | 合法性状态。 | C, A, D | 0 | distinct=4 |

### 3.7 `order`

事实/明细表，通常需要 join 维表解释 ID。 行数：`6471`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `order_id` | `INTEGER` | PK, NOT NULL | 支付命令 ID。 | 29401, 29402, 29403 | 0 | distinct=6471; range=29401 - 46338 |
| `account_id` | `INTEGER` | NOT NULL, FK -> account.account_id | 账户ID。 外键，指向 `account.account_id`。 | 96, 97, 173 | 0 | distinct=3758; range=1 - 11362 |
| `bank_to` | `TEXT` | NOT NULL | 银行to。 | QR, YZ, AB | 0 | distinct=13 |
| `account_to` | `INTEGER` | NOT NULL | 账户to。 | 1301700, 1838881, 2692229 | 0 | distinct=6446; range=399 - 99994199 |
| `amount` | `REAL` | NOT NULL | 金额。 | 2.0, 107.0, 5.0 | 0 | distinct=4412; range=1.0 - 14882.0 |
| `k_symbol` | `TEXT` | NOT NULL | 交易/支付类别代码。 | SIPO, , UVER | 0 | distinct=5 |

### 3.8 `trans`

交易流水表。 行数：`1056320`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `trans_id` | `INTEGER` | PK, NOT NULL | 交易ID。 | 1, 5, 6 | 0 | range=1 - 3682987 |
| `account_id` | `INTEGER` | NOT NULL, FK -> account.account_id | 账户ID。 外键，指向 `account.account_id`。 | 8261, 3834, 96 | 0 | range=1 - 11382 |
| `date` | `DATE` | NOT NULL | 日期。 过滤前注意实际日期格式。 | 1998-06-30, 1998-09-30, 1998-07-31 | 0 |  |
| `type` | `TEXT` | NOT NULL | 类型。 | VYDAJ, PRIJEM, VYBER | 0 |  |
| `operation` | `TEXT` |  | 操作。 | VYBER, PREVOD NA UCET, VKLAD | 183114 |  |
| `amount` | `INTEGER` | NOT NULL | 金额。 | 15, 30, 100 | 0 | range=0 - 87400 |
| `balance` | `INTEGER` | NOT NULL | 余额。 | 900, 1100, 600 | 0 | range=-41126 - 209637 |
| `k_symbol` | `TEXT` |  | 交易/支付类别代码。 | UROK, SLUZBY, SIPO | 481881 |  |
| `bank` | `TEXT` |  | 银行。 | QR, AB, ST | 782812 |  |
| `account` | `INTEGER` |  | 账户。 | 0, 66487163, 13943797 | 760931 | range=0 - 99994199 |

## 4. 常用查询模板

### 4.1 `account` join `district`

```sql
SELECT *
FROM "account" AS t1
JOIN "district" AS t2
  ON t1."district_id" = t2."district_id";
```

### 4.2 `card` join `disp`

```sql
SELECT *
FROM "card" AS t1
JOIN "disp" AS t2
  ON t1."disp_id" = t2."disp_id";
```

### 4.3 `client` join `district`

```sql
SELECT *
FROM "client" AS t1
JOIN "district" AS t2
  ON t1."district_id" = t2."district_id";
```

### 4.4 `disp` join `client`

```sql
SELECT *
FROM "disp" AS t1
JOIN "client" AS t2
  ON t1."client_id" = t2."client_id";
```

### 4.5 `disp` join `account`

```sql
SELECT *
FROM "disp" AS t1
JOIN "account" AS t2
  ON t1."account_id" = t2."account_id";
```

### 4.6 `loan` join `account`

```sql
SELECT *
FROM "loan" AS t1
JOIN "account" AS t2
  ON t1."account_id" = t2."account_id";
```

### 4.7 `order` join `account`

```sql
SELECT *
FROM "order" AS t1
JOIN "account" AS t2
  ON t1."account_id" = t2."account_id";
```

### 4.8 `trans` join `account`

```sql
SELECT *
FROM "trans" AS t1
JOIN "account" AS t2
  ON t1."account_id" = t2."account_id";
```

## 5. Text-to-SQL 易错点

- 日期/时间相关字段：`account.date`, `client.birth_date`, `loan.date`, `trans.date`。过滤前先查看实际字符串格式。
- 本次评测错题暴露出的典型坑：
  - qid94（协议/轮数/收敛失败）：探索阶段没有收敛到核心 join 路径 `client -> disp -> account -> district`，并且被无关的 `order/trans/loan` 表和保留字表名错误分散，最终没有生成 SQL。
  - qid95（聚合/公式/粒度错误）：模型知道 `client.birth_date` 和 `district.A11`，但没有建立 `client.client_id = disp.client_id`、`disp.account_id = account.account_id` 的关系，导致无法输出 account_id。
  - qid98（聚合/公式/粒度错误）：自然语言 “approved loan date” 被误解成需要解析 loan status，模型没有直接按 `loan.date` 和 `account.frequency` 生成最终 SQL。
  - qid99（输出形状/答案格式错误）：筛选和排序正确，但输出形状错。gold 只要 `account_id`；pred 多输出了 account opening date、loan amount、duration。
  - qid100（聚合/公式/粒度错误）：pred 用 `client.district_id = account.district_id` 连接，产生 client-account 笛卡尔式放大。gold 只在 `district -> client` 上计客户数，不应按同 district 的所有 account 重复客户。
  - qid115（类型/日期/NULL/值规范错误）：pred 对人口字段 `A4` 做了字符串排序，没有 `CAST(A4 AS INTEGER)`，选错了 south Bohemia 人口最多的 district；同时还做了 `ROUND(...,2)`。
  - qid116（聚合/公式/粒度错误）：多轮推理停在定位 loan/account，没有完成数值计算阶段。正确应对 account 1787 在 `trans.date='1993-03-22'` 和 `1998-12-27` 的 balance 做 `(end-start)/start*100`。
  - qid117（聚合/公式/粒度错误）：公式正确，但 pred 使用 `ROUND(...,2)`，gold 不四舍五入。严格 EX 下 `18.02` 不等于完整浮点。
  - qid118（聚合/公式/粒度错误）：公式正确，但 pred 使用 `ROUND(...,2)`，gold 不四舍五入。
  - qid125（输出形状/答案格式错误）：- gold 要每个符合条件 loan 对应 district 的 increment，允许同一 district 因多个 loan 重复出现；pred `GROUP BY district` 去重了。 - pred 还 `ROUND(...,2)` 并多输出了 `district_id`。 - pred 没有显式过滤 `A12 IS NOT NULL AND A12 > 0`，可能引入额外空值/异常组。
  - qid129（输出形状/答案格式错误）：top ten withdrawals 指 top 10 笔非信用卡取款交易，不是 district 汇总排行。pred 聚合粒度错，并多输出汇总金额。
  - qid136（聚合/公式/粒度错误）：与 q98 类似，模型把 “loans were approved” 过度解释成需要 status 映射；gold 只是对 `loan.date BETWEEN ...` 的已批准贷款记录计数，并结合 `account.frequency='POPLATEK MESICNE'` 与 amount 条件。
  - qid137（聚合/公式/粒度错误）：schema exploration 未进入 generate_sql。正确路径是 `account JOIN loan`，过滤 `account.district_id=1` 和 `loan.status IN ('C','D')` 后 count account。
  - qid145（聚合/公式/粒度错误）：- “account-holder identification numbers” 应走 `disp.type='OWNER'`，pred 按 district 错连 client。 - “overall average transaction amount in 1998” 是所有 1998 transactions 的平均，不是信用卡交易平均。 - pred 没有 `DISTINCT`，输出大量重复 client_id。
  - qid149（聚合/公式/粒度错误）：字段位置识别错。账户资格类型在 `disp.type`，不是 `account` 表，也不是 `card.type`；非 eligible 即 `disp.type <> 'OWNER'`。
  - qid152（聚合/公式/粒度错误）：district-level 平均被 account 明细行重复加权。应先 `SELECT DISTINCT district_id`，再平均 district.A15。
  - qid169（聚合/公式/粒度错误）：工具协议失败叠加未完成聚合。正确路径是 `loan -> account -> disp(type='OWNER') -> client(gender='M')`，按 loan year 1996/1997 分别 SUM(amount) 后计算增长率。
  - qid173（聚合/公式/粒度错误）：模型把 “debiting 3539 in total” 误解成 `account_id=3539` 的交易查询；正确应在 `"order"` 表中对 account 3 的 debiting order amount 按 `k_symbol` 求和。
  - 另有 3 条错题根因，详见 `wrong_root_cause_summary_238.md`。
