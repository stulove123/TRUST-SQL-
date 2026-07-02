# Wrong Full Trace Detail Progress

目标：把所有错题分析文件从“概括表格”扩展为“概括版表格 + 逐轮完整详情”。

完成标准：

- 每个 qid 的 `### 运行轨迹` 下保留 `概括版表格：`。
- 概括表格后追加 `逐轮完整详情：`。
- 每个 conversation round 都有 `#### Round N`。
- 每轮包含阶段、think 中文完整翻译、SQL、完整返回结果。
- `#### Round N` 数量与 `wrong_details.pretty.json` 中 conversation 轮数一致。
- `- 返回结果：` 数量与 conversation 轮数一致。

控制源：

- `wrong_details.pretty.json`
- 各数据库错题分析 markdown 文件

## 当前完成度

| 数据库 / 范围 | 错题数 | 状态 | 分析文件 |
| --- | ---: | --- | --- |
| `debit_card_specializing` | 18 | 已完成并校验 | `debit_card_specializing_wrong_analysis.md` |
| `student_club` | 15 | 已完成并校验 | `student_club_wrong_analysis.md` |
| `california_schools` | 22 | 已完成并校验 | `california_schools_qid11_36_wrong_analysis.md`, `california_schools_qid37plus_wrong_analysis.md` |
| `card_games` | 26 | 已完成并校验 | `card_games_wrong_analysis.md` |
| `codebase_community` | 20 | 已完成并校验 | `codebase_community_wrong_analysis.md` |
| `european_football_2` | 18 | 已完成并校验 | `european_football_2_wrong_analysis.md` |
| `financial` | 21 | 已完成并校验 | `financial_wrong_analysis.md` |
| `formula_1` | 32 | 待补逐轮详情 | `formula_1_wrong_analysis.md` |
| `superhero` | 16 | 已完成并校验 | `superhero_wrong_analysis.md` |
| `thrombosis_prediction` | 26 | 待补逐轮详情 | `thrombosis_prediction_wrong_analysis.md` |
| `toxicology` | 24 | 待补逐轮详情 | `toxicology_wrong_analysis.md` |

已完成逐轮详情：156 / 238。

## 最近校验

```text
debit_card_specializing: 18/18, bad=0
student_club: 15/15, bad=0
superhero: 16/16, bad=0
european_football_2: 18/18, bad=0
california_schools: 22/22, bad=0
card_games: 26/26, bad=0
codebase_community: 20/20, bad=0
financial: 21/21, bad=0
ALL_DONE: 156/238
```
