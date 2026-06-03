# Plan 13: Study Plan Decomposition Quality

> 本计划优化复习计划任务拆解质量：在生成计划前补齐学习上下文，让计划不再只按空闲时间模板化平均铺任务。

## Goal

让“下周四有大学英语3考试，帮我做复习计划”这类请求从“能写入候选任务”升级为“先收集关键学习变量，再生成更个性化、可执行、可验证的复习任务”。

## Files

- Create: `docs/superpowers/specs/2026-06-02-study-plan-decomposition-quality-design.md`
- Create: `docs/superpowers/plans/2026-06-02-study-plan-decomposition-quality.md`
- Modify: `student-planner/Agent.md`
- Modify: `student-planner/app/agent/prompt.py`
- Modify: `student-planner/app/agent/tools.py`
- Modify: `student-planner/app/agent/tool_executor.py`
- Modify: `student-planner/app/agent/study_planner.py`
- Modify: `student-planner/app/agent/loop.py`
- Modify: `student-planner/tests/test_study_planner.py`
- Modify: `student-planner/tests/test_agent_loop_task_creation.py`
- Modify: `student-planner/tests/test_tools_schema.py`
- Modify: `student-planner/frontend/e2e-agent/agent-loop.spec.ts`
- Modify: `progress.md`
- Modify: `bugs.md` only if a new confirmed issue appears

## Task 1: 固定设计和执行边界

- [x] Step 1: 读取 `progress.md`、`bugs.md`、现有学习计划代码和 E2E。
- [x] Step 2: 写入本设计 spec。
- [x] Step 3: 写入本执行 plan。
- [x] Step 4: 更新 `progress.md`，说明当前活跃计划切到 Plan 13。

## Task 2: 实现学习计划 intake 和上下文透传

- [x] Step 1: 扩展 `create_study_plan` schema，加入 `study_context`。
- [x] Step 2: 扩展 `generate_study_plan` 和执行器，透传 `study_context`。
- [x] Step 3: 更新 `PLAN_PROMPT`、`Agent.md` 和动态 task 规则，要求先收集关键学习变量。
- [x] Step 4: 在 `run_agent_loop` 的 `create_study_plan` 执行前加入本地 intake guard。

## Task 3: 补后端回归

- [x] Step 1: 覆盖 `generate_study_plan` prompt 包含学习上下文。
- [x] Step 2: 覆盖缺少 `study_context` 时先 ask_user，不直接生成计划。
- [x] Step 3: 覆盖用户补充后 `create_study_plan` 收到结构化 context，确认后仍写入任务。
- [x] Step 4: 覆盖工具 schema 暴露新字段。

## Task 4: 补完整 live E2E

- [x] Step 1: 更新模糊请求 E2E，继续断言追问且不落库。
- [x] Step 2: 更新完整考试请求 E2E，要求先出现学习计划 intake。
- [x] Step 3: E2E 用户补充范围/薄弱点/每日上限后确认写入。
- [x] Step 4: evidence JSON 记录 context hints 和最终任务质量断言。

## Task 5: 验证和交接

- [x] Step 1: 运行后端学习计划/Agent/schema 定向回归。
- [x] Step 2: 运行前端 typecheck。
- [x] Step 3: 沙箱外运行 study plan live E2E。
- [x] Step 4: 更新 `progress.md` 和必要的 `bugs.md`。

## Verification

- `C:\Users\Chen\anaconda3\python.exe -m pytest -q tests/test_study_planner.py tests/test_agent_loop_task_creation.py tests/test_tools_schema.py` -> `20 passed, 1 warning`，warning 为既有 `.pytest_cache` 权限。
- `C:\Users\Chen\anaconda3\python.exe -m pytest -q tests/test_study_planner.py tests/test_agent_loop_task_creation.py tests/test_tool_preflight.py tests/test_tool_executor.py tests/test_tools_schema.py` -> `40 passed, 1 warning`，warning 为既有 `.pytest_cache` 权限。
- `npm.cmd run typecheck` -> PASS。
- `npm.cmd run e2e:agent-loop -- --grep "study plan" --reporter=list --global-timeout=420000`（沙箱外权限）-> `2 passed (1.2m)`。
