# Course RAG v1.1 第二标注者盲审说明

> 2026-07-29 范围决定：因人力限制，本轮不执行人工盲审。本文件和导出 TSV 仅作为可选归档，不再阻塞正式 synthetic 四模式消融，也不得据此宣称数据经过人工复核。

## 目标

这次复核不是重新评价模型，而是检查当前 synthetic golden set 的问题可回答性和 chunk 相关度是否可信。标注者只能使用导出的盲审包，不查看 `golden_queries.jsonl`、旧在线评测结果或生成器中的原始标签。

盲审包位于：

- `student-planner/data/rag/review/course_v1_1/query_review.tsv`
- `student-planner/data/rag/review/course_v1_1/qrel_review.tsv`
- `student-planner/data/rag/review/course_v1_1/review_manifest.json`

两个 TSV 使用 UTF-8 BOM，可直接用 Excel、WPS 或文本编辑器打开。

## 标注顺序

1. 在 `query_review.tsv` 填写 `reviewer_id` 和 `review_date`。
2. 对照同一 `review_id` 在 `qrel_review.tsv` 中的 12 个候选证据。
3. 先为每个候选填写 `review_relevance`。
4. 再回到 `query_review.tsv` 判断整体 `review_answerability`。
5. 填写能够由证据支持的 `review_reference_answer`、关键词和必要备注。

## Chunk 相关度

`review_relevance` 只能填写：

- `2`：直接回答问题的核心部分，可作为主要答案证据。
- `1`：只支持局部信息、背景、条件或例子，单独不足以完整回答。
- `0`：不支持该问题；只有主题词重叠、通用模板或容易误导的内容也标为 0。

不要因为材料“看起来像同一门课”就给 1。相关度必须针对当前问题判断。

## 问题可回答性

`review_answerability` 只能填写：

- `full`：候选证据合起来足以形成完整、可靠的回答。
- `partial`：只能回答其中一部分，仍缺少问题要求的关键事实、比较项或条件。
- `none`：没有足够证据可靠回答，系统应拒答。

判断可回答性时以资料为边界，不使用个人常识补全。

## 参考答案与关键词

- `review_reference_answer`：只写候选证据能够支持的内容；`none` 可留空。
- `review_expected_terms`：填写答案中应出现的核心词，多个词使用 `|` 分隔。
- `review_notes`：记录歧义、资料重复、模板噪声、候选缺失或无法裁决的原因。

## 盲审与裁决

- 标注过程中不得查看已有 `answerability`、`reference_answer` 或 qrels relevance。
- 不修改原始 corpus、golden queries 或 review manifest。
- 完成后保留两份已填写 TSV，由项目维护者与现有标签比较。
- 分歧项必须逐条裁决；裁决前不得把数据集状态改为人工最终 golden set。
- 正式四模式 benchmark 只能在裁决完成、数据版本和 Git 基线冻结后运行。
