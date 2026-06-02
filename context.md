# Student Planner 项目地图

## 项目定位
Student Planner 是一个 AI 驱动的学生时间规划 Agent，核心目标是把“课前提醒”和“任务拆解”结合起来，帮助学生围绕课程安排管理每日任务。

## 技术栈
- 后端：FastAPI
- 前端：React PWA
- 模型：国产 LLM，走 OpenAI 兼容接口
- 数据层：SQLite + Alembic

## 仓库结构
- `docs/`
  - 设计文档、计划文档、历史实现说明。
- `student-planner/`
  - 主工程目录。
- `student-planner/app/`
  - 后端主代码。
- `student-planner/app/agent/`
  - Agent loop、工具定义、guardrail、LLM client。
- `student-planner/app/routers/`
  - API 路由。
- `student-planner/app/services/`
  - 课表解析、时间转换等服务。
- `student-planner/frontend/src/`
  - 前端主代码。
- `student-planner/frontend/src/pages/`
  - 页面层。
- `student-planner/frontend/src/stores/`
  - 状态管理。
- `student-planner/frontend/src/components/`
  - 复用 UI 组件。
- `student-planner/tests/`
  - 后端与集成测试。

## 已落地能力
- 后端基础能力与认证链路。
- Agent 核心 loop、工具调用、上下文压缩与跨轮恢复。
- 课表导入，包括文件解析、图片 OCR、确认链路与课程管理。
- Memory / 上下文管理。
- 推送系统。
- 前端 PWA 与现代化 UI。
- 日历、课程查看与编辑相关能力。

## 关键文档
### 总设计
- `docs/superpowers/specs/2026-03-29-student-time-planner-design.md`
- `docs/superpowers/specs/2026-03-30-frontend-pwa-design.md`

### 实施计划
- `docs/superpowers/plans/2026-03-29-plan1-backend-foundation.md`
- `docs/superpowers/plans/2026-03-29-plan2-agent-core.md`
- `docs/superpowers/plans/2026-03-30-plan3-schedule-import.md`
- `docs/superpowers/plans/2026-03-30-plan4-memory-context.md`
- `docs/superpowers/plans/2026-03-30-plan5-push-notifications.md`
- `docs/superpowers/plans/2026-03-30-plan6-frontend-pwa.md`
- `docs/superpowers/plans/2026-04-18-plan7-frontend-ui-modernization.md`

## 进入新任务时的阅读顺序
1. 固定先读 `AGENTS.md`、`progress.md`、`bugs.md`。
2. 只有在任务跨模块、需要项目地图，或对代码结构不熟时，再读 `context.md`。
3. 只读与当前任务直接相关的 design / plan。
4. 最后进入对应代码目录和测试文件定位改动点。
