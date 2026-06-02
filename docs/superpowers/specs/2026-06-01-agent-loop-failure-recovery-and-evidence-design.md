# Agent Loop Failure Recovery and Evidence 设计

## 状态

Accepted. 本轮承接 Plan 11，继续做剩余的 Agent Loop 稳定性收口：Plan B 是 provider/network 失败的用户可见恢复，Plan C 是连续多轮任务/提醒操作的 evidence 对比。

## 背景

Plan 10 已有 live E2E harness，但普通沙箱内会因为 provider 网络访问失败退化成通用“聊天暂时不可用”。这能说明连接失败，却不能给用户一个可操作、可区分的恢复反馈。

Plan 10 的 E2E 也只覆盖“创建一次”和“修改一次”。真实自用里更容易出问题的是连续多轮修改同一个任务：同一个 task 不能被重复创建，旧 reminder 不能残留，新的 `advance_minutes` 和 `remind_at` 要随每次修改保持一致。

## 目标

1. provider/network 失败时返回明确、可恢复的错误事件，而不是只给通用聊天失败。
2. 保留普通未知异常的通用错误，避免把所有后端错误误报为 provider 问题。
3. E2E harness 增加连续多轮任务/提醒修改场景，并输出每一轮 DB snapshot 作为 evidence。
4. 连续修改场景验证同一个 task 被复用、每轮只有一条关联 reminder、旧提醒时间不会残留。

## 非目标

1. 不做 provider 自动切换或重试队列。
2. 不改变 LLM provider 配置。
3. 不把 live E2E 混入默认 `npm run e2e`。
4. 不扩新业务能力，不引入 RAG。

## 方案

### Plan B: provider/network 可见恢复

在 WebSocket chat router 中把 agent loop 抛出的异常分类：

- OpenAI-compatible provider 连接失败、超时、HTTP/network 失败、`WinError 5` 等归为 `llm_provider_unavailable`。
- 返回错误事件：
  - `type: "error"`
  - `code: "llm_provider_unavailable"`
  - `recoverable: true`
  - `message: "模型服务暂时连接不上，刚才的操作还没有执行。请稍后重试，或检查当前网络/模型服务配置。"`
- 其他未知异常仍返回原通用文案。

前端 store 兼容 `code/recoverable` 字段，不改变现有 UI 结构；当前页面已经显示 `message`，所以用户可以直接看到更具体的恢复提示。

### Plan C: 连续多轮 evidence 对比

在 `frontend/e2e-agent/agent-loop.spec.ts` 增加新用例：

1. 通过真实 UI 注册登录。
2. 用 `/api/tasks/` 预置一个任务和 30 分钟提醒。
3. 第一轮让 Agent 把任务改到新日期/时间，提前 15 分钟提醒。
4. 第二轮让 Agent 再把同一个任务改到另一个日期/时间，并取消提醒或改成准点提醒。
5. 每轮等待 DB invariant 成立，记录 snapshot。
6. 写出 evidence JSON，包含 `snapshots`、WebSocket 事件、最终 DB 状态和断言摘要。

## 验收标准

1. WebSocket provider/network 失败测试能证明返回专用错误 code 和可恢复文案。
2. 普通 agent loop 异常仍返回通用错误。
3. Agent Loop E2E 文件包含连续多轮任务/提醒修改场景。
4. 该场景的 DB invariant 检查同一个 task、无旧 reminder 残留、最终 reminder 状态正确。
5. 后端定向测试通过；前端相关 store/type 或 E2E 静态检查通过。

## 实施补充

连续多轮 live E2E 首次运行时暴露一个真实对齐问题：模型认为系统没有删除提醒工具。执行器和 preflight 已支持用 `update_task.reminder_advance_minutes=null` 删除已有普通任务提醒，但工具描述和 Agent 规则没有把这个能力暴露给模型。最终实现把取消提醒规则补到 `update_task` 工具契约、`Agent.md`、动态 task 规则和 task routing hint，并用 schema/rule 测试锁住。
