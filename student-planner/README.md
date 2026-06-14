# Student Planner

Student Planner 是一个面向大学生的 AI 时间规划应用，核心目标是把“聊天式规划”变成真正能落到课表、任务和提醒上的实际动作。

## 核心能力

- 查看与管理课程表
- 通过聊天生成任务和复习计划
- 课表 Excel 导入
- 课表截图识别与确认导入
- 日历视图查看课程与任务
- 推送提醒与服务端定时调度
- 移动端 PWA 使用体验

## 目录结构

- [app](./app): FastAPI 后端、Agent、路由、模型和服务层
- [frontend](./frontend): React + TypeScript 前端
- [alembic](./alembic): 数据库迁移
- [tests](./tests): 后端自动化测试
- [scripts](./scripts): 辅助脚本，例如 VAPID key 生成、公开 RAG 资料导入和 RAG 质量评测

## 技术实现概览

### 后端

- FastAPI 提供认证、课程、任务、提醒、聊天、导入等接口
- SQLAlchemy Async + SQLite 负责数据持久化
- Alembic 管理 schema 演进
- APScheduler 负责 reminder 定时触发

### Agent

- 使用 OpenAI-compatible 接口完成对话与 tool calling
- 将课程、任务、提醒、导入等能力注册为可调用工具
- 通过确认卡与 guardrails 控制写入动作，避免“直接修改用户数据”

#### LangChain / LangGraph / RAG 运行时

期末作业版新增了可开关的 LangGraph 外层运行时，但没有重写原有稳定业务闭环：

- [app/agent/langgraph_loop.py](./app/agent/langgraph_loop.py): LangGraph `StateGraph`，节点为 `load_context -> retrieve_study_materials -> compose_runtime_hints`。
- [app/agent/rag.py](./app/agent/rag.py): 课程资料 RAG，加载 `data/rag` 下的 Markdown/TXT，使用 LangChain Document / splitter，当前 `chunk_size=520`、`chunk_overlap=150`；向量层支持阿里云百炼 DashScope OpenAI-compatible Embeddings，并按每批 10 条 chunk 调用，避免长文档触发百炼 batch 限制；默认使用 Chroma 持久化向量库，避免每次进程重启后重新 embed 全库；如果运行环境检测到 Chroma native upsert 不可用，会自动退到 SQLite 持久化文件；没有配置 Key 或网络异常时保留本地 hash fallback，便于测试。
- [app/agent/langchain_tools.py](./app/agent/langchain_tools.py): 将现有 `TOOL_DEFINITIONS` 转换为 LangChain tool schema，突出课程、任务、复习计划、作业拆解等工具。
- [app/routers/chat.py](./app/routers/chat.py): 通过 `SP_AGENT_RUNTIME` 选择 `langgraph` 或 `legacy` runtime。

关键设计是“框架外层 + 原业务内核”：LangGraph/RAG 负责检索课程资料和注入上下文，真正的工具调用、确认卡、schema preflight、冲突校验和数据库写入仍复用 [app/agent/loop.py](./app/agent/loop.py)。

启用方式：

```bash
SP_AGENT_RUNTIME=langgraph
SP_RAG_CORPUS_DIR=data/rag
SP_RAG_EMBEDDING_PROVIDER=dashscope
SP_RAG_EMBEDDING_MODEL=text-embedding-v4
SP_RAG_EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
SP_RAG_EMBEDDING_API_KEY=<your-dashscope-api-key>
SP_RAG_EMBEDDING_BATCH_SIZE=10
SP_RAG_VECTOR_STORE_PROVIDER=chroma
SP_RAG_VECTOR_STORE_DIR=data/rag/chroma
```

`text-embedding-v4` 和 `https://dashscope.aliyuncs.com/compatible-mode/v1` 来自阿里云百炼/Model Studio 的 Embedding 官方示例；如果不填写 `SP_RAG_EMBEDDING_API_KEY`，系统会在返回的 RAG 事件里标记 `embedding_provider=hash-fallback`。默认请求的向量库是 Chroma `data/rag/chroma`，不是纯内存缓存；RAG 返回信息里会包含 `vector_store_requested_provider`、`vector_store_effective_provider`、`vector_store_fallback_reason`、`vector_store_hits` / `vector_store_misses`，可用于确认是否复用了已持久化的 chunk 向量。本 worktree 已用原生 Python 3.12 venv `.venv-native` 验证 `chromadb 1.5.9` 可正常 upsert/query，真实 RAG 报告中 `vector_store_effective_provider=chroma`；如果改用当前 Anaconda Python，Chroma native upsert 会触发 access violation，系统会自动 fallback。

示例资料：

- [data/rag/大学英语3复习资料.md](./data/rag/大学英语3复习资料.md)
- [data/rag/机器学习报告要求.md](./data/rag/机器学习报告要求.md)
- [data/rag/中国近现代史复习大纲.md](./data/rag/中国近现代史复习大纲.md)
- [data/rag/思想政治理论复习大纲.md](./data/rag/思想政治理论复习大纲.md)
- [data/rag/世界现代史专题案例.md](./data/rag/世界现代史专题案例.md)
- [data/rag/public](./data/rag/public): 通过 [scripts/import_public_rag_sources.py](./scripts/import_public_rag_sources.py) 导入的中文维基百科公开条目，覆盖中国近现代史、世界现代史、思想政治理论和机器学习基础等主题；本轮请求 80 个来源，实际导入 74 个，来源、URL、许可和导入错误记录在 [data/rag/public/PUBLIC_SOURCES.json](./data/rag/public/PUBLIC_SOURCES.json)。这些资料用于 RAG 检索测试，遵循 CC BY-SA 4.0 署名和相同方式共享要求。

#### ReAct 风格执行闭环

当前 Agent 更接近 ReAct / function calling 模式，而不是严格的 Plan-and-Execute：

```text
Thought(模型内部判断) -> Action(tool_call) -> Observation(tool_result) -> 下一轮判断 -> Final
```

实现上对应几层代码：

- [app/agent/loop.py](./app/agent/loop.py): 主循环，负责构造上下文、调用模型、处理 `tool_call`、回填 `tool_result`，直到最终回复。
- [app/agent/tools.py](./app/agent/tools.py): 工具能力表，限制模型能调用哪些业务动作。
- [app/agent/tool_executor.py](./app/agent/tool_executor.py): 工具执行层，真正查询或写入课程、任务、提醒等数据。
- [app/agent/tool_preflight.py](./app/agent/tool_preflight.py): 执行前校验，拦截缺必填参数、非法枚举、任务创建/修改混淆等风险。
- [app/agent/study_planner.py](./app/agent/study_planner.py): 复习计划生成器，只生成候选任务 JSON，不直接写入数据库。

一个典型任务修改流程是：

```text
用户要求修改任务
-> 模型调用 list_tasks 查找目标
-> 工具返回任务列表
-> 模型调用 ask_user 请求确认
-> 用户确认
-> 模型调用 update_task
-> 后端更新任务并同步 reminder
-> 模型返回最终结果
```

写入类动作必须先走 `ask_user`；工具结果会作为 Observation 回到模型上下文，驱动下一步决策。

### 前端

- React 18 + TypeScript + Zustand
- 移动端优先的聊天、日历、课程和通知页面
- Vite PWA 支持安装、缓存和推送订阅

## 本地运行

### 1. 配置环境变量

- 参考 [`.env.example`](./.env.example)
- 本地实际运行需要创建 `student-planner/.env`

### 2. 后端

在 `student-planner/` 目录下：

```bash
py -3.12 -m alembic upgrade head
py -3.12 -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 3. 前端

在仓库根目录下：

```bash
npm --prefix student-planner/frontend install
npm --prefix student-planner/frontend run dev
```

## 测试

### 后端测试

```bash
py -3.12 -m pytest -q
```

期末版核心回归：

```bash
py -3.12 -m pytest -q tests/test_chat_ws.py tests/test_agent_loop_task_creation.py tests/test_tool_preflight.py tests/test_tools_schema.py tests/test_langgraph_rag_runtime.py
```

### 前端测试

```bash
npm --prefix student-planner/frontend test
npm --prefix student-planner/frontend run build
```

LangGraph/RAG 浏览器证据：

```bash
npm --prefix student-planner/frontend run e2e:agent-loop -- --grep "emits LangGraph RAG" --reporter=list
npm --prefix student-planner/frontend run e2e:agent-loop -- --grep "generates a study plan and writes confirmed review tasks" --reporter=list --global-timeout=420000
```

RAG 质量评测：

```bash
py -3.12 scripts/import_public_rag_sources.py --preset expanded --limit 80 --max-chars 18000 --delay 1.2 --skip-existing
py -3.12 scripts/evaluate_rag_quality.py --top-k 5 --queries-per-case 50 --include-details --output data/rag/RAG_QUALITY_300_DETAILS.json --summary-output data/rag/RAG_QUALITY_300.json --sample-output data/rag/RAG_QUALITY_SAMPLE_QA.md --samples-per-case 4
py -3.12 scripts/generate_rag_result_samples.py --top-k 5
```

最近一次验证结果：

- 后端核心回归：`54 passed`
- 前端 `typecheck`：PASS
- 前端 build：PASS
- RAG smoke：`1 passed`
- 真实百炼 Embedding smoke：`embedding_provider=dashscope`，`embedding_model=text-embedding-v4`，`fallback_reason=none`
- 公开大语料 RAG quality：`300 queries / 6 scenarios / 50 each`，`Recall@5=100%`，`Top1 source hit=93.33%`，严格术语通过率 `92.00%`，`chunk_count=2472`，`chunk_overlap=150`，`embedding_provider=dashscope`，`vector_store_provider=chroma`，首次构建 `vector_store_hits=0 / misses=2472`，清进程缓存后复查 `vector_store_hits=2472 / misses=0`。汇总报告位于 [data/rag/RAG_QUALITY_300.json](./data/rag/RAG_QUALITY_300.json)，完整明细位于 [data/rag/RAG_QUALITY_300_DETAILS.json](./data/rag/RAG_QUALITY_300_DETAILS.json)，可读召回样例位于 [data/rag/RAG_QUALITY_SAMPLE_QA.md](./data/rag/RAG_QUALITY_SAMPLE_QA.md)，最终回答 result 样例位于 [data/rag/RAG_RESULT_SAMPLE_ANSWERS.md](./data/rag/RAG_RESULT_SAMPLE_ANSWERS.md)
- 真实模型复习计划写入 E2E：`1 passed (57.2s)`，`plan_write.created_count=19 / failed_count=0`

## 阅读建议

- 如果你关心产品能力：先看 [app/agent](./app/agent) 和 [frontend/src/pages](./frontend/src/pages)
- 如果你关心架构与质量：再看 [tests](./tests) 和 [../docs/superpowers](../docs/superpowers)
- 如果你关心移动端体验：重点看 [frontend/src/sw.ts](./frontend/src/sw.ts)、[frontend/src/pages/NotificationsPage.tsx](./frontend/src/pages/NotificationsPage.tsx) 和 [frontend/src/pages/ChatPage.tsx](./frontend/src/pages/ChatPage.tsx)
