# Student Planner 课程复习资料 RAG 设计

> 生成日期：2026-07-28
> 状态：IMPLEMENTED（2026-07-28）；采用 synthetic 未人工复核评测边界，当前四门课版本的真实 Qwen 在线 benchmark 待执行
> 模式：毕业设计 / 研究型系统设计

## 1. 问题与目标

Student Planner 的 RAG 不是独立的技术演示，而是服务于一个明确的学生复习场景：

```text
预先准备课程复习资料
→ 学生遇到不会或不确定的问题
→ 系统从课程资料中检索证据
→ 只基于证据回答并展示来源
→ 资料不足时明确拒答
```

本设计同时服务两类目标：

1. 产品目标：让学生能够基于预置复习资料获得有来源、可核查的回答。
2. 研究目标：在完全相同的语料、切块、查询集和 Top-K 合同下，对比纯向量、BM25、混合融合和重排方案。

RAG 与混合意图路由并列为毕业设计的两项主要实验内容；安全确认与事务写入作为系统可靠性验证，不与前两项争夺算法创新口径。

## 2. 已确认前提

1. 第一版继续使用预置资料，不实现学生自行上传 PDF、Word 或 PPT。
2. 允许正式实验调用在线 Embedding、Reranker 和 LLM Judge，但必须冻结模型、参数、运行日期和原始输出。
3. 课程资料允许使用生成式模型辅助构造，但必须显式标注为模拟语料，不宣称来自真实高校课程。
4. 语料目标为 4 门课程、45～60 份结构化资料、500～850 个有效 chunk。
5. 检索评测集目标为 80～120 条自动构造问题；因人力限制不执行人工复核，论文必须显式说明 synthetic 标签边界。
6. 当前运行时继续由 LangGraph 负责路由和状态流转，不迁移到 LlamaIndex。

## 3. 当前基线

当前 `app/agent/rag.py` 已具备：

- `text-embedding-v4` 或其他 OpenAI-compatible Embedding；
- Chroma / SQLite / memory 向量缓存；
- 本地 BM25；
- 向量与 BM25 候选的 RRF 融合；
- 基于融合分数、向量分数、BM25 分数和覆盖率特征的本地加权重排；
- 证据充分性判断；
- evidence chunk 与来源诊断字段。

LangGraph 的 RAG 路径负责：

```text
route
→ retrieve_rag
→ rag_insufficient 或 compose_runtime_hints
→ rag_qa
```

当前主要缺口不是框架能力，而是：

1. 缺少结构统一、覆盖课程复习场景的模拟语料。
2. 旧评测只标注预期 source，缺少 chunk 级 qrels。
3. 评测脚本仍以纯向量路径为主，尚未在同一数据集上公平运行四种模式。
4. 当前 `local-feature-rerank` 是人工特征加权，不是学习型 Reranker。

## 4. 方案比较

### 方案 A：保留现有混合检索

继续使用向量召回、BM25、RRF 和本地特征重排，仅扩充语料并补 benchmark。

- 工作量：S
- 风险：低
- 优点：改动最小，能够快速形成先导实验。
- 缺点：最终重排仍由人工权重决定，对语义相关性的建模有限。

### 方案 B：现有框架内加入学习型 Reranker

保持语料、切块、候选池和 LangGraph 边界不变，在 RRF 之后增加 `qwen3-rerank`，并将当前本地重排保留为基线和网络失败时的显式降级能力。

- 工作量：M
- 风险：中低
- 优点：与当前架构兼容，能够形成单变量、可解释的检索消融。
- 缺点：增加在线 API 成本与延迟，需要处理配额、超时和结果可复现性。

### 方案 C：迁移 LlamaIndex / GraphRAG

使用 LlamaIndex ingestion、Node、Retriever 和 Postprocessor，或进一步引入图谱抽取与多轮检索。

- 工作量：L～XL
- 风险：高
- 优点：适合未来的大量异构文件导入、自动元数据抽取和跨文档主题聚合。
- 缺点：当前预置 Markdown、600～1000 chunk 的场景用不到主要优势；会重写缓存、chunk identity、证据 gate、诊断字段和测试，且使实验难以区分算法收益与框架迁移影响。

## 5. 推荐决策

采用方案 B，但把产品增强与核心检索消融分开。

第一阶段只做公平的四模式比较：

```text
embedding_only
bm25_only
hybrid_rrf
hybrid_rerank
```

四种模式的固定排名合同为：

| 模式 | 第一阶段候选 | 融合 / 重排 | 评测输出 |
|---|---|---|---|
| `embedding_only` | 向量 Top 20 | 不融合、不重排 | 保留原始向量排序的 Top 10 |
| `bm25_only` | BM25 Top 20 | 不融合、不重排 | 保留原始 BM25 排序的 Top 10 |
| `hybrid_rrf` | 向量 Top 20 + BM25 Top 20 的去重并集 | `RRF_K=60` | RRF 排序 Top 10 |
| `hybrid_rerank` | `hybrid_rrf` 排序后的 Top 20 | `qwen3-rerank` | Reranker 排序 Top 10 |

检索指标统一在 Top 10 排名结果上计算；答案生成默认只使用最终 Top 3 evidence chunks。候选数、RRF 常数、评测 Top-K 和答案上下文 Top-K 只能在开发集调整一次，冻结测试集前写入 run config。

四种模式必须共享：

- 同一 corpus manifest；
- 同一切块结果与稳定 chunk ID；
- 同一 Embedding 模型和维度；
- 同一向量候选数、BM25 候选数和最终 Top-K；
- 同一查询集和 qrels；
- 同一证据充分性合同。

`hybrid_rrf` 与 `hybrid_rerank` 的唯一差异是是否调用学习型 Reranker。课程过滤、标题感知切块、相邻上下文扩展不能只在最终模式启用，否则会破坏核心消融的公平性。

课程元数据和相邻上下文可以在核心消融完成后作为独立辅助实验；若不做辅助实验，则所有四种模式统一启用或统一关闭。

当前 `LocalFeatureReranker` 不进入已确认的四模式主表。它仅作为：

- 现有运行时兼容基线；
- 可选的辅助实验；
- 交互运行时在线 Reranker 失败后的显式降级实现。

正式 `hybrid_rerank` benchmark 不允许降级到 `LocalFeatureReranker`。

## 6. 框架边界

不迁移 LlamaIndex。保留：

```text
LangGraph
+ LocalRAGRetriever
+ LangChain Document / Embedding / TextSplitter 抽象
+ Chroma
+ text-embedding-v4
+ qwen3-rerank
```

LlamaIndex 只有在后续范围明确扩大到用户上传大量 PDF、Word、PPT、自动元数据提取或复杂父子索引时才重新评估。框架优劣不进入本次毕业设计的对照实验。

技术选择依据：

- 阿里云当前将 `text-embedding-v4` 定位为文本搜索与 RAG 的主力文本向量模型：<https://help.aliyun.com/en/model-studio/embedding>
- 阿里云当前推荐 `qwen3-rerank` 用于文本 RAG 重排：<https://help.aliyun.com/en/model-studio/rerank>
- LlamaIndex ingestion 与 Node 能力适合复杂资料导入，但不是当前预置 Markdown 范围的必要依赖：<https://docs.llamaindex.ai/en/v0.10.19/understanding/loading/loading.html>

## 7. 模拟课程语料

### 7.1 课程范围

优先沿用当前项目主题：

1. 机器学习基础
2. 中国近现代史
3. 世界现代史
4. 思想政治理论

2026-07-29 范围调整：大学英语模拟资料偏听说读写训练，概念问答密度低，容易引入与其他课程不一致的模板噪声，因此从正式 corpus、查询和 qrels 中整体移除；普通课程管理和复习计划功能仍可处理英语课程。

每门课程准备 10～14 份资料，资料类型包括：

- 章节讲义
- 复习提纲
- 概念辨析
- 例题与答案解析
- 高频易错点
- 作业或考试要求

### 7.2 语料难度

生成语料必须刻意包含：

- 精确术语和专有名词；
- 同义表达与语义改写；
- 相近但不同的概念；
- 同一术语在不同课程或章节中的不同语义；
- 需要两个以上证据片段的问题；
- 资料中仅部分可回答的问题；
- 资料中完全没有答案的问题。

不得通过机械改写同一句话制造大量重复资料。语料生成和评测问题生成应使用不同提示或不同批次，并经过人工检查，避免测试问题直接复制语料标题或原句。

### 7.3 元数据与稳定 ID

每份资料采用 UTF-8 Markdown，文件顶部使用 YAML front matter 记录：

```yaml
course_id: machine_learning
chapter_id: model_evaluation
material_type: review_outline
synthetic: true
corpus_version: rag-course-v1
```

`source_id` 定义为 corpus 根目录下区分大小写的 POSIX 相对路径，例如：

```text
machine_learning/model_evaluation/review_outline.md
```

在切块前执行固定的 `course-rag-normalize-v1`：

1. 去除 UTF-8 BOM；
2. 将 CRLF / CR 统一为 LF；
3. 对 Unicode 执行 NFC 规范化；
4. 删除每行尾部空白；
5. 文档首尾空白只保留为零；
6. YAML front matter 不进入正文 chunk，但其字段复制到每个 chunk metadata。

核心实验使用固定 `course-rag-chunker-v1`：

- `chunk_size=520` 个 Python 字符；
- `chunk_overlap=150` 个 Python 字符；
- `length_function=len`；
- `keep_separator=True`；
- 分隔符顺序固定为 `["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""]`；
- chunk 顺序按 `source_id` 排序后的文件顺序和文内出现顺序确定；
- 空白 chunk 丢弃，其余 chunk 不再二次改写。

chunk ID 必须独立于 Embedding provider、模型和向量维度，定义为：

```text
SHA256(
  "course-rag-chunk-v1\n"
  + source_id + "\n"
  + chunk_index + "\n"
  + SHA256(normalized_chunk_text)
)
```

Embedding 缓存 ID 可以继续包含模型配置，但不能作为 qrels 中的黄金 chunk ID。

切块后导出：

- `corpus_manifest.json`：corpus version、所有 source hash、规范化和切块参数；
- `chunks.jsonl`：chunk ID、source ID、chunk index、正文和复制后的 metadata。

任何 source 正文、规范化规则或切块参数变化都产生新的 corpus/chunk-set 版本，旧 qrels 不得继续使用。

## 8. 检索与回答数据流

```text
用户问题
→ 混合意图路由判断是否为课程资料问答
→ 读取冻结 corpus/index
→ 按实验模式产生候选
→ 可选 RRF
→ 可选 qwen3-rerank
→ 证据充分性判断
→ 取最终 evidence chunks
→ LLM 仅依据 evidence 生成答案
→ 输出答案、课程、文件、章节与片段引用
```

回答合同：

1. 模型不得使用未提供的外部常识补充事实。
2. 引用只展示真正进入回答上下文的 evidence chunk。
3. evidence 不足时返回稳定的资料不足提示。
4. `out_of_scope` 问题不得因为语义相似而强行回答。
5. Reranker 失败或降级必须进入诊断信息，不能伪装成完整 `hybrid_rerank` 结果。

检索排序评测与 evidence gate 评测是两个独立合同：

1. 检索排序评测不经过 evidence gate，也不按阈值删除结果，直接对各模式 Top 10 与 qrels 计算 Recall、MRR、nDCG 等指标。
2. evidence gate / 拒答评测在开发集上为每种检索模式分别校准阈值，因为向量、BM25、RRF 和 Reranker 分数不在同一尺度。每种模式的阈值随后冻结，在测试集上报告 full-answer acceptance、partial/none rejection 和 false-rejection。
3. 不允许把同一个原始分数阈值机械复用于四种模式，也不允许用测试集调整阈值。

answerability 使用三级真值：

- `full`：资料足以完整回答，gate 期望 `accept`；
- `partial`：资料只能支持部分结论，不能完整回答，gate 期望 `reject`；
- `none`：资料没有可用答案，gate 期望 `reject`。

`partial` 的交互提示应明确“当前资料只能支持部分内容，无法完整回答”，不得把局部证据包装成完整答案。

每种模式的 gate 参数从实施计划预先声明的有限参数网格中选择。开发集选择规则固定为：

1. 优先保留对 `partial + none` 的 false-accept rate 不超过 5% 的配置；
2. 在合格配置中最大化 accept/reject Macro-F1；
3. 并列时依次选择更高的 insufficient-recall、更高的 full-answer recall、字典序更小的 `config_id`；
4. 如果没有配置满足 5% 约束，则选择 false-accept rate 最低者，再按上述第 2～3 条打破并列，并明确报告约束未满足。

参数网格、每个 `config_id` 的完整参数和选择过程写入 run manifest。测试集只使用选出的单一配置。

## 9. Reranker 接口

设计统一接口，避免把供应商调用散落到检索流程：

```text
Reranker.rerank(query, candidates, top_n) -> ranked_candidates
```

至少包含：

- `LocalFeatureReranker`：封装当前人工特征权重，作为兼容基线。
- `Qwen3Reranker`：调用在线 `qwen3-rerank`，返回模型分数和最终 rank。

每个 hit 保留：

- `chunk_id`
- `source`
- `vector_rank` / `vector_score`
- `bm25_rank` / `bm25_score`
- `rrf_score`
- `rerank_provider`
- `rerank_score`
- `final_rank`

正式 benchmark 中，`hybrid_rerank` 如果在线调用失败，应使该条 run 失败并记录错误，不得静默混入本地降级结果。交互运行时可以显式降级，但必须展示 `reranker_fallback_reason`。

## 10. Golden Set 与标注

### 10.1 查询类型

80～120 条问题覆盖：

- `exact_entity`
- `paraphrase`
- `comparison`
- `multi_concept`
- `summary`
- `long_student_query`
- `out_of_scope`

建议至少 10% 为 `out_of_scope`。

### 10.2 标注格式

每条 query 记录：

- `query_id`
- `query`
- `query_type`
- `answerability`（`full | partial | none`）
- `reference_answer`
- `relevant_source_ids`
- `relevant_chunk_ids`
- `qrels`
- `evidence_requirements`
- `expected_terms`（可选）

`qrels` 显式记录每个已判断 chunk 的三级相关性：

```json
{
  "qrels": [
    {"chunk_id": "chunk-a", "relevance": 2},
    {"chunk_id": "chunk-b", "relevance": 1},
    {"chunk_id": "chunk-c", "relevance": 0}
  ]
}
```

等级含义：

- `2`：直接支持答案或属于必要证据；
- `1`：提供相关背景但不能完整回答；
- `0`：不相关。

未进入人工候选池的 chunk 标记为 unjudged，不写入 qrels。主指标按固定 TREC-style 合同将检索结果中的 unjudged chunk 计为 non-relevant，同时额外报告 judged@K，暴露候选池覆盖不足。二值 Recall、Precision 和 MRR 将 `relevance >= 1` 视为相关；nDCG 使用 `0/1/2` 原始等级。`relevant_chunk_ids` 从 `qrels.relevance > 0` 派生，不能与 qrels 手工维护两份冲突真值。

候选标注池由四种检索模式各自 Top 20 的并集构成，并补充对已知相关资料的人工搜索，降低单一检索器造成的标注偏差。

多证据问题使用 `evidence_requirements` 表达“全部要求都要覆盖，每个要求允许多个替代 chunk”：

```json
{
  "evidence_requirements": [
    {
      "requirement_id": "cause",
      "any_of_chunk_ids": ["chunk-a", "chunk-b"]
    },
    {
      "requirement_id": "effect",
      "any_of_chunk_ids": ["chunk-c"]
    }
  ]
}
```

当 Top-K 对每个 requirement 都命中至少一个 `any_of_chunk_ids` 时，才算完整证据召回。`relevant_chunk_ids` 是所有 requirement 候选和其他相关 chunk 的并集，用于普通 Recall/MRR/nDCG；完整证据召回率单独报告。

`evidence_requirements` 只用于 `answerability=full` 的完整证据评测；`partial` 和 `none` 不进入 complete-evidence recall 分母，而进入独立的 gate/拒答评测。检索指标按 answerability 分层报告，避免把“能召回局部相关资料”和“资料足以完整回答”混为一类。

先完成 15～20 条 pilot 并修订生成规则，再扩展到完整数据集。pilot 不进入最终结果。正式 synthetic 数据集按 course、query type 和 answerability 分层，以固定 seed 划分为 30% development、70% test；划分清单与 dataset manifest 一起冻结。所有 Top-K、RRF、Reranker、证据阈值和提示词只能在 development 调整，test 只在最终配置冻结后运行。本项目因人力限制不执行人工复标，因此结果只表示各检索方案在同一自动构造数据合同上的相对表现，不能外推为人工相关性判断或真实课程问答效果。

## 11. 评测

### 11.1 检索层

主要指标：

- Recall@3 / Recall@5 / Recall@10
- Precision@K
- MRR
- nDCG@5 / nDCG@10
- Top-1 source hit
- 不可回答问题的错误证据通过率
- 平均延迟、P95 延迟
- 单次查询估算成本

结果必须按 query type 分组，避免总平均值掩盖 BM25 对精确术语和 Embedding 对语义改写的差异。

多证据问题额外报告 requirement-level recall 和 complete-evidence recall。检索层主表不应用 evidence gate；gate/拒答结果单独成表，避免把排序质量和阈值质量混成一个指标。

### 11.2 答案层

检索消融稳定后，只选择：

1. `embedding_only` 基线；
2. 开发集确定的最佳 hybrid 方案。

在冻结测试集上比较：

- 答案正确性
- Faithfulness
- Answer Relevance
- 引用准确率
- 拒答准确率

LLM Judge 不是唯一真值，必须保留原始回答、模型配置和人工抽查记录。

## 12. 错误处理与可复现性

- Embedding 或 Reranker 超时：交互运行时返回可见降级原因；正式实验 run 失败，不静默替换模式。
- corpus 变化：corpus manifest 或 hash 改变后必须重建索引，并产生新数据集版本。
- chunker 变化：产生新 chunk set 和 qrels 版本，旧 qrels 不得继续复用。
- 返回空候选：进入 evidence insufficient，不调用自由知识回答。
- 在线模型升级：固定模型 ID；若供应商只提供浮动别名，记录运行日期和完整原始响应。
- 每次正式运行记录 Git commit、工作区状态、数据集版本、配置、随机种子、开始时间和结果文件校验值。

## 13. 验证与完成标准

设计落地后至少满足：

1. 四种模式由同一入口运行，并输出统一 schema。
2. `hybrid_rrf` 与 `hybrid_rerank` 除 Reranker 外没有其他变量差异。
3. qrels 使用稳定 chunk ID，不依赖 Embedding 模型配置。
4. 所有回答引用与实际 evidence context 一致。
5. 资料不足和 out-of-scope 问题不会被模型常识绕过。
6. 在线 Reranker 失败不会被统计为成功的 `hybrid_rerank`。
7. 能以固定命令导出原始 JSON/JSONL、汇总 CSV 和论文图表数据。
8. 后端 RAG、路由、LangGraph、WebSocket 相关回归通过，`git diff --check` 通过。

2026-07-28 实现审计：以上八项均已有代码与自动化证据；pilot/full corpus 与 dataset 校验通过，四模式离线 fallback smoke 成功，禁止 fallback 的 Reranker 缺配置路径以失败状态和 `failed_run.json` 收口，RAG/路由/LangGraph/WebSocket 联合回归 `97 passed`，后端全量 `432 passed`，前端 Chat/store `64 passed, 2 skipped`，typecheck/build 与 `git diff --check` 通过。真实 Qwen 在线 benchmark 仍按第 15 节列为外部后续，不计入当前代码落地完成声明。

2026-07-29 语料范围调整审计：移除大学英语后重新冻结 full corpus 和查询集，当前论文基线为 `rag-course-v1.1 / rag-course-golden-v1.1`，包含 4 门课程、49 份资料、552 个 chunks、80 条查询（development 24 / test 56、2295 qrels），`corpus_manifest_sha256=8ac077eb690cba2db97fe1d3335a00b19d2a2f933a1b9e6a40cca723b93c52d7`；corpus/dataset 校验以及包含盲审导出的 76 项 RAG 定向测试通过。此前基于 5 门课程版本的在线 comparison smoke 仅保留为历史记录，不能代表当前数据集。

## 14. 非目标

- 本阶段不实现用户上传资料。
- 不迁移 LlamaIndex。
- 不引入 GraphRAG、多 Agent 或 LLM 自主多轮检索。
- 不比较 LangChain、LangGraph、LlamaIndex 的框架优劣。
- 不把模拟语料结果宣传为真实高校课程或生产级结论。
- 不在核心检索消融中同时改变 chunking、metadata filtering 和上下文扩展。

## 15. 开放事项

1. 已冻结 4 门 synthetic 课程、49 份资料、552 个 chunks 和 80 条自动构造查询；20 题、240 个候选 chunks 的无标签盲审包仅作为可选归档，不执行人工填写与裁决。
2. `qwen3-rerank` 的模型名和 `/reranks` 请求合同已按官方文档实现；当前账号所在地区/workspace 的 base URL、配额与真实在线稳定性仍需使用实际凭据验证。
3. 当前评测集明确标记为 `synthetic_unreviewed`，任何结果均不得称为人工 golden set、人工标注准确率或真实课程效果。
4. 课程 metadata filtering 和相邻上下文扩展是否进入第二阶段辅助实验，待核心消融结果后决定。

## 16. 下一项具体工作

实现已经完成 pilot 和完整 synthetic 数据集。下一步不再扩功能：

1. 配置实际 workspace 的 Embedding/Reranker endpoint、Key 和单价。
2. 从干净 Git commit 运行不带 `--allow-reranker-fallback` 的正式四模式 synthetic benchmark。
3. 只用 development set 冻结各模式 gate，再一次性报告 test set。
4. 输出论文表格、图表、失败案例和限制说明，明确 synthetic 未人工复核边界。

2026-07-30 更新：正式评测协议已由 `docs/superpowers/specs/2026-07-30-rag-benchmark-v2-design.md` 接管。旧在线 pilot 已查看完整主集结果，因此当前 56 条 test 的证据等级明确为 `internal_test_exposed_by_pilot`；唯一一次正式在线运行必须使用 v2 的 dev/test 分离汇总、bootstrap CI、配对比较和 `--formal` preflight。独立 challenge holdout 与答案层判断仍按 v2 合同另行冻结，不再直接按本节旧命令运行正式结果。
