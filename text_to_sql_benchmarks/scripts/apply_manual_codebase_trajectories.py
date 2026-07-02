#!/usr/bin/env python3
"""Apply hand-written, root-cause-oriented trajectory tables for codebase_community."""

from __future__ import annotations

import re
from pathlib import Path


RESULT_DIR = Path("/root/autodl-tmp/text_to_sql_benchmarks/results/qwen35-4b-arcwise-plat-trustsql-full-final-thinking")
TARGET = RESULT_DIR / "codebase_community_wrong_analysis.md"


TABLES = {
    "531": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 找到 `users` 等表，方向很快收敛到用户信息。 |
| Round 2 | explore_schema | 查看 `users` 字段 | 已看到 `DisplayName` 和 `Reputation`，具备比较两人声望的全部字段。 |
| Round 3 | generate_sql | 按 `Reputation DESC LIMIT 1` 查询两人中最高者 | 已经找到核心答案 `Harlan`，但仍输出了 `Reputation`，不是 gold 需要的单列人名。 |
| Round 4 | generate_sql | 又改成直接列出 Harlan/Jarrod Dixon 两人的 `DisplayName, Reputation` | 这一步丢掉了“谁更高”的筛选逻辑，结果变成 2 行 2 列。 |
| Round 5 | confirm_answer | 确认 Round 4 的列表 SQL | 最终错因是输出形状和筛选目标退化：应只返回 `Harlan`。 |""",
    "533": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 找到 `users` 表。 |
| Round 2 | explore_schema | 查看 `users` 字段 | 已看到 `LastAccessDate`，但没有进一步检查该字段含时间。 |
| Round 3 | generate_sql | 直接用 `LastAccessDate > '2014-09-01'` 计数 | 返回 `5146`，把 `2014-09-01 xx:xx:xx` 当天记录也算进“after 2014/9/1”。 |
| Round 4 | confirm_answer | 确认字符串比较版本 | 根因是没按 evidence 使用 `date(LastAccessDate)`；正确结果是 `4941`。 |""",
    "565": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 定位到 `comments`、`posts` 可回答问题。 |
| Round 2 | explore_schema | 查看 `comments` 字段 | 找到 `UserId`、`PostId`、`CreationDate`，可定位指定评论。 |
| Round 3 | explore_schema | 查看 `posts` 字段 | 找到 `ClosedDate`，可判断 YES/NO。 |
| Round 4 | explore_schema | 又查看 `users` 字段 | 这题不需要用户表，探索有些冗余但不影响逻辑。 |
| Round 5 | generate_sql | 用 comment 定位 post，并用 `ClosedDate IS NULL` 生成 YES/NO | 判断值 `YES` 是对的，但同时输出了 `PostId`、comment 时间、`ClosedDate` 等中间列。 |
| Round 6 | confirm_answer | 确认包含中间列的 SQL | 根因是 final shape 没收敛；gold 只要一列 `YES/NO`。 |""",
    "567": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 定位到 `users` 与 `posts`。 |
| Round 2 | explore_schema | 查看 `users` 字段 | 已看到 `Id`、`DisplayName`。 |
| Round 3 | explore_schema | 查看 `posts` 字段 | 已看到 `OwnerUserId` 和 `OwnerDisplayName` 两条可能路径。 |
| Round 4 | propose_schema | 提出 `users` + `posts` | schema 方向基本正确。 |
| Round 5 | generate_sql | 先用 `posts.OwnerDisplayName='Tiago Pasqualini'` 计数 | 返回 0，说明注册用户名不在 `OwnerDisplayName` 路径上。 |
| Round 6 | explore_schema | 去 `users.DisplayName` 验证 Tiago Pasqualini | 确认用户存在，应改走 `users.Id -> posts.OwnerUserId`。 |
| Round 7 | generate_sql | 改用 `users` join `posts` 计数 | 计数 `2` 正确，但多输出了 `u.Id=16160`。 |
| Round 8 | confirm_answer | 确认含 user id 的 SQL | 根因是修正了 join，却没有修正答案列；gold 只要 count。 |""",
    "571": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 找到 `posts`、`votes`。 |
| Round 2 | explore_schema | 查看 `posts` 字段 | 已看到 `OwnerUserId`，可数 user 24 的帖子。 |
| Round 3 | explore_schema | 查看 `users` 字段 | 对本题帮助不大，关键不是用户资料而是两个独立计数。 |
| Round 4 | explore_schema | 查看 `votes` 字段 | 已看到 `UserId`，可数 user 24 cast 的 votes。 |
| Round 5 | explore_schema | 重复查看 `votes` 字段 | 没有进一步验证 posts 数和 votes 数应分别聚合。 |
| Round 6 | propose_schema | 提出 `posts` 与 `votes` | 没有明确“先分别 count，再相除”的粒度约束。 |
| Round 7 | generate_sql | 直接 join `posts.OwnerUserId = votes.UserId` 后做 `COUNT(p)/COUNT(v)` | 对 user 24 形成 3×8 的 join 乘法，分子分母都变成 24，所以错误地得到 `1.0`。 |
| Round 8 | confirm_answer | 确认直接 join 版本 | 根因是一对多独立计数被 join 乘法污染；正确是 `3/8=0.375`。 |""",
    "581": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 定位到 `posts` 和 `users`。 |
| Round 2 | explore_schema | 查看 `posts` 建表 SQL | 已看到 `Title`、`OwnerUserId`、`OwnerDisplayName`。 |
| Round 3 | explore_schema | 查看 `users` 建表 SQL | 已看到 `users.Id` 与 `DisplayName`。 |
| Round 4 | propose_schema | 提出候选 schema | 方向应是 `posts.OwnerUserId -> users.Id`。 |
| Round 5 | generate_sql | 先直接取该 title 的 `OwnerDisplayName` | 该字段不能可靠表示注册用户作者，结果无法给出 gold 的 `Paul`。 |
| Round 6 | generate_sql | 放宽 title 搜索并查看 `OwnerUserId` | 找到目标帖子的 `OwnerUserId=87`，这是应 join users 的关键证据。 |
| Round 7 | generate_sql | join `users` 得到 `Paul` | 人名正确，但多输出了 `OwnerUserId=87`。 |
| Round 8 | confirm_answer | 确认含 `OwnerUserId` 的 SQL | 根因是最后没有做答案形状裁剪；gold 只要 `DisplayName`。 |""",
    "584": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `posts` 定位标题、`postHistory` 找 edit comments。 |
| Round 2 | explore_schema | 查看 `posts` 建表 SQL | 已看到 `Title` 和 `Id`。 |
| Round 3 | explore_schema | 查看 `comments` 建表 SQL | 这题问 edit comments，普通 `comments` 表其实不是主路径。 |
| Round 4 | explore_schema | 查看 `postHistory` 建表 SQL | 找到 `PostId`、`Comment`、`UserId`、`CreationDate`，可回答问题。 |
| Round 5 | propose_schema | 提出候选 schema | 主链路应是 `posts.Id -> postHistory.PostId`。 |
| Round 6 | explore_schema | 又查看 `users` 字段 | 引入了不必要的用户维度，埋下多输出列的风险。 |
| Round 7 | generate_sql | 查到 8 条 `postHistory.Comment`，并 join users 输出编辑者和时间 | comment 集合正确，空字符串也保留了；失败只因多输出 `DisplayName/UserId/CreationDate`。 |
| Round 8 | confirm_answer | 确认多列 SQL | 根因是输出形状错；gold 只要 `Comment` 一列。 |""",
    "586": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 相关表是 `posts`、`votes`、`users`。 |
| Round 2 | explore_schema | 查看 `posts` 字段 | 可用 `Title` 找包含 variance 的帖子，也看到 `OwnerUserId`。 |
| Round 3 | explore_schema | 查看 `users` 字段 | 可通过 `users.Id -> DisplayName` 输出用户名。 |
| Round 4 | explore_schema | 查看 `postHistory` 字段 | 与 bounty 用户无关，探索分散。 |
| Round 5 | explore_schema | 查看 `tags` 字段 | 与 bounty 用户无关。 |
| Round 6 | explore_schema | 查看 `votes` 字段 | 关键证据已经出现：`votes.UserId` 才是投票/加 bounty 的用户，`BountyAmount` 是金额。 |
| Round 7 | propose_schema | 提出候选 schema | 没有明确区分“加 bounty 的用户”与“帖子作者”。 |
| Round 8 | generate_sql | 用 `votes.PostId -> posts.Id` 找到 bounty 记录，但把 `users` join 到 `posts.OwnerUserId` | 返回 `Rok/whuber`，这是帖子作者；同一结果里 `v.UserId=930/795` 已暴露真正 bounty 用户应另 join users。 |
| Round 9 | confirm_answer | 确认 post owner 版本 | 根因是角色识别错：应 `votes.UserId -> users.Id`，不是 `posts.OwnerUserId -> users.Id`。 |""",
    "587": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `posts`、`comments`。 |
| Round 2 | explore_schema | 查看 `posts` 建表 SQL | 已看到 `Title`、`Tags`、`ViewCount`。 |
| Round 3 | explore_schema | 查看 `comments` 建表 SQL | 已看到 `PostId`、`Text`，可列评论。 |
| Round 4 | explore_schema | 查看 `tags` 建表 SQL | 该表不是本题 gold 主路径，真正标签存在 `posts.Tags` 字符串。 |
| Round 5 | explore_schema | 查看 `posts` 样例 | 应能看到 tag 是形如 `<humor>` 或多标签拼接的字符串。 |
| Round 6 | explore_schema | 查看 tag 相关样例 | 没有澄清“tagged 'humor'”在 gold 中是精确 `Tags='<humor>'`。 |
| Round 7 | explore_schema | 继续查看 `posts` 样例 | 仍未区分精确标签和包含标签。 |
| Round 8 | generate_sql | 用 `LIKE '%<humor>%'` 同时算平均值和筛评论 | 把多标签中包含 `<humor>` 的帖子也算入，返回 19 行且平均值变成 `33236.25`。 |
| Round 9 | confirm_answer | 确认包含匹配版本 | 根因是 tag 匹配口径错；gold 只要 `Tags='<humor>'` 的 9 行，平均值 `32384.5`。 |""",
    "595": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 定位到 `users` 和 `postHistory`。 |
| Round 2 | explore_schema | 查看 `users` 字段 | 已看到 `Id` 与 `Views`，满足 “at least 100 views”。 |
| Round 3 | explore_schema | 查看 `postHistory` 字段 | 已看到 `UserId` 与 `PostHistoryTypeId`，可计算 distinct type。 |
| Round 4 | explore_schema | 又查看 `postLinks` 字段 | 与本题无关，探索冗余。 |
| Round 5 | propose_schema | 提出 `users.Id = postHistory.UserId`，按用户聚合 distinct history type | 语义链路基本正确。 |
| Round 6 | generate_sql | 找到只有一种 history type 且 views>=100 的用户 | 用户集合正确，但输出了 `Id, DisplayName, Views, post_history_types` 四列。 |
| Round 7 | confirm_answer | 确认多列 SQL | 根因是输出形状错；gold 只要 `UserId` 两行。 |""",
    "634": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 找到 `posts`、`users` 等表。 |
| Round 2 | explore_schema | 查看 `posts` 和 `users` 的建表 SQL | 已经看到 `posts.OwnerUserId -> users.Id`，也看到 `users.DisplayName`。 |
| Round 3 | explore_schema | 查 `PRAGMA table_info(posts)` | 继续确认 `posts` 字段。 |
| Round 4 | propose_schema | 提出应使用 `posts` 和 `users`，按用户聚合 `ViewCount` | 这一轮思路基本正确。 |
| Round 5 | generate_sql | 生成 SQL，但用了 `posts.OwnerDisplayName` 过滤名字 | 返回空结果 `[]`。 |
| Round 6 | explore_schema | 去 `users.DisplayName` 里查 Motulsky / Snyder | 发现 `Harvey Motulsky` 和 `Noah Snyder` 都存在。 |
| Round 7 | generate_sql | 明明意识到可能需要 join users，但又重复用了 `OwnerDisplayName` | 还是空结果。 |
| Round 8 | explore_schema | 查 `posts.OwnerDisplayName` 是否有这些名字 | 仍然没有。 |
| Round 9 | explore_schema | 查看 `posts LIMIT 10` | 样例显示 `OwnerUserId` 有值，`OwnerDisplayName` 多为空。 |
| Round 10 | explore_schema | 又去查 `OwnerDisplayName LIKE ...` | 继续空结果，达到最大轮数，没有修正。 |""",
    "637": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 找到 `users`、`posts`、`tags`。 |
| Round 2 | explore_schema | 查看 `users` 字段 | 已看到 `DisplayName` 和 `Id`，这是找 Mark Meckes 的正确入口。 |
| Round 3 | explore_schema | 查看 `posts` 字段 | 已看到 `OwnerUserId`、`OwnerDisplayName`、`CommentCount`、`Tags`。 |
| Round 4 | explore_schema | 查看 `tags` 字段 | 但本题要的是 `posts.Tags`，不是 tag 字典表。 |
| Round 5 | explore_schema | 直接用 `posts.OwnerDisplayName='Mark Meckes'` 且 `CommentCount=0` 查 tags | 返回空结果，第一次暴露 OwnerDisplayName 路径不对。 |
| Round 6 | explore_schema | 查看 `posts.OwnerDisplayName` 样例 | 看到该列只有少量回填名/NULL，不适合作为注册用户主键。 |
| Round 7 | explore_schema | 列出非空 `OwnerDisplayName` | 继续在错误字段上探索，没有回到 `users.DisplayName`。 |
| Round 8 | explore_schema | 查 `OwnerDisplayName LIKE '%Meckes%'` | 仍为空，反证更强。 |
| Round 9 | explore_schema | 查看非空 `Tags` 样例 | 证明 tags 数据存在，但没有和 Mark Meckes 正确 join。 |
| Round 10 | explore_schema | 再次查 `OwnerDisplayName='Mark Meckes'` | 继续空结果，耗尽轮数；最终没有生成 SQL。 |""",
    "639": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `users` 找用户、`posts` 算比例。 |
| Round 2 | explore_schema | 查看 `posts` 字段 | 已看到 `OwnerUserId`、`OwnerDisplayName`、`Tags`。 |
| Round 3 | explore_schema | 查看 `tags` 字段 | R language 实际在 `posts.Tags LIKE '%<r>%'`，tag 表不是必要路径。 |
| Round 4 | explore_schema | 查看 `users` 字段 | 已看到 `DisplayName` 与 `Id`。 |
| Round 5 | explore_schema | 用 `users.DisplayName='user1140126'` 查 id | 找到 `Id=18164`，这是正确过滤用户的证据。 |
| Round 6 | propose_schema | 提出 `posts.OwnerUserId = users.Id` | schema 思路正确，但同时保留了危险的 `OwnerDisplayName`。 |
| Round 7 | generate_sql | 计算 `<r>` 比例时同时过滤 `OwnerUserId=18164` 和 `OwnerDisplayName='user1140126'` | 只剩下 1 条 owner display name 被填的帖子，比例变成 `100.0`。 |
| Round 8 | confirm_answer | 确认过窄过滤版本 | 根因是多加了 `OwnerDisplayName` 条件；正确应按 `users.DisplayName`/`OwnerUserId` 覆盖该用户全部 18 帖。 |""",
    "640": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 相关表是 `posts` 和 `users`。 |
| Round 2 | explore_schema | 查看 `posts` 字段 | 已看到 `ViewCount`、`OwnerUserId`、`OwnerDisplayName`。 |
| Round 3 | explore_schema | 查看 `users` 字段 | 已看到 `DisplayName`，应通过 join 找 Amos/Mornington。 |
| Round 4 | propose_schema | 提出 `posts` 和 `users`，但仍把 `OwnerDisplayName` 放进候选字段 | 正确 join 关系出现了，但后续没有真正使用。 |
| Round 5 | generate_sql | 尝试在 `OwnerDisplayName` 上同时算 Mornington/Amos 差值 | SQL 语法错误，且字段路径已经偏了。 |
| Round 6 | generate_sql | 改成在 `OwnerDisplayName` 上求两个 SUM | 返回两个 NULL，说明该字段找不到目标用户帖子。 |
| Round 7 | generate_sql | 列出 `posts.OwnerDisplayName` 样例 | 看到很多 NULL/回填名，仍没有切换到 `users` join。 |
| Round 8 | generate_sql | 继续列非空 `OwnerDisplayName` | 仍在错误字段上确认取值分布。 |
| Round 9 | generate_sql | 去 `users.DisplayName` 查 Amos/Mornington | 只查到 `Amos`，这是应改用 `users` 表的信号；Mornington 无匹配应按 0 处理。 |
| Round 10 | generate_sql | 最终只算 `OwnerDisplayName='Amos'` 的 SUM | 得到 NULL，没有计算 Mornington - Amos，也没有使用 `users` join。 |""",
    "671": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 找到 `badges` 和 `users`。 |
| Round 2 | explore_schema | 查看 `badges` 字段 | 已看到 `Name`、`Date`、`UserId`，可找 Autobiographer 最早日期。 |
| Round 3 | explore_schema | 查看 `users` 字段 | 可通过 `UserId -> users.Id` 得到 DisplayName。 |
| Round 4 | propose_schema | 提出 badge-user join | join 方向正确。 |
| Round 5 | generate_sql | 按 `b.Date ASC LIMIT 1` 取第一个 Autobiographer | 只返回 `Geoff Dalgas`，没有检查最早时间是否有并列。 |
| Round 6 | confirm_answer | 确认 `LIMIT 1` 版本 | 根因是 tie 处理错；gold 要所有 `Date = MIN(Date)` 的 12 个用户。 |""",
    "682": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `posts` 找最 valuable post，`users` 找 owner name。 |
| Round 2 | explore_schema | 查看 `posts` 字段 | 已看到拼写为 `CreaionDate`、以及 `FavoriteCount`、`OwnerUserId`、`OwnerDisplayName`。 |
| Round 3 | explore_schema | 查看 `users` 字段 | 已看到 `Id` 和 `DisplayName`。 |
| Round 4 | propose_schema | 提出候选 schema | 应走 `posts.OwnerUserId -> users.Id`。 |
| Round 5 | generate_sql | 先用正常拼写 `CreationDate` 过滤 2010 | 报 `no such column`，随后修正日期字段拼写。 |
| Round 6 | generate_sql | 改用 `CreaionDate`，按 `FavoriteCount DESC LIMIT 1` 找 post | 找到正确 `Id=1595`，但输出 `OwnerDisplayName=NULL`。 |
| Round 7 | confirm_answer | 确认 `posts.OwnerDisplayName` 版本 | 根因是 post 定位正确、owner name 字段取错；应 join `users.DisplayName` 得到 Fabian Fagerholm。 |""",
    "683": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `posts` 和 `users`。 |
| Round 2 | explore_schema | 查看 `posts` 建表 SQL | 已看到帖子创建时间列实际拼作 `CreaionDate`。 |
| Round 3 | explore_schema | 查看 `users` 建表 SQL | 也看到 `users.CreationDate`，这里埋下字段歧义。 |
| Round 4 | propose_schema | 提出 `posts.CreaionDate`、`OwnerUserId` | schema proposal 里日期字段其实是对的。 |
| Round 5 | generate_sql | 用 `YEAR(CreationDate)` 写比例 SQL | SQLite 不支持 `YEAR()`，且字段名也没限定到 `posts.CreaionDate`。 |
| Round 6 | generate_sql | 改成 `strftime('%Y', CreationDate)` 并 join users 计分母 | SQL 能跑，但 `CreationDate` 实际落到 `users.CreationDate`；分母也变成 join 后 posts，不是全部 posts。 |
| Round 7 | confirm_answer | 确认字段歧义和分母错误的 SQL | 根因是没有沿用 `posts.CreaionDate`，且分母范围应是全体 posts。 |""",
    "694": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `posts` 定位标题、`comments` 找最新评论、`users` 找评论者显示名。 |
| Round 2 | explore_schema | 查看 `posts` 建表 SQL | 已看到 `Title` 与 `Id`。 |
| Round 3 | explore_schema | 查看 `comments` 建表 SQL | 已看到 `Text`、`CreationDate`、`UserId`、`UserDisplayName`。 |
| Round 4 | propose_schema | 提出候选 schema | 没有把 `comments.UserId -> users.Id` 作为必要 join 固化下来。 |
| Round 5 | generate_sql | 按标题取最新 10 条 comment，并直接输出 `comments.UserDisplayName` | comment 文本和排序正确，但第二列全是 NULL。 |
| Round 6 | confirm_answer | 确认 `UserDisplayName` 版本 | 根因是注册用户评论者显示名取错字段；应 join `users.DisplayName`。 |""",
    "701": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 相关表是 `users` 和 `posts`。 |
| Round 2 | explore_schema | 查看 `users` 字段 | 已看到 `Reputation`，可定义 most influential user。 |
| Round 3 | explore_schema | 查看 `posts` 字段 | 已看到 `OwnerUserId` 与 `Score`。 |
| Round 4 | explore_schema | 查看 reputation 最高的用户 | 找到最高声望用户，为后续 posts 过滤提供依据。 |
| Round 5 | explore_schema | 查看该用户的 posts 样例 | 确认该用户有大量帖子，可计算 `Score > 50` 占比。 |
| Round 6 | propose_schema | 提出 `users` + `posts` 方案 | 语义基本正确。 |
| Round 7 | generate_sql | 先写 CTE/WITH 版本 | 被工具白名单拒绝，不是语义问题。 |
| Round 8 | generate_sql | 改写成普通 SELECT，计算最高声望用户 posts 中高分比例 | 结果 `0.66` 是四舍五入后的值；原始应是 `0.664451827...`。评测详情中 gold SQL 本身超时。 |
| Round 9 | confirm_answer | 确认 `ROUND(...,2)` 版本 | 根因分两层：gold 执行超时导致 EX 不可过；即使 gold 可执行，pred 也因主动 round 会精度不一致。 |""",
    "707": """### 运行轨迹

| 轮次 | 阶段 | 做了什么 | 结果/问题 |
| --- | --- | --- | --- |
| Round 1 | explore_schema | 查询所有表 | 需要 `posts` 根据 views 过滤、`comments` 按 score 排序。 |
| Round 2 | explore_schema | 查看 `posts` 字段 | 已看到 `ViewCount` 与 `Id`。 |
| Round 3 | explore_schema | 查看 `comments` 字段 | 已看到 `PostId`、`Score`、`Text`。 |
| Round 4 | generate_sql | join posts/comments，按 `Score DESC LIMIT 1` 找最高分 comment | 找到的 comment 文本正确，但同时输出 comment id、score、时间、用户、帖子标题、view count 等 8 列。 |
| Round 5 | confirm_answer | 确认多列上下文 SQL | 根因是输出形状错；gold 只要最高分 comment 的 `Text`。 |""",
}


def replace_table(section: str, table: str) -> str:
    marker = "\n### 运行轨迹\n"
    if marker not in section:
        return section.rstrip() + "\n\n" + table.rstrip() + "\n"
    return section[: section.index(marker)].rstrip() + "\n\n" + table.rstrip() + "\n"


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")
    matches = list(re.finditer(r"^## qid(\d+)\b.*$", text, re.M))
    pieces: list[str] = []
    last = 0
    changed = []
    for idx, match in enumerate(matches):
        qid = match.group(1)
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        if idx + 1 == len(matches):
            next_h = re.search(r"^##\s+", text[match.end():], re.M)
            if next_h:
                end = match.end() + next_h.start()
        pieces.append(text[last:start])
        section = text[start:end]
        if qid in TABLES:
            section = replace_table(section, TABLES[qid])
            changed.append(qid)
        pieces.append(section)
        last = end
    pieces.append(text[last:])
    TARGET.write_text("".join(pieces), encoding="utf-8")
    print(f"updated {len(changed)} qids:", ", ".join(changed))


if __name__ == "__main__":
    main()
