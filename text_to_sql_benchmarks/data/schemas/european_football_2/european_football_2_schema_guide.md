# european_football_2 Schema Guide

本文件整理 `european_football_2` SQLite 数据库的表结构、字段含义、示例值和 Text-to-SQL 常见 join/过滤注意点。

- 数据库文件：`/root/autodl-tmp/DeepEye-SQL/data/arcwise_plat/dev/dev_databases/european_football_2/european_football_2.sqlite`
- 字段说明来源：`/root/autodl-tmp/text_to_sql_benchmarks/data/schemas/european_football_2/database_description`
- 生成时间：`2026-06-21 22:56:18`
- 生成方式：基于 SQLite schema、database_description CSV、字段样例值以及本次错题根因汇总自动生成。

## 1. 数据库概览

| 表 | 行数 | 字段数 | 作用 |
|---|---:|---:|---|
| `Country` | 11 | 2 | 关系/映射表。 |
| `League` | 11 | 3 | 关系/映射表。 |
| `Match` | 25979 | 115 | 比赛事实表，含赛季、日期、主客队、进球和球员阵容。 |
| `Player` | 11060 | 7 | 球员主表。 |
| `Player_Attributes` | 183978 | 42 | 球员能力属性历史表。 |
| `Team` | 299 | 5 | 球队主表。 |
| `Team_Attributes` | 1458 | 25 | 球队战术属性历史表。 |

## 2. 表关系与 Join 注意点

### 2.1 SQLite 声明的外键

| From | To | 说明 |
|---|---|---|
| `League.country_id` | `country.id` | 声明外键 |
| `Match.away_player_11` | `Player.player_api_id` | 声明外键 |
| `Match.away_player_10` | `Player.player_api_id` | 声明外键 |
| `Match.away_player_9` | `Player.player_api_id` | 声明外键 |
| `Match.away_player_8` | `Player.player_api_id` | 声明外键 |
| `Match.away_player_7` | `Player.player_api_id` | 声明外键 |
| `Match.away_player_6` | `Player.player_api_id` | 声明外键 |
| `Match.away_player_5` | `Player.player_api_id` | 声明外键 |
| `Match.away_player_4` | `Player.player_api_id` | 声明外键 |
| `Match.away_player_3` | `Player.player_api_id` | 声明外键 |
| `Match.away_player_2` | `Player.player_api_id` | 声明外键 |
| `Match.away_player_1` | `Player.player_api_id` | 声明外键 |
| `Match.home_player_11` | `Player.player_api_id` | 声明外键 |
| `Match.home_player_10` | `Player.player_api_id` | 声明外键 |
| `Match.home_player_9` | `Player.player_api_id` | 声明外键 |
| `Match.home_player_8` | `Player.player_api_id` | 声明外键 |
| `Match.home_player_7` | `Player.player_api_id` | 声明外键 |
| `Match.home_player_6` | `Player.player_api_id` | 声明外键 |
| `Match.home_player_5` | `Player.player_api_id` | 声明外键 |
| `Match.home_player_4` | `Player.player_api_id` | 声明外键 |
| `Match.home_player_3` | `Player.player_api_id` | 声明外键 |
| `Match.home_player_2` | `Player.player_api_id` | 声明外键 |
| `Match.home_player_1` | `Player.player_api_id` | 声明外键 |
| `Match.away_team_api_id` | `Team.team_api_id` | 声明外键 |
| `Match.home_team_api_id` | `Team.team_api_id` | 声明外键 |
| `Match.league_id` | `League.id` | 声明外键 |
| `Match.country_id` | `Country.id` | 声明外键 |
| `Player_Attributes.player_api_id` | `Player.player_api_id` | 声明外键 |
| `Player_Attributes.player_fifa_api_id` | `Player.player_fifa_api_id` | 声明外键 |
| `Team_Attributes.team_api_id` | `Team.team_api_id` | 声明外键 |
| `Team_Attributes.team_fifa_api_id` | `Team.team_fifa_api_id` | 声明外键 |

### 2.2 按字段名推断的常用连接

| From | To | 推断依据 |
|---|---|---|
| `League.country_id` | `Country.id` | 字段名指向目标表 |

### 2.3 通用注意点

- 字段名含空格、连字符、括号或大小写敏感时，建议使用双引号，例如 `"Some Column"`。
- 表中 ID 字段通常只是连接键；最终输出是否需要 ID，要以 question/gold 语义为准，避免多输出中间列。
- 做 top/max/min/rank 查询时，先确认是否需要返回所有并列值，而不是默认 `LIMIT 1`。
- `Player_Attributes.date`、`Team_Attributes.date` 含时间，日期边界要用 `SUBSTR(date,1,10)` 或 `LIKE`。
- latest record 需要按 player/team 分组后取 date 最大的一条。
- “highest/most” 类题常需要保留所有并列第一。

## 3. 字段明细

### 3.1 `Country`

关系/映射表。 行数：`11`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `id` | `INTEGER` | PK | 国家的唯一标识符。 | 1, 1729, 4769 | 0 | distinct=11; range=1 - 24558 |
| `name` | `TEXT` |  | 名称。 | Belgium, England, France | 0 | distinct=11 |

### 3.2 `League`

关系/映射表。 行数：`11`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `id` | `INTEGER` | PK | 联赛的唯一标识符。 | 1, 1729, 4769 | 0 | distinct=11; range=1 - 24558 |
| `country_id` | `INTEGER` | FK -> country.id | 国家 ID。 外键，指向 `country.id`。 | 1, 1729, 4769 | 0 | distinct=11; range=1 - 24558 |
| `name` | `TEXT` |  | 名称。 | Belgium Jupiler League, England Premier League, France Ligue 1 | 0 | distinct=11 |

### 3.3 `Match`

比赛事实表，含赛季、日期、主客队、进球和球员阵容。 行数：`25979`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `id` | `INTEGER` | PK | 比赛的唯一标识符。 | 1, 2, 3 | 0 | distinct=25979; range=1 - 25979 |
| `country_id` | `INTEGER` | FK -> Country.id | 国家 ID。 外键，指向 `Country.id`。 | 1729, 4769, 21518 | 0 | distinct=11; range=1 - 24558 |
| `league_id` | `INTEGER` | FK -> League.id | 联赛 ID。 外键，指向 `League.id`。 | 1729, 4769, 21518 | 0 | distinct=11; range=1 - 24558 |
| `season` | `TEXT` |  | 赛季。 | 2008/2009, 2015/2016, 2014/2015 | 0 | distinct=8 |
| `stage` | `INTEGER` |  | 轮次/阶段。 | 1, 2, 3 | 0 | distinct=38; range=1 - 38 |
| `date` | `TEXT` |  | 日期。 过滤前注意实际日期格式。 | 2009-04-11 00:00:00, 2015-04-04 00:00:00, 2009-05-16 00:00:00 | 0 | distinct=1694 |
| `match_api_id` | `INTEGER` |  | 比赛 API ID。 | 483129, 483130, 483131 | 0 | distinct=25979; range=483129 - 2216672 |
| `home_team_api_id` | `INTEGER` | FK -> Team.team_api_id | 主队 API ID。 外键，指向 `Team.team_api_id`。 | 8302, 8305, 8315 | 0 | distinct=299; range=1601 - 274581 |
| `away_team_api_id` | `INTEGER` | FK -> Team.team_api_id | 客队 API ID。 外键，指向 `Team.team_api_id`。 | 9927, 8302, 8305 | 0 | distinct=299; range=1601 - 274581 |
| `home_team_goal` | `INTEGER` |  | 主队进球数。 | 1, 2, 0 | 0 | distinct=11; range=0 - 10 |
| `away_team_goal` | `INTEGER` |  | 客队进球数。 | 1, 0, 2 | 0 | distinct=10; range=0 - 9 |
| `home_player_X1` | `INTEGER` |  | 主场球员X1。 | 1, 0, 2 | 1821 | distinct=3; range=0 - 2 |
| `home_player_X2` | `INTEGER` |  | 主场球员X2。 | 2, 3, 1 | 1821 | distinct=9; range=0 - 8 |
| `home_player_X3` | `INTEGER` |  | 主场球员X3。 | 4, 5, 6 | 1832 | distinct=8; range=1 - 8 |
| `home_player_X4` | `INTEGER` |  | 主场球员X4。 | 6, 7, 8 | 1832 | distinct=7; range=2 - 8 |
| `home_player_X5` | `INTEGER` |  | 主场球员X5。 | 8, 1, 2 | 1832 | distinct=9; range=1 - 9 |
| `home_player_X6` | `INTEGER` |  | 主场球员X6。 | 4, 2, 3 | 1832 | distinct=9; range=1 - 9 |
| `home_player_X7` | `INTEGER` |  | 主场球员X7。 | 4, 6, 5 | 1832 | distinct=9; range=1 - 9 |
| `home_player_X8` | `INTEGER` |  | 主场球员X8。 | 6, 3, 7 | 1832 | distinct=9; range=1 - 9 |
| `home_player_X9` | `INTEGER` |  | 主场球员X9。 | 8, 5, 3 | 1832 | distinct=9; range=1 - 9 |
| `home_player_X10` | `INTEGER` |  | 主场球员X10。 | 4, 7, 5 | 1832 | distinct=9; range=1 - 9 |
| `home_player_X11` | `INTEGER` |  | 主场球员X11。 | 6, 5, 7 | 1832 | distinct=6; range=1 - 7 |
| `away_player_X1` | `INTEGER` |  | 客场球员X1。 | 1, 2, 6 | 1832 | distinct=3; range=1 - 6 |
| `away_player_X2` | `INTEGER` |  | 客场球员X2。 | 2, 3, 1 | 1832 | distinct=8; range=1 - 8 |
| `away_player_X3` | `INTEGER` |  | 客场球员X3。 | 4, 5, 3 | 1832 | distinct=8; range=2 - 9 |
| `away_player_X4` | `INTEGER` |  | 客场球员X4。 | 6, 7, 5 | 1832 | distinct=8; range=1 - 8 |
| `away_player_X5` | `INTEGER` |  | 客场球员X5。 | 8, 1, 2 | 1832 | distinct=9; range=1 - 9 |
| `away_player_X6` | `INTEGER` |  | 客场球员X6。 | 4, 2, 3 | 1832 | distinct=9; range=1 - 9 |
| `away_player_X7` | `INTEGER` |  | 客场球员X7。 | 4, 6, 5 | 1832 | distinct=9; range=1 - 9 |
| `away_player_X8` | `INTEGER` |  | 客场球员X8。 | 6, 3, 7 | 1832 | distinct=9; range=1 - 9 |
| `away_player_X9` | `INTEGER` |  | 客场球员X9。 | 5, 8, 3 | 1833 | distinct=9; range=1 - 9 |
| `away_player_X10` | `INTEGER` |  | 客场球员X10。 | 4, 7, 5 | 1833 | distinct=9; range=1 - 9 |
| `away_player_X11` | `INTEGER` |  | 客场球员X11。 | 5, 6, 7 | 1839 | distinct=6; range=3 - 8 |
| `home_player_Y1` | `INTEGER` |  | 主场球员Y1。 | 1, 0, 3 | 1821 | distinct=3; range=0 - 3 |
| `home_player_Y2` | `INTEGER` |  | 主场球员Y2。 | 3, 0 | 1821 | distinct=2; range=0 - 3 |
| `home_player_Y3` | `INTEGER` |  | 主场球员Y3。 | 3, 5 | 1832 | distinct=2; range=3 - 5 |
| `home_player_Y4` | `INTEGER` |  | 主场球员Y4。 | 3, 5 | 1832 | distinct=2; range=3 - 5 |
| `home_player_Y5` | `INTEGER` |  | 主场球员Y5。 | 3, 7, 5 | 1832 | distinct=5; range=3 - 8 |
| `home_player_Y6` | `INTEGER` |  | 主场球员Y6。 | 7, 6, 5 | 1832 | distinct=6; range=3 - 9 |
| `home_player_Y7` | `INTEGER` |  | 主场球员Y7。 | 7, 6, 5 | 1832 | distinct=6; range=3 - 9 |
| `home_player_Y8` | `INTEGER` |  | 主场球员Y8。 | 7, 8, 6 | 1832 | distinct=7; range=3 - 10 |
| `home_player_Y9` | `INTEGER` |  | 主场球员Y9。 | 7, 8, 10 | 1832 | distinct=6; range=1 - 10 |
| `home_player_Y10` | `INTEGER` |  | 主场球员Y10。 | 10, 8, 9 | 1832 | distinct=7; range=3 - 11 |
| `home_player_Y11` | `INTEGER` |  | 主场球员Y11。 | 10, 11, 1 | 1832 | distinct=4; range=1 - 11 |
| `away_player_Y1` | `INTEGER` |  | 客场球员Y1。 | 1, 3 | 1832 | distinct=2; range=1 - 3 |
| `away_player_Y2` | `INTEGER` |  | 客场球员Y2。 | 3 | 1832 | distinct=1; range=3 - 3 |
| `away_player_Y3` | `INTEGER` |  | 客场球员Y3。 | 3, 7 | 1832 | distinct=2; range=3 - 7 |
| `away_player_Y4` | `INTEGER` |  | 客场球员Y4。 | 3, 5, 7 | 1832 | distinct=3; range=3 - 7 |
| `away_player_Y5` | `INTEGER` |  | 客场球员Y5。 | 3, 7, 5 | 1832 | distinct=5; range=3 - 9 |
| `away_player_Y6` | `INTEGER` |  | 客场球员Y6。 | 7, 6, 5 | 1832 | distinct=7; range=3 - 10 |
| `away_player_Y7` | `INTEGER` |  | 客场球员Y7。 | 7, 6, 8 | 1832 | distinct=7; range=3 - 10 |
| `away_player_Y8` | `INTEGER` |  | 客场球员Y8。 | 7, 8, 6 | 1832 | distinct=7; range=3 - 10 |
| `away_player_Y9` | `INTEGER` |  | 客场球员Y9。 | 7, 8, 10 | 1833 | distinct=7; range=5 - 11 |
| `away_player_Y10` | `INTEGER` |  | 客场球员Y10。 | 10, 8, 7 | 1833 | distinct=6; range=6 - 11 |
| `away_player_Y11` | `INTEGER` |  | 客场球员Y11。 | 10, 11, 7 | 1839 | distinct=4; range=7 - 11 |
| `home_player_1` | `INTEGER` | FK -> Player.player_api_id | 主场球员1。外键，指向 `Player.player_api_id`。 | 31293, 41097, 26295 | 1224 | distinct=906; range=2984 - 698273 |
| `home_player_2` | `INTEGER` | FK -> Player.player_api_id | 主场球员2。外键，指向 `Player.player_api_id`。 | 33025, 33988, 26111 | 1315 | distinct=2414; range=2802 - 748432 |
| `home_player_3` | `INTEGER` | FK -> Player.player_api_id | 主场球员3。外键，指向 `Player.player_api_id`。 | 35606, 32769, 38458 | 1281 | distinct=2375; range=2752 - 705484 |
| `home_player_4` | `INTEGER` | FK -> Player.player_api_id | 主场球员4。外键，指向 `Player.player_api_id`。 | 30627, 56678, 41884 | 1323 | distinct=2606; range=2752 - 723037 |
| `home_player_5` | `INTEGER` | FK -> Player.player_api_id | 主场球员5。外键，指向 `Player.player_api_id`。 | 24846, 32569, 35502 | 1316 | distinct=2769; range=2752 - 733787 |
| `home_player_6` | `INTEGER` | FK -> Player.player_api_id | 主场球员6。外键，指向 `Player.player_api_id`。 | 39854, 31037, 30966 | 1325 | distinct=3798; range=2625 - 750584 |
| `home_player_7` | `INTEGER` | FK -> Player.player_api_id | 主场球员7。外键，指向 `Player.player_api_id`。 | 154257, 30682, 24405 | 1227 | distinct=3422; range=2625 - 692984 |
| `home_player_8` | `INTEGER` | FK -> Player.player_api_id | 主场球员8。外键，指向 `Player.player_api_id`。 | 30955, 75192, 33991 | 1309 | distinct=4076; range=2625 - 693171 |
| `home_player_9` | `INTEGER` | FK -> Player.player_api_id | 主场球员9。外键，指向 `Player.player_api_id`。 | 36378, 38398, 31235 | 1273 | distinct=4114; range=2625 - 730065 |
| `home_player_10` | `INTEGER` | FK -> Player.player_api_id | 主场球员10。外键，指向 `Player.player_api_id`。 | 107417, 24383, 35724 | 1436 | distinct=3642; range=2625 - 742405 |
| `home_player_11` | `INTEGER` | FK -> Player.player_api_id | 主场球员11。外键，指向 `Player.player_api_id`。 | 27734, 33028, 93447 | 1555 | distinct=2890; range=2802 - 726956 |
| `away_player_1` | `INTEGER` | FK -> Player.player_api_id | 客场球员1。外键，指向 `Player.player_api_id`。 | 31293, 33764, 41097 | 1234 | distinct=926; range=2796 - 698273 |
| `away_player_2` | `INTEGER` | FK -> Player.player_api_id | 客场球员2。外键，指向 `Player.player_api_id`。 | 33988, 26111, 33025 | 1278 | distinct=2504; range=2790 - 748432 |
| `away_player_3` | `INTEGER` | FK -> Player.player_api_id | 客场球员3。外键，指向 `Player.player_api_id`。 | 35606, 38458, 32769 | 1293 | distinct=2470; range=2752 - 705484 |
| `away_player_4` | `INTEGER` | FK -> Player.player_api_id | 客场球员4。外键，指向 `Player.player_api_id`。 | 30627, 41884, 36388 | 1321 | distinct=2657; range=2752 - 728414 |
| `away_player_5` | `INTEGER` | FK -> Player.player_api_id | 客场球员5。外键，指向 `Player.player_api_id`。 | 24846, 33848, 41167 | 1335 | distinct=2884; range=2790 - 746419 |
| `away_player_6` | `INTEGER` | FK -> Player.player_api_id | 客场球员6。外键，指向 `Player.player_api_id`。 | 39854, 31037, 32575 | 1313 | distinct=3930; range=2625 - 722766 |
| `away_player_7` | `INTEGER` | FK -> Player.player_api_id | 客场球员7。外键，指向 `Player.player_api_id`。 | 154257, 30731, 23782 | 1235 | distinct=3620; range=2625 - 750435 |
| `away_player_8` | `INTEGER` | FK -> Player.player_api_id | 客场球员8。外键，指向 `Player.player_api_id`。 | 75192, 30955, 33991 | 1341 | distinct=4249; range=2625 - 717248 |
| `away_player_9` | `INTEGER` | FK -> Player.player_api_id | 客场球员9。外键，指向 `Player.player_api_id`。 | 36378, 37441, 38398 | 1328 | distinct=4319; range=2625 - 722766 |
| `away_player_10` | `INTEGER` | FK -> Player.player_api_id | 客场球员10。外键，指向 `Player.player_api_id`。 | 35724, 107417, 30981 | 1441 | distinct=3891; range=2770 - 722766 |
| `away_player_11` | `INTEGER` | FK -> Player.player_api_id | 客场球员11。外键，指向 `Player.player_api_id`。 | 33028, 38098, 26344 | 1554 | distinct=3040; range=2802 - 726956 |
| `goal` | `TEXT` |  | 进球。 | <goal />, <goal><br> <value><br> <comment>n</comment><br> <stats><br> <goals>1</goals><br> <shoton>1</shoton><br> </stats><br> <event_incident_typefk>6</event_incident_typefk><br> <elapse..., <goal><value><comment>dg</comment><elapsed_plus>1</elapsed_plus><event_incident_typefk>289</event_incident_typefk><coordinates><value>26</value><value>4</value></coordinates><el... | 11762 | distinct=13225 |
| `shoton` | `TEXT` |  | 射正事件数据。 | <shoton />, <shoton><br> <value><br> <stats><br> <shoton>1</shoton><br> </stats><br> <event_incident_typefk>147</event_incident_typefk><br> <elapsed>6</elapsed><br> <subtype>shot</subtype><..., <shoton><value><elapsed_plus>2</elapsed_plus><event_incident_typefk>139</event_incident_typefk><coordinates><value>18</value><value>56</value></coordinates><elapsed>45</elapsed>... | 11762 | distinct=8464 |
| `shotoff` | `TEXT` |  | 射偏事件数据。 | <shotoff />, <shotoff><br> <value><br> <stats><br> <shotoff>1</shotoff><br> </stats><br> <event_incident_typefk>28</event_incident_typefk><br> <elapsed>19</elapsed><br> <subtype>post</subtyp..., <shotoff><value><event_incident_typefk>589</event_incident_typefk><elapsed>3</elapsed><subtype>big chance post</subtype><player1>10491</player1><sortorder>1</sortorder><team>866... | 11762 | distinct=8464 |
| `foulcommit` | `TEXT` |  | 犯规事件数据。 | <foulcommit />, <foulcommit><br> <value><br> <stats><br> <foulscommitted>1</foulscommitted><br> </stats><br> <event_incident_typefk>3</event_incident_typefk><br> <elapsed>3</elapsed><br> <subty..., <foulcommit><value><event_incident_typefk>162</event_incident_typefk><coordinates><value>30</value><value>63</value></coordinates><elapsed>1</elapsed><subtype>diving</subtype><p... | 11762 | distinct=8466 |
| `card` | `TEXT` |  | 红黄牌事件数据。 | <card />, <card><br> <value><br> <comment>y</comment><br> <stats><br> <ycards>1</ycards><br> </stats><br> <event_incident_typefk>70</event_incident_typefk><br> <elapsed>25</elapsed><br> <..., <card><value><comment>r</comment><event_incident_typefk>270</event_incident_typefk><elapsed>13</elapsed><del>1</del><sortorder>0</sortorder><n>14</n><type>card</type><id>2101901... | 11762 | distinct=13777 |
| `cross` | `TEXT` |  | 传中事件数据。 | <cross />, <cross><br> <value><br> <stats><br> <crosses>1</crosses><br> </stats><br> <event_incident_typefk>774</event_incident_typefk><br> <elapsed>3</elapsed><br> <subtype>cross</subtype..., <cross><value><event_incident_typefk>123</event_incident_typefk><elapsed>10</elapsed><subtype>cross</subtype><sortorder>0</sortorder><team>8558</team><n>35</n><type>throwin</typ... | 11762 | distinct=8466 |
| `corner` | `TEXT` |  | 角球事件数据。 | <corner />, <corner><br> <value><br> <stats><br> <corners>1</corners><br> </stats><br> <event_incident_typefk>329</event_incident_typefk><br> <elapsed>6</elapsed><br> <subtype>cross</subtyp..., <corner><value><stats><corners>1</corners></stats><elapsed_plus>1</elapsed_plus><event_incident_typefk>329</event_incident_typefk><elapsed>45</elapsed><subtype>cross</subtype><p... | 11762 | distinct=8465 |
| `possession` | `TEXT` |  | 控球率事件数据。 | <possession />, <possession><br> <value><br> <comment>58</comment><br> <event_incident_typefk>352</event_incident_typefk><br> <elapsed>21</elapsed><br> <subtype>possession</subtype><br> <sortor..., <possession><value><comment>11</comment><event_incident_typefk>352</event_incident_typefk><elapsed>6</elapsed><subtype>possession</subtype><sortorder>0</sortorder><awaypos>89</a... | 11762 | distinct=8420 |
| `B365H` | `REAL` |  | Bet365 的主胜赔率。 | 2.1, 2.0, 2.5 | 3387 | distinct=121; range=1.04 - 26.0 |
| `B365D` | `REAL` |  | Bet365 的平局赔率。 | 3.4, 3.3, 3.5 | 3387 | distinct=72; range=1.4 - 17.0 |
| `B365A` | `REAL` |  | Bet365 的客胜赔率。 | 4.0, 3.0, 3.4 | 3387 | distinct=115; range=1.08 - 51.0 |
| `BWH` | `REAL` |  | Bet&Win 的主胜赔率。 | 2.0, 2.1, 1.95 | 3404 | distinct=237; range=1.03 - 34.0 |
| `BWD` | `REAL` |  | Bet&Win 的平局赔率。 | 3.3, 3.2, 3.4 | 3404 | distinct=133; range=1.65 - 19.5 |
| `BWA` | `REAL` |  | Bet&Win 的客胜赔率。 | 3.1, 3.0, 3.4 | 3404 | distinct=261; range=1.1 - 51.0 |
| `IWH` | `REAL` |  | Interwetten 的主胜赔率。 | 2.0, 2.1, 2.2 | 3459 | distinct=147; range=1.03 - 20.0 |
| `IWD` | `REAL` |  | Interwetten 的平局赔率。 | 3.3, 3.2, 3.1 | 3459 | distinct=73; range=1.5 - 11.0 |
| `IWA` | `REAL` |  | Interwetten 的客胜赔率。 | 3.3, 3.1, 2.6 | 3459 | distinct=159; range=1.1 - 25.0 |
| `LBH` | `REAL` |  | Ladbrokes 的主胜赔率。 | 2.1, 2.0, 2.2 | 3423 | distinct=129; range=1.04 - 26.0 |
| `LBD` | `REAL` |  | Ladbrokes 的平局赔率。 | 3.2, 3.3, 3.4 | 3423 | distinct=72; range=1.4 - 19.0 |
| `LBA` | `REAL` |  | Ladbrokes 的客胜赔率。 | 4.0, 3.0, 4.5 | 3423 | distinct=128; range=1.1 - 51.0 |
| `PSH` | `REAL` |  | Pinnacle Sports 的主胜赔率。 | 1.93, 1.83, 1.85 | 14811 | distinct=948; range=1.04 - 36.0 |
| `PSD` | `REAL` |  | Pinnacle Sports 的平局赔率。 | 3.44, 3.35, 3.41 | 14811 | distinct=665; range=2.2 - 29.0 |
| `PSA` | `REAL` |  | Pinnacle Sports 的客胜赔率。 | 2.19, 3.02, 3.06 | 14811 | distinct=1475; range=1.09 - 47.5 |
| `WHH` | `REAL` |  | William Hill 的主胜赔率。 | 2.5, 2.0, 2.3 | 3408 | distinct=125; range=1.02 - 26.0 |
| `WHD` | `REAL` |  | William Hill 的平局赔率。 | 3.2, 3.1, 3.3 | 3408 | distinct=78; range=1.02 - 17.0 |
| `WHA` | `REAL` |  | William Hill 的客胜赔率。 | 4.0, 5.0, 3.1 | 3408 | distinct=136; range=1.08 - 51.0 |
| `SJH` | `REAL` |  | Stan James 的主胜赔率。 | 2.1, 2.0, 2.5 | 8882 | distinct=137; range=1.04 - 23.0 |
| `SJD` | `REAL` |  | Stan James 的平局赔率。 | 3.4, 3.25, 3.5 | 8882 | distinct=79; range=1.4 - 15.0 |
| `SJA` | `REAL` |  | Stan James 的客胜赔率。 | 4.0, 3.0, 3.6 | 8882 | distinct=132; range=1.1 - 41.0 |
| `VCH` | `REAL` |  | VC Bet 的主胜赔率。 | 2.1, 2.0, 2.2 | 3411 | distinct=160; range=1.03 - 36.0 |
| `VCD` | `REAL` |  | VC Bet 的平局赔率。 | 3.4, 3.3, 3.5 | 3411 | distinct=82; range=1.62 - 26.0 |
| `VCA` | `REAL` |  | VC Bet 的客胜赔率。 | 4.0, 3.0, 3.4 | 3411 | distinct=151; range=1.08 - 67.0 |
| `GBH` | `REAL` |  | Gamebookers 的主胜赔率。 | 2.1, 2.0, 2.2 | 11817 | distinct=159; range=1.05 - 21.0 |
| `GBD` | `REAL` |  | Gamebookers 的平局赔率。 | 3.25, 3.2, 3.3 | 11817 | distinct=84; range=1.45 - 11.0 |
| `GBA` | `REAL` |  | Gamebookers 的客胜赔率。 | 4.0, 3.0, 3.75 | 11817 | distinct=172; range=1.12 - 34.0 |
| `BSH` | `REAL` |  | Blue Square 的主胜赔率。 | 2.1, 2.0, 2.5 | 11818 | distinct=101; range=1.04 - 17.0 |
| `BSD` | `REAL` |  | Blue Square 的平局赔率。 | 3.25, 3.3, 3.4 | 11818 | distinct=59; range=1.33 - 13.0 |
| `BSA` | `REAL` |  | Blue Square 的客胜赔率。 | 3.0, 2.88, 5.0 | 11818 | distinct=96; range=1.12 - 34.0 |

### 3.4 `Player`

球员主表。 行数：`11060`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `id` | `INTEGER` | PK | 球员的唯一标识符。 | 1, 2, 3 | 0 | distinct=11060; range=1 - 11075 |
| `player_api_id` | `INTEGER` |  | 球员 API ID。 | 2625, 2752, 2768 | 0 | distinct=11060; range=2625 - 750584 |
| `player_name` | `TEXT` |  | 球员姓名。 | Danilo, Paulinho, Ricardo | 0 | distinct=10848 |
| `player_fifa_api_id` | `INTEGER` |  | 球员 FIFA API ID。 | 2, 6, 11 | 0 | distinct=11060; range=2 - 234141 |
| `birthday` | `TEXT` |  | 生日。 | 1989-03-02 00:00:00, 1988-08-31 00:00:00, 1990-01-13 00:00:00 | 0 | distinct=5762 |
| `height` | `INTEGER` |  | 身高。 | 182.88, 177.8, 180.34 | 0 | distinct=20; range=157.48 - 208.28 |
| `weight` | `INTEGER` |  | 体重。 | 165, 176, 154 | 0 | distinct=50; range=117 - 243 |

### 3.5 `Player_Attributes`

球员能力属性历史表。 行数：`183978`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `id` | `INTEGER` | PK | 球员属性的唯一标识符。 | 1, 2, 3 | 0 | range=1 - 183978 |
| `player_fifa_api_id` | `INTEGER` | FK -> Player.player_fifa_api_id | 球员 FIFA API ID。 外键，指向 `Player.player_fifa_api_id`。 | 184431, 178393, 193061 | 0 | range=2 - 234141 |
| `player_api_id` | `INTEGER` | FK -> Player.player_api_id | 球员 API ID。 外键，指向 `Player.player_api_id`。 | 41269, 210278, 42116 | 0 | range=2625 - 750584 |
| `date` | `TEXT` |  | 球员属性记录日期时间；通常形如 `YYYY-MM-DD HH:MM:SS`，按日期过滤需截取日期部分。 | 2007-02-22 00:00:00, 2013-09-20 00:00:00, 2011-08-30 00:00:00 | 0 |  |
| `overall_rating` | `INTEGER` |  | 综合评分。 | 68, 69, 67 | 836 | range=33 - 94 |
| `potential` | `INTEGER` |  | 潜力评分。 | 75, 74, 76 | 836 | range=39 - 97 |
| `preferred_foot` | `TEXT` |  | 惯用脚。 | right, left | 836 |  |
| `attacking_work_rate` | `TEXT` |  | 进攻投入程度。 | medium, high, low | 3230 |  |
| `defensive_work_rate` | `TEXT` |  | 防守投入程度。 | medium, high, low | 836 |  |
| `crossing` | `INTEGER` |  | 传中。 | 68, 62, 67 | 836 | range=1 - 95 |
| `finishing` | `INTEGER` |  | 射门。 | 25, 64, 66 | 836 | range=1 - 97 |
| `heading_accuracy` | `INTEGER` |  | 头球准确度。 | 68, 60, 64 | 836 | range=1 - 98 |
| `short_passing` | `INTEGER` |  | 缩写传球。 | 65, 64, 68 | 836 | range=3 - 97 |
| `volleys` | `INTEGER` |  | 凌空射门能力值。 | 25, 59, 58 | 2713 | range=1 - 93 |
| `dribbling` | `INTEGER` |  | 盘带。 | 68, 66, 64 | 836 | range=1 - 97 |
| `curve` | `INTEGER` |  | 弧线。 | 25, 68, 60 | 2713 | range=2 - 94 |
| `free_kick_accuracy` | `INTEGER` |  | freekick准确度。 | 25, 60, 58 | 836 | range=1 - 97 |
| `long_passing` | `INTEGER` |  | 全称传球。 | 64, 65, 62 | 836 | range=3 - 97 |
| `ball_control` | `INTEGER` |  | 控球能力值。 | 68, 74, 73 | 836 | range=5 - 97 |
| `acceleration` | `INTEGER` |  | 加速度能力值。 | 68, 69, 74 | 836 | range=10 - 97 |
| `sprint_speed` | `INTEGER` |  | 冲刺速度。 | 68, 69, 76 | 836 | range=12 - 97 |
| `agility` | `INTEGER` |  | 敏捷。 | 72, 74, 73 | 2713 | range=11 - 96 |
| `reactions` | `INTEGER` |  | 反应能力值。 | 68, 66, 70 | 836 | range=17 - 96 |
| `balance` | `INTEGER` |  | 余额。 | 70, 72, 71 | 2713 | range=12 - 96 |
| `shot_power` | `INTEGER` |  | shot力量/能力。 | 68, 72, 74 | 836 | range=2 - 97 |
| `jumping` | `INTEGER` |  | 弹跳。 | 72, 70, 71 | 2713 | range=14 - 96 |
| `stamina` | `INTEGER` |  | 体能能力值。 | 68, 72, 70 | 836 | range=10 - 96 |
| `strength` | `INTEGER` |  | 力量。 | 68, 74, 72 | 836 | range=10 - 96 |
| `long_shots` | `INTEGER` |  | 全称shots。 | 25, 64, 68 | 836 | range=1 - 96 |
| `aggression` | `INTEGER` |  | 侵略性/对抗能力值。 | 68, 74, 72 | 836 | range=6 - 97 |
| `interceptions` | `INTEGER` |  | 拦截能力值。 | 25, 64, 68 | 836 | range=1 - 96 |
| `positioning` | `INTEGER` |  | 站位。 | 25, 68, 64 | 836 | range=2 - 96 |
| `vision` | `INTEGER` |  | 视野。 | 68, 64, 65 | 2713 | range=1 - 97 |
| `penalties` | `INTEGER` |  | 点球。 | 58, 64, 60 | 836 | range=2 - 96 |
| `marking` | `INTEGER` |  | 盯人。 | 25, 68, 64 | 836 | range=1 - 96 |
| `standing_tackle` | `INTEGER` |  | 站立抢断。 | 25, 68, 66 | 836 | range=1 - 95 |
| `sliding_tackle` | `INTEGER` |  | 滑铲抢断。 | 25, 68, 65 | 2713 | range=2 - 95 |
| `gk_diving` | `INTEGER` |  | 门将扑救。 | 8, 9, 7 | 836 | range=1 - 94 |
| `gk_handling` | `INTEGER` |  | 门将手控球。 | 7, 11, 14 | 836 | range=1 - 93 |
| `gk_kicking` | `INTEGER` |  | 门将开球。 | 7, 12, 10 | 836 | range=1 - 97 |
| `gk_positioning` | `INTEGER` |  | 门将站位。 | 9, 7, 8 | 836 | range=1 - 96 |
| `gk_reflexes` | `INTEGER` |  | 门将反应。 | 8, 10, 14 | 836 | range=1 - 96 |

### 3.6 `Team`

球队主表。 行数：`299`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `id` | `INTEGER` | PK | 球队的唯一标识符。 | 1, 2, 3 | 0 | distinct=299; range=1 - 51606 |
| `team_api_id` | `INTEGER` |  | 球队 API ID。 | 1601, 1773, 1957 | 0 | distinct=299; range=1601 - 274581 |
| `team_fifa_api_id` | `INTEGER` |  | 球队 FIFA API ID。 | 301, 111429, 111560 | 11 | distinct=285; range=1 - 112513 |
| `team_long_name` | `TEXT` |  | 球队全称。 | Polonia Bytom, Royal Excel Mouscron, Widzew Łódź | 0 | distinct=296 |
| `team_short_name` | `TEXT` |  | 球队简称。 | BEL, GEN, GRA | 0 | distinct=259 |

### 3.7 `Team_Attributes`

球队战术属性历史表。 行数：`1458`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `id` | `INTEGER` | PK | 球队属性的唯一标识符。 | 1, 2, 3 | 0 | distinct=1458; range=1 - 1458 |
| `team_fifa_api_id` | `INTEGER` | FK -> Team.team_fifa_api_id | 球队 FIFA API ID。 外键，指向 `Team.team_fifa_api_id`。 | 301, 1, 2 | 0 | distinct=285; range=1 - 112513 |
| `team_api_id` | `INTEGER` | FK -> Team.team_api_id | 球队 API ID。 外键，指向 `Team.team_api_id`。 | 1601, 1957, 2182 | 0 | distinct=288; range=1601 - 274581 |
| `date` | `TEXT` |  | 球队属性记录日期时间；通常形如 `YYYY-MM-DD HH:MM:SS`，按日期过滤需截取日期部分。 | 2015-09-10 00:00:00, 2011-02-22 00:00:00, 2014-09-19 00:00:00 | 0 | distinct=6 |
| `buildUpPlaySpeed` | `INTEGER` |  | 组织进攻打法速度。 | 50, 30, 55 | 0 | distinct=57; range=20 - 80 |
| `buildUpPlaySpeedClass` | `TEXT` |  | 组织进攻打法速度类别。 | Balanced, Fast, Slow | 0 | distinct=3 |
| `buildUpPlayDribbling` | `INTEGER` |  | 组织进攻打法盘带。 | 52, 48, 55 | 969 | distinct=49; range=24 - 77 |
| `buildUpPlayDribblingClass` | `TEXT` |  | 组织进攻打法盘带类别。 | Little, Normal, Lots | 0 | distinct=3 |
| `buildUpPlayPassing` | `INTEGER` |  | 组织进攻打法传球。 | 50, 30, 52 | 0 | distinct=58; range=20 - 80 |
| `buildUpPlayPassingClass` | `TEXT` |  | 组织进攻打法传球类别。 | Mixed, Short, Long | 0 | distinct=3 |
| `buildUpPlayPositioningClass` | `TEXT` |  | 组织进攻打法站位类别。 | Organised, Free Form | 0 | distinct=2 |
| `chanceCreationPassing` | `INTEGER` |  | chance创建传球。 | 50, 55, 52 | 0 | distinct=50; range=21 - 80 |
| `chanceCreationPassingClass` | `TEXT` |  | chance创建传球类别。 | Normal, Risky, Safe | 0 | distinct=3 |
| `chanceCreationCrossing` | `INTEGER` |  | chance创建传中。 | 50, 70, 52 | 0 | distinct=56; range=20 - 80 |
| `chanceCreationCrossingClass` | `TEXT` |  | chance创建传中类别。 | Normal, Lots, Little | 0 | distinct=3 |
| `chanceCreationShooting` | `INTEGER` |  | chance创建Shooting。 | 50, 70, 52 | 0 | distinct=57; range=22 - 80 |
| `chanceCreationShootingClass` | `TEXT` |  | chance创建Shooting类别。 | Normal, Lots, Little | 0 | distinct=3 |
| `chanceCreationPositioningClass` | `TEXT` |  | chance创建站位类别。 | Organised, Free Form | 0 | distinct=2 |
| `defencePressure` | `INTEGER` |  | 防守压迫强度。 | 45, 47, 30 | 0 | distinct=48; range=23 - 72 |
| `defencePressureClass` | `TEXT` |  | defencePressure类别。 | Medium, Deep, High | 0 | distinct=3 |
| `defenceAggression` | `INTEGER` |  | 防守侵略性。 | 45, 47, 50 | 0 | distinct=47; range=24 - 72 |
| `defenceAggressionClass` | `TEXT` |  | defenceAggression类别。 | Press, Double, Contain | 0 | distinct=3 |
| `defenceTeamWidth` | `INTEGER` |  | defence球队Width。 | 50, 52, 53 | 0 | distinct=43; range=29 - 73 |
| `defenceTeamWidthClass` | `TEXT` |  | defence球队Width类别。 | Normal, Wide, Narrow | 0 | distinct=3 |
| `defenceDefenderLineClass` | `TEXT` |  | defenceDefenderLine类别。 | Cover, Offside Trap | 0 | distinct=2 |

## 4. 常用查询模板

### 4.1 `League` join `country`

```sql
SELECT *
FROM "League" AS t1
JOIN "country" AS t2
  ON t1."country_id" = t2."id";
```

### 4.2 `Match` join `Player`

```sql
SELECT *
FROM "Match" AS t1
JOIN "Player" AS t2
  ON t1."away_player_11" = t2."player_api_id";
```

### 4.3 `Match` join `Player`

```sql
SELECT *
FROM "Match" AS t1
JOIN "Player" AS t2
  ON t1."away_player_10" = t2."player_api_id";
```

### 4.4 `Match` join `Player`

```sql
SELECT *
FROM "Match" AS t1
JOIN "Player" AS t2
  ON t1."away_player_9" = t2."player_api_id";
```

### 4.5 `Match` join `Player`

```sql
SELECT *
FROM "Match" AS t1
JOIN "Player" AS t2
  ON t1."away_player_8" = t2."player_api_id";
```

### 4.6 `Match` join `Player`

```sql
SELECT *
FROM "Match" AS t1
JOIN "Player" AS t2
  ON t1."away_player_7" = t2."player_api_id";
```

### 4.7 `Match` join `Player`

```sql
SELECT *
FROM "Match" AS t1
JOIN "Player" AS t2
  ON t1."away_player_6" = t2."player_api_id";
```

### 4.8 `Match` join `Player`

```sql
SELECT *
FROM "Match" AS t1
JOIN "Player" AS t2
  ON t1."away_player_5" = t2."player_api_id";
```

## 5. Text-to-SQL 易错点

- 日期/时间相关字段：`Match.date`, `Player.birthday`, `Player_Attributes.date`, `Team_Attributes.date`。过滤前先查看实际字符串格式。
- 本次评测错题暴露出的典型坑：
  - qid1028（输出形状/答案格式错误）：并列第一处理错误。Scotland Premier League 在 `2009/2010` season 中 away win 最多的队伍有 `Rangers` 和 `Celtic` 两个并列；pred 用 `ORDER BY win_count DESC LIMIT 1` 只保留 `Celtic`。同时 pred 多输出了 `win_count`，输出形状也不匹配。
  - qid1029（输出形状/答案格式错误）：latest-record 和排序逻辑正确，失败来自输出形状。gold 只要求 `buildUpPlaySpeed` 一列；pred 多输出了 team name、short name 和 date。
  - qid1031（输出形状/答案格式错误）：年龄计算少了生日月日修正，把 exact age 算成 naive age；同时没有按玩家/年龄去重，并多输出了姓名、速度和日期。
  - qid1032（排序/TopK/Tie/排名错误）：并列第一处理错误。三个 league 的 match count 都是 3040，pred 使用 `ORDER BY ... LIMIT 1` 只返回一条。
  - qid1037（聚合/公式/粒度错误）：gold 按出生在 1987-1992 的 distinct players 统计“曾经 preferred_foot = left 的玩家占比”；pred 按 `Player_Attributes` 记录行统计，玩家属性记录越多权重越大。另有 `ROUND(..., 2)` 精度损失，但主因是 entity-level percentage 被写成 record-level percentage。
  - qid1040（输出形状/答案格式错误）：排序和 top 10 逻辑正确，失败来自输出形状。gold 只要 player name；pred 多输出了平均 heading accuracy。
  - qid1044（输出形状/答案格式错误）：筛选逻辑正确，失败来自输出形状。gold 只要求姓名；pred 多输出生日。
  - qid1076（输出形状/答案格式错误）：差值计算正确，失败来自输出形状。gold 只要最终 difference；pred 多输出了两人的中间平均值。
  - qid1078（输出形状/答案格式错误）：pred 只列出了两人的生日，没有完成“older”比较并只选择年龄更大者；同时多输出 birthday。
  - qid1079（输出形状/答案格式错误）：最高身高玩家定位正确，失败来自输出形状。gold 只要 player name；pred 多输出 height。
  - qid1092（输出形状/答案格式错误）：并列第一处理错误。2008/2009 season 中四个 league 都有 380 场，pred `LIMIT 1` 只保留一个；同时多输出 match count。
  - qid1094（聚合/公式/粒度错误）：百分比公式缺少括号，把 `(A - B) * 100 / B` 写成了 `A - B * 100 / B`。`ROUND(..., 2)` 也是精度问题，但不是造成符号错误的主因。
  - qid1110（协议/轮数/收敛失败）：探索阶段已经拿到正确答案，但确认/收敛失败；模型把题目中的属性日期错误路由到 `Match` 表，忽略了 `Team_Attributes.date` 才是目标字段所在表。
  - qid1114（类型/日期/NULL/值规范错误）：日期边界处理错误。pred 没有用 `SUBSTR(date,1,10)` 或 `LIKE '2016-04-21%'` 包含结束日，漏掉 2016-04-21 当天记录。
  - qid1115（协议/轮数/收敛失败）：任务语义路由错表。题目问的是玩家属性在某日期的 rating，不需要 match；pred 把日期解释成比赛日期，导致多轮探索耗尽，最终没有 SQL。
  - qid1136（聚合/公式/粒度错误）：gold 问的是玩家数，应 `COUNT(DISTINCT player_api_id)`；pred 用 `COUNT(*)` 按属性记录计数，把同一玩家多条属性记录重复计入。
  - qid1144（输出形状/答案格式错误）：目标记录集合正确，失败来自输出形状。gold 只要 finishing 和 curve；pred 多输出玩家名和体重。
  - qid1145（输出形状/答案格式错误）：top 4 集合正确，行顺序不影响本评测；失败来自输出形状。gold 只要 league name，pred 多输出 count。
