# thrombosis_prediction Schema Guide

本文件整理 `thrombosis_prediction` SQLite 数据库的表结构、字段含义、示例值和 Text-to-SQL 常见 join/过滤注意点。

- 数据库文件：`/root/autodl-tmp/DeepEye-SQL/data/arcwise_plat/dev/dev_databases/thrombosis_prediction/thrombosis_prediction.sqlite`
- 字段说明来源：`/root/autodl-tmp/text_to_sql_benchmarks/data/schemas/thrombosis_prediction/database_description`
- 生成时间：`2026-06-21 22:56:18`
- 生成方式：基于 SQLite schema、database_description CSV、字段样例值以及本次错题根因汇总自动生成。

## 1. 数据库概览

| 表 | 行数 | 字段数 | 作用 |
|---|---:|---:|---|
| `Examination` | 806 | 13 | 临床检查/诊断记录表。 |
| `Laboratory` | 13908 | 44 | 实验室检查结果表。 |
| `Patient` | 1238 | 7 | 患者主表。 |

## 2. 表关系与 Join 注意点

### 2.1 SQLite 声明的外键

| From | To | 说明 |
|---|---|---|
| `Examination.ID` | `Patient.ID` | 声明外键 |
| `Laboratory.ID` | `Patient.ID` | 声明外键 |


### 2.3 通用注意点

- 字段名含空格、连字符、括号或大小写敏感时，建议使用双引号，例如 `"Some Column"`。
- 表中 ID 字段通常只是连接键；最终输出是否需要 ID，要以 question/gold 语义为准，避免多输出中间列。
- 做 top/max/min/rank 查询时，先确认是否需要返回所有并列值，而不是默认 `LIMIT 1`。
- 很多字段名含空格或特殊字符，例如 `First Date`，必须用双引号或反引号引用。
- 患者题常要先定位 `Patient.ID`，再连 `Examination` / `Laboratory`。
- 日期和年龄题要区分生日、首次入院日期、检查日期、实验室日期。

## 3. 字段明细

### 3.1 `Examination`

临床检查/诊断记录表。 行数：`806`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `ID` | `INTEGER` | FK -> Patient.ID | 检查记录的唯一标识符。 | 5329900, 5346280, 5399200 | 36 | distinct=763; range=14872 - 9334040 |
| `Examination Date` | `DATE` |  | 检查日期。 过滤前注意实际日期格式。 | 1995-09-04, 1995-06-19, 1996-02-05 | 10 | distinct=475 |
| `aCL IgG` | `REAL` |  | 抗心磷脂抗体 IgG 指标。 | 0.0, 0.8, 1.0 | 0 | distinct=115; range=0.0 - 2150.3 |
| `aCL IgM` | `REAL` |  | 抗心磷脂抗体 IgM 指标。 | 0.0, 1.8, 1.7 | 0 | distinct=140; range=0.0 - 187122.0 |
| `ANA` | `INTEGER` |  | 抗核抗体 ANA 指标。 | 0, 16, 64 | 38 | distinct=8; range=0 - 4096 |
| `ANA Pattern` | `TEXT` |  | 抗核抗体 ANA 模式。 | S, P, P,S | 261 | distinct=15 |
| `aCL IgA` | `INTEGER` |  | 抗心磷脂抗体 IgA 指标。 | 0, 3, 2 | 0 | distinct=52; range=0 - 48547 |
| `Diagnosis` | `TEXT` |  | 诊断。 | SLE, SjS, RA | 331 | distinct=181 |
| `KCT` | `TEXT` |  | KCT 凝血检查指标。 | -, + | 660 | distinct=2 |
| `RVVT` | `TEXT` |  | RVVT 凝血检查指标。 | -, + | 660 | distinct=2 |
| `LAC` | `TEXT` |  | 狼疮抗凝物 LAC 指标。 | -, + | 584 | distinct=2 |
| `Symptoms` | `TEXT` |  | 症状记录。 | CNS lupus, brain infarction, AMI | 726 | distinct=39 |
| `Thrombosis` | `INTEGER` |  | 血栓诊断/血栓状态。 | 0, 1, 2 | 0 | distinct=4; range=0 - 3 |

### 3.2 `Laboratory`

实验室检查结果表。 行数：`13908`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `ID` | `INTEGER` | PK, NOT NULL, FK -> Patient.ID | 实验室记录的唯一标识符。 | 2933261, 3182521, 444499 | 0 | distinct=302; range=27654 - 5452747 |
| `Date` | `DATE` | PK, NOT NULL | 日期。 过滤前注意实际日期格式。 | 1985-11-11, 1985-09-09, 1984-10-01 | 0 | distinct=3723 |
| `GOT` | `INTEGER` |  | GOT 实验室检查指标。 | 16, 18, 15 | 2630 | distinct=218; range=3 - 21480 |
| `GPT` | `INTEGER` |  | GPT 实验室检查指标。 | 11, 13, 14 | 2634 | distinct=302; range=1 - 4780 |
| `LDH` | `INTEGER` |  | LDH 实验室检查指标。 | 142, 143, 148 | 2603 | distinct=917; range=25 - 67080 |
| `ALP` | `INTEGER` |  | ALP 实验室检查指标。 | 67, 80, 62 | 2757 | distinct=532; range=11 - 1308 |
| `TP` | `REAL` |  | TP 实验室检查指标。 | 7.1, 7.0, 7.2 | 2790 | distinct=62; range=0.0 - 9.9 |
| `ALB` | `REAL` |  | ALB 实验室检查指标。 | 4.2, 4.3, 4.1 | 2840 | distinct=39; range=1.0 - 5.8 |
| `UA` | `REAL` |  | UA 实验室检查指标。 | 3.8, 3.9, 4.4 | 2805 | distinct=132; range=0.4 - 17.3 |
| `UN` | `INTEGER` |  | UN 实验室检查指标。 | 12, 13, 14 | 2670 | distinct=108; range=0 - 152 |
| `CRE` | `REAL` |  | CRE 实验室检查指标。 | 0.6, 0.7, 0.5 | 2655 | distinct=65; range=0.1 - 17.1 |
| `T-BIL` | `REAL` |  | T-BIL 实验室检查指标。 | 0.4, 0.5, 0.3 | 4287 | distinct=40; range=0.1 - 7.9 |
| `T-CHO` | `INTEGER` |  | T-CHO 实验室检查指标。 | 185, 194, 170 | 3244 | distinct=325; range=37 - 568 |
| `TG` | `INTEGER` |  | TG 实验室检查指标。 | 62, 70, 91 | 7471 | distinct=392; range=1 - 867 |
| `CPK` | `INTEGER` |  | CPK 实验室检查指标。 | 17, 16, 18 | 8892 | distinct=463; range=0 - 10835 |
| `GLU` | `INTEGER` |  | GLU 实验室检查指标。 | 101, 100, 92 | 12203 | distinct=208; range=62 - 499 |
| `WBC` | `REAL` |  | WBC 实验室检查指标。 | 5.3, 6.5, 6.4 | 1827 | distinct=217; range=0.9 - 35.2 |
| `RBC` | `REAL` |  | RBC 实验室检查指标。 | 4.4, 4.2, 4.5 | 1827 | distinct=56; range=0.4 - 6.6 |
| `HGB` | `REAL` |  | HGB 实验室检查指标。 | 12.8, 13.1, 13.0 | 1827 | distinct=138; range=1.3 - 18.9 |
| `HCT` | `REAL` |  | HCT 实验室检查指标。 | 39.1, 38.6, 37.7 | 1827 | distinct=363; range=3.0 - 56.0 |
| `PLT` | `INTEGER` |  | PLT 实验室检查指标。 | 248, 271, 202 | 2621 | distinct=657; range=5 - 5844 |
| `PT` | `REAL` |  | PT 实验室检查指标。 | 11.3, 11.4, 11.8 | 13287 | distinct=104; range=10.1 - 27.0 |
| `APTT` | `INTEGER` |  | APTT 实验室检查指标。 | 95, 96, 93 | 13857 | distinct=27; range=57 - 146 |
| `FG` | `REAL` |  | FG 实验室检查指标。 | 26.4, 34.4, 35.6 | 13453 | distinct=279; range=23.8 - 106.5 |
| `PIC` | `INTEGER` |  | PIC 实验室检查指标。 | 320, 150, 200 | 13832 | distinct=63; range=114 - 700 |
| `TAT` | `INTEGER` |  | TAT 实验室检查指标。 | 101, 131, 107 | 13766 | distinct=82; range=63 - 183 |
| `TAT2` | `INTEGER` |  | TAT2 实验室检查指标。 | 108, 101, 125 | 13789 | distinct=60; range=59 - 155 |
| `U-PRO` | `TEXT` |  | U-PRO 实验室检查指标。 | -, 0, TR | 4241 | distinct=16 |
| `IGG` | `INTEGER` |  | IGG 实验室检查指标。 | 1380, 1390, 1134 | 11228 | distinct=1516; range=3 - 6510 |
| `IGA` | `INTEGER` |  | IGA 实验室检查指标。 | 331, 300, 337 | 11228 | distinct=682; range=1 - 1765 |
| `IGM` | `INTEGER` |  | IGM 实验室检查指标。 | 128, 132, 81 | 11230 | distinct=487; range=0 - 1573 |
| `CRP` | `TEXT` |  | CRP 实验室检查指标。 | -, <0.3, <0.2 | 2453 | distinct=211 |
| `RA` | `TEXT` |  | RA 实验室检查指标。 | -, +, 2+ | 11053 | distinct=5 |
| `RF` | `TEXT` |  | RF 实验室检查指标。 | <40, <20.5, <19.5 | 10571 | distinct=903 |
| `C3` | `INTEGER` |  | C3 实验室检查指标。 | 72, 59, 52 | 8447 | distinct=151; range=15 - 196 |
| `C4` | `INTEGER` |  | C4 实验室检查指标。 | 21, 17, 24 | 8447 | distinct=62; range=3 - 80 |
| `RNP` | `TEXT` |  | RNP 实验室检查指标。 | 0, negative, 4 | 13765 | distinct=8 |
| `SM` | `TEXT` |  | SM 实验室检查指标。 | 0, negative, 1 | 13780 | distinct=5 |
| `SC170` | `TEXT` |  | SC170 实验室检查指标。 | 0, negative, 4 | 13880 | distinct=5 |
| `SSA` | `TEXT` |  | SSA 实验室检查指标。 | 0, negative, 16 | 13809 | distinct=7 |
| `SSB` | `TEXT` |  | SSB 实验室检查指标。 | 0, negative, 32 | 13815 | distinct=6 |
| `CENTROMEA` | `TEXT` |  | CENTROMEA 实验室检查指标。 | 0, negative | 13893 | distinct=2 |
| `DNA` | `TEXT` |  | DNA 实验室检查指标。 | 18, 18.2, 30.3 | 13839 | distinct=66 |
| `DNA-II` | `INTEGER` |  | DNA-II 实验室检查指标。 |  | 13908 | distinct=0 |

### 3.3 `Patient`

患者主表。 行数：`1238`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `ID` | `INTEGER` | PK, NOT NULL | 患者的唯一标识符。 | 2110, 11408, 12052 | 0 | distinct=1238; range=2110 - 5845877 |
| `SEX` | `TEXT` |  | 患者性别。 | F, M, | 0 | distinct=3 |
| `Birthday` | `DATE` |  | 出生日期。 | 1938-01-01, 1968-05-21, 1935-04-19 | 1 | distinct=1193 |
| `Description` | `DATE` |  | 患者记录描述/说明日期。 | 1996-12-03, 1997-08-20, 1991-08-13 | 216 | distinct=97 |
| `First Date` | `DATE` |  | 首次入院日期。 过滤前注意实际日期格式。 | 1992-05-18, 1992-12-14, 1993-03-29 | 251 | distinct=797 |
| `Admission` | `TEXT` |  | 入院信息。 | -, +, | 0 | distinct=4 |
| `Diagnosis` | `TEXT` |  | 诊断。 | SLE, SJS, RA | 0 | distinct=220 |

## 4. 常用查询模板

## 5. Text-to-SQL 易错点

- 以下字段名需要特别注意引用：`Examination.Examination Date`, `Examination.aCL IgG`, `Examination.aCL IgM`, `Examination.ANA Pattern`, `Examination.aCL IgA`, `Laboratory.T-BIL`, `Laboratory.T-CHO`, `Laboratory.U-PRO`, `Laboratory.DNA-II`, `Patient.First Date`。
- 日期/时间相关字段：`Examination.Examination Date`, `Laboratory.Date`, `Patient.Birthday`, `Patient.First Date`。过滤前先查看实际字符串格式。
- 本次评测错题暴露出的典型坑：
  - qid1149（输出形状/答案格式错误）：模型算的是比例 fraction，并且额外输出了分子和分母；gold 按百分比口径乘以 100，只输出一个值。这里不是筛选条件错，而是百分比尺度和输出形状错。
  - qid1166（协议/轮数/收敛失败）：多轮工具协议失败。模型已经找到方向，但反复违反单条 SQL 工具约束，耗尽轮数，没有产出最终 SQL。
  - qid1168（SQL 可执行性错误）：- `First Date` 是带空格字段，pred 写成 `p.First Date`，没有使用 `p."First Date"` 或 `p.\`First Date\``，直接语法错误。 - 题目问“oldest SJS patient”，应按 `Birthday ASC` 找最老患者；pred 却按 `age_at_arrival ASC` 排序，语义变成“入院年龄最小”。 - gold 只要求输出最后一次实验室日期和入院年龄，pred 还额外输出了 `p.ID`。
  - qid1169（聚合/公式/粒度错误）：模型在 `Laboratory` 行粒度上计数，没有按患者 `COUNT(DISTINCT ID)` 去重；同时额外输出了分子分母列。核心错因是患者粒度和实验室记录粒度混淆。
  - qid1175（输出形状/答案格式错误）：查询定位和年龄计算都对了，但输出形状错。gold 只要 `(age, Diagnosis)`，pred 多输出了 `ID`、`Date`、`HGB`，且列顺序也不是 gold 的两列顺序。
  - qid1179（输出形状/答案格式错误）：答案值正确，但额外输出了日期、描述日期和诊断列；严格 EX 下列数不一致。
  - qid1185（SQL 可执行性错误）：- 模型前面尝试计算 `(Nov sum - Dec sum) / Nov sum`，但把字段 `T-CHO` 写成未引用的 `T-CHO`，SQLite 按减号解析，报 `no such column: T`。 - 后续没有修成 `\`T-CHO\`` 或 `"T-CHO"`，反而退回到探索 1981 年 11 月的样例记录。 - 最后一轮探索 SQL 被当成最终 `pred_sql`，完全没有按患者生日过滤，也没有计算下降率。
  - qid1187（类型/日期/NULL/值规范错误）：题目中的 “examined” 在 evidence 中明确指 `Laboratory.Date`，因为 GPT/ALB 都在 `Laboratory`；模型误把日期条件放到 `Examination` 表，额外 join 缩小了集合。
  - qid1192（聚合/公式/粒度错误）：- `T-BIL` 是带连字符字段，必须写成 `l."T-BIL"` 或 `l.\`T-BIL\``；pred 写成 `l.T_BIL`，字段名不存在。 - 即使字段名修正，pred 还额外输出了患者属性和 `l.Date`、`T-BIL`；gold 只输出 `DISTINCT ID`。
  - qid1205（输出形状/答案格式错误）：判断逻辑正确，纯输出形状错误。gold 只要布尔标签列；pred 额外输出了 `ID`、`SEX`、`UA`。
  - qid1209（排序/TopK/Tie/排名错误）：gold 先按 `Laboratory` 找 `DISTINCT ID`，再回到 `Patient` 输出患者诊断；pred 直接输出每条异常 GPT 检验记录，导致重复患者大量出现，并额外输出了 ID、生日、GPT。
  - qid1227（聚合/公式/粒度错误）：- gold 用 `SELECT DISTINCT ID, age` 后再 `AVG(age)`，按患者平均。 - pred 直接在 join 后的实验室记录上平均，每个患者按高胆固醇记录条数被重复加权。 - pred 还用 `julianday / 365.25` 得到小数年龄；gold 用整岁公式。核心错因仍是未按患者去重。
  - qid1231（类型/日期/NULL/值规范错误）：pred 写成 `p.Birthday BETWEEN '1936' AND '1956'`。`Birthday` 是完整日期字符串，不能和年份字符串直接比较；应该用 `STRFTIME('%Y', p.Birthday) BETWEEN '1936' AND '1956'`。这个错误导致本应命中的 1938、1944 年患者没有被正确保留。
  - qid1235（SQL 可执行性错误）：- 最直接原因是多了一个右括号，SQL 语法错误。 - 早期轮次曾产出可执行 SQL，但年龄是天数 `32957`，后续修复时引入括号错误。 - 即使修掉语法，pred 输出顺序是 `(ID, Diagnosis, age)`，gold 是 `(Diagnosis, ID, age)`，列顺序仍不一致。
  - qid1239（类型/日期/NULL/值规范错误）：pred 只做 `当前年份 - 出生年份`，没有按月日比较扣 1；gold 使用 `strftime('%m-%d','now') < strftime('%m-%d', Birthday)` 做整岁修正。
  - qid1241（输出形状/答案格式错误）：差值本身正确，但输出形状错误。gold 只要差值一列；pred 额外输出了两个中间计数。
  - qid1242（聚合/公式/粒度错误）：过滤语义基本命中，但输出粒度错。gold 要的是患者 ID 去重；pred 把每条 1984 年正常血小板实验室记录都输出，并额外带出生日、PLT、日期，导致同一患者多行。
  - qid1243（类型/日期/NULL/值规范错误）：多轮协议没有完成最终阶段。模型没有产出可评测 SQL；并且探索中对年龄条件的表达式也不可靠，应该使用 `date(Birthday, '+55 years') < date('now')`。
  - 另有 8 条错题根因，详见 `wrong_root_cause_summary_238.md`。
