# Student Planner Architecture Boundary Hardening

## Goal

以契约优先、渐进改造方式消除 Goal 文件列出的 7 项合并阻断问题，保持 LangGraph 为聊天主运行时和现有产品能力；为确认授权/事务、意图路由/真实 trace、RAG 运行时/索引/前端来源契约补齐可失败回归、最小实现和运行证据。

## Scope

- 允许修改：`student-planner/app/agent`、`student-planner/app/routers/chat.py`、相关前端聊天事件/来源组件、对应测试、`scripts/langgraph_ws_smoke.py`、`.gitignore`、本计划、`progress.md`、`bugs.md`。
- 禁止修改：数据库 schema、`data/rag/corpus` 来源内容、认证/OCR/scheduler/无关业务和页面。
- 保留现有 `.idea`、SQLite、Chroma、E2E、日志和临时运行产物；不自动 commit、push、merge、reset 或删除不明归属文件。

## Execution

### Step 1: Baseline and contracts

- [x] 记录分支、HEAD、工作树、已有运行产物和定向测试基线。
- [x] 阅读确认、路由、LangGraph、RAG、WebSocket 和前端来源的现有实现/测试，列出每项缺口及最小写入边界。
- [x] 只有确认没有覆盖本 Goal 的活跃计划后才创建本计划；完成后更新 `progress.md`。

### Step 2: Confirmation and transactional writes

- [x] 先补票据精确绑定、参数/工具校验、一次性消费和所有确认工具可达性的失败回归。
- [x] 实现最小 DBWritePlan/nonce/有效状态校验，确认前不产生 `confirmed_write`，重放和参数不匹配拒绝。
- [x] 为复习/作业/批量任务/课程合并补齐 preflight 后单事务写入、失败整体回滚和幂等重试；未修改数据库 schema。
- [x] 通过定向测试后更新本计划和 `progress.md`，否则停留在本 step。

### Step 3: Intent routing and real LangGraph trace

- [x] 补首次意图只分类一次、RAG 后不改 route、课程资料问答不误入 `NO_WEB`、实时新闻仍进入 `NO_WEB` 的回归。
- [x] 让 `graph_nodes` 只来源于实际状态转移；确认前、确认后和数据库结果保持互相对应，并覆盖后续分类/检索失败不改 action route。
- [x] 通过定向测试后更新本计划和 `progress.md`，否则停留在本 step。

### Step 4: RAG runtime, portable index, and frontend grounding

- [x] 补异步事件循环不被完整 RAG/Embedding/重试/冷构建阻塞的回归，增加单次构建锁和受控线程边界。
- [x] 用相对 source、内容哈希、embedding/chunk 配置和 index version 生成可移植 key/ID，固定兼容 Chroma 版本并验证跨目录、mtime 改变和可重建行为。
- [x] 对 WebSocket 和 tokenizer 增加 UTF-8 字节/字符上限及稳定拒绝事件；真实 `rag_qa` 携带 grounding/answer_kind，前端来源可见。
- [x] 通过定向测试后更新本计划和 `progress.md`，否则停留在本 step。

### Step 5: Full verification and handoff

- [x] 串行运行 Goal 文件指定的后端矩阵、占位凭证下的 `test_intent_router.py`、前端测试/typecheck/build、WS smoke 和至少一次真实 WebSocket/E2E。
- [x] 保存 task/study/work/course/RAG/NO_WEB 事件序列、graph_nodes、确认前后 DB 不变量及剩余风险。
- [x] 运行 `git diff --check`、`git status --short`，确认只留下本 Goal 预期源码/测试/文档改动且无运行产物进入改动。
- [x] 完成 `progress.md`/`bugs.md` 交接；不自动提交或推送。

## Pause conditions

- 需要破坏性数据库操作、schema migration、真实凭证/付费外部服务、破坏 WebSocket 兼容性、恢复 legacy runtime、删除不明归属文件或覆盖用户改动时暂停。
- 同一阻塞条件在 3 轮基于新证据的尝试后仍无法解决时暂停并报告事实、命令和最小待决策问题。
