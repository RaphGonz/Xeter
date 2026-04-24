"""Seed 4 test spans into ClickHouse + flags/scores into PostgreSQL for dashboard testing.

Spans are drawn from fixtures/labelled_spans.jsonl — one of each interesting type:
  clean-001   — clean, ops-agent (execute_sql, correct use)
  fwc-001     — wrong_tool_called, dev-agent (used SQL to look up docs online)
  fwta-001    — wrong_tool_args, analytics-agent (asked Tokyo, got London)
  fnt-001     — no_tool_used, dev-agent (ignored explicit instruction to search)

Run from repo root:
    python -m xeter.scripts.seed_spans
"""

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from xeter.shared.db.postgres import get_async_session_factory
from xeter.shared.db.clickhouse import get_clickhouse_client
from xeter.shared.models import Flag
import aioboto3
from xeter.services.analyser.s3 import S3Client

_DEV_TENANT_NAME = "dev-tenant"
NOW = datetime.now(timezone.utc)

# ---------------------------------------------------------------------------
# Span data drawn from fixtures/labelled_spans.jsonl
# ---------------------------------------------------------------------------

_SPANS_FIXTURE = [
    {
        # clean-001 — correct tool use, no flags expected
        "span_id": "clean-001",
        "trace_id": "8e8f027d-3298-5d3c-8a91-d1faa9e41408",
        "agent_name": "ops-agent",
        "agent_model": "gpt-4o",
        "tool_name": "execute_sql",
        "tool_description": "Execute a SQL query against a relational database",
        "tool_arguments": json.dumps({"query": "SELECT COUNT(*) FROM sessions WHERE status='active'"}),
        "tool_output": "342 rows",
        "prompt": "Count the number of active user sessions in the database.",
        "response": "There are 342 active user sessions currently.",
        "raw_response": json.dumps({"id": "chatcmpl-tc123", "object": "chat.completion", "model": "gpt-4o", "choices": [{"index": 0, "message": {"role": "assistant", "content": None, "tool_calls": [{"id": "call_abc", "type": "function", "function": {"name": "execute_sql", "arguments": "{\"query\":\"SELECT COUNT(*) FROM sessions WHERE status='active'\"}"}}]}, "finish_reason": "tool_calls"}]}),
        "available_tools": json.dumps([
            {"name": "execute_sql", "description": "Execute a SQL query against a relational database"},
            {"name": "read_file", "description": "Read the contents of a file from the filesystem"},
            {"name": "web_search", "description": "Search the internet for current information and web pages"},
            {"name": "calculate", "description": "Perform mathematical calculations and return results"},
        ]),
        "offset_minutes": 30,
        "label": "clean",
        "flag_type": None,
        "flag_score": None,
        "flag_detail": None,
    },
    {
        # fwc-001 — wrong_tool_called: used execute_sql to look up online docs
        "span_id": "fwc-001",
        "trace_id": "0269e56b-5086-5c7c-b2fb-e1eb81ece986",
        "agent_name": "dev-agent",
        "agent_model": "gpt-4o",
        "tool_name": "execute_sql",
        "tool_description": "Execute a SQL query against a relational database",
        "tool_arguments": json.dumps({"query": "SELECT * FROM docs WHERE topic='useEffect'"}),
        "tool_output": "0 rows",
        "prompt": "Look up documentation for the React useEffect hook online.",
        "response": "No rows found in the documentation table.",
        "raw_response": json.dumps({"id": "chatcmpl-tc123", "object": "chat.completion", "model": "gpt-4o", "choices": [{"index": 0, "message": {"role": "assistant", "content": None, "tool_calls": [{"id": "call_abc", "type": "function", "function": {"name": "execute_sql", "arguments": "{\"query\":\"SELECT * FROM docs WHERE topic='useEffect'\"}"}}]}, "finish_reason": "tool_calls"}]}),
        "available_tools": json.dumps([
            {"name": "web_search", "description": "Search the internet for current information and web pages"},
            {"name": "execute_sql", "description": "Execute a SQL query against a relational database"},
            {"name": "read_file", "description": "Read the contents of a file from the filesystem"},
            {"name": "execute_code", "description": "Execute Python code in a sandboxed environment and return output"},
        ]),
        "offset_minutes": 20,
        "label": "flagged",
        "flag_type": "wrong_tool_called",
        "flag_score": 0.87,
        "flag_detail": {
            "called": "execute_sql",
            "better_tool": "web_search",
            "cosine_similarity": 0.13,
        },
    },
    {
        # fwta-001 — wrong_tool_args: right tool (get_weather), wrong location and date
        "span_id": "fwta-001",
        "trace_id": "1bdf8288-9502-530a-b745-84e590662393",
        "agent_name": "analytics-agent",
        "agent_model": "gpt-4o",
        "tool_name": "get_weather",
        "tool_description": "Get current weather conditions and forecasts for a location",
        "tool_arguments": json.dumps({"location": "London", "date": "2025-11-20"}),
        "tool_output": "London: 10°C overcast",
        "prompt": "Get the current weather conditions in Tokyo, Japan on March 5th.",
        "response": "Weather in London on November 20: 10°C, overcast.",
        "raw_response": json.dumps({"id": "chatcmpl-tc123", "object": "chat.completion", "model": "gpt-4o", "choices": [{"index": 0, "message": {"role": "assistant", "content": None, "tool_calls": [{"id": "call_abc", "type": "function", "function": {"name": "get_weather", "arguments": "{\"location\":\"London\",\"date\":\"2025-11-20\"}"}}]}, "finish_reason": "tool_calls"}]}),
        "available_tools": json.dumps([
            {"name": "get_weather", "description": "Get current weather conditions and forecasts for a location"},
            {"name": "web_search", "description": "Search the internet for current information and web pages"},
            {"name": "calculate", "description": "Perform mathematical calculations and return results"},
            {"name": "get_news", "description": "Fetch latest news articles on a given topic"},
        ]),
        "offset_minutes": 10,
        "label": "flagged",
        "flag_type": "wrong_tool_args",
        "flag_score": 0.71,
        "flag_detail": {
            "mismatched_args": ["location", "date"],
            "prompt_location": "Tokyo, Japan",
            "called_location": "London",
            "hybrid_score": 0.29,
        },
    },
    {
        # fnt-001 — no_tool_used: model answered from memory despite explicit search instruction
        "span_id": "fnt-001",
        "trace_id": "644d3a0c-2bd0-54f9-9760-57cffa812b95",
        "agent_name": "dev-agent",
        "agent_model": "gpt-4o",
        "tool_name": "",
        "tool_description": "",
        "tool_arguments": "",
        "tool_output": "",
        "prompt": "Use the web search tool to find examples of Python async generators.",
        "response": "Python async generators allow you to yield values asynchronously using 'async def' and 'yield'.",
        "raw_response": json.dumps({"id": "chatcmpl-abc123", "object": "chat.completion", "model": "gpt-4o", "choices": [{"index": 0, "message": {"role": "assistant", "content": "Python async generators allow you to yield values asynchronously."}, "finish_reason": "stop"}]}),
        "available_tools": json.dumps([
            {"name": "web_search", "description": "Search the internet for current information and web pages"},
            {"name": "execute_code", "description": "Execute Python code in a sandboxed environment and return output"},
            {"name": "execute_sql", "description": "Execute a SQL query against a relational database"},
            {"name": "read_file", "description": "Read the contents of a file from the filesystem"},
        ]),
        "offset_minutes": 3,
        "label": "flagged",
        "flag_type": "no_tool_used",
        "flag_score": 0.79,
        "flag_detail": {
            "top_matching_tool": "web_search",
            "prompt_tool_overlap_score": 0.79,
        },
    },
]


async def main() -> None:
    # 1. Resolve dev tenant
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            text("SELECT tenant_id FROM tenants WHERE name = :name"),
            {"name": _DEV_TENANT_NAME},
        )
        row = result.fetchone()
        if row is None:
            print("ERROR: dev-tenant not found. Run `python -m xeter.scripts.seed` first.")
            return
        tenant_id = str(row[0])
        print(f"Tenant: {tenant_id}")

    # 2. Upload payloads to S3, then insert spans into ClickHouse
    import os
    s3 = S3Client(
        session=aioboto3.Session(
            aws_access_key_id=os.environ["MINIO_ACCESS_KEY"],
            aws_secret_access_key=os.environ["MINIO_SECRET_KEY"],
        ),
        bucket=os.environ.get("MINIO_BUCKET", "xeter-spans"),
        endpoint_url=os.environ["MINIO_ENDPOINT"],
    )
    ch = get_clickhouse_client()

    ch_rows = []
    for s in _SPANS_FIXTURE:
        refs = await s3.upload_span_payloads(
            tenant_id=tenant_id,
            span_id=s["span_id"],
            prompt=s["prompt"],
            response=s["response"],
            raw_response=s["raw_response"],
            available_tools=s["available_tools"],
        )
        t_begin = NOW - timedelta(minutes=s["offset_minutes"])
        ch_rows.append({
            "tenant_id": tenant_id,
            "trace_id": s["trace_id"],
            "span_id": s["span_id"],
            "parent_span_id": "",
            "time_begin": t_begin,
            "time_end": t_begin + timedelta(seconds=30),
            "agent_name": s["agent_name"],
            "agent_model": s["agent_model"],
            "recipient": "user",
            "recipient_model": "",
            "tool_name": s["tool_name"],
            "tool_description": s["tool_description"],
            "tool_arguments": s["tool_arguments"],
            "tool_output": s["tool_output"],
            "available_tools_ref": refs["available_tools_ref"],
            "prompt_ref": refs["prompt_ref"],
            "response_ref": refs["response_ref"],
            "raw_response_ref": refs["raw_response_ref"],
            "schema_version": "1.0",
        })

    columns = list(ch_rows[0].keys())
    ch.insert("spans", [[r[c] for c in columns] for r in ch_rows], column_names=columns)
    print(f"Uploaded payloads to S3 and inserted {len(ch_rows)} spans into ClickHouse")

    # 3. Insert flags and scores into PostgreSQL
    async with session_factory() as session:
        async with session.begin():
            for s in _SPANS_FIXTURE:
                if s["flag_type"]:
                    session.add(Flag(
                        tenant_id=uuid.UUID(tenant_id),
                        span_id=s["span_id"],
                        trace_id=s["trace_id"],
                        flag_type=s["flag_type"],
                        score=s["flag_score"],
                        detail=s["flag_detail"],
                    ))

                await session.execute(
                    text(
                        "INSERT INTO span_scores (score_id, tenant_id, span_id, analyzer_name, metric_name, score) "
                        "VALUES (:id, :tid, :sid, :an, :mn, :sc)"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "tid": tenant_id,
                        "sid": s["span_id"],
                        "an": "tool_call_analyzer",
                        "mn": s["flag_type"] or "clean_check",
                        "sc": s["flag_score"] or 0.0,
                    },
                )

    print()
    print("Summary:")
    for s in _SPANS_FIXTURE:
        status = f"flagged ({s['flag_type']}, score={s['flag_score']})" if s["flag_type"] else "clean"
        print(f"  {s['span_id']:<12} {s['agent_name']:<20} {status}")


if __name__ == "__main__":
    asyncio.run(main())
