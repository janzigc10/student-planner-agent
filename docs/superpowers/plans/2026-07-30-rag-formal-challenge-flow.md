# 课程 RAG 主集—Challenge 两阶段正式评测计划

> 目标：主集 development 负责 gate 校准；challenge 只读取冻结 gate 并单独报告。实现阶段只做离线合同测试，不运行仓库内 28 题的正式在线指标。

## Task 1：冻结主集 Gate Bundle

- [x] 主集 evaluator 输出独立 `frozen_gate_config.json`。
- [x] Bundle 记录语料/数据 hash、四种模式、development-only 来源、选中 gate、检索合同和模型合同。
- [x] 主集 run manifest 记录 bundle SHA-256。

## Task 2：Challenge-only Runner

- [x] Challenge runner 验证 challenge manifest、全部 artifact hash 与 pool/qrels 对齐。
- [x] Challenge runner 验证主集 run/bundle、当前 corpus、冻结配置和模型/检索合同一致。
- [x] Challenge 只允许 `split=holdout`，禁止调用 `calibrate_gate()`。
- [x] 独立输出 holdout ranking、bootstrap CI、配对差值、gate、图表数据和 run manifest。

## Task 3：单命令正式编排

- [x] 新增主集后接 challenge 的两阶段入口。
- [x] 正式模式继续要求干净 Git、真实 Embedding/Reranker、四模式、空输出目录和禁止 fallback。
- [x] 根 manifest 同时记录 main/challenge run manifest hash，明确 challenge 未用于调参。

## Task 4：防泄漏测试与交接

- [x] 覆盖冻结 gate 复用、holdout 禁止调参、hash/config/provider 不匹配和输出目录复用。
- [x] 只用临时 synthetic fixture 做离线双阶段 smoke，不读取仓库 28 题指标。
- [x] 运行 RAG 定向回归、`py_compile`、`git diff --check`，更新 README、`progress.md`、`bugs.md`。
