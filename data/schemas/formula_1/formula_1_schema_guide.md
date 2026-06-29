# formula_1 Schema Guide

本文件整理 `formula_1` SQLite 数据库的表结构、字段含义、示例值和 Text-to-SQL 常见 join/过滤注意点。

- 数据库文件：`/root/autodl-tmp/DeepEye-SQL/data/arcwise_plat/dev/dev_databases/formula_1/formula_1.sqlite`
- 字段说明来源：`/root/autodl-tmp/text_to_sql_benchmarks/data/schemas/formula_1/database_description`
- 生成时间：`2026-06-21 22:56:18`
- 生成方式：基于 SQLite schema、database_description CSV、字段样例值以及本次错题根因汇总自动生成。

## 1. 数据库概览

| 表 | 行数 | 字段数 | 作用 |
|---|---:|---:|---|
| `circuits` | 72 | 9 | 赛道维表。 |
| `constructorResults` | 11082 | 5 | 事实/明细表，通常需要 join 维表解释 ID。 |
| `constructorStandings` | 11836 | 7 | 车队积分榜表。 |
| `constructors` | 208 | 5 | 车队维表。 |
| `driverStandings` | 31578 | 7 | 车手积分榜表。 |
| `drivers` | 840 | 9 | 车手维表。 |
| `lapTimes` | 420369 | 6 | 逐圈成绩表。 |
| `pitStops` | 6070 | 7 | 事实/明细表，通常需要 join 维表解释 ID。 |
| `qualifying` | 7397 | 9 | 排位赛成绩表。 |
| `races` | 976 | 8 | 赛事主表。 |
| `results` | 23657 | 18 | 比赛结果事实表。 |
| `seasons` | 68 | 2 | 关系/映射表。 |
| `status` | 134 | 2 | 关系/映射表。 |

## 2. 表关系与 Join 注意点

### 2.1 SQLite 声明的外键

| From | To | 说明 |
|---|---|---|
| `constructorResults.constructorId` | `constructors.constructorId` | 声明外键 |
| `constructorResults.raceId` | `races.raceId` | 声明外键 |
| `constructorStandings.constructorId` | `constructors.constructorId` | 声明外键 |
| `constructorStandings.raceId` | `races.raceId` | 声明外键 |
| `driverStandings.driverId` | `drivers.driverId` | 声明外键 |
| `driverStandings.raceId` | `races.raceId` | 声明外键 |
| `lapTimes.driverId` | `drivers.driverId` | 声明外键 |
| `lapTimes.raceId` | `races.raceId` | 声明外键 |
| `pitStops.driverId` | `drivers.driverId` | 声明外键 |
| `pitStops.raceId` | `races.raceId` | 声明外键 |
| `qualifying.constructorId` | `constructors.constructorId` | 声明外键 |
| `qualifying.driverId` | `drivers.driverId` | 声明外键 |
| `qualifying.raceId` | `races.raceId` | 声明外键 |
| `races.circuitId` | `circuits.circuitId` | 声明外键 |
| `races.year` | `seasons.year` | 声明外键 |
| `results.statusId` | `status.statusId` | 声明外键 |
| `results.constructorId` | `constructors.constructorId` | 声明外键 |
| `results.driverId` | `drivers.driverId` | 声明外键 |
| `results.raceId` | `races.raceId` | 声明外键 |

### 2.2 按字段名推断的常用连接

| From | To | 推断依据 |
|---|---|---|
| `constructorResults.raceId` | `lapTimes.raceId` | 同名字段且目标为 PK |
| `constructorResults.raceId` | `pitStops.raceId` | 同名字段且目标为 PK |
| `constructorStandings.raceId` | `lapTimes.raceId` | 同名字段且目标为 PK |
| `constructorStandings.raceId` | `pitStops.raceId` | 同名字段且目标为 PK |
| `driverStandings.raceId` | `lapTimes.raceId` | 同名字段且目标为 PK |
| `driverStandings.raceId` | `pitStops.raceId` | 同名字段且目标为 PK |
| `driverStandings.driverId` | `lapTimes.driverId` | 同名字段且目标为 PK |
| `driverStandings.driverId` | `pitStops.driverId` | 同名字段且目标为 PK |
| `drivers.driverId` | `lapTimes.driverId` | 同名字段且目标为 PK |
| `drivers.driverId` | `pitStops.driverId` | 同名字段且目标为 PK |
| `lapTimes.raceId` | `pitStops.raceId` | 同名字段且目标为 PK |
| `lapTimes.driverId` | `pitStops.driverId` | 同名字段且目标为 PK |
| `pitStops.raceId` | `lapTimes.raceId` | 同名字段且目标为 PK |
| `pitStops.driverId` | `lapTimes.driverId` | 同名字段且目标为 PK |
| `pitStops.lap` | `lapTimes.lap` | 同名字段且目标为 PK |
| `qualifying.raceId` | `lapTimes.raceId` | 同名字段且目标为 PK |
| `qualifying.raceId` | `pitStops.raceId` | 同名字段且目标为 PK |
| `qualifying.driverId` | `lapTimes.driverId` | 同名字段且目标为 PK |
| `qualifying.driverId` | `pitStops.driverId` | 同名字段且目标为 PK |
| `races.raceId` | `lapTimes.raceId` | 同名字段且目标为 PK |
| `races.raceId` | `pitStops.raceId` | 同名字段且目标为 PK |
| `results.raceId` | `lapTimes.raceId` | 同名字段且目标为 PK |
| `results.raceId` | `pitStops.raceId` | 同名字段且目标为 PK |
| `results.driverId` | `lapTimes.driverId` | 同名字段且目标为 PK |
| `results.driverId` | `pitStops.driverId` | 同名字段且目标为 PK |

### 2.3 通用注意点

- 字段名含空格、连字符、括号或大小写敏感时，建议使用双引号，例如 `"Some Column"`。
- 表中 ID 字段通常只是连接键；最终输出是否需要 ID，要以 question/gold 语义为准，避免多输出中间列。
- 做 top/max/min/rank 查询时，先确认是否需要返回所有并列值，而不是默认 `LIMIT 1`。
- 时间字段存在多种格式：`lapTimes.time` 通常是 `M:SS.mmm`；`results.time` 对冠军和非冠军含义不同；能用 `milliseconds` 时优先用数值字段。
- `results.fastestLapSpeed` 是 TEXT，按速度排序时需要 `CAST(... AS REAL)`。
- 冠军/积分题要区分 `results.points`、`driverStandings.points`、`constructorResults.points`、`constructorStandings.points`。

## 3. 字段明细

### 3.1 `circuits`

赛道维表。 行数：`72`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `circuitId` | `INTEGER` | PK | 赛道 ID。 | 2, 3, 4 | 0 | distinct=72; range=2 - 73 |
| `circuitRef` | `TEXT` | NOT NULL | 赛道引用名。 | BAK, adelaide, ain-diab | 0 | distinct=72 |
| `name` | `TEXT` | NOT NULL | 名称。 | A1-Ring, AVUS, Adelaide Street Circuit | 0 | distinct=72 |
| `location` | `TEXT` |  | 地点。 | Barcelona, California, Spielburg | 0 | distinct=69 |
| `country` | `TEXT` |  | 国家。 | USA, France, Spain | 0 | distinct=32 |
| `lat` | `REAL` |  | 纬度。 | 47.2197, -34.9272, -34.6943 | 0 | distinct=71; range=-34.9272 - 57.2653 |
| `lng` | `REAL` |  | 经度。 | 14.7647, -118.189, -117.273 | 0 | distinct=71; range=-118.189 - 138.927 |
| `alt` | `INTEGER` |  | 海拔。 |  | 72 | distinct=0 |
| `url` | `TEXT` | NOT NULL | URL 链接。 | http://en.wikipedia.org/wiki/A1-Ring, http://en.wikipedia.org/wiki/AVUS, http://en.wikipedia.org/wiki/Adelaide_Street_Circuit | 0 | distinct=72 |

### 3.2 `constructorResults`

事实/明细表，通常需要 join 维表解释 ID。 行数：`11082`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `constructorResultsId` | `INTEGER` | PK | 车队单场结果 ID。 | 1, 2, 3 | 0 | distinct=11082; range=1 - 15579 |
| `raceId` | `INTEGER` | NOT NULL, FK -> races.raceId | 比赛 ID。 外键，指向 `races.raceId`。 | 356, 357, 358 | 0 | distinct=907; range=1 - 982 |
| `constructorId` | `INTEGER` | NOT NULL, FK -> constructors.constructorId | 车队 ID。 外键，指向 `constructors.constructorId`。 | 6, 1, 3 | 0 | distinct=172; range=1 - 210 |
| `points` | `REAL` |  | 积分。 | 0.0, 1.0, 2.0 | 0 | distinct=45; range=0.0 - 66.0 |
| `status` | `TEXT` |  | 合法性状态。 | D | 11065 | distinct=1 |

### 3.3 `constructorStandings`

车队积分榜表。 行数：`11836`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `constructorStandingsId` | `INTEGER` | PK | 车队积分榜记录 ID。 | 1, 2, 3 | 0 | distinct=11836; range=1 - 26872 |
| `raceId` | `INTEGER` | NOT NULL, FK -> races.raceId | 比赛 ID。 外键，指向 `races.raceId`。 | 728, 559, 575 | 0 | distinct=906; range=1 - 982 |
| `constructorId` | `INTEGER` | NOT NULL, FK -> constructors.constructorId | 车队 ID。 外键，指向 `constructors.constructorId`。 | 6, 1, 3 | 0 | distinct=156; range=1 - 210 |
| `points` | `REAL` | NOT NULL | 积分。 | 0.0, 1.0, 3.0 | 0 | distinct=436; range=0.0 - 765.0 |
| `position` | `INTEGER` |  | 职务/职位。 | 1, 2, 3 | 0 | distinct=22; range=1 - 22 |
| `positionText` | `TEXT` |  | 名次文本。 通常不是核心查询字段。 | 1, 2, 3 | 0 | distinct=23 |
| `wins` | `INTEGER` | NOT NULL | 获胜次数。 | 0, 1, 2 | 0 | distinct=20; range=0 - 19 |

### 3.4 `constructors`

车队维表。 行数：`208`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `constructorId` | `INTEGER` | PK | 车队 ID。 | 1, 2, 3 | 0 | distinct=208; range=1 - 210 |
| `constructorRef` | `TEXT` | NOT NULL | 车队引用名。 | adams, afm, ags | 0 | distinct=208 |
| `name` | `TEXT` | NOT NULL | 名称。 | AFM, AGS, ATS | 0 | distinct=208 |
| `nationality` | `TEXT` |  | 国籍。 | British, American, Italian | 0 | distinct=24 |
| `url` | `TEXT` | NOT NULL | URL 链接。 | http://en.wikipedia.org/wiki/Cooper_Car_Company, http://en.wikipedia.org/wiki/Team_Lotus, http://en.wikipedia.org/wiki/Brabham | 0 | distinct=171 |

### 3.5 `driverStandings`

车手积分榜表。 行数：`31578`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `driverStandingsId` | `INTEGER` | PK | 车手积分榜记录 ID。 | 1, 2, 3 | 0 | distinct=31578; range=1 - 68460 |
| `raceId` | `INTEGER` | NOT NULL, FK -> races.raceId | 比赛 ID。 外键，指向 `races.raceId`。 | 816, 824, 815 | 0 | distinct=970; range=1 - 982 |
| `driverId` | `INTEGER` | NOT NULL, FK -> drivers.driverId | 车手 ID。 外键，指向 `drivers.driverId`。 | 30, 18, 22 | 0 | distinct=833; range=1 - 841 |
| `points` | `REAL` | NOT NULL | 积分。 | 0.0, 1.0, 2.0 | 0 | distinct=337; range=0.0 - 397.0 |
| `position` | `INTEGER` |  | 职务/职位。 | 1, 2, 3 | 0 | distinct=108; range=1 - 108 |
| `positionText` | `TEXT` |  | 名次文本。 通常不是核心查询字段。 | 1, 2, 3 | 0 | distinct=109 |
| `wins` | `INTEGER` | NOT NULL | 获胜次数。 | 0, 1, 2 | 0 | distinct=14; range=0 - 13 |

### 3.6 `drivers`

车手维表。 行数：`840`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `driverId` | `INTEGER` | PK | 车手 ID。 | 1, 2, 3 | 0 | distinct=840; range=1 - 841 |
| `driverRef` | `TEXT` | NOT NULL | 车手引用名。 | Cannoc, Changy, abate | 0 | distinct=840 |
| `number` | `INTEGER` |  | 编号。 | 2, 3, 4 | 804 | distinct=36; range=2 - 99 |
| `code` | `TEXT` |  | 代码。 | BIA, MAG, VER | 757 | distinct=80 |
| `forename` | `TEXT` | NOT NULL | 名。 | John, Mike, Peter | 0 | distinct=465 |
| `surname` | `TEXT` | NOT NULL | 姓。 | Taylor, Wilson, Brabham | 0 | distinct=784 |
| `dob` | `DATE` |  | 出生日期。 | 1915-10-26, 1918-10-06, 1919-09-30 | 1 | distinct=821 |
| `nationality` | `TEXT` |  | 国籍。 | British, American, Italian | 0 | distinct=41 |
| `url` | `TEXT` | NOT NULL | URL 链接。 | , http://en.wikipedia.org/wiki/%C3%89lie_Bayol, http://en.wikipedia.org/wiki/%C3%89ric_Bernard | 0 | distinct=840 |

### 3.7 `lapTimes`

逐圈成绩表。 行数：`420369`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `raceId` | `INTEGER` | PK, NOT NULL, FK -> races.raceId | 比赛 ID。 外键，指向 `races.raceId`。 | 354, 870, 846 | 0 | range=1 - 982 |
| `driverId` | `INTEGER` | PK, NOT NULL, FK -> drivers.driverId | 车手 ID。 外键，指向 `drivers.driverId`。 | 18, 4, 13 | 0 | range=1 - 841 |
| `lap` | `INTEGER` | PK, NOT NULL | 圈数。 | 1, 2, 3 | 0 | range=1 - 78 |
| `position` | `INTEGER` |  | 职务/职位。 | 1, 2, 3 | 0 | range=1 - 24 |
| `time` | `TEXT` |  | 时间。 过滤前注意实际时间格式。 | 1:23.794, 1:19.613, 1:20.329 | 0 |  |
| `milliseconds` | `INTEGER` |  | 毫秒时间。 | 83794, 79613, 80329 | 0 | range=67411 - 7507547 |

### 3.8 `pitStops`

事实/明细表，通常需要 join 维表解释 ID。 行数：`6070`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `raceId` | `INTEGER` | PK, NOT NULL, FK -> races.raceId | 比赛 ID。 外键，指向 `races.raceId`。 | 936, 851, 844 | 0 | distinct=131; range=841 - 982 |
| `driverId` | `INTEGER` | PK, NOT NULL, FK -> drivers.driverId | 车手 ID。 外键，指向 `drivers.driverId`。 | 13, 1, 20 | 0 | distinct=54; range=1 - 841 |
| `stop` | `INTEGER` | PK, NOT NULL | 进站次数。 | 1, 2, 3 | 0 | distinct=6; range=1 - 6 |
| `lap` | `INTEGER` | NOT NULL | 圈数。 | 13, 11, 12 | 0 | distinct=73; range=1 - 74 |
| `time` | `TEXT` | NOT NULL | 时间。 过滤前注意实际时间格式。 | 14:56:46, 14:18:36, 14:19:03 | 0 | distinct=4872 |
| `duration` | `TEXT` |  | 持续时间。 | 22.303, 22.838, 21.012 | 0 | distinct=4713 |
| `milliseconds` | `INTEGER` |  | 毫秒时间。 | 22303, 22838, 21012 | 0 | distinct=4713; range=12897 - 2011266 |

### 3.9 `qualifying`

排位赛成绩表。 行数：`7397`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `qualifyId` | `INTEGER` | PK | 排位赛记录 ID。 | 1, 2, 3 | 0 | distinct=7397; range=1 - 7419 |
| `raceId` | `INTEGER` | NOT NULL, FK -> races.raceId | 比赛 ID。 外键，指向 `races.raceId`。 | 259, 240, 241 | 0 | distinct=339; range=1 - 982 |
| `driverId` | `INTEGER` | NOT NULL, FK -> drivers.driverId | 车手 ID。 外键，指向 `drivers.driverId`。 | 4, 18, 13 | 0 | distinct=151; range=1 - 841 |
| `constructorId` | `INTEGER` | NOT NULL, FK -> constructors.constructorId | 车队 ID。 外键，指向 `constructors.constructorId`。 | 6, 3, 1 | 0 | distinct=41; range=1 - 210 |
| `number` | `INTEGER` | NOT NULL | 编号。 | 8, 3, 7 | 0 | distinct=48; range=0 - 99 |
| `position` | `INTEGER` |  | 职务/职位。 | 1, 2, 3 | 0 | distinct=28; range=1 - 28 |
| `q1` | `TEXT` |  | 排位赛 Q1 时间。 | 1:20.888, 1:12.409, 1:14.412 | 117 | distinct=6635 |
| `q2` | `TEXT` |  | 排位赛 Q2 时间。 | , 1:15.150, 1:15.974 | 3807 | distinct=3403 |
| `q3` | `TEXT` |  | 排位赛 Q3 时间。 | , 1:35.766, 1:38.513 | 5251 | distinct=2066 |

### 3.10 `races`

赛事主表。 行数：`976`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `raceId` | `INTEGER` | PK | 比赛 ID。 | 1, 2, 3 | 0 | distinct=976; range=1 - 988 |
| `year` | `INTEGER` | NOT NULL, FK -> seasons.year | 年份。外键，指向 `seasons.year`。 | 2016, 2012, 2017 | 0 | distinct=68; range=1950 - 2017 |
| `round` | `INTEGER` | NOT NULL | 比赛轮次。 | 1, 2, 3 | 0 | distinct=21; range=1 - 21 |
| `circuitId` | `INTEGER` | NOT NULL, FK -> circuits.circuitId | 赛道 ID。 外键，指向 `circuits.circuitId`。 | 14, 6, 9 | 0 | distinct=72; range=1 - 73 |
| `name` | `TEXT` | NOT NULL | 名称。 | British Grand Prix, Italian Grand Prix, Monaco Grand Prix | 0 | distinct=42 |
| `date` | `DATE` | NOT NULL | 日期。 过滤前注意实际日期格式。 | 1950-05-13, 1950-05-21, 1950-05-30 | 0 | distinct=976 |
| `time` | `TEXT` |  | 时间。 过滤前注意实际时间格式。 | 12:00:00, 14:00:00, 06:00:00 | 731 | distinct=20 |
| `url` | `TEXT` |  | URL 链接。 | http://en.wikipedia.org/wiki/1950_Belgian_Grand_Prix, http://en.wikipedia.org/wiki/1950_British_Grand_Prix, http://en.wikipedia.org/wiki/1950_French_Grand_Prix | 0 | distinct=976 |

### 3.11 `results`

比赛结果事实表。 行数：`23657`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `resultId` | `INTEGER` | PK | 比赛结果 ID。 | 1, 2, 3 | 0 | distinct=23657; range=1 - 23661 |
| `raceId` | `INTEGER` | NOT NULL, FK -> races.raceId | 比赛 ID。 外键，指向 `races.raceId`。 | 800, 809, 357 | 0 | distinct=970; range=1 - 982 |
| `driverId` | `INTEGER` | NOT NULL, FK -> drivers.driverId | 车手 ID。 外键，指向 `drivers.driverId`。 | 22, 18, 30 | 0 | distinct=840; range=1 - 841 |
| `constructorId` | `INTEGER` | NOT NULL, FK -> constructors.constructorId | 车队 ID。 外键，指向 `constructors.constructorId`。 | 6, 1, 3 | 0 | distinct=207; range=1 - 210 |
| `number` | `INTEGER` |  | 编号。 | 6, 8, 12 | 6 | distinct=128; range=0 - 208 |
| `grid` | `INTEGER` | NOT NULL | 发车位。 | 0, 7, 1 | 0 | distinct=35; range=0 - 34 |
| `position` | `INTEGER` |  | 职务/职位。 | 3, 4, 2 | 10528 | distinct=33; range=1 - 33 |
| `positionText` | `TEXT` | NOT NULL | 名次文本。 通常不是核心查询字段。 | R, F, 3 | 0 | distinct=39 |
| `positionOrder` | `INTEGER` | NOT NULL | 完赛顺序。 | 3, 4, 2 | 0 | distinct=39; range=1 - 39 |
| `points` | `REAL` | NOT NULL | 积分。 | 0.0, 2.0, 4.0 | 0 | distinct=33; range=0.0 - 50.0 |
| `laps` | `INTEGER` | NOT NULL | 圈数。 | 0, 70, 53 | 0 | distinct=172; range=0 - 200 |
| `time` | `TEXT` |  | 完赛时间文本；冠军与非冠军的格式/含义不同，严谨比较优先使用 `milliseconds`。 | +8:22.19, +0.7, +1:29.6 | 17696 | distinct=5755 |
| `milliseconds` | `INTEGER` |  | 毫秒时间。 | 14259460, 10928200, 4584572 | 17697 | distinct=5923; range=1474899 - 15090540 |
| `fastestLap` | `INTEGER` |  | 最快圈圈数。 | 52, 50, 53 | 18389 | distinct=77; range=2 - 78 |
| `rank` | `INTEGER` |  | 排名。 | 1, 2, 3 | 18246 | distinct=25; range=0 - 24 |
| `fastestLapTime` | `TEXT` |  | 最快圈时间。 过滤前注意实际时间格式。 | 1:14.117, 1:16.802, 1:18.262 | 18389 | distinct=4955 |
| `fastestLapSpeed` | `TEXT` |  | 最快圈速度；该字段为 TEXT，按数值排序时需要 `CAST(... AS REAL)`。 | 189.423, 195.933, 196.785 | 18389 | distinct=5045 |
| `statusId` | `INTEGER` | NOT NULL, FK -> status.statusId | 状态 ID。 外键，指向 `status.statusId`。 | 1, 11, 5 | 0 | distinct=132; range=1 - 136 |

### 3.12 `seasons`

关系/映射表。 行数：`68`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `year` | `INTEGER` | PK, NOT NULL | 年份。 | 1950, 1951, 1952 | 0 | distinct=68; range=1950 - 2017 |
| `url` | `TEXT` | NOT NULL | URL 链接。 | http://en.wikipedia.org/wiki/1950_Formula_One_season, http://en.wikipedia.org/wiki/1951_Formula_One_season, http://en.wikipedia.org/wiki/1952_Formula_One_season | 0 | distinct=68 |

### 3.13 `status`

关系/映射表。 行数：`134`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `statusId` | `INTEGER` | PK | 状态 ID。 | 1, 2, 3 | 0 | distinct=134; range=1 - 136 |
| `status` | `TEXT` | NOT NULL | 合法性状态。 | +1 Lap, +10 Laps, +11 Laps | 0 | distinct=134 |

## 4. 常用查询模板

### 4.1 `constructorResults` join `constructors`

```sql
SELECT *
FROM "constructorResults" AS t1
JOIN "constructors" AS t2
  ON t1."constructorId" = t2."constructorId";
```

### 4.2 `constructorResults` join `races`

```sql
SELECT *
FROM "constructorResults" AS t1
JOIN "races" AS t2
  ON t1."raceId" = t2."raceId";
```

### 4.3 `constructorStandings` join `constructors`

```sql
SELECT *
FROM "constructorStandings" AS t1
JOIN "constructors" AS t2
  ON t1."constructorId" = t2."constructorId";
```

### 4.4 `constructorStandings` join `races`

```sql
SELECT *
FROM "constructorStandings" AS t1
JOIN "races" AS t2
  ON t1."raceId" = t2."raceId";
```

### 4.5 `driverStandings` join `drivers`

```sql
SELECT *
FROM "driverStandings" AS t1
JOIN "drivers" AS t2
  ON t1."driverId" = t2."driverId";
```

### 4.6 `driverStandings` join `races`

```sql
SELECT *
FROM "driverStandings" AS t1
JOIN "races" AS t2
  ON t1."raceId" = t2."raceId";
```

### 4.7 `lapTimes` join `drivers`

```sql
SELECT *
FROM "lapTimes" AS t1
JOIN "drivers" AS t2
  ON t1."driverId" = t2."driverId";
```

### 4.8 `lapTimes` join `races`

```sql
SELECT *
FROM "lapTimes" AS t1
JOIN "races" AS t2
  ON t1."raceId" = t2."raceId";
```

## 5. Text-to-SQL 易错点

- 日期/时间相关字段：`drivers.dob`, `lapTimes.time`, `pitStops.time`, `races.date`, `races.time`, `results.time`, `results.fastestLapTime`。过滤前先查看实际字符串格式。
- 本次评测错题暴露出的典型坑：
  - qid854（输出形状/答案格式错误）：多输出 circuit/race name，且缺 `DISTINCT`，导致同一坐标重复 11 次。
  - qid861（类型/日期/NULL/值规范错误）：查到了匹配 Q3 时间，但没有 join `drivers` 返回 `driver.number`，而是返回 q3 时间本身。
  - qid866（类型/日期/NULL/值规范错误）：时间格式误读：数据库用 `1:27%`，pred 用 `0:01:27%`，结果为空。
  - qid872（类型/日期/NULL/值规范错误）：没按 `q3 LIKE '1:33%'` 过滤并 join drivers，返回了整场 q3 列表。
  - qid877（输出形状/答案格式错误）：年龄排序方向反了，`dob ASC` 选到最老；还多输出 dob。
  - qid879（类型/日期/NULL/值规范错误）：`fastestLapSpeed` 是 TEXT，pred 按字符串排序，未 `CAST(... AS REAL)`。
  - qid881（SQL 可执行性错误）：未 join `status` 表，却引用 `res.status`，SQL 执行失败。
  - qid884（SQL 可执行性错误）：最后一轮用了 SQLite 不存在的 `month()` 函数，并多输出 date/year/month；上一轮正确思路被覆盖。
  - qid897（Schema/字段/Join 选择错误）：用 `results.points` 求和当作最大积分；gold 要 `driverStandings` 中 `MAX(points)`。
  - qid898（输出形状/答案格式错误）：年龄计算硬编码 2024，且输出列顺序/形状错；gold 用当前时间。
  - qid902（输出形状/答案格式错误）：筛选语义对，但多输出 position 和 raceId；gold 只要 race name。
  - qid906（输出形状/答案格式错误）：筛选语义对，但多输出 race date；gold 只要 race name 和 points。
  - qid909（输出形状/答案格式错误）：百分比算对但多输出分子/分母，并 `ROUND` 到两位导致精度不一致。
  - qid915（类型/日期/NULL/值规范错误）：未过滤 `dob IS NOT NULL`，NULL 被排在最前。
  - qid930（SQL 可执行性错误）：SQL alias 写错，引用未定义的 `r.name/r.year`；修后仍会多输出 year。
  - qid937（输出形状/答案格式错误）：找到第二名完赛时间，但多输出 driver forename/surname。
  - qid944（协议/轮数/收敛失败）：复杂时间差题 10 轮内没有产出 SQL，最终 empty SQL。
  - qid948（Schema/字段/Join 选择错误）：用错表：pred 查 `constructorResults.points`，gold 查 `constructorStandings.points`。
  - 另有 14 条错题根因，详见 `wrong_root_cause_summary_238.md`。
