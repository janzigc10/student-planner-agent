# 课程 RAG Benchmark v2 落地计划

> 目标：保留现有四模式检索与四门课 synthetic 主集，升级评测协议、统计、正式运行门槛、challenge holdout 和答案层输出合同。本计划不执行唯一一次正式在线 benchmark，不修改产品功能。

## Task 1：冻结 v2 合同

- [x] 审计当前 evaluator、dataset/qrels、dev/test、输出与正式运行门槛。
- [x] 明确受控 synthetic 主集、internal test 暴露边界和 challenge holdout 证据等级。
- [x] 冻结检索指标、答案指标、统计方法、图表与正式运行门槛。

## Task 2：修正检索汇总与统计

- [x] development/test 分离汇总，主表与图表只读取 test。
- [x] 增加主指标 bootstrap 95% CI。
- [x] 增加相对 Embedding-only 的逐 query 配对 bootstrap 差值。
- [x] 输出 v2 summary、CI、paired comparison 和分组图表 CSV。

## Task 3：实现正式运行合同

- [x] 增加显式 `--formal`。
- [x] 正式模式拒绝 dirty Git、非空输出目录、fallback、非完整四模式和缺失在线配置。
- [x] run/failure manifest 升级为 v2，并记录统计、运行环境和证据等级。

## Task 4：增加 challenge holdout 合同

- [x] 定义 challenge manifest、query 去重、冻结 split 和证据等级校验。
- [x] 增加独立 validator/入口。
- [x] 补齐 challenge contract 测试；不在本计划中伪造人工审核状态。

## Task 5：增加答案层评测合同

- [x] 定义 answer run 与 judgment schema。
- [x] 汇总 citation、support、nugget、refusal 和 completeness 指标。
- [x] 输出答案层 JSON/CSV 与图表数据。
- [x] 补齐答案层合同与汇总测试。

## Task 6：验证与交接

- [x] 运行 v2 定向测试和现有 RAG 相关回归。
- [x] 验证当前四门课 corpus/dataset。
- [x] 运行 `py_compile` 与 `git diff --check`。
- [x] 更新 `progress.md`、`bugs.md` 和运行说明。
