# 课程复习资料 RAG 落地计划

> 对应设计：`docs/superpowers/specs/2026-07-28-course-material-rag-design.md`
> 状态：COMPLETE
>
> 2026-07-29 完成后范围调整：大学英语从正式 RAG 数据集中移除；当前 full corpus 为 4 门课程、49 份资料、552 个 chunks、80 条查询。下方 Task 5 数字保留为原始实施验收记录。

## Task 1：冻结合同与基线

- [x] 把设计中的语料、切块、检索模式、Reranker、qrels、gate 和输出要求映射到代码与测试。
- [x] 记录现有 `rag.py`、旧评测脚本、语料和运行时事件的基线，确认兼容边界。
- [x] 验证 `qwen3-rerank` 官方 endpoint、模型名和请求合同，并写入配置边界。

## Task 2：实现冻结语料与稳定 chunk

- [x] 实现 `course-rag-normalize-v1`、YAML front matter 解析和固定 `course-rag-chunker-v1`。
- [x] 实现与 Embedding 无关的稳定 chunk ID，并让向量缓存 ID 与 chunk ID 分离。
- [x] 实现 `corpus_manifest.json`、`chunks.jsonl` 导出和版本/hash 校验。
- [x] 补齐规范化、切块、稳定 ID、manifest 失配测试。

## Task 3：实现四种检索模式和 Reranker

- [x] 统一实现 `embedding_only`、`bm25_only`、`hybrid_rrf`、`hybrid_rerank`。
- [x] 抽出 `Reranker`、`LocalFeatureReranker`、`Qwen3Reranker` 接口。
- [x] 保证 RRF 与 Rerank 候选合同、最终 rank 和诊断字段一致。
- [x] 实现正式 benchmark 失败即失败、交互运行时显式降级的不同合同。
- [x] 补齐四模式单变量、公平候选、失败/降级和诊断测试。

## Task 4：实现正式评测框架

- [x] 定义并校验 query、三级 qrels、answerability 和 evidence requirements schema。
- [x] 实现固定 seed 的 course/query type/answerability 分层 development/test 划分。
- [x] 实现 Recall/Precision/MRR/nDCG/judged@K、source hit、完整证据召回、延迟和成本输出。
- [x] 实现各模式有限参数网格的 gate 校准、5% false-accept 约束和固定 tie-break。
- [x] 输出原始 JSONL、run manifest、汇总 JSON/CSV 和图表数据；测试集禁止调参。

## Task 5：生成完整模拟语料和 golden set

- [x] 生成 5 门课程、50～70 份带 `synthetic: true` 元数据的结构化 Markdown。
- [x] 导出并校验 600～1000 个冻结 chunk。
- [x] 生成 80～120 条覆盖七类查询和 full/partial/none 的人工可复核查询。
- [x] 先完成独立 pilot 检查，再冻结正式数据集、qrels、划分和 manifest。

## Task 6：接入运行时与用户可见证据

- [x] 让运行时使用冻结语料/索引和统一检索入口，默认答案上下文只取最终 Top 3。
- [x] 保证回答引用只来自实际 evidence chunks，并保留课程、文件、章节和片段。
- [x] 保证 partial/none/out-of-scope 稳定拒答，在线 Reranker 降级原因进入事件诊断。
- [x] 更新配置样例、运行说明、设计状态和 `progress.md`。

## Task 7：完成验证与审计

- [x] 运行语料/数据集校验和离线四模式 smoke。
- [x] 运行 RAG、路由、LangGraph、WebSocket 定向回归。
- [x] 运行后端全量回归及相关前端测试/typecheck/build。
- [x] 运行 `git diff --check`，逐项审计设计第 13 节完成标准。
