# Plan 10: Agent Loop E2E Harness

> 当前计划接替 Plan 9 的后端闭环 hardening，目标是把真实浏览器里的 Agent Loop 关键路径固化成少量但严格的 E2E。

## Goal

建立可重复运行的 Agent Loop E2E Harness：真实浏览器、真实本地后端、真实 E2E SQLite 数据库、数据库 invariant 断言和 evidence JSON。

## Files

- Create: `docs/superpowers/specs/2026-06-01-agent-loop-e2e-harness-design.md`
- Create: `docs/superpowers/plans/2026-06-01-agent-loop-e2e-harness.md`
- Create: `student-planner/scripts/start_agent_e2e_backend.py`
- Create: `student-planner/scripts/agent_loop_e2e_db.py`
- Create: `student-planner/frontend/playwright.agent-loop.config.ts`
- Create: `student-planner/frontend/e2e-agent/agent-loop.spec.ts`
- Modify: `student-planner/frontend/package.json`
- Modify: `.gitignore`
- Modify: `progress.md`
- Modify: `bugs.md`

## Task 1: 固定 E2E 设计和计划边界

- [x] Step 1: 写入 Agent Loop E2E Harness 设计 spec。
- [x] Step 2: 写入本执行 plan，并把范围限制在 3 条黄金路径。
- [x] Step 3: 更新 `progress.md`，说明当前活跃计划切到 Plan 10。

## Task 2: 搭建 E2E 基础设施

- [x] Step 1: 新增后端 E2E 启动脚本，负责 migrate + uvicorn。
- [x] Step 2: 新增 DB helper，支持 cleanup 和 snapshot JSON。
- [x] Step 3: 新增专用 Playwright config，串行启动 E2E 前后端。
- [x] Step 4: 新增 `npm run e2e:agent-loop`，不影响默认 `npm run e2e`。

## Task 3: 实现第一批 Agent Loop E2E

- [x] Step 1: 创建任务 + 提醒 E2E。
- [x] Step 2: 修改已有任务 + 修改提醒提前分钟 E2E。
- [x] Step 3: 缺参数追问恢复 E2E。
- [x] Step 4: 每条路径输出 screenshot 和 evidence JSON。

## Task 4: 验证和交接

- [x] Step 1: 运行 Agent Loop E2E，记录通过或失败证据。
- [x] Step 2: 如果 live provider / 网络导致失败，把失败类型记录到 `bugs.md`，但保留 harness。
- [x] Step 3: 跑相关快速回归，确保默认前端 E2E 未被新 harness 扩大。
- [x] Step 4: 更新 `progress.md`，记录可运行命令、结果和下一步。

## Verification

- `npm.cmd run e2e:agent-loop -- --reporter=list --global-timeout=420000`（沙箱外 live provider）：`3 passed (1.5m)`。
- `npm.cmd run e2e:agent-loop -- --reporter=list --global-timeout=420000`（普通沙箱）：失败，前两条路径超时，后端日志出现 `openai.APIConnectionError` / `PermissionError: [WinError 5] 拒绝访问。`，属于 live provider 网络环境问题。
- `npm.cmd run e2e -- --list`：仍只列出默认 `app.spec.ts` 1 条用例，Agent Loop E2E 保持独立 config。
- `C:\Users\Chen\anaconda3\python.exe -m pytest -q tests\test_agent_loop_task_creation.py tests\test_agent_loop.py tests\test_tool_preflight.py`：`33 passed, 1 warning`；warning 为 `.pytest_cache` 写入 `WinError 5`。

## Notes

- 本计划是 live E2E，不 mock LLM。它可以暴露 provider / 网络 / 模型输出波动，这属于该层测试的价值。
- 如果后续需要 CI 稳定版，再单独设计 deterministic fixture；不要把 live E2E 降级成 mock smoke。
