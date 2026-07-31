# 课程 RAG Challenge Holdout 落地计划

> 范围：只创建独立 challenge 数据、四模式候选池和审核材料；不运行唯一一次正式 benchmark，不根据 challenge 指标调参。

## Task 1：冻结未见难题

- [x] 审计现有 80 条主集 query，确保 challenge 的 query ID 与文本零重复。
- [x] 为四门课各编写 7 条 challenge query，共 28 条。
- [x] 每门课覆盖 5 条 `full`、1 条 `partial`、1 条 `none`，全局覆盖七种 query type。

## Task 2：实现生成与冻结

- [x] 新增确定性 challenge 生成脚本。
- [x] 冻结检索配置并计算 `frozen_config_sha256`。
- [x] 使用四种模式 Top 20 建立去重候选池，保留可追溯的模式与 rank。
- [x] 生成最低证据等级 `llm_assisted_unreviewed` manifest，不声称人工复核。

## Task 3：生成审核材料

- [x] 写出 `challenge_queries.jsonl`、`challenge_manifest.json`、`frozen_config.json`。
- [x] 写出内部候选池与隐藏 mode/rank/score 的盲审 TSV。
- [x] 写出独立 review key，支持未来单人抽查或双人盲审。

## Task 4：验证与交接

- [x] 运行 challenge validator，确认规模、课程、难题类型、answerability 和零重复合同。
- [x] 补充生成器与盲审包测试并运行 RAG 定向回归。
- [x] 运行 `py_compile`、`git diff --check`，更新 `progress.md` 与 `bugs.md`。
