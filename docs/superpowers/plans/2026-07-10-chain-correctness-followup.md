# Student Planner 提交级端到端链路收口 Follow-up

目标：在现有未提交改动基础上，按“路由 → trace → 确认参数 → 批量事务 → RAG 来源”顺序，证明真实运行事件、确认计划、数据库事实和前端来源展示一致。

约束：不修改 schema、RAG corpus、部署/认证/OCR/scheduler，不恢复 legacy runtime，不删除现有运行产物，不自动 commit/push/merge/reset。

## 链路一：课程问答路由

- [x] 为两条课程问句和两条实时公共信息问句补充 `decide_hard_agent_route`、hybrid router、`prepare_langgraph_state` 三层失败回归。
- [x] 统一实时信息 hard guard，课程知识问答优先进入本地 RAG，不被宽泛 marker 抢先判成 `NO_WEB`；实时新闻/汇率仍进入 `NO_WEB`。
- [x] 定向测试通过后更新本计划和 `progress.md`。

## 链路二：真实 graph trace

- [x] 先补 task cancel、用户拒绝、票据失效、tool error、rollback 与成功创建的事件/数据库失败回归。
- [x] 让 `confirmed_write` 只由成功确认且提交后的真实结果产生；移除按工具名猜测未来节点的逻辑，并校正 ask_user/plan 前置节点。
- [x] 更新 `scripts/langgraph_ws_smoke.py` 的强断言并通过定向测试与 smoke 后更新交接。

## 链路三：fail-closed 确认参数

- [x] 补结构化计划、深冻结参数、稳定 digest、confirmation_id/tool/args 精确绑定，以及 planned_args 为空、嵌套修改、digest 不一致、确认 A 执行 B、普通 review 追问的失败回归。
- [x] 为全部指定写工具确认路径补齐或证明可达；拒绝无可验证计划的通用 ask_user 写入。
- [x] 移除通用 `allow_derived_reschedule` 绕过；重排必须遵守新的确认计划或完整批次规则。
- [x] 定向测试通过后更新本计划和 `progress.md`。

## 链路四：批量事务事实一致

- [x] 补 study/work、批量任务、课程混合 update/delete 的整批 preflight、rollback、计数和最终回复失败回归。
- [x] 冲突时先形成完整重排批次，再一次性提交；无法形成完整批次则整体不写入。
- [x] 工作流级测试通过后更新本计划和 `progress.md`。

## 链路五：RAG 来源稳定显示

- [x] 补 `classifyAssistantResult` 命中结果卡时 RAG 来源仍显示的前端回归，调整渲染结构使 grounding 不依赖结果卡互斥分支。
- [x] 增加后端 rag_qa 事件到 chatStore/ChatPage 的真实 metadata 契约测试或 Playwright 场景。
- [x] 通过后端矩阵、前端测试/typecheck/build、WS smoke 和至少一次真实 WS/E2E 后更新本计划和 `progress.md`。

## 暂停条件

- 需要 schema migration、破坏 WS 兼容性、真实凭证/付费服务、恢复 legacy runtime、删除/覆盖不明归属文件时暂停。
- 同一链路经过三轮新证据驱动尝试仍失败时暂停并记录命令、事件、DB 状态和最小待决策问题。

## 2026-07-11 审查修复

- [x] 将 `planned_operations` 写入真实 `ask_user` schema/prompt，并把写授权改为严格确认值。
- [x] 统一 route-owned `confirmed_write` 的 committed 判定，移除批量 rollback 后逐条重放。
- [x] 将 reminder schedule/cancel 延后到数据库 commit 之后，并区分 `write_status/effect_status`。
- [x] 让 RAG 来源引用真实 `evidence_hits`，补课程语境 NO_WEB 豁免和 WS 字段类型校验。
- [x] 完成后端矩阵、前端测试/typecheck/build、WS smoke 和最终交接。
