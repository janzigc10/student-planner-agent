# Agent Execution Loop V1 设计

## 状态

Accepted. 用户已确认下一阶段从“继续调 prompt”切到“Agent 执行闭环 V1”，目标是把计划、确认、工具执行、数据库结果和最终回复拉成可验证闭环。

## 背景

当前 Agent 已经能完成登录、课表导入、任务创建、复习计划拆解等 MVP 流程，但真实 QA 暴露出几个核心问题：

1. 课表周次真值不稳定，离散奇偶周会被压成连续全周，导致日历、查课和提醒都可能错误。
2. 任务更新和提醒更新会分叉，Agent 可以把任务时间改了，但提醒仍停留在旧时间。
3. `ask_user` 确认和纯文本确认混用，用户说“确认”时，系统有时重新让 LLM 猜上下文。
4. 工具结果多为自然语言或局部字段，最终回复可以声称“全部完成”，但数据库未必完全完成。

V1 不追求做一个复杂 Agent 框架；它只收敛当前产品最关键的确定性闭环。

## 目标

1. LLM 负责理解和计划，代码负责校验、状态、执行和结果汇总。
2. 课表有效周判断有统一来源，日历、查课、空闲时间和课程提醒必须一致。
3. 任务创建、任务修改和提醒更新在 Agent 工具层保持一体化。
4. 批量计划创建必须能返回结构化结果，说明 created / updated / skipped / errors。
5. 回归测试覆盖真实 QA 中暴露的核心问题。

## 非目标

1. 不在本轮实现 OCR-first 课表图片导入；该 spec 保留。
2. 不重写前端聊天 UI。
3. 不引入独立工作流引擎或复杂持久化状态机。
4. 不把语义意图硬编码成大量关键词规则；语义仍交给 LLM，代码只做可验证执行边界。

## 方案

### 1. 课程有效周服务

新增后端服务：

`student-planner/app/services/course_occurrence.py`

职责：

- 从 `week_start` / `week_end` / `week_pattern` / `week_text` 计算有效周。
- 支持连续周、单周、双周、离散周文本。
- 提供 `course_occurs_on_date(course, target_date, semester_start)`。
- 提供 `next_course_occurrence(course, semester_start, now)` 给课程提醒使用。

第一版不新增数据库字段，优先从已有字段推导 `active_weeks`。如果后续需要完整保留混合离散周，再加 schema。

### 2. 课表解析保留周次语义

`schedule_parser` 和 agent 工具层应避免把原始 `3,5,7,9,11,13,15,17周` 覆盖成 `第3-17周/all`。

V1 规则：

- 如果数字列表全是奇数，归一化为 `week_pattern=odd`。
- 如果数字列表全是偶数，归一化为 `week_pattern=even`。
- 原始 `week_text` 尽量保留。
- 补充学期总周数时，只裁剪越界周，不覆盖有意义的 `week_text`。

### 3. 任务提醒一体化工具能力

HTTP `/api/tasks/` 已支持 `reminder_advance_minutes`，但 Agent `create_task` / `update_task` 工具层尚未完全同步。V1 要求：

- `create_task` 工具可接收 `reminder_advance_minutes`，在同一工具结果里返回 task 和 reminder。
- `update_task` 工具可接收 `reminder_advance_minutes`，同步更新或删除旧 reminder。
- 只改任务时间但未显式改提醒时，已有 reminder 跟随任务新时间重算。
- 工具返回结构中明确 `task`、`reminders`、`created`、`updated`、`deleted`、`errors`。

### 4. 批量执行结果结构化

复习计划确认后批量创建任务时，后续应逐步收敛为一个可验证批处理工具。V1 的最低要求是先让单任务工具结果稳定，测试覆盖 Agent 多轮能正确使用返回的 task id 和 reminder 状态。

后续 V1.1 可新增：

`batch_create_tasks`

用于一次性创建复习计划，返回每条任务和提醒的执行结果。

### 5. 测试

后端定向测试必须覆盖：

- 离散奇数周解析成 odd pattern。
- 有效周服务能过滤第 14 周的奇数周课程。
- 课程提醒只找真实下一次上课日期。
- Agent 工具创建任务时可同步创建 reminder。
- Agent 工具修改任务时间和 `reminder_advance_minutes` 时同步更新 reminder。
- Agent loop 在“确认 -> create/update -> final response”路径中拿到结构化工具结果。

## 验收标准

1. 导入 `3,5,7,9,11,13,15,17周` 课程后，第 14 周日历/空闲时间/查课不应显示该课程。
2. 课程 reminder 不应为无效教学周创建下一次提醒。
3. Agent 创建带提醒任务后，任务和 reminder 在数据库中一一对应。
4. Agent 修改任务时间和提前提醒分钟后，旧 reminder 被同步更新。
5. 定向后端测试通过。
6. `progress.md` 记录本轮结果和下一步。

## 风险

1. 仅从 `week_text` 推导离散周有上限，复杂混合周次未来仍可能需要 `active_weeks` 字段。
2. 任务提醒一体化如果只修 Agent 工具，不修 prompt，LLM 仍可能继续拆成 `create_task -> set_reminder`；因此 tools schema 和 prompt 也要同步更新。
3. 前端日历仍有自己的周次判断逻辑，本轮后端先收敛，下一步需要前后端共用或对齐规则。
