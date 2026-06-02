# Plan 9: Agent Execution Loop V1

> 当前计划接替 Plan 8 中暴露出的 Agent 执行闭环问题。执行时按 step 顺序推进；每完成一个 step，立即把对应 `- [ ]` 改为 `- [x]`。

## Goal

把 Student Planner Agent 从“能说会做的 MVP”推进到“可验证执行闭环 V1”：课表真值一致、任务/提醒一致、确认后执行可追踪、工具结果结构化、核心回归测试覆盖。

## Files

- Create: `docs/superpowers/specs/2026-05-31-agent-execution-loop-v1-design.md`
- Create: `docs/superpowers/plans/2026-05-31-agent-execution-loop-v1.md`
- Modify: `student-planner/app/services/schedule_parser.py`
- Create: `student-planner/app/services/course_occurrence.py`
- Modify: `student-planner/app/agent/tool_executor.py`
- Modify: `student-planner/app/agent/tools.py`
- Modify: `student-planner/app/agent/prompt.py`
- Modify: targeted backend tests under `student-planner/tests/`
- Modify: `progress.md`
- Modify: `bugs.md`

## Task 1: 固定 V1 文档和执行边界

- [x] Step 1: 写入 Agent Execution Loop V1 设计 spec。
- [x] Step 2: 写入本执行 plan，并把 V1 范围限制在后端执行闭环和定向回归。
- [x] Step 3: 更新 `progress.md`，说明当前活跃计划切到 Plan 9。

## Task 2: 修课程有效周真值

- [x] Step 1: 补 schedule parser 测试，覆盖 `3,5,7,9,11,13,15,17([周])` 应归一为 odd。
- [x] Step 2: 新增课程有效周服务，统一判断课程是否出现在某个日期。
- [x] Step 3: 让空闲时间和课程提醒使用有效周服务。
- [x] Step 4: 跑 schedule/parser/calendar/reminder 定向后端测试。

## Task 3: 修 Agent 任务/提醒一体化工具

- [x] Step 1: 给 `create_task` 和 `update_task` 工具 schema 增加 `reminder_advance_minutes`。
- [x] Step 2: 工具执行层同步创建、更新、删除 task reminder。
- [x] Step 3: 工具结果返回结构化 task/reminder summary。
- [x] Step 4: 补工具层回归测试。

## Task 4: 修 Agent 多轮确认回归

- [x] Step 1: 补 Agent loop 测试，覆盖“确认后修改任务时间和提醒分钟”。
- [x] Step 2: 调整 prompt，要求优先用一体化 task 工具，避免任务和提醒分叉。
- [x] Step 3: 跑 Agent loop 定向测试。

## Task 5: 收尾验证和交接

- [x] Step 1: 跑本轮定向后端测试和后端全量测试。
- [x] Step 2: 如果时间允许，启动本地前后端做一次浏览器 smoke。
- [x] Step 3: 更新 `progress.md` 和 `bugs.md`，记录已修、仍待做、验证命令。

## Task 6: 修 E2E 暴露的提醒意图参数丢失

- [x] Step 1: 增加窄范围 task reminder preflight，检测用户明确表达的提醒提前分钟是否进入工具参数。
- [x] Step 2: 补回归测试，覆盖 LLM 漏传 `reminder_advance_minutes` 时执行前自动补齐。
- [x] Step 3: 跑定向后端测试和真实 smoke，确认任务时间与 reminder 同步更新。
- [x] Step 4: 更新 `progress.md` 和 `bugs.md`，记录修复结果与剩余风险。

## Task 7: Hardening Agent routing and tool preflight evals
- [x] Step 1: Extend `tool_preflight` from reminder-only correction to generic schema/required-slot validation.
- [x] Step 2: Cover explicit reminder cancellation and missing-required-tool-argument recovery in agent-loop regression tests.
- [x] Step 3: Run targeted and broader backend regressions.
- [x] Step 4: Update `progress.md` and `bugs.md` with the new execution-chain evidence and limits.

## Verification

- `C:\Users\Chen\anaconda3\python.exe -m pytest -q tests/test_tool_preflight.py tests/test_agent_loop_task_creation.py`
  - Result: `17 passed`
- `C:\Users\Chen\anaconda3\python.exe -m pytest -q tests/test_schedule_parser.py tests/test_course_occurrence.py tests/test_tool_executor.py tests/test_set_reminder_scheduling.py tests/test_auto_reminder.py tests/test_bulk_import.py tests/test_agent_loop_task_creation.py tests/test_tools_schema.py tests/test_tool_preflight.py`
  - Result: `57 passed`
- `C:\Users\Chen\anaconda3\python.exe -m pytest -q`
  - Result: `229 passed`

## Notes

- Task 7 没有重跑浏览器 smoke，因为改动集中在后端 Agent 工具执行前校验；Task 6 的真实 `5174 -> 8001` smoke 已覆盖本次修复前暴露的主要用户路径。
- pytest 仍有 APScheduler coroutine warning 和一次 `.pytest_cache` permission warning，已记录到 `bugs.md`。
