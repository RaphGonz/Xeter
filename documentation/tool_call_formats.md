# Tool Call Format Registry

Reference for all model formats supported by `xeter/services/worker/tool_call_registry.py`.

Source: [r/LocalLLaMA benchmark](https://old.reddit.com/r/LocalLLaMA/comments/1r4ie8z/i_tested_21_small_llms_on_toolcalling_judgment/)

---

## API-Structured Models

These models return tool calls as structured JSON via provider SDKs. Xeter validates the JSON structure and argument field types.

| Model | Format | Argument Field | Argument Type | Notes |
|-------|--------|---------------|---------------|-------|
| claude-3-opus | anthropic_api | input | object | Multiple tool_use blocks possible |
| claude-3-sonnet | anthropic_api | input | object | Parallel tool calls in content[] |
| claude-3-haiku | anthropic_api | input | object | |
| claude-3-5-sonnet | anthropic_api | input | object | |
| claude-3-7-sonnet | anthropic_api | input | object | Extended thinking blocks before tool_use |
| claude-opus-4 | anthropic_api | input | object | Unicode/forward-slash escaping in input |
| claude-sonnet-4 | anthropic_api | input | object | |
| gpt-4o | openai_chat_completions | function.arguments | json_string | Must JSON.parse arguments |
| gpt-4o-mini | openai_chat_completions | function.arguments | json_string | |
| gpt-4-turbo | openai_chat_completions | function.arguments | json_string | |
| gpt-4 | openai_function_call_legacy | function_call.arguments | json_string | Legacy single function_call |
| gpt-3-5-turbo | openai_function_call_legacy | function_call.arguments | json_string | |
| gpt-4o-responses-api | openai_responses_api | arguments | json_string | Newer /v1/responses endpoint |
| o1 | openai_responses_api | arguments | json_string | Reasoning items must be passed back |
| o3 | openai_responses_api | arguments | json_string | |
| gemini-2-0-flash | gemini_native | function_call.args | proto_struct | args is a dict, not string. Check parts[i].function_call |
| gemini-2-5-flash | gemini_native | function_call.args | proto_struct | thought_signature in parts |
| gemini-2-5-pro | gemini_native | function_call.args | proto_struct | Mixed functionCall/toolCall parts |
| gemini-3-flash | gemini_native | function_call.args | proto_struct | Do not merge parts with/without signature |
| gemini-openai-compat | openai_chat_completions | function.arguments | json_string | Vertex AI OpenAI-compatible endpoint |
| mistral-large | openai_chat_completions | function.arguments | json_string | OpenAI-compatible API |
| mistral-small | openai_chat_completions | function.arguments | json_string | |
| command-r-plus | cohere_api | parameters | object | finish_reason is 'TOOL_CALL' (uppercase) |
| command-r | cohere_api | parameters | object | |

---

## Raw-Text Models (Local/Open)

These models emit tool calls as raw text. The parser must extract the tool call from the model output using regex patterns.

| Model | Format | Detect Pattern | Notes |
|-------|--------|---------------|-------|
| claude-2-bedrock | anthropic_bedrock_xml | `<function_calls>`, `<invoke>`, `<tool_name>` | Not valid XML — do not use XML parser |
| hermes-2-pro | hermes_xml | `<tool_call>`, `</tool_call>` | JSON inside tags. Standard Nous Research format |
| hermes-3 | hermes_xml | `<tool_call>`, `</tool_call>` | |
| qwen2-5 | hermes_xml | `<tool_call>`, `</tool_call>` | Hermes-style by default |
| qwen3 | hermes_xml_or_bracket | `<tool_call>` or `[Calling tool:` | Format varies by version. Non-monotonic capability: 0.6B ~ 4B > 1.7B |
| qwen2-5-0-5b | hermes_xml | `<tool_call>` | Higher wrong-tool rate |
| qwen2-5-1-5b | hermes_xml | `<tool_call>` | |
| qwen2-5-3b | hermes_xml | `<tool_call>` | |
| qwen3-0-6b | hermes_xml | `<tool_call>` | Ties #1 at 600M params |
| qwen3-1-7b | hermes_xml | `<tool_call>` | Capability valley: aggressive calls, poor restraint |
| qwen3-4b | hermes_xml | `<tool_call>` | Ties #1. ~17x slower than 0.6B |
| llama-3-1 | llama3_function_tag | `<\|python_tag\|>` or `<function=` | Two sub-variants. Custom prompts can cause XML output |
| llama-3-2-1b | llama3_function_tag | `<\|python_tag\|>` or `<function=` | Lowest benchmark score (0.430) |
| llama-3-2-3b | llama3_function_tag | `<\|python_tag\|>` or `<function=` | Zero restraint — tools on every prompt |
| llama-3-3 | llama3_function_tag | `<\|python_tag\|>` or `<function=` | Wrong parser = silent A4 failure |
| llama-4 | llama3_function_tag | `<\|python_tag\|>` or `<function=` | |
| mistral-7b-instruct | mistral_bracket | `[TOOL_CALLS]` | Arguments is an object, not string |
| devstral | mistral_bracket | `[TOOL_CALLS]` | |
| ministral-3b | mistral_bracket | `[TOOL_CALLS]` | Score 0.800. Good restraint |
| deepseek-v3 | deepseek_special_tokens | (non-printable Unicode) | Regex on UTF-8 fails silently. Inspect raw bytes |
| deepseek-r1 | deepseek_bare | `^\s*\w+\s*\(` | Bare function call: `get_weather(city="X")` |
| deepseek-r1-1-5b | deepseek_bare | `^\s*\w+\s*\(` | |
| phi4-mini | hermes_xml | `<tool_call>`, `</tool_call>` | Ties #1 at 3.8B. Perfect restraint |
| smollm2-1-7b | hermes_xml | `<tool_call>` | |
| smollm3-3b | hermes_xml_no_tags | `<tool_call>` or bare JSON | Sometimes omits tags entirely |
| lfm2-5-1-2b | bracket_pythonic | `[func_name(` | LiquidAI. Python-style args, not JSON |
| xlam | pythonic_list | `[func_name(` | Salesforce. May wrap in `<think>` tags |
| olmo-3 | olmo_function_calls | `<function_calls>` or `[func(` | Pythonic in XML wrapper. Allows JSON + Python booleans |
| gemma3-1b | gemma_function_tag | `<function>`, `</function>` | Python syntax inside custom tags |
| functiongemma | bare_json | `{"name":` | 270M, fastest (476ms). Perfect restraint |
| jan-v3-4b | bare_json | `{"name":` | Zero restraint — always calls a tool |
| granite4-3b | granite_special_token | `<\|tool_call\|>` or `<tool_call>` | Score 0.670 |
| granite3-3-2b | granite_special_token | `<\|tool_call\|>` or `<tool_call>` | Score 0.480 |
| nemotron-3 | nemotron_nested_xml | `<tool_call>`, `<function=`, `<parameter=` | Nested XML with parameter subnodes |
| kimi-k2 | kimi_special_tokens | `<\|tool_call_begin\|>`, `<\|tool_call_end\|>` | Moonshot AI |
| glm-4-7 | glm_xml | `<tool_call>`, `<arg_key>`, `<arg_value>` | XML with named arg subnodes |
| bitnet-2b | hermes_xml | `<tool_call>` | Aggressive action (0.900), 0.500 restraint |
| bitnet-3b | hermes_xml | `<tool_call>` | Action 0.000 — never calls a tool |
| internlm2 | hermes_xml | `<tool_call>` | Unstable per vLLM docs |

---

## Format Groups

| Format | Argument Type | Stop Signal |
|--------|--------------|-------------|
| anthropic_api | object | stop_reason:tool_use |
| anthropic_bedrock_xml | xml_params | closing_tag |
| openai_chat_completions | json_string | finish_reason:tool_calls |
| openai_function_call_legacy | json_string | finish_reason:function_call |
| openai_responses_api | json_string | type:function_call |
| cohere_api | object | finish_reason:TOOL_CALL |
| gemini_native | proto_struct | parts[i].function_call |
| hermes_xml | json_object_in_tag | `</tool_call>` |
| hermes_xml_or_bracket | json_object_in_tag | `</tool_call>` or ] |
| hermes_xml_no_tags | json_object_or_bare | `</tool_call>` or EOF |
| mistral_bracket | object | [TOOL_CALLS] |
| llama3_function_tag | json_object_in_tag | `</function>` or `<\|eot_id\|>` |
| deepseek_special_tokens | json_object | special_token_end |
| deepseek_bare | python_call | closing_paren |
| bracket_pythonic | python_call | ] |
| pythonic_list | python_call | ] |
| olmo_function_calls | python_call | `</function_calls>` |
| gemma_function_tag | python_call | `</function>` |
| bare_json | object | } |
| granite_special_token | json_object | `<\|end_of_text\|>` |
| nemotron_nested_xml | xml_params | `</tool_call>` |
| kimi_special_tokens | json_object | `<\|tool_call_end\|>` |
| glm_xml | xml_params | `</tool_call>` |
