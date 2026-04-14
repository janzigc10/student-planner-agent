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
**Task 3 宸插畬鎴愶紝涓嬩竴姝ユ槸鍓嶇 Task 4锛氭渶缁堝洖褰掑拰鎵嬪姩楠岃瘉銆?**
（每完成一个 task，更新这里指向下一个 task）

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
