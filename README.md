# Xeter
Local Agent Tool Call Debugger

# Stop debugging local agent tool calls in the dark.

When your agent fails to call a tool, you shouldn't have to spend hours discovering it was a parser format mismatch, a model capability ceiling, or a bad tool description. Icosa tells you immediately which layer broke and why.

Drop it into any stack. Works with any local model. No framework lock-in

# Goals

A debugger that tracks tool calls and detects :
* format/parsing failure
*  model capability ceiling
*  wrong tool selection
*  prompt quality issues
*  tool description quality issues
*  overcalls or undercalls

# Architecture

layer 1 catches the obvious mechanical failures fast and cheap, layer 2 explains the ambiguous reasoning failures using an LLM supervisor
