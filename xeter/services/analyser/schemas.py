# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
"""
Pydantic v2 schema for the POST /v1/spans request body.

Provides:
  - SpanPayload: validated request model for a single span ingestion

The xeter.schema.version field uses a dotted alias due to Python naming
restrictions. Pydantic v2 populate_by_name=True allows both the alias
and the field name to be used.
"""

from typing import Optional

from pydantic import BaseModel, Field


class SpanPayload(BaseModel):
    """Request body for POST /v1/spans.

    Required fields: span_id, agent_name, agent_model, time_begin, time_end.
    All other fields are optional (tool spans may omit prompt/response;
    non-tool spans may omit tool_* fields).

    The schema_version field is sent by the SDK as "xeter.schema.version"
    (dotted key) and mapped via Pydantic alias.
    """

    span_id: str
    trace_id: Optional[str] = None
    parent_span_id: Optional[str] = None
    agent_name: str
    agent_model: str
    tool_name: Optional[str] = None
    tool_description: Optional[str] = None
    tool_arguments: Optional[str] = None  # JSON string, stored inline in ClickHouse
    expected_output_schema: Optional[str] = None  # inline JSON string, same pattern as tool_arguments
    tool_output: Optional[str] = None
    prompt: Optional[str] = None
    response: Optional[str] = None
    raw_response: Optional[str] = None
    available_tools_ref: Optional[str] = None  # raw value — goes to S3
    time_begin: str  # ISO 8601
    time_end: str  # ISO 8601
    schema_version: str = Field(alias="xeter.schema.version", default="1.0")

    model_config = {"populate_by_name": True}
