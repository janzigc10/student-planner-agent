# Student Planner - 项目上下文

## 这是什么项目
AI 驱动的学生时间规划 Agent，核心功能：课前提醒 + AI 任务拆解。  
技术栈：FastAPI + React PWA + 国产 LLM（OpenAI 兼容接口）。

## 关键文件（每次新 session 必读）
1. **本文件** - 项目上下文和当前进度
2. `docs/superpowers/specs/2026-03-29-student-time-planner-design.md` - 完整设计文档
3. `docs/superpowers/plans/2026-03-29-plan1-backend-foundation.md` - Plan 1: 后端基础
4. `docs/superpowers/plans/2026-03-29-plan2-agent-core.md` - Plan 2: Agent 核心
5. `docs/superpowers/plans/2026-03-30-plan3-schedule-import.md` - Plan 3: 课表导入
6. `docs/superpowers/plans/2026-03-30-plan4-memory-context.md` - Plan 4: Memory + 上下文管理
7. `docs/superpowers/plans/2026-03-30-plan5-push-notifications.md` - Plan 5: 推送系统
8. `docs/superpowers/specs/2026-03-30-frontend-pwa-design.md` - 前端 PWA 设计
9. `docs/superpowers/plans/2026-03-30-plan6-frontend-pwa.md` - Plan 6: 前端 PWA
10. `docs/superpowers/plans/2026-04-18-plan7-frontend-ui-modernization.md` - Plan 7: 前端 UI 现代化重构

## 当前进度
- [x] Plan 1: 后端基础（9 个 task）
- [x] Plan 2: Agent 核心（10 个 task）
- [x] Plan 3: 课表导入（9 个 task）
- [x] Plan 4: Memory + 上下文管理（10 个 task）
- [x] Plan 5: 推送系统（9 个 task）
- [x] Plan 6: 前端 PWA（7 个 task）
- [x] Plan 7: 前端 UI 现代化重构（5 个 task）

## 当前正在执行
**下一优先级：Plan 7 已完成，进入视觉细节验收与交互微调（动效节奏、触控命中、文案密度）。**
（每完成一个 task，更新这里指向下一个 task）

## 交接摘要（2026-04-17）
- 已完成：
  - 课表节次追问改为自然聊天输入（无结构化 `data/options` 的 `review` 不再渲染确认卡片按钮）。
  - 修复确认卡片“点确认后看似卡住”：WebSocket 重连新会话时前端清理旧 `pendingAsk`，后端对“非等待态 answer”返回明确错误提示。
  - 修复 `schedule_parser` 回归：不再把 `1-16周` 误当节次覆盖 period；修复空行分块导致“操场”被识别为新课程的问题。
  - 完成附件链路最终回归与真实浏览器 smoke 验证（两图待发送、移除、混发拦截、合法批次发送后进入确认卡片）。
  - 完成日历页联调收口：顶部 `+` 与任务弹层联动、月视图按天选择回填日期并触发当日数据重载。
  - 修复日历“前一天/后一天”日期跳转异常：根因是前端 `toISOString()` 的 UTC 截断导致时区偏移（在 Asia/Shanghai 表现为“后一天不变、前一天跳两天”）；已改为本地日期格式化。
  - 补充日历回归测试：新增 store 层 `shiftDate(+/-1)` 单测与页面层“前一天/后一天仅跳 1 天”集成测试。
  - 开发环境补充 Service Worker 清理：`main.tsx` 在非生产模式自动注销已注册 SW，避免 IAB 命中旧缓存导致“修复未生效”的假象。
- 关键提交：
  - `20f6412` - `feat: stabilize schedule import chat workflow`
  - `99d0ff2` - `fix: restore period parsing and course block grouping`
- 本轮验证：
  - `py -3.12 -m pytest tests/test_schedule_parser.py tests/test_schedule_import_api.py tests/test_agent_loop.py tests/test_chat_ws.py -q`（31 passed）
  - `npm --prefix frontend run test -- src/pages/ChatPage.test.tsx src/stores/chatStore.test.ts`（17 passed）
  - `py -3.12 -m pytest tests/test_schedule_import_api.py tests/test_schedule_integration.py tests/test_chat_ws.py -v`（15 passed）
  - `npm --prefix frontend test -- src/pages/ChatPage.test.tsx src/stores/chatStore.test.ts`（17 passed）
  - `npm --prefix frontend run build`（PASS）
  - `npm --prefix frontend test -- src/App.test.tsx src/stores/calendarStore.test.ts src/pages/CalendarPage.test.tsx`（6 passed）
  - `npm --prefix frontend run build`（PASS）
  - `npm --prefix frontend test -- src/stores/calendarStore.test.ts`（3 passed）
  - `npm --prefix frontend test -- src/pages/CalendarPage.test.tsx src/stores/calendarStore.test.ts`（6 passed）
  - `npm --prefix frontend test -- src/pages/CalendarPage.test.tsx src/App.test.tsx src/stores/calendarStore.test.ts`（9 passed）
  - `npm --prefix frontend run build`（PASS）

## 交接补充（2026-04-18）

### 本 session 已解决
1. 多轮对话“你继续”循环（高优先级）已修复：
   - `list_courses` 压缩结果改为可执行结构化候选，固定前缀 `[TOOL_SUMMARY:list_courses:v1]`。
   - 候选字段包含：`id/name/location/weekday/start_time/end_time`。
   - 采用稳定排序，并显式输出 `truncated/omitted_groups/omitted_options`，避免“前 5 条同名”摘要偏差。
2. 跨轮工具上下文可恢复：
   - 工具结果摘要以 `assistant` 压缩消息持久化（`is_compressed=True`），不直接持久化 `role=tool`，规避 `tool_call_id` 链路风险。
   - 第二轮用户仅输入“你继续”时，可复用上一轮 `list_courses` 候选推进到 `delete_course`。
3. 回归测试已补齐并通过：
   - 新增/更新 `tests/test_context_compressor.py`：结构化摘要字段、稳定排序、截断标记验证。
   - 新增 `tests/test_agent_loop.py::test_continue_message_can_reuse_persisted_list_course_summary`。

### 本 session 关键提交
- `787440c` - `fix: persist actionable course summaries across chat turns`

### 本 session 关键验证
- `py -3.12 -m pytest tests/test_context_compressor.py tests/test_agent_loop.py tests/test_chat_ws.py -q`（18 passed）

## 交接补充（2026-04-18，UI 现代化）

### 本 session 已解决
1. 完成 Plan 7（前端 UI 现代化重构）正式落地：
   - 新增 `docs/superpowers/plans/2026-04-18-plan7-frontend-ui-modernization.md`，并按 step 全量勾选完成。
2. 建立统一前端设计系统底座：
   - `frontend/src/index.css` 重构为 token 驱动（颜色、层级、圆角、阴影、动效时序、字体链）。
   - 增加 `prefers-reduced-motion` 降级策略，保证动效可访问。
3. 全站图标统一矢量化（去 emoji）：
   - 新增 `frontend/src/components/icons.tsx`，并替换 Shell/Chat/Calendar/Me/Courses/Preferences/Notifications 页面图标。
4. 全量页面视觉统一完成：
   - 主三页（聊天/日历/我的）与登录注册、课表管理、偏好设置、通知设置统一到同一视觉语法。
5. TDD 回归约束补齐：
   - 新增 `frontend/src/components/AppShell.test.tsx`（tab 使用 SVG 且不含 emoji）。
   - 补充 `frontend/src/pages/CalendarPage.test.tsx` 的无 emoji 前缀断言。

### 本 session 关键验证
- `npm --prefix D:\student_time_plan\student-planner\frontend test -- src/components/AppShell.test.tsx src/pages/CalendarPage.test.tsx`（5 passed）
- `npm --prefix D:\student_time_plan\student-planner\frontend test -- src/App.test.tsx src/pages/ChatPage.test.tsx src/pages/CalendarPage.test.tsx src/stores/chatStore.test.ts src/stores/calendarStore.test.ts`（27 passed）
- `npm --prefix D:\student_time_plan\student-planner\frontend test`（30 passed）
- `npm --prefix D:\student_time_plan\student-planner\frontend run build`（PASS）

## 规则
- 严格按 plan 文件中的 step 顺序执行
- 每完成一个 step，在 plan 文件中把 `- [ ]` 改成 `- [x]`
- 每完成一个 task，更新本文件的“当前正在执行”
- 遇到问题记录到下面的“问题记录”区域，不要自己改设计
- 测试必须通过才能进入下一个 task

## 问题记录
- 2026-03-29: 当前环境没有 `python` / `py` 命令，执行 Plan 中的 Python、pip、pytest 命令时需要改用 `C:\Users\Chen\anaconda3\python.exe`。
- 2026-03-29: `apply_patch` 在嵌套目录下落盘失败，当前改用 PowerShell 写文件继续执行；未改变设计或文件内容目标。
- 2026-03-29: PowerShell 默认 UTF-8 with BOM 会导致 `pyproject.toml` 解析失败，后续写文件统一改为 UTF-8 without BOM。
- 2026-03-29: `pip install -e '.[dev]'` 在当前 Anaconda 基础环境中提示 `pyasn1-modules` 与新装 `pyasn1` 版本冲突；Plan 1 已完成，但需要后续关注环境隔离。
- 2026-03-29: 首次 commit 因仓库缺少 git 用户名 / 邮箱失败，已在本仓库本地配置 `user.name=Codex`、`user.email=codex@local.invalid` 后继续执行。
- 2026-03-29: FastAPI 当前版本下 `/api/auth/me` 无 token 的默认行为与计划测试预期不一致，已在认证依赖中显式处理为 `403 Not authenticated` 以匹配计划。
- 2026-03-29: `pytest` 生成的 `student-planner/.pytest_cache` 目录当前权限异常，git 状态会给出访问警告，但未阻塞 Plan 1 完成。
- 2026-03-29: 早期用全文替换勾选 commit step 时误影响了后续 task 的同名 step，现已改为按 task 区段精确更新。
- 2026-03-29: Task 4 提交时混入了 `__pycache__/*.pyc` 运行产物，Task 5 已新增 `.gitignore` 并将这些文件从版本控制中移除。
- 2026-03-29: 当前账户对 `D:\student_time_plan` 仓库触发 git `dubious ownership` 安全检查，Task 1 提交前需要先将该目录加入 git `safe.directory`。
- 2026-03-30: Plan 3 / Task 2 添加 `openpyxl` 依赖时，`pip install -e '.[dev]'` 因 setuptools 将 `app` 与 `alembic` 同时识别为顶层包而失败；当前环境已存在 `openpyxl 3.1.2`，因此先继续执行 parser 开发，后续需要单独修复打包配置。
- 2026-04-13: 当前 PATH 上的 `python` 是 3.8.10；项目后端测试改用 `py -3.12 -m pytest`。
- 2026-04-13: Plan 6 / Task 1 使用 `py -3.12 -m pip install -e ".[dev]"` 时仍复现 setuptools 顶层包冲突；已改为安装 pyproject 中的直接依赖和测试依赖来继续验证。
- 2026-04-13: Python 3.12 环境缺少既有 LLM client 所需 `openai` 包，Plan 6 / Task 1 已补入 `pyproject.toml`；`passlib[bcrypt]` 拉到 `bcrypt 5.0.0` 会导致认证测试失败，已 pin `bcrypt<5`。
- 2026-04-17: WebSocket 重连后会话切换导致旧确认卡片可见但 answer 落到新会话，出现“已选择确认但流程不继续”。已修复：前端在 `connected` 事件清理 `pendingAsk`，后端在非等待态收到 `answer` 返回明确错误事件，避免静默吞包。
- 2026-04-17: `schedule_parser` 曾将周次（如 `1-16周`）误识别为节次并覆盖 `period`，且空行分块会把“操场”误识别为独立课程。已修复并补回归测试。
- 2026-04-17: Final regression（`tests/test_schedule_integration.py`）暴露 `DEFAULT_SCHEDULE` 回归导入错误。已在 `app/services/period_converter.py` 恢复兼容常量并补齐分隔符归一化（`—/–/〞/每`）。
- 2026-04-17: 附件 smoke 中，合法课表文件发送后会先进入“节次作息追问”，补全作息后再出现确认卡片；与“自然聊天追问”改造一致，非卡死。
- 2026-04-17: 日历页“单双周显示未生效”问题已在后续 session 修复：日历渲染已结合 `current_semester_start` 计算教学周奇偶，并联合课程周次字段完成过滤。
- 2026-04-18: 多轮聊天在“先 `list_courses` 再精确删除”的场景出现“你继续”循环（重复口头回复、不推进工具）。已修复：`list_courses` 压缩改为可执行候选结构化摘要 + 跨轮持久化工具摘要。
- 2026-04-18: 当前环境 `rg.exe` 无法执行（Access is denied），本 session 前端检索改用 PowerShell `Get-ChildItem + Select-String` 替代；未影响功能设计与实现。

## 当前正在执行（2026-04-18 晚间更新）
**下一优先级：Chat 确认后空窗衔接优化（后续 session 处理）。**
- 目标：在不破坏当前稳定链路的前提下，提升“确认 -> 下一步处理”的连续感。
- 状态：本 session 先冻结在稳定版，延期到后续 session 继续。

## 交接补充（2026-04-18，UI 会话晚间补充）

### 本 session 已完成
1. Chat 输入区交互统一为图标模式：
   - 无输入且无待发附件时右侧显示 `+`（添加附件）。
   - 有文字或附件时右侧切换为发送图标。
   - 语音入口统一为图标按钮（不显示文字标签）。
2. Chat 时间线层级修复：
   - 进度卡与确认卡按 anchor 固定在对应消息后。
   - 新用户消息与后续 assistant 回复均渲染在卡片下方，避免“插入到卡片上方”的错位。
3. 课表确认卡可读性升级：
   - `review` 数据优先渲染为课程卡片和键值详情，不再直接输出 JSON 原文块。
4. “确认卡片/处理卡片”链路稳定化：
   - `ask_user` 到达即收起处理卡并展示确认卡。
   - 已根据用户反馈回退到稳定版本：确认后仅显示“已选择：xxx”，下一次 `tool_call` 才重新出现处理卡。
5. 工程稳定性修复：
   - 修复本地撤销导致 `ChatPage.tsx` 混入冲突标记（`<<<<<<< / ======= / >>>>>>>`）并恢复可编译状态。

### 本 session 关键验证
- `npm --prefix student-planner/frontend test -- src/pages/ChatPage.test.tsx src/stores/chatStore.test.ts`（33 passed）
- `npm --prefix student-planner/frontend test`（51 passed）
- `npm --prefix student-planner/frontend run build`（PASS）

### 留到后续 session 的待解决问题
- Chat 在“点击确认后 -> 后端下一次 tool_call 前”的短暂空窗衔接仍可继续优化。
- 当前决策：保持稳定版（仅显示“已选择”），后续再设计不突兀的轻量过渡方案，避免处理卡与确认卡并存、闪烁或文案突兀。

## 问题记录（晚间补充）
- 2026-04-18: IAB/本地撤销可能把 `ChatPage.tsx` 写入 Git 冲突标记，导致前端编译失败。已恢复并补测通过；后续若再次出现，优先全局检索 `<<<<<<<|=======|>>>>>>>`。