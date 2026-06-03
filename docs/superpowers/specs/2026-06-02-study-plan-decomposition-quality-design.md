# Study Plan Decomposition Quality 设计

## 状态

Accepted. 用户已明确把“任务拆解优化”交给本轮执行，范围包括落文档、写代码和完整 E2E 测试。

## 背景

当前学习计划链路已经能完成 `get_free_slots -> create_study_plan -> review -> create_task` 的确认写入闭环。上一轮 live E2E 证明它能把 2026-06-11 的大学英语3考试拆成多条复习任务并写入日程。

剩余问题不是“不会写库”，而是“拆解质量偏模板化”：在用户只给课程和考试日期时，系统会按空闲时间平均铺任务，但不会主动收集考试范围、薄弱点、目标成绩、每日最大可学习时长等决定复习计划质量的变量。这会让计划看起来可执行，但个性化和学习策略不足。

## 目标

1. 完整考试请求在生成计划前，至少补一次学习计划 intake，收集或确认复习范围、薄弱点、目标和每日学习上限。
2. `create_study_plan` 接收结构化 `study_context`，生成器 prompt 必须使用这些信息，而不是只按课程名和空闲时间模板化分配。
3. 计划 review 和最终写入的任务要保留可见质量信息：任务描述应体现范围、薄弱项、练习方式或考前策略。
4. 模糊考试请求仍然先追问考试日期/课程名，不能因为新增 intake 而写入任务。
5. 继续保留确认后确定性逐条 `create_task` 的闭环，不把写库重新交回模型自由发挥。

## 非目标

1. 不引入 BERT、RAG 或多 Agent 调度。
2. 不重写整个 Agent Loop。
3. 不做完整学习诊断系统，也不读取外部教材。
4. 不让 `create_study_plan` 直接写库；它仍然只生成候选计划。
5. 不在默认前端 E2E 中混入 live provider 场景；仍使用专用 `e2e:agent-loop`。

## 方案

### 1. 生成前 intake guard

在 `run_agent_loop` 执行 `create_study_plan` 前增加本地 guard：

- 如果 `tool_args.study_context` 已包含有效信息，则直接放行。
- 如果缺少 `study_context`，但用户已经在本轮文本里提供范围/薄弱项/目标/每日上限，则从文本中构建 `study_context`。
- 如果仍缺少上下文，则由后端发出一次 `ask_user`：
  - 询问复习范围、薄弱点、目标成绩和每日最大可学时长。
  - 告诉用户也可以回复“按默认”，避免卡死。
- 用户回复后，把原始回复和可解析字段写入 `tool_args.study_context`，再继续执行原来的 `create_study_plan`。

这样即使模型过早调用 `create_study_plan`，后端也能把质量问题拦在生成前。

### 2. 结构化 study_context

`create_study_plan` 的 schema 增加可选 `study_context`：

- `exam_scope`: 复习范围，如 Unit1-6、第1-5章、老师划重点。
- `weak_areas`: 薄弱点数组，如听力、写作、阅读、错题。
- `target_score`: 目标成绩或目标等级。
- `daily_study_limit_minutes`: 每日最大复习时长。
- `raw_notes`: 用户原始补充说明。
- `using_defaults`: 用户明确选择按默认安排时为 true。

执行器把该对象传给 `generate_study_plan`。

### 3. 生成 prompt 质量规则

`PLAN_PROMPT` 增加学习上下文区块和约束：

- 有 `exam_scope` 时，任务描述必须明确覆盖该范围。
- 有 `weak_areas` 时，至少安排对应专项任务。
- 有每日上限时，同一天任务总时长不能超过上限。
- 计划要包含“基础覆盖、薄弱突破、综合练习、错题/考前回顾”的节奏，不只是平均铺时间。
- 如果用户选择默认，必须在任务描述中体现合理假设，而不是假装知道具体范围。

### 4. 测试与 E2E

后端回归覆盖：

- `generate_study_plan` prompt 会包含 `study_context`。
- Agent 在 `create_study_plan` 前缺少上下文时会先 ask_user。
- 用户补充范围/薄弱点/每日上限后，`create_study_plan` 收到结构化 `study_context`。
- 确认后仍由本地确定性分支逐条 `create_task`。

Live E2E 覆盖：

- 模糊请求仍只追问信息且不落库。
- 完整考试请求需要先出现学习计划 intake，再按用户补充生成计划。
- 最终 DB 任务不少于 2 条，日期在考试前，描述至少体现用户补充的范围或薄弱点。
- evidence JSON 记录 `toolSequence`、`studyContextHints`、写入任务数量和任务 ID。

## 验收标准

1. 新设计和执行计划文档存在，并与本轮代码一致。
2. `create_study_plan` 工具 schema、执行器和生成器支持 `study_context`。
3. 后端定向测试覆盖 intake guard、context 透传和确认后落库。
4. `npm.cmd run typecheck` 通过。
5. 沙箱外 `npm.cmd run e2e:agent-loop -- --grep "study plan" --reporter=list --global-timeout=420000` 通过，并写出新的 evidence。
6. `progress.md` 记录本轮完成内容、验证命令和下一步边界。
