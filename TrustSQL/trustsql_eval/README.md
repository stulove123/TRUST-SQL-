# trustsql_eval

A multi-turn NL2SQL evaluation framework that uses a local LLM (via [vLLM](https://github.com/vllm-project/vllm)) to iteratively explore a database schema, generate SQL queries, and verify them by executing against a local SQLite database.

## Overview

The agent follows a structured **Action Protocol**:

1. **explore_schema** — Query database metadata (tables, columns, foreign keys)
2. **propose_schema** — Document the verified schema
3. **generate_sql** — Generate a SQL query and verify it by execution
4. **confirm_answer** — Output the final, verified SQL query

Each conversation is multi-turn: the agent can loop back to earlier steps if the generated SQL is incorrect or incomplete.

## Directory Structure

```
trustsql_eval/
├── main.py                    # Entry point: single-thread vLLM inference
├── main_batch.py              # Entry point: synchronous batch vLLM inference
├── main_batch_async.py        # Entry point: async continuous-batching vLLM inference
├── main_batch_latency.py      # Entry point: latency analysis mode
├── llm_agent.py               # Single-thread LLM agent
├── llm_agent_batch.py         # Batch LLM agent (synchronous vLLM)
├── llm_agent_batch_async.py   # Batch LLM agent (async vLLM AsyncLLMEngine)
├── llm_agent_batch_latency.py # Latency analyzer (async, measures per-round timing)
├── message_processor.py       # Multi-turn conversation logic + SQL execution
├── prompt_builders.py         # Prompt rendering via tokenizer.apply_chat_template
├── file_manager.py            # Result persistence (per-instance JSON files)
├── prompt_template.txt        # System prompt template
├── chat_template_test.py      # Example: test Jinja2 chat template rendering
└── test_vllm.py               # Smoke test for vLLM AsyncLLMEngine
```

## Requirements

```
torch
vllm
transformers
```

Install dependencies:

```bash
pip install torch vllm transformers
```

## Usage

### Basic (single-thread)

```bash
python main.py \
  --input_file /path/to/questions.jsonl \
  --output_folder /path/to/output \
  --system_prompt_path prompt_template.txt \
  --databases_path /path/to/databases \
  --documents_path /path/to/documents \
  --model /path/to/your/model \
  --template_dir /path/to/your/model \
  --temperature 0.7 \
  --top_p 0.9 \
  --max_new_tokens 4096 \
  --max_rounds 20 \
  --rollout_number 1
```

### Batch (synchronous vLLM)

```bash
python main_batch.py \
  --input_file /path/to/questions.jsonl \
  --output_folder /path/to/output \
  --system_prompt_path prompt_template.txt \
  --databases_path /path/to/databases \
  --documents_path /path/to/documents \
  --model /path/to/your/model \
  --template_dir /path/to/your/model \
  --batch_size 64 \
  --temperature 0.7 \
  --max_rounds 20
```

### Async (continuous batching)

```bash
python main_batch_async.py \
  --input_file /path/to/questions.jsonl \
  --output_folder /path/to/output \
  --system_prompt_path prompt_template.txt \
  --databases_path /path/to/databases \
  --documents_path /path/to/documents \
  --model /path/to/your/model \
  --template_dir /path/to/your/model \
  --batch_size 128 \
  --temperature 0.7 \
  --max_rounds 20
```

### Latency analysis

```bash
python main_batch_latency.py \
  --input_file /path/to/questions.jsonl \
  --output_folder /path/to/latency_results \
  --system_prompt_path prompt_template.txt \
  --databases_path /path/to/databases \
  --documents_path /path/to/documents \
  --model /path/to/your/model \
  --template_dir /path/to/your/model \
  --max_rounds 10
```

Latency mode runs only the first 5 instances and outputs per-instance timing to both JSON and CSV files.

## Input Format

The input file should be a JSONL file where each line is a JSON object with at least:

```json
{
  "id": "unique_instance_id",
  "db_id": "database_name",
  "instruction": "What is the total revenue by region?",
  "reward_model": {
    "database": "/path/to/databases"
  }
}
```

The `database` field (under `reward_model`, `extra_info`, or at the top level) should point to the directory containing the SQLite database files.

## Database Path Formats

The framework supports two common benchmark layouts:

| Format | Path pattern |
|--------|-------------|
| BIRD   | `{databases_path}/{db_id}/{db_id}.sqlite` |
| Spider2 | `{databases_path}/{db_id}.sqlite` |
| Direct | `{databases_path}` (the path itself is a `.sqlite` file) |

## Output Format

Each instance produces a JSON file at `{output_folder}/{instance_id}.json`:

```json
[
  {
    "instance_id": "...",
    "rollout_idx": 0,
    "conversation": [...],
    "final_messages": [...],
    "terminated": true,
    "rounds_completed": 4
  }
]
```

`terminated: true` means the agent successfully produced a `<answer>` tag with the final SQL.

## Key Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--model` | Path to the local model | required |
| `--template_dir` | Path to the tokenizer directory | `None` |
| `--input_file` | Input JSONL file | required |
| `--output_folder` | Output directory | required |
| `--system_prompt_path` | Path to the system prompt file | required |
| `--databases_path` | Root directory of SQLite databases | required |
| `--documents_path` | Directory for external knowledge files | required |
| `--max_rounds` | Maximum conversation turns per instance | `20` |
| `--rollout_number` | Number of rollouts per instance | `1` |
| `--batch_size` | Batch size / concurrency limit | `64` / `128` |
| `--temperature` | Sampling temperature | `0.7` |
| `--top_p` | Top-p sampling | `0.9` |
| `--max_new_tokens` | Maximum tokens to generate per turn | `4096` |
| `--gpu_memory_utilization` | vLLM GPU memory fraction | `0.9` |

## Resume Support

All modes support **resume from checkpoint**: already-completed instances (those with an existing output JSON file) are automatically skipped on restart.

## Notes

- The framework uses `VLLM_USE_V1=0` to disable the vLLM V1 engine for compatibility.
- RoPE configuration (`max_position_embeddings`, `rope_scaling`, `rope_theta`) is automatically read from the model's `config.json`.
- Stop tokens are automatically detected from the tokenizer config, with a hardcoded fallback for Qwen3 models.
- SQL execution is sandboxed to read-only queries (`SELECT`, `PRAGMA`, `EXPLAIN`).
