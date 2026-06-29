# toxicology Schema Guide

本文件整理 `toxicology` SQLite 数据库的表结构、字段含义、示例值和 Text-to-SQL 常见 join/过滤注意点。

- 数据库文件：`/root/autodl-tmp/DeepEye-SQL/data/arcwise_plat/dev/dev_databases/toxicology/toxicology.sqlite`
- 字段说明来源：`/root/autodl-tmp/text_to_sql_benchmarks/data/schemas/toxicology/database_description`
- 生成时间：`2026-06-21 22:56:18`
- 生成方式：基于 SQLite schema、database_description CSV、字段样例值以及本次错题根因汇总自动生成。

## 1. 数据库概览

| 表 | 行数 | 字段数 | 作用 |
|---|---:|---:|---|
| `atom` | 12333 | 3 | 原子表。 |
| `bond` | 12379 | 3 | 化学键表。 |
| `connected` | 24758 | 3 | 原子连接关系表。 |
| `molecule` | 343 | 2 | 分子主表。 |

## 2. 表关系与 Join 注意点

### 2.1 SQLite 声明的外键

| From | To | 说明 |
|---|---|---|
| `atom.molecule_id` | `molecule.molecule_id` | 声明外键 |
| `bond.molecule_id` | `molecule.molecule_id` | 声明外键 |
| `connected.bond_id` | `bond.bond_id` | 声明外键 |
| `connected.atom_id2` | `atom.atom_id` | 声明外键 |
| `connected.atom_id` | `atom.atom_id` | 声明外键 |

### 2.2 按字段名推断的常用连接

| From | To | 推断依据 |
|---|---|---|
| `atom.atom_id` | `connected.atom_id` | 同名字段且目标为 PK |

### 2.3 通用注意点

- 字段名含空格、连字符、括号或大小写敏感时，建议使用双引号，例如 `"Some Column"`。
- 表中 ID 字段通常只是连接键；最终输出是否需要 ID，要以 question/gold 语义为准，避免多输出中间列。
- 做 top/max/min/rank 查询时，先确认是否需要返回所有并列值，而不是默认 `LIMIT 1`。
- 分子结构题通常围绕 `molecule`、`atom`、`bond`、`connected` 的连接关系。
- 按 molecule 聚合时要避免 atom/bond join 造成重复计数。
- 属性值和元素符号要区分字段来源，先确认 `atom.element`、`bond.bond_type` 等取值。

## 3. 字段明细

### 3.1 `atom`

原子表。 行数：`12333`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `atom_id` | `TEXT` | PK, NOT NULL | 原子 ID。 | TR000_1, TR000_2, TR000_3 | 0 | distinct=12333 |
| `molecule_id` | `TEXT` | FK -> molecule.molecule_id | 分子 ID。 外键，指向 `molecule.molecule_id`。 | TR338, TR496, TR060 | 0 | distinct=444 |
| `element` | `TEXT` |  | 元素符号。 | h, c, o | 0 | distinct=21 |

### 3.2 `bond`

化学键表。 行数：`12379`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `bond_id` | `TEXT` | PK, NOT NULL | 化学键 ID。 | TR000_1_2, TR000_2_3, TR000_2_4 | 0 | distinct=12379 |
| `molecule_id` | `TEXT` | FK -> molecule.molecule_id | 分子 ID。 外键，指向 `molecule.molecule_id`。 | TR338, TR496, TR059 | 0 | distinct=444 |
| `bond_type` | `TEXT` |  | 化学键类型。 | -, =, # | 1 | distinct=3 |

### 3.3 `connected`

原子连接关系表。 行数：`24758`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `atom_id` | `TEXT` | PK, NOT NULL, FK -> atom.atom_id | 原子 ID。 外键，指向 `atom.atom_id`。 | TR000_2, TR001_1, TR001_2 | 0 | distinct=12284 |
| `atom_id2` | `TEXT` | PK, NOT NULL, FK -> atom.atom_id | 原子id2。外键，指向 `atom.atom_id`。 | TR000_2, TR001_1, TR001_2 | 0 | distinct=12284 |
| `bond_id` | `TEXT` | FK -> bond.bond_id | 化学键 ID。 外键，指向 `bond.bond_id`。 | TR000_1_2, TR000_2_3, TR000_2_4 | 0 | distinct=12379 |

### 3.4 `molecule`

分子主表。 行数：`343`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `molecule_id` | `TEXT` | PK, NOT NULL | 分子 ID。 | TR000, TR001, TR002 | 0 | distinct=343 |
| `label` | `TEXT` |  | 标签/类别。 | -, + | 0 | distinct=2 |

## 4. 常用查询模板

### 4.1 `atom` join `molecule`

```sql
SELECT *
FROM "atom" AS t1
JOIN "molecule" AS t2
  ON t1."molecule_id" = t2."molecule_id";
```

### 4.2 `bond` join `molecule`

```sql
SELECT *
FROM "bond" AS t1
JOIN "molecule" AS t2
  ON t1."molecule_id" = t2."molecule_id";
```

### 4.3 `connected` join `bond`

```sql
SELECT *
FROM "connected" AS t1
JOIN "bond" AS t2
  ON t1."bond_id" = t2."bond_id";
```

### 4.4 `connected` join `atom`

```sql
SELECT *
FROM "connected" AS t1
JOIN "atom" AS t2
  ON t1."atom_id2" = t2."atom_id";
```

### 4.5 `connected` join `atom`

```sql
SELECT *
FROM "connected" AS t1
JOIN "atom" AS t2
  ON t1."atom_id" = t2."atom_id";
```

### 4.6 `atom` join `connected`

```sql
SELECT *
FROM "atom" AS t1
JOIN "connected" AS t2
  ON t1."atom_id" = t2."atom_id";
```

## 5. Text-to-SQL 易错点

- 本次评测错题暴露出的典型坑：
  - qid195（输出形状/答案格式错误）：top bond type 判断正确，但输出形状错。gold 只要 `bond_type`；pred 多输出了 `COUNT(*)`。
  - qid197（聚合/公式/粒度错误）：平均值分母错。题目问含单键分子的平均氧原子数，0 氧分子必须计入；pred 只平均了“至少有一个氧”的分子。
  - qid200（输出形状/答案格式错误）：筛选正确，但输出形状错。gold 只要 `molecule_id`；pred 多输出了 `label`。
  - qid201（协议/轮数/收敛失败）：先是元素值大小写错误，然后修复过程失控，探索 SQL 覆盖最终答案。正确查询应在含双键 molecule 的 atom 集合中计算 `COUNT(DISTINCT carbon atom_id) / COUNT(DISTINCT atom_id) * 100`。
  - qid208（输出形状/答案格式错误）：label 判断正确，但输出形状错。gold 只要 label；pred 多输出了 count。
  - qid212（排序/TopK/Tie/排名错误）：- pred `ORDER BY count ASC LIMIT 1` 只取一个最小值，没有处理并列最小元素。 - pred 还额外输出了 `count`。
  - qid213（协议/轮数/收敛失败）：多轮修复/确认阶段倒退。模型已经找到答案，但最后用探索 SQL 覆盖了正确 SQL。
  - qid218（聚合/公式/粒度错误）：- pred 的 `COUNT(DISTINCT CASE WHEN a.element != 'f' THEN m.molecule_id END)` 不是“不含 fluorine”，而是“至少有一个非 fluorine 原子”。几乎所有 molecule 都满足。 - 题目要求 percentage，pred 输出了三个计数字段，没有返回百分比标量。
  - qid219（聚合/公式/粒度错误）：分母粒度错。题目问 molecule 百分比，gold 按 distinct molecule_id 计算；pred 按 bond 行计算，而且 join 到 `molecule` 后还改变了分母集合。
  - qid226（聚合/公式/粒度错误）：公式正确，但没有按题目要求和 gold SQL `ROUND(..., 5)` 保留五位小数。严格 EX 下完整浮点值不一致。
  - qid227（聚合/公式/粒度错误）：公式正确，但没有 `ROUND(..., 3)`。严格 EX 下未四舍五入的浮点值不等于 gold。
  - qid230（输出形状/答案格式错误）：- gold 用 `DISTINCT element, label`；pred 没有 `DISTINCT`，输出每个 atom 明细行。 - 列顺序也反了：gold 是 `(element, label)`，pred 是 `(label, element)`。
  - qid231（输出形状/答案格式错误）：top bond type 判断正确，但输出形状错。gold 只要 `bond_type`；pred 多输出了 `bond_count`。
  - qid234（聚合/公式/粒度错误）：`connected` 表对每条 bond 存了两个方向，pred 用 `COUNT(*)` 把双向记录都算了；gold 用 `COUNT(DISTINCT bond_id)`。
  - qid239（Schema/字段/Join 选择错误）：`connected` 表本身已经包含双向边。gold 只按 `atom_id` 这一方向计连接；pred 同时查 `atom_id` 和 `atom_id2`，把每条连接翻倍。
  - qid243（输出形状/答案格式错误）：连接逻辑基本正确，输出形状错。gold 只要 `bond_id`；pred 多输出了 `bond_type`。
  - qid244（排序/TopK/Tie/排名错误）：- pred 写 `b.bond_type = ' = '`，多了空格；真实值是 `'='`，所以没有命中。 - 即使修正，也需要处理并列最大，gold 返回两个 label；pred 的 `LIMIT 1` 会漏掉 tie。 - pred 还额外输出了 `double_bond_count`。
  - qid245（聚合/公式/粒度错误）：子查询里 `connected` 和 `atom` 都有 `atom_id`，pred 的 `SELECT atom_id ... GROUP BY atom_id` 未加表别名，SQLite 报歧义列。正确写法应使用 `atom.atom_id` 或 `connected.atom_id`。核查显示 iodine atom 有 6 个，join 到 connected 的 bond 行也是 6，平均为 1.0。
  - 另有 6 条错题根因，详见 `wrong_root_cause_summary_238.md`。
