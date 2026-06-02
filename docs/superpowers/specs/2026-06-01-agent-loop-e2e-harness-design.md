# Agent Loop E2E Harness 设计

## 状态

Accepted. 用户明确选择 E2E 方向，目标是验证真实 Agent Loop 闭环，而不是继续做轻量 smoke。

## 背景

Plan 9 已把 Agent Loop 的后端执行边界补强：课程有效周、任务/提醒一体化、工具 preflight、缺参恢复和多轮修改回归都有后端测试覆盖。下一阶段的风险不再是“有没有某个函数”，而是真实浏览器会话中用户输入、确认卡、WebSocket、LLM 工具调用、数据库结果和最终回复是否稳定一致。

现有前端 Playwright 只覆盖登录入口，不能证明 Agent Loop 闭环正确。后端 agent-loop 测试可以精确覆盖工具行为，但不经过浏览器、登录态、WebSocket 和前端确认交互。

## 目标

1. 新增专用 Agent Loop E2E 入口，不影响现有快速 `npm run e2e`。
2. 用真实浏览器走 `/chat`，连接真实本地后端和真实 SQLite E2E 数据库。
3. 第一批只覆盖 3 条黄金路径：
   - 创建任务 + 提醒。
   - 修改已有任务时间 + 修改提醒提前分钟。
   - 缺必填参数后追问恢复。
4. 每条 E2E 必须断言数据库 invariant，而不是只看前端回复。
5. 每条 E2E 输出 evidence JSON：用户输入、WebSocket 事件、DB snapshot、截图路径和断言摘要。

## 非目标

1. 不把所有 Agent 能力一次性 E2E 化。
2. 不把 E2E 混入默认快速前端 E2E。
3. 不为了测试引入新的生产业务协议。
4. 不用 E2E 替代后端定向测试；E2E 只验证少数关键闭环。

## 方案

### Playwright 专用配置

新增 `student-planner/frontend/playwright.agent-loop.config.ts`：

- 独立 `testDir`，只运行 Agent Loop E2E。
- 启动后端 `127.0.0.1:8011`。
- 启动前端 `127.0.0.1:5178`，并通过 `STUDENT_PLANNER_BACKEND_ORIGIN` 指向 E2E 后端。
- 使用独立数据库 `student-planner/agent_loop_e2e.db`。
- 单 worker 串行执行，避免 LLM 和 SQLite 状态互相干扰。

### 后端启动脚本

新增 `student-planner/scripts/start_agent_e2e_backend.py`：

- 先运行 Alembic migration。
- 再启动 `app.main:app`。
- 仅用于 E2E webServer，不改变生产启动方式。

### 数据库 evidence helper

新增 `student-planner/scripts/agent_loop_e2e_db.py`：

- 根据 username 清理 E2E 用户数据。
- 读取 DB snapshot：user、tasks、reminders、agent logs、conversation snippets。
- 输出 JSON 给 Playwright 断言和 evidence。

### E2E 测试

新增 `student-planner/frontend/e2e-agent/agent-loop.spec.ts`：

- 通过注册/登录 UI 建立真实浏览器会话。
- 注入 WebSocket recorder，捕获 client/server 事件。
- 发送真实自然语言到 Chat。
- 如出现确认卡，则点击确认；缺参数场景需要填补充答案。
- 轮询 DB snapshot 直到 invariant 成立。
- 保存 screenshot 和 evidence JSON 到 `output/playwright/`。

## 验收标准

1. `npm.cmd run e2e:agent-loop` 能启动前后端、进入 `/chat` 并运行专用 E2E。
2. 创建任务路径断言：
   - 只有 1 个目标 task。
   - task 日期/时间正确。
   - 只有 1 个 task reminder。
   - reminder `advance_minutes` 与 `remind_at` 正确。
3. 修改任务路径断言：
   - 不创建重复 task。
   - 旧 reminder 被更新，无旧时间残留。
4. 缺参恢复路径断言：
   - 出现追问或确认衔接。
   - 用户补充后落库正确。
5. 每条路径都有 evidence JSON。

## 风险

1. 真实 LLM E2E 会慢且有概率波动；因此只保留少数黄金路径，并输出强 evidence。
2. 若 provider 或网络不可用，E2E 会失败；这是 live E2E 的预期成本，不把它混入默认快速测试。
3. E2E 不能替代后端 preflight 单测，失败后仍应回到更窄的测试定位根因。
