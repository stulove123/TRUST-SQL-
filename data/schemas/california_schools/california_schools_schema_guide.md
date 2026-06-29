# california_schools Schema Guide

本文件整理 `california_schools` SQLite 数据库的表结构、字段含义、示例值和 Text-to-SQL 常见 join/过滤注意点。

- 数据库文件：`/root/autodl-tmp/DeepEye-SQL/data/bird/dev/dev_databases/california_schools/california_schools.sqlite`
- 字段说明来源：`/root/autodl-tmp/text_to_sql_benchmarks/data/schemas/california_schools/database_description`
- 生成时间：`2026-06-19 16:35:24`

## 1. 数据库概览

| 表 | 行数 | 作用 |
|---|---:|---|
| `schools` | 17686 | 主实体表。既包含具体学校，也包含学区、县教育办公室、行政机构等记录。做“school”语义查询时经常需要排除 School IS NULL 的 district-level 记录。 |
| `frpm` | 9986 | FRPM/招生统计表。通常一行对应一个 CDSCode 在某学年的免费餐、减价餐和 enrollment 信息。 |
| `satscores` | 2269 | SAT 统计表。包含 school-level 和 district-level 两种粒度，rtype 是重要过滤字段。 |

## 2. 表关系与 Join 注意点

### 2.1 推荐 Join

```sql
-- schools 与 frpm：可以直接按字符串连接
SELECT *
FROM schools AS s
JOIN frpm AS f ON s.CDSCode = f.CDSCode;

-- schools 与 satscores：建议 cast 后连接，避免前导 0 导致漏匹配
SELECT *
FROM schools AS s
JOIN satscores AS sat
  ON CAST(s.CDSCode AS INTEGER) = CAST(sat.cds AS INTEGER);
```

- `frpm.CDSCode = schools.CDSCode` 可匹配 `9986` 行，等于 `frpm` 全表行数。
- `satscores.cds = schools.CDSCode` 直接字符串连接只匹配 `2058` 行；cast 后连接匹配 `2269` 行，等于 `satscores` 全表行数。

### 2.2 常见过滤规则

- `schools.School IS NULL` 有 `1369` 行，常表示学区办公室、县教育办公室或其他 district-level 记录，不是具体学校。
- `frpm."School Code" = '0000000'` 或 `frpm."School Name" = 'District Office'` 有 `45` 行，通常是 district-level 记录。
- 问题中明确说 “school” 时，常需要加 `schools.School IS NOT NULL`，或排除 `frpm."School Code" = '0000000'`。
- `satscores.rtype = 'S'` 表示 school-level，`rtype = 'D'` 表示 district-level；问具体学校 SAT 时通常过滤 `rtype = 'S'`。
- BIRD/Arcwise-Plat 中有题目把 “Total enrollment” 定义为 `frpm."Enrollment (K-12)" + frpm."Enrollment (Ages 5-17)"`，需要看 evidence。
- FRPM rate 可直接用表中百分比字段，也可按 `FRPM Count / Enrollment` 计算；题目如要求比例，要确认使用 K-12 还是 Ages 5-17。
- SAT excellence rate 常用 `NumGE1500 * 1.0 / NumTstTakr`。

## 3. 字段明细

### 3.1 `schools`

主实体表。既包含具体学校，也包含学区、县教育办公室、行政机构等记录。做“school”语义查询时经常需要排除 School IS NULL 的 district-level 记录。

| 字段 | SQLite 类型 | 约束 | 中文含义 | 示例值 | NULL 数 |
|---|---|---|---|---|---:|
| `CDSCode` | `TEXT` | PK, NOT NULL | 加州学校/学区/教育机构唯一代码。主键。常用于连接 frpm.CDSCode；连接 satscores.cds 时注意前导 0。 | 01100170000000, 01100170109835, 01100170112607 | 0 |
| `NCESDist` | `TEXT` |  | NCES 学区编号，7 位；前 2 位表示州，后 5 位表示学区。 | 0691051, 0600002, 0600003 | 1030 |
| `NCESSchool` | `TEXT` |  | NCES 学校编号，通常 5 位；与 NCESDist 合起来构成学校级 NCES ID。 | 10546, 10947, 12283 | 5040 |
| `StatusType` | `TEXT` | NOT NULL | 机构状态。常见值：Active、Closed、Merged、Pending。 | Active, Closed, Merged | 0 |
| `County` | `TEXT` | NOT NULL | 县名。 | Alameda, Alpine, Amador | 0 |
| `District` | `TEXT` | NOT NULL | 学区名或教育行政机构名。 | Alameda County Office of Education, California School for the Blind (State Special Schl), California School for the Deaf-Fremont (State Special Schl) | 0 |
| `School` | `TEXT` |  | 学校名。为空时通常表示该记录不是具体学校，而是学区办公室、县教育办公室或其他 district-level 记录。 | FAME Public Charter, Envision Academy for Arts & Technology, Aspire California College Preparatory Academy | 1369 |
| `Street` | `TEXT` |  | 实体地址。 | 313 West Winton Avenue, 39899 Balentine Drive, Suite 335, 1515 Webster Street | 294 |
| `StreetAbr` | `TEXT` |  | 缩写形式的实体地址。 | 313 West Winton Ave., 39899 Balentine Dr., Ste. 335, 1515 Webster St. | 294 |
| `City` | `TEXT` |  | 实体地址所在城市。 | Hayward, Newark, Oakland | 293 |
| `Zip` | `TEXT` |  | 实体地址邮编。 | 94544-1136, 94560-5359, 94612-3355 | 293 |
| `State` | `TEXT` |  | 实体地址所在州，通常为 CA。 | CA | 293 |
| `MailStreet` | `TEXT` |  | 邮寄地址；缺失时数据中可能用实体地址补齐。 | 313 West Winton Avenue, 39899 Balentine Drive, Suite 335, 1515 Webster Street | 292 |
| `MailStrAbr` | `TEXT` |  | 缩写形式的邮寄地址。 | 313 West Winton Ave., 39899 Balentine Dr., Ste. 335, 1515 Webster St. | 292 |
| `MailCity` | `TEXT` |  | 邮寄城市。 | Hayward, Newark, Oakland | 292 |
| `MailZip` | `TEXT` |  | 邮寄邮编。 | 94544-1136, 94560-5359, 94612 | 292 |
| `MailState` | `TEXT` |  | 邮寄州。 | CA | 292 |
| `Phone` | `TEXT` |  | 联系电话。 | (510) 887-0152, (510) 596-8901, (510) 686-4131 | 5969 |
| `Ext` | `TEXT` |  | 电话分机。 | 130, 1240, 1200 | 17146 |
| `Website` | `TEXT` |  | 学校、学区或教育行政机构网站。 | www.acoe.org, www.envisionacademy.org/, www.aspirepublicschools.org | 10722 |
| `OpenDate` | `DATE` |  | 学校开办日期。district-level 记录常为空。 | 2005-08-29, 2006-08-28, 2008-08-21 | 1369 |
| `ClosedDate` | `DATE` |  | 学校关闭日期。 | 2015-07-31, 2015-06-30, 1989-06-30 | 11992 |
| `Charter` | `INTEGER` |  | 是否 charter school：1 表示是，0 表示否；district-level 记录可能为空。 | 1, 0 | 1369 |
| `CharterNum` | `TEXT` |  | charter school 编号，通常为 4 位。 | 0728, 0811, 1049 | 15885 |
| `FundingType` | `TEXT` |  | charter school 资助类型，如 Directly funded、Locally funded。 | Directly funded, Locally funded, Not in CS funding model | 16044 |
| `DOC` | `TEXT` | NOT NULL | District Ownership Code，用于表示教育行政机构类别。 | 00, 31, 34 | 0 |
| `DOCType` | `TEXT` | NOT NULL | DOC 的文本解释，如 County Office of Education、Unified School District。 | County Office of Education (COE), State Special Schools, Non-School Locations | 0 |
| `SOC` | `TEXT` |  | School Ownership Code，用于表示学校类型。 | 65, 66, 60 | 1369 |
| `SOCType` | `TEXT` |  | SOC 的文本解释，如 Elementary School、High School、K-12 Schools。 | K-12 Schools (Public), High Schools (Public), Elementary Schools (Public) | 1369 |
| `EdOpsCode` | `TEXT` |  | Educational Option Code，教育选项短代码，如 TRAD、JUV、COMM。 | TRAD, JUV, COMM | 5711 |
| `EdOpsName` | `TEXT` |  | Educational Option Name，教育选项名称，如 Traditional。 | Traditional, Juvenile Court School, County Community School | 5711 |
| `EILCode` | `TEXT` |  | Educational Instruction Level Code，教育阶段短代码，如 ELEM、HS、UG。 | ELEMHIGH, HS, ELEM | 1369 |
| `EILName` | `TEXT` |  | Educational Instruction Level Name，教育阶段名称。 | Elementary-High Combination, High School, Elementary | 1369 |
| `GSoffered` | `TEXT` |  | Grade Span Offered，机构提供或支持的最低到最高年级。 | K-12, 9-12, K-8 | 3882 |
| `GSserved` | `TEXT` |  | Grade Span Served，最近 CALPADS 数据中实际有学生注册的年级跨度。 | K-12, 9-12, K-7 | 5743 |
| `Virtual` | `TEXT` |  | 虚拟教学类型。常见代码：F=Exclusively Virtual，V=Primarily Virtual，C=Primarily Classroom，N=Not Virtual，P=Partial Virtual。 | P, N, F | 6868 |
| `Magnet` | `INTEGER` |  | 是否 magnet school 或提供 magnet program：1 表示是，0 表示否。 | 0, 1 | 7076 |
| `Latitude` | `REAL` |  | 纬度。 | 37.658212, 37.521436, 37.80452 | 4823 |
| `Longitude` | `REAL` |  | 经度。 | -122.09713, -121.99391, -122.26815 | 4823 |
| `AdmFName1` | `TEXT` |  | 第一位管理员/校长/负责人名。 | L Karen, Laura, Clifford | 5986 |
| `AdmLName1` | `TEXT` |  | 第一位管理员/校长/负责人姓。 | Monroe, Robell, Thompson | 5986 |
| `AdmEmail1` | `TEXT` |  | 第一位管理员/校长/负责人邮箱。 | lkmonroe@acoe.org, laura@envisionacademy.org, cliffordt@communityschoolforcreativeeducation.org | 6012 |
| `AdmFName2` | `TEXT` |  | 第二位管理员/校长/负责人名。 | Sau-Lim (Lance), Jennifer, Annalisa | 17255 |
| `AdmLName2` | `TEXT` |  | 第二位管理员/校长/负责人姓。 | Tsang, Koelling, Moore | 17255 |
| `AdmEmail2` | `TEXT` |  | 第二位管理员/校长/负责人邮箱。 | stsang@unityhigh.org, jkoelling@efcps.net, annalisa.moore@neaclc.org | 17262 |
| `AdmFName3` | `TEXT` |  | 第三位管理员/校长/负责人名。 | Drew, Irma, Vickie | 17644 |
| `AdmLName3` | `TEXT` |  | 第三位管理员/校长/负责人姓。 | Sarratore, Munoz, Chang | 17644 |
| `AdmEmail3` | `TEXT` |  | 第三位管理员/校长/负责人邮箱。 | dsarratore@vincentacademy.org, gmunoz@piedmont.k12.ca.us, vickiechang@acoe.org | 17644 |
| `LastUpdate` | `DATE` | NOT NULL | 该记录最后更新时间。 | 2015-06-23, 2015-09-01, 2015-06-18 | 0 |

### 3.2 `frpm`

FRPM/招生统计表。通常一行对应一个 CDSCode 在某学年的免费餐、减价餐和 enrollment 信息。

| 字段 | SQLite 类型 | 约束 | 中文含义 | 示例值 | NULL 数 |
|---|---|---|---|---|---:|
| `CDSCode` | `TEXT` | PK, NOT NULL | 对应 schools.CDSCode。主键。 | 01100170109835, 01100170112607, 01100170118489 | 0 |
| `Academic Year` | `TEXT` |  | 统计学年，例如 2014-2015。 | 2014-2015 | 0 |
| `County Code` | `TEXT` |  | 县代码。 | 01, 02, 03 | 0 |
| `District Code` | `INTEGER` |  | 学区代码。 | 10017, 31609, 31617 | 0 |
| `School Code` | `TEXT` |  | 学校代码。0000000 通常表示 district-level / District Office，不是具体学校。 | 0109835, 0112607, 0118489 | 0 |
| `County Name` | `TEXT` |  | 县名。 | Alameda, Alpine, Amador | 0 |
| `District Name` | `TEXT` |  | 学区名。 | Alameda County Office of Education, California School for the Blind (State Special Schl), California School for the Deaf-Fremont (State Special Schl) | 0 |
| `School Name` | `TEXT` |  | 学校名；district-level 记录可能为 District Office。 | FAME Public Charter, Envision Academy for Arts & Technology, Aspire California College Preparatory Academy | 0 |
| `District Type` | `TEXT` |  | 学区类型。 | County Office of Education (COE), State Special Schools, Unified School District | 0 |
| `School Type` | `TEXT` |  | 学校类型。 | K-12 Schools (Public), High Schools (Public), Elementary Schools (Public) | 45 |
| `Educational Option Type` | `TEXT` |  | 教育选项类型，如 Traditional。 | Traditional, Juvenile Court School, County Community School | 45 |
| `NSLP Provision Status` | `TEXT` |  | National School Lunch Program 相关 provision 状态。 | Breakfast Provision 2, Provision 2, CEP | 8139 |
| `Charter School (Y/N)` | `INTEGER` |  | 是否 charter school：1=Y，0=N。 | 1, 0 | 45 |
| `Charter School Number` | `TEXT` |  | charter school 编号。 | 0728, 0811, 1049 | 8819 |
| `Charter Funding Type` | `TEXT` |  | charter school 资助类型。 | Directly funded, Locally funded, Not in CS funding model | 8819 |
| `IRC` | `INTEGER` |  | 数据说明中标注为不太有用的辅助字段。 | 1, 0 | 45 |
| `Low Grade` | `TEXT` |  | 最低年级。 | K, 9, 1 | 0 |
| `High Grade` | `TEXT` |  | 最高年级。 | 12, 8, 5 | 0 |
| `Enrollment (K-12)` | `REAL` |  | K-12 注册/招生人数。 | 1087.0, 395.0, 244.0 | 0 |
| `Free Meal Count (K-12)` | `REAL` |  | K-12 符合免费餐资格人数。 | 565.0, 186.0, 134.0 | 56 |
| `Percent (%) Eligible Free (K-12)` | `REAL` |  | K-12 免费餐资格比例，通常等于 Free Meal Count / Enrollment。 | 0.519779208831647, 0.470886075949367, 0.549180327868853 | 56 |
| `FRPM Count (K-12)` | `REAL` |  | K-12 免费或减价餐资格人数。FRPM = Free or Reduced Price Meal。 | 715.0, 186.0, 175.0 | 50 |
| `Percent (%) Eligible FRPM (K-12)` | `REAL` |  | K-12 免费或减价餐资格比例，通常等于 FRPM Count / Enrollment。 | 0.657773689052438, 0.470886075949367, 0.717213114754098 | 50 |
| `Enrollment (Ages 5-17)` | `REAL` |  | 5-17 岁注册/招生人数。 | 1070.0, 376.0, 230.0 | 14 |
| `Free Meal Count (Ages 5-17)` | `REAL` |  | 5-17 岁符合免费餐资格人数。 | 553.0, 182.0, 128.0 | 78 |
| `Percent (%) Eligible Free (Ages 5-17)` | `REAL` |  | 5-17 岁免费餐资格比例。 | 0.516822429906542, 0.484042553191489, 0.556521739130435 | 78 |
| `FRPM Count (Ages 5-17)` | `REAL` |  | 5-17 岁免费或减价餐资格人数。 | 702.0, 182.0, 168.0 | 72 |
| `Percent (%) Eligible FRPM (Ages 5-17)` | `REAL` |  | 5-17 岁免费或减价餐资格比例。 | 0.65607476635514, 0.484042553191489, 0.730434782608696 | 72 |
| `2013-14 CALPADS Fall 1 Certification Status` | `INTEGER` |  | 2013-14 CALPADS Fall 1 认证状态。当前库中均为 1。 | 1 | 0 |

### 3.3 `satscores`

SAT 统计表。包含 school-level 和 district-level 两种粒度，rtype 是重要过滤字段。

| 字段 | SQLite 类型 | 约束 | 中文含义 | 示例值 | NULL 数 |
|---|---|---|---|---|---:|
| `cds` | `TEXT` | PK, NOT NULL | California Department Schools 代码。逻辑上对应 schools.CDSCode；注意可能缺少前导 0。 | 10101080000000, 10101080109991, 10101080111682 | 0 |
| `rtype` | `TEXT` | NOT NULL | 记录类型。S=school-level，D=district-level。 | D, S | 0 |
| `sname` | `TEXT` |  | 学校名。rtype=D 时通常为空。 | FAME Public Charter, Envision Academy for Arts & Technology, Aspire California College Preparatory Academy | 520 |
| `dname` | `TEXT` |  | 学区名。 | Alameda County Office of Education, Alameda Unified, Albany City Unified | 0 |
| `cname` | `TEXT` |  | 县名。 | Alameda, Amador, Butte | 0 |
| `enroll12` | `INTEGER` | NOT NULL | 12 年级注册/招生人数。 | 398, 62, 75 | 0 |
| `NumTstTakr` | `INTEGER` | NOT NULL | SAT 参加人数。 | 88, 17, 71 | 0 |
| `AvgScrRead` | `INTEGER` |  | SAT 阅读平均分。 | 418, 503, 397 | 596 |
| `AvgScrMath` | `INTEGER` |  | SAT 数学平均分。 | 418, 546, 387 | 596 |
| `AvgScrWrite` | `INTEGER` |  | SAT 写作平均分。 | 417, 505, 395 | 596 |
| `NumGE1500` | `INTEGER` |  | SAT 总分大于等于 1500 的考生人数。常用于计算 Excellence Rate = NumGE1500 / NumTstTakr。 | 14, 9, 5 | 596 |

## 4. 常用查询模板

### 4.1 查询具体学校，不含 district office

```sql
SELECT s.CDSCode, s.School, s.District, s.County
FROM schools AS s
WHERE s.School IS NOT NULL;
```

### 4.2 学校 + FRPM/enrollment

```sql
SELECT s.CDSCode, s.School, f."Enrollment (K-12)", f."FRPM Count (K-12)"
FROM schools AS s
JOIN frpm AS f ON s.CDSCode = f.CDSCode
WHERE s.School IS NOT NULL;
```

### 4.3 学校 + SAT 分数

```sql
SELECT s.CDSCode, s.School, sat.NumTstTakr, sat.AvgScrRead, sat.AvgScrMath, sat.AvgScrWrite
FROM schools AS s
JOIN satscores AS sat
  ON CAST(s.CDSCode AS INTEGER) = CAST(sat.cds AS INTEGER)
WHERE sat.rtype = 'S';
```

### 4.4 SAT 高分率

```sql
SELECT sat.sname, sat.NumGE1500 * 1.0 / sat.NumTstTakr AS excellence_rate
FROM satscores AS sat
WHERE sat.rtype = 'S' AND sat.NumTstTakr > 0;
```

### 4.5 FRPM 比例

```sql
SELECT f."School Name",
       f."FRPM Count (K-12)" * 1.0 / f."Enrollment (K-12)" AS frpm_rate
FROM frpm AS f
WHERE f."Enrollment (K-12)" > 0
  AND f."School Code" != '0000000';
```

## 5. Text-to-SQL 易错点

- **具体学校 vs 学区/办公室**：`CDSCode` 不为空不代表一定是具体学校。`schools.School IS NULL` 或 `frpm."School Code" = '0000000'` 往往是 district-level。
- **前导 0 join**：`satscores.cds` 有时缺前导 0，连接 `schools` 时用 `CAST(... AS INTEGER)` 更稳。
- **同名字段来源**：`schools.School` 是主档案中的学校名；`frpm."School Name"` 是 FRPM 统计表中的学校名；二者可对应但不要随意混用过滤逻辑。
- **粒度过滤**：SAT 查询要注意 `rtype`，FRPM 查询要注意 `School Code` 和 district office。
- **百分比字段**：表中百分比字段是小数比例，不是 0-100 的百分数展示；输出时是否乘 100 要看题意。
- **空值字段**：`OpenDate`、`ClosedDate`、`Charter`、`Magnet`、管理员信息等在 district-level 或历史记录中可能为空。
