#!/usr/bin/env python3
"""Apply hand-written, root-cause-oriented trajectory tables for toxicology."""

from __future__ import annotations

import re
from pathlib import Path


TARGET = Path("/root/autodl-tmp/text_to_sql_benchmarks/results/qwen35-4b-arcwise-plat-trustsql-full-final-thinking/toxicology_wrong_analysis.md")


TABLES = {
    "195": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 只有 `bond` 与“bond type”直接相关。 |
| Round 2 | explore_schema | 查看 `bond` 建表 SQL | 找到 `bond_type` 和 `bond_id`，可按类型计数。 |
| Round 3 | explore_schema | 查看 `bond` 结构 | 进一步锁定 `bond_type`。 |
| Round 4 | generate_sql | 按 `bond_type` 分组并按 count 降序取 1 | top 类型 `'-'` 正确，但 SQL 同时输出了 `COUNT(*)`。 |
| Round 5 | confirm_answer | 确认二列结果 | gold 只要 `bond_type` 单列，输出形状导致 EX 失败。 |""",
    "197": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要 `bond` 找含单键 molecule，`atom` 数氧原子。 |
| Round 2 | explore_schema | 查看四张表建表 SQL | 已知道 `atom.molecule_id` 与 `bond.molecule_id` 可对齐。 |
| Round 3 | explore_schema | 查看 `bond` 结构 | 锁定 `bond_type`。 |
| Round 4 | explore_schema | 查询 `bond_type` 取值 | 看到单键真实值是 `'-'`。 |
| Round 5 | generate_sql | 只在 `atom.element='o'` 的行中按 molecule 计数后求平均 | 把 0 氧 molecule 排除了；gold 要所有含单键 molecule 都参与平均，0 氧计为 0。 |
| Round 6 | confirm_answer | 确认排除 0 值分子的平均值 | pred 得 3.3537，gold 是 2.3597，分母集合错。 |""",
    "200": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要 `bond` 的 triple bond 与 `molecule` 的 carcinogenic label。 |
| Round 2 | explore_schema | 查看四张表建表 SQL | 已找到 `bond.molecule_id` 和 `molecule.label`。 |
| Round 3 | propose_schema | schema JSON 解析失败 | 没有成功记录 schema，但不影响后续 SQL。 |
| Round 4 | generate_sql | 筛 `bond_type='#'` 且 `label='+'` | 两个 molecule ID 都正确，但多输出了 label 列。 |
| Round 5 | confirm_answer | 确认二列 SQL | gold 只要 `molecule_id`，输出形状错。 |""",
    "201": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要含 double bond molecule 的 atom 集合。 |
| Round 2 | explore_schema | 查看 `atom` | 找到 `element`，但还不知道大小写取值。 |
| Round 3 | explore_schema | 查看 `bond` | 找到 `bond_type`。 |
| Round 4 | explore_schema | 查看 `molecule` | 本题不需要 label。 |
| Round 5 | explore_schema | 再看 `atom` 建表 SQL | 仍未探索元素实际值。 |
| Round 6 | explore_schema | 查询 `bond_type` 取值 | 确认 double bond 是 `'='`。 |
| Round 7 | generate_sql | 计算百分比，但用 `a.element = 'C'` | 数据库元素是小写 `'c'`，结果变成 0。 |
| Round 8 | generate_sql | 改成列出含 double bond 的 molecule_id | 从计算退回探索，未产出百分比。 |
| Round 9 | generate_sql | 查询这些 molecule 的 distinct element | 看到真实值含小写 `c`，但没有用来修正最终公式。 |
| Round 10 | generate_sql | 又查全表 distinct element | 探索 SQL 覆盖最终 SQL，pred 变成 20 行元素列表。 |""",
    "208": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要含 hydrogen 的 molecule label 分布。 |
| Round 2 | explore_schema | 查看 `atom` | 找到 `element`。 |
| Round 3 | explore_schema | 查看 `molecule` | 找到 `label`。 |
| Round 4 | explore_schema | 一次提交多条样例和枚举查询 | 工具拒绝多语句。 |
| Round 5 | explore_schema | 查询 element 真实取值 | 看到 hydrogen 用小写 `'h'`。 |
| Round 6 | explore_schema | 查询 label 取值 | 看到 `+` 和 `-`。 |
| Round 7 | generate_sql | 按含 `h` 的 atom 行统计 label，取最多 label | label `'-'` 正确，但输出了计数 2465。 |
| Round 8 | confirm_answer | 确认二列 SQL | gold 只要 label 单列。 |""",
    "212": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要非致癌 molecule 中元素频次。 |
| Round 2 | explore_schema | 查看 `atom` | 找到 `element`。 |
| Round 3 | explore_schema | 查看 `molecule` | 找到非致癌 label `'-'` 的使用位置。 |
| Round 4 | explore_schema | 再看 `atom` 建表 SQL | 表路径无问题。 |
| Round 5 | propose_schema | 提出 `atom` + `molecule` | join 方向正确。 |
| Round 6 | generate_sql | 按元素计数后 `ORDER BY count ASC LIMIT 1` | 只返回 `ca`，漏掉同为最小计数 1 的 `k` 和 `pb`，还多输出 count。 |
| Round 7 | confirm_answer | 确认 `LIMIT 1` SQL | gold 要返回所有 tie，且只输出 element。 |""",
    "213": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要 `connected` 找两原子之间的 bond，再到 `bond` 取类型。 |
| Round 2 | explore_schema | 查看 `bond` | 找到 `bond_type`。 |
| Round 3 | explore_schema | 查看 `atom` | 确认 atom_id 格式。 |
| Round 4 | explore_schema | 查看 `connected` | 找到 `atom_id/atom_id2/bond_id`。 |
| Round 5 | propose_schema | 提出 `connected` join `bond` | 表路径正确。 |
| Round 6 | generate_sql | 查 TR004_8 与 TR004_20 两个方向的 bond type | 已得到 `-`，但因为双向记录返回两行，缺少 `DISTINCT`。 |
| Round 7 | generate_sql | 转去查看两个 atom 明细 | 偏离了最终答案。 |
| Round 8 | generate_sql | 查看涉及这两个 atom 的 connected 行 | 找到 `TR004_8_20`，但仍是探索。 |
| Round 9 | generate_sql | 用 bond_id 查 bond type | 又得到两个 `-`，仍缺 distinct。 |
| Round 10 | generate_sql | 最后一轮退回 `SELECT * FROM bond LIMIT 10` | 探索 SQL 覆盖了已经接近正确的查询，最终 pred 是 10 行 bond 样例。 |""",
    "218": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要致癌 molecule 中“不含 fluorine”的百分比。 |
| Round 2 | explore_schema | 查看 `molecule` | 找到 label。 |
| Round 3 | explore_schema | 查看 `atom` | 找到 element。 |
| Round 4 | propose_schema | 提出 `molecule` + `atom` | 表路径正确。 |
| Round 5 | generate_sql | 按 molecule 分组输出 total/with_f/without_f 三列 | 每个 molecule 一行，只是在做中间计数，且 `element!='f'` 逻辑会误判“不含 f”。 |
| Round 6 | generate_sql | 重复按 molecule 分组计数 | 没有改成百分比。 |
| Round 7 | generate_sql | 第三次重复按 molecule 分组计数 | 仍然是中间表。 |
| Round 8 | generate_sql | 去掉 group 后得到 152、1、152 三个计数 | 第二个数对，但“不含 fluorine”应为 151；同时题目要百分比单值。 |
| Round 9 | null | 输出格式不合协议 | 没有工具执行。 |
| Round 10 | null | 再次格式不合协议 | 最终停在三列计数 SQL。 |""",
    "219": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要 triple bond molecule 的致癌比例。 |
| Round 2 | explore_schema | 查看 `molecule` | 找到 label。 |
| Round 3 | explore_schema | 查看 `bond` | 找到 `bond_type/molecule_id`。 |
| Round 4 | explore_schema | 查看 `bond` 结构 | 锁定 triple bond 用 `'#'`。 |
| Round 5 | propose_schema | schema JSON 解析失败 | 没有成功记录 schema。 |
| Round 6 | generate_sql | join bond 后按 triple-bond 行计算 label 为 `+` 的比例 | 得到 60%；gold 要按 distinct molecule 计算，4 个 molecule 中 2 个致癌是 50%。 |
| Round 7 | confirm_answer | 确认 bond 行粒度百分比 | 分母粒度错。 |""",
    "226": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要 TR008 中 double bond 占比。 |
| Round 2 | explore_schema | 查看 `bond` | 找到 `bond_type` 和 `molecule_id`。 |
| Round 3 | explore_schema | 查看 `molecule` | 本题不需要 label。 |
| Round 4 | generate_sql | 正确计算 double bond 百分比 | 数值公式对，但输出完整浮点 3.8461538461538463。 |
| Round 5 | confirm_answer | 确认未 round 的 SQL | 题目和 gold 要 `ROUND(..., 5)`，严格 EX 下 3.84615 才对。 |""",
    "227": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 只需要 `molecule.label`。 |
| Round 2 | explore_schema | 查看 `molecule` | 找到 label。 |
| Round 3 | propose_schema | 提出只用 `molecule` | 表选择正确。 |
| Round 4 | generate_sql | 正确计算致癌 molecule 百分比 | 得到完整浮点 44.31486880466473。 |
| Round 5 | confirm_answer | 确认未 round 的 SQL | gold 使用 `ROUND(..., 3)`，应输出 44.315。 |""",
    "230": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要 TR060 的元素集合和 label。 |
| Round 2 | explore_schema | 查看 `molecule` | 找到 label。 |
| Round 3 | explore_schema | 查看 `atom` | 找到 element。 |
| Round 4 | propose_schema | 提出 `molecule` + `atom` | join 路径正确。 |
| Round 5 | generate_sql | 输出 `m.label, a.element` 的每个 atom 行 | TR060 的所有 atom 明细都被输出，未 `DISTINCT`，且列顺序与 gold 相反。 |
| Round 6 | confirm_answer | 确认 atom 行级 SQL | gold 要 5 行 distinct `(element, label)`。 |""",
    "231": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 只需要 `bond` 统计 TR010 的多数 bond type。 |
| Round 2 | explore_schema | 查看 `bond` | 找到 `bond_type/molecule_id`。 |
| Round 3 | explore_schema | 查看 `molecule` | 本题不需要。 |
| Round 4 | generate_sql | 按 `bond_type` 计数排序取 1 | 找到 `'-'`，但多输出 count=16。 |
| Round 5 | generate_sql | 列出全部类型及计数 | 看到 `-` 为 16、`=` 为 1，仍多输出 count。 |
| Round 6 | generate_sql | 重复全部类型计数 | 没有改成只输出 bond_type。 |
| Round 7 | confirm_answer | 确认二列 SQL | gold 只要 `bond_type`。 |""",
    "234": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要 `connected` 中涉及 TR009_12 的 bond。 |
| Round 2 | explore_schema | 查看 `atom` | 确认 atom_id 格式。 |
| Round 3 | explore_schema | 查看 `bond` | 可用 molecule_id 限定 TR009，但不是关键。 |
| Round 4 | explore_schema | 查看 `connected` | 看到 `atom_id/atom_id2/bond_id`，但未意识到双向存储。 |
| Round 5 | generate_sql | 对 `atom_id` 或 `atom_id2` 命中的 connected 行做 `COUNT(*)` | 返回 6；同一 bond 两个方向都存，gold 用 `COUNT(DISTINCT bond_id)` 得 3。 |
| Round 6 | confirm_answer | 确认双向行计数 | 计数翻倍。 |""",
    "239": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要统计编号为 19 的 atom 连接数。 |
| Round 2 | explore_schema | 查看 `atom` | 知道 atom_id 形如 `TRxxx_19`。 |
| Round 3 | explore_schema | 查看 `connected` | 找到 `atom_id` 和 `atom_id2` 两列。 |
| Round 4 | explore_schema | 查询所有 `_19` atom_id | 证明匹配对象很多，但没有核查 connected 的双向含义。 |
| Round 5 | generate_sql | 同时统计 `atom_id LIKE 'TR%_19'` 或 `atom_id2 LIKE 'TR%_19'` | `connected` 已双向存储，这样把每条连接数翻倍，返回 996。 |
| Round 6 | confirm_answer | 确认双列 OR 计数 | gold 只按 `atom_id` 方向计数，结果 498。 |""",
    "243": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要找同时连接 phosphorus 和 nitrogen 的 bond_id。 |
| Round 2 | explore_schema | 查看四张表建表 SQL | 表路径是 `connected` 两端 join `atom`，再关联 `bond`。 |
| Round 3 | generate_sql | 输出 bond_id、bond_type 和两个端点元素 | 找到正确 6 个 bond，但双向记录导致 12 行，且列太多。 |
| Round 4 | generate_sql | 重复四列端点明细 | 没有去掉元素和类型列。 |
| Round 5 | generate_sql | 用 `DISTINCT` 收敛到 6 个 bond，但仍输出 `bond_type` | bond 集合正确，输出多一列。 |
| Round 6 | confirm_answer | 确认 `(bond_id, bond_type)` | gold 只要 `bond_id`。 |""",
    "244": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要 double bond 最多 molecule 的 label。 |
| Round 2 | explore_schema | 查看 `molecule` | 找到 label。 |
| Round 3 | explore_schema | 查看 `bond` | 找到 `bond_type`。 |
| Round 4 | generate_sql | 用 `b.bond_type = ' = '` 查 double bond | 因为多了空格，返回空。 |
| Round 5 | explore_schema | 查询 `bond_type` distinct 值 | 已看到真实 double bond 值是 `'='`，没有空格。 |
| Round 6 | explore_schema | 查看 `bond` 样例 | 再次显示 `=`。 |
| Round 7 | generate_sql | 仍重复 `b.bond_type = ' = '` | 继续空结果，没有吸收取值证据。 |
| Round 8 | explore_schema | 统计 `bond_type = ' = '` | 返回 0，进一步证明取值写错。 |
| Round 9 | explore_schema | 查询 molecule 总数 | 与解题无关。 |
| Round 10 | explore_schema | 查询 bond 总数 | 没有再生成修正 SQL；最终 pred 为空。 |""",
    "245": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要 iodine atom 参与的 bond 数均值。 |
| Round 2 | explore_schema | 查看 `atom` | 找到 element。 |
| Round 3 | explore_schema | 查看 `bond` | bond 表本身不含 atom 端点。 |
| Round 4 | explore_schema | 查看 `connected` | 端点和 bond_id 都在这里。 |
| Round 5 | explore_schema | 查看 iodine atom 样例 | 确认 iodine 用小写 `'i'`。 |
| Round 6 | propose_schema | 试图同时 propose schema 和生成 SQL | 解析器只接受 schema；内嵌 SQL 未执行，没得到错误反馈。 |
| Round 7 | confirm_answer | 确认含 `SELECT atom_id ... JOIN atom ... GROUP BY atom_id` 的 SQL | `connected` 和 `atom` 都有 `atom_id`，未加表别名导致离线执行报歧义列。 |""",
    "249": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要 bond_id `TR144_8_19` 两端 atom 的元素。 |
| Round 2 | explore_schema | 查看 `bond` | 找到 bond_id。 |
| Round 3 | explore_schema | 查看 `atom` | 找到 element。 |
| Round 4 | explore_schema | 查看 `connected` | 找到 bond_id 到 atom_id 的关系。 |
| Round 5 | propose_schema | 提出 schema，同时文本中给出 SQL 思路 | schema 里的 join 说明还写成 `connected.bond_id = atom.bond_id`，但最终 SQL 改用 `c.atom_id = a.atom_id`。 |
| Round 6 | confirm_answer | 确认 `SELECT DISTINCT c.atom_id, a.element ...` | 元素 h/c 正确，但 gold 只要 element；多输出 atom_id。 |""",
    "253": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要 triple bond 两端 atom 的元素。 |
| Round 2 | explore_schema | 查看 `bond` | 找到 `bond_type='#'` 所在表。 |
| Round 3 | explore_schema | 查看 `atom` | 找到 element。 |
| Round 4 | propose_schema | 只提出 `bond` + `atom` | 漏掉连接端点所必需的 `connected`。 |
| Round 5 | confirm_answer | 确认 `bond JOIN atom ON molecule_id` | 取的是含 triple bond 分子的所有 atom 元素，额外带入 `cl/h`；gold 只取 triple bond 端点元素。 |""",
    "263": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要含单键 molecule 中 chlorine atom 占比。 |
| Round 2 | explore_schema | 查看四张表建表 SQL | 知道应从 `molecule` 主表与 `bond` 定义目标 molecule 集合。 |
| Round 3 | explore_schema | 查看 `atom` | 找到 element。 |
| Round 4 | explore_schema | 查询非空 `bond_type` | 看到单键是 `'-'`。 |
| Round 5 | generate_sql | 用 `bond` 表里的 distinct molecule_id 作为目标集合 | 百分比公式对，但集合比 gold 多：没有通过 `molecule` 主表过滤，纳入只在 bond/atom 中出现的 molecule。 |
| Round 6 | confirm_answer | 确认未经过 molecule 主表限定的 SQL | pred 3.48073 与 gold 3.48237 仅因参照集合不同。 |""",
    "281": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要致癌 molecule 中第 4 个 atom 的元素分布。 |
| Round 2 | explore_schema | 查看 `molecule` | 找到 label。 |
| Round 3 | explore_schema | 查看 `atom` | 找到 atom_id 和 element。 |
| Round 4 | explore_schema | 再看 `atom` 结构 | 应注意 atom_id 后缀格式。 |
| Round 5 | explore_schema | 查看 molecule 样例 | 看到 label `+/-`。 |
| Round 6 | explore_schema | 查看 atom 样例 | 看到 `TR000_4` 这类后缀，但也存在 `TR001_14` 等会被 LIKE 误匹配。 |
| Round 7 | propose_schema | 提出 `atom` + `molecule` | 表路径正确。 |
| Round 8 | generate_sql | 用 `a.atom_id LIKE '%_4'` 过滤第 4 个 atom | SQLite 中 `_` 是通配符，误匹配 `_14/_24` 等，计数大幅膨胀。 |
| Round 9 | confirm_answer | 确认 LIKE 版本 | gold 用 `substr(atom_id, -2) = '_4'` 精确匹配。 |""",
    "282": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要 TR006 的 hydrogen 比例和 label。 |
| Round 2 | explore_schema | 查看 `molecule` | 找到 label。 |
| Round 3 | explore_schema | 查看 `atom` | 找到 element。 |
| Round 4 | propose_schema | 提出 `atom` + `molecule` | 表路径正确。 |
| Round 5 | generate_sql | 先用 `a.element='H'` 计算 | 大小写错，返回比例 0。 |
| Round 6 | explore_schema | 查看 TR006 的 atom 明细 | 看到 hydrogen 是小写 `h`。 |
| Round 7 | explore_schema | 统计 TR006 总 atom 和 hydrogen 数 | 得到 47 和 17，比例应为 17/47。 |
| Round 8 | generate_sql | 改用小写 `h`，算出正确比例 | 数值和 label 都对，但列顺序是 `(label, ratio)`。 |
| Round 9 | confirm_answer | 确认列序错误的 SQL | gold 要 `(ratio, label)`。 |""",
    "327": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询数据库表 | 需要非致癌且 atom 数大于 5 的 molecule。 |
| Round 2 | explore_schema | 查看 `molecule` | 找到 label。 |
| Round 3 | explore_schema | 查看 `atom` | 找到 `atom_id` 和 `molecule_id`。 |
| Round 4 | generate_sql | 正确筛出非致癌且 atom_count 大于 5 的 molecule | molecule 集合正确，但输出了 `label` 和 `atom_count`。 |
| Round 5 | confirm_answer | 确认三列 SQL | gold 只要 `molecule_id`。 |""",
}


def replace_table(text: str, qid: str, table: str) -> str:
    header = re.search(rf"^## qid{re.escape(qid)}\b", text, re.M)
    if not header:
        raise SystemExit(f"Missing qid section: {qid}")
    next_section = re.search(r"^## qid\d+\b|^## 错误类型归纳|^## 对后续改进", text[header.end():], re.M)
    section_end = header.end() + next_section.start() if next_section else len(text)
    section = text[header.end():section_end]
    table_start = section.find("### 运行轨迹")
    if table_start == -1:
        raise SystemExit(f"Missing trajectory table: {qid}")
    abs_start = header.end() + table_start
    after = re.search(r"\n(?=## qid\d+\b|## 错误类型归纳|## 对后续改进)", text[abs_start:], re.M)
    abs_end = abs_start + after.start() if after else section_end
    return text[:abs_start] + table.rstrip() + "\n" + text[abs_end:]


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")
    for qid, table in TABLES.items():
        text = replace_table(text, qid, table)
    TARGET.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
