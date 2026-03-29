"""Tool Call Format Registry — pure data, no logic dependencies.

Each model entry maps a model name to its tool-call format, transport type,
regex detection patterns, argument field path, and known hazards.

To add a new model: add a dict entry to TOOL_CALL_REGISTRY. No code changes,
no rebuilds. Restart the worker process to pick up the new entry.

To add a new format family: add to FORMAT_GROUPS and reference it from entries.

Reference: https://old.reddit.com/r/LocalLLaMA/comments/1r4ie8z/i_tested_21_small_llms_on_toolcalling_judgment/
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Registry: model name → format spec
# ---------------------------------------------------------------------------

TOOL_CALL_REGISTRY: dict[str, dict] = {

    # ── FRONTIER / CLOUD APIs — transport: api_structured ──────────────
    # Tool calls are parsed by the provider SDK into structured objects.
    # For Xeter: check the parsed span fields, not raw_response regex.

    "claude-3-opus": {
        "format": "anthropic_api",
        "transport": "api_structured",
        "detect": [
            re.compile(r'"type"\s*:\s*"tool_use"'),
            re.compile(r'"stop_reason"\s*:\s*"tool_use"'),
        ],
        "argument_field": "input",
        "notes": "input is an object, not a string. Multiple tool_use blocks possible in one response.",
    },

    "claude-3-sonnet": {
        "format": "anthropic_api",
        "transport": "api_structured",
        "detect": [
            re.compile(r'"type"\s*:\s*"tool_use"'),
            re.compile(r'"stop_reason"\s*:\s*"tool_use"'),
        ],
        "argument_field": "input",
        "notes": "Parallel tool calls: multiple tool_use blocks in content[].",
    },

    "claude-3-haiku": {
        "format": "anthropic_api",
        "transport": "api_structured",
        "detect": [
            re.compile(r'"type"\s*:\s*"tool_use"'),
            re.compile(r'"stop_reason"\s*:\s*"tool_use"'),
        ],
        "argument_field": "input",
        "notes": "Same as opus.",
    },

    "claude-3-5-sonnet": {
        "format": "anthropic_api",
        "transport": "api_structured",
        "detect": [
            re.compile(r'"type"\s*:\s*"tool_use"'),
            re.compile(r'"stop_reason"\s*:\s*"tool_use"'),
        ],
        "argument_field": "input",
        "notes": "Same as opus.",
    },

    "claude-3-7-sonnet": {
        "format": "anthropic_api",
        "transport": "api_structured",
        "detect": [
            re.compile(r'"type"\s*:\s*"tool_use"'),
            re.compile(r'"stop_reason"\s*:\s*"tool_use"'),
        ],
        "argument_field": "input",
        "notes": "Extended thinking blocks may appear before tool_use blocks.",
    },

    "claude-opus-4": {
        "format": "anthropic_api",
        "transport": "api_structured",
        "detect": [
            re.compile(r'"type"\s*:\s*"tool_use"'),
            re.compile(r'"stop_reason"\s*:\s*"tool_use"'),
        ],
        "argument_field": "input",
        "notes": "May produce different JSON string escaping in input fields (Unicode, forward-slash). Always json.loads input values.",
    },

    "claude-sonnet-4": {
        "format": "anthropic_api",
        "transport": "api_structured",
        "detect": [
            re.compile(r'"type"\s*:\s*"tool_use"'),
            re.compile(r'"stop_reason"\s*:\s*"tool_use"'),
        ],
        "argument_field": "input",
        "notes": "Same as opus-4.",
    },

    # Legacy Claude 2 via Amazon Bedrock (XML orchestration prompt)
    "claude-2-bedrock": {
        "format": "anthropic_bedrock_xml",
        "transport": "raw_text",
        "detect": [
            re.compile(r"<function_calls>"),
            re.compile(r"<invoke>"),
            re.compile(r"<tool_name>"),
        ],
        "argument_field": None,
        "notes": "Used in Bedrock orchestration prompts for Claude 2.x. Not valid XML — do not use an XML parser.",
    },

    # ── OpenAI / GPT ──────────────────────────────────────────────────

    "gpt-4o": {
        "format": "openai_chat_completions",
        "transport": "api_structured",
        "detect": [
            re.compile(r'"tool_calls"\s*:'),
            re.compile(r'"finish_reason"\s*:\s*"tool_calls"'),
        ],
        "argument_field": "function.arguments",
        "notes": "function.arguments is a JSON string, not an object. finish_reason is 'tool_calls'. Parallel calls: message.tool_calls[].",
    },

    "gpt-4o-mini": {
        "format": "openai_chat_completions",
        "transport": "api_structured",
        "detect": [
            re.compile(r'"tool_calls"\s*:'),
            re.compile(r'"finish_reason"\s*:\s*"tool_calls"'),
        ],
        "argument_field": "function.arguments",
        "notes": "Same as gpt-4o.",
    },

    "gpt-4-turbo": {
        "format": "openai_chat_completions",
        "transport": "api_structured",
        "detect": [
            re.compile(r'"tool_calls"\s*:'),
            re.compile(r'"finish_reason"\s*:\s*"tool_calls"'),
        ],
        "argument_field": "function.arguments",
        "notes": "Same as gpt-4o.",
    },

    "gpt-4": {
        "format": "openai_function_call_legacy",
        "transport": "api_structured",
        "detect": [
            re.compile(r'"function_call"\s*:'),
            re.compile(r'"finish_reason"\s*:\s*"function_call"'),
        ],
        "argument_field": "function_call.arguments",
        "notes": "Legacy single function_call field (pre-tools API). finish_reason is 'function_call'.",
    },

    "gpt-3-5-turbo": {
        "format": "openai_function_call_legacy",
        "transport": "api_structured",
        "detect": [
            re.compile(r'"function_call"\s*:'),
            re.compile(r'"finish_reason"\s*:\s*"function_call"'),
        ],
        "argument_field": "function_call.arguments",
        "notes": "Same as gpt-4 legacy.",
    },

    # OpenAI Responses API (gpt-4o and later via /v1/responses)
    "gpt-4o-responses-api": {
        "format": "openai_responses_api",
        "transport": "api_structured",
        "detect": [
            re.compile(r'"type"\s*:\s*"function_call"'),
            re.compile(r'"call_id"\s*:'),
        ],
        "argument_field": "arguments",
        "notes": "Newer Responses API format. output[] items with type='function_call', call_id, name, arguments (still a JSON string).",
    },

    "o1": {
        "format": "openai_responses_api",
        "transport": "api_structured",
        "detect": [
            re.compile(r'"type"\s*:\s*"function_call"'),
            re.compile(r'"call_id"\s*:'),
        ],
        "argument_field": "arguments",
        "notes": "Reasoning items in response must also be passed back with tool call outputs.",
    },

    "o3": {
        "format": "openai_responses_api",
        "transport": "api_structured",
        "detect": [
            re.compile(r'"type"\s*:\s*"function_call"'),
            re.compile(r'"call_id"\s*:'),
        ],
        "argument_field": "arguments",
        "notes": "Same as o1.",
    },

    # ── Google Gemini ─────────────────────────────────────────────────

    "gemini-2-0-flash": {
        "format": "gemini_native",
        "transport": "api_structured",
        "detect": [
            re.compile(r'"function_call"\s*:'),
            re.compile(r'"finishReason"\s*:'),
        ],
        "argument_field": "function_call.args",
        "notes": "args is a dict object, not a JSON string. Detect tool call by checking parts[i].function_call, not finish_reason. Parallel calls: iterate all parts[].",
    },

    "gemini-2-5-flash": {
        "format": "gemini_native",
        "transport": "api_structured",
        "detect": [
            re.compile(r'"function_call"\s*:'),
        ],
        "argument_field": "function_call.args",
        "notes": "With Gemini 3+ models, thought_signature may appear in parts — must be passed back to model unchanged.",
    },

    "gemini-2-5-pro": {
        "format": "gemini_native",
        "transport": "api_structured",
        "detect": [
            re.compile(r'"function_call"\s*:'),
        ],
        "argument_field": "function_call.args",
        "notes": "Tool combination (built-in + custom) can produce mixed functionCall, toolCall, toolResponse parts in same turn.",
    },

    "gemini-3-flash": {
        "format": "gemini_native",
        "transport": "api_structured",
        "detect": [
            re.compile(r'"function_call"\s*:'),
            re.compile(r'"toolCall"\s*:'),
        ],
        "argument_field": "function_call.args",
        "notes": "Gemini 3 adds thought_signature. Do not merge parts with and without signature.",
    },

    "gemini-openai-compat": {
        "format": "openai_chat_completions",
        "transport": "api_structured",
        "detect": [
            re.compile(r'"tool_calls"\s*:'),
        ],
        "argument_field": "function.arguments",
        "notes": "When accessed via OpenAI-compatible Vertex endpoint, format matches openai_chat_completions. function.arguments is a JSON string.",
    },

    # ── Mistral (API) ─────────────────────────────────────────────────

    "mistral-large": {
        "format": "openai_chat_completions",
        "transport": "api_structured",
        "detect": [
            re.compile(r'"tool_calls"\s*:'),
            re.compile(r'"finish_reason"\s*:\s*"tool_calls"'),
        ],
        "argument_field": "function.arguments",
        "notes": "OpenAI-compatible API format. arguments is a JSON string.",
    },

    "mistral-small": {
        "format": "openai_chat_completions",
        "transport": "api_structured",
        "detect": [
            re.compile(r'"tool_calls"\s*:'),
        ],
        "argument_field": "function.arguments",
        "notes": "Same as mistral-large.",
    },

    # ── Cohere ────────────────────────────────────────────────────────

    "command-r-plus": {
        "format": "cohere_api",
        "transport": "api_structured",
        "detect": [
            re.compile(r'"tool_calls"\s*:'),
            re.compile(r'"finish_reason"\s*:\s*"TOOL_CALL"'),
        ],
        "argument_field": "parameters",
        "notes": "parameters is already an object. finish_reason is 'TOOL_CALL' (uppercase).",
    },

    "command-r": {
        "format": "cohere_api",
        "transport": "api_structured",
        "detect": [
            re.compile(r'"tool_calls"\s*:'),
            re.compile(r'"finish_reason"\s*:\s*"TOOL_CALL"'),
        ],
        "argument_field": "parameters",
        "notes": "Same as command-r-plus.",
    },

    # ── LOCAL / OPEN MODELS — transport: raw_text ─────────────────────
    # Parser must extract tool call from raw model output string.

    "hermes-2-pro": {
        "format": "hermes_xml",
        "transport": "raw_text",
        "detect": [
            re.compile(r"<tool_call>"),
            re.compile(r"</tool_call>"),
        ],
        "argument_field": None,
        "notes": "JSON object inside <tool_call> tags. Keys: name, arguments (object). Standard Nous Research format.",
    },

    "hermes-3": {
        "format": "hermes_xml",
        "transport": "raw_text",
        "detect": [
            re.compile(r"<tool_call>"),
            re.compile(r"</tool_call>"),
        ],
        "argument_field": None,
        "notes": "Same as hermes-2-pro.",
    },

    "qwen2-5": {
        "format": "hermes_xml",
        "transport": "raw_text",
        "detect": [
            re.compile(r"<tool_call>"),
            re.compile(r"</tool_call>"),
        ],
        "argument_field": None,
        "notes": "Qwen 2.5 uses Hermes-style <tool_call> by default.",
    },

    "qwen3": {
        "format": "hermes_xml_or_bracket",
        "transport": "raw_text",
        "detect": [
            re.compile(r"<tool_call>"),
            re.compile(r"\[Calling tool:"),
        ],
        "argument_field": None,
        "notes": "Qwen3 outputs <tool_call>{...}</tool_call> or [Calling tool: X] depending on version and prompt. Non-monotonic capability across sizes: 0.6B ~ 4B > 1.7B.",
    },

    "qwen2-5-0-5b": {
        "format": "hermes_xml",
        "transport": "raw_text",
        "detect": [re.compile(r"<tool_call>")],
        "argument_field": None,
        "notes": "Smallest Qwen2.5. Higher wrong-tool rate per benchmark.",
    },

    "qwen2-5-1-5b": {
        "format": "hermes_xml",
        "transport": "raw_text",
        "detect": [re.compile(r"<tool_call>")],
        "argument_field": None,
        "notes": "Same format.",
    },

    "qwen2-5-3b": {
        "format": "hermes_xml",
        "transport": "raw_text",
        "detect": [re.compile(r"<tool_call>")],
        "argument_field": None,
        "notes": "Same format.",
    },

    "qwen3-0-6b": {
        "format": "hermes_xml",
        "transport": "raw_text",
        "detect": [re.compile(r"<tool_call>")],
        "argument_field": None,
        "notes": "Ties #1 in benchmark at 600M params. Hermes-style output.",
    },

    "qwen3-1-7b": {
        "format": "hermes_xml",
        "transport": "raw_text",
        "detect": [re.compile(r"<tool_call>")],
        "argument_field": None,
        "notes": "Capability valley per benchmark: aggressive tool calls, poor restraint.",
    },

    "qwen3-4b": {
        "format": "hermes_xml",
        "transport": "raw_text",
        "detect": [re.compile(r"<tool_call>")],
        "argument_field": None,
        "notes": "Ties #1 in benchmark. ~17x slower than 0.6B.",
    },

    "llama-3-1": {
        "format": "llama3_function_tag",
        "transport": "raw_text",
        "detect": [
            re.compile(r"<\|python_tag\|>"),
            re.compile(r"<function="),
        ],
        "argument_field": None,
        "notes": "Two sub-variants: <|python_tag|>{JSON} or <function=name>{...}</function>. Custom system prompts can cause XML output that the llama3_json parser cannot handle.",
    },

    "llama-3-2-1b": {
        "format": "llama3_function_tag",
        "transport": "raw_text",
        "detect": [
            re.compile(r"<\|python_tag\|>"),
            re.compile(r"<function="),
        ],
        "argument_field": None,
        "notes": "Lowest score in benchmark (0.430). High wrong-tool and restraint failure rate.",
    },

    "llama-3-2-3b": {
        "format": "llama3_function_tag",
        "transport": "raw_text",
        "detect": [
            re.compile(r"<\|python_tag\|>"),
            re.compile(r"<function="),
        ],
        "argument_field": None,
        "notes": "Zero restraint score in benchmark — calls a tool on almost every prompt.",
    },

    "llama-3-3": {
        "format": "llama3_function_tag",
        "transport": "raw_text",
        "detect": [
            re.compile(r"<\|python_tag\|>"),
            re.compile(r"<function="),
        ],
        "argument_field": None,
        "notes": "Using hermes parser with llama3.3 silently produces no tool calls — wrong parser = silent A4 failure.",
    },

    "llama-4": {
        "format": "llama3_function_tag",
        "transport": "raw_text",
        "detect": [
            re.compile(r"<\|python_tag\|>"),
            re.compile(r"<function="),
        ],
        "argument_field": None,
        "notes": "Same family format as Llama 3.x.",
    },

    "mistral-7b-instruct": {
        "format": "mistral_bracket",
        "transport": "raw_text",
        "detect": [
            re.compile(r"\[TOOL_CALLS\]"),
        ],
        "argument_field": None,
        "notes": "Output: [TOOL_CALLS] [{\"name\":\"f\",\"arguments\":{...}}]. Arguments is an object, not a string.",
    },

    "devstral": {
        "format": "mistral_bracket",
        "transport": "raw_text",
        "detect": [
            re.compile(r"\[TOOL_CALLS\]"),
        ],
        "argument_field": None,
        "notes": "Same as mistral-7b-instruct local.",
    },

    "ministral-3b": {
        "format": "mistral_bracket",
        "transport": "raw_text",
        "detect": [
            re.compile(r"\[TOOL_CALLS\]"),
        ],
        "argument_field": None,
        "notes": "Score 0.800 in benchmark. Good restraint.",
    },

    "deepseek-v3": {
        "format": "deepseek_special_tokens",
        "transport": "raw_text",
        "detect": [],
        "argument_field": None,
        "notes": "Uses non-printable Unicode delimiters. Regex on UTF-8 string will silently fail. Inspect raw bytes.",
    },

    "deepseek-r1": {
        "format": "deepseek_bare",
        "transport": "raw_text",
        "detect": [
            re.compile(r"^\s*\w+\s*\(", re.MULTILINE),
        ],
        "argument_field": None,
        "notes": "Bare function calls: get_weather(city=\"X\"). Low action score (0.300).",
    },

    "deepseek-r1-1-5b": {
        "format": "deepseek_bare",
        "transport": "raw_text",
        "detect": [
            re.compile(r"^\s*\w+\s*\(", re.MULTILINE),
        ],
        "argument_field": None,
        "notes": "Same as deepseek-r1.",
    },

    "phi4-mini": {
        "format": "hermes_xml",
        "transport": "raw_text",
        "detect": [
            re.compile(r"<tool_call>"),
            re.compile(r"</tool_call>"),
        ],
        "argument_field": None,
        "notes": "phi4-mini:3.8b ties #1 in benchmark. Hermes-style format. Perfect restraint score.",
    },

    "smollm2-1-7b": {
        "format": "hermes_xml",
        "transport": "raw_text",
        "detect": [
            re.compile(r"<tool_call>"),
        ],
        "argument_field": None,
        "notes": "Generally standard Hermes format.",
    },

    "smollm3-3b": {
        "format": "hermes_xml_no_tags",
        "transport": "raw_text",
        "detect": [
            re.compile(r"<tool_call>"),
            re.compile(r'^\s*\{.*"name"\s*:', re.MULTILINE | re.DOTALL),
        ],
        "argument_field": None,
        "notes": "Sometimes omits wrapper tags entirely, emitting bare JSON. Must attempt both patterns.",
    },

    "lfm2-5-1-2b": {
        "format": "bracket_pythonic",
        "transport": "raw_text",
        "detect": [
            re.compile(r"^\s*\[\w+\s*\(", re.MULTILINE),
        ],
        "argument_field": None,
        "notes": "LiquidAI SSM hybrid. Bracket notation: [get_weather(city=\"X\")]. Arguments are Python-style, not JSON.",
    },

    "xlam": {
        "format": "pythonic_list",
        "transport": "raw_text",
        "detect": [
            re.compile(r"^\s*\[\w+\s*\(", re.MULTILINE),
            re.compile(r"<think>.*\[\w+\s*\(", re.MULTILINE | re.DOTALL),
        ],
        "argument_field": None,
        "notes": "Salesforce xLAM. Python list syntax. May wrap in <think> tags before emitting the list.",
    },

    "olmo-3": {
        "format": "olmo_function_calls",
        "transport": "raw_text",
        "detect": [
            re.compile(r"<function_calls>"),
            re.compile(r"\[\w+\s*\(", re.MULTILINE),
        ],
        "argument_field": None,
        "notes": "Pythonic list wrapped in <function_calls> XML. Allows JSON booleans alongside Python literals.",
    },

    "gemma3-1b": {
        "format": "gemma_function_tag",
        "transport": "raw_text",
        "detect": [
            re.compile(r"<function>"),
            re.compile(r"</function>"),
        ],
        "argument_field": None,
        "notes": "Outputs function syntax inside custom tags: <function>get_weather(city=\"X\")</function>.",
    },

    "functiongemma": {
        "format": "bare_json",
        "transport": "raw_text",
        "detect": [
            re.compile(r'^\s*\{"name"\s*:', re.MULTILINE),
        ],
        "argument_field": None,
        "notes": "270M model. Fastest (476ms). Bare JSON: {\"name\":\"f\",\"parameters\":{...}}.",
    },

    "jan-v3-4b": {
        "format": "bare_json",
        "transport": "raw_text",
        "detect": [
            re.compile(r'^\s*\{"name"\s*:', re.MULTILINE),
        ],
        "argument_field": None,
        "notes": "Raw JSON object with no wrapper. Action 0.900 but zero restraint.",
    },

    "granite4-3b": {
        "format": "granite_special_token",
        "transport": "raw_text",
        "detect": [
            re.compile(r"<\|tool_call\|>"),
            re.compile(r"<tool_call>"),
        ],
        "argument_field": None,
        "notes": "IBM Granite 4.x. Uses <|tool_call|> special token or <tool_call>.",
    },

    "granite3-3-2b": {
        "format": "granite_special_token",
        "transport": "raw_text",
        "detect": [
            re.compile(r"<\|tool_call\|>"),
            re.compile(r"<tool_call>"),
        ],
        "argument_field": None,
        "notes": "Same format as granite4. Lower score (0.480).",
    },

    "nemotron-3": {
        "format": "nemotron_nested_xml",
        "transport": "raw_text",
        "detect": [
            re.compile(r"<tool_call>"),
            re.compile(r"<function="),
            re.compile(r"<parameter="),
        ],
        "argument_field": None,
        "notes": "NVIDIA Nemotron. Nested XML: <tool_call><function=name><parameter=k>v</parameter></function></tool_call>.",
    },

    "kimi-k2": {
        "format": "kimi_special_tokens",
        "transport": "raw_text",
        "detect": [
            re.compile(r"<\|tool_call_begin\|>"),
            re.compile(r"<\|tool_call_end\|>"),
        ],
        "argument_field": None,
        "notes": "Moonshot AI Kimi K2. Uses special tokens as delimiters.",
    },

    "glm-4-7": {
        "format": "glm_xml",
        "transport": "raw_text",
        "detect": [
            re.compile(r"<tool_call>"),
            re.compile(r"<arg_key>"),
            re.compile(r"<arg_value>"),
        ],
        "argument_field": None,
        "notes": "Zhipu GLM-4.7. XML with named arg subnodes.",
    },

    "bitnet-2b": {
        "format": "hermes_xml",
        "transport": "raw_text",
        "detect": [re.compile(r"<tool_call>")],
        "argument_field": None,
        "notes": "bitnet-2B-4T. Aggressive action (0.900) but only 0.500 restraint.",
    },

    "bitnet-3b": {
        "format": "hermes_xml",
        "transport": "raw_text",
        "detect": [re.compile(r"<tool_call>")],
        "argument_field": None,
        "notes": "bitnet-3B. Action 0.000 — never calls a tool.",
    },

    "internlm2": {
        "format": "hermes_xml",
        "transport": "raw_text",
        "detect": [re.compile(r"<tool_call>")],
        "argument_field": None,
        "notes": "InternLM2. Tool call results are not stable. Treat as unreliable.",
    },
}

# ---------------------------------------------------------------------------
# Format groups — family-level metadata
# ---------------------------------------------------------------------------

FORMAT_GROUPS: dict[str, dict] = {
    "anthropic_api":               {"argument_type": "object",               "stop_signal": "stop_reason:tool_use"},
    "anthropic_bedrock_xml":       {"argument_type": "xml_params",           "stop_signal": "closing_tag"},
    "openai_chat_completions":     {"argument_type": "json_string",          "stop_signal": "finish_reason:tool_calls"},
    "openai_function_call_legacy": {"argument_type": "json_string",          "stop_signal": "finish_reason:function_call"},
    "openai_responses_api":        {"argument_type": "json_string",          "stop_signal": "type:function_call"},
    "cohere_api":                  {"argument_type": "object",               "stop_signal": "finish_reason:TOOL_CALL"},
    "gemini_native":               {"argument_type": "proto_struct",         "stop_signal": "parts[i].function_call"},
    "hermes_xml":                  {"argument_type": "json_object_in_tag",   "stop_signal": "</tool_call>"},
    "hermes_xml_or_bracket":       {"argument_type": "json_object_in_tag",   "stop_signal": "</tool_call> or ]"},
    "hermes_xml_no_tags":          {"argument_type": "json_object_or_bare",  "stop_signal": "</tool_call> or EOF"},
    "mistral_bracket":             {"argument_type": "object",               "stop_signal": "[TOOL_CALLS]"},
    "llama3_function_tag":         {"argument_type": "json_object_in_tag",   "stop_signal": "</function> or <|eot_id|>"},
    "deepseek_special_tokens":     {"argument_type": "json_object",          "stop_signal": "special_token_end"},
    "deepseek_bare":               {"argument_type": "python_call",          "stop_signal": "closing_paren"},
    "bracket_pythonic":            {"argument_type": "python_call",          "stop_signal": "]"},
    "pythonic_list":               {"argument_type": "python_call",          "stop_signal": "]"},
    "olmo_function_calls":         {"argument_type": "python_call",          "stop_signal": "</function_calls>"},
    "gemma_function_tag":          {"argument_type": "python_call",          "stop_signal": "</function>"},
    "bare_json":                   {"argument_type": "object",               "stop_signal": "}"},
    "granite_special_token":       {"argument_type": "json_object",          "stop_signal": "<|end_of_text|>"},
    "nemotron_nested_xml":         {"argument_type": "xml_params",           "stop_signal": "</tool_call>"},
    "kimi_special_tokens":         {"argument_type": "json_object",          "stop_signal": "<|tool_call_end|>"},
    "glm_xml":                     {"argument_type": "xml_params",           "stop_signal": "</tool_call>"},
}


def extract_nested(obj: dict, path: str):
    """Safely access a nested path like 'function.arguments' in a dict."""
    if not path:
        return None
    current = obj
    for key in path.split("."):
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current
