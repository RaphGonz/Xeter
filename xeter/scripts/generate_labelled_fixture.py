"""Generate synthetic labelled spans for calibration.

Produces fixtures/labelled_spans.jsonl with 210 spans:
  - 63 flagged (~30%) covering all six anomaly types
  - 147 clean (~70%)

Each line is a JSON object with all SpanData fields plus:
  - label: "flagged" | "clean"
  - anomaly_type: one of the six types, or null for clean spans

Run:
    python xeter/scripts/generate_labelled_fixture.py

Output: fixtures/labelled_spans.jsonl (deterministic via fixed seed 42)
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
        "anomaly_type": "wrong_tool",
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


def make_excessive_tool_span(i: int) -> dict:
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
        "anomaly_type": "excessive_tool",
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

    # excessive_tool: 10 spans
    for i in range(10):
        overrides = make_excessive_tool_span(i)
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
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)

    flagged = generate_flagged_spans()   # 63 spans
    clean = generate_clean_spans(147)    # 147 spans
    all_spans = flagged + clean

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
