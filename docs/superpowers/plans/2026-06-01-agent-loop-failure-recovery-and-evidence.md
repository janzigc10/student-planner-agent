# Plan 12: Agent Loop Failure Recovery and Evidence

> 本计划实现用户所说剩余 Plan B/C：provider/network 失败的用户可见恢复，以及连续多轮任务/提醒操作的 evidence 对比。

## Goal

让 Agent Loop 在 provider/network 失败时给出明确恢复反馈，并用 E2E evidence 覆盖连续多轮修改同一任务/提醒的稳定性。

## Files

- Create: `docs/superpowers/specs/2026-06-01-agent-loop-failure-recovery-and-evidence-design.md`
- Create: `docs/superpowers/plans/2026-06-01-agent-loop-failure-recovery-and-evidence.md`
- Modify: `student-planner/Agent.md`
- Modify: `student-planner/app/agent/loop.py`
- Modify: `student-planner/app/agent/prompt.py`
- Modify: `student-planner/app/agent/tool_preflight.py`
- Modify: `student-planner/app/agent/tools.py`
- Modify: `student-planner/app/routers/chat.py`
- Modify: `student-planner/tests/test_chat_ws.py`
- Modify: `student-planner/tests/test_tools_schema.py`
- Modify: `student-planner/frontend/src/stores/chatStore.ts`
- Modify: `student-planner/frontend/src/stores/chatStore.test.ts`
- Modify: `student-planner/frontend/e2e-agent/agent-loop.spec.ts`
- Modify: `progress.md`
- Modify: `bugs.md` if a new confirmed issue appears

## Task 1: 固定设计和计划边界

- [x] Step 1: 写入 failure recovery + evidence 设计 spec。
- [x] Step 2: 写入本执行 plan，并把范围限定为 Plan B/C。
- [x] Step 3: 更新 `progress.md`，说明当前活跃计划切到 Plan 12。

## Task 2: 实现 Plan B provider/network 可见恢复

- [x] Step 1: 在 Chat WebSocket router 中识别 provider/network 类异常。
- [x] Step 2: 返回带 `code` 和 `recoverable` 的用户可见错误事件。
- [x] Step 3: 保持普通未知异常走通用失败文案。
- [x] Step 4: 补 WebSocket 后端回归和前端 reducer 兼容测试。

## Task 3: 实现 Plan C 连续多轮 evidence 对比

- [x] Step 1: 扩展 Agent Loop E2E evidence writer，支持多阶段 snapshots。
- [x] Step 2: 新增连续两轮修改同一任务/提醒的 live E2E 场景。
- [x] Step 3: 断言同一个 task 被复用、每轮 reminder 正确、旧 reminder 不残留。
- [x] Step 4: 根据 live E2E 失败补齐 `update_task` 取消普通任务提醒的工具契约、Agent 规则和路由提示。

## Task 4: 验证和交接

- [x] Step 1: 运行后端 Chat/Agent 定向回归。
- [x] Step 2: 运行前端 store 测试和 E2E 列表/类型相关检查。
- [x] Step 3: 更新 `progress.md` 的完成记录、下一步和验证基线。
- [x] Step 4: 若发现新环境坑或延期项，更新 `bugs.md`；否则保持不变。

## Verification

- `C:\Users\Chen\anaconda3\python.exe -m pytest -q tests\test_chat_ws.py tests\test_agent_loop_task_creation.py tests\test_tool_preflight.py tests\test_tools_schema.py` -> `30 passed, 1 warning`，warning 为既有 `.pytest_cache` 权限。
- `npm.cmd test -- src/stores/chatStore.test.ts` -> `14 passed`。普通沙箱里 Vitest setup 绝对路径会失败，已在沙箱外权限下重跑通过。
- `npm.cmd run typecheck` -> PASS。
- `npm.cmd run e2e:agent-loop -- --list` -> 4 tests listed。
- `npm.cmd run e2e:agent-loop -- --reporter=list --global-timeout=600000`（沙箱外权限）-> `4 passed (3.0m)`。

## Notes

- Live E2E 仍依赖真实 provider；如果当前环境无法联网，只能验证 harness 结构和定向单元测试，live 通过结果仍以沙箱外运行作为准。
- 本计划不实现 provider 自动切换。
- 连续多轮场景首次 live 运行失败在“取消提醒”：模型曾回复没有删除提醒工具。根因不是执行器不支持，而是 `update_task.reminder_advance_minutes=null` 没有在工具契约和 Agent 规则里暴露。修复后 live E2E 4 条全部通过。
