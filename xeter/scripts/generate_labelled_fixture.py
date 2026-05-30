# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
"""Generate synthetic labelled spans for calibration.

Produces fixtures/labelled_spans.jsonl with 210 original spans plus new type spans:
  - 63 flagged (~30%) covering all six original anomaly types
  - 147 clean (~70%)
  - 17 new flag types (Phases 24/25/26): ≥8 flagged groups + ≥8 clean groups each

Each line is a JSON object with all SpanData fields plus:
  - label: "flagged" | "clean"
  - anomaly_type: one of the flag types, or null for clean spans

For trace-level types, multiple rows share a trace_id; the LAST row carries the label.

Run:
    python xeter/scripts/generate_labelled_fixture.py

Output: fixtures/labelled_spans.jsonl (deterministic via SEED=42 for original rows,
        NEW_SEED=27 for new type rows)
"""

from __future__ import annotations

import json
import random
import sys
import uuid
from pathlib import Path

# ---------------------------------------------------------------------------
# Deterministic seed — MUST NOT be changed once fixture is committed
# ---------------------------------------------------------------------------
SEED = 42
rng = random.Random(SEED)

# ---------------------------------------------------------------------------
# New-type seed — separate rng for Phase 24/25/26 additions (NEW_SEED=27)
# Keeps existing 100 rows stable when new types are added
# ---------------------------------------------------------------------------
NEW_SEED = 27

PROJECT_ROOT = Path(__file__).parent.parent.parent
FIXTURE_PATH = PROJECT_ROOT / "fixtures" / "labelled_spans.jsonl"

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

AGENT_MODEL = "gpt-4o"  # In TOOL_CALL_REGISTRY; api_structured transport

# Valid raw_response for gpt-4o (no tool call detected pattern, so no parsing error)
CLEAN_RAW_RESPONSE = json.dumps({
    "id": "chatcmpl-abc123",
    "object": "chat.completion",
    "model": "gpt-4o",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "I can help you with that.",
            },
            "finish_reason": "stop",
        }
    ],
})

# Malformed JSON for parsing_error spans
MALFORMED_RAW_RESPONSE = '{"id": "chatcmpl-bad", "tool_calls": [BROKEN JSON'

# gpt-4o raw_response WITH tool_calls (triggers detect patterns, but valid JSON)
def make_tool_call_raw_response(fn_name: str, args: dict) -> str:
    return json.dumps({
        "id": "chatcmpl-tc123",
        "object": "chat.completion",
        "model": "gpt-4o",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_abc",
                            "type": "function",
                            "function": {
                                "name": fn_name,
                                "arguments": json.dumps(args),
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
    })


# ---------------------------------------------------------------------------
# Tool catalogue — realistic tools used across spans
# ---------------------------------------------------------------------------

WEB_SEARCH_TOOL = {"name": "web_search", "description": "Search the internet for information"}
SQL_TOOL = {"name": "execute_sql", "description": "Execute a SQL query against a database"}
EMAIL_TOOL = {"name": "send_email", "description": "Send an email message to a recipient"}
CALENDAR_TOOL = {"name": "create_event", "description": "Create a calendar event or meeting"}
WEATHER_TOOL = {"name": "get_weather", "description": "Get current weather and forecasts for a location"}
FILE_TOOL = {"name": "read_file", "description": "Read the contents of a file from the filesystem"}
TRANSLATE_TOOL = {"name": "translate_text", "description": "Translate text between languages"}
CALCULATOR_TOOL = {"name": "calculate", "description": "Perform mathematical calculations"}
CODE_EXEC_TOOL = {"name": "execute_code", "description": "Execute Python code in a sandbox"}
NEWS_TOOL = {"name": "get_news", "description": "Fetch latest news articles on a topic"}
MAPS_TOOL = {"name": "get_directions", "description": "Get driving or walking directions between locations"}
SUMMARIZE_TOOL = {"name": "summarize_text", "description": "Summarize a long document or text"}

ALL_TOOLS = [
    WEB_SEARCH_TOOL, SQL_TOOL, EMAIL_TOOL, CALENDAR_TOOL, WEATHER_TOOL,
    FILE_TOOL, TRANSLATE_TOOL, CALCULATOR_TOOL, CODE_EXEC_TOOL, NEWS_TOOL,
    MAPS_TOOL, SUMMARIZE_TOOL,
]


def pick_tools(primary: dict, n_others: int = 3) -> list[dict]:
    """Pick primary tool plus n_others distinct tools."""
    others = [t for t in ALL_TOOLS if t["name"] != primary["name"]]
    chosen = rng.sample(others, n_others)
    # Primary is NOT first (it'll be placed in mixed position for clean spans)
    result = chosen + [primary]
    rng.shuffle(result)
    return result


# ---------------------------------------------------------------------------
# Clean span templates
# ---------------------------------------------------------------------------

CLEAN_TEMPLATES = [
    # (prompt, tool, tool_description, tool_arguments_dict, response)
    (
        "Search the web for Python documentation on list comprehensions.",
        "web_search",
        "Search the internet for information",
        {"query": "Python list comprehensions documentation"},
        "I found the official Python documentation on list comprehensions at docs.python.org.",
    ),
    (
        "Send an email to bob@company.com with subject 'Q4 Report' and body 'Please review the attached report.'",
        "send_email",
        "Send an email message to a recipient",
        {"to": "bob@company.com", "subject": "Q4 Report", "body": "Please review the attached report."},
        "Email sent successfully to bob@company.com.",
    ),
    (
        "What is the weather in London right now?",
        "get_weather",
        "Get current weather and forecasts for a location",
        {"location": "London", "units": "celsius"},
        "Current weather in London: 14°C, partly cloudy with a chance of rain.",
    ),
    (
        "Create a calendar meeting for Monday at 2pm called 'Sprint Planning'.",
        "create_event",
        "Create a calendar event or meeting",
        {"title": "Sprint Planning", "start": "Monday 14:00", "duration_minutes": 60},
        "Calendar event 'Sprint Planning' created for Monday at 2:00 PM.",
    ),
    (
        "Read the config file at /etc/app/config.yaml.",
        "read_file",
        "Read the contents of a file from the filesystem",
        {"path": "/etc/app/config.yaml"},
        "File contents: database_url: postgres://localhost/mydb\nport: 8080",
    ),
    (
        "Translate 'Hello, how are you?' from English to Spanish.",
        "translate_text",
        "Translate text between languages",
        {"text": "Hello, how are you?", "source_lang": "en", "target_lang": "es"},
        "Translation: '¿Hola, cómo estás?'",
    ),
    (
        "Calculate 15% tip on a $87.50 restaurant bill.",
        "calculate",
        "Perform mathematical calculations",
        {"expression": "87.50 * 0.15"},
        "15% tip on $87.50 is $13.13. Total with tip: $100.63.",
    ),
    (
        "Run the Python script to check if 97 is a prime number.",
        "execute_code",
        "Execute Python code in a sandbox",
        {"code": "n=97; print(all(n%i!=0 for i in range(2,n)))"},
        "True — 97 is a prime number.",
    ),
    (
        "Get the latest news about artificial intelligence breakthroughs.",
        "get_news",
        "Fetch latest news articles on a topic",
        {"topic": "artificial intelligence", "max_results": 5},
        "Top AI news: 1. New model achieves SOTA on reasoning benchmarks...",
    ),
    (
        "Get directions from New York to Philadelphia by car.",
        "get_directions",
        "Get driving or walking directions between locations",
        {"from": "New York, NY", "to": "Philadelphia, PA", "mode": "driving"},
        "Drive south on I-95 for approximately 95 miles. Estimated time: 1h 45min.",
    ),
    (
        "Summarize this research paper about transformer architectures.",
        "summarize_text",
        "Summarize a long document or text",
        {"text": "Attention is All You Need introduces the transformer model...", "max_length": 150},
        "Summary: The transformer model uses self-attention mechanisms instead of recurrent layers, enabling parallelism and better long-range dependency modeling.",
    ),
    (
        "Search online for best practices in Python error handling.",
        "web_search",
        "Search the internet for information",
        {"query": "Python error handling best practices 2024"},
        "Found several articles on Python exception handling. Key practices include using specific exceptions and logging errors properly.",
    ),
    (
        "Execute SQL to count active users in the database.",
        "execute_sql",
        "Execute a SQL query against a database",
        {"query": "SELECT COUNT(*) FROM users WHERE is_active = true"},
        "Query result: 1,247 active users.",
    ),
    (
        "Send a notification email to alice@example.com about the deployment.",
        "send_email",
        "Send an email message to a recipient",
        {"to": "alice@example.com", "subject": "Deployment Successful", "body": "The v2.1 deployment completed successfully."},
        "Notification email sent to alice@example.com.",
    ),
    (
        "Check the weather forecast for Paris for the next 3 days.",
        "get_weather",
        "Get current weather and forecasts for a location",
        {"location": "Paris", "days": 3},
        "Paris 3-day forecast: Saturday 18°C sunny, Sunday 16°C cloudy, Monday 14°C rainy.",
    ),
    (
        "Schedule a team sync meeting on Wednesday at 10am.",
        "create_event",
        "Create a calendar event or meeting",
        {"title": "Team Sync", "start": "Wednesday 10:00", "duration_minutes": 30},
        "Team Sync meeting scheduled for Wednesday at 10:00 AM.",
    ),
    (
        "Read the deployment log at /var/log/deploy.log.",
        "read_file",
        "Read the contents of a file from the filesystem",
        {"path": "/var/log/deploy.log"},
        "Log shows: Deploy started 09:12, completed 09:18, 0 errors.",
    ),
    (
        "Translate the word 'bonjour' from French to English.",
        "translate_text",
        "Translate text between languages",
        {"text": "bonjour", "source_lang": "fr", "target_lang": "en"},
        "Translation: 'hello'",
    ),
    (
        "Calculate compound interest on $10,000 at 5% for 3 years.",
        "calculate",
        "Perform mathematical calculations",
        {"expression": "10000 * (1 + 0.05) ** 3"},
        "Compound interest result: $11,576.25",
    ),
    (
        "Run Python code to reverse the string 'hello world'.",
        "execute_code",
        "Execute Python code in a sandbox",
        {"code": "print('hello world'[::-1])"},
        "Output: 'dlrow olleh'",
    ),
]


# ---------------------------------------------------------------------------
# Flagged span templates (anomaly OBVIOUS, strong signal)
# ---------------------------------------------------------------------------

def make_wrong_tool_span(i: int) -> dict:
    """Prompt says 'search the web' but tool is execute_sql; web_search ranks higher."""
    prompt = rng.choice([
        "Search the web for information about climate change impacts.",
        "Look up online articles about machine learning tutorials.",
        "Find web pages about Python asyncio documentation.",
        "Search the internet for the latest cryptocurrency prices.",
        "Look up news articles about space exploration missions.",
        "Search online for restaurant recommendations in Seattle.",
        "Find web resources about quantum computing fundamentals.",
        "Search the web for Python packaging best practices.",
        "Look up information about renewable energy solutions online.",
        "Find articles about remote work productivity tips on the web.",
    ])
    # Tool used is SQL but prompt demands web search
    available = [
        WEB_SEARCH_TOOL,  # correct tool, ranked higher
        SQL_TOOL,         # wrong tool actually called
        CALENDAR_TOOL,
        FILE_TOOL,
    ]
    return {
        "prompt": prompt,
        "tool_name": "execute_sql",
        "tool_description": "Execute a SQL query against a database",
        "tool_arguments": json.dumps({"query": "SELECT * FROM web_index LIMIT 10"}),
        "tool_output": "No rows returned",
        "response": "I searched the database but found no relevant results.",
        "available_tools": available,
        "label": "flagged",
        "anomaly_type": "wrong_tool_choice",
    }


def make_wrong_tool_args_span(i: int) -> dict:
    """Prompt says 'email Alice at alice@example.com' but args use Bob's email."""
    prompts_and_args = [
        (
            "Send an email to alice@example.com with the project update.",
            {"to": "bob@otherdomain.com", "subject": "Budget Meeting", "body": "Please prepare next quarter budget."},
        ),
        (
            "Email carol@company.com about the Q3 results presentation.",
            {"to": "dave@unrelated.org", "subject": "Team Outing", "body": "Let's plan a team outing next month."},
        ),
        (
            "Send meeting notes to frank@engineering.com from today's standup.",
            {"to": "grace@marketing.com", "subject": "Product Launch", "body": "The launch is scheduled for Friday."},
        ),
        (
            "Notify helen@example.com that her pull request was approved.",
            {"to": "ivan@example.com", "subject": "Invoice Due", "body": "Your invoice is overdue. Please pay ASAP."},
        ),
        (
            "Email support@company.com with the customer complaint details.",
            {"to": "sales@competitor.com", "subject": "Partnership Proposal", "body": "We'd like to discuss a partnership."},
        ),
    ]
    prompt, args = prompts_and_args[i % len(prompts_and_args)]
    available = [EMAIL_TOOL, WEB_SEARCH_TOOL, CALENDAR_TOOL, FILE_TOOL]
    return {
        "prompt": prompt,
        "tool_name": "send_email",
        "tool_description": "Send an email message to a recipient",
        "tool_arguments": json.dumps(args),
        "tool_output": "Email delivered",
        "response": "I sent the email as requested.",
        "available_tools": available,
        "label": "flagged",
        "anomaly_type": "wrong_tool_args",
    }


def make_no_tool_span(i: int) -> dict:
    """Prompt explicitly asks to call a function/tool but tool_name is None."""
    prompts = [
        "Please call the search function to look up current stock prices for AAPL.",
        "Use the weather tool to get the forecast for Chicago tomorrow.",
        "Invoke the calculate function to compute the square root of 144.",
        "Call the translate tool to convert 'good morning' to Japanese.",
        "Use the database query tool to find all orders placed this week.",
        "Please call the file reader function to load the configuration file.",
        "Invoke the news fetch tool to get headlines about climate policy.",
        "Use the mapping function to get directions from Boston to Providence.",
        "Call the code execution tool to run the fibonacci sequence script.",
        "Please use the email sending function to notify the team about the outage.",
    ]
    return {
        "prompt": prompts[i % len(prompts)],
        "tool_name": None,
        "tool_description": None,
        "tool_arguments": None,
        "tool_output": None,
        "response": "I'll help you with that request.",
        "available_tools": [WEB_SEARCH_TOOL, WEATHER_TOOL, CALCULATOR_TOOL, TRANSLATOR_TOOL := TRANSLATE_TOOL],
        "label": "flagged",
        "anomaly_type": "no_tool",
    }


def make_unnecessary_tool_call_span(i: int) -> dict:
    """Simple conversational prompt (greeting/chitchat) but a database tool was called."""
    prompts_and_tools = [
        ("Hello, how are you doing today?", "execute_sql", "Execute a SQL query against a database",
         json.dumps({"query": "SELECT status FROM system_health"})),
        ("Good morning! Have a great day.", "execute_code", "Execute Python code in a sandbox",
         json.dumps({"code": "import datetime; print(datetime.datetime.now())"})),
        ("Thanks for your help!", "execute_sql", "Execute a SQL query against a database",
         json.dumps({"query": "INSERT INTO audit_log VALUES (NOW(), 'thanks')"})),
        ("Goodbye, see you later.", "execute_code", "Execute Python code in a sandbox",
         json.dumps({"code": "print('Session terminated')"})),
        ("What is your name?", "execute_sql", "Execute a SQL query against a database",
         json.dumps({"query": "SELECT name FROM agents WHERE id = 1"})),
        ("I understand.", "execute_code", "Execute Python code in a sandbox",
         json.dumps({"code": "logging.info('User acknowledged')"})),
        ("That makes sense, thank you.", "execute_sql", "Execute a SQL query against a database",
         json.dumps({"query": "UPDATE conversation_state SET ack=true WHERE session_id='abc'"})),
        ("Nice to meet you!", "execute_sql", "Execute a SQL query against a database",
         json.dumps({"query": "INSERT INTO contacts (greeting_time) VALUES (NOW())"})),
    ]
    prompt, tool_name, tool_desc, args = prompts_and_tools[i % len(prompts_and_tools)]
    available = [SQL_TOOL, CODE_EXEC_TOOL, WEB_SEARCH_TOOL, WEATHER_TOOL]
    return {
        "prompt": prompt,
        "tool_name": tool_name,
        "tool_description": tool_desc,
        "tool_arguments": args,
        "tool_output": "OK",
        "response": "Sure, I've processed your message.",
        "available_tools": available,
        "label": "flagged",
        "anomaly_type": "unnecessary_tool_call",
    }


def make_parsing_error_span(i: int) -> dict:
    """gpt-4o (api_structured) with intentionally malformed raw_response JSON."""
    malformed_variants = [
        '{"id": "chatcmpl-err", "tool_calls": [BROKEN JSON',
        'NOT JSON AT ALL - just plaintext response here',
        '{"incomplete": true,',
        '{id: "chatcmpl-bad", choices: []}',  # unquoted keys — invalid JSON
        '{"choices": [{"finish_reason": "tool_calls", "message": {broken}}]}',
        '<<<XML style response unexpected format>>>',
        'undefined',
        '',
    ]
    prompt = rng.choice([
        "Search for documentation on async/await in Python.",
        "Get the weather forecast for Tokyo.",
        "Translate 'good evening' to Italian.",
        "Calculate the area of a circle with radius 7.",
        "Find recent news about electric vehicles.",
    ])
    raw = malformed_variants[i % len(malformed_variants)]
    available = [WEB_SEARCH_TOOL, WEATHER_TOOL, TRANSLATE_TOOL, CALCULATOR_TOOL]
    return {
        "prompt": prompt,
        "tool_name": "web_search",
        "tool_description": "Search the internet for information",
        "tool_arguments": json.dumps({"query": "async await Python"}),
        "tool_output": "Some results",
        "response": "Here is the information you requested.",
        "raw_response": raw,  # Override with malformed
        "available_tools": available,
        "label": "flagged",
        "anomaly_type": "parsing_error",
    }


def make_response_anomaly_span(i: int) -> dict:
    """Prompt asks about X but response is about completely unrelated topic Y."""
    prompt_response_pairs = [
        (
            "What is the current temperature in Sydney Australia?",
            "To make pasta carbonara, you need eggs, guanciale, pecorino, and black pepper. Cook the pasta al dente and mix off heat.",
        ),
        (
            "How do I fix a segmentation fault in my C++ program?",
            "The best hiking trails in Colorado include Rocky Mountain National Park and the Maroon Bells area.",
        ),
        (
            "What is the GDP of France in 2024?",
            "For growing tomatoes, plant them in full sun, water deeply, and stake them as they grow tall.",
        ),
        (
            "How do I configure PostgreSQL for high availability?",
            "The history of jazz music traces back to New Orleans in the early 20th century with roots in blues and ragtime.",
        ),
        (
            "What are the best practices for writing unit tests in Python?",
            "Ocean temperatures affect coral reef bleaching when they rise above 1-2 degrees Celsius above the seasonal maximum.",
        ),
        (
            "How does HTTPS encryption work?",
            "The recipe for banana bread requires ripe bananas, flour, butter, eggs, and baking soda.",
        ),
        (
            "What is the difference between REST and GraphQL APIs?",
            "Training for a marathon typically takes 16-20 weeks with long runs on weekends building up gradually.",
        ),
        (
            "How do I sort a dictionary by value in Python?",
            "The Eiffel Tower was built in 1889 for the World's Fair and stands 330 meters tall in Paris, France.",
        ),
        (
            "What is machine learning and how does gradient descent work?",
            "Sourdough bread fermentation requires maintaining the starter at 70-75°F and feeding it daily with equal parts flour and water.",
        ),
        (
            "How do I set up a Kubernetes cluster for production?",
            "The best strategy for chess openings involves controlling the center with pawns and developing knights before bishops.",
        ),
    ]
    prompt, response = prompt_response_pairs[i % len(prompt_response_pairs)]
    available = [WEB_SEARCH_TOOL, WEATHER_TOOL, CALCULATOR_TOOL, FILE_TOOL]
    return {
        "prompt": prompt,
        "tool_name": "web_search",
        "tool_description": "Search the internet for information",
        "tool_arguments": json.dumps({"query": prompt}),
        "tool_output": "Search completed",
        "response": response,  # Completely off-topic
        "available_tools": available,
        "label": "flagged",
        "anomaly_type": "response_anomaly",
    }


# ---------------------------------------------------------------------------
# Span builder
# ---------------------------------------------------------------------------

def make_span(
    span_id: str,
    agent_name: str,
    template_overrides: dict,
    *,
    is_clean: bool,
) -> dict:
    """Build a full span dict from template data."""
    defaults = {
        "span_id": span_id,
        "tenant_id": "calibration-tenant",
        "trace_id": str(uuid.UUID(int=rng.getrandbits(128))),
        "agent_name": agent_name,
        "agent_model": AGENT_MODEL,
        "tool_name": None,
        "tool_description": None,
        "tool_arguments": None,
        "tool_output": None,
        "prompt": None,
        "response": None,
        "raw_response": CLEAN_RAW_RESPONSE,
        "available_tools": None,
        "label": "clean" if is_clean else "flagged",
        "anomaly_type": None,
    }
    defaults.update(template_overrides)
    return defaults


AGENT_NAMES = ["research-agent", "data-agent", "ops-agent", "comms-agent", "analytics-agent"]


def generate_clean_spans(n: int) -> list[dict]:
    spans = []
    for i in range(n):
        tmpl = CLEAN_TEMPLATES[i % len(CLEAN_TEMPLATES)]
        (prompt, tool_name, tool_desc, args_dict, response) = tmpl

        # Build available_tools: primary + 3 random others
        primary_tool = next((t for t in ALL_TOOLS if t["name"] == tool_name), ALL_TOOLS[0])
        available = pick_tools(primary_tool, 3)

        overrides = {
            "prompt": prompt,
            "tool_name": tool_name,
            "tool_description": tool_desc,
            "tool_arguments": json.dumps(args_dict),
            "tool_output": "Success",
            "response": response,
            "available_tools": available,
            "raw_response": make_tool_call_raw_response(tool_name, args_dict),
            "label": "clean",
            "anomaly_type": None,
        }
        span_id = f"clean-{i:04d}"
        agent = AGENT_NAMES[i % len(AGENT_NAMES)]
        spans.append(make_span(span_id, agent, overrides, is_clean=True))
    return spans


def generate_flagged_spans() -> list[dict]:
    """Generate exactly 63 flagged spans (10 or 11 per anomaly type)."""
    spans = []

    # wrong_tool: 11 spans
    for i in range(11):
        overrides = make_wrong_tool_span(i)
        overrides["raw_response"] = make_tool_call_raw_response(
            overrides["tool_name"],
            json.loads(overrides["tool_arguments"]),
        )
        span_id = f"flagged-wrong-tool-{i:04d}"
        agent = AGENT_NAMES[i % len(AGENT_NAMES)]
        spans.append(make_span(span_id, agent, overrides, is_clean=False))

    # wrong_tool_args: 10 spans
    for i in range(10):
        overrides = make_wrong_tool_args_span(i)
        overrides["raw_response"] = make_tool_call_raw_response(
            overrides["tool_name"],
            json.loads(overrides["tool_arguments"]),
        )
        span_id = f"flagged-wrong-args-{i:04d}"
        agent = AGENT_NAMES[i % len(AGENT_NAMES)]
        spans.append(make_span(span_id, agent, overrides, is_clean=False))

    # no_tool: 10 spans
    for i in range(10):
        overrides = make_no_tool_span(i)
        overrides["raw_response"] = CLEAN_RAW_RESPONSE  # no tool called
        span_id = f"flagged-no-tool-{i:04d}"
        agent = AGENT_NAMES[i % len(AGENT_NAMES)]
        spans.append(make_span(span_id, agent, overrides, is_clean=False))

    # unnecessary_tool_call: 10 spans
    for i in range(10):
        overrides = make_unnecessary_tool_call_span(i)
        overrides["raw_response"] = make_tool_call_raw_response(
            overrides["tool_name"],
            json.loads(overrides["tool_arguments"]),
        )
        span_id = f"flagged-excessive-{i:04d}"
        agent = AGENT_NAMES[i % len(AGENT_NAMES)]
        spans.append(make_span(span_id, agent, overrides, is_clean=False))

    # parsing_error: 11 spans (malformed raw_response already set in make fn)
    for i in range(11):
        overrides = make_parsing_error_span(i)
        span_id = f"flagged-parsing-{i:04d}"
        agent = AGENT_NAMES[i % len(AGENT_NAMES)]
        spans.append(make_span(span_id, agent, overrides, is_clean=False))

    # response_anomaly: 11 spans
    for i in range(11):
        overrides = make_response_anomaly_span(i)
        overrides["raw_response"] = make_tool_call_raw_response(
            overrides["tool_name"],
            json.loads(overrides["tool_arguments"]),
        )
        span_id = f"flagged-response-anomaly-{i:04d}"
        agent = AGENT_NAMES[i % len(AGENT_NAMES)]
        spans.append(make_span(span_id, agent, overrides, is_clean=False))

    return spans


# ---------------------------------------------------------------------------
# New-type span builders (Phase 24 / 25 / 26)
# All builders use rng_new = random.Random(NEW_SEED) — never the global rng.
# Passing rng_new as a parameter keeps each builder stateless/deterministic.
# ---------------------------------------------------------------------------

# -------- SPAN-LEVEL builders (single row per example) --------

def make_output_schema_violation_span(i: int, rng_new: random.Random) -> dict:
    """expected_output_schema set; response is free text (not JSON) — violation."""
    schema = json.dumps({"type": "object", "properties": {"result": {"type": "string"}}})
    if i % 2 == 0:  # flagged
        return {
            "expected_output_schema": schema,
            "response": "Here is the answer you requested.",
            "label": "flagged",
            "anomaly_type": "output_schema_violation",
            "anomaly_types": ["output_schema_violation"],
        }
    else:  # clean
        return {
            "expected_output_schema": schema,
            "response": json.dumps({"result": "The answer is 42."}),
            "label": "clean",
            "anomaly_type": None,
            "anomaly_types": [],
        }


def make_required_fields_missing_span(i: int, rng_new: random.Random) -> dict:
    """expected_output_schema requires name+email; tool_arguments missing email — violation."""
    schema = json.dumps({
        "type": "object",
        "required": ["name", "email"],
        "properties": {
            "name": {"type": "string"},
            "email": {"type": "string"},
        },
    })
    if i % 2 == 0:  # flagged
        return {
            "expected_output_schema": schema,
            "tool_arguments": json.dumps({"name": "Alice"}),
            "label": "flagged",
            "anomaly_type": "required_fields_missing",
            "anomaly_types": ["required_fields_missing"],
        }
    else:  # clean
        return {
            "expected_output_schema": schema,
            "tool_arguments": json.dumps({"name": "Alice", "email": "alice@example.com"}),
            "label": "clean",
            "anomaly_type": None,
            "anomaly_types": [],
        }


def make_output_truncated_span(i: int, rng_new: random.Random) -> dict:
    """raw_response finish_reason=length → truncated; finish_reason=stop → clean."""
    if i % 2 == 0:  # flagged
        raw = json.dumps({
            "id": "chatcmpl-trunc",
            "choices": [{"finish_reason": "length", "message": {"content": "partial answer"}}],
        })
        return {
            "raw_response": raw,
            "response": "Here is the partial answer that got cut off",
            "label": "flagged",
            "anomaly_type": "output_truncated",
            "anomaly_types": ["output_truncated"],
        }
    else:  # clean
        raw = json.dumps({
            "id": "chatcmpl-ok",
            "choices": [{"finish_reason": "stop", "message": {"content": "complete answer"}}],
        })
        return {
            "raw_response": raw,
            "response": "Here is the complete answer.",
            "label": "clean",
            "anomaly_type": None,
            "anomaly_types": [],
        }


def make_type_coercion_error_span(i: int, rng_new: random.Random) -> dict:
    """expected_output_schema requires count as integer; tool_arguments has string → violation."""
    schema = json.dumps({
        "type": "object",
        "properties": {"count": {"type": "integer"}},
    })
    if i % 2 == 0:  # flagged
        return {
            "expected_output_schema": schema,
            "tool_arguments": json.dumps({"count": "42"}),  # string instead of integer
            "label": "flagged",
            "anomaly_type": "type_coercion_error",
            "anomaly_types": ["type_coercion_error"],
        }
    else:  # clean
        return {
            "expected_output_schema": schema,
            "tool_arguments": json.dumps({"count": 42}),
            "label": "clean",
            "anomaly_type": None,
            "anomaly_types": [],
        }


# ~700 repetitions × ~9 words ≈ ~6300 tokens; 700 is safe over the 8000-token threshold
_OVERFLOW_TEXT = ("The quick brown fox jumps over the lazy dog. " * 700).strip()
_SHORT_TEXT = "What is the capital of France?"


def make_context_overflow_span(i: int, rng_new: random.Random) -> dict:
    """prompt > 9000 tokens → overflow; short prompt → clean."""
    if i % 2 == 0:  # flagged — use 1100 repetitions to be well above 8000 token threshold
        long_prompt = ("The quick brown fox jumps over the lazy dog. " * 1100).strip()
        return {
            "prompt": long_prompt,
            "label": "flagged",
            "anomaly_type": "context_overflow",
            "anomaly_types": ["context_overflow"],
        }
    else:  # clean
        return {
            "prompt": _SHORT_TEXT,
            "label": "clean",
            "anomaly_type": None,
            "anomaly_types": [],
        }


_MISSING_DETAILS_FLAGGED = [
    (
        "Explain the roles of Alice Johnson and Bob Smith in the Paris Agreement.",
        "The Paris Agreement is an international treaty on climate change.",
    ),
    (
        "What did Carol White and David Brown contribute to the Apollo programme?",
        "The Apollo programme successfully landed humans on the Moon.",
    ),
    (
        "Summarise the work of Emma Davis and Frank Wilson in Project Aurora.",
        "Project Aurora involved advanced research into renewable energy.",
    ),
    (
        "Describe the findings of Grace Lee and Henry Martinez in the 2025 study.",
        "The 2025 study produced important scientific conclusions.",
    ),
    (
        "What were the conclusions of Iris Chen and James Taylor?",
        "The research produced interesting results worthy of further study.",
    ),
    (
        "Explain what Kate Anderson and Liam Thompson said about quantum computing.",
        "Quantum computing offers substantial computational advantages over classical approaches.",
    ),
    (
        "Summarise the contributions of Mia Robinson and Noah Walker to the framework.",
        "The framework provides a structured approach to problem solving.",
    ),
    (
        "What did Olivia Scott and Paul Harris conclude about neural networks?",
        "Neural networks are powerful tools for pattern recognition.",
    ),
]

_MISSING_DETAILS_CLEAN = [
    (
        "Explain the roles of Alice Johnson and Bob Smith in the Paris Agreement.",
        "Alice Johnson led negotiations for Article 6, while Bob Smith coordinated country pledges.",
    ),
    (
        "What did Carol White and David Brown contribute to the Apollo programme?",
        "Carol White designed the navigation software; David Brown led astronaut training.",
    ),
    (
        "Summarise the work of Emma Davis and Frank Wilson in Project Aurora.",
        "Emma Davis directed the energy storage component and Frank Wilson led field trials.",
    ),
    (
        "Describe the findings of Grace Lee and Henry Martinez in the 2025 study.",
        "Grace Lee found a 30% efficiency gain; Henry Martinez confirmed results via independent review.",
    ),
    (
        "What were the conclusions of Iris Chen and James Taylor?",
        "Iris Chen concluded that latency was the primary bottleneck; James Taylor proposed a caching solution.",
    ),
    (
        "Explain what Kate Anderson and Liam Thompson said about quantum computing.",
        "Kate Anderson argued for near-term applications; Liam Thompson focused on long-term error correction.",
    ),
    (
        "Summarise the contributions of Mia Robinson and Noah Walker to the framework.",
        "Mia Robinson built the data pipeline; Noah Walker wrote the evaluation module.",
    ),
    (
        "What did Olivia Scott and Paul Harris conclude about neural networks?",
        "Olivia Scott showed transformers outperform CNNs on NLP tasks; Paul Harris extended this to vision.",
    ),
]


def make_missing_details_span(i: int, rng_new: random.Random) -> dict:
    """prompt has named entities absent from response → missing_details."""
    if i % 2 == 0:  # flagged
        prompt, response = _MISSING_DETAILS_FLAGGED[i // 2 % len(_MISSING_DETAILS_FLAGGED)]
        return {
            "prompt": prompt,
            "response": response,
            "label": "flagged",
            "anomaly_type": "missing_details",
            "anomaly_types": ["missing_details"],
        }
    else:  # clean
        prompt, response = _MISSING_DETAILS_CLEAN[i // 2 % len(_MISSING_DETAILS_CLEAN)]
        return {
            "prompt": prompt,
            "response": response,
            "label": "clean",
            "anomaly_type": None,
            "anomaly_types": [],
        }


# -------- TRACE-LEVEL builders (list of rows, same trace_id, last row carries label) --------

def _new_trace_id(rng_new: random.Random) -> str:
    """Generate a deterministic trace_id from rng_new."""
    return str(uuid.UUID(int=rng_new.getrandbits(128)))


def make_stale_context_spans(i: int, rng_new: random.Random) -> list[dict]:
    """2 spans; span[1].prompt copies span[0].tool_output verbatim → stale_context."""
    trace_id = _new_trace_id(rng_new)
    tool_output = "Result: 42 active users in North region"
    if i % 2 == 0:  # flagged
        spans = [
            {
                "span_id": f"new-stale-ctx-{i:04d}-0",
                "trace_id": trace_id,
                "tool_output": tool_output,
                "label": "clean", "anomaly_type": None, "anomaly_types": [],
            },
            {
                "span_id": f"new-stale-ctx-{i:04d}-1",
                "trace_id": trace_id,
                "prompt": f"Please process this data: {tool_output}",
                "label": "flagged",
                "anomaly_type": "stale_context",
                "anomaly_types": ["stale_context"],
            },
        ]
    else:  # clean
        spans = [
            {
                "span_id": f"new-stale-ctx-{i:04d}-0",
                "trace_id": trace_id,
                "tool_output": tool_output,
                "label": "clean", "anomaly_type": None, "anomaly_types": [],
            },
            {
                "span_id": f"new-stale-ctx-{i:04d}-1",
                "trace_id": trace_id,
                "prompt": "Summarise the database query results and identify outliers.",
                "label": "clean",
                "anomaly_type": None,
                "anomaly_types": [],
            },
        ]
    return spans


def make_step_repetition_spans(i: int, rng_new: random.Random) -> list[dict]:
    """2 spans; near-identical tool_name + tool_arguments → step_repetition."""
    trace_id = _new_trace_id(rng_new)
    query = "SELECT * FROM users WHERE id=1"
    if i % 2 == 0:  # flagged — identical queries
        spans = [
            {
                "span_id": f"new-step-rep-{i:04d}-0",
                "trace_id": trace_id,
                "tool_name": "execute_sql",
                "tool_arguments": json.dumps({"query": query}),
                "label": "clean", "anomaly_type": None, "anomaly_types": [],
            },
            {
                "span_id": f"new-step-rep-{i:04d}-1",
                "trace_id": trace_id,
                "tool_name": "execute_sql",
                "tool_arguments": json.dumps({"query": query}),
                "label": "flagged",
                "anomaly_type": "step_repetition",
                "anomaly_types": ["step_repetition"],
            },
        ]
    else:  # clean — different queries
        spans = [
            {
                "span_id": f"new-step-rep-{i:04d}-0",
                "trace_id": trace_id,
                "tool_name": "execute_sql",
                "tool_arguments": json.dumps({"query": "SELECT * FROM users WHERE id=1"}),
                "label": "clean", "anomaly_type": None, "anomaly_types": [],
            },
            {
                "span_id": f"new-step-rep-{i:04d}-1",
                "trace_id": trace_id,
                "tool_name": "execute_sql",
                "tool_arguments": json.dumps({"query": "SELECT * FROM orders WHERE status='pending' LIMIT 50"}),
                "label": "clean",
                "anomaly_type": None,
                "anomaly_types": [],
            },
        ]
    return spans


def make_termination_loop_spans(i: int, rng_new: random.Random) -> list[dict]:
    """4 spans; all same tool_name → termination_loop (n=4 >= default threshold 3)."""
    trace_id = _new_trace_id(rng_new)
    if i % 2 == 0:  # flagged — 4 identical tool calls
        tool_name = "web_search"
        spans = []
        for k in range(4):
            spans.append({
                "span_id": f"new-term-loop-{i:04d}-{k}",
                "trace_id": trace_id,
                "tool_name": tool_name,
                "tool_arguments": json.dumps({"query": f"search query {k}"}),
                "label": "clean" if k < 3 else "flagged",
                "anomaly_type": None if k < 3 else "termination_loop",
                "anomaly_types": [] if k < 3 else ["termination_loop"],
            })
    else:  # clean — 4 different tool names
        tool_names = ["web_search", "execute_sql", "send_email", "get_weather"]
        spans = []
        for k in range(4):
            spans.append({
                "span_id": f"new-term-loop-{i:04d}-{k}",
                "trace_id": trace_id,
                "tool_name": tool_names[k],
                "tool_arguments": json.dumps({"param": f"value{k}"}),
                "label": "clean",
                "anomaly_type": None,
                "anomaly_types": [],
            })
    return spans


def make_context_propagation_failure_spans(i: int, rng_new: random.Random) -> list[dict]:
    """2 spans; span[1].prompt ignores span[0].tool_output → context_propagation_failure."""
    trace_id = _new_trace_id(rng_new)
    tool_output = "Customer ID: C-9912, Account: Premium, Balance: $5,432"
    if i % 2 == 0:  # flagged
        spans = [
            {
                "span_id": f"new-ctx-prop-{i:04d}-0",
                "trace_id": trace_id,
                "tool_output": tool_output,
                "label": "clean", "anomaly_type": None, "anomaly_types": [],
            },
            {
                "span_id": f"new-ctx-prop-{i:04d}-1",
                "trace_id": trace_id,
                "prompt": "Update the billing address for the account.",
                "label": "flagged",
                "anomaly_type": "context_propagation_failure",
                "anomaly_types": ["context_propagation_failure"],
            },
        ]
    else:  # clean — span[1] references the prior tool_output
        spans = [
            {
                "span_id": f"new-ctx-prop-{i:04d}-0",
                "trace_id": trace_id,
                "tool_output": tool_output,
                "label": "clean", "anomaly_type": None, "anomaly_types": [],
            },
            {
                "span_id": f"new-ctx-prop-{i:04d}-1",
                "trace_id": trace_id,
                "prompt": "Update the billing address for Customer ID C-9912 (Premium account, Balance $5,432).",
                "label": "clean",
                "anomaly_type": None,
                "anomaly_types": [],
            },
        ]
    return spans


def make_history_loss_spans(i: int, rng_new: random.Random) -> list[dict]:
    """3 spans about database migration; span[2] topic jumps to weather → history_loss."""
    trace_id = _new_trace_id(rng_new)
    if i % 2 == 0:  # flagged
        spans = [
            {
                "span_id": f"new-hist-loss-{i:04d}-0",
                "trace_id": trace_id,
                "prompt": "Prepare the database migration script for the user_accounts table.",
                "label": "clean", "anomaly_type": None, "anomaly_types": [],
            },
            {
                "span_id": f"new-hist-loss-{i:04d}-1",
                "trace_id": trace_id,
                "prompt": "Validate the database migration against staging environment.",
                "label": "clean", "anomaly_type": None, "anomaly_types": [],
            },
            {
                "span_id": f"new-hist-loss-{i:04d}-2",
                "trace_id": trace_id,
                "prompt": "What is the weather in Tokyo?",
                "label": "flagged",
                "anomaly_type": "history_loss",
                "anomaly_types": ["history_loss"],
            },
        ]
    else:  # clean — all prompts stay on topic
        spans = [
            {
                "span_id": f"new-hist-loss-{i:04d}-0",
                "trace_id": trace_id,
                "prompt": "Prepare the database migration script for the user_accounts table.",
                "label": "clean", "anomaly_type": None, "anomaly_types": [],
            },
            {
                "span_id": f"new-hist-loss-{i:04d}-1",
                "trace_id": trace_id,
                "prompt": "Validate the database migration against staging environment.",
                "label": "clean", "anomaly_type": None, "anomaly_types": [],
            },
            {
                "span_id": f"new-hist-loss-{i:04d}-2",
                "trace_id": trace_id,
                "prompt": "Execute the database migration script and verify row counts match.",
                "label": "clean",
                "anomaly_type": None,
                "anomaly_types": [],
            },
        ]
    return spans


def make_wrong_agent_handoff_spans(i: int, rng_new: random.Random) -> list[dict]:
    """2 spans; orchestrator → billing_agent (not in routing graph) → wrong_agent_handoff."""
    trace_id = _new_trace_id(rng_new)
    if i % 2 == 0:  # flagged — billing_agent not in orchestrator's allowed destinations
        spans = [
            {
                "span_id": f"new-wrong-handoff-{i:04d}-0",
                "trace_id": trace_id,
                "agent_name": "orchestrator",
                "prompt": "Route this task to the appropriate agent.",
                "label": "clean", "anomaly_type": None, "anomaly_types": [],
            },
            {
                "span_id": f"new-wrong-handoff-{i:04d}-1",
                "trace_id": trace_id,
                "agent_name": "billing_agent",
                "prompt": "Process the request.",
                "label": "flagged",
                "anomaly_type": "wrong_agent_handoff",
                "anomaly_types": ["wrong_agent_handoff"],
            },
        ]
    else:  # clean — orchestrator → search_agent (valid destination)
        spans = [
            {
                "span_id": f"new-wrong-handoff-{i:04d}-0",
                "trace_id": trace_id,
                "agent_name": "orchestrator",
                "prompt": "Route this search task to the search agent.",
                "label": "clean", "anomaly_type": None, "anomaly_types": [],
            },
            {
                "span_id": f"new-wrong-handoff-{i:04d}-1",
                "trace_id": trace_id,
                "agent_name": "search_agent",
                "prompt": "Search for relevant documents.",
                "label": "clean",
                "anomaly_type": None,
                "anomaly_types": [],
            },
        ]
    return spans


def make_information_withholding_spans(i: int, rng_new: random.Random) -> list[dict]:
    """2 spans; span[1].prompt omits entities from span[0].response → information_withholding."""
    trace_id = _new_trace_id(rng_new)
    response_with_entities = "Alice Johnson approved the $50,000 budget for Project Aurora."
    if i % 2 == 0:  # flagged — span[1] ignores Alice Johnson, $50,000, Project Aurora
        spans = [
            {
                "span_id": f"new-info-with-{i:04d}-0",
                "trace_id": trace_id,
                "response": response_with_entities,
                "label": "clean", "anomaly_type": None, "anomaly_types": [],
            },
            {
                "span_id": f"new-info-with-{i:04d}-1",
                "trace_id": trace_id,
                "prompt": "Send the approval confirmation.",
                "label": "flagged",
                "anomaly_type": "information_withholding",
                "anomaly_types": ["information_withholding"],
            },
        ]
    else:  # clean — span[1] references key entities
        spans = [
            {
                "span_id": f"new-info-with-{i:04d}-0",
                "trace_id": trace_id,
                "response": response_with_entities,
                "label": "clean", "anomaly_type": None, "anomaly_types": [],
            },
            {
                "span_id": f"new-info-with-{i:04d}-1",
                "trace_id": trace_id,
                "prompt": "Send confirmation to Alice Johnson that the $50,000 budget for Project Aurora has been approved.",
                "label": "clean",
                "anomaly_type": None,
                "anomaly_types": [],
            },
        ]
    return spans


def make_conversation_reset_spans(i: int, rng_new: random.Random) -> list[dict]:
    """3 spans; first 2 about kubernetes; span[2] completely off-topic → conversation_reset."""
    trace_id = _new_trace_id(rng_new)
    if i % 2 == 0:  # flagged
        spans = [
            {
                "span_id": f"new-conv-reset-{i:04d}-0",
                "trace_id": trace_id,
                "prompt": "Deploy the kubernetes cluster to the production environment.",
                "label": "clean", "anomaly_type": None, "anomaly_types": [],
            },
            {
                "span_id": f"new-conv-reset-{i:04d}-1",
                "trace_id": trace_id,
                "prompt": "Check the status of the kubernetes pods in the production namespace.",
                "label": "clean", "anomaly_type": None, "anomaly_types": [],
            },
            {
                "span_id": f"new-conv-reset-{i:04d}-2",
                "trace_id": trace_id,
                "prompt": "I love pizza. What toppings do you recommend?",
                "label": "flagged",
                "anomaly_type": "conversation_reset",
                "anomaly_types": ["conversation_reset"],
            },
        ]
    else:  # clean — all on kubernetes topic
        spans = [
            {
                "span_id": f"new-conv-reset-{i:04d}-0",
                "trace_id": trace_id,
                "prompt": "Deploy the kubernetes cluster to the production environment.",
                "label": "clean", "anomaly_type": None, "anomaly_types": [],
            },
            {
                "span_id": f"new-conv-reset-{i:04d}-1",
                "trace_id": trace_id,
                "prompt": "Check the status of the kubernetes pods in the production namespace.",
                "label": "clean", "anomaly_type": None, "anomaly_types": [],
            },
            {
                "span_id": f"new-conv-reset-{i:04d}-2",
                "trace_id": trace_id,
                "prompt": "Scale the kubernetes deployment to 5 replicas for the production namespace.",
                "label": "clean",
                "anomaly_type": None,
                "anomaly_types": [],
            },
        ]
    return spans


def make_clarification_skipped_spans(i: int, rng_new: random.Random) -> list[dict]:
    """1 span; disjunctive prompt without question in response → clarification_skipped."""
    if i % 2 == 0:  # flagged — no "?" in response
        row = {
            "prompt": "Should we deploy to production or staging environment?",
            "response": "I will proceed with the deployment immediately.",
            "label": "flagged",
            "anomaly_type": "clarification_skipped",
            "anomaly_types": ["clarification_skipped"],
        }
    else:  # clean — response has a question
        row = {
            "prompt": "Should we deploy to production or staging environment?",
            "response": "Which environment has been validated — production or staging?",
            "label": "clean",
            "anomaly_type": None,
            "anomaly_types": [],
        }
    return [row]  # single-span, wrapped in list for uniform interface


def make_no_verification_spans(i: int, rng_new: random.Random) -> list[dict]:
    """3 spans; none has verification keyword in tool_name → no_verification."""
    trace_id = _new_trace_id(rng_new)
    if i % 2 == 0:  # flagged — no verification step
        tool_names = ["execute_sql", "web_search", "send_email"]
        spans = []
        for k in range(3):
            is_last = k == 2
            spans.append({
                "span_id": f"new-no-ver-{i:04d}-{k}",
                "trace_id": trace_id,
                "tool_name": tool_names[k],
                "tool_description": f"Tool {tool_names[k]} performs data operations",
                "label": "clean" if not is_last else "flagged",
                "anomaly_type": None if not is_last else "no_verification",
                "anomaly_types": [] if not is_last else ["no_verification"],
            })
    else:  # clean — one span has validate_output tool
        spans = [
            {
                "span_id": f"new-no-ver-{i:04d}-0",
                "trace_id": trace_id,
                "tool_name": "execute_sql",
                "tool_description": "Execute SQL query against database",
                "label": "clean", "anomaly_type": None, "anomaly_types": [],
            },
            {
                "span_id": f"new-no-ver-{i:04d}-1",
                "trace_id": trace_id,
                "tool_name": "validate_output",
                "tool_description": "Verify and validate the output results",
                "label": "clean", "anomaly_type": None, "anomaly_types": [],
            },
            {
                "span_id": f"new-no-ver-{i:04d}-2",
                "trace_id": trace_id,
                "tool_name": "send_email",
                "tool_description": "Send email notification",
                "label": "clean",
                "anomaly_type": None,
                "anomaly_types": [],
            },
        ]
    return spans


def make_incomplete_verification_spans(i: int, rng_new: random.Random) -> list[dict]:
    """3 spans; verification covers only Alice Smith, missing Bob Jones and Carol Williams."""
    trace_id = _new_trace_id(rng_new)
    if i % 2 == 0:  # flagged — verification covers only 1 of 3 entities
        spans = [
            {
                "span_id": f"new-inc-ver-{i:04d}-0",
                "trace_id": trace_id,
                "response": "Processing completed for Alice Smith, Bob Jones, and Carol Williams.",
                "label": "clean", "anomaly_type": None, "anomaly_types": [],
            },
            {
                "span_id": f"new-inc-ver-{i:04d}-1",
                "trace_id": trace_id,
                "tool_name": "verify_output",
                "tool_description": "verify output completeness",
                "prompt": "Verify that Alice Smith was processed correctly.",
                "label": "clean", "anomaly_type": None, "anomaly_types": [],
            },
            {
                "span_id": f"new-inc-ver-{i:04d}-2",
                "trace_id": trace_id,
                "prompt": "Confirm the verification step is complete.",
                "label": "flagged",
                "anomaly_type": "incomplete_verification",
                "anomaly_types": ["incomplete_verification"],
            },
        ]
    else:  # clean — verification covers all three names
        spans = [
            {
                "span_id": f"new-inc-ver-{i:04d}-0",
                "trace_id": trace_id,
                "response": "Processing completed for Alice Smith, Bob Jones, and Carol Williams.",
                "label": "clean", "anomaly_type": None, "anomaly_types": [],
            },
            {
                "span_id": f"new-inc-ver-{i:04d}-1",
                "trace_id": trace_id,
                "tool_name": "verify_output",
                "tool_description": "verify output completeness",
                "prompt": "Verify that Alice Smith, Bob Jones, and Carol Williams were all processed correctly.",
                "label": "clean", "anomaly_type": None, "anomaly_types": [],
            },
            {
                "span_id": f"new-inc-ver-{i:04d}-2",
                "trace_id": trace_id,
                "prompt": "Confirm the verification step is complete for all three.",
                "label": "clean",
                "anomaly_type": None,
                "anomaly_types": [],
            },
        ]
    return spans


# ---------------------------------------------------------------------------
# New-type span generation orchestrator
# ---------------------------------------------------------------------------

# Maps flag_type → (builder_fn, n_flagged_examples, n_clean_examples).
# Each flagged call uses even i, each clean call uses odd i.
# Trace-level builders return a list of rows; span-level builders return a dict.
# We wrap span-level single dicts in a list below for uniform processing.

_NEW_TYPE_BUILDERS = [
    ("output_schema_violation",        make_output_schema_violation_span,        8, 8),
    ("required_fields_missing",         make_required_fields_missing_span,         8, 8),
    ("output_truncated",                make_output_truncated_span,                8, 8),
    ("type_coercion_error",             make_type_coercion_error_span,             8, 8),
    ("context_overflow",                make_context_overflow_span,                8, 8),
    ("missing_details",                 make_missing_details_span,                 8, 8),
    ("stale_context",                   make_stale_context_spans,                  8, 8),
    ("step_repetition",                 make_step_repetition_spans,                8, 8),
    ("termination_loop",                make_termination_loop_spans,               8, 8),
    ("context_propagation_failure",     make_context_propagation_failure_spans,    8, 8),
    ("history_loss",                    make_history_loss_spans,                   8, 8),
    ("wrong_agent_handoff",             make_wrong_agent_handoff_spans,            8, 8),
    ("information_withholding",         make_information_withholding_spans,        8, 8),
    ("conversation_reset",              make_conversation_reset_spans,             8, 8),
    ("clarification_skipped",           make_clarification_skipped_spans,          8, 8),
    ("no_verification",                 make_no_verification_spans,                8, 8),
    ("incomplete_verification",         make_incomplete_verification_spans,        8, 8),
]


def _apply_defaults(rows: list[dict], flag_type: str, group_idx: int, rng_new: random.Random) -> None:
    """Apply SpanData field defaults to a group of rows in-place.

    If any row in the group already has a span_id (set by the builder), keep it.
    Otherwise assign a deterministic id: new-{flag_type}-g{group_idx}-{row_idx}.
    All rows in the same group share a trace_id (set by builder or generated here).
    """
    # Determine shared trace_id for this group (all rows must share it)
    # Prefer the first non-None trace_id already set by a builder
    shared_trace_id = next(
        (r["trace_id"] for r in rows if r.get("trace_id")),
        str(uuid.UUID(int=rng_new.getrandbits(128))),
    )

    for row_idx, row in enumerate(rows):
        # Stable span_id: builder-set ID takes priority
        if "span_id" not in row or row.get("span_id") is None:
            row["span_id"] = f"new-{flag_type}-g{group_idx:04d}-{row_idx}"
        row.setdefault("trace_id", shared_trace_id)
        # Force all rows to share the same trace_id (trace-level groups must share it)
        row["trace_id"] = shared_trace_id
        row.setdefault("tenant_id", "calibration-tenant")
        row.setdefault("agent_name", "calibration-agent")
        row.setdefault("agent_model", AGENT_MODEL)
        row.setdefault("tool_name", None)
        row.setdefault("tool_description", None)
        row.setdefault("tool_arguments", None)
        row.setdefault("tool_output", None)
        row.setdefault("prompt", None)
        row.setdefault("response", None)
        row.setdefault("raw_response", CLEAN_RAW_RESPONSE)
        row.setdefault("available_tools", None)
        row.setdefault("expected_output_schema", None)
        row.setdefault("parent_span_id", None)


def generate_new_type_spans() -> list[dict]:
    """Generate spans for all 17 new flag types using rng_new (NEW_SEED=27).

    Returns a flat list of span dicts. Trace-level builders produce multiple
    rows per call; they are flattened here. Existing 100 rows are NOT touched.
    """
    rng_new = random.Random(NEW_SEED)
    all_new: list[dict] = []

    for flag_type, builder, n_flagged, n_clean in _NEW_TYPE_BUILDERS:
        # Generate n_flagged groups (even i values)
        for group_idx in range(n_flagged):
            i = group_idx * 2  # even → flagged
            result = builder(i, rng_new)
            # Span-level builders return a single dict; trace-level return list
            rows = [result] if isinstance(result, dict) else result
            _apply_defaults(rows, flag_type, group_idx * 2, rng_new)
            all_new.extend(rows)

        # Generate n_clean groups (odd i values)
        for group_idx in range(n_clean):
            i = group_idx * 2 + 1  # odd → clean
            result = builder(i, rng_new)
            rows = [result] if isinstance(result, dict) else result
            _apply_defaults(rows, flag_type, group_idx * 2 + 1, rng_new)
            all_new.extend(rows)

    return all_new


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)

    flagged = generate_flagged_spans()   # 63 spans (original 7 types)
    clean = generate_clean_spans(147)    # 147 spans (original clean)
    new_type_spans = generate_new_type_spans()  # 17 new types (Phase 24/25/26)
    all_spans = flagged + clean + new_type_spans

    # Shuffle reproducibly so flagged spans aren't all bunched at the top
    rng.shuffle(all_spans)

    with FIXTURE_PATH.open("w", encoding="utf-8") as f:
        for span in all_spans:
            f.write(json.dumps(span, ensure_ascii=False) + "\n")

    total = len(all_spans)
    n_flagged = sum(1 for s in all_spans if s["label"] == "flagged")
    n_clean = total - n_flagged
    ratio = n_flagged / total
    types = set(s["anomaly_type"] for s in all_spans if s["label"] == "flagged")

    print(f"Written {total} spans to {FIXTURE_PATH}")
    print(f"  Flagged: {n_flagged} ({ratio:.1%})")
    print(f"  Clean:   {n_clean}")
    print(f"  Anomaly types: {sorted(types)}")


if __name__ == "__main__":
    main()
