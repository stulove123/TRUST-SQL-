# card_games Schema Guide

本文件整理 `card_games` SQLite 数据库的表结构、字段含义、示例值和 Text-to-SQL 常见 join/过滤注意点。

- 数据库文件：`/root/autodl-tmp/DeepEye-SQL/data/arcwise_plat/dev/dev_databases/card_games/card_games.sqlite`
- 字段说明来源：`/root/autodl-tmp/text_to_sql_benchmarks/data/schemas/card_games/database_description`
- 生成时间：`2026-06-21 22:56:18`
- 生成方式：基于 SQLite schema、database_description CSV、字段样例值以及本次错题根因汇总自动生成。

## 1. 数据库概览

| 表 | 行数 | 字段数 | 作用 |
|---|---:|---:|---|
| `cards` | 56822 | 74 | 卡牌 printing 主表，一行通常是一个 uuid/printing。 |
| `foreign_data` | 229186 | 8 | 外文卡名与外文文本表。 |
| `legalities` | 427907 | 4 | 赛制合法性表。 |
| `rulings` | 87769 | 4 | 规则释疑表。 |
| `set_translations` | 1210 | 4 | 系列名称翻译表。 |
| `sets` | 551 | 21 | 卡牌系列表。 |

## 2. 表关系与 Join 注意点

### 2.1 SQLite 声明的外键

| From | To | 说明 |
|---|---|---|
| `foreign_data.uuid` | `cards.uuid` | 声明外键 |
| `legalities.uuid` | `cards.uuid` | 声明外键 |
| `rulings.uuid` | `cards.uuid` | 声明外键 |
| `set_translations.setCode` | `sets.code` | 声明外键 |


### 2.3 通用注意点

- 字段名含空格、连字符、括号或大小写敏感时，建议使用双引号，例如 `"Some Column"`。
- 表中 ID 字段通常只是连接键；最终输出是否需要 ID，要以 question/gold 语义为准，避免多输出中间列。
- 做 top/max/min/rank 查询时，先确认是否需要返回所有并列值，而不是默认 `LIMIT 1`。
- 同一 card name 可能对应多个 printing/uuid，按卡名还是按 printing 计数要看题意。
- 外文卡名/文本通常来自 `foreign_data`，不是 `set_translations`。
- `isPromo` 等布尔字段常是 0/1，输出值类型不要转成 Yes/No，除非题目明确要求。

## 3. 字段明细

### 3.1 `cards`

卡牌 printing 主表，一行通常是一个 uuid/printing。 行数：`56822`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `id` | `INTEGER` | PK, NOT NULL | 卡牌 printing的唯一标识符。 | 1, 2, 3 | 0 | range=1 - 56832 |
| `artist` | `TEXT` |  | 插画师。 | John Avon, Kev Walker, Dan Frazier | 3 |  |
| `asciiName` | `TEXT` |  | ASCII 格式卡名。 | El-Hajjaj, Ghazban Ogre, Junun Efreet | 56755 |  |
| `availability` | `TEXT` |  | 可用发行/平台类型。 | mtgo,paper, paper, arena,mtgo,paper | 1 |  |
| `borderColor` | `TEXT` |  | 边框颜色。 | black, white, gold | 0 |  |
| `cardKingdomFoilId` | `TEXT` |  | Card Kingdom 闪卡 ID。 | 110299, 110301, 110305 | 27910 |  |
| `cardKingdomId` | `TEXT` |  | Card Kingdom 平台 ID。 | 10000, 10001, 10002 | 13622 |  |
| `colorIdentity` | `TEXT` |  | 颜色标识。 | G, B, R | 6224 |  |
| `colorIndicator` | `TEXT` |  | 颜色指示。 | R, G, U | 56655 |  |
| `colors` | `TEXT` |  | 卡牌颜色。 | G, B, R | 12540 |  |
| `convertedManaCost` | `REAL` |  | 转换法术力费用。 | 3.0, 2.0, 4.0 | 0 | range=0.0 - 1000000.0 |
| `duelDeck` | `TEXT` |  | 决斗套牌标识。 | a, b | 55228 |  |
| `edhrecRank` | `INTEGER` |  | EDHREC 排名。 | 808, 17, 5084 | 4761 | range=1 - 20900 |
| `faceConvertedManaCost` | `REAL` |  | 牌面转换法术力费用。 | 2.0, 3.0, 0.0 | 55867 | range=0.0 - 7.0 |
| `faceName` | `TEXT` |  | 牌面名称。 | Fire, Ice, Nezumi Graverobber | 55455 |  |
| `flavorName` | `TEXT` |  | 风味名称。 | Anguirus, Armored Killer, Babygodzilla, Ruin Reborn, Battra, Dark Destroyer | 56801 |  |
| `flavorText` | `TEXT` |  | 风味文本。 | Without the interfering hands of civilization, nature will always shape itself to its own needs., All seeds share a common bond, calling to each other across infinity., One bone broken for every twig snapped underfoot.<br>—Llanowar penalty for trespassing | 26020 |  |
| `frameEffects` | `TEXT` |  | 牌框效果。 | legendary, extendedart, nyxtouched | 53864 |  |
| `frameVersion` | `TEXT` |  | 牌框版本。 | 2015, 2003, 1997 | 0 |  |
| `hand` | `TEXT` |  | 手牌修正值。 | 0, 1, -1 | 56704 |  |
| `hasAlternativeDeckLimit` | `INTEGER` | NOT NULL | 是否有特殊套牌数量限制。 | 0, 1 | 0 | range=0 - 1 |
| `hasContentWarning` | `INTEGER` | NOT NULL | 是否有内容警告。 | 0, 1 | 0 | range=0 - 1 |
| `hasFoil` | `INTEGER` | NOT NULL | 是否有闪卡版本。 | 1, 0 | 0 | range=0 - 1 |
| `hasNonFoil` | `INTEGER` | NOT NULL | 是否有非闪版本。 | 1, 0 | 0 | range=0 - 1 |
| `isAlternative` | `INTEGER` | NOT NULL | 是否为替代版本。 | 0, 1 | 0 | range=0 - 1 |
| `isFullArt` | `INTEGER` | NOT NULL | 是否为全画卡。 | 0, 1 | 0 | range=0 - 1 |
| `isOnlineOnly` | `INTEGER` | NOT NULL | 是否仅线上发行。 | 0, 1 | 0 | range=0 - 1 |
| `isOversized` | `INTEGER` | NOT NULL | 是否为大尺寸卡。 | 0, 1 | 0 | range=0 - 1 |
| `isPromo` | `INTEGER` | NOT NULL | 是否为促销/宣传 printing。 | 0, 1 | 0 | range=0 - 1 |
| `isReprint` | `INTEGER` | NOT NULL | 是否为再版。 | 1, 0 | 0 | range=0 - 1 |
| `isReserved` | `INTEGER` | NOT NULL | 是否在保留名单。 | 0, 1 | 0 | range=0 - 1 |
| `isStarter` | `INTEGER` | NOT NULL | 是否为 starter 产品卡。 | 0, 1 | 0 | range=0 - 1 |
| `isStorySpotlight` | `INTEGER` | NOT NULL | 是否为剧情聚焦卡。 | 0, 1 | 0 | range=0 - 1 |
| `isTextless` | `INTEGER` | NOT NULL | 是否无规则文字。 | 0, 1 | 0 | range=0 - 1 |
| `isTimeshifted` | `INTEGER` | NOT NULL | 是否为时移卡。 | 0, 1 | 0 | range=0 - 1 |
| `keywords` | `TEXT` |  | 关键词能力。 | Flying, Enchant, Trample | 36183 |  |
| `layout` | `TEXT` |  | 版式。 | normal, transform, modal_dfc | 0 |  |
| `leadershipSkills` | `TEXT` |  | 指挥官领导能力。 | {'brawl': False, 'commander': True, 'oathbreaker': False}, {'brawl': False, 'commander': False, 'oathbreaker': True}, {'brawl': True, 'commander': True, 'oathbreaker': False} | 53072 |  |
| `life` | `TEXT` |  | 生命修正值。 | -2, -3, -5 | 56704 |  |
| `loyalty` | `TEXT` |  | 忠诚值。 | 5, 4, 3 | 55992 |  |
| `manaCost` | `TEXT` |  | 法术力费用。 | {1}{W}, {1}{G}, {1}{U} | 7323 |  |
| `mcmId` | `TEXT` |  | Cardmarket 平台 ID。 | 288658, 14883, 438469 | 8024 |  |
| `mcmMetaId` | `TEXT` |  | Cardmarket 元数据 ID。 | 2177, 3743, 5739 | 17906 |  |
| `mtgArenaId` | `TEXT` |  | MTG Arena 平台 ID。 | 66003, 66109, 66143 | 50975 |  |
| `mtgjsonV4Id` | `TEXT` |  | MTGJSON v4 标识符。 | 000031ff-f095-52c5-98a1-35bdb5e18a5b, 0001fc69-3a61-51e3-aa17-19abb29803f2, 00028782-6ec2-54fe-8633-2c906d8f1076 | 0 |  |
| `mtgoFoilId` | `TEXT` |  | MTGO 闪卡 ID。 | 21206, 21212, 21214 | 32462 |  |
| `mtgoId` | `TEXT` |  | MTGO 平台 ID。 | 15023, 15025, 15027 | 24684 |  |
| `multiverseId` | `TEXT` |  | Multiverse 多元宇宙 ID。 | 479463, 74358, 476230 | 14753 |  |
| `name` | `TEXT` |  | 名称。 | Forest, Swamp, Island | 0 |  |
| `number` | `TEXT` |  | 编号。 | 1, 2, 3 | 0 |  |
| `originalReleaseDate` | `TEXT` |  | 原始发行日期。 过滤前注意实际日期格式。 | 2014/10/17, 2013/1/11, 2018/12/6 | 54757 |  |
| `originalText` | `TEXT` |  | 原始规则文本。 | G, R, B | 15616 |  |
| `originalType` | `TEXT` |  | 原始类型栏。 | Instant, Sorcery, Land | 14766 |  |
| `otherFaceIds` | `TEXT` |  | other牌面ID。 | 1b18ca2b-4e5e-54c1-bf43-1f32afa75f78, 3f8cdafb-10d5-510a-b908-49dd4c80fff3, 7c6860bb-b02a-5356-a0b9-c07ddf4dfd39 | 55455 |  |
| `power` | `TEXT` |  | 力量。 | 2, 1, 3 | 30624 |  |
| `printings` | `TEXT` |  | 出现过的系列代码。 | 10E,2ED,2XM,3ED,4BB,4ED,5ED,6ED,7ED,8ED,9ED,AKH,AKR,ALA,ANA,ANB,ARC,ATH,AVR,BBD,BFZ,BRB,BTD,C13,C14,C15,C16,C17,C18,C19,CED,CEI,CHK,CM2,CMA,CMD,CMR,CST,DD1,DDD,DDE,DDG,DDH,DDJ,D..., 10E,2ED,2XM,3ED,4BB,4ED,5ED,6ED,7ED,8ED,9ED,AKH,AKR,ALA,ANA,ANB,ARC,ATH,AVR,BBD,BFZ,BRB,BTD,C13,C14,C15,C16,C17,C18,C19,CED,CEI,CHK,CM2,CMA,CMD,CST,DDC,DDD,DDE,DDH,DDJ,DDK,DDM,D..., 10E,2ED,2XM,3ED,4BB,4ED,5ED,6ED,7ED,8ED,9ED,AKH,AKR,ALA,ANA,ANB,ARC,AVR,BBD,BFZ,BRB,BTD,C13,C14,C15,C16,C17,C18,C19,CED,CEI,CHK,CM2,CMA,CMD,CMR,CST,DD2,DDE,DDF,DDH,DDI,DDJ,DDM,D... | 0 |  |
| `promoTypes` | `TEXT` |  | 促销类型。 | mediainsert, setpromo,prerelease,datestamped, boosterfun | 50685 |  |
| `purchaseUrls` | `TEXT` |  | 购买链接。 | {'cardKingdom': 'https://mtgjson.com/links/000088042e46f4b8', 'cardKingdomFoil': 'https://mtgjson.com/links/aef77f5fc5f86cb0', 'cardmarket': 'https://mtgjson.com/links/7955e2b8e..., {'cardKingdom': 'https://mtgjson.com/links/000141e3ac01d931', 'cardmarket': 'https://mtgjson.com/links/1ed178554c32ec53', 'tcgplayer': 'https://mtgjson.com/links/b43cb2ab3cb15bd1'}, {'cardKingdom': 'https://mtgjson.com/links/000149252670828c', 'cardKingdomFoil': 'https://mtgjson.com/links/311a7d5af7ce285d', 'cardmarket': 'https://mtgjson.com/links/bfd32bc28... | 6371 |  |
| `rarity` | `TEXT` |  | 稀有度。 | common, rare, uncommon | 0 |  |
| `scryfallId` | `TEXT` |  | Scryfall 平台 ID。 | 8987644d-5a31-4a4e-9a8a-3d6260ed0fd6, fea4a077-718b-44af-87be-90df61aab643, 25d09421-08d5-4ca9-8937-5f937bc9c929 | 0 |  |
| `scryfallIllustrationId` | `TEXT` |  | Scryfall 插画 ID。 | c6230ffb-dd2c-4a2c-aeaf-13ba42c89472, 78034c44-88d3-47ab-8cc5-2c211c5ded76, 49e42a5f-3347-4aa4-a600-dad810304420 | 2 |  |
| `scryfallOracleId` | `TEXT` |  | Scryfall Oracle 规则对象 ID。 | b34bb2dc-c1af-4d77-b0b3-a0fb342a5fc6, 56719f6a-1a6c-4c0a-8d21-18f7d7350b68, b2c6aa39-2d2a-459c-a555-fb48ba993373 | 0 |  |
| `setCode` | `TEXT` |  | 系列代码。 | MB1, PRM, PSAL | 0 |  |
| `side` | `TEXT` |  | 双面/分面卡的一面。 | a, b, c | 55455 |  |
| `subtypes` | `TEXT` |  | 副类别。 | Aura, Human,Wizard, Elemental | 22228 |  |
| `supertypes` | `TEXT` |  | 超类别。 | Legendary, Basic, Snow | 48982 |  |
| `tcgplayerProductId` | `TEXT` |  | tcgplayer商品ID。 | 208535, 37950, 202685 | 6600 |  |
| `text` | `TEXT` |  | 文本。 | ({T}: Add {G}.), ({T}: Add {B}.), ({T}: Add {U}.) | 955 |  |
| `toughness` | `TEXT` |  | 防御力。 | 2, 1, 3 | 30624 |  |
| `type` | `TEXT` |  | 类型。 | Instant, Sorcery, Artifact | 0 |  |
| `types` | `TEXT` |  | 类型。 | Creature, Instant, Land | 0 |  |
| `uuid` | `TEXT` | NOT NULL | UUID 标识符。 | 00010d56-fe38-5e35-8aed-518019aa36a5, 0001e0d0-2dcd-5640-aadc-a84765cf5fc9, 0003caab-9ff5-5d1a-bc06-976dd0457f19 | 0 |  |
| `variations` | `TEXT` |  | 变体卡牌 UUID 列表。 | 1c4da28c-6a4a-569e-ad97-5f3ed5e72a9c,1e6a3596-107d-514f-81a6-eee66324224f,44c0a4f3-bf5b-55a0-927d-57ab21b0db70,8885af90-376b-5695-a494-d99c53f4289c,ffc7166b-e64a-5c1f-8871-574dc..., 96503317-76b3-5dd1-ac16-2ab17fbcdb44,d5139d56-d42f-540d-a5a7-9f6e84e0e497,985b60cd-02a9-558d-9805-830d91a800a0,5780c091-fbb9-5b20-93f8-734fca2e576c,37c5dfce-228b-59cf-a4ac-83fa3..., e17e040f-bff4-5db2-a7ba-a0a951f3b620,3daf06cd-c860-5f4e-ad9d-d9bfa10b0f5e,0e9f5c4a-d7b9-5fbf-a96c-dcd306d62c0e,de769dcb-b738-5da3-9cbf-eab89631052c,f4b5d2e8-89a7-5d02-81d9-54262... | 48186 |  |
| `watermark` | `TEXT` |  | 水印。 | mirran, phyrexian, golgari | 52373 |  |

### 3.2 `foreign_data`

外文卡名与外文文本表。 行数：`229186`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `id` | `INTEGER` | PK, NOT NULL | 外文卡牌数据的唯一标识符。 | 1, 2, 3 | 0 | range=1 - 229205 |
| `flavorText` | `TEXT` |  | 风味文本。 | , 全ての種には繋がりがあり、互いを無限の彼方から呼び合う。, 文明の手による介入がなければ、自然は必ずその必要に応じて自らを変容させる。 | 0 |  |
| `language` | `TEXT` |  | 语言。 | Japanese, French, German | 0 |  |
| `multiverseid` | `INTEGER` |  | 外文数据对应的 Multiverse 多元宇宙 ID。 | 122609, 122620, 122654 | 38418 | range=73246 - 507640 |
| `name` | `TEXT` |  | 名称。 | Pacifismo, Naturalizar, Desencantar | 0 |  |
| `text` | `TEXT` |  | 文本。 | , 飛行, Fliegend | 0 |  |
| `type` | `TEXT` |  | 类型。 | , Spontanzauber, Hexerei | 0 |  |
| `uuid` | `TEXT` | FK -> cards.uuid | UUID。 外键，指向 `cards.uuid`。 | 0003caab-9ff5-5d1a-bc06-976dd0457f19, 0004a4fb-92c6-59b2-bdbe-ceb584a9e401, 0005d268-3fd0-5424-bc6b-573ecd713aa1 | 0 |  |

### 3.3 `legalities`

赛制合法性表。 行数：`427907`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `id` | `INTEGER` | PK, NOT NULL | 赛制合法性的唯一标识符。 | 1, 2, 3 | 0 | range=1 - 427907 |
| `format` | `TEXT` |  | 赛制。 | commander, legacy, vintage | 0 |  |
| `status` | `TEXT` |  | 合法性状态。 | Legal, Banned, Restricted | 0 |  |
| `uuid` | `TEXT` | FK -> cards.uuid | UUID。 外键，指向 `cards.uuid`。 | 00c3841e-97a2-5b6c-8f8f-28dd3e399cdb, 02104a60-7d28-5e0e-afdc-d77271d8829f, 0350483c-f9ac-5692-8238-ff5e39c0c1ed | 0 |  |

### 3.4 `rulings`

规则释疑表。 行数：`87769`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `id` | `INTEGER` | PK, NOT NULL | 规则释疑的唯一标识符。 | 1, 2, 3 | 0 | range=1 - 87769 |
| `date` | `DATE` |  | 日期。 过滤前注意实际日期格式。 | 2004-10-04, 2021-02-05, 2019-10-04 | 0 |  |
| `text` | `TEXT` |  | 文本。 | Cycling is an activated ability. Effects that interact with activated abilities (such as Stifle or Rings of Brighthearth) will interact with cycling. Effects that interact with ..., If an effect copies an Adventure spell, that copy is exiled as it resolves. It ceases to exist as a state-based action; it’s not possible to cast the copy as a creature., An adventurer card is a creature card in every zone except the stack, as well as while on the stack if not cast as an Adventure. Ignore its alternative characteristics in those ... | 0 |  |
| `uuid` | `TEXT` | FK -> cards.uuid | UUID。 外键，指向 `cards.uuid`。 | 23a64ed6-aeda-5607-8cc9-35ae7ac6a0ce, 8ae00a8c-0670-5a96-9cf4-49f375a903c2, a9290322-839e-5942-a907-bbe6349cb22c | 0 |  |

### 3.5 `set_translations`

系列名称翻译表。 行数：`1210`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `id` | `INTEGER` | PK, NOT NULL | 系列翻译的唯一标识符。 | 1, 2, 3 | 0 | distinct=1210; range=1 - 1210 |
| `language` | `TEXT` |  | 语言。 | Chinese Simplified, Chinese Traditional, French | 0 | distinct=10 |
| `setCode` | `TEXT` | FK -> sets.code | 系列代码。 外键，指向 `sets.code`。 | 10E, 4ED, 5DN | 0 | distinct=121 |
| `translation` | `TEXT` |  | 翻译文本。 | Ajani vs. Nicol Bolas, Archenemy, Battle Royale | 231 | distinct=504 |

### 3.6 `sets`

卡牌系列表。 行数：`551`。

| 字段 | SQLite 类型 | 约束 | 字段含义 / 说明 | 示例值 | NULL 数 | Distinct/范围 |
|---|---|---|---|---|---:|---|
| `id` | `INTEGER` | PK, NOT NULL | 卡牌系列的唯一标识符。 | 1, 2, 3 | 0 | distinct=551; range=1 - 551 |
| `baseSetSize` | `INTEGER` |  | base系列Size。 | 5, 1, 2 | 0 | distinct=166; range=0 - 1694 |
| `block` | `TEXT` |  | 所属区块/大系列。 | Core Set, Commander, Judge Gift Cards | 279 | distinct=33 |
| `booster` | `TEXT` |  | 补充包配置。 | {'default': {'boosters': [{'contents': {'basic': 1, 'common': 10, 'rareMythic': 1, 'uncommon': 3}, 'weight': 31}, {'contents': {'basic': 1, 'common': 9, 'foil': 1, 'rareMythic':..., {'default': {'boosters': [{'contents': {'common': 11, 'rare': 1, 'uncommon': 3}, 'weight': 272757}, {'contents': {'common': 10, 'foilCommon': 1, 'rare': 1, 'uncommon': 3}, 'weig..., {'default': {'boosters': [{'contents': {'common': 11, 'rare': 1, 'uncommon': 3}, 'weight': 854667}, {'contents': {'common': 10, 'foilCommon': 1, 'rare': 1, 'uncommon': 3}, 'weig... | 413 | distinct=85 |
| `code` | `TEXT` | NOT NULL | 代码。 | 10E, 2ED, 2XM | 0 | distinct=551 |
| `isFoilOnly` | `INTEGER` | NOT NULL | 是否仅有闪卡版本。 | 0, 1 | 0 | distinct=2; range=0 - 1 |
| `isForeignOnly` | `INTEGER` | NOT NULL | is外文Only。 | 0, 1 | 0 | distinct=2; range=0 - 1 |
| `isNonFoilOnly` | `INTEGER` | NOT NULL | 是否仅有非闪版本。 | 0, 1 | 0 | distinct=2; range=0 - 1 |
| `isOnlineOnly` | `INTEGER` | NOT NULL | 是否仅线上发行。 | 0, 1 | 0 | distinct=2; range=0 - 1 |
| `isPartialPreview` | `INTEGER` | NOT NULL | 是否为部分预览系列。 | 0, 1 | 0 | distinct=2; range=0 - 1 |
| `keyruneCode` | `TEXT` |  | keyrune代码。 | PMEI, DEFAULT, DCI | 0 | distinct=249 |
| `mcmId` | `INTEGER` |  | Cardmarket 平台 ID。 | 4, 5, 7 | 350 | distinct=201; range=4 - 3660 |
| `mcmIdExtras` | `INTEGER` |  | Cardmarket 额外 ID。 | 2371, 2419, 2451 | 541 | distinct=10; range=2371 - 3680 |
| `mcmName` | `TEXT` |  | mcm名称。 | Aether Revolt, Alara Reborn, Alliances | 350 | distinct=201 |
| `mtgoCode` | `TEXT` |  | mtgo代码。 | 10E, 2XM, 5DN | 391 | distinct=160 |
| `name` | `TEXT` |  | 名称。 | 15th Anniversary Cards, 2016 Heroes of the Realm, 2017 Gift Pack | 0 | distinct=551 |
| `parentCode` | `TEXT` |  | parent代码。 | ZNR, BFZ, BNG | 397 | distinct=117 |
| `releaseDate` | `DATE` |  | release日期。 过滤前注意实际日期格式。 | 2006-01-01, 2011-01-01, 2003-01-01 | 0 | distinct=342 |
| `tcgplayerGroupId` | `INTEGER` |  | TCGplayer 分组 ID。 | 62, 33, 2359 | 291 | distinct=238; range=1 - 2778 |
| `totalSetSize` | `INTEGER` |  | total系列Size。 | 5, 1, 2 | 0 | distinct=181; range=0 - 1694 |
| `type` | `TEXT` |  | 类型。 | promo, expansion, memorabilia | 0 | distinct=20 |

## 4. 常用查询模板

### 4.1 `foreign_data` join `cards`

```sql
SELECT *
FROM "foreign_data" AS t1
JOIN "cards" AS t2
  ON t1."uuid" = t2."uuid";
```

### 4.2 `legalities` join `cards`

```sql
SELECT *
FROM "legalities" AS t1
JOIN "cards" AS t2
  ON t1."uuid" = t2."uuid";
```

### 4.3 `rulings` join `cards`

```sql
SELECT *
FROM "rulings" AS t1
JOIN "cards" AS t2
  ON t1."uuid" = t2."uuid";
```

### 4.4 `set_translations` join `sets`

```sql
SELECT *
FROM "set_translations" AS t1
JOIN "sets" AS t2
  ON t1."setCode" = t2."code";
```

## 5. Text-to-SQL 易错点

- 日期/时间相关字段：`cards.isTimeshifted`, `cards.originalReleaseDate`, `rulings.date`, `sets.releaseDate`。过滤前先查看实际字符串格式。
- 本次评测错题暴露出的典型坑：
  - qid344（协议/轮数/收敛失败）：多轮 schema exploration 没有收敛。模型未把 `cards` 和 `legalities` 的 `uuid` 关系转成最终查询，耗尽 10 轮。
  - qid347（类型/日期/NULL/值规范错误）：题目要求 “Find all cards”，即使没有 ruling 也要列出卡牌并给 `NULL` ruling；pred 用 inner join 丢掉了没有 ruling 的卡牌。
  - qid349（输出形状/答案格式错误）：- pred `ORDER BY COUNT(...) DESC LIMIT 1` 只取一个 printing，漏掉同一最大 ruling 数下另一个 `isPromo` 状态。 - pred 把 `isPromo` 从整数 0/1 转成字符串 `Yes/No`，值类型也不匹配。
  - qid352（Schema/字段/Join 选择错误）：表语义错。`set_translations` 是系列/卡包翻译，不是卡牌外文版本；应该使用 `foreign_data.language`。
  - qid368（协议/轮数/收敛失败）：计算公式基本正确，但 pred 使用 `ROUND(..., 2)` 截断精度。严格 EX 比较完整数值，`0.42` 不等于 `0.42413149836331`。
  - qid371（排序/TopK/Tie/排名错误）：- pred 仍然使用 `set_translations`，把系列翻译当成卡牌语言。 - pred 还 `GROUP BY c.id ... LIMIT 1`，得到的是某一个卡牌/系列的局部比例，不是全体 Story Spotlight 卡牌的总体比例。
  - qid383（排序/TopK/Tie/排名错误）：`legalities` 中同一张卡可在多个 format 下 banned，题目问 banned cards，应 `COUNT(DISTINCT cards.id)`；pred 用 `COUNT(*)` 统计了 format 明细行。
  - qid391（Schema/字段/Join 选择错误）：- pred join 条件写成 `c.id = fd.uuid`，但 `fd.uuid` 是文本 UUID，应使用 `c.uuid = fd.uuid`。 - pred 没有加 `c.colors = 'B'` 过滤。 - gold 要输出卡牌 `name`，pred 输出的是 `originalType/colors/language/foreign_text`。
  - qid402（聚合/公式/粒度错误）：模型把 “没有符合条件的明细行” 当成答案，但题目问 percentage。即使分子为 0，也应返回一个标量百分比 `0.0`，不是空结果集。
  - qid407（类型/日期/NULL/值规范错误）：pred 误读了 “types” 的目标字段。应从英文主表 `cards` 输出 `subtypes, supertypes`，并只用 `foreign_data` 判断是否有 German 版本；pred 直接输出德语外文 `type` 字符串。
  - qid408（聚合/公式/粒度错误）：- “ruling contains” 应查 `rulings.text`，不是 `foreign_data.text`。 - 布尔条件缺少括号，SQLite 中 `AND` 优先级高于 `OR`，导致所有 `power IS NULL` 的外文数据行都被计入。 - pred 用 `COUNT(*)`，不是去重卡牌数。
  - qid412（筛选条件/业务约束错误）：探索阶段过长，没有收敛到最终 SQL。正确路径是 `cards.uuid = foreign_data.uuid`，在 `cards` 上过滤 `types/layout/borderColor/artist`，在 `foreign_data` 上过滤 `language='French'` 并输出 `foreign_data.name`。
  - qid415（聚合/公式/粒度错误）：- pred 使用大小写错误的状态值，导致空集合。 - pred 返回的是 `COUNT(*)`，不是 `hasContentWarning = 0` 在 commander Legal 卡中的百分比。
  - qid416（聚合/公式/粒度错误）：多轮生成失败；同时 schema 选择方向也错，把 `set_translations` 当成卡牌语言数据。正确应 `cards LEFT JOIN foreign_data ON uuid`，在 `power IS NULL OR power='*'` 人群中按 `DISTINCT cards.id` 算 French 占比。
  - qid422（Schema/字段/Join 选择错误）：目标字段在 `foreign_data.multiverseid`，不是 `cards.multiverseId`。这里的 multiverse number 指外文数据行的 `multiverseid`，直接查 `foreign_data WHERE multiverseid = 149934` 即可。
  - qid440（协议/轮数/收敛失败）：`A Pedra Fellwar` 本身是外文卡名，存在于 `foreign_data.name`，不是英文主表 `cards.name`。模型把外文名错当英文卡名，导致找不到目标后耗尽轮次。
  - qid459（排序/TopK/Tie/排名错误）：pred 没有执行比较逻辑，没有 `ORDER BY convertedManaCost DESC LIMIT 1`，也额外输出了 `convertedManaCost`。
  - qid465（输出形状/答案格式错误）：集合本身正确，但输出形状错。gold 只要 set name；pred 多输出了 set code。
  - 另有 8 条错题根因，详见 `wrong_root_cause_summary_238.md`。
