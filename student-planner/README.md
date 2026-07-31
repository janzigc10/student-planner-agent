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

当前聊天入口固定使用 LangGraph，同时保留原有稳定业务闭环：

- [app/agent/langgraph_loop.py](./app/agent/langgraph_loop.py)：LangGraph 路由、检索、证据 gate、资料不足拒答和最终回答节点。
- [app/agent/rag_corpus.py](./app/agent/rag_corpus.py)：冻结语料、YAML 元数据、固定切块、稳定 chunk ID、manifest/hash 校验。
- [app/agent/rag.py](./app/agent/rag.py)：统一实现 `embedding_only`、`bm25_only`、`hybrid_rrf`、`hybrid_rerank`；默认运行时只把最终 Top 3 evidence chunks 注入回答上下文。
- [app/agent/rerankers.py](./app/agent/rerankers.py)：`LocalFeatureReranker` 与在线 `Qwen3Reranker`。交互运行时允许显式降级并返回原因，正式 benchmark 禁止静默降级。
- [app/agent/rag_evaluation.py](./app/agent/rag_evaluation.py)：qrels、固定 development/test 划分、检索指标、evidence 指标和 gate 校准。
- [app/agent/langchain_tools.py](./app/agent/langchain_tools.py): 将现有 `TOOL_DEFINITIONS` 转换为 LangChain tool schema，突出课程、任务、复习计划、作业拆解等工具。

关键设计仍是“框架外层 + 原业务内核”：LangGraph/RAG 负责检索课程资料和注入上下文，真正的工具调用、确认卡、schema preflight、冲突校验和数据库写入仍复用既有业务能力。本阶段不迁移 LlamaIndex，也不引入 GraphRAG 或多 Agent。

默认配置：

```bash
SP_AGENT_RUNTIME=langgraph
SP_RAG_CORPUS_DIR=data/rag/course_v1
SP_RAG_EMBEDDING_PROVIDER=dashscope
SP_RAG_EMBEDDING_MODEL=text-embedding-v4
SP_RAG_EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
SP_RAG_EMBEDDING_API_KEY=<your-dashscope-api-key>
SP_RAG_EMBEDDING_BATCH_SIZE=10
SP_RAG_EMBEDDING_DIMENSIONS=1024
SP_RAG_EMBEDDING_QUERY_INSTRUCT=
SP_RAG_VECTOR_STORE_PROVIDER=chroma
SP_RAG_VECTOR_STORE_DIR=data/rag/chroma
SP_RAG_RETRIEVAL_MODE=hybrid_rerank
SP_RAG_RERANKER_PROVIDER=qwen3
SP_RAG_RERANKER_MODEL=qwen3-rerank
SP_RAG_RERANKER_BASE_URL=<workspace-specific-rerank-base-url>
SP_RAG_RERANKER_API_KEY=<your-dashscope-api-key>
SP_RAG_RERANKER_TIMEOUT_SECONDS=20
```

阿里云百炼的 OpenAI-compatible Embedding 接口支持 `text-embedding-v4` 和 `dimensions`；本项目固定 1024 维。`qwen3-rerank` 使用官方 OpenAI-compatible `/reranks` 合同，但 base URL 可能随地域和 workspace 而异，因此样例不写死。若未配置 Embedding Key，交互运行时会明确标记 `embedding_provider=hash-fallback`；若未配置 Reranker，`hybrid_rerank` 会明确标记 `reranker_provider=local-feature-rerank` 和 `reranker_fallback_reason`。正式 `hybrid_rerank` 评测默认禁止 Reranker 降级；使用 hash Embedding 的离线 run 也必须在 manifest 和结果说明中标为 smoke，不能伪装成真实百炼 Embedding 结果。

冻结数据位于 [data/rag/course_v1](./data/rag/course_v1)：论文基线版本 `rag-course-v1.1 / rag-course-golden-v1.1`，包含 4 门 synthetic 课程（机器学习、中国近现代史、世界现代史、思想政治理论）、49 份资料、552 个稳定 chunks、80 条自动构造查询（development 24 / test 56）。大学英语已因资料偏技能训练、概念性不足而从正式语料中移除。该数据集的 `human_review_status` 为 `synthetic_unreviewed`：可用于同一 synthetic 数据上的受控四模式消融，但不能称为人工 golden set、真实课程结论或人工标注准确率。20 题盲审包保留在 [data/rag/review/course_v1_1](./data/rag/review/course_v1_1) 作为可选归档，不再是实验前置项；小规模独立检查集位于 [data/rag/course_pilot](./data/rag/course_pilot)。

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
py -3.12 scripts/build_course_rag_corpus.py --corpus-dir data/rag/course_pilot --verify-only
py -3.12 scripts/build_course_rag_corpus.py --corpus-dir data/rag/course_v1 --verify-only
py -3.12 scripts/validate_course_rag_dataset.py --profile pilot --root data/rag/course_pilot
py -3.12 scripts/validate_course_rag_dataset.py --profile full --root data/rag/course_v1
py -3.12 scripts/evaluate_course_rag.py --output-dir output/rag/course_v1_v2_smoke --allow-reranker-fallback --bootstrap-iterations 200
```

Benchmark v2 把 development 与 test 完全分开；`summary.csv` 和全部主图只使用 test，development 仅用于 evidence gate 校准。输出同时包含主指标 bootstrap 95% CI、相对 `embedding_only` 的逐 query 配对差值、query type/answerability 图表数据和逐题 gate prediction。

离线 smoke 必须使用全新空目录，并显式追加 `--allow-reranker-fallback`。它只能验证代码和输出合同，不能作为正式 `hybrid_rerank` 结果。

唯一一次正式运行现在使用两阶段入口。它先运行主集 development/test 并写出 `main/frozen_gate_config.json`，再让 challenge 只复用该 gate：

```bash
.\.venv-native\Scripts\python.exe scripts/run_course_rag_benchmark_v2.py --formal --output-root output/rag/course_v2_formal
```

`.venv-native` 已验证包含 `langchain-text-splitters`、`chromadb 1.5.9` 和 OpenAI SDK，Chroma native probe 为 `(True, '')`。`--formal` 会在任何在线调用前拒绝 dirty Git、非空输出目录、非完整四模式、Embedding/Reranker/Vector Store fallback、缺失真实 Embedding 配置或缺失真实 `qwen3-rerank` 配置。根目录输出 `benchmark_manifest.json`，主集与 challenge 分别位于 `main/`、`challenge/`；两个 run manifest 和 gate bundle 全部以 SHA-256 绑定。当前 80 题主集的证据等级为 `synthetic_unreviewed`，且旧 pilot 已查看过完整数据结果，因此正式论文口径是受控 internal test，不是人工 gold 或严格未见测试集。

独立 challenge holdout 已冻结在 [data/rag/course_challenge_v1](./data/rag/course_challenge_v1)：28 条未用于调参的 query，四门课各 7 条，覆盖七种 query type，包含 `full 20 / partial 4 / none 4`。候选池由四模式各 Top 20 去重合并，共 842 个 query-chunk 判断项；当前证据等级仍是 `llm_assisted_unreviewed`、`human_review_status=not_reviewed`，不能称为人工 gold。验证命令：

```bash
py -3.12 scripts/validate_course_rag_challenge.py --challenge-dataset data/rag/course_challenge_v1/challenge_queries.jsonl --challenge-manifest data/rag/course_challenge_v1/challenge_manifest.json
```

`candidate_pool.jsonl` 保留 mode/rank/score 供审计；`blind_query_review.tsv`、`blind_qrel_review.tsv` 和 `blind_judge_input.jsonl` 隐藏这些信息及现有标签；`review_key.json` 单独保存映射。创建候选池时只使用本地 hash embedding 和 local-feature rerank，因此它只是判定覆盖池，不是正式四模式结果。challenge runner 不包含 `calibrate_gate()` 路径，只接受主集 development 生成且 hash 验证通过的 frozen gate bundle。

答案层不在评测脚本中即时调用 Judge；它读取已保存的答案和独立逐句/信息点判断，保证 Judge 原始证据可追溯：

```bash
py -3.12 scripts/evaluate_course_rag_answers.py --dataset <queries.jsonl> --answer-runs <answer_runs.jsonl> --judgments <answer_judgments.jsonl> --output-dir <new-empty-output-dir>
```

本版落地验证结果：

- 冻结语料：`4 courses / 49 documents / 552 chunks`
- 冻结查询：`80 queries / development 24 / internal test 56 / 2295 qrels`
- 后端 RAG/LangGraph 定向回归：见 `progress.md` 的当前 session 记录
- 前端 Chat/store：`64 passed / 2 skipped`
- 前端 `typecheck`：PASS
- 前端 build：PASS

旧的公开语料 300-query 报告仍保留为历史运行记录，但它没有使用本版冻结 corpus、稳定 qrels、四模式统一入口和 development/test gate，因此不属于本版正式对比结果。

## 阅读建议

- 如果你关心产品能力：先看 [app/agent](./app/agent) 和 [frontend/src/pages](./frontend/src/pages)
- 如果你关心架构与质量：再看 [tests](./tests) 和 [../docs/superpowers](../docs/superpowers)
- 如果你关心移动端体验：重点看 [frontend/src/sw.ts](./frontend/src/sw.ts)、[frontend/src/pages/NotificationsPage.tsx](./frontend/src/pages/NotificationsPage.tsx) 和 [frontend/src/pages/ChatPage.tsx](./frontend/src/pages/ChatPage.tsx)
