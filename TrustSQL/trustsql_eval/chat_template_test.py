"""
Example script to test chat template rendering with Jinja2.

Usage:
    python chat_template_test.py

Set `template_dir` to the directory containing your model's chat_template.jinja file.
"""

from jinja2 import Environment, FileSystemLoader

# Set this to the directory containing your model's chat_template.jinja
template_dir = "/path/to/your/model/directory"

env = Environment(
    loader=FileSystemLoader(template_dir),
    trim_blocks=True,
    lstrip_blocks=True,
)
template = env.get_template("chat_template.jinja")

tools = [
    {
        "type": "code_interpreter",
        "function": {
            "name": "sql-execute_sql_query",
            "description": (
                "Execute SQL query and return partial results containing column names "
                "(maximum 10 records).\n"
                "Args:\n"
                "  db_name (str): The name of the database.\n"
                "  sql (str): The SQL query to execute.\n"
                "Returns:\n"
                "  Dict[str, Union[List[Dict], Dict, None]]: A dictionary containing "
                "'columns' and 'data' of the query (maximum of 10 records).\n"
                "Raises:\n"
                "  TimeoutError: If the query execution exceeds the timeout.\n"
                "  sqlite3.Error: If an error occurs during the query execution."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "db_name": {"title": "Db Name", "type": "string"},
                    "sql": {"title": "Sql", "type": "string"},
                },
                "required": ["db_name", "sql"],
            },
        },
    }
]

messages = [
    {"role": "system", "content": "You are a helpful SQL assistant."},
    {"role": "user", "content": "What is the weather in New York?"},
    {
        "role": "assistant",
        "content": "I will call the weather query tool.",
        "tool_calls": [
            {
                "function": {
                    "name": "get_weather",
                    "arguments": {"city": "New York"},
                }
            }
        ],
    },
    {"role": "tool", "content": "Sunny, 72°F"},
]

output = template.render(
    tools=tools,
    tool_choice="auto",
    messages=messages,
    add_generation_prompt=False,
)

print(output)
