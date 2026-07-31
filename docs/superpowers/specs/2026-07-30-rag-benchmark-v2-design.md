# 课程 RAG Benchmark v2 设计

## 1. 目标

在不推翻现有四模式检索实现与 `rag-course-v1.1` 语料的前提下，把当前工程评测升级为可用于毕业论文的、证据边界明确的 Benchmark v2。

v2 只回答以下问题：

1. 在完全相同的语料、chunk、查询、候选规模和 Top-K 下，`embedding_only`、`bm25_only`、`hybrid_rrf`、`hybrid_rerank` 的检索排序有何差异？
2. development set 上冻结的 evidence gate 在未参与调参的数据上表现如何？
3. 检索差异是否转化为更完整、更受证据支持、引用更准确的最终回答？
4. 这些差异是否具有稳定的配对置信区间，而不只是单个平均数的偶然波动？

## 2. 证据等级

### 2.1 受控 synthetic 主集

现有 `data/rag/course_v1` 保留为受控 synthetic 主集：

- 4 门课程；
- 49 份 synthetic 资料；
- 552 个稳定 chunks；
- 80 条自动构造查询；
- 24 条 development / 56 条 internal test；
- 2295 条自动构造 qrels；
- `human_review_status=synthetic_unreviewed`。

这组数据只支持以下表述：

> 在同一自动构造课程语料和相关性合同上的受控四模式消融。

不得称为人工 golden set、真实课程效果、人工标注准确率或对未知真实数据的泛化结论。

旧在线 smoke 已查看完整数据上的逐题结果，因此 56 条 internal test 不再视为严格未见测试集。它仍可用于受控内部比较，但论文必须显式标注为 `internal_test_exposed_by_pilot`。

### 2.2 独立 challenge holdout

v2 新增独立 challenge holdout 合同，目标为 24～32 条，不并入主集：

- 在检索模式、RRF 参数、candidate Top-K 和 gate 阈值冻结后创建；
- 覆盖四门课程；
- 优先覆盖复杂改写、多证据、相似主题干扰、`partial`、`none`；
- query 文本不得与 development/internal test 重复；
- qrels 从四模式 pooled candidates 中独立判定；
- 评测前不得用于调参；
- 只运行一次正式结果。

若没有第二标注者，允许使用 LLM 辅助判定加单人抽查，但证据等级只能写成 `llm_assisted_single_review_silver`。若连单人抽查也没有完成，只能写成 `llm_assisted_unreviewed`，不得称为 gold。

challenge holdout 不是 Benchmark v2 基础设施完成的阻塞项，但它是“外部/未见验证”结论的阻塞项。

## 3. 公平对照合同

四种模式固定为：

| 模式 | 候选 | 最终排序 |
|---|---|---|
| `embedding_only` | Vector Top 20 | Vector rank |
| `bm25_only` | BM25 Top 20 | BM25 rank |
| `hybrid_rrf` | Vector Top 20 + BM25 Top 20 | RRF `k=60` |
| `hybrid_rerank` | 与 `hybrid_rrf` 相同的 Top 20 | `qwen3-rerank` |

所有模式统一：

- corpus / chunks / query / qrels；
- course filter；
- chunking；
- final Top 10；
- answer context Top 3；
- development/test/holdout 划分；
- 成本单价记录方式。

正式 `hybrid_rerank` 禁止 `LocalFeatureReranker` fallback。

## 4. 数据划分与报告边界

### 4.1 Development

仅用于：

- evidence gate 阈值选择；
- 预注册模式选择；
- 运行合同与输出 schema 验证。

Development 结果可以附录报告，但不得与 test 混合成主表。

### 4.2 Internal test

用于：

- 四模式受控主表；
- 按 course/query type/answerability 分组分析；
- 配对 bootstrap 差值；
- 失败案例筛选。

所有主图和 `chart_data.csv` 只读取 test 结果，不再读取 development + test 混合平均。

### 4.3 Challenge holdout

只用于：

- 冻结系统的未见难例验证；
- 检查主实验结论方向是否保持；
- 报告外部有效性限制。

不得根据 holdout 结果修改语料、阈值或排序参数后再次报告同一 holdout。

## 5. 检索层指标

主指标：

- `nDCG@10`
- `MRR`
- `Recall@5`

辅助指标：

- `Recall@3 / Recall@10`
- `Precision@K`
- `Top-1 source hit`
- `complete_evidence_recall@10`
- `judged@K`
- evidence gate Macro-F1
- evidence gate false accept rate
- mean / P95 latency
- token usage / estimated cost

每个主指标必须输出：

- test 均值；
- 95% bootstrap 置信区间；
- 相对 `embedding_only` 的配对均值差；
- 配对差值 95% bootstrap 置信区间。

当差值区间跨 0 时，只能写“未观察到稳定差异”，不得写“显著提升”。

## 6. 答案层合同

答案层只比较：

1. `embedding_only`；
2. development set 预先选定的最佳 hybrid 模式。

每条答案输出：

- `query_id`
- `mode`
- `answer`
- 逐句文本和引用 chunk IDs
- 是否拒答
- 使用的 evidence chunk IDs
- 模型、提示词版本、温度和运行日期

答案层判断拆成：

- citation validity：引用是否来自本次实际 evidence；
- citation relevance：引用是否在 qrels 中相关；
- sentence support：需要引用的句子是否被引用证据完整/部分支持；
- nugget coverage：参考信息点是否被覆盖；
- refusal correctness：`full/partial/none` 下是否正确回答或拒答；
- answer completeness：必要信息是否完整。

允许 LLM Judge 辅助 `sentence support` 与 `nugget coverage`，但必须：

- 固定 Judge 模型和 rubric；
- 保存逐条 Judge 原始输出；
- 对小样本进行人工抽查；
- 不把单一 Judge 当作人工真值。

## 7. 正式运行门槛

CLI 的 `--formal` 模式必须拒绝：

- 非空输出目录；
- dirty Git 工作区；
- 非四模式完整运行；
- `--allow-reranker-fallback`；
- 缺失真实 Embedding 配置；
- 缺失真实 Qwen Reranker 配置；
- corpus/dataset manifest 或 hash 不匹配；
- 未冻结的 split；
- 结果 schema 版本不是 v2。

正式 run manifest 至少记录：

- Git commit 与 clean 状态；
- corpus/dataset/challenge hashes；
- 模型、endpoint、维度、instruction；
- candidate Top-K、RRF k、answer Top-K；
- bootstrap seed/iterations；
- cost rates；
- Python 与关键依赖版本；
- 全部输出文件 hash。

## 8. 输出

每次 v2 run 输出：

- `{mode}.jsonl`：逐题原始检索结果；
- `summary.json`：development/test 分离汇总；
- `summary.csv`：test 主表；
- `confidence_intervals.json`；
- `paired_comparisons.csv`；
- `chart_overall.csv`；
- `chart_query_type.csv`；
- `chart_answerability.csv`；
- `gate_predictions.jsonl`；
- `run_manifest.json`；
- 失败时独立 `failed_run.json`。

答案层另输出：

- `answer_runs.jsonl`；
- `answer_judgments.jsonl`；
- `answer_summary.json/csv`；
- `chart_answer_quality.csv`。

## 9. 可视化

论文主图固定为：

1. 四模式检索指标分组柱状图，带 95% CI；
2. `nDCG@10`—P95 latency 质量/效率散点图；
3. query type × mode 热力图；
4. answerability gate 混淆矩阵；
5. Embedding-only 与最佳 Hybrid 的答案层指标对比；
6. 2～4 个成功/失败案例的 evidence rank 对照图。

## 10. 完成标准

Benchmark v2 基础设施完成必须满足：

- development/test 汇总完全分离；
- 主图只使用 test；
- bootstrap CI 和配对差值可复现；
- formal preflight 能阻止 dirty Git、非空目录和 fallback；
- challenge holdout 有独立 schema/validator；
- 答案层 run/judgment schema 可校验并汇总；
- 所有新增逻辑有测试；
- 现有四门课数据验证通过；
- 不执行正式在线 run；
- `git diff --check` 通过；
- `progress.md` 与 `bugs.md` 同步。
