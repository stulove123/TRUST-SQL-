# codebase_community Schema Guide

本文件整理 `codebase_community` SQLite 数据库的表结构、字段含义、示例值和 Text-to-SQL 常见 join/过滤注意点。

- 数据库文件：`/root/autodl-tmp/DeepEye-SQL/data/arcwise_plat/dev/dev_databases/codebase_community/codebase_community.sqlite`
- 字段说明来源：`/root/autodl-tmp/text_to_sql_benchmarks/data/schemas/codebase_community/database_description`
- 生成时间：`2026-06-21 22:56:18`
- 生成方式：基于 SQLite schema、database_description CSV、字段样例值以及本次错题根因汇总自动生成。

## 1. 数据库概览

| 表 | 行数 | 字段数 | 作用 |
|---|---:|---:|---|
| `badges` | 79851 | 4 | 徽章表。 |
| `comments` | 174285 | 7 | 评论表。 |
| `postHistory` | 303155 | 9 | 事实/明细表，通常需要 join 维表解释 ID。 |
| `postLinks` | 11102 | 5 | 事实/明细表，通常需要 join 维表解释 ID。 |
| `posts` | 91966 | 21 | 帖子/问题/回答主表。 |
| `tags` | 1032 | 5 | 事实/明细表，通常需要 join 维表解释 ID。 |
| `users` | 40325 | 14 | 用户主表。 |
| `votes` | 38930 | 6 | 投票/悬赏等行为表。 |

## 2. 表关系与 Join 注意点

### 2.1 SQLite 声明的外键

| From | To | 说明 |
|---|---|---|
| `badges.UserId` | `users.Id` | 声明外键 |
| `comments.UserId` | `users.Id` | 声明外键 |
| `comments.PostId` | `posts.Id` | 声明外键 |
| `postHistory.UserId` | `users.Id` | 声明外键 |
| `postHistory.PostId` | `posts.Id` | 声明外键 |
| `postLinks.RelatedPostId` | `posts.Id` | 声明外键 |
| `postLinks.PostId` | `posts.Id` | 声明外键 |
| `posts.ParentId` | `posts.Id` | 声明外键 |
| `posts.OwnerUserId` | `users.Id` | 声明外键 |
| `posts.LastEditorUserId` | `users.Id` | 声明外键 |
| `tags.ExcerptPostId` | `posts.Id` | 声明外键 |
| `votes.UserId` | `users.Id` | 声明外键 |
| `votes.PostId` | `posts.Id` | 声明外键 |


### 2.3 通用注意点

- 字段名含空格、连字符、括号或大小写敏感时，建议使用双引号，例如 `"Some Column"`。
- 表中 ID 字段通常只是连接键；最终输出是否需要 ID，要以 question/gold 语义为准，避免多输出中间列。
- 做 top/max/min/rank 查询时，先确认是否需要返回所有并列值，而不是默认 `LIMIT 1`。
- `posts.OwnerDisplayName`、`comments.UserDisplayName` 可能为空；注册用户通常通过 `OwnerUserId/UserId -> users.Id` 取 `users.DisplayName`。
- 日期字段含时间，按自然日过滤时用 `date(...)` 或 `LIKE 'YYYY-MM-DD%'`。
- `posts` 的创建时间列在该库中可能拼写为 `CreaionDate`。

## 3. 字段明细

### 3.1 `badges`

徽章表。 行数：`79851`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `Id` | `INTEGER` | PK, NOT NULL | 徽章的唯一标识符。 | 1, 2, 3 | 0 | range=1 - 92240 |
| `UserId` | `INTEGER` | FK -> users.Id | 用户 ID。 外键，指向 `users.Id`。 | 919, 805, 930 | 0 | range=2 - 55746 |
| `Name` | `TEXT` |  | 名称。 | Student, Supporter, Editor | 0 |  |
| `Date` | `DATETIME` |  | 日期。 过滤前注意实际日期格式。 | 2014-07-02 16:05:34.0, 2012-06-08 23:00:52.0, 2012-09-21 23:23:23.0 | 0 |  |

### 3.2 `comments`

评论表。 行数：`174285`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `Id` | `INTEGER` | PK, NOT NULL | 评论的唯一标识符。 | 1, 2, 3 | 0 | range=1 - 221292 |
| `PostId` | `INTEGER` | FK -> posts.Id | 帖子 ID。 外键，指向 `posts.Id`。 | 31038, 2365, 92246 | 0 | range=1 - 115376 |
| `Score` | `INTEGER` |  | 得分。 | 0, 1, 2 | 0 | range=0 - 90 |
| `Text` | `TEXT` |  | 文本。 | Thank you very much!, While this link may answer the question, it is better to include the essential parts of the answer here and provide the link for reference. Link-only answers can become invalid ..., Velcome to the site! | 0 |  |
| `CreationDate` | `DATETIME` |  | 创建时间。 过滤前注意实际日期格式。 | 2010-10-10 08:23:43.0, 2010-10-21 13:02:54.0, 2010-11-09 21:52:12.0 | 0 |  |
| `UserId` | `INTEGER` | FK -> users.Id | 用户 ID。 外键，指向 `users.Id`。 | 919, 805, 7290 | 2835 | range=3 - 55746 |
| `UserDisplayName` | `TEXT` |  | 评论用户显示名。 | user10525, user28, user25658 | 171454 |  |

### 3.3 `postHistory`

事实/明细表，通常需要 join 维表解释 ID。 行数：`303155`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `Id` | `INTEGER` | PK, NOT NULL | 帖子历史的唯一标识符。 | 1, 2, 3 | 0 | range=1 - 386848 |
| `PostHistoryTypeId` | `INTEGER` |  | 帖子History类型ID。 | 2, 5, 3 | 0 | range=1 - 38 |
| `PostId` | `INTEGER` | FK -> posts.Id | 帖子 ID。 外键，指向 `posts.Id`。 | 12670, 64147, 87242 | 0 | range=1 - 115378 |
| `RevisionGUID` | `TEXT` |  | 修订记录 GUID。 | 00000000-0000-0000-0000-000000000000, 6887d756-76f7-4279-bd02-adccbc90ac17, 49d80dfa-80ed-46f8-8352-0c96493db975 | 0 |  |
| `CreationDate` | `DATETIME` |  | 创建时间。 过滤前注意实际日期格式。 | 2012-02-22 19:46:04.0, 2012-02-22 19:46:03.0, 2012-02-22 19:46:05.0 | 0 |  |
| `UserId` | `INTEGER` | FK -> users.Id | 用户 ID。 外键，指向 `users.Id`。 | 7290, 919, 805 | 21326 | range=-1 - 55746 |
| `Text` | `TEXT` |  | 文本。 | , <regression>, <r> | 0 |  |
| `Comment` | `TEXT` |  | 编辑备注。 | , edited title, edited tags | 0 |  |
| `UserDisplayName` | `TEXT` |  | 评论用户显示名。 | , user10525, user28 | 0 |  |

### 3.4 `postLinks`

事实/明细表，通常需要 join 维表解释 ID。 行数：`11102`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `Id` | `INTEGER` | PK, NOT NULL | 帖子链接的唯一标识符。 | 108, 145, 217 | 0 | distinct=11102; range=108 - 3356789 |
| `CreationDate` | `DATETIME` |  | 创建时间。 过滤前注意实际日期格式。 | 2013-02-18 03:03:17.0, 2014-03-25 20:34:26.0, 2014-02-28 22:31:57.0 | 0 | distinct=9450 |
| `PostId` | `INTEGER` | FK -> posts.Id | 帖子 ID。 外键，指向 `posts.Id`。 | 91253, 88290, 54724 | 0 | distinct=7604; range=4 - 115360 |
| `RelatedPostId` | `INTEGER` | FK -> posts.Id | 相关帖子 ID。 外键，指向 `posts.Id`。 | 2492, 20836, 20523 | 0 | distinct=5177; range=1 - 115163 |
| `LinkTypeId` | `INTEGER` |  | Link类型ID。 | 1, 3 | 0 | distinct=2; range=1 - 3 |

### 3.5 `posts`

帖子/问题/回答主表。 行数：`91966`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `Id` | `INTEGER` | PK, NOT NULL | 帖子的唯一标识符。 | 1, 2, 3 | 0 | range=1 - 115378 |
| `PostTypeId` | `INTEGER` |  | 帖子类型 ID。 | 2, 1, 5 | 0 | range=1 - 7 |
| `AcceptedAnswerId` | `INTEGER` |  | Accepted回答ID。 | 5, 15, 18 | 77269 | range=5 - 115345 |
| `CreaionDate` | `DATETIME` |  | 创建时间。 过滤前注意实际日期格式。 | 2013-08-11 17:01:04.0, 2010-07-19 19:28:12.0, 2010-07-19 19:43:20.0 | 0 |  |
| `Score` | `INTEGER` |  | 得分。 | 1, 0, 2 | 0 | range=-19 - 192 |
| `ViewCount` | `INTEGER` |  | 浏览次数。 | 31, 38, 27 | 49054 | range=1 - 175495 |
| `Body` | `TEXT` |  | 正文。 | <p><a href="http://en.wikipedia.org/wiki/Proportional_hazards_models" rel="nofollow">Cox proportional hazards regression</a> is a very popular, semi-parametric method for surviv..., <p><a href="http://www.math.umass.edu/~lavine/Book/book.html">Introduction to Statistical Thought</a></p><br>, <p>Actually, <strong>frequent itemset mining</strong> may be a better choice than clustering on such data.</p><br><br><p>The usual vector-oriented set of algorithms does not mak... | 220 |  |
| `OwnerUserId` | `INTEGER` | FK -> users.Id | 帖子作者用户 ID。 外键，指向 `users.Id`。 | 805, 686, 919 | 1392 | range=-1 - 55746 |
| `LasActivityDate` | `DATETIME` |  | Las活动日期。 过滤前注意实际日期格式。 | 2011-01-03 11:13:42.0, 2014-08-26 14:01:02.0, 2011-07-22 15:30:25.0 | 0 |  |
| `Title` | `TEXT` |  | 标题。 | A reliable measure of series similarity - correlation just doesn't cut it for me, Algorithm for rating books: Relative perception, Anomaly/outlier detection using fuzzy clustering | 49054 |  |
| `Tags` | `TEXT` |  | 帖子标签文本。 | <regression>, <r>, <probability> | 49054 |  |
| `AnswerCount` | `INTEGER` |  | 回答数。 | 1, 0, 2 | 49054 | range=0 - 136 |
| `CommentCount` | `INTEGER` |  | 评论数。 | 0, 1, 2 | 0 | range=0 - 45 |
| `FavoriteCount` | `INTEGER` |  | 收藏数。 | 1, 2, 3 | 78723 | range=0 - 233 |
| `LastEditorUserId` | `INTEGER` | FK -> users.Id | 最后编辑者用户 ID。 外键，指向 `users.Id`。 | 7290, 88, 805 | 47361 | range=-1 - 55733 |
| `LastEditDate` | `DATETIME` |  | 最后编辑时间。 过滤前注意实际日期格式。 | 2014-04-23 13:43:43.0, 2010-10-28 07:46:12.0, 2011-03-11 19:34:18.0 | 46934 |  |
| `CommunityOwnedDate` | `DATETIME` |  | CommunityOwned日期。 过滤前注意实际日期格式。 | 2010-08-01 18:56:25.0, 2010-08-16 13:01:42.0, 2011-06-01 03:42:00.0 | 89499 |  |
| `ParentId` | `INTEGER` | FK -> posts.Id | ParentID。 外键，指向 `posts.Id`。 | 726, 1337, 423 | 44211 | range=1 - 115375 |
| `ClosedDate` | `DATETIME` |  | 关闭时间。 过滤前注意实际日期格式。 | 2010-07-19 20:19:46.0, 2010-07-20 00:21:48.0, 2010-07-29 12:38:50.0 | 90356 |  |
| `OwnerDisplayName` | `TEXT` |  | 帖子作者显示名。 | user28, user25658, user5644 | 89457 |  |
| `LastEditorDisplayName` | `TEXT` |  | 最后Editor显示名称。 | user10525, user28, user5644 | 91501 |  |

### 3.6 `tags`

事实/明细表，通常需要 join 维表解释 ID。 行数：`1032`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `Id` | `INTEGER` | PK, NOT NULL | 标签的唯一标识符。 | 1, 2, 3 | 0 | distinct=1032; range=1 - 1869 |
| `TagName` | `TEXT` |  | 标签名。 | 2sls, ab-test, abc | 0 | distinct=1032 |
| `Count` | `INTEGER` |  | 计数。 | 1, 2, 3 | 0 | distinct=272; range=1 - 7244 |
| `ExcerptPostId` | `INTEGER` | FK -> posts.Id | Excerpt帖子ID。 外键，指向 `posts.Id`。 | 2331, 2417, 2601 | 436 | distinct=596; range=2331 - 114058 |
| `WikiPostId` | `INTEGER` |  | Wiki帖子ID。 | 2254, 2416, 2600 | 436 | distinct=596; range=2254 - 114057 |

### 3.7 `users`

用户主表。 行数：`40325`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `Id` | `INTEGER` | PK, NOT NULL | 用户的唯一标识符。 | -1, 2, 3 | 0 | distinct=40325; range=-1 - 55747 |
| `Reputation` | `INTEGER` |  | 声望值。 | 1, 101, 6 | 0 | distinct=965; range=1 - 87393 |
| `CreationDate` | `DATETIME` |  | 创建时间。 过滤前注意实际日期格式。 | 2010-07-19 19:09:32.0, 2010-07-19 19:13:09.0, 2011-09-12 00:37:36.0 | 0 | distinct=40315 |
| `DisplayName` | `TEXT` |  | 用户显示名。 | Chris, John, Alex | 0 | distinct=35644 |
| `LastAccessDate` | `DATETIME` |  | 最后访问时间。 过滤前注意实际日期格式。 | 2014-09-08 15:53:04.0, 2012-11-09 00:37:43.0, 2013-07-24 21:40:07.0 | 0 | distinct=40287 |
| `WebsiteUrl` | `TEXT` |  | 个人网站 URL。 | http://none, http://www.google.com, http://None | 32204 | distinct=7787 |
| `Location` | `TEXT` |  | 地点。 | United States, London, United Kingdom, Germany | 28634 | distinct=2464 |
| `AboutMe` | `TEXT` |  | 用户自我介绍。 | <p></p><br>, <p>please delete me</p><br>, <p>merge keep</p><br> | 30946 | distinct=9140 |
| `Views` | `INTEGER` |  | 浏览次数。 | 0, 1, 2 | 0 | distinct=362; range=0 - 20932 |
| `UpVotes` | `INTEGER` |  | 进攻Votes。 | 0, 1, 2 | 0 | distinct=332; range=0 - 11442 |
| `DownVotes` | `INTEGER` |  | 反对票数量。 | 0, 1, 2 | 0 | distinct=76; range=0 - 1920 |
| `AccountId` | `INTEGER` |  | 账户ID。 | -1, 1, 2 | 0 | distinct=40325; range=-1 - 5027354 |
| `Age` | `INTEGER` |  | 年龄。 | 28, 27, 29 | 32007 | distinct=70; range=13 - 94 |
| `ProfileImageUrl` | `TEXT` |  | 头像图片 URL。 | https://www.gravatar.com/avatar/?s=128&d=identicon&r=PG&f=1, https://lh3.googleusercontent.com/-XdUIqdMkCWA/AAAAAAAAAAI/AAAAAAAAAAA/4252rscbv5M/photo.jpg, https://lh3.googleusercontent.com/-XdUIqdMkCWA/AAAAAAAAAAI/AAAAAAAAAAA/4252rscbv5M/photo.jpg?sz=128 | 23846 | distinct=13115 |

### 3.8 `votes`

投票/悬赏等行为表。 行数：`38930`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `Id` | `INTEGER` | PK, NOT NULL | 投票的唯一标识符。 | 1, 2, 3 | 0 | distinct=38930; range=1 - 43538 |
| `PostId` | `INTEGER` | FK -> posts.Id | 帖子 ID。 外键，指向 `posts.Id`。 | 7224, 726, 730 | 0 | distinct=8584; range=1 - 16921 |
| `VoteTypeId` | `INTEGER` |  | 投票类型 ID。 | 2, 5, 1 | 0 | distinct=10; range=1 - 16 |
| `CreationDate` | `DATE` |  | 创建时间。 过滤前注意实际日期格式。 | 2010-07-20, 2010-07-27, 2010-07-19 | 0 | distinct=287 |
| `UserId` | `INTEGER` | FK -> users.Id | 用户 ID。 外键，指向 `users.Id`。 | 253, 3911, 71 | 35505 | distinct=509; range=5 - 11954 |
| `BountyAmount` | `INTEGER` |  | 悬赏金额。 | 50, 100, 25 | 38829 | distinct=6; range=0 - 200 |

## 4. 常用查询模板

### 4.1 `badges` join `users`

```sql
SELECT *
FROM "badges" AS t1
JOIN "users" AS t2
  ON t1."UserId" = t2."Id";
```

### 4.2 `comments` join `users`

```sql
SELECT *
FROM "comments" AS t1
JOIN "users" AS t2
  ON t1."UserId" = t2."Id";
```

### 4.3 `comments` join `posts`

```sql
SELECT *
FROM "comments" AS t1
JOIN "posts" AS t2
  ON t1."PostId" = t2."Id";
```

### 4.4 `postHistory` join `users`

```sql
SELECT *
FROM "postHistory" AS t1
JOIN "users" AS t2
  ON t1."UserId" = t2."Id";
```

### 4.5 `postHistory` join `posts`

```sql
SELECT *
FROM "postHistory" AS t1
JOIN "posts" AS t2
  ON t1."PostId" = t2."Id";
```

### 4.6 `postLinks` join `posts`

```sql
SELECT *
FROM "postLinks" AS t1
JOIN "posts" AS t2
  ON t1."RelatedPostId" = t2."Id";
```

### 4.7 `postLinks` join `posts`

```sql
SELECT *
FROM "postLinks" AS t1
JOIN "posts" AS t2
  ON t1."PostId" = t2."Id";
```

### 4.8 `posts` join `posts`

```sql
SELECT *
FROM "posts" AS t1
JOIN "posts" AS t2
  ON t1."ParentId" = t2."Id";
```

## 5. Text-to-SQL 易错点

- 日期/时间相关字段：`badges.Date`, `comments.CreationDate`, `postHistory.CreationDate`, `postLinks.CreationDate`, `posts.CreaionDate`, `posts.LasActivityDate`, `posts.LastEditDate`, `posts.CommunityOwnedDate`, `posts.ClosedDate`, `users.CreationDate`, `users.LastAccessDate`, `votes.CreationDate`。过滤前先查看实际字符串格式。
- 本次评测错题暴露出的典型坑：
  - qid531（输出形状/答案格式错误）：pred 只列出两人的 reputation，没有做 `MAX(Reputation)` 筛选；同时多输出了 `Reputation`。正确应只输出 reputation 更高者的 `DisplayName`。
  - qid533（类型/日期/NULL/值规范错误）：pred 没有按 evidence 使用 `date(LastAccessDate)`，把 2014-09-01 当天但带时间的访问也算进去了。
  - qid565（输出形状/答案格式错误）：判断逻辑正确，但输出形状错。gold 只要 `YES/NO` 一列；pred 多输出了 post id、comment date 和 closed date。
  - qid567（输出形状/答案格式错误）：计数正确，但输出形状错。gold 只要 count；pred 多输出了 user id。
  - qid571（聚合/公式/粒度错误）：两个独立计数被错误 join，产生笛卡尔乘法。应分别聚合 posts 和 votes，再相除。
  - qid581（输出形状/答案格式错误）：owner 定位正确，但输出形状错。gold 只要 `DisplayName`；pred 多输出了 `OwnerUserId`。
  - qid584（输出形状/答案格式错误）：核心 comment 集合正确，`Comment IS NOT NULL` 没有排掉空字符串；失败来自输出形状，pred 多输出了编辑用户和时间。
  - qid586（Schema/字段/Join 选择错误）：pred 把“添加 bounty 的用户”错当成“post owner”，join 到 `posts.OwnerUserId`；正确应使用 `votes.UserId -> users.Id`。
  - qid587（输出形状/答案格式错误）：tag 匹配口径错。题目/gold 是只要 tag 字符串等于 `<humor>` 的帖子；pred 做了包含匹配，扩大了帖子和评论集合。
  - qid595（输出形状/答案格式错误）：用户集合正确，但输出形状错。gold 只要 `UserId`；pred 多输出了 display name、views 和 distinct post history type count。
  - qid634（筛选条件/业务约束错误）：pred 错用 `posts.OwnerDisplayName` 过滤作者，导致找不到 Harvey Motulsky / Noah Snyder 的帖子。
  - qid637（协议/轮数/收敛失败）：同 q634，作者显示名字段位置错。模型没有改用 `users` join，探索耗尽 10 轮。
  - qid639（Schema/字段/Join 选择错误）：pred 同时过滤 `OwnerUserId=18164` 和 `OwnerDisplayName='user1140126'`，只保留了一个 owner display name 被填充的 post；应 join `users` 并仅按 `users.DisplayName` 过滤。
  - qid640（聚合/公式/粒度错误）：pred 错用 `posts.OwnerDisplayName='Amos'`，该字段为空导致 SUM over empty set 为 NULL；同时没有计算 Mornington - Amos 的差值。
  - qid671（排序/TopK/Tie/排名错误）：tie 处理错误。pred `ORDER BY b.Date ASC LIMIT 1` 只取一人；gold 要所有 `b.Date = MIN(Date)` 的用户。
  - qid682（Schema/字段/Join 选择错误）：post id 定位正确，但 owner display name 取错字段。注册用户应 join `users`，不能直接用 `posts.OwnerDisplayName`。
  - qid683（聚合/公式/粒度错误）：- 字段名错：posts 表创建时间列拼作 `CreaionDate`，pred 使用 `CreationDate`，SQLite 解析到了 `users.CreationDate`。 - 分母错：gold 分母是全部 posts，pred join users 后的 `COUNT(*)` 排除了没有 owner user 的 posts。
  - qid694（Schema/字段/Join 选择错误）：评论文本和排序正确，但 commenter display name 取错字段。注册用户的显示名应 `comments.UserId -> users.Id`，不是 `comments.UserDisplayName`。
  - 另有 2 条错题根因，详见 `wrong_root_cause_summary_238.md`。
