# Student Planner 链路正确性修复设计

## 目标

修复 2026-07-10 follow-up 审查确认的链路缺口，使“意图路由、确认授权、工具执行、事务提交、trace、RAG 来源和前端展示”描述同一份真实事实。修复不改变数据库 schema、RAG corpus、部署、认证、OCR 或 scheduler 的业务策略。

## 设计原则

1. 写入授权必须来自结构化且精确的计划，不从自然语言问题猜测工具或参数。
2. 用户确认只接受确认卡协议中的明确选择；任何取消语义优先于肯定前缀。
3. `confirmed_write` 表示数据库已经成功提交，而不是进入过写入节点。
4. 数据库事务提交前不得产生不可回滚的 scheduler 副作用。
5. RAG 来源必须对应真正进入模型上下文的证据 chunk。
6. hard route 只拦截明确的实时公共信息；课程资料和概念语境优先进入本地 RAG。

## 组件与数据流

### 1. 结构化确认协议

`ask_user.data` 增加公开的 `planned_operations` 结构：每项包含 `tool_name` 和完整 `args`。工具 schema、系统提示和测试使用同一契约。确认票据深冻结 `planned_tool_names/planned_args`，执行时逐项比对工具、参数 digest、route 和 confirmation id。

`args` 的“完整”以工具 schema 的显式输入为准：模型必须提交用户可见且会影响写入结果的全部字段；schema 默认值由服务端在签发票据前展开。日期和时间统一为工具 schema 当前使用的 ISO 日期、`HH:MM` 时间格式；对象键排序、数组顺序保留，使用 UTF-8、无多余空白的确定性 JSON 计算 SHA-256。签发后不允许模型或运行时修改业务字段。只有签发前的 schema preflight 可以补默认值；冲突重排必须生成新计划、新 digest 和新确认票据。

确认答案使用严格规范化：确认卡只接受完整的 `确认/可以/是/yes/ok` 等明确值；包含取消、否定、暂缓语义的答案一律拒绝。自由文本 review 不再自动授权写入。

### 2. 提交事实与 trace

所有 route-owned state helper 通过统一谓词判断 `confirmed_result.write_status == "committed"`。失败、拒绝、取消、rollback 只保留实际经过的前置节点，不追加 `confirmed_write`。

票据在当前单进程内采用四态：`issued -> consuming -> consumed`，或 `issued/consuming -> rejected`。执行前以 `(user_id, nonce)` 原子 claim 进入 `consuming`；数据库 commit 成功后进入 `consumed`，重复提交永久拒绝。参数不匹配、用户取消和 preflight 失败进入 `rejected`。工具异常或数据库 rollback 释放 claim 并回到 `issued`，允许同一份未经修改的计划重试；任何参数变化必须重新签发。票据随当前 WebSocket generator/state 保存，不跨会话恢复；跨进程持久幂等明确不在本轮范围。

### 3. 数据库与 scheduler 原子边界

批量 handler 在 `_commit=False` 时只写入/flush 数据库并返回待执行的内部 scheduler effects，不立即 schedule/cancel。`execute_tool_batch()` 在数据库 commit 成功后统一执行这些 effects；执行中失败则返回可观察错误。数据库 commit 失败时不执行任何 effect。

单项默认 `_commit=True` 路径保持现有对外行为，但同样在 commit 成功后执行 scheduler effect。`set_reminder` 必须显式遵守 `_commit`。旧计划 shortcut 在 batch rollback 后不得逐条重放；若要重排，必须生成完整新批次并再次确认。

数据库 commit 与 scheduler effect 使用两个独立状态：数据库成功后始终为 `write_status=committed`，因此 trace 可以记录 `confirmed_write`；调度结果另用 `effect_status=committed|failed|not_required`。若 effect 失败，工具结果必须包含稳定错误和失败 effect 列表，前端使用 warning/partial 状态，正文明确“数据已保存但提醒调度失败”，不得渲染完整成功卡。数据库 rollback 时为 `write_status=rolled_back`，且不执行任何 effect。

### 4. RAG 与路由边界

grounding 从 `evidence_hits[:requested_top_k]` 生成，与 `build_rag_context()` 构造模型 context 的集合一致。若没有证据，不展示普通候选 hits。

NO_WEB 判断增加课程语境豁免：包含课件、讲义、课程、老师材料、概念解释等信号时，即使出现“当前/现在 + 法律/政策/利率”，也不进入 hard NO_WEB；明确新闻、天气、汇率现价、比分等请求仍拦截。

### 5. WebSocket 输入契约

顶层 payload 必须是 object；`message`、`answer` 如存在必须是 string。类型错误返回稳定 `invalid_input_type`，保持当前等待中的 generator，不触发 `.strip()` 异常。

## 错误处理

- 缺少或不匹配的 `planned_operations`：拒绝写入并返回 `write_status=rejected`。
- 批量任一数据库操作失败：整体 rollback，计数为 0，不执行 scheduler effects。
- scheduler effect 在 commit 后失败：数据库事实保留，返回明确调度错误并记录失败项，禁止宣称完整成功。
- RAG 来源为空：正文仍按 evidence gate 结果处理，来源区显示空标签或不显示伪来源。

## 验证

1. 真实 schema/prompt 测试证明模型可见 `planned_operations`。
2. 否定句、混合肯定/取消句均不能授权；明确确认仍可写入。
3. schedule/course/plan 的 rejected、cancelled、rollback 均不含 `confirmed_write`。
4. 使用真实数据库 handler 制造批次第二项失败，断言数据库无部分行且 scheduler 未注册/取消任何 job。
5. 旧今晚复习 shortcut 的 batch failure 不再逐条写入。
6. `hits` 与 `evidence_hits` 不同时，grounding 只引用 `evidence_hits`。
7. 法律/政策课程问答进入 RAG，明确实时公共信息仍进入 NO_WEB。
8. WebSocket 对 object/list/number 类型输入返回稳定错误并能继续提交合法回答。
9. 运行目标后端矩阵、前端 Chat/store、typecheck/build、WS smoke；使用独立数据库避免共享 `test.db` 污染。

## 边界

不新增数据库表或迁移，不引入分布式票据存储。跨进程持久幂等作为后续生产化议题保留；本轮保证当前 WebSocket 会话和单进程执行路径 fail-closed、不可重复消费。
