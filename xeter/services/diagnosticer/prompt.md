You are diagnosing a failing AI agent tool call. Analyze the data below and identify the root cause.

## Span Information
- span_id: {span_id}
- trace_id: {trace_id}
- agent_name: {agent_name}
- agent_model: {agent_model}
- tool_name: {tool_name}
- tool_description: {tool_description}
- tool_arguments: {tool_arguments}
- tool_output: {tool_output}
- time_begin: {time_begin}

## Prompt Text (full content)
{prompt_text}

## Response Text (full content)
{response_text}

## Anomaly Flags (all flags for this span, with scores)
{flags_section}

## Task
Based on the above, call the `record_diagnosis` tool with your root-cause analysis.
