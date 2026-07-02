# NL2SQL Reinforcement Learning with Schema Linking

A multi-turn NL2SQL training pipeline based on [Slime](https://github.com/THUDM/slime), using GRPO/GSPO/PPO to train language models to generate SQL through tool-use interactions. Supports optional **schema linking** as an intermediate reward signal.

---

## Table of Contents

- [Overview](#overview)
- [Repository Structure](#repository-structure)
- [Quick Start](#quick-start)
- [Data Format](#data-format)
- [Rollout Protocol](#rollout-protocol)
- [Reward Design](#reward-design)
- [Schema Linking](#schema-linking)
- [Training Arguments](#training-arguments)
- [Algorithm Selection](#algorithm-selection)
- [Dependencies](#dependencies)
- [Notes](#notes)

---

## Overview

The model learns to solve NL2SQL tasks through a **multi-turn agentic loop**:

1. **Explore** the database schema via SQL queries
2. **Propose** the relevant tables and columns
3. **Generate and verify** a SQL query by executing it
4. **Confirm** the final answer

Training uses token-level rewards: the SQL correctness reward is placed at the last response token, and an optional schema linking reward is placed at the schema proposal token.

---

## Repository Structure

```
slime_trust_sql/examples/nl2sql
├── generate_sql_token.py        # Multi-turn rollout + reward function
└── sql_reward_with_schema.py    # SQL execution scoring + schema linking evaluation
```

---

## Quick Start

### 1. Install dependencies

```bash
pip install torch>=2.1 ray>=2.9 wandb
# Install Megatron-LM, SGLang, and Slime per their official instructions
```

### 2. Prepare data

See [Data Format](#data-format) for the expected JSONL schema.

### 3. Convert model checkpoint

```bash
CUDA_VISIBLE_DEVICES=0 python tools/convert_hf_to_torch_dist.py \
    --hf-checkpoint /path/to/Qwen3-7B \
    --save /path/to/model_torch_dist
```

> If `--ref_load` is not provided, the training script will attempt this conversion automatically.

### 4. Launch training
Parameters can seen in slime_trust_sql/submit_training.sh

---

## Data Format

Each line in the training JSONL should be:

```json
{
  "prompt": "<user question in chat-template format>",
  "reward_model": {
    "data_source": "spider_db_id",
    "database": "/path/to/databases/",
    "ground_truth": {
      "target": "SELECT col FROM table WHERE ...",
      "schema": {
        "tables": ["table1", "table2"],
        "columns": {
          "table1": ["col1", "col2"],
          "table2": ["col3"]
        }
      }
    }
  }
}
```

| Field | Required | Description |
|---|---|---|
| `prompt` | ✅ | Natural language question, formatted for chat template |
| `reward_model.data_source` | ✅ | SQLite database ID (folder name under `database/`) |
| `reward_model.database` | ✅ | Root path containing all database folders |
| `ground_truth.target` | ✅ | Ground-truth SQL query |
| `ground_truth.schema` | Schema mode only | Ground-truth tables and columns for schema linking evaluation |

---

## Rollout Protocol

Each rollout episode proceeds as follows:

```
User prompt
    └─► [Turn 1] explore_schema
            <think> ... </think>
            <action>explore_schema</action>
            <tool_call>{"name": "execute_sql_query", "arguments": {"db_id": "...", "sql": "..."}}</tool_call>
            → DB execution result (observation, loss_mask=0)

    └─► [Turn 2] propose_schema
            <think> ... </think>
            <action>propose_schema</action>
            <schema>{"tables": [...], "columns": {...}}</schema>
            → Acknowledgement (observation, loss_mask=0)

    └─► [Turn 3] generate_sql
            <think> ... </think>
            <action>generate_sql</action>
            <tool_call>{"name": "execute_sql_query", "arguments": {"db_id": "...", "sql": "..."}}</tool_call>
            → SQL execution result (observation, loss_mask=0)

    └─► [Turn 4] confirm_answer
            <think> ... </think>
            <action>confirm_answer</action>
            <answer>```sql SELECT ... ```</answer>
            → Episode ends
```

**Constraints:**
- Maximum 10 turns per episode
- Maximum context length: 40 000 tokens (episodes exceeding this are marked `TRUNCATED`)
- Tool response tokens are masked from the loss (`loss_mask = 0`)

---

## Reward Design

### Token-level reward placement

```
Response tokens:  [ t1, t2, ..., t_schema, ..., t_last ]
                                     ↑                ↑
                              schema_reward      sql_reward + format_reward
```

| Token position | Reward |
|---|---|
| `response_length - 1` (last token) | `sql_execution_score + format_score` |
| `schema_end_position - 1` | `schema_score × schema_weight` *(schema mode only)* |

### SQL execution score

| Outcome | Score |
|---|---|
| Result set matches ground truth | `1.0` |
| SQL executes but result is wrong | `0.2` |
| Cannot extract or execute SQL | `0.0` |

### Format score

`overall_format_score = 0.1` if and only if **all** of the following hold:

1. Every turn passes the per-turn format check
2. All four actions (`explore_schema`, `propose_schema`, `generate_sql`, `confirm_answer`) appeared at least once
3. No user-reported errors (invalid format / syntax error) in any turn

### Per-turn format requirements

| Action | Required tags |
|---|---|
| `explore_schema` | `<think>` + `<action>` + `<tool_call>` |
| `propose_schema` | `<think>` + `<action>` + `<schema>` |
| `generate_sql` | `<think>` + `<action>` + `<tool_call>` |
| `confirm_answer` | `<think>` + `<action>` + `<answer>` |

---

## Schema Linking

When `--use_schema true`, the model is rewarded for proposing the correct set of tables and columns before generating SQL.

### Schema proposal format

The model should emit a `propose_schema` turn with:

```json
{
  "tables": ["orders", "customers"],
  "columns": {
    "orders":    ["id", "amount", "customer_id"],
    "customers": ["id", "name"]
  }
}
```

### Scoring modes

| Mode | Description | Use when |
|---|---|---|
| `totalmatch` | `1.0` only if tables **and** columns both match exactly; else `0.0` | You want a strict all-or-nothing signal |
| `recall_then_precision_strict` | Recall = 1.0 required; weighted precision bucketed into `{0.1, 0.2, 0.4, 0.6, 0.8, 1.0}` | You require full coverage but allow some noise |
| `f1` | Harmonic mean of precision and recall | You want a soft, balanced signal |
| `precision` | Fraction of predicted items that are correct | You want to penalize over-prediction |
| `recall` | Fraction of ground-truth items that were predicted | You want to penalize under-prediction |

Weights: **table score × 0.4 + column score × 0.6**

### Segmented advantage normalization

When `--use_segmented_propagation true`, schema-segment advantages and SQL-segment advantages are whitened **independently**, preventing the two reward signals from interfering with each other's scale.

---

## Training Arguments

### Core

| Argument | Default | Description |
|---|---|---|
| `--alg` | `grpo` | RL algorithm: `grpo` / `gspo` / `ppo` |
| `--hf_checkpoint` | *(required)* | HuggingFace model path or URL |
| `--ref_load` | auto-detected | Megatron torch_dist checkpoint path |
| `--data` | *(required)* | Training data JSONL path |
| `--val_data` | *(required)* | Validation data JSONL path |
| `--save_dir` | *(required)* | Checkpoint save directory |
| `--save_interval` | — | Save every N rollout steps |

### Rollout

| Argument | Default | Description |
|---|---|---|
| `--rollout_batch_size` | — | Number of prompts per rollout |
| `--n_samples_per_prompt` | — | Samples per prompt (group size for GRPO) |
| `--rollout_max_response_len` | — | Maximum response length in tokens |
| `--rollout_temperature` | — | Sampling temperature |
| `--num_rollout` | — | Total number of rollout steps |

### Schema linking

| Argument | Default | Description |
|---|---|---|
| `--use_schema` | `false` | Enable schema linking mode |
| `--schema_scoring_mode` | `totalmatch` | Schema evaluation mode |
| `--schema_weight` | `0.5` | Multiplier for schema token reward |

### Optimization

| Argument | Default | Description |
|---|---|---|
| `--lr_actor` | — | Actor learning rate |
| `--kl_loss_coef` | — | KL divergence loss coefficient |
| `--entropy_coef` | — | Entropy bonus coefficient |
| `--eps_clip` | — | PPO clip lower bound |
| `--eps_clip_high` | — | PPO clip upper bound |
| `--optimizer` | — | Optimizer type (e.g. `adam`) |

### Logging

| Argument | Default | Description |
|---|---|---|
| `--wandb_project` | — | W&B project name |
| `--wandb_group` | — | W&B run group |
| `--wandb_key` | — | W&B API key |
| `--experiment_name` | — | Run name |

---

## Algorithm Selection

| `--alg` | Estimator | Advantage normalization |
|---|---|---|
| `grpo` | Group-wise relative reward | Disabled (self-normalizing via group comparison) |
| `gspo` | Group-wise with sequence-level KL penalty | Disabled |
| `ppo` | GAE (Generalized Advantage Estimation) | Enabled |

> `reinforce_plus_plus` (`rpp`) has been removed. Use `grpo` as the recommended default.

---

## Dependencies

| Package | Version |
|---|---|
| Python | ≥ 3.10 |
| PyTorch | ≥ 2.1 |
| [Megatron-LM](https://github.com/NVIDIA/Megatron-LM) | latest |
| [SGLang](https://github.com/sgl-project/sglang) | ≥ 0.4.9 |
| [Ray](https://docs.ray.io/) | ≥ 2.9 |
| [Slime](https://github.com/THUDM/slime) | latest |
| SQLite3 | stdlib |
| wandb | latest |

---

## Notes

- All SQL execution uses **read-only SQLite connections** (`?mode=ro`). Write operations are rejected.
- Observation tokens (tool responses returned to the model) are excluded from the training loss via `loss_mask = 0`.
- If no `propose_schema` action is detected in a rollout, `schema_end_position` defaults to `0` and the schema reward is suppressed for that sample.
- The model checkpoint path is auto-detected from `--hf_checkpoint` using pattern matching on common model family names (`qwen3`, `llama`, `mistral`, etc.). If detection fails, provide `--ref_load` explicitly.
- Multi-node training requires a shared filesystem accessible from all nodes for checkpoint saving and database access.