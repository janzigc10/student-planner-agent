# Student Planner — 项目上下文

## 这是什么项目
AI 驱动的学生时间规划 Agent，核心功能：课前提醒 + AI 任务拆解。
技术栈：FastAPI + React PWA + 国产 LLM（OpenAI 兼容接口）。

## 关键文件（每次新 session 必读）
1. **本文件** — 项目上下文和当前进度
2. `docs/superpowers/specs/2026-03-29-student-time-planner-design.md` — 完整设计文档
3. `docs/superpowers/plans/2026-03-29-plan1-backend-foundation.md` — Plan 1: 后端基础
4. `docs/superpowers/plans/2026-03-29-plan2-agent-core.md` — Plan 2: Agent 核心

## 当前进度
- [ ] Plan 1: 后端基础（9 个 task）
- [ ] Plan 2: Agent 核心（10 个 task）
- [ ] Plan 3: 课表导入（未写）
- [ ] Plan 4: Memory + 上下文管理（未写）
- [ ] Plan 5: 推送系统（未写）
- [ ] Plan 6: 前端 PWA（未写）

## 当前正在执行
**Plan 1 — Task 6: Reminder Model + CRUD API**
（每完成一个 task，更新这里指向下一个 task）

## 规则
- 严格按 plan 文件中的 step 顺序执行
- 每完成一个 step，在 plan 文件中把 `- [ ]` 改成 `- [x]`
- 每完成一个 task，更新本文件的"当前正在执行"
- 遇到问题记录到下面的"问题记录"区域，不要自己改设计
- 测试必须通过才能进入下一个 task

## 问题记录
- 2026-03-29: 当前环境没有 `python`/`py` 命令，执行 Plan 中的 Python、pip、pytest 命令时需要改用 `C:\Users\Chen\anaconda3\python.exe`。
- 2026-03-29: `apply_patch` 在嵌套目录下落盘失败，当前改用 PowerShell 写文件继续执行；未改变设计或文件内容目标。
- 2026-03-29: PowerShell 默认 UTF-8 with BOM 会导致 `pyproject.toml` 解析失败，后续写文件统一改为 UTF-8 without BOM。
- 2026-03-29: `pip install -e '.[dev]'` 在当前 Anaconda 基础环境中提示 `pyasn1-modules` 与新装 `pyasn1` 版本冲突；Task 1 本身未被阻塞，但需要后续关注环境隔离。
- 2026-03-29: 首次 commit 因仓库缺少 git 用户名/邮箱失败，已在本仓库本地配置 `user.name=Codex`、`user.email=codex@local.invalid` 后继续执行。
- 2026-03-29: FastAPI 当前版本下 `/api/auth/me` 无 token 的默认行为与计划测试预期不一致，已在认证依赖中显式处理为 `403 Not authenticated` 以匹配计划。
- 2026-03-29: `pytest` 生成的 `student-planner/.pytest_cache` 目录当前权限异常，git 状态会给出访问警告，但未阻塞 Task 2/Task 3/Task 4/Task 5 提交。
- 2026-03-29: 早期用全文替换勾选 commit step 时误影响了后续 task 的同名 step，现已改为按 task 区段精确更新。
- 2026-03-29: Task 4 提交时混入了 `__pycache__/*.pyc` 运行产物，Task 5 已新增 `.gitignore` 并将这些文件从版本控制中移除。