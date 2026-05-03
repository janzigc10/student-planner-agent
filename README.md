# Student Planner Agent

一个面向大学生日常使用场景的 AI 时间规划项目。它把课程表、任务、提醒和聊天式规划放在同一个产品里，重点不是“单纯聊天”，而是让助手能基于真实日程数据做可确认、可执行的安排。

## 项目亮点

- 聊天式规划助手：支持通过自然语言查看课表、安排任务、生成复习计划、设置提醒。
- Agent 工具编排：助手不是只输出文本，而是会调用任务、课程、提醒等后端能力，并通过确认卡控制写入动作。
- 课表导入链路：支持 Excel 课表导入，也支持课表截图识别后的结构化确认导入。
- 移动端 PWA：提供适合手机使用的聊天、日历、课程与通知体验。
- 提醒系统：支持 Web Push 推送与服务端定时调度。

## 技术栈

- Backend: FastAPI, SQLAlchemy Async, Alembic, APScheduler
- Agent: OpenAI-compatible LLM client, tool calling loop, guardrails
- Frontend: React 18, TypeScript, Zustand, Vite, vite-plugin-pwa
- Testing: pytest, Vitest, Playwright

## 这个仓库里有什么

- [student-planner](./student-planner): 实际项目源码，包含前后端、Agent、数据库迁移和测试。
- [docs/superpowers](./docs/superpowers): 设计文档与阶段计划，记录了项目从基础能力到移动端内测的演进过程。
- [AGENTS.md](./AGENTS.md), [progress.md](./progress.md), [bugs.md](./bugs.md): 开发过程中的协作文档和交接记录。它们不是产品文档，而是项目迭代过程的一部分。

## 推荐阅读顺序

1. [student-planner/README.md](./student-planner/README.md): 看完整项目说明、运行方式和目录结构。
2. [student-planner/app](./student-planner/app): 看后端与 Agent 主体实现。
3. [student-planner/frontend/src](./student-planner/frontend/src): 看前端页面、状态管理和 PWA 入口。
4. [student-planner/tests](./student-planner/tests): 看自动化测试覆盖的核心链路。

## 适合向面试官强调的点

- 这是一个完整的全栈产品项目，不是单一算法 demo。
- Agent 能力和业务动作之间有明确边界：查询、确认、落库、提醒是分层的。
- 项目既覆盖了后端接口和调度，也覆盖了移动端 PWA、推送订阅和真实使用场景下的体验问题。
- 仓库中保留了设计、计划、测试和迭代痕迹，能看出从需求到交付的完整过程。

## 说明

- 当前仓库展示的是持续迭代中的版本，因此会看到设计文档、计划文档和测试文件一起保留。
- 如果你只想快速理解项目，优先看上面的源码与 README，不需要先看内部协作文档。
