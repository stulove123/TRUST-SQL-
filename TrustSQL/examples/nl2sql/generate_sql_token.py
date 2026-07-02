"""
NL2SQL Rollout with Schema Linking Support
Refactored: Turn-level format scoring + Token-level Reward
"""

import asyncio
import re
import os
import sqlite3
from typing import Dict, Tuple, Optional
import json
from concurrent.futures import ThreadPoolExecutor

from slime.rollout.sglang_rollout import GenerateState
from slime.utils.http_utils import post
from slime.utils.types import Sample

from sql_reward_with_schema import (
    compute_score_sql_async,
    compute_schema_linking_score,
    check_single_turn_format,
    set_thread_pool
)

# ==================== Configuration ====================
NL2SQL_CONFIGS = {
    "max_turns": 10,
    "sql_execution_concurrency": 100,
    "sql_execution_timeout": 10.0,
    "return_logprob": True,
}

SEMAPHORE = asyncio.Semaphore(NL2SQL_CONFIGS["sql_execution_concurrency"])

_thread_pool = ThreadPoolExecutor(max_workers=NL2SQL_CONFIGS["sql_execution_concurrency"])
set_thread_pool(_thread_pool)

ALLOWED_SQL_PREFIXES = ('SELECT', 'PRAGMA', 'EXPLAIN')


# ==================== Database Executor ====================
class LocalDatabaseExecutor:
    """Local SQLite database executor - read-only, thread-safe"""

    def __init__(self, databases_path: str):
        self.databases_path = databases_path

    def execute(self, db_id: str, sql_query: str, max_rows: int = 100) -> Dict:
        """Execute a SQL query and return results (read-only mode)"""
        conn = None
        try:
            db_path = os.path.join(self.databases_path, db_id, f"{db_id}.sqlite")

            if not os.path.exists(db_path):
                return {"error": f"Database file not found: {db_path}"}

            conn = sqlite3.connect(
                f'file:{db_path}?mode=ro',
                uri=True,
                check_same_thread=False
            )
            conn.row_factory = sqlite3.Row

            cursor = conn.cursor()
            cursor.execute(sql_query)
            rows = cursor.fetchall()

            if not rows:
                return {"content": "Query executed successfully. No results returned."}

            column_names = [description[0] for description in cursor.description]
            result_lines = ["\t".join(column_names)]

            for i, row in enumerate(rows):
                if i >= max_rows:
                    result_lines.append(f"... ({len(rows) - max_rows} more rows)")
                    break
                result_lines.append("\t".join(
                    str(value) if value is not None else "NULL" for value in row
                ))

            return {
                "content": "\n".join(result_lines),
                "row_count": len(rows),
                "column_names": column_names
            }

        except sqlite3.Error as e:
            return {"error": f"SQLite error: {str(e)}"}
        except Exception as e:
            return {"error": f"Unexpected error: {str(e)}"}
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass


def _format_execution_result(execution_result: Dict) -> str:
    """Format SQL execution result into a readable string"""
    if "error" in execution_result:
        return f"Error: {execution_result['error']}"
    return execution_result.get("content", "Query executed successfully.")


async def execute_sql_local(db_id: str, sql_query: str, databases_path: str, timeout: float = None) -> str:
    """Execute SQL query locally using a dedicated thread pool with timeout control"""
    if timeout is None:
        timeout = NL2SQL_CONFIGS["sql_execution_timeout"]

    executor = LocalDatabaseExecutor(databases_path)

    try:
        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(_thread_pool, executor.execute, db_id, sql_query),
            timeout=timeout
        )
        return _format_execution_result(result)
    except asyncio.TimeoutError:
        return f"Error: SQL execution timeout (exceeded {timeout}s)."


# ==================== Prediction Parsing ====================
def postprocess_predictions(prediction: str) -> Tuple[Optional[str], str]:
    """Extract action type and content from model prediction"""
    if not isinstance(prediction, str):
        prediction = str(prediction)

    # Check <answer> tag
    answer_match = re.search(r"<answer>(.*?)</answer>", prediction, re.DOTALL)
    if answer_match:
        return "answer", answer_match.group(1).strip()

    # Check <schema> tag
    schema_match = re.search(r"<schema>(.*?)</schema>", prediction, re.DOTALL)
    if schema_match:
        return "schema", schema_match.group(1).strip()

    # Check <action> and <tool_call> tags
    action_match = re.search(r"<action>(.*?)</action>", prediction, re.DOTALL)
    action_type = action_match.group(1).strip() if action_match else None

    tool_match = re.search(r"<tool_call>(.*?)</tool_call>", prediction, re.DOTALL)
    if tool_match:
        try:
            tool_data = json.loads(tool_match.group(1).strip())

            if not isinstance(tool_data, dict):
                return None, ""

            if tool_data.get("name") == "execute_sql_query":
                arguments = tool_data.get("arguments", {})
                if not isinstance(arguments, dict):
                    return None, ""

                result_data = {
                    "sql": arguments.get("sql", ""),
                    "db_id": arguments.get("db_id", "")
                }

                if action_type == "explore_schema":
                    return "explore_schema", json.dumps(result_data)
                elif action_type == "generate_sql":
                    return "generate_sql", json.dumps(result_data)
                else:
                    return "sql", json.dumps(result_data)

        except (json.JSONDecodeError, Exception):
            pass

    return None, ""


# ==================== Action Execution ====================
async def execute_predictions(prediction: str, db_id: str, databases_path: str) -> Tuple[str, bool]:
    """Execute the predicted action and return (observation, done)"""
    action, content = postprocess_predictions(prediction)

    # SQL-related actions
    if action in ["sql", "explore_schema", "generate_sql"]:
        try:
            sql_data = json.loads(content)
            sql_query = sql_data.get("sql", "")
            tool_db_id = sql_data.get("db_id", "") or db_id

            if not sql_query:
                return "\nError: SQL query is empty.\n", False

            async with SEMAPHORE:
                execution_result = await execute_sql_local(tool_db_id, sql_query, databases_path)

            return f"\n{execution_result}\n", False

        except Exception as e:
            return f"\nError parsing SQL request: {str(e)}\nPlease check your format and try again.\n", False

    # Schema proposal
    elif action == "schema":
        try:
            schema_data = json.loads(content)
            tables = schema_data.get('tables', [])
            columns = schema_data.get('columns', {})

            if isinstance(columns, dict):
                col_count = sum(len(cols) for cols in columns.values())
            elif isinstance(columns, list):
                col_count = len(columns)
            else:
                col_count = 0

            return (
                f"\nSchema acknowledged: {len(tables)} table(s), "
                f"{col_count} column(s). "
                "You may now proceed to generate SQL.\n"
            ), False

        except json.JSONDecodeError as e:
            return (
                f"\nError: Invalid JSON in schema - {str(e)}\n"
                "Expected format: {\"tables\": [...], \"columns\": {...}}\n"
            ), False

    # Final answer
    elif action == "answer":
        return "", True

    # Invalid format
    else:
        return (
            "\nInvalid format detected. Your response is missing required components.\n\n"
            "Option 1: EXPLORE SCHEMA\n"
            "Purpose: Investigate database structure\n"
            "Required format:\n"
            "<think>Your reasoning process</think>\n"
            "<action>explore_schema</action>\n"
            "<tool_call>{\"name\": \"execute_sql_query\", \"arguments\": {\"db_id\": \"...\", \"sql\": \"...\"}}</tool_call>\n\n"
            "Option 2: PROPOSE SCHEMA\n"
            "Purpose: Document your understanding of relevant tables and columns\n"
            "Required format:\n"
            "<think>Your reasoning process</think>\n"
            "<action>propose_schema</action>\n"
            "<schema>{\"tables\": [...], \"columns\": {...}}</schema>\n\n"
            "Option 3: GENERATE SQL\n"
            "Purpose: Create SQL query and VERIFY it works by executing\n"
            "<think>Your reasoning process</think>\n"
            "<action>generate_sql</action>\n"
            "<tool_call>{\"name\": \"execute_sql_query\", \"arguments\": {\"db_id\": \"...\", \"sql\": \"...\"}}</tool_call>\n\n"
            "Option 4: FINAL ANSWER\n"
            "Purpose: Provide verified SQL query as final result\n"
            "ONLY use this AFTER successfully executing and verifying your SQL.\n"
            "Required format:\n"
            "<think>Your reasoning process</think>\n"
            "<action>confirm_answer</action>\n"
            "<answer>```sql\nYOUR_SQL\n```</answer>\n\n"
        ), False


# ==================== Rollout ====================
async def generate(args, sample: Sample, sampling_params) -> Sample:
    """
    Generate SQL query through multi-turn interaction.
    Records turn_boundaries and computes turn-level format scores.
    """
    state = GenerateState(args)
    url = f"http://{args.sglang_router_ip}:{args.sglang_router_port}/generate"

    db_id = sample.label.get("data_source", "")
    databases_path = sample.label.get("database", "")

    MODEL_MAX_LENGTH = 40960
    SAFE_MAX_LENGTH = 40000
    MAX_OBS_TOKENS = 1024

    enable_schema = getattr(args, 'enable_schema', False)

    if enable_schema:
        schema_end_position = None
        last_explore_schema_position = None
        cached_schema_content = None

    turn_boundaries = []
    turn_texts = []
    turn_user_feedbacks = []

    messages = [{"role": "user", "content": sample.prompt}]
    prompt_tokens_ids = state.tokenizer.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=True
    )

    all_token_ids = list(prompt_tokens_ids)
    response_loss_mask = []
    full_response_text = ""
    rollout_log_probs = [] if NL2SQL_CONFIGS["return_logprob"] else None

    for turn_idx in range(NL2SQL_CONFIGS["max_turns"]):
        current_length = len(all_token_ids)

        if current_length > SAFE_MAX_LENGTH:
            print(f"[ERROR] Context length {current_length} exceeds safe limit {SAFE_MAX_LENGTH}, stopping at turn {turn_idx}")
            sample.status = Sample.Status.TRUNCATED
            break

        current_prompt_str = state.tokenizer.decode(all_token_ids, skip_special_tokens=False)
        payload = {"text": current_prompt_str, "sampling_params": sampling_params}

        if NL2SQL_CONFIGS["return_logprob"]:
            payload["return_logprob"] = True

        try:
            output = await post(url, payload)
        except Exception as e:
            error_msg = str(e)
            if "longer than the model's context length" in error_msg:
                print(f"[ERROR] Model context length exceeded at turn {turn_idx}")
                sample.status = Sample.Status.TRUNCATED
                break
            print(f"Request failed: {e}")
            sample.status = Sample.Status.ABORTED
            return sample

        if output["meta_info"]["finish_reason"]["type"] == "abort":
            sample.status = Sample.Status.ABORTED
            return sample

        cur_response_text = output["text"]
        turn_start_pos = len(all_token_ids) - len(prompt_tokens_ids)

        if NL2SQL_CONFIGS["return_logprob"]:
            cur_response_token_ids = [item[1] for item in output["meta_info"]["output_token_logprobs"]]
            cur_response_log_probs = [item[0] for item in output["meta_info"]["output_token_logprobs"]]
        else:
            cur_response_token_ids = state.tokenizer(cur_response_text, add_special_tokens=False)["input_ids"]

        all_token_ids.extend(cur_response_token_ids)
        response_loss_mask.extend([1] * len(cur_response_token_ids))
        full_response_text += cur_response_text

        if NL2SQL_CONFIGS["return_logprob"]:
            rollout_log_probs.extend(cur_response_log_probs)

        messages.append({"role": "assistant", "content": cur_response_text})

        turn_end_pos = len(all_token_ids) - len(prompt_tokens_ids)
        turn_boundaries.append((turn_start_pos, turn_end_pos))
        turn_texts.append(cur_response_text)

        # Track schema-related actions
        if enable_schema:
            action, content = postprocess_predictions(cur_response_text)

            if action == "schema":
                schema_end_position = turn_end_pos
                cached_schema_content = content
            elif action == "explore_schema":
                last_explore_schema_position = turn_end_pos

        if output["meta_info"]["finish_reason"]["type"] == "length":
            break

        next_obs, done = await execute_predictions(cur_response_text, db_id, databases_path)
        turn_user_feedbacks.append(next_obs)

        if done:
            break

        if next_obs:
            obs_tokens = state.tokenizer(next_obs, add_special_tokens=False)["input_ids"]

            if len(obs_tokens) > MAX_OBS_TOKENS:
                obs_tokens = obs_tokens[:MAX_OBS_TOKENS]
                next_obs = state.tokenizer.decode(obs_tokens) + "\n... (result truncated due to length)"

            messages_copy = messages + [{"role": "tool", "content": next_obs}]
            predicted_token_ids = state.tokenizer.apply_chat_template(
                messages_copy, tokenize=True, add_generation_prompt=True
            )

            if len(predicted_token_ids) > SAFE_MAX_LENGTH:
                available_space = SAFE_MAX_LENGTH - len(all_token_ids) - 100
                if available_space < 50:
                    sample.status = Sample.Status.TRUNCATED
                    break
                obs_tokens = obs_tokens[:available_space]
                next_obs = state.tokenizer.decode(obs_tokens) + "\n... (truncated)"

            messages.append({"role": "tool", "content": next_obs})
            full_response_text += next_obs

            new_full_token_ids = state.tokenizer.apply_chat_template(
                messages, tokenize=True, add_generation_prompt=True
            )

            start_idx = len(all_token_ids)
            obs_segment_ids = new_full_token_ids[start_idx:]

            all_token_ids.extend(obs_segment_ids)
            response_loss_mask.extend([0] * len(obs_segment_ids))

            if NL2SQL_CONFIGS["return_logprob"]:
                rollout_log_probs.extend([0.0] * len(obs_segment_ids))

    # Pack sample
    sample.tokens = all_token_ids
    response_length = len(all_token_ids) - len(prompt_tokens_ids)
    sample.response_length = response_length
    sample.response = full_response_text

    if len(response_loss_mask) != response_length:
        if len(response_loss_mask) > response_length:
            response_loss_mask = response_loss_mask[:response_length]
        else:
            response_loss_mask.extend([0] * (response_length - len(response_loss_mask)))

    sample.loss_mask = response_loss_mask

    if NL2SQL_CONFIGS["return_logprob"]:
        sample.rollout_log_probs = rollout_log_probs

    match output["meta_info"]["finish_reason"]["type"]:
        case "length":
            sample.status = Sample.Status.TRUNCATED
        case "abort":
            sample.status = Sample.Status.ABORTED
        case "stop":
            sample.status = Sample.Status.COMPLETED

    sample.turn_boundaries = turn_boundaries
    sample.turn_texts = turn_texts
    sample.turn_user_feedbacks = turn_user_feedbacks

    turn_format_scores, overall_format_score = compute_turn_level_format_scores(turn_texts, turn_user_feedbacks)
    sample.turn_format_scores = turn_format_scores
    sample.overall_format_score = overall_format_score

    # Handle schema trajectory
    if enable_schema:
        if schema_end_position is not None:
            sample.schema_end_position = schema_end_position
            sample.schema_response_length = schema_end_position
            sample.cached_schema_json = cached_schema_content
            sample.is_dummy_schema = False
        elif last_explore_schema_position is not None:
            sample.schema_end_position = last_explore_schema_position
            sample.schema_response_length = last_explore_schema_position
            sample.cached_schema_json = None
            sample.is_dummy_schema = True
        else:
            sample.schema_end_position = 0
            sample.is_dummy_schema = True
            print(f"[WARNING] No schema actions found, schema_end_position set to 0")

    return sample


# ==================== Format Scoring ====================
def compute_turn_level_format_scores(
    turn_texts: list[str],
    turn_user_feedbacks: list[str]
) -> tuple[list[float], float]:
    """
    Compute format scores with a single strict condition.

    Overall format score = 0.1 if and only if ALL of the following are met:
      1. All turns pass code format check
      2. All four key actions have been correctly executed
      3. No user-reported errors across all turns

    Args:
        turn_texts: Assistant responses for each turn
        turn_user_feedbacks: User feedback after each turn

    Returns:
        Tuple of (per-turn format scores, overall format score)
    """
    turn_format_scores = []
    has_any_error = False

    executed_actions = {
        'explore_schema': False,
        'propose_schema': False,
        'generate_sql': False,
        'confirm_answer': False
    }

    action_map = {
        'explore_schema': 'explore_schema',
        'schema': 'propose_schema',
        'generate_sql': 'generate_sql',
        'answer': 'confirm_answer'
    }

    error_markers = ["Invalid format", "try again", "syntax error"]

    for turn_idx, turn_text in enumerate(turn_texts):
        turn_check = check_single_turn_format(turn_text)
        current_score = turn_check["format_score"]
        is_format_valid = turn_check.get("is_valid", False)
        turn_format_scores.append(current_score)

        # Check for user-reported errors
        has_turn_error = False
        if turn_idx < len(turn_user_feedbacks):
            user_feedback = turn_user_feedbacks[turn_idx]
            if user_feedback and any(marker in user_feedback for marker in error_markers):
                has_turn_error = True
                has_any_error = True

        # Record valid action execution (format passed + no user error)
        if is_format_valid and not has_turn_error:
            action, _ = postprocess_predictions(turn_text)
            if action in action_map:
                executed_actions[action_map[action]] = True

    all_format_valid = all(score == 0.1 for score in turn_format_scores)
    all_actions_executed = all(executed_actions.values())
    no_user_errors = not has_any_error

    overall_format_score = 0.1 if (all_format_valid and all_actions_executed and no_user_errors) else 0.0

    return turn_format_scores, overall_format_score


# ==================== Reward Functions ====================
async def reward_func(args, sample, **kwargs):
    """
    Async reward function for NL2SQL task.

    Mode 1 (enable_schema=False): Returns sentence-level scalar reward
        reward = format_score + sql_execution_score

    Mode 2 (enable_schema=True): Returns token-level reward list
        Computes schema_score + sql_score + format_score
        Supported schema_scoring_mode: totalmatch / truematch / recall_then_precision_strict
    """
    if not isinstance(sample, Sample):
        raise TypeError("Sample must be an instance of Sample class.")

    db_root_path = sample.label.get("database", "")
    enable_schema = getattr(args, 'enable_schema', False)
    schema_scoring_mode = getattr(args, 'schema_scoring_mode', 'totalmatch').lower()

    # ===== 1. Compute SQL execution reward =====
    try:
        sql_execution_score = await asyncio.wait_for(
            compute_score_sql_async(
                solution_str=sample.prompt + sample.response,
                ground_truth=sample.label,
                db_root_path=db_root_path,
                timeout=NL2SQL_CONFIGS["sql_execution_timeout"],
                include_schema_score=False,
                thread_pool=_thread_pool
            ),
            timeout=60.0
        )
    except asyncio.TimeoutError:
        print(f"[SQL REWARD TIMEOUT] Exceeded 60s", flush=True)
        sql_execution_score = 0.0
    except Exception as e:
        print(f"[SQL REWARD ERROR] {e}", flush=True)
        sql_execution_score = 0.0

    # ===== 2. Retrieve format score =====
    format_score = getattr(sample, 'overall_format_score', 0.0)
    sample.sql_reward = sql_execution_score + format_score

    # ===== 3. Sentence-level reward (schema disabled) =====
    if not enable_schema:
        total_reward = format_score + sql_execution_score
        sample.reward = total_reward

        if hash(id(sample)) % 128 == 0:
            print(f"[SENTENCE-LEVEL REWARD]", flush=True)
            print(f"  Format score:  {format_score}", flush=True)
            print(f"  SQL score:     {sql_execution_score:.3f}", flush=True)
            print(f"  Total reward:  {total_reward:.3f}", flush=True)

        return total_reward

    # ===== 4. Validate required turn-level attributes =====
    if not hasattr(sample, 'turn_boundaries') or not hasattr(sample, 'turn_format_scores'):
        print(f"[WARNING] Missing turn_boundaries or turn_format_scores, falling back to sentence-level", flush=True)
        total_reward = format_score + sql_execution_score
        sample.reward = total_reward
        return total_reward

    turn_boundaries = sample.turn_boundaries
    turn_format_scores = sample.turn_format_scores
    response_length = sample.response_length

    # ===== 5. Compute schema reward =====
    schema_score = 0.0
    has_valid_schema = False

    is_dummy = getattr(sample, 'is_dummy_schema', False)
    has_cached = hasattr(sample, 'cached_schema_json') and sample.cached_schema_json is not None

    if not is_dummy and has_cached:
        try:
            schema_score = await asyncio.wait_for(
                _compute_schema_reward_async(sample, schema_scoring_mode),
                timeout=5.0
            )
            has_valid_schema = True
        except asyncio.TimeoutError:
            print(f"[SCHEMA REWARD TIMEOUT] Exceeded 5s", flush=True)
        except Exception as e:
            print(f"[SCHEMA REWARD ERROR] {type(e).__name__}: {e}", flush=True)

    schema_end_position = getattr(sample, 'schema_end_position', None)
    use_segmented_propagation = getattr(args, 'use_segmented_propagation', False)

    # Resolve schema turn index
    schema_turn_idx = None
    if has_valid_schema and schema_end_position is not None:
        for turn_idx, (start_pos, end_pos) in enumerate(turn_boundaries):
            if start_pos <= schema_end_position < end_pos:
                schema_turn_idx = turn_idx
                break
        if schema_turn_idx is None:
            schema_turn_idx = len(turn_boundaries) - 1

    # Compute SQL format score
    if use_segmented_propagation:
        if has_valid_schema and schema_turn_idx is not None:
            sql_format_scores = turn_format_scores[schema_turn_idx + 1:]
            sql_format_valid = all(score == 0.1 for score in sql_format_scores) if sql_format_scores else True
            sql_format_score = 0.1 if sql_format_valid else 0.0
        else:
            all_format_valid = all(score == 0.1 for score in turn_format_scores)
            sql_format_score = 0.1 if all_format_valid else 0.0
    else:
        sql_format_score = format_score

    # ===== 6. Build sparse token-level reward =====
    token_rewards = [0.0] * response_length
    sql_reward_total = format_score + sql_execution_score
    token_rewards[response_length - 1] = sql_reward_total

    schema_weight = getattr(args, 'schema_token_weight', 1.0)

    if schema_scoring_mode in ('truematch', 'recall_then_precision_strict'):
        # Only assign schema reward when SQL is correct
        if sql_execution_score == 1.0:
            if has_valid_schema and schema_end_position is not None and schema_end_position < response_length:
                token_rewards[schema_end_position - 1] = schema_score * schema_weight
        else:
            if schema_score:
                print(
                    f"[SCHEMA SKIPPED] schema_score={schema_score:.3f} discarded "
                    f"because sql_execution_score={sql_execution_score:.3f}",
                    flush=True
                )

    elif schema_scoring_mode == 'totalmatch':
        # Assign schema reward regardless of SQL correctness
        if has_valid_schema and schema_end_position is not None and schema_end_position < response_length:
            token_rewards[schema_end_position - 1] = schema_score * schema_weight

    # ===== 7. Save results =====
    sample.reward = token_rewards
    sample.schema_end_position_for_advantage = schema_end_position if schema_end_position is not None else response_length
    sample.schema_reward = schema_score
    sample.has_valid_schema = has_valid_schema

    if hash(id(sample)) % 128 == 0:
        non_zero_positions = [i for i, r in enumerate(token_rewards) if r != 0.0]
        print(f"[TOKEN-LEVEL REWARD]", flush=True)
        print(f"  Schema scoring mode:    {schema_scoring_mode}", flush=True)
        print(f"  Segmented propagation:  {use_segmented_propagation}", flush=True)
        print(f"  Schema score:           {schema_score:.3f}", flush=True)
        print(f"  SQL score:              {sql_execution_score:.3f}", flush=True)
        print(f"  SQL format score:       {sql_format_score}", flush=True)
        print(f"  Has valid schema:       {has_valid_schema}", flush=True)
        print(f"  Non-zero positions:     {non_zero_positions}", flush=True)

    return token_rewards


# ==================== Schema Reward Computation ====================
async def _compute_schema_reward_async(sample: Sample, schema_mode: str = 'totalmatch') -> float:
    """
    Asynchronously compute schema reward (excludes format score).
    Scoring: 0.0 - 1.0 (table score 0.5 + column score 0.5)
    """
    def _compute_sync():
        try:
            if not (hasattr(sample, 'cached_schema_json') and sample.cached_schema_json is not None):
                return 0.0

            try:
                predicted_schema = json.loads(sample.cached_schema_json)
            except json.JSONDecodeError:
                print(f"[SCHEMA COMPUTE ERROR] Failed to parse cached schema JSON", flush=True)
                return 0.0

            ground_truth = sample.label.get('ground_truth', {})
            if isinstance(ground_truth, str):
                try:
                    ground_truth = json.loads(ground_truth)
                except Exception:
                    return 0.0

            ground_truth_schema = ground_truth.get('schema') if isinstance(ground_truth, dict) else None
            if ground_truth_schema is None:
                return 0.0

            schema_scores = compute_schema_linking_score(predicted_schema, ground_truth_schema, schema_mode)
            score = schema_scores['total_score']

            if hash(id(sample)) % 128 == 0:
                mode = schema_scores.get('mode', schema_mode)
                print(f"[SCHEMA LINKING DETAIL]", flush=True)
                print(f"  Total score:   {score:.3f}", flush=True)
                print(f"  Table {mode}:  {schema_scores.get('table_score', 0):.3f}", flush=True)
                print(f"  Column {mode}: {schema_scores.get('column_score', 0):.3f}", flush=True)

            return score

        except Exception as e:
            if hash(id(sample)) % 100 == 0:
                print(f"[SCHEMA COMPUTE ERROR] {e}", flush=True)
            return 0.0

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_thread_pool, _compute_sync)


# ==================== Cleanup ====================
def cleanup():
    """Release thread pool resources"""
    global _thread_pool
    if _thread_pool is not None:
        _thread_pool.shutdown(wait=True)
        _thread_pool = None