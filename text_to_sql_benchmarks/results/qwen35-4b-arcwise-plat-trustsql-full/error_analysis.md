# Qwen3.5-4B TRUST-SQL-style Arcwise-Plat 全量错误分析

## 运行配置

- 数据集: `/root/autodl-tmp/text_to_sql_benchmarks/data/arcwise_plat_full_with_diff.json`
- DB root: `/root/autodl-tmp/DeepEye-SQL/data/arcwise_plat/dev/dev_databases`
- 模型: `/root/autodl-tmp/DeepEye-SQL/workspace/models/modelscope/Qwen/Qwen3___5-4B`
- vLLM API: `http://127.0.0.1:8000/v1`
- 输出目录: `/root/autodl-tmp/text_to_sql_benchmarks/results/qwen35-4b-arcwise-plat-trustsql-full`
- max_rounds: `10`, temperature: `0.2`, top_p: `0.9`, fallback_to_last_generated: `True`

## 总体结果

| 指标 | 数值 |
|---|---:|
| 样本数 | 498 |
| 正确数 | 226 |
| Execution Accuracy | 45.38% |
| 错误数 | 272 |
| 平均轮数 | 7.83 |
| 中位轮数 | 8 |
| 正常 confirm_answer 终止 | 372 (74.7%) |
| 未终止 | 126 (25.3%) |
| 未终止但 fallback 正确 | 12 |
| 未产出最终 SQL | 49 |
| 预测 SQL 执行报错 | 15 |

## 主错误类型

主类是互斥分类；语义类按 `表/连接 -> 聚合/分组 -> 过滤/日期 -> DISTINCT -> 排序/Top-K -> 投影差异` 的优先级归因。

| 错误类型 | 数量 | 占错误比例 | 占全量比例 |
|---|---:|---:|---:|
| 未终止，fallback SQL 语义错 | 51 | 18.8% | 10.2% |
| 未产出最终 SQL | 49 | 18.0% | 9.8% |
| 表/连接路径或 schema linking 错 | 44 | 16.2% | 8.8% |
| 过滤条件、值或日期错 | 43 | 15.8% | 8.6% |
| 聚合或分组粒度错 | 37 | 13.6% | 7.4% |
| 投影列或等价表达差异 | 22 | 8.1% | 4.4% |
| SQL 执行报错 | 15 | 5.5% | 3.0% |
| DISTINCT/去重错 | 11 | 4.0% | 2.2% |

## 可执行错误 SQL 的多标签语义问题

说明: 同一条 SQL 可能同时有 schema linking、过滤条件、聚合粒度等多个问题。

| 语义标签 | 数量 |
|---|---:|
| 过滤条件、值或日期错 | 140 |
| 聚合或分组粒度错 | 78 |
| 表/连接路径或 schema linking 错 | 76 |
| DISTINCT/去重错 | 50 |
| 排序或 Top-K 错 | 34 |
| 投影列或等价表达差异 | 23 |

## 按数据库统计

| db_id | n | correct | EX | not_terminated | no_sql | pred_exec_error |
|---|---:|---:|---:|---:|---:|---:|
| california_schools | 30 | 7 | 23.3% | 10 | 6 | 2 |
| financial | 30 | 7 | 23.3% | 18 | 13 | 2 |
| toxicology | 40 | 13 | 32.5% | 8 | 0 | 1 |
| thrombosis_prediction | 50 | 17 | 34.0% | 15 | 4 | 5 |
| debit_card_specializing | 30 | 11 | 36.7% | 9 | 2 | 0 |
| formula_1 | 66 | 28 | 42.4% | 18 | 7 | 2 |
| card_games | 52 | 26 | 50.0% | 8 | 2 | 0 |
| student_club | 48 | 26 | 54.2% | 15 | 5 | 2 |
| codebase_community | 49 | 28 | 57.1% | 7 | 1 | 1 |
| superhero | 52 | 30 | 57.7% | 11 | 5 | 0 |
| european_football_2 | 51 | 33 | 64.7% | 7 | 4 | 0 |

## 阶段动作统计

| 项 | 数量 |
|---|---:|
| action=explore_schema | 2348 |
| action=generate_sql | 719 |
| action=propose_schema | 459 |
| action=confirm_answer | 372 |
| last_action=confirm_answer | 372 |
| last_action=generate_sql | 75 |
| last_action=explore_schema | 42 |
| last_action=propose_schema | 9 |

Top action 序列:

- 88x: `explore_schema -> explore_schema -> explore_schema -> propose_schema -> generate_sql -> confirm_answer`
- 73x: `explore_schema -> explore_schema -> explore_schema -> explore_schema -> propose_schema -> generate_sql -> confirm_answer`
- 42x: `explore_schema -> explore_schema -> explore_schema -> explore_schema -> explore_schema -> propose_schema -> generate_sql -> confirm_answer`
- 38x: `explore_schema -> explore_schema -> explore_schema -> explore_schema -> explore_schema -> explore_schema -> explore_schema -> explore_schema -> explore_schema -> explore_schema`
- 32x: `explore_schema -> explore_schema -> propose_schema -> generate_sql -> confirm_answer`
- 20x: `explore_schema -> explore_schema -> explore_schema -> explore_schema -> propose_schema -> generate_sql -> generate_sql -> confirm_answer`
- 18x: `explore_schema -> explore_schema -> explore_schema -> explore_schema -> propose_schema -> generate_sql -> generate_sql -> generate_sql -> generate_sql -> generate_sql`
- 18x: `explore_schema -> explore_schema -> explore_schema -> explore_schema -> explore_schema -> explore_schema -> propose_schema -> generate_sql -> confirm_answer`

## 典型错误样例

### 未产出最终 SQL

- qid=1479, db=debit_card_specializing, rounds=10, terminated=False, fallback=False
  - Q: Which year recorded the most consumption of gas paid in CZK?
  - Gold: `SELECT SUBSTR(T2.Date, 1, 4) FROM customers AS T1 INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID WHERE T1.Currency = 'CZK' GROUP BY SUBSTR(T2.Date, 1, 4) ORDER BY SUM(T2.Consumption) DESC LIMIT 1`
  - Pred: ``

- qid=1526, db=debit_card_specializing, rounds=10, terminated=False, fallback=False
  - Q: For the customer who paid 634.8 in 2012/8/25, what was the consumption decrease rate from Year 2012 to 2013?
  - Gold: `SELECT CAST(SUM(IIF(SUBSTRING(Date, 1, 4) = '2012', Consumption, 0)) - SUM(IIF(SUBSTRING(Date, 1, 4) = '2013', Consumption, 0)) AS FLOAT) / SUM(IIF(SUBSTRING(Date, 1, 4) = '2012', Consumption, 0)) FROM yearmonth WHERE CustomerID = ( SELECT ...`
  - Pred: ``

- qid=1317, db=student_club, rounds=10, terminated=False, fallback=False
  - Q: Among the students from the Student_Club who attended the event "Women's Soccer", how many of them want a T-shirt that's in medium size?
  - Gold: `SELECT COUNT(T1.event_id) FROM event AS T1 INNER JOIN attendance AS T2 ON T1.event_id = T2.link_to_event INNER JOIN member AS T3 ON T2.link_to_member = T3.member_id WHERE T1.event_name = 'Women''s Soccer' AND T3.t_shirt_size = 'Medium'`
  - Pred: ``

### 未终止，fallback SQL 语义错

- qid=1476, db=debit_card_specializing, rounds=10, terminated=False, fallback=True
  - Q: What was the difference in gas consumption between CZK-paying customers and EUR-paying customers in 2012?
  - Gold: `SELECT SUM(IIF(T1.Currency = 'CZK', T2.Consumption, 0)) - SUM(IIF(T1.Currency = 'EUR', T2.Consumption, 0)) FROM customers AS T1 INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID WHERE SUBSTR(T2.Date, 1, 4) = '2012'`
  - Pred: `SELECT c.Currency, COUNT(*) as record_count, SUM(ym.Consumption) as total_consumption FROM yearmonth ym JOIN customers c ON ym.CustomerID = c.CustomerID WHERE ym.Date BETWEEN '201201' AND '201212' GROUP BY c.Currency;`

- qid=1481, db=debit_card_specializing, rounds=10, terminated=False, fallback=True
  - Q: What is the difference in the annual average consumption of the customers with the least amount of consumption paid in CZK for 2013 between SME and LAM, LAM and...
  - Gold: `WITH customer_consumption AS (SELECT c.Segment, c.CustomerID, SUM(ym.Consumption) AS TotalConsumption, COUNT(DISTINCT ym.CustomerID) AS CustomerCount FROM customers AS c JOIN yearmonth AS ym ON c.CustomerID = ym.CustomerID WHERE ym.Date BET...`
  - Pred: `WITH yearly_consumption AS (     SELECT          c.CustomerID,         c.Segment,         SUM(y.Consumption) AS total_consumption     FROM customers c     JOIN yearmonth y ON c.CustomerID = y.CustomerID     WHERE y.Date BETWEEN '201301' AND...`

- qid=1483, db=debit_card_specializing, rounds=10, terminated=False, fallback=True
  - Q: How much did customer 6 consume in total between August and November 2013?
  - Gold: `SELECT SUM(Consumption) FROM yearmonth WHERE CustomerID = 6 AND Date BETWEEN '201308' AND '201311'`
  - Pred: `SELECT * FROM transactions_1k WHERE CustomerID = 6;`

### SQL 执行报错

- qid=1376, db=student_club, rounds=10, terminated=False, fallback=True
  - Q: Among all the closed events, which event has the highest spend-to-budget ratio?
  - Gold: `SELECT e.event_name FROM event AS e JOIN budget AS b ON e.event_id = b.link_to_event WHERE e.status = 'Closed' GROUP BY e.event_id, e.event_name HAVING SUM(b.amount) > 0 AND SUM(b.spent) / SUM(b.amount) = ( SELECT MAX(ratio) FROM ( SELECT S...`
  - Pred: `SELECT e.event_name, MAX(DIVIDE(SUM(b.spent), SUM(b.amount))) as ratio FROM event e JOIN budget b ON e.event_id = b.link_to_event WHERE e.status = 'Closed' GROUP BY e.event_id ORDER BY ratio DESC LIMIT 1;`
  - Pred error: `misuse of aggregate function SUM()`

- qid=1387, db=student_club, rounds=10, terminated=False, fallback=True
  - Q: Which student has been entrusted to use the budget for the Yearly Kickoff?
  - Gold: `SELECT T4.first_name, T4.last_name FROM event AS T1 INNER JOIN budget AS T2 ON T1.event_id = T2.link_to_event INNER JOIN expense AS T3 ON T2.budget_id = T3.link_to_budget INNER JOIN member AS T4 ON T3.link_to_member = T4.member_id WHERE T1....`
  - Pred: `SELECT m.first_name, m.last_name FROM member m JOIN budget b ON m.member_id = expense.link_to_member JOIN expense e ON b.budget_id = e.link_to_budget WHERE b.link_to_event = (SELECT event_id FROM event WHERE event_name = 'Yearly Kickoff');`
  - Pred error: `no such column: expense.link_to_member`

- qid=1168, db=thrombosis_prediction, rounds=10, terminated=False, fallback=True
  - Q: For the oldest SJS patient, on what date was their medical laboratory work last completed, and what age was the patient when they initially arrived at the hospi...
  - Gold: `SELECT T1.Date, STRFTIME('%Y', "First Date") - STRFTIME('%Y', Birthday) - CASE     WHEN strftime('%m-%d',"First Date") < strftime('%m-%d', Birthday) THEN 1     ELSE 0   END AS age FROM Laboratory AS T1 INNER JOIN Patient AS T2 ON T1.ID = T2...`
  - Pred: `SELECT      l.Date AS last_lab_date,     p.age_at_arrival FROM (     SELECT          p.ID,         p."First Date",         p.Birthday,         CASE              WHEN (strftime('%Y', p."First Date") - strftime('%Y', p.Birthday)) > 0         ...`
  - Pred error: `no such column: l.Date`

### 表/连接路径或 schema linking 错

- qid=1472, db=debit_card_specializing, rounds=8, terminated=True, fallback=False
  - Q: In 2012, who had the least consumption in LAM?
  - Gold: `SELECT T1.CustomerID FROM customers AS T1 INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID WHERE T1.Segment = 'LAM' AND SUBSTR(T2.Date, 1, 4) = '2012' GROUP BY T1.CustomerID ORDER BY SUM(T2.Consumption) ASC LIMIT 1`
  - Pred: `SELECT ym.CustomerID, ym.Consumption  FROM yearmonth ym  WHERE CAST(ym.Date AS INTEGER) BETWEEN 201201 AND 201212  GROUP BY ym.CustomerID  ORDER BY ym.Consumption ASC  LIMIT 1;`

- qid=1480, db=debit_card_specializing, rounds=8, terminated=True, fallback=False
  - Q: What was the gas consumption peak month for SME customers in 2013?
  - Gold: `SELECT SUBSTR(T2.Date, 5, 2) FROM customers AS T1 INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID WHERE SUBSTR(T2.Date, 1, 4) = '2013' AND T1.Segment = 'SME' GROUP BY SUBSTR(T2.Date, 5, 2) ORDER BY SUM(T2.Consumption) DESC LIMIT...`
  - Pred: `SELECT yearmonth.Date, yearmonth.Consumption  FROM yearmonth  WHERE yearmonth.CustomerID IN (SELECT CustomerID FROM customers WHERE Segment = 'SME')    AND yearmonth.Date BETWEEN '201301' AND '201312'  ORDER BY yearmonth.Consumption DESC  L...`

- qid=1490, db=debit_card_specializing, rounds=8, terminated=True, fallback=False
  - Q: What percentage of LAM customers consumed more than 46.73 in at least one month?
  - Gold: `SELECT CAST(COUNT(DISTINCT IIF(T2.Consumption > 46.73, T1.CustomerID, NULL)) AS REAL) * 100 / COUNT(DISTINCT T1.CustomerID) FROM customers AS T1 LEFT JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID WHERE T1.Segment = 'LAM'`
  - Pred: `SELECT      ROUND(         (SELECT COUNT(DISTINCT CustomerID)           FROM transactions_1k           WHERE Amount > 46.73           AND CustomerID IN (SELECT CustomerID FROM customers WHERE Segment = 'LAM')) * 100.0 /          (SELECT COU...`

### 聚合或分组粒度错

- qid=1473, db=debit_card_specializing, rounds=7, terminated=True, fallback=False
  - Q: What was the average monthly consumption of customers in SME for the year 2013?
  - Gold: `SELECT AVG(TotalConsumption) / 12 FROM (SELECT SUM(T2.Consumption) AS TotalConsumption FROM customers AS T1 INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID WHERE SUBSTR(T2.Date, 1, 4) = '2013' AND T1.Segment = 'SME' GROUP BY T1....`
  - Pred: `SELECT AVG(y.Consumption) as average_monthly_consumption  FROM yearmonth y  JOIN customers c ON y.CustomerID = c.CustomerID  WHERE c.Segment = 'SME'  AND y.Date BETWEEN '201301' AND '201312';`

- qid=1482, db=debit_card_specializing, rounds=9, terminated=True, fallback=False
  - Q: Provide the percentage increase in consumption paid in EUR between 2012 and 2013 for SME, LAM, and KAM respectively.
  - Gold: `SELECT CAST((SUM(IIF(T1.Segment = 'SME' AND T2.Date LIKE '2013%', T2.Consumption, 0)) - SUM(IIF(T1.Segment = 'SME' AND T2.Date LIKE '2012%', T2.Consumption, 0))) AS FLOAT) * 100 / SUM(IIF(T1.Segment = 'SME' AND T2.Date LIKE '2012%', T2.Cons...`
  - Pred: `SELECT      c.Segment,     ROUND((SUM(CASE WHEN SUBSTR(y.Date, 1, 4) = '2013' THEN y.Consumption END) - SUM(CASE WHEN SUBSTR(y.Date, 1, 4) = '2012' THEN y.Consumption END)) / NULLIF(SUM(CASE WHEN SUBSTR(y.Date, 1, 4) = '2012' THEN y.Consump...`

- qid=1484, db=debit_card_specializing, rounds=8, terminated=True, fallback=False
  - Q: How many more "discount" gas stations does the Czech Republic have compared to Slovakia?
  - Gold: `SELECT SUM(IIF(Country = 'CZE', 1, 0)) - SUM(IIF(Country = 'SVK', 1, 0)) FROM gasstations WHERE Segment = 'Discount'`
  - Pred: `SELECT (SELECT COUNT(*) FROM gasstations WHERE Country = 'CZE' AND Segment = 'Value for money') - (SELECT COUNT(*) FROM gasstations WHERE Country = 'SVK' AND Segment = 'Value for money') AS discount_difference;`

### 过滤条件、值或日期错

- qid=1525, db=debit_card_specializing, rounds=9, terminated=True, fallback=False
  - Q: What percentage of customers who made at least one transaction on 2012-08-25 used EUR on that date?
  - Gold: `SELECT CAST(COUNT(DISTINCT IIF(T2.Currency = 'EUR', T1.CustomerID, NULL)) AS FLOAT) * 100 / COUNT(DISTINCT T1.CustomerID) FROM transactions_1k AS T1 INNER JOIN customers AS T2 ON T1.CustomerID = T2.CustomerID WHERE T1.Date = '2012-08-25'`
  - Pred: `SELECT      COUNT(*) FILTER (WHERE c.Currency = 'EUR') * 100.0 / COUNT(*) AS eur_percentage FROM transactions_1k t JOIN customers c ON t.CustomerID = c.CustomerID WHERE t.Date = '2012-08-25';`

- qid=1334, db=student_club, rounds=6, terminated=True, fallback=False
  - Q: List the full name of the Student_Club members that grew up in Illinois state.
  - Gold: `SELECT T1.first_name, T1.last_name FROM member AS T1 INNER JOIN zip_code AS T2 ON T1.zip = T2.zip_code WHERE T2.state = 'Illinois'`
  - Pred: `SELECT CONCAT(m.first_name, ' ', m.last_name) AS full_name  FROM member m  JOIN zip_code z ON m.zip = z.zip_code  WHERE z.state = 'Illinois';`

- qid=1375, db=student_club, rounds=6, terminated=True, fallback=False
  - Q: List all the members of the "School of Applied Sciences, Technology and Education" department.
  - Gold: `SELECT T1.first_name, T1.last_name FROM member AS T1 INNER JOIN major AS T2 ON T1.link_to_major = T2.major_id WHERE T2.department = 'School of Applied Sciences, Technology and Education'`
  - Pred: `SELECT m.first_name || ' ' || m.last_name AS full_name  FROM member m  INNER JOIN major maj ON m.link_to_major = maj.major_id  WHERE maj.department = 'School of Applied Sciences, Technology and Education';`

### DISTINCT/去重错

- qid=1247, db=thrombosis_prediction, rounds=9, terminated=True, fallback=False
  - Q: How many male patients had a lab result with a normal level of white blood cells, but abnormal fibrinogen level?
  - Gold: `SELECT COUNT(DISTINCT T1.ID) FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE (T2.FG <= 150 OR T2.FG >= 450) AND T2.WBC > 3.5 AND T2.WBC < 9.0 AND T1.SEX = 'M'`
  - Pred: `SELECT COUNT(*)  FROM Patient p  JOIN Laboratory l ON p.ID = l.ID  WHERE p.SEX = 'M'    AND l.WBC > 3.5    AND l.WBC < 9.0    AND (l.FG <= 150 OR l.FG >= 450);`

- qid=1256, db=thrombosis_prediction, rounds=7, terminated=True, fallback=False
  - Q: How many patients with a abnormal C-reactive protein don't have their data recorded?
  - Gold: `SELECT COUNT(DISTINCT T1.ID) FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE (T2.CRP = '+') AND T1.Description IS NULL`
  - Pred: `SELECT COUNT(*) FROM Laboratory l JOIN Patient p ON l.ID = p.ID WHERE l.CRP = '+' AND p.Description IS NULL;`

- qid=1136, db=european_football_2, rounds=5, terminated=True, fallback=False
  - Q: How many players had the highest potential score for crossing that preferred to use their left foots while attacking?
  - Gold: `SELECT COUNT(DISTINCT t1.player_api_id) FROM Player_Attributes AS t1 WHERE t1.preferred_foot = 'left' AND t1.crossing = ( SELECT MAX(crossing) FROM Player_Attributes)`
  - Pred: `SELECT COUNT(*)  FROM Player_Attributes  WHERE preferred_foot = 'left'  AND crossing = (SELECT MAX(crossing) FROM Player_Attributes WHERE preferred_foot = 'left');`

### 投影列或等价表达差异

- qid=1392, db=student_club, rounds=6, terminated=True, fallback=False
  - Q: Indicate the top source of funds received in September 2019 based on their amount.
  - Gold: `SELECT `source` FROM `Income` WHERE `date_received` BETWEEN '2019-09-01' AND '2019-09-30' GROUP BY `source` ORDER BY SUM(`amount`) DESC LIMIT 1;`
  - Pred: `SELECT source, SUM(amount) as total_amount  FROM income  WHERE date_received BETWEEN '2019-09-01' AND '2019-09-30'  GROUP BY source  ORDER BY total_amount DESC  LIMIT 1;`

- qid=1401, db=student_club, rounds=8, terminated=True, fallback=False
  - Q: Indicate the cost of posters for 'September Speaker' event.
  - Gold: `SELECT T3.cost FROM event AS T1 INNER JOIN budget AS T2 ON T1.event_id = T2.link_to_event INNER JOIN expense AS T3 ON T2.budget_id = T3.link_to_budget WHERE T1.event_name = 'September Speaker' AND T3.expense_description = 'Posters'`
  - Pred: `SELECT e.expense_description, e.cost  FROM expense e  INNER JOIN budget b ON e.link_to_budget = b.budget_id  INNER JOIN event ev ON b.link_to_event = ev.event_id  WHERE ev.event_name = 'September Speaker'    AND e.expense_description = 'Pos...`

- qid=1040, db=european_football_2, rounds=7, terminated=True, fallback=False
  - Q: List the top 10 players' names whose heights are above 180 in descending order of average heading accuracy.
  - Gold: `SELECT p.player_name FROM Player            AS p JOIN  Player_Attributes AS pa       ON p.player_api_id = pa.player_api_id WHERE p.height > 180 GROUP BY p.player_api_id, p.player_name ORDER BY AVG(pa.heading_accuracy) DESC LIMIT 10;`
  - Pred: `SELECT p.player_name, AVG(pa.heading_accuracy) as avg_heading_accuracy  FROM Player p  JOIN Player_Attributes pa ON p.player_fifa_api_id = pa.player_fifa_api_id  WHERE p.height > 180  GROUP BY p.player_fifa_api_id, p.player_name  ORDER BY a...`

## 初步结论

- 当前多轮推理 baseline 可以完整跑通 Arcwise-Plat，但 EX 只有 45.38%，明显低于一个稳定训练后的 TRUST-SQL agent 应该达到的状态。
- 最大的错误来源不是 vLLM 或 SQLite 崩溃，而是两类: 正常终止但 SQL 语义不等价，以及多轮协议没有在 10 轮内收束。
- `financial`、`california_schools`、`thrombosis_prediction`、`toxicology` 是主要低分库，适合优先做 schema exploration / value grounding / stage transition 改进。
- 有 12 条样本未正式 confirm_answer 但 fallback SQL 正确，说明执行器层面增加“生成 SQL 后强制确认/停止”的规则，可能不训练也能提升稳定性。
