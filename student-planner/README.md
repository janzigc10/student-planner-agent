# Student Planner

Student Planner 是一个面向大学生的 AI 时间规划应用，核心目标是把“聊天式规划”变成真正能落到课表、任务和提醒上的实际动作。

## 核心能力

- 查看与管理课程表
- 通过聊天生成任务和复习计划
- 课表 Excel 导入
- 课表截图识别与确认导入
- 日历视图查看课程与任务
- 推送提醒与服务端定时调度
- 移动端 PWA 使用体验

## 目录结构

- [app](./app): FastAPI 后端、Agent、路由、模型和服务层
- [frontend](./frontend): React + TypeScript 前端
- [alembic](./alembic): 数据库迁移
- [tests](./tests): 后端自动化测试
- [scripts](./scripts): 辅助脚本，例如 VAPID key 生成

## 技术实现概览

### 后端

- FastAPI 提供认证、课程、任务、提醒、聊天、导入等接口
- SQLAlchemy Async + SQLite 负责数据持久化
- Alembic 管理 schema 演进
- APScheduler 负责 reminder 定时触发

### Agent

- 使用 OpenAI-compatible 接口完成对话与 tool calling
- 将课程、任务、提醒、导入等能力注册为可调用工具
- 通过确认卡与 guardrails 控制写入动作，避免“直接修改用户数据”

#### ReAct 风格执行闭环

当前 Agent 更接近 ReAct / function calling 模式，而不是严格的 Plan-and-Execute：

```text
Thought(模型内部判断) -> Action(tool_call) -> Observation(tool_result) -> 下一轮判断 -> Final
```

实现上对应几层代码：

- [app/agent/loop.py](./app/agent/loop.py): 主循环，负责构造上下文、调用模型、处理 `tool_call`、回填 `tool_result`，直到最终回复。
- [app/agent/tools.py](./app/agent/tools.py): 工具能力表，限制模型能调用哪些业务动作。
- [app/agent/tool_executor.py](./app/agent/tool_executor.py): 工具执行层，真正查询或写入课程、任务、提醒等数据。
- [app/agent/tool_preflight.py](./app/agent/tool_preflight.py): 执行前校验，拦截缺必填参数、非法枚举、任务创建/修改混淆等风险。
- [app/agent/study_planner.py](./app/agent/study_planner.py): 复习计划生成器，只生成候选任务 JSON，不直接写入数据库。

一个典型任务修改流程是：

```text
用户要求修改任务
-> 模型调用 list_tasks 查找目标
-> 工具返回任务列表
-> 模型调用 ask_user 请求确认
-> 用户确认
-> 模型调用 update_task
-> 后端更新任务并同步 reminder
-> 模型返回最终结果
```

写入类动作必须先走 `ask_user`；工具结果会作为 Observation 回到模型上下文，驱动下一步决策。

### 前端

- React 18 + TypeScript + Zustand
- 移动端优先的聊天、日历、课程和通知页面
- Vite PWA 支持安装、缓存和推送订阅

## 本地运行

### 1. 配置环境变量

- 参考 [`.env.example`](./.env.example)
- 本地实际运行需要创建 `student-planner/.env`

### 2. 后端

在 `student-planner/` 目录下：

```bash
py -3.12 -m alembic upgrade head
py -3.12 -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 3. 前端

在仓库根目录下：

```bash
npm --prefix student-planner/frontend install
npm --prefix student-planner/frontend run dev
```

## 测试

### 后端测试

```bash
py -3.12 -m pytest -q
```

### 前端测试

```bash
npm --prefix student-planner/frontend test
npm --prefix student-planner/frontend run build
```

## 阅读建议

- 如果你关心产品能力：先看 [app/agent](./app/agent) 和 [frontend/src/pages](./frontend/src/pages)
- 如果你关心架构与质量：再看 [tests](./tests) 和 [../docs/superpowers](../docs/superpowers)
- 如果你关心移动端体验：重点看 [frontend/src/sw.ts](./frontend/src/sw.ts)、[frontend/src/pages/NotificationsPage.tsx](./frontend/src/pages/NotificationsPage.tsx) 和 [frontend/src/pages/ChatPage.tsx](./frontend/src/pages/ChatPage.tsx)
