# Plan 7: 前端 UI 现代化重构（全量页面，移动优先）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改业务逻辑和后端接口的前提下，完成全量前端页面现代化视觉升级：明亮玻璃拟态、青蓝主色、统一矢量图标、移动端优先阅读与交互体验。

**Scope:** `student-planner/frontend` 全部页面（聊天、日历、我的、登录注册、课表管理、偏好设置、通知设置），以及 `AGENTS.md` 与本计划文件的流程落地更新。

**Out of scope:** 后端 API、WebSocket 协议、业务数据模型、dark mode。

---

### Task 1: 设计系统底座（Design Tokens + 基础组件风格）

**Files:**
- Modify: `student-planner/frontend/src/index.css`

- [x] **Step 1: 建立统一视觉变量**
- [x] **Step 2: 建立统一组件语法（按钮、输入、卡片、提示）**
- [x] **Step 3: 增加 `prefers-reduced-motion` 降级策略**

---

### Task 2: Shell 与导航体系重构

**Files:**
- Create: `student-planner/frontend/src/components/icons.tsx`
- Modify: `student-planner/frontend/src/components/AppShell.tsx`
- Create: `student-planner/frontend/src/components/AppShell.test.tsx`

- [x] **Step 1: 将底部 tab emoji 替换为统一 SVG 图标**
- [x] **Step 2: 重做顶部与底部导航的玻璃层级视觉**
- [x] **Step 3: 保持路由行为和可访问语义不变**
- [x] **Step 4: 新增视觉契约测试并验证先失败后通过（TDD）**

Run: `npm --prefix student-planner/frontend test -- src/components/AppShell.test.tsx`

---

### Task 3: 页面视觉重构（全量页面）

**Files:**
- Modify: `student-planner/frontend/src/pages/ChatPage.tsx`
- Modify: `student-planner/frontend/src/pages/CalendarPage.tsx`
- Modify: `student-planner/frontend/src/pages/MePage.tsx`
- Modify: `student-planner/frontend/src/pages/CoursesPage.tsx`
- Modify: `student-planner/frontend/src/pages/PreferencesPage.tsx`
- Modify: `student-planner/frontend/src/pages/NotificationsPage.tsx`
- Modify: `student-planner/frontend/src/pages/LoginPage.tsx`
- Modify: `student-planner/frontend/src/pages/RegisterPage.tsx`
- Modify: `student-planner/frontend/src/pages/CalendarPage.test.tsx`

- [x] **Step 1: 聊天页现代化（消息、进度卡、ask 卡、附件托盘、输入区）**
- [x] **Step 2: 日历页现代化（时间轴、月视图、任务表单）**
- [x] **Step 3: 我的页与二级页视觉统一（菜单、表单、设置块）**
- [x] **Step 4: 登录/注册视觉统一**
- [x] **Step 5: 新增去 emoji 视觉契约测试并验证先失败后通过（TDD）**

Run: `npm --prefix student-planner/frontend test -- src/pages/CalendarPage.test.tsx`

---

### Task 4: 图标与字体系统统一

**Files:**
- Create: `student-planner/frontend/src/components/icons.tsx`
- Modify: `student-planner/frontend/src/index.css`

- [x] **Step 1: 全量替换 UI emoji 图标为统一矢量图标**
- [x] **Step 2: 使用本地优先几何现代无衬线字体 fallback 链**
- [x] **Step 3: 复查确保业务协议与数据类型无变更**

---

### Task 5: 流程落地（文档与验证）

**Files:**
- Modify: `docs/superpowers/plans/2026-04-18-plan7-frontend-ui-modernization.md`
- Modify: `AGENTS.md`

- [x] **Step 1: 创建并维护 Plan 7 文档（本文件）**
- [x] **Step 2: 更新 AGENTS 当前执行状态与交接记录**
- [x] **Step 3: 执行前端回归与构建验证**

Run:
- `npm --prefix student-planner/frontend test -- src/App.test.tsx src/pages/ChatPage.test.tsx src/pages/CalendarPage.test.tsx src/stores/chatStore.test.ts src/stores/calendarStore.test.ts`
- `npm --prefix student-planner/frontend test`
- `npm --prefix student-planner/frontend run build`
