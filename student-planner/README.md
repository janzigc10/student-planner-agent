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
