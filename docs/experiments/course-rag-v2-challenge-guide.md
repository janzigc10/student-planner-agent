# 课程 RAG Benchmark v2 Challenge Holdout 指南

## 用途

Challenge holdout 用于检查已经冻结的四模式检索与 evidence gate 在未用于调参的难例上是否保持结论方向。它不替代当前 80 条 synthetic 主集，也不与主集混合计算。

## 创建时点

只有在以下内容冻结后才创建：

- corpus/chunk hash；
- 四种检索模式；
- Vector/BM25 candidate Top-K；
- RRF `k`；
- final Top-K；
- evidence gate 参数；若阈值由 development 校准，则必须先冻结搜索空间、选择规则和“只读 development”的程序，并在第一次读取 holdout 结果前保存选中阈值；
- Embedding 与 Reranker 模型。

将冻结配置文件计算 SHA-256，并写入 challenge manifest 的 `frozen_config_sha256`。

## 规模与分布

- 24～32 条；
- 四门课程都覆盖，每门至少 4 条；
- 至少 4 条 `partial`；
- 至少 4 条 `none`；
- 必须覆盖 `paraphrase`、`multi_concept`、`long_student_query`、`out_of_scope`；
- 优先加入跨章节相似概念、多个必要证据、口语省略、错误前提和诱导回答。

## Pooling 与判定

1. 对每条 query 收集四种模式 Top 20 的去重并集。
2. 判定时隐藏模式、rank、score、development/test 历史结果。
3. 对每个 query-chunk 给出 `0/1/2` 相关度：
   - `0`：不能帮助回答；
   - `1`：提供部分背景或辅助证据；
   - `2`：直接回答核心信息。
4. `partial/none` 同时记录资料是否足以完整回答。
5. LLM Judge 必须保存模型、rubric 和原始输出。
6. 单人抽查需要记录抽查 query IDs、修改项和日期。

## 证据等级

- `llm_assisted_unreviewed`：只有自动判定；
- `llm_assisted_single_review_silver`：自动判定加单人抽查；
- `human_double_review_gold`：两位人工独立判断并完成分歧裁决。

没有完成对应流程时不得提高证据等级。

## 使用边界

- holdout 只正式运行一次；
- 不允许根据 holdout 结果修改参数后再次报告同一数据；
- 若确实需要修改系统，原 holdout 降级为诊断集，并创建新的未见 holdout；
- 论文中分别报告 internal test 与 challenge holdout，不计算混合平均。

## 当前冻结实例

- 目录：`student-planner/data/rag/course_challenge_v1/`
- 数据版本：`rag-course-challenge-v1`
- 规模：28 条 query，四门课各 7 条，`full 20 / partial 4 / none 4`
- query types：七类全部覆盖
- 四模式 Top 20 去重候选：842 条 query-chunk pair
- 数据集 SHA-256：`9b3e603a58645929905335e7bf2cf3fb74f0501bfee166e55d412635c711edf5`
- 冻结配置 SHA-256：`8d230372c28545ec33113532c0d704e6f2b4a5551a33dce843c61731afe2d9aa`
- 证据等级：`llm_assisted_unreviewed`
- 人工复核状态：`not_reviewed`

候选池构造使用本地 hash embedding 和 local-feature rerank，只为扩大待判定候选覆盖，不属于正式在线结果。`candidate_pool.jsonl` 保留检索来源供审计；`blind_query_review.tsv`、`blind_qrel_review.tsv`、`blind_judge_input.jsonl` 隐藏 mode、rank、score、source 和现有标签；`review_key.json` 与盲审文件分离。

验证：

```bash
py -3.12 scripts/validate_course_rag_challenge.py --challenge-dataset data/rag/course_challenge_v1/challenge_queries.jsonl --challenge-manifest data/rag/course_challenge_v1/challenge_manifest.json
```

当前只完成冻结与合同验证，没有运行 challenge 正式指标，也没有完成人工抽查。

## 两阶段正式入口

正式运行使用单一入口：

```bash
.\.venv-native\Scripts\python.exe scripts/run_course_rag_benchmark_v2.py --formal --output-root output/rag/course_v2_formal
```

该环境已通过课程切块依赖导入、`chromadb 1.5.9` native probe 和 benchmark 核心合同测试。

执行顺序固定：

1. `main/development` 校准四种模式各自的 evidence gate；
2. 写出并 hash 绑定 `main/frozen_gate_config.json`；
3. `main/test` 使用相同 run 中的冻结 gate；
4. challenge runner 验证主集 run、gate bundle、challenge manifest、模型、检索合同和当前 Git commit；
5. challenge 只读取 `split=holdout`，直接应用 frozen gate，不再校准；
6. `challenge/` 单独输出 holdout 指标、置信区间、配对差值和图表数据；
7. 根 `benchmark_manifest.json` 绑定 main/challenge 两个 run manifest。

正式模式禁止 dirty Git、非空输出目录、缺失真实在线配置、Reranker fallback、Embedding fallback 和 Vector Store fallback。当前仓库仍是 dirty 工作区，因此预检会在在线调用前退出；不得为了绕过预检而关闭 `--formal` 运行仓库内这 28 题。
