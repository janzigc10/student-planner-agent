# Course Maintenance Agent Loop V1 设计

## 状态

Accepted. 用户已确认下一步从继续扩任务拆解，切到课表真值维护：课程纠错、合并和删除。

## 背景

Plan 14 和主动重排 V1 已经把短中期任务拆解推进到可确认、可写库、可重排的闭环。但这些能力依赖一个前提：课表数据必须可信。

真实课表截图 OCR 已确认存在质量问题：课程名可能被拆裂，周几可能左移，重复或错误课程可能进入数据库。继续扩更复杂的规划能力前，应先补上用户可低成本修正课表的 Agent Loop。

当前已有基础：

- `list_courses`、`update_course`、`delete_course` 工具已存在。
- Agent prompt 已要求课程纠错先查当前课表，再确认后修改。
- `loop.py` 已有一个本地 course merge shortcut，但主要覆盖“同一时段/地点/周次的重复课程合并”，对单纯改名、明确删除、OCR 拆裂后的用户话术覆盖不足。

## 目标

1. 课程纠错：用户说“把 A 改成 B”时，先 `list_courses`，定位已有课程，review 确认后调用 `update_course`。
2. 重复合并：用户说“把 A 和 B 合并/优化成一门课”时，先 `list_courses`，生成保留/删除方案，review 确认后调用 `update_course` 和/或 `delete_course`。
3. 错课删除：用户说“删掉 A / 删除识别错的 A”时，先 `list_courses`，review 确认后调用 `delete_course`。
4. 所有写操作都必须先 `ask_user` review/confirm；未确认不落库。
5. 找不到唯一目标时不乱改，给出需要用户补充课程名或时段的提示。
6. 补后端回归和 live E2E，证明真实浏览器路径可落库并输出 evidence JSON。

## 非目标

1. 不重做 OCR 模型、prompt 或视觉解析策略。
2. 不实现课表确认卡内的可视化编辑器。
3. 不做复杂相似度/机器学习匹配，只做可解释的名称包含、明确映射和同槽位重复合并。
4. 不自动合并不同周次、不同地点、不同时间的课程，除非用户明确指定并确认。
5. 不新增多 Agent。

## 方案

### 1. 统一 Course Maintenance shortcut

在 `run_agent_loop` 前置本地确定性分支，覆盖课程维护请求：

- 改名：识别“把 X 改成 Y / X 改名 Y / X 统一成 Y”。
- 删除：识别“删掉 X / 删除 X / 去掉 X”。
- 合并：复用并扩展现有合并 shortcut。

触发后统一流程：

1. 调用 `list_courses`。
2. 根据用户文本匹配课程。
3. 生成结构化 maintenance plan。
4. `ask_user(type=review)` 展示将要修改/删除的课程。
5. 用户确认后执行 `update_course` / `delete_course`。
6. 保存工具摘要和 AgentLog，最终回复明确完成了哪些动作。

### 2. 匹配规则

V1 只使用可解释规则：

- 精确包含：用户文本中出现已有课程名。
- 改名映射：从“把 X 改成 Y / 把 X 统一成 Y / X 改名为 Y”抽取 `old_name -> new_name`。
- 删除目标：从“删掉/删除/去掉 X”抽取 `target_name`。
- 合并目标：用户文本中出现多个课程名时，只处理同一 weekday/start/end/location/week_start/week_end/week_pattern 的重复槽位。

如果匹配到 0 条，提示用户补充课程名；如果匹配到多条且无法确认唯一目标，提示用户补充时段或地点。

### 3. 写入策略

- 改名：对匹配目标逐条 `update_course(course_id, name=new_name)`。
- 删除：对匹配目标逐条 `delete_course(course_id)`。
- 合并：优先保留 canonical name 对应记录；必要时先 rename keeper，再 delete 重复记录。
- 不跨时间/周次合并，避免误删真实不同课程。

### 4. 测试与 E2E

后端回归：

- 改名 shortcut 不调用 LLM，走 `list_courses -> ask_user -> update_course`。
- 删除 shortcut 不调用 LLM，走 `list_courses -> ask_user -> delete_course`。
- 合并 shortcut 继续保留周次边界，不合并 odd/even 不同记录。
- 找不到目标时不落库。

Live E2E：

- 预置 OCR 错课和正确课。
- 用户发送课程维护话术。
- 断言工具序列、DB 课程结果和最终文本。
- 输出 evidence JSON 到 `output/playwright`。

## 验收标准

1. 设计和执行计划文档存在，并明确 OCR 算法不在本轮范围内。
2. 课程改名、删除、合并都能先 review 再落库。
3. 后端定向回归通过。
4. 前端 typecheck 通过。
5. 沙箱外 live E2E 至少覆盖一条课程维护真实浏览器链路。
6. `progress.md` 记录完成内容、验证命令和剩余边界。
