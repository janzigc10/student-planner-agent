# Course RAG Benchmark v2 正式结果

> 运行日期：2026-07-31
>
> 成功运行：formal attempt 2
>
> Git commit：`0c375ebd00db9e75f29de48546fa6a215d4fcb2e`
>
> 结果目录：`student-planner/output/rag/course_v2_formal_attempt2/`

## 1. 证据身份与边界

- 主集：4 门 synthetic 课程、49 份资料、552 chunks、80 queries；development 24 条用于冻结 gate，test 56 条只用于报告。
- 主集 test 已被旧 pilot 暴露，证据状态为 `internal_test_exposed_by_pilot`，不能称为严格未见测试集。
- Challenge：28 条独立 holdout query，四门课各 7 条；证据等级为 `llm_assisted_unreviewed`，未人工复核。
- 正式运行使用 DashScope `text-embedding-v4`、Qwen `qwen3-rerank` 和 Chroma，Embedding、Reranker、Vector Store 均无 fallback。
- Challenge 只复用主集 development 冻结的 gate，未参与调参。
- 所有结论只表示四种检索方案在同一 synthetic 数据合同上的相对表现，不代表真实课程问答准确率或人工相关性判断。

## 2. 排序指标

### 2.1 主集 internal test（56 queries）

| 模式 | Recall@5（95% CI） | MRR（95% CI） | nDCG@10（95% CI） | 完整证据召回@10 | 平均延迟 |
|---|---:|---:|---:|---:|---:|
| Embedding-only | 0.3758 [0.3354, 0.4138] | 0.8988 [0.8155, 0.9644] | 0.8043 [0.7296, 0.8685] | 0.4545 | 197 ms |
| BM25-only | 0.3573 [0.3207, 0.3906] | 0.9167 [0.8333, 0.9821] | 0.7968 [0.7207, 0.8623] | 0.2727 | 57 ms |
| Hybrid RRF | **0.3828** [0.3436, 0.4182] | **0.9286** [0.8571, 0.9821] | **0.8544** [0.7821, 0.9154] | 0.5455 | 260 ms |
| Hybrid + Qwen Rerank | 0.3722 [0.3323, 0.4089] | 0.8929 [0.8125, 0.9556] | 0.7797 [0.7105, 0.8389] | **0.8182** | 1112 ms |

相对 Embedding-only 的 paired bootstrap：

- Hybrid RRF 的 Recall@5 提升 `+0.0071`，95% CI `[+0.0016, +0.0146]`；nDCG@10 提升 `+0.0502`，95% CI `[+0.0245, +0.0812]`。
- Hybrid RRF 的 MRR 差值为 `+0.0298`，95% CI `[0.0000, +0.0685]`，按当前判定规则记为 inconclusive。
- Qwen Rerank 三个排序主指标相对 Embedding-only 均未形成确定提升。

### 2.2 Challenge holdout（28 queries）

| 模式 | Recall@5（95% CI） | MRR（95% CI） | nDCG@10（95% CI） | 完整证据召回@10 | 平均延迟 |
|---|---:|---:|---:|---:|---:|
| Embedding-only | 0.4087 [0.2976, 0.5278] | 0.6131 [0.4702, 0.7500] | 0.4721 [0.3713, 0.5762] | 0.5500 | 229 ms |
| BM25-only | **0.5595** [0.4345, 0.6845] | 0.6905 [0.5534, 0.8214] | **0.5899** [0.4819, 0.6937] | **0.7000** | 67 ms |
| Hybrid RRF | 0.5238 [0.3988, 0.6488] | **0.7381** [0.5891, 0.8690] | 0.5869 [0.4741, 0.7001] | 0.6500 | 293 ms |
| Hybrid + Qwen Rerank | 0.4722 [0.3651, 0.5794] | 0.7292 [0.5804, 0.8661] | 0.5588 [0.4521, 0.6606] | **0.7000** | 1121 ms |

相对 Embedding-only 的 paired bootstrap：

- BM25-only 的 Recall@5 提升 `+0.1508`，95% CI `[+0.0893, +0.2163]`；nDCG@10 提升 `+0.1178`，95% CI `[+0.0546, +0.1893]`。
- Hybrid RRF 的 Recall@5、MRR、nDCG@10 分别提升 `+0.1151`、`+0.1250`、`+0.1148`，三个 95% CI 均不跨 0。
- Qwen Rerank 的 nDCG@10 提升 `+0.0867`，95% CI `[+0.0110, +0.1623]`；Recall@5 与 MRR 的差异仍不确定。

## 3. 冻结 Gate 结果

| 数据 | 模式 | Macro-F1 | False accept rate | 资料不足召回 | Full answer recall |
|---|---|---:|---:|---:|---:|
| Main test | Embedding-only | **0.9683** | 0.0000 | 1.0000 | **0.9787** |
| Main test | BM25-only | 0.9391 | 0.0000 | 1.0000 | 0.9574 |
| Main test | Hybrid RRF | 0.9121 | 0.0000 | 1.0000 | 0.9362 |
| Main test | Hybrid + Qwen Rerank | **0.9683** | 0.0000 | 1.0000 | **0.9787** |
| Challenge | Embedding-only | **0.7418** | 0.0000 | 1.0000 | **0.6500** |
| Challenge | BM25-only | **0.7418** | 0.0000 | 1.0000 | **0.6500** |
| Challenge | Hybrid RRF | 0.6748 | 0.0000 | 1.0000 | 0.5500 |
| Challenge | Hybrid + Qwen Rerank | **0.7418** | 0.0000 | 1.0000 | **0.6500** |

冻结 gate 在两个报告集上都保持 `false_accept_rate=0` 和 `insufficient_recall=1`，说明当前策略偏保守；代价是 challenge 的 full answer recall 只有 0.55～0.65。

## 4. 论文结论建议

1. 主检索方案选 Hybrid RRF 最有证据：它在主集拿到最高三项排序指标，在独立 challenge 上对 Embedding-only 的 Recall@5、MRR、nDCG@10 都有 paired bootstrap 支持。
2. BM25 不是可删除的旧基线：它在 challenge 的 Recall@5 和 nDCG@10 最优、延迟最低，说明课程资料中的术语和实体精确匹配很重要。
3. Qwen Rerank 应作为“高成本完整证据增强”而不是默认赢家：它在完整证据召回上更强，但没有稳定赢得排序指标，平均延迟约 1.1 秒。
4. 路由与资料充分性 gate 仍值得保留为独立对比层：四种检索模式都实现零 false accept，但 full answer recall 明显下降，可以形成“安全拒答与覆盖率”的权衡分析。

## 5. 审计链

- 根 manifest：`student-planner/output/rag/course_v2_formal_attempt2/benchmark_manifest.json`
- 主集：`main/summary.json`、`main/confidence_intervals.json`、`main/paired_comparisons.csv`、`main/frozen_gate_config.json`、`main/run_manifest.json`
- Challenge：`challenge/summary.json`、`challenge/confidence_intervals.json`、`challenge/paired_comparisons.csv`、`challenge/gate_predictions.jsonl`、`challenge/run_manifest.json`
- 根 manifest 验证结果：main run、frozen gate、challenge run 三个 SHA-256 均匹配。
- 成功运行总时长约 214 秒；bootstrap 为 2000 次，seed 为 `20260730`。

## 6. 失败 attempt 的保留说明

attempt 1 位于 `student-planner/output/rag/course_v2_formal/`，只完成主集；challenge 在读取前因 tracked Chroma 缓存污染 Git 而终止。失败根 manifest 为 `course_v2_formal.failed_run.json`，对应 SQLite 变化保存在 stash 对象 `1da5bd5648f07cf7fa2eb3fd21019208e7156ed9`。attempt 1 不进入论文结果，只作为基础设施失败审计证据。
