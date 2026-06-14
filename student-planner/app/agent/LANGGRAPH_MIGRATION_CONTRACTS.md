# LangGraph Migration Contracts

This is the pre-migration contract for replacing the legacy `run_agent_loop()` with a LangGraph-native loop later. It is not a full migration plan and it must not change the current product behavior by itself.

## Architecture Boundary

LangGraph should own orchestration: route selection, state transitions, loop limits, confirmation pauses, tool execution ordering, and event emission order. LangChain chains or Runnables are still useful inside graph nodes for local LLM work, prompt formatting, parsing, retrieval, and tool-bound model calls. The graph is the control plane; chains are node implementation details.

The current runtime is only partially LangGraph-based:

1. `chat.py` chooses `run_langgraph_agent_loop` when `SP_AGENT_RUNTIME=langgraph`.
2. `langgraph_loop.py` runs a small graph for RAG/context preparation.
3. RAG evidence gate can return directly before free LLM fallback.
4. Non-gated paths delegate to the proven legacy `run_agent_loop()`.

## Router Contract

Priority is part of the contract. Later graph edges must keep this order. RAG retrieval is also a context side-channel: messages that match local study-material keywords may retrieve RAG context before the final route runs, but only `should_gate_rag_answer=true` routes are allowed to stop as `rag_insufficient`.

1. `no_web`: current public/news/realtime requests. Next step: return the no-web text and `done`; do not call RAG, tools, or ordinary LLM.
2. `rag_qa`: local knowledge-answer candidate with sufficient or not-yet-retrieved evidence. Next step: retrieve local study material, inject runtime hints, answer only from local context.
3. `rag_insufficient`: local knowledge-answer candidate after retrieval but local evidence is insufficient. Next step: return the fixed insufficient-knowledge-base text and `done`; do not delegate to ordinary LLM.
4. `schedule_import`: upload or `file_id` based timetable import. Next step: parse schedule, ask for missing period/semester data if needed, ask for final import confirmation, then write.
5. `course_maintenance`: course rename, merge, delete, or correction. Next step: list/disambiguate courses, ask for confirmation, then update/delete.
6. `study_plan`: study/work plan generation. Next step: keep any RAG context retrieval as non-gating context, collect study/work context when needed, get free slots, generate candidate plan, ask for review, then write tasks only after confirmation.
7. `tool_workflow`: task, reminder, schedule, and other action workflows. Next step: keep any RAG context retrieval as non-gating context, then run the guarded tool loop.
8. `plain_chat`: no tool/RAG route. Next step: text-only LLM response within normal no-web constraints.

`decide_agent_route()` in `contracts.py` is the executable anchor for this priority. It is intentionally conservative and does not execute tools or call a model.

## State Schema

A LangGraph-native state must include at least:

- `route`: selected `AgentRoute`.
- `should_retrieve`: whether the current message should retrieve local RAG context before the final route executes.
- `should_gate_rag_answer`: whether insufficient RAG evidence must stop the turn instead of delegating to the tool/plain loop.
- `retrieval_mode`: `local_rag_context` for the current RAG side-channel, otherwise `none`.
- `messages`: LLM-visible conversation and tool messages.
- `runtime_hints`: system hints such as RAG context.
- `rag_result`: retrieval result and evidence metadata.
- `pending_confirmation`: active `ask_user` request and data required to resume.
- `tool_history`: ordered tool names used for loop guardrails and stream mode decisions.
- `preflight_reference_texts`: user and confirmed question text used for reminder/context argument repair.
- `preflight_user_texts`: user-provided text used for tool intent and task preflight decisions.
- `error_count`: per-tool retry counts.
- `last_tool_result`: last raw result from `execute_tool`.
- `last_free_slots_result`: free-slot result reused by study/work plan generation.
- `review_data`: candidate plan, parsed schedule, or course disambiguation payload shown to the user.
- `db_write_plan`: intended write operation awaiting confirmation.
- `stream_state`: message id, buffered deltas, and whether text deltas were emitted.
- `step`: persisted agent-log step counter.
- `initial_study_context_text`: early study-context intake answer that must feed later plan preflight.
- `graph_nodes`, `uses_langgraph`, `uses_langchain_tools`: runtime trace fields used by current LangGraph/RAG evidence events.

Runtime dependencies such as `user`, `session_id`, `db`, and `llm_client` may live in graph config/context instead of the serializable state, but every node that writes, logs, or calls a model needs access to them.

## Event Contract

Agent events are JSON objects sent through the WebSocket after the `connected` handshake.

- `text_delta`: `{type, message_id, delta}`. Only emitted for text-only streaming or replayed buffered deltas after a non-tool final response.
- `text`: `{type, message_id, content}`. Final assistant text for a turn or direct guard/gate response.
- `tool_call`: `{type, name, args}`. Must precede the matching `tool_result`, except `ask_user` emits a pause event instead of a normal tool result.
- `tool_result`: `{type, name, result}`. Emitted after non-`ask_user` tool execution.
- `ask_user`: `{type, question, ask_type, options?, data?}`. Pauses the generator and resumes with the submitted answer.
- `result`: `{type, message_id, content, tone?, eyebrow?, title?, chips?, data?}`. Structured assistant result used by review override and rich result surfaces.
- `done`: `{type}`. Exactly one terminal success event after text/tool workflow completion.
- `error`: `{type, message}`. User-visible runtime or guardrail error. Agent-generator terminal errors should be followed by `done`; WebSocket-wrapper exceptions are currently standalone `error` events.

Allowed direct guard/gate sequences:

- no-web: `text -> done`.
- RAG insufficient: `tool_call(rag_retrieve_study_materials) -> tool_result -> text -> done`.
- RAG hit: `tool_call(rag_retrieve_study_materials) -> tool_result -> inner loop events -> done`.

## Confirmation Contract

Database writes and scheduler side effects require code-level confirmation as the migration target. Prompt instructions alone are not sufficient.

Tools that must be behind `ask_user` before their write effect:

- Course writes: `add_course`, `update_course`, `delete_course`, `bulk_import_courses`.
- Task writes: `create_task`, `update_task`, `complete_task`.
- Reminder writes: `set_reminder`.
- Schedule import metadata writes: `save_period_times`.
- Memory writes: `save_memory`, `delete_memory`.

Plan generators `create_study_plan` and `create_work_plan` create candidate task data only. The generated tasks must go through a review `ask_user` before any `create_task` calls. A cancel response must return a short text response plus `done` and must not write.

Current legacy caveat: `execute_tool` is a direct dispatcher and write handlers can commit if called directly. Existing safety comes from local shortcuts, prompt/tool contracts, preflight, and regression tests, not from a central confirmation ticket. The LangGraph-native migration must close this by requiring `pending_confirmation` and `db_write_plan` state before any write tool node can execute.

## Tool Boundary

The graph-native tool node must preserve the current boundary:

1. `check_unknown_tool`.
2. `check_consecutive_ask_user`.
3. `check_max_retries`.
4. `task_tool_preflight_error`.
5. Context preflight for study/work plans.
6. `tool_schema_preflight_error`.
7. `apply_tool_preflight` for confirmed reminder slots.
8. `execute_tool`.
9. `tool_result` event for non-`ask_user` tools.
10. Persist compressed tool summary when applicable.
11. Persist agent log step.
12. Append tool message for the model.
13. Update `tool_history` and `error_count`.

## Streaming Strategy

These modes must be preserved:

- `text_only_stream`: no tool intent. Forward `content_delta` as `text_delta`, then emit final `text` and `done`.
- `tool_call_preamble_buffer`: tool-capable stream. Buffer model text while waiting for the final response; if the response contains tool calls, do not emit the preamble as user-visible text.
- `rag_retrieve_then_inner_stream`: LangGraph wrapper emits RAG tool events, then delegates to the inner loop stream.
- `rag_insufficient_text_done`: after RAG retrieval, emit fixed insufficient-evidence text and stop.
- `no_web_text_done`: skip retrieval/model/tool execution and emit the no-web text directly.
- `structured_result`: emit `result` for structured review/write summaries, then `done`.

## Golden E2E Matrix

These scenarios must stay green during a full LangGraph migration:

- RAG hit: local study-material question retrieves evidence and answers from local context.
- RAG insufficient: local knowledge-answer candidate with weak evidence does not call ordinary LLM.
- no-web: current public event/news question is blocked before RAG/LLM.
- create task confirmed: `ask_user` confirmation precedes `create_task` DB write.
- study plan confirmed write: candidate plan is reviewed before generated tasks are persisted.
- schedule import confirmed: parsed timetable is reviewed before `bulk_import_courses`.
- reminder set: reminder side effects follow confirmation and emit tool result.
- ask_user multiturn: generator pauses and resumes with the user's answer.
- tool failure recovery: tool errors increment retry state and remain under guardrails.
- plain chat streaming: non-tool chat emits `text_delta` before final `text`.
- tool preamble buffering: pre-tool prose is not emitted when a tool call is returned.
- course maintenance confirmed: rename/delete/merge asks for confirmation before write.
- empty schedule parse: no recognized courses returns `text -> done` and does not show a confirmation card.

`GOLDEN_E2E_MATRIX` in `contracts.py` mirrors this list for tests.
