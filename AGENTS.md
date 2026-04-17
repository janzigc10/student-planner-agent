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

## 当前进度
- [x] Plan 1: 后端基础（9 个 task）
- [x] Plan 2: Agent 核心（10 个 task）
- [x] Plan 3: 课表导入（9 个 task）
- [x] Plan 4: Memory + 上下文管理（10 个 task）
- [x] Plan 5: 推送系统（9 个 task）
- [x] Plan 6: 前端 PWA（7 个 task）

## 当前正在执行
**下一优先级：日历页单双周渲染修复（引入学期开始时间并按周次计算单双周）；随后进行前端 UI 系统与视觉优化。**
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
- 2026-04-17: 日历页当前仍存在“单双周显示未生效”：虽然课表解析已能识别单双周，但日历渲染仅按 `weekday` 过滤，尚未结合“学期开始时间”计算当前教学周奇偶并过滤课程；下个 session 需先补齐学期起始日期来源与周次计算，再完成前后端联调与回归测试。
