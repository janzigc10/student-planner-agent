# Plan 15: Course Maintenance Agent Loop V1

> 本计划补齐课表真值维护：课程纠错、合并、删除。目标是让 OCR 或导入后的错误课程能通过 Agent 可确认地修正。

## Goal

让 Agent 能在不重新上传课表的情况下，先查看当前课程，再确认并落库课程改名、重复合并和错误删除。

## Files

- Create: `docs/superpowers/specs/2026-06-04-course-maintenance-agent-loop-v1-design.md`
- Create: `docs/superpowers/plans/2026-06-04-course-maintenance-agent-loop-v1.md`
- Modify: `student-planner/app/agent/loop.py`
- Modify: `student-planner/Agent.md`
- Modify: `student-planner/app/agent/prompt.py`
- Modify: `student-planner/frontend/e2e-agent/agent-loop.spec.ts`
- Modify: `student-planner/scripts/agent_loop_e2e_db.py`
- Modify: `student-planner/tests/test_agent_loop.py`
- Modify: `progress.md`
- Modify: `bugs.md` only if a new confirmed issue appears

## Task 1: 固定设计和执行边界

- [x] Step 1: 读取 `progress.md`、`bugs.md`、现有课程工具、Agent loop 和测试。
- [x] Step 2: 写入本设计 spec。
- [x] Step 3: 写入本执行 plan。
- [x] Step 4: 更新 `progress.md`，说明当前活跃计划切到 Plan 15。

## Task 2: 实现课程维护 shortcut

- [x] Step 1: 扩展课程维护请求识别，覆盖改名、删除、合并。
- [x] Step 2: 增加改名和删除 plan 构造，复用现有合并 plan。
- [x] Step 3: review 确认后确定性执行 `update_course` / `delete_course`。
- [x] Step 4: 找不到目标或多目标歧义时明确提示，不落库。

## Task 3: 更新 Agent 规则

- [x] Step 1: 更新 `Agent.md`，说明课程维护闭环和边界。
- [x] Step 2: 更新 `prompt.py` 的任务补充规则，强调不要重新要求上传课表。

## Task 4: 补后端回归

- [x] Step 1: 覆盖课程改名 shortcut。
- [x] Step 2: 覆盖课程删除 shortcut。
- [x] Step 3: 保留并扩展课程合并 shortcut 回归。
- [x] Step 4: 覆盖未匹配目标不落库。

## Task 5: 补 live E2E

- [x] Step 1: 增加课程维护 E2E seed helper。
- [x] Step 2: 新增一条真实浏览器课程维护场景。
- [x] Step 3: evidence JSON 记录工具序列、改名前后课程和最终 DB 状态。

## Task 6: 验证和交接

- [x] Step 1: 运行后端课程/Agent 定向回归。
- [x] Step 2: 运行前端 typecheck。
- [x] Step 3: 沙箱外运行新增 Agent Loop live E2E。
- [x] Step 4: 更新 `progress.md`。
- [x] Step 5: commit 并 push。

## Verification

- `C:\Users\Chen\anaconda3\python.exe -m pytest -q tests/test_agent_loop.py::test_course_merge_shortcut_collapses_duplicate_courses_without_llm tests/test_agent_loop.py::test_course_merge_shortcut_preserves_distinct_week_patterns tests/test_agent_loop.py::test_course_rename_shortcut_updates_existing_course_without_llm tests/test_agent_loop.py::test_course_delete_shortcut_deletes_unique_course_after_confirmation tests/test_agent_loop.py::test_course_delete_shortcut_does_not_delete_ambiguous_same_name_courses tests/test_agent_loop.py::test_course_maintenance_shortcut_does_not_write_when_target_missing tests/test_tool_executor.py::test_update_course_changes_name` -> `7 passed, 1 warning`
- `C:\Users\Chen\anaconda3\python.exe -m pytest -q tests/test_agent_loop.py tests/test_agent_loop_task_creation.py tests/test_tool_preflight.py tests/test_tool_executor.py tests/test_tools_schema.py` -> `66 passed, 1 warning`
- `npm.cmd run typecheck` -> PASS
- `npm.cmd run e2e:agent-loop -- --grep "renames an imported course" --reporter=list --global-timeout=420000` -> `1 passed`
