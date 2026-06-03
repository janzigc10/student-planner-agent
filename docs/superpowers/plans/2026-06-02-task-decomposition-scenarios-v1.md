# Plan 14: Task Decomposition Scenarios V1

> 本计划扩展短中期任务拆解场景：作业/报告/大作业、多考试复习、计划调整、时间不足/冲突处理。长期目标拆解明确不在本轮范围内。

## Goal

让 Agent 的任务拆解从“单一考试复习计划”扩到学生近期高频任务，并保持可确认、可落库、可 E2E 验证。

## Files

- Create: `docs/superpowers/specs/2026-06-02-task-decomposition-scenarios-v1-design.md`
- Create: `docs/superpowers/plans/2026-06-02-task-decomposition-scenarios-v1.md`
- Create: `student-planner/app/agent/work_planner.py`
- Modify: `student-planner/Agent.md`
- Modify: `student-planner/app/agent/prompt.py`
- Modify: `student-planner/app/agent/tools.py`
- Modify: `student-planner/app/agent/tool_executor.py`
- Modify: `student-planner/app/agent/loop.py`
- Modify: `student-planner/frontend/e2e-agent/agent-loop.spec.ts`
- Modify: `student-planner/tests/test_agent_loop_task_creation.py`
- Modify: `student-planner/tests/test_study_planner.py`
- Modify: `student-planner/tests/test_tools_schema.py`
- Add or modify: `student-planner/tests/test_work_planner.py`
- Modify: `progress.md`
- Modify: `bugs.md` only if a new confirmed issue appears

## Task 1: 固定设计和执行边界

- [x] Step 1: 读取 `progress.md`、`bugs.md`、现有 Agent loop、工具、执行器、学习计划和 E2E。
- [x] Step 2: 写入本设计 spec。
- [x] Step 3: 写入本执行 plan。
- [x] Step 4: 更新 `progress.md`，说明当前活跃计划切到 Plan 14，且长期目标拆解不在范围内。

## Task 2: 实现 deadline 型作业计划工具

- [x] Step 1: 新增 `work_planner.py`，实现 `generate_work_plan`。
- [x] Step 2: 在 `tools.py` 暴露 `create_work_plan` schema。
- [x] Step 3: 在 `tool_executor.py` 接入 `create_work_plan`。
- [x] Step 4: 更新 `Agent.md` 和 `prompt.py`，说明作业/报告拆解规则。

## Task 3: 实现作业计划 shortcut 和通用确认写入

- [x] Step 1: 泛化确认写入候选任务函数，复习计划和作业计划共用。
- [x] Step 2: 增加作业/报告请求识别和上下文 intake。
- [x] Step 3: 作业计划 shortcut 调用 `get_free_slots -> create_work_plan -> review -> create_task`。
- [x] Step 4: 保留冲突失败统计，不能在部分失败时声称全部完成。

## Task 4: 实现计划调整 V1

- [x] Step 1: 增加“计划太满/每天最多 N”请求识别。
- [x] Step 2: 从未来 30 天 pending 任务中匹配计划关键词。
- [x] Step 3: review 后逐条 `update_task` 缩短单条任务时长。
- [x] Step 4: 无匹配任务或无法解析上限时返回明确提示，不乱改。

## Task 5: 补后端回归

- [x] Step 1: 覆盖 `generate_work_plan` prompt 包含 deadline、work context 和每日上限。
- [x] Step 2: 覆盖 `create_work_plan` executor。
- [x] Step 3: 覆盖作业计划 shortcut：先 intake，确认后写入。
- [x] Step 4: 覆盖计划调整 shortcut：确认后批量 update_task。
- [x] Step 5: 覆盖工具 schema 和 prompt 规则。

## Task 6: 补 live E2E

- [x] Step 1: 新增作业/报告计划 E2E，断言写入阶段任务。
- [x] Step 2: 新增多考试复习 E2E，断言至少两门考试任务写入。
- [x] Step 3: 新增计划调整 E2E，断言相关任务时长被缩到每日上限。
- [x] Step 4: evidence JSON 记录任务数量、工具序列、计划关键词和时长断言。

## Task 7: 验证和交接

- [x] Step 1: 运行后端定向回归。
- [x] Step 2: 运行前端 typecheck。
- [x] Step 3: 沙箱外运行 Agent Loop live E2E 新增场景。
- [x] Step 4: 更新 `progress.md` 和必要的 `bugs.md`。

## Verification

- `C:\Users\Chen\anaconda3\python.exe -m pytest -q tests/test_work_planner.py tests/test_study_planner.py tests/test_agent_loop_task_creation.py tests/test_tool_preflight.py tests/test_tool_executor.py tests/test_tools_schema.py` -> `50 passed, 1 warning`，warning 为既有 `.pytest_cache` 权限。
- `npm.cmd run typecheck` -> PASS。
- `npm.cmd run e2e:agent-loop -- --grep "assignment report|multi-exam|daily limit" --reporter=list --global-timeout=600000`（沙箱外权限）-> `3 passed (1.8m)`。
