# TRUST-SQL 源码导读

本文是给刚接触本仓库时用的源码地图，目标不是逐行解释 Slime，而是把论文
`TRUST-SQL: Tool-Integrated Multi-Turn Reinforcement Learning for Text-to-SQL over Unknown Schemas`
里的核心概念，映射到当前仓库的具体入口、函数和可改造位置。

参考来源：

- 论文 arXiv: https://arxiv.org/abs/2603.16448
- 论文 HTML 版: https://arxiv.org/html/2603.16448v1
- 本地源码根目录: `TrustSQL/`

## 1. 先抓住项目主线

这份代码可以理解成两层：

1. `examples/nl2sql/` 是 TRUST-SQL 的任务实现层，负责 Text-to-SQL 的多轮工具交互、SQL 执行、schema reward、final execution reward。
2. `slime/` 是通用 RL 训练框架层，负责 rollout 调度、Ray/SGLang 服务、Megatron/FSDP 训练、GRPO/PPO/GSPO loss、checkpoint 和日志。

论文里的主张是：unknown schema 场景下，不把完整 schema 预先塞进上下文，而是让 agent 通过工具查询数据库；交互被约束成四阶段协议：

1. `explore_schema`: 查询数据库元信息。
2. `propose_schema`: 显式提交已经验证过的相关表和列。
3. `generate_sql`: 基于提交的 schema 生成并执行候选 SQL。
4. `confirm_answer`: 输出最终 SQL。

源码里最重要的一句话是：

> `examples/nl2sql/generate_sql_token.py` 负责生成多轮轨迹和稀疏 token-level reward；`slime/backends/megatron_utils/loss.py` 负责把这些 reward 按 `schema_end_position` 转成 Dual-Track/segmented GRPO 的 advantage 和 policy loss。

## 2. 论文概念到源码位置

| 论文概念 | 源码位置 | 你应该关注什么 |
|---|---|---|
| Unknown Schema | `data_for_sql/filtered_questions.jsonl`, `examples/nl2sql/generate_sql_token.py` | prompt 只给问题、db_id、外部知识和工具；完整 ground-truth schema 只放在 `reward_model` 里做训练监督 |
| 四阶段协议 | `generate_sql_token.py:postprocess_predictions`, `execute_predictions`, `generate` | 解析 `<action>`、`<tool_call>`、`<schema>`、`<answer>` 并推动多轮循环 |
| Explore Schema | `execute_predictions()` | 对 `explore_schema` 的 SQL tool call 做 SQLite 执行并返回 observation |
| Propose Schema | `execute_predictions()`, `generate()` | 解析 `<schema>`，缓存到 `sample.cached_schema_json`，记录 `sample.schema_end_position` |
| Generate SQL | `execute_predictions()` | 对 `generate_sql` 的候选 SQL 执行，返回数据库反馈 |
| Confirm Answer | `sql_reward_with_schema.py:extract_final_answer_sql` | 从最后的 `<answer>` 中抽取最终 SQL，用于 execution reward |
| Format reward | `sql_reward_with_schema.py:check_single_turn_format`, `generate_sql_token.py:compute_turn_level_format_scores` | 检查每轮是否包含合法 `<think>`、`<action>` 和对应内容标签 |
| Schema exploration reward | `sql_reward_with_schema.py:compute_schema_linking_score`, `generate_sql_token.py:_compute_schema_reward_async` | 比较 proposed schema 和 label schema，支持 `f1/precision/recall/totalmatch/recall_then_precision*` |
| Final execution reward | `sql_reward_with_schema.py:compute_score_sql_async` | 执行预测 SQL 和 gold SQL，比较结果集 |
| Dual-Track GRPO | `slime/backends/megatron_utils/loss.py` | 根据 `schema_end_positions` 构造 schema advantage、answer advantage、schema-only mask 和 full-response mask |
| SFT warm-up | `slime/rollout/sft_rollout.py`, `slime/backends/megatron_utils/loss.py:sft_loss_function`, `scripts/run-qwen3-4B-base-sft.sh` | 本仓库提供 Slime 通用 SFT 入口；NL2SQL 专用 SFT 数据生成脚本没有展开在 `examples/nl2sql` 中 |

## 3. 目录结构怎么读

优先读这些：

```text
TrustSQL/
├── README.md
├── submit_training.sh
├── examples/nl2sql/
│   ├── generate_sql_token.py
│   ├── sql_reward_with_schema.py
│   ├── run_qwen3_unified.sh
│   └── run_qwen3_async_oversampling.sh
├── data_for_sql/
│   └── filtered_questions.jsonl
├── slime/
│   ├── rollout/
│   ├── ray/
│   ├── utils/
│   └── backends/megatron_utils/
└── trustsql_eval/
```

各部分职责：

- `examples/nl2sql/generate_sql_token.py`: 任务核心。多轮 rollout、工具执行、格式分、schema reward 位置、SQL reward 位置都在这里。
- `examples/nl2sql/sql_reward_with_schema.py`: reward 后端。负责 schema matching、format check、SQL 安全执行和 execution accuracy。
- `examples/nl2sql/run_qwen3_unified.sh`: 同步训练启动脚本。把 NL2SQL 的自定义 `generate` 和 `reward_func` 注入 Slime。
- `examples/nl2sql/run_qwen3_async_oversampling.sh`: async/oversampling 版本，适合论文里 8B async 设置。
- `submit_training.sh`: 更上层的作业配置模板，设置模型、batch、rollout、schema mode、reward mode。
- `slime/ray/rollout.py`: RolloutManager。负责取样、调用 rollout、调用 reward、把 `Sample` 转成训练 batch。
- `slime/backends/megatron_utils/loss.py`: RL loss 和 advantage 主入口。后续做 Dual-Track GRPO 改法，基本绕不开这里。
- `slime/rollout/sft_rollout.py`: SFT 阶段的通用 rollout，直接从文件读取 message 并构造 loss mask。
- `trustsql_eval/`: 离线推理/评测 agent runner，和训练 rollout 思路相似，但不是训练主路径。

## 4. 数据格式和 unknown schema 的含义

训练样例在 `data_for_sql/filtered_questions.jsonl`。一行大致包含：

```json
{
  "id": 0,
  "question": "...",
  "prompt": [
    {"role": "system", "content": "... four-phase protocol ..."},
    {"role": "user", "content": "... Database: movie_platform ... User Question ..."}
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "execute_sql_query",
        "parameters": {
          "required": ["db_id", "sql"]
        }
      }
    }
  ],
  "reward_model": {
    "ground_truth": {
      "target": ["SELECT ..."],
      "schema": {
        "tables": ["..."],
        "columns": {"table": ["col"]}
      }
    },
    "data_source": "db_id",
    "database": "/path/to/databases"
  }
}
```

关键点：

- agent 的输入 prompt 不应该包含完整数据库 schema。
- `reward_model.ground_truth.schema` 是隐藏标签，只用于训练时评估 `propose_schema`，不是给模型看的 schema prefill。
- `reward_model.ground_truth.target` 是 gold SQL，用于 execution reward。
- `reward_model.data_source` 是 `db_id`。
- `reward_model.database` 是 SQLite 数据库根路径。

注意一个工程细节：`run_qwen3_unified.sh` 中开启了 `--apply-chat-template`，而 `generate_sql_token.generate()` 内部又会用 tokenizer 对 `sample.prompt` 包一层 chat template。你后续换数据模板时，建议先 dump 一条 `sample.prompt` 和真正发给 SGLang 的 `current_prompt_str`，确认没有重复模板或 role 嵌套问题。

## 5. 单样本从问题到 SQL 的完整执行链路

入口来自训练脚本：

```text
submit_training.sh
  -> examples/nl2sql/run_qwen3_unified.sh 或 run_qwen3_async_oversampling.sh
  -> train.py 或 train_async.py
  -> slime.ray.rollout.RolloutManager.generate()
  -> custom generate: examples.nl2sql.generate_sql_token.generate
  -> custom reward: examples.nl2sql.generate_sql_token.reward_func
```

具体到一个样本：

1. `slime/utils/data.py:Dataset` 读取 JSONL/parquet。
2. `slime/ray/rollout_data_source.py:RolloutDataSource.get_samples()` 按 `n_samples_per_prompt` 复制同一个 prompt，形成 GRPO group。
3. `RolloutManager._get_rollout_data()` 调用 `call_rollout_fn()`。
4. `slime/rollout/sglang_rollout.py:generate_and_rm()` 检查是否配置了 `--custom-generate-function-path`。
5. 训练脚本设置为 `generate_sql_token.generate`，所以进入 NL2SQL 自定义多轮逻辑。
6. `generate()` 初始化 `messages = [{"role": "user", "content": sample.prompt}]`，用 tokenizer 的 chat template 得到第一轮 prompt tokens。
7. 每一轮向 SGLang router 的 `/generate` 发请求，得到 assistant 文本和 token logprobs。
8. `postprocess_predictions()` 解析动作：
   - `<action>explore_schema</action>` + `<tool_call>` -> 执行 SQL，返回 observation。
   - `<action>propose_schema</action>` + `<schema>` -> 缓存 schema JSON，返回 schema acknowledged。
   - `<action>generate_sql</action>` + `<tool_call>` -> 执行候选 SQL，返回 observation。
   - `<action>confirm_answer</action>` + `<answer>` -> episode 结束。
9. 工具返回会被追加到上下文里继续下一轮。训练 rollout 中工具消息 role 是 `tool`。
10. 工具 observation 对应的 token 会加入 `sample.tokens`，但 `sample.loss_mask` 中置为 0；模型自己生成的 assistant token 置为 1。
11. 如果检测到 `<schema>`，`generate()` 记录：
    - `sample.schema_end_position`
    - `sample.schema_response_length`
    - `sample.cached_schema_json`
    - `sample.is_dummy_schema`
12. episode 结束后，`compute_turn_level_format_scores()` 计算每轮格式分和整体格式分。
13. `reward_func()` 抽取 final SQL、计算 SQL execution reward、schema reward，并写成稀疏 token-level reward。

这里最值得记住的字段：

| 字段 | 产生位置 | 用途 |
|---|---|---|
| `sample.tokens` | `generate()` | prompt + response + tool observation 的完整 token 序列 |
| `sample.response_length` | `generate()` | response 区间长度，用于训练时切出 response tokens |
| `sample.loss_mask` | `generate()` | 1 表示 assistant 输出，0 表示 tool observation |
| `sample.response` | `generate()` | 拼接后的可读轨迹文本 |
| `sample.turn_boundaries` | `generate()` | 每个 assistant turn 在 response 区间的起止 |
| `sample.cached_schema_json` | `generate()` | 最近一次 `propose_schema` 的 JSON |
| `sample.schema_end_position` | `generate()` | Propose 阶段结束位置，也是 Dual-Track 的切分点 |
| `sample.reward` | `reward_func()` | scalar reward 或 token-level reward list |
| `sample.sql_reward` | `reward_func()` | SQL reward + format reward，便于日志 |
| `sample.schema_reward` | `_compute_schema_reward_async()` | schema linking reward，便于日志 |

## 6. 四阶段协议在代码里怎么落地

### 6.1 Explore Schema

位置：`examples/nl2sql/generate_sql_token.py`

- `postprocess_predictions()` 会找 `<action>` 和 `<tool_call>`。
- 当 tool name 是 `execute_sql_query` 且 action 是 `explore_schema` 时，返回 `("explore_schema", json.dumps({"sql": ..., "db_id": ...}))`。
- `execute_predictions()` 对 `explore_schema` 执行 SQL，并把结果包装成下一轮 observation。

论文说 Explore 阶段应查询 metadata。当前源码主要通过 prompt 约束模型这么做；执行器层面使用只读 SQLite 连接，但没有严格限制 `explore_schema` 必须是 `PRAGMA/table_info/sqlite_master` 这类元数据查询。后续如果要做更强 unknown-schema 设定，这里是一个很自然的改造点。

### 6.2 Propose Schema

位置：`execute_predictions()` 和 `generate()`

- `<schema>{...}</schema>` 被解析成 action `schema`。
- `execute_predictions()` 只做 JSON parse 和统计表/列数量，然后返回 acknowledgement。
- `generate()` 遇到 action `schema` 时记录 `schema_end_position` 和 `cached_schema_json`。

这是论文里 Propose checkpoint 的代码边界：后续 Dual-Track GRPO 正是靠 `schema_end_position` 把轨迹切成 schema segment 和 answer/full segment。

### 6.3 Generate SQL

位置：`execute_predictions()`

- `generate_sql` 也是 `execute_sql_query` tool call。
- 执行结果作为 observation 拼回上下文。
- 这一步是模型在 Confirm 前自我验证 SQL 的机会。

### 6.4 Confirm Answer

位置：`execute_predictions()` 和 `sql_reward_with_schema.py:extract_final_answer_sql`

- `execute_predictions()` 看到 `<answer>` 后返回 `done=True`，rollout 结束。
- reward 阶段从最后一个 `<answer>` 里抽取 SQL。
- 支持三引号 SQL block 和 markdown SQL block，也支持直接把 answer 内容当 SQL。

## 7. Reward 设计

### 7.1 Format reward

`sql_reward_with_schema.py:check_single_turn_format()` 检查单轮：

- 必须恰好一个 `<think>...</think>`。
- 必须恰好一个 `<action>...</action>`。
- action 必须是四种之一。
- 不同 action 必须带对应标签：
  - `explore_schema`: `<tool_call>`
  - `propose_schema`: `<schema>`
  - `generate_sql`: `<tool_call>`
  - `confirm_answer`: `<answer>`

`generate_sql_token.py:compute_turn_level_format_scores()` 再把所有 turn 合成整体格式分。当前逻辑要求：

- 每轮格式分都是 0.1。
- 四个 action 都至少出现过一次。
- observation 中没有 `Invalid format`、`try again`、`syntax error` 这类错误提示。

这和论文 Appendix C 的 format check 对应。

### 7.2 SQL execution reward

位置：`sql_reward_with_schema.py:compute_score_sql_async()`

流程：

1. 从 `sample.prompt + sample.response` 中抽取 final answer SQL。
2. 找到 `reward_model.data_source` 对应的 SQLite 文件。
3. 并发执行 predicted SQL 和 ground-truth SQL。
4. 比较结果集。

分数：

- 结果集匹配：`1.0`
- SQL 可执行但结果不对：`0.2`
- 抽取失败、执行失败或不可读：`0.0`

### 7.3 Schema reward

位置：

- `generate_sql_token.py:_compute_schema_reward_async()`
- `sql_reward_with_schema.py:compute_schema_linking_score()`

流程：

1. 读取 `sample.cached_schema_json`。
2. 读取 label 里的 `ground_truth.schema`。
3. 分别计算 tables 和 columns 的 precision/recall/f1。
4. 按表 0.4、列 0.6 加权。

支持模式：

- `f1`
- `precision`
- `recall`
- `totalmatch`
- `truematch` / `allmatch`，源码里会 alias 到 `totalmatch`
- `recall_then_precision_strict`
- `recall_then_precision`

论文里强调 schema reward 和 final execution reward 要分开优化。当前源码实现方式是先在 `reward_func()` 里构造 sparse token reward，然后在训练 loss 里按 `schema_end_position` 做分段 advantage / mask。

### 7.4 Token-level reward 放置

位置：`generate_sql_token.py:reward_func()`

当 `--enable_schema` 关闭时：

```text
sample.reward = format_score + sql_execution_score
```

当 `--enable_schema` 开启时：

```text
token_rewards = [0.0] * response_length
token_rewards[response_length - 1] = format_score + sql_execution_score
token_rewards[schema_end_position - 1] = schema_score * schema_token_weight
sample.reward = token_rewards
```

也就是说：

- final SQL reward 放在最后一个 response token。
- schema reward 放在 propose schema 结束前一个 token。
- tool observation token 虽然在 response 区间里，但 loss mask 为 0，不参与 policy loss。

一个细节：`reward_func()` 中计算了 `sql_format_score`，但最后写到 last token 的仍是 `format_score + sql_execution_score`。如果你后续想严格做 “schema 段格式分 / SQL 段格式分” 分离，这里需要再核对和改造。

## 8. Dual-Track GRPO 在哪里

论文说 Dual-Track GRPO 用 Propose checkpoint 作为结构边界，通过 token-level masked advantages 分离 schema exploration reward 和 final execution reward。

当前源码里最贴近论文主线的是这条路径：

```text
--enable_schema
--use_weighted_schema_policy_loss
```

启动脚本 `run_qwen3_unified.sh` 中，当 `USE_SCHEMA=true` 时会加入：

```bash
--enable_schema
--use_weighted_schema_policy_loss
--answer_policy_loss_weight 1.0
--schema_policy_loss_weight ${SCHEMA_WEIGHT}
```

训练侧关键链路：

1. `RolloutManager._convert_samples_to_train_data()` 把这些字段放入 train data：
   - `rewards`
   - `schema_end_positions`
   - `sql_rewards`
   - `schema_rewards`
   - `loss_masks`
2. `slime/utils/data.py:process_rollout_data()` 把字段广播并切到各 data parallel rank。
3. `slime/backends/megatron_utils/actor.py:train_actor()` 计算 log_probs/ref_log_probs 后调用 `compute_advantages_and_returns()`。
4. `slime/backends/megatron_utils/loss.py:compute_advantages_and_returns()` 检测到 token-level reward 和 `schema_end_positions`，进入 GRPO/GSPO token-level 分支。
5. 如果 `--use_weighted_schema_policy_loss` 开启，调用 `get_grpo_returns_schema_answer_separate()`：
   - 从 sparse reward 中抽出 schema reward 和 answer reward。
   - 在同一个 prompt 的 `n_samples_per_prompt` 个样本内分别计算 schema advantage 和 answer advantage。
   - 生成 `schema_advantages` 和 `answer_advantages`。
6. `policy_loss_function()` 里构造两个 loss：
   - schema-only policy loss：用 `schema_loss_masks` 把 `schema_end_position` 后面的 SQL/answer token mask 掉。
   - answer/full policy loss：使用完整 loss mask。
7. 最终 loss：

```text
pg_loss =
  schema_policy_loss_weight * schema_pg_loss
  + answer_policy_loss_weight * answer_pg_loss
```

这就是后续改 Dual-Track 的主战场。

另有两个变体也在 `loss.py`：

- `--use_weighted_schema_advantage`: 把 schema advantage 加到 schema 段，但仍是单 policy loss。
- 默认 token-level GRPO 路径 `compute_advantages_schema_reward_weighted()`: 用 answer advantage 全段传播，再把 schema reward 加权叠到 schema 段。

还有一个 `--use_segmented_propagation`，在当前参数说明里主要服务 token-level REINFORCE++ 的 segmented return；对 GRPO 主路径来说，更关键的开关是 `--use_weighted_schema_policy_loss`。不要把这两个概念混在一起。

## 9. SFT warm-up 在源码中的对应

论文里 SFT warm-up 很重要：作者用高质量四阶段轨迹先让模型学会结构化探索，再做 Dual-Track GRPO。论文 Appendix A 说 SFT 数据来自 SynSQL-2.5M 的中高难度问题，经多模型生成完整四阶段轨迹，并用 execution correctness 和 format check 过滤；论文还指出没有 SFT 时，模型容易学会“第一轮枚举全库 schema”的 reward hack。

源码中对应的是 Slime 的通用 SFT 机制：

- `slime/rollout/sft_rollout.py:generate_rollout()`
- `slime/backends/megatron_utils/loss.py:sft_loss_function()`
- `scripts/run-qwen3-4B-base-sft.sh`
- `scripts/run-qwen3-235B-A22B-sft.sh`

SFT 的关键参数通常是：

```bash
--rollout-function-path slime.rollout.sft_rollout.generate_rollout
--loss-type sft_loss
--disable-compute-advantages-and-returns
--debug-train-only
--calculate-per-token-loss
```

不过要注意：当前 `examples/nl2sql/` 没有提供论文级的 NL2SQL SFT 数据构造脚本，也没有把 SynSQL 多模型 annotation pipeline 完整开源成可直接运行的脚本。也就是说：

- 训练框架支持 SFT。
- 论文所述 SFT 数据构造逻辑需要你自己补齐或从作者数据中获得。
- 如果后续要复现论文完整两阶段训练，SFT 数据格式和 loss mask 是第一处需要确认的东西。

## 10. 训练脚本链路

### 10.1 顶层配置

`submit_training.sh` 设置：

- 机器数和 GPU 数。
- `N_SAMPLES_PER_PROMPT=8`，这是 GRPO group size。
- `ROLLOUT_BATCH_SIZE=32`。
- `NUM_ROLLOUT=2000`。
- `ROLLOUT_TEMPERATURE=0.8`。
- `use_schema=True`。
- `SCHEMA_WEIGHT=0.25`。
- `SCHEMA_SCORING_MODE="truematch"`。
- `USE_ASYNC=True` 时走 `run_qwen3_async_oversampling.sh`。

里面很多路径还是 `/path/to/your/...` 占位，真正跑之前必须改。

### 10.2 NL2SQL 训练脚本

`examples/nl2sql/run_qwen3_unified.sh` 做了几件事：

1. 解析命令行参数。
2. 根据 HF checkpoint 路径猜模型大小。
3. 加载 `scripts/models/qwen3-*.sh` 的 Megatron 模型配置。
4. 如未提供 `--ref_load`，尝试把 HF checkpoint 转成 torch_dist。
5. 设置 `PYTHONPATH`，让 `generate_sql_token` 可被动态 import。
6. 构造 `ROLLOUT_ARGS`：
   - `--prompt-data`
   - `--input-key prompt`
   - `--label-key reward_model`
   - `--tool-key tools`
   - `--apply-chat-template`
   - `--n-samples-per-prompt`
   - `--schema_scoring_mode`
7. 构造 `GRPO_ARGS`：
   - `--advantage-estimator grpo`
   - `--use-kl-loss`
   - `--kl-loss-type low_var_kl`
   - clip、entropy 等。
8. 构造 `CUSTOM_ARGS`：

```bash
--custom-generate-function-path "${REWARD_FUNC}.generate"
--custom-rm-path "${REWARD_FUNC}.reward_func"
```

9. 用 Ray job 启动 `python3 train.py`。

### 10.3 同步和异步训练差别

- `train.py`: 每轮先 rollout，再 train，再 update rollout engine 权重。
- `train_async.py`: 提前发起下一轮 rollout，实现 rollout 和训练的流水线重叠。

论文 Appendix B 里 4B 用 sync，8B 用 async；这和脚本命名基本对应。

## 11. 评测/推理链路

训练用的是 `examples/nl2sql/generate_sql_token.py`。

离线评测还有一套在 `trustsql_eval/`：

- `trustsql_eval/main.py`: CLI 入口。
- `trustsql_eval/llm_agent.py`: vLLM 加载、采样、循环处理样本。
- `trustsql_eval/message_processor.py`: 解析 `<answer>`、`<schema>`、`<tool_call>`，执行 SQLite，拼接下一轮消息。
- `trustsql_eval/prompt_builders.py`: 构造 prompt 或用 tokenizer chat template 渲染 messages。

它和训练 rollout 很像，但有一些差异：

- 训练中 tool observation role 是 `tool`；评测代码里很多反馈是以 `user` role 追加。
- 训练的 max turns 是 `NL2SQL_CONFIGS["max_turns"] = 10`；评测 CLI 默认 `--max_rounds 20`。
- 评测的数据库路径查找更兼容 BIRD/Spider2/direct sqlite 多种布局。

如果你后续比较训练和推理行为，最好同时看 `generate_sql_token.py` 和 `trustsql_eval/message_processor.py`，避免 rollout protocol 细节不一致。

## 12. 最适合做 RL 改进的位置

### 12.1 改 schema reward

文件：

- `examples/nl2sql/sql_reward_with_schema.py`
- `examples/nl2sql/generate_sql_token.py:_compute_schema_reward_async`

可做 idea：

- 从 exact table/column matching 改为 join-aware reward。
- 区分 required columns、filter columns、join columns、aggregation columns。
- 对 over-exploration 加惩罚，避免 propose 过多无关列。
- 做 schema graph coverage reward，而不是平面 set matching。
- 加入 value grounding reward，比如是否验证了关键 literal/value 所在列。

### 12.2 改探索工具和 action space

文件：

- `examples/nl2sql/generate_sql_token.py:execute_predictions`
- `LocalDatabaseExecutor`
- `trustsql_eval/message_processor.py`

可做 idea：

- 把通用 SQL tool 拆成更细工具：`list_tables`、`describe_table`、`list_foreign_keys`、`sample_values`、`execute_candidate_sql`。
- Explore 阶段只允许 metadata query，Generate 阶段才允许 user-intent SQL。
- 给工具调用加成本 reward，鼓励少查但查准。
- 限制单次返回长度，并把 observation compression 做成可训练策略。

### 12.3 改 Dual-Track GRPO / credit assignment

文件：

- `slime/backends/megatron_utils/loss.py`
- `slime/utils/ppo_utils.py`
- `slime/utils/data.py`

可做 idea：

- 用三段 advantage：explore 段、propose 段、SQL 段。
- 让 final execution reward 只回传到 SQL 段，让 schema reward 只回传到 explore/propose 段。
- 加入 turn-level advantage，而不是只在 token 上放稀疏点奖励。
- 把 schema reward 和 SQL reward 的 group normalization 完全分开，并记录二者方差。
- 对失败样本做 failure attribution：schema 错 vs SQL 错，进入不同 reward track。

### 12.4 改 SFT/RL 数据构造

文件/目录：

- `data_for_sql/`
- `slime/rollout/sft_rollout.py`
- 需要新增你自己的数据构造脚本

可做 idea：

- 构造更短、更高信息密度的探索轨迹。
- 用 teacher agent 自动生成多条探索路径，然后按 cost/accuracy 过滤。
- 做 curriculum：先单表，再多表 join，再嵌套/聚合。
- 复现论文的 pass-rate filtering，并比较不同阈值，比如 `< 6/8`、`< 7/8`、`1-5/8`。

### 12.5 改 prompt/protocol

文件：

- `data_for_sql/filtered_questions.jsonl` 内的 system prompt
- `trustsql_eval/prompt_builders.py`
- 如果训练时动态构造 prompt，也可以新增 preprocessing 脚本

可做 idea：

- 加入显式 “已验证 schema memory” 格式。
- 把 `propose_schema` 分成 `propose_tables` 和 `propose_columns`。
- 引入 `revise_schema`，让模型能在 SQL 失败后回滚 schema。
- 对不同难度问题使用不同 turn budget。

## 13. 目前源码和论文之间的注意点

1. 论文的数据构造 pipeline 写得很清楚，但本仓库没有完整暴露 SynSQL SFT annotation、multi-model schema consensus、RL pass-rate filtering 的可运行脚本。
2. `examples/nl2sql` 是论文任务主线；`slime` 里还有很多通用 RL/Slime 示例，不要一开始陷进去。
3. Explore 阶段的“只查 metadata”主要靠 prompt 约束，执行器没有在 action 层做强 metadata-only 校验。
4. `--use_segmented_propagation` 和 `--use_weighted_schema_policy_loss` 不是一回事。当前 schema-enabled GRPO 脚本默认走后者。
5. `schema_scoring_mode` 在不同位置默认值不完全一致：arguments 里默认 `f1`，`reward_func()` 内默认 `totalmatch`，脚本里常传 `truematch`。实际实验要以命令行最终值为准。
6. 训练 rollout 和 `trustsql_eval` 的 message role、turn budget、数据库路径兼容逻辑不完全相同。评测复现实验时要对齐。
7. 只读安全依赖 SQLite `mode=ro` 和 reward 侧 `is_sql_readonly()`，但 rollout 执行路径没有系统性使用 `ALLOWED_SQL_PREFIXES`。

## 14. 推荐阅读顺序

第一轮只读这些，基本能建立全局图：

1. `README.md`
2. `data_for_sql/filtered_questions.jsonl` 头两行
3. `examples/nl2sql/generate_sql_token.py`
4. `examples/nl2sql/sql_reward_with_schema.py`
5. `examples/nl2sql/run_qwen3_unified.sh`
6. `slime/ray/rollout.py`
7. `slime/utils/data.py`
8. `slime/backends/megatron_utils/loss.py`
9. `trustsql_eval/message_processor.py`

第二轮带着问题读：

- 想改 agent 行为：读 `generate_sql_token.py` 和 prompt。
- 想改 reward：读 `sql_reward_with_schema.py` 和 `reward_func()`。
- 想改 RL 算法：读 `loss.py` 的 `compute_advantages_and_returns()` 和 `policy_loss_function()`。
- 想复现实验：读 `submit_training.sh`、`run_qwen3_unified.sh`、`run_qwen3_async_oversampling.sh`。
- 想做离线评测：读 `trustsql_eval/`。

## 15. 一句话版 pipeline

```text
JSONL prompt/reward_model
  -> Dataset + RolloutDataSource 复制成 GRPO groups
  -> SGLang 多轮生成
  -> execute_sql_query 工具返回 observation
  -> loss_mask 屏蔽工具 token
  -> 缓存 proposed schema 和 schema_end_position
  -> SQL execution reward + schema linking reward
  -> token-level sparse reward
  -> RolloutManager 转成训练 batch
  -> Megatron actor 计算 log_probs/ref_log_probs
  -> Dual-Track GRPO 生成 schema/full advantages
  -> policy loss 更新 actor
  -> 更新 SGLang rollout engine 权重
  -> 下一轮 rollout
```

这份源码后续最值得你做论文 idea 的地方，是 `schema_end_position` 这条边界。它把“探索是否找对 schema”和“SQL 是否写对”从一个黑盒 terminal reward 拆成了可操作的两个训练信号。你可以围绕这条边界继续做更细的 reward、更细的 action space、更细的 credit assignment。
