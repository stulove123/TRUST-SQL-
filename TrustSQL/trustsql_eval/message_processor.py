import re
import os
import sqlite3
import asyncio
from typing import Dict, List, Optional, Tuple
import json
from concurrent.futures import ThreadPoolExecutor

# Global SQL execution configuration
SQL_EXECUTION_CONFIG = {
    "timeout": 15.0,
    "max_workers": 64,
    "semaphore_limit": 64,
}

# Dedicated thread pool and semaphore for SQL execution
_thread_pool = ThreadPoolExecutor(max_workers=SQL_EXECUTION_CONFIG["max_workers"])
_semaphore = asyncio.Semaphore(SQL_EXECUTION_CONFIG["semaphore_limit"])

# Safety check: only allow read-only SQL prefixes
ALLOWED_SQL_PREFIXES = ('SELECT', 'PRAGMA', 'EXPLAIN')


def is_sql_readonly(sql: str) -> Tuple[bool, Optional[str]]:
    """Check whether a SQL statement is read-only."""
    sql_stripped = sql.strip()

    # Strip leading comments
    while sql_stripped.startswith('--') or sql_stripped.startswith('/*'):
        if sql_stripped.startswith('--'):
            newline_pos = sql_stripped.find('\n')
            if newline_pos == -1:
                return False, "SQL contains only comments"
            sql_stripped = sql_stripped[newline_pos + 1:].strip()
        elif sql_stripped.startswith('/*'):
            end_pos = sql_stripped.find('*/')
            if end_pos == -1:
                return False, "Unclosed comment"
            sql_stripped = sql_stripped[end_pos + 2:].strip()

    if not sql_stripped:
        return False, "Empty SQL query"

    if sql_stripped.upper().startswith(ALLOWED_SQL_PREFIXES):
        return True, None

    first_word = sql_stripped.split()[0] if sql_stripped else "EMPTY"
    return False, f"SQL must start with {ALLOWED_SQL_PREFIXES}, got: {first_word}"


def _format_execution_result(execution_result: Dict) -> str:
    """Uniformly format a SQL execution result dict into a string."""
    if "error" in execution_result:
        return f"Error: {execution_result['error']}"

    content = execution_result.get("content", "")
    if content:
        return content

    return "Query executed successfully."


def _find_db_path(databases_path: str, db_id: str) -> Optional[str]:
    """
    Unified database path lookup that supports multiple directory layouts:

    Format 1 (BIRD):    {databases_path}/{db_id}/{db_id}.sqlite
    Format 2 (Spider2): {databases_path}/{db_id}.sqlite
    Format 3 (direct):  {databases_path}  (databases_path is itself a .sqlite file)
    """
    # Format 3: databases_path is itself a sqlite file
    if databases_path.endswith('.sqlite') and os.path.exists(databases_path):
        return databases_path

    # Format 1: BIRD-style, with an intermediate folder
    path1 = os.path.join(databases_path, db_id, f"{db_id}.sqlite")
    if os.path.exists(path1):
        return path1

    # Format 2: Spider2-style, directly under the root directory
    path2 = os.path.join(databases_path, f"{db_id}.sqlite")
    if os.path.exists(path2):
        return path2

    return None


def _execute_sql_sync(db_id: str, sql_query: str, databases_path: str, max_rows: int = 100) -> Dict:
    """
    Synchronously execute a SQL query (used inside the thread pool).
    Compatible with both BIRD and Spider2 path formats.
    """
    conn = None
    try:
        db_path = _find_db_path(databases_path, db_id)

        if not db_path:
            tried = [
                databases_path,
                os.path.join(databases_path, db_id, f"{db_id}.sqlite"),
                os.path.join(databases_path, f"{db_id}.sqlite"),
            ]
            return {"error": f"Database file not found. Tried:\n" + "\n".join(f"  - {p}" for p in tried)}

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
            result_lines.append("\t".join(str(value) if value is not None else "NULL" for value in row))

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
            except:
                pass


async def execute_sql_local(db_id: str, sql_query: str, databases_path: str, timeout: float = None) -> str:
    """
    Asynchronously execute a SQL query locally. Returns a string result.
    """
    if timeout is None:
        timeout = SQL_EXECUTION_CONFIG["timeout"]

    try:
        async with _semaphore:
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    _thread_pool,
                    _execute_sql_sync,
                    db_id,
                    sql_query,
                    databases_path
                ),
                timeout=timeout
            )

        return _format_execution_result(result)

    except asyncio.TimeoutError:
        return f"Error: SQL execution timeout (exceeded {timeout}s). The query may be too complex or the database is too large."
    except Exception as e:
        return f"Error: Execution error: {str(e)}"


class MessageProcessor:
    def __init__(self, args):
        self.args = args
        self.tokenizer = getattr(args, 'tokenizer', None)
        self.max_obs_tokens = getattr(args, 'max_obs_tokens', 2048)
        self._last_parse_error = None  # Track the last parse error
        self.max_rounds = getattr(args, 'max_rounds', 10)  # Maximum number of rounds

    def _format_progress_prefix(self, current_round: int) -> str:
        """Generate a progress prefix; add a warning when approaching the round limit."""
        base_prefix = f"This is turn {current_round + 1} of {self.max_rounds}.\n\n"

        remaining_turns = self.max_rounds - (current_round + 1)

        if remaining_turns == 0:
            return ""

        if remaining_turns == 1:
            # Second-to-last round
            warning = (
                "Only 1 turn remaining after this.\n"
                "You MUST provide the final answer in the next turn.\n\n"
                "Use <action>confirm_answer</action> with your best SQL query.\n"
                "If you don't have a complete solution, provide your best attempt.\n\n"
            )
            return base_prefix + warning

        elif remaining_turns == 2:
            # Third-to-last round
            warning = (
                "Only 2 turns remaining after this.\n"
                "Start preparing your final SQL query.\n\n"
            )
            return base_prefix + warning

        else:
            return base_prefix

    def _get_databases_path(self, item: Dict) -> Optional[str]:
        """Extract databases_path from the item dict (supports multiple formats)."""
        try:
            # Try multiple possible paths in priority order
            possible_paths = [
                # Priority 1: reward_model.database
                ('reward_model.database', item.get('reward_model', {}).get('database')),

                # Priority 2: reward_model.ground_truth.database
                ('reward_model.ground_truth.database',
                 item.get('reward_model', {}).get('ground_truth', {}).get('database')),

                # Priority 3: extra_info.database
                ('extra_info.database', item.get('extra_info', {}).get('database')),

                # Priority 4: top-level database
                ('database', item.get('database')),

                # Priority 5: top-level databases_path
                ('databases_path', item.get('databases_path')),
            ]

            for path_name, path_value in possible_paths:
                if path_value and isinstance(path_value, str):
                    return path_value

            # If none found, print debug information
            print(f"[ERROR] databases_path not found in item")
            print(f"[DEBUG] Available top-level keys: {list(item.keys())}")
            if 'reward_model' in item:
                print(f"[DEBUG] reward_model keys: {list(item['reward_model'].keys())}")
                if 'ground_truth' in item['reward_model']:
                    print(f"[DEBUG] ground_truth keys: {list(item['reward_model']['ground_truth'].keys())}")
            if 'extra_info' in item:
                print(f"[DEBUG] extra_info keys: {list(item['extra_info'].keys())}")

            return None

        except Exception as e:
            print(f"[ERROR] Failed to extract databases_path: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _validate_database_path(self, databases_path: str, db_id: str) -> Tuple[bool, Optional[str]]:
        """Validate the database path; compatible with BIRD and Spider2 formats."""
        try:
            if not os.path.exists(databases_path):
                return False, f"Database directory does not exist: {databases_path}"

            db_path = _find_db_path(databases_path, db_id)
            if not db_path:
                tried = [
                    databases_path,
                    os.path.join(databases_path, db_id, f"{db_id}.sqlite"),
                    os.path.join(databases_path, f"{db_id}.sqlite"),
                ]
                return False, (
                    f"Database file not found for db_id='{db_id}'. Tried:\n"
                    + "\n".join(f"  - {p}" for p in tried)
                )

            return True, None
        except Exception as e:
            return False, f"Path validation error: {str(e)}"

    def _truncate_observation_tokens(self, text: str, max_tokens: int = None) -> str:
        """Truncate observation text to a maximum number of tokens."""
        if max_tokens is None:
            max_tokens = self.max_obs_tokens

        if not self.tokenizer:
            max_chars = max_tokens * 4
            if len(text) <= max_chars:
                return text
            return text[:max_chars] + "\n... (result truncated due to length)"

        try:
            obs_tokens = self.tokenizer(text, add_special_tokens=False)["input_ids"]
            original_length = len(obs_tokens)

            if original_length <= max_tokens:
                return text

            print(f"[WARNING] Observation truncated: {original_length} -> {max_tokens} tokens")
            truncated_tokens = obs_tokens[:max_tokens]
            truncated_text = self.tokenizer.decode(truncated_tokens) + "\n... (result truncated due to length)"

            return truncated_text

        except Exception as e:
            print(f"[WARNING] Tokenization failed: {e}, using character-based truncation")
            max_chars = max_tokens * 4
            if len(text) <= max_chars:
                return text
            return text[:max_chars] + "\n... (result truncated due to length)"

    def _contains_answer_tag(self, content):
        """Check whether the content contains an <answer> tag."""
        answer_pattern = r'<answer>.*?</answer>'
        return bool(re.search(answer_pattern, content, re.DOTALL | re.IGNORECASE))

    def _contains_schema_tag(self, content):
        """Check whether the content contains a <schema> tag."""
        return bool(re.search(r'<schema>.*?</schema>', content, re.DOTALL | re.IGNORECASE))

    def _extract_action(self, content):
        """Extract the content of the <action> tag."""
        action_pattern = r'<action>(.*?)</action>'
        match = re.search(action_pattern, content, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip().lower()
        return None

    async def process_round(self, llm_response, item, messages, conversation_history, current_round: int = 0):
        """Process a single conversation round."""
        # Generate progress prefix
        progress_prefix = self._format_progress_prefix(current_round)

        # 1. Check for <answer> tag (termination condition)
        if self._contains_answer_tag(llm_response):
            messages.append({"role": "assistant", "content": llm_response})
            conversation_history.append({
                "role": "assistant",
                "content": llm_response,
                "tool_calls": []
            })
            return {"terminated": True, "has_answer": True}

        # Fix malformed tool tag if needed
        llm_response = self._fix_tool_tag_if_needed(llm_response)

        # 2. Check for <schema> tag
        if self._contains_schema_tag(llm_response):
            messages.append({"role": "assistant", "content": llm_response})
            conversation_history.append({
                "role": "assistant",
                "content": llm_response,
                "tool_calls": []
            })

            try:
                schema_match = re.search(r'<schema>(.*?)</schema>', llm_response, re.DOTALL)
                if schema_match:
                    schema_data = json.loads(schema_match.group(1))
                    tables = schema_data.get('tables', [])
                    columns = schema_data.get('columns', {})

                    if isinstance(columns, dict):
                        col_count = sum(len(cols) for cols in columns.values())
                    elif isinstance(columns, list):
                        col_count = len(columns)
                    else:
                        col_count = 0

                    schema_feedback = (
                        progress_prefix +
                        f"Schema acknowledged: {len(tables)} table(s), "
                        f"{col_count} column(s). "
                        "You may now proceed to generate SQL.\n"
                    )
                else:
                    schema_feedback = progress_prefix + "Schema acknowledged. You may proceed to generate SQL.\n"
            except json.JSONDecodeError:
                schema_feedback = progress_prefix + "Schema acknowledged. You may proceed to generate SQL.\n"

            feedback_msg = {"role": "user", "content": schema_feedback}
            messages.append(feedback_msg)
            conversation_history.append(feedback_msg)

            return {"continue": True}

        # 3. Parse tool calls (with error information)
        assistant_content, tool_calls, preserved_content = self.parse_assistant_message(llm_response, item)
        parse_error = self._last_parse_error

        # 4. Handle the case where no tool calls were found
        if not tool_calls:
            messages.append({"role": "assistant", "content": llm_response})
            conversation_history.append({
                "role": "assistant",
                "content": assistant_content,
                "tool_calls": []
            })

            if parse_error:
                error_feedback = (
                    progress_prefix +
                    f"Tool call parsing error:\n{parse_error}\n\n"
                    "Please fix the JSON format and try again. Common issues:\n"
                    "1. Ensure all quotes are properly escaped\n"
                    "2. Remove any unescaped newlines in SQL strings\n"
                    "3. Check for missing or extra commas\n"
                    "4. Verify all brackets and braces are matched\n"
                    "5. Ensure 'name' and 'arguments' fields are present\n\n"
                    "Required format:\n"
                    '<tool_call>{"name": "execute_sql_query", "arguments": {"db_id": "...", "sql": "..."}}</tool_call>\n\n'
                    "Example:\n"
                    '<tool_call>{"name": "execute_sql_query", "arguments": {"db_id": "concert_singer", "sql": "SELECT * FROM singer LIMIT 5"}}</tool_call>\n'
                )
            else:
                error_feedback = (
                    progress_prefix +
                    "Invalid format detected. Your response is missing required components.\n\n"
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
                )

            user_msg = {"role": "user", "content": error_feedback}
            messages.append(user_msg)
            conversation_history.append(user_msg)
            return {"continue": True}

        # 5. Normal tool call processing (async execution)
        messages.append({"role": "assistant", "content": preserved_content})
        conversation_history.append({
            "role": "assistant",
            "content": assistant_content,
            "tool_calls": tool_calls
        })

        action_type = self._extract_action(llm_response)

        exec_results = await self.execute_tool_calls_async(tool_calls, item, current_round)

        for tool_call, exec_result in zip(tool_calls, exec_results):
            truncated_content = self._truncate_observation_tokens(exec_result)
            wrapped_content = self._wrap_result_by_action(truncated_content, action_type)

            conversation_history.append({
                "role": "user",
                "content": wrapped_content
            })

            messages.append({
                "role": "user",
                "content": wrapped_content
            })

        return {"continue": True}

    def _wrap_result_by_action(self, content: str, action_type: str) -> str:
        """Wrap the result with appropriate tags based on the action type."""
        return content

    def parse_assistant_message(self, content, item):
        """Parse assistant message, separating content and tool_calls."""
        tool_call_pattern = r'<tool_call>(.*?)</tool_call>'
        matches = list(re.finditer(tool_call_pattern, content, re.DOTALL))

        if not matches:
            self._last_parse_error = None
            return content, [], content

        first_match = matches[0]
        pre_tool_call_content = content[:first_match.start()].strip()
        first_tool_call_end = first_match.end()
        preserved_content = content[:first_tool_call_end]

        tool_calls, error_msg = self.parse_tool_calls(preserved_content, item)
        self._last_parse_error = error_msg

        return pre_tool_call_content, tool_calls, preserved_content

    def _fix_tool_tag_if_needed(self, content: str) -> str:
        """Replace <tool>…</tool> with <tool_call>…</tool_call>."""
        content = re.sub(r"<tool>(.*?)</tool>",
                         r"<tool_call>\1</tool_call>",
                         content, flags=re.DOTALL)
        content = re.sub(r"<tools>(.*?)</tools>",
                         r"<tool_call>\1</tool_call>",
                         content, flags=re.DOTALL)
        return content

    def parse_tool_calls(self, content, item) -> Tuple[List[Dict], Optional[str]]:
        """Parse tool calls from content; supports multi-line JSON format."""
        tool_calls = []
        error_msg = None

        pattern = r'<tool_call>(.*?)</tool_call>'
        matches = re.findall(pattern, content, re.DOTALL)

        if not matches:
            return [], None

        match = matches[0].strip()

        try:
            tool_call_data = json.loads(match)

            if not isinstance(tool_call_data, dict):
                error_msg = f"Tool call must be a JSON object, got: {type(tool_call_data).__name__}"
                return [], error_msg

            function_name = tool_call_data.get("name", "")
            arguments = tool_call_data.get("arguments", {})

            if not isinstance(function_name, str) or not function_name:
                error_msg = f"Missing or invalid 'name' field. Expected non-empty string, got: {repr(function_name)}"
                return [], error_msg

            if not isinstance(arguments, dict):
                error_msg = f"'arguments' must be a JSON object, got: {type(arguments).__name__}"
                return [], error_msg

            if function_name == "execute_sql_query":
                is_valid, validation_error = self._validate_sql_arguments(arguments)
                if not is_valid:
                    return [], validation_error

            tool_calls.append({
                "name": function_name,
                "arguments": arguments
            })

            return tool_calls, None

        except json.JSONDecodeError as e:
            error_msg = (
                f"JSON parsing failed at line {e.lineno}, column {e.colno}: {e.msg}\n\n"
                f"Problematic content:\n{match}\n\n"
                f"Common fixes:\n"
                f"- Check for unescaped quotes in strings (use \\\" inside strings)\n"
                f"- Remove trailing commas before closing braces\n"
                f"- Ensure all brackets and braces are properly matched\n"
                f"- Use double quotes for JSON keys and string values"
            )
            return [], error_msg
        except Exception as e:
            error_msg = f"Unexpected parsing error: {str(e)}"
            return [], error_msg

    def _validate_sql_arguments(self, arguments: dict) -> Tuple[bool, Optional[str]]:
        """Validate SQL query arguments; returns (is_valid, error_message)."""
        if "sql" not in arguments:
            return False, "Missing required argument 'sql' in tool call arguments"

        sql = arguments.get("sql", "")

        if not isinstance(sql, str):
            return False, f"'sql' argument must be a string, got: {type(sql).__name__}"

        if not sql.strip():
            return False, "'sql' query cannot be empty or whitespace-only"

        db_id = arguments.get("db_id")
        if db_id is not None and not isinstance(db_id, str):
            return False, f"'db_id' argument must be a string, got: {type(db_id).__name__}"

        return True, None

    async def execute_tool_calls_async(self, tool_calls: List[Dict], item: Dict, current_round: int = 0) -> List[str]:
        """Asynchronously execute a list of tool calls."""
        if not tool_calls:
            return []

        progress_prefix = self._format_progress_prefix(current_round)

        tasks = [self.execute_single_tool_async(tool_call, item) for tool_call in tool_calls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"[ERROR] Tool call {i} failed: {result}")
                processed_results.append(progress_prefix + f"Error: Tool execution error: {str(result)}")
            else:
                processed_results.append(progress_prefix + result)

        return processed_results

    async def execute_single_tool_async(self, tool_call: Dict, item: Dict) -> str:
        """Asynchronously execute a single tool call; returns a string result."""
        function_name = tool_call.get("name")
        arguments = tool_call.get("arguments", {})

        if function_name == "execute_sql_query":
            try:
                result = await asyncio.wait_for(
                    self.execute_sql_query_async(arguments, item),
                    timeout=SQL_EXECUTION_CONFIG["timeout"]
                )
                return result
            except asyncio.TimeoutError:
                return f"Error: SQL execution timeout (exceeded {SQL_EXECUTION_CONFIG['timeout']}s)"
            except Exception as e:
                return f"Error: Tool execution error: {str(e)}"
        else:
            return f"Error: Unknown function: {function_name}"

    async def execute_sql_query_async(self, arguments: Dict, item: Dict) -> str:
        """
        Asynchronously execute a SQL query; returns a string result.
        Retrieves databases_path from the item dict.
        """
        sql_query = arguments.get("sql", "").strip()

        if not sql_query:
            return "Error: SQL query is empty"

        db_id = arguments.get("db_id") or item.get('db_id')
        if not db_id:
            return "Error: Database ID not found in item"

        databases_path = self._get_databases_path(item)
        if not databases_path:
            return "Error: Database path not found in item. Please ensure 'database' field exists in reward_model.ground_truth or extra_info."

        is_valid, error_msg = self._validate_database_path(databases_path, db_id)
        if not is_valid:
            return f"Error: {error_msg}"

        try:
            result = await execute_sql_local(
                db_id=db_id,
                sql_query=sql_query,
                databases_path=databases_path,
                timeout=SQL_EXECUTION_CONFIG["timeout"]
            )

            if result.startswith("Error:") and self.tokenizer:
                try:
                    error_tokens = self.tokenizer(result, add_special_tokens=False)["input_ids"]
                    if len(error_tokens) > 500:
                        truncated_tokens = error_tokens[:500]
                        result = self.tokenizer.decode(truncated_tokens) + "... (error truncated)"
                except:
                    pass

            return result

        except Exception as e:
            error_msg = f"Error: SQL execution error: {str(e)}"
            if self.tokenizer:
                try:
                    error_tokens = self.tokenizer(error_msg, add_special_tokens=False)["input_ids"]
                    if len(error_tokens) > 500:
                        truncated_tokens = error_tokens[:500]
                        error_msg = self.tokenizer.decode(truncated_tokens) + "... (error truncated)"
                except:
                    pass
            return error_msg


def force_cleanup():
    global _thread_pool
    if _thread_pool:
        _thread_pool.shutdown(wait=False)
        _thread_pool = None


import atexit
atexit.register(force_cleanup)
