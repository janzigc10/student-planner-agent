# 课程 RAG 论文基线冻结计划

> 状态：COMPLETE
> 范围：只冻结四门课 synthetic RAG 数据与人工复核入口，不运行正式在线 benchmark，不修改产品功能。
>
> 2026-07-29 后续范围决定：用户因人力限制取消人工复核；已生成盲审包保留为可选归档，数据状态改为 `synthetic_unreviewed`，不再把第二标注者作为 benchmark 前置项。

## Task 1：冻结数据版本

- [x] 将当前四门课 corpus/dataset 从原五门课沿用的 v1 标识升级为 v1.1。
- [x] 重新生成 full corpus、chunks、golden queries 与 manifests。
- [x] 保留 `requires_second_person_review`，不得提前宣称为人工最终 golden set。

## Task 2：生成人工盲审包

- [x] 固定抽取 20 道问题，每门课 5 道，并覆盖 full/partial/none。
- [x] 为每题导出不含原始标签的候选证据，供第二标注者填写 0/1/2 相关度。
- [x] 导出问题可回答性、参考答案和备注的空白标注表。
- [x] 写明标注规则、盲审边界和后续裁决流程。

## Task 3：验证与交接

- [x] 运行 corpus/dataset 校验与 RAG 定向测试。
- [x] 确认正式 `course_v1` 中不存在大学英语资料或标签。
- [x] 更新设计、`progress.md` 与正式 benchmark 前置门槛。
- [x] 运行 `git diff --check` 并记录未 commit/push 状态。
