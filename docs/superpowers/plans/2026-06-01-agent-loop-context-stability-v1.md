# Plan 11: Agent Loop Context Stability V1

> 当前计划接替 Plan 10 的 live E2E Harness，目标是补齐长上下文和动态上下文注入边界，让 Agent Loop 在真实持续会话里更稳定。

## Goal

把 Agent Loop 的长历史压缩、上下文注入优先级和记忆参考边界做成代码与测试都能验证的 V1。

## Files

- Create: `docs/superpowers/specs/2026-06-01-agent-loop-context-stability-v1-design.md`
- Create: `docs/superpowers/plans/2026-06-01-agent-loop-context-stability-v1.md`
- Modify: `student-planner/app/agent/loop.py`
- Modify: `student-planner/app/agent/context.py`
- Modify: `student-planner/tests/test_agent_loop.py`
- Modify: `student-planner/tests/test_context.py`
- Modify: `student-planner/tests/test_context_loading.py`
- Modify: `progress.md`
- Modify: `bugs.md` if a new confirmed issue appears

## Task 1: 固定设计和计划边界

- [x] Step 1: 写入 Context Stability V1 设计 spec。
- [x] Step 2: 写入本执行 plan，并把范围限制在长历史压缩和上下文注入边界。
- [x] Step 3: 更新 `progress.md`，说明当前活跃计划切到 Plan 11。

## Task 2: 接入长历史压缩

- [x] Step 1: 在 `run_agent_loop` 初始消息构造阶段压缩持久化历史。
- [x] Step 2: 确保当前用户消息、routing hints 和本轮 in-flight tool 链不进入历史摘要。
- [x] Step 3: 补 Agent Loop 回归，证明 LLM 收到摘要和当前用户消息。

## Task 3: 收紧动态上下文边界

- [x] Step 1: 删除动态上下文里的乱码重复字段。
- [x] Step 2: 增加上下文使用规则，明确记忆、摘要和数据库上下文不能覆盖系统/工具规则。
- [x] Step 3: 更新上下文测试，覆盖边界文案和乱码清理。

## Task 4: 验证和交接

- [x] Step 1: 运行后端定向回归。
- [x] Step 2: 更新 `progress.md` 的完成记录、下一步和验证基线。
- [x] Step 3: 若发现新环境坑或延期项，更新 `bugs.md`；否则保持不变。

## Verification

- `C:\Users\Chen\anaconda3\python.exe -m pytest -q tests\test_context.py tests\test_context_loading.py tests\test_conversation_compression.py tests\test_loop_compression.py tests\test_agent_loop.py`：`24 passed, 1 warning`；warning 为既有 `.pytest_cache` 写入权限。
- `C:\Users\Chen\anaconda3\python.exe -m pytest -q tests\test_agent_loop_task_creation.py tests\test_tool_preflight.py`：`20 passed, 1 warning`；warning 为既有 `.pytest_cache` 写入权限。
- `git diff --check -- progress.md docs\superpowers\specs\2026-06-01-agent-loop-context-stability-v1-design.md docs\superpowers\plans\2026-06-01-agent-loop-context-stability-v1.md student-planner\app\agent\loop.py student-planner\app\agent\context.py student-planner\tests\test_agent_loop.py student-planner\tests\test_context.py student-planner\tests\test_context_loading.py`：通过；仅有 Windows line-ending 提示。

## Notes

- 本计划不引入 RAG。当前项目的课程、任务、提醒仍优先走结构化数据库查询和 Agent 工具调用。
- 记忆在本计划中只是动态上下文的一部分，不做新增提取策略或 embedding 检索。
