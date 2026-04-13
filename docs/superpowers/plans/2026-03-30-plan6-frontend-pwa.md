# Plan 6: 前端 PWA — React 手机端薄客户端

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基于 `docs/superpowers/specs/2026-03-30-frontend-pwa-design.md` 实现学生时间规划 Agent 的手机端 React PWA：登录注册、聊天、日历、我的页、课表管理、偏好设置、通知订阅。

**Architecture:** 前端新建在 `student-planner/frontend/`，使用 Vite + React 18 + TypeScript + React Router v6 + Zustand + Ant Design Mobile + vite-plugin-pwa。前端只负责 UI、状态缓存、API/WebSocket 调用；任务拆解、课表导入确认、时间换算、提醒创建继续由后端和 Agent 负责。开发环境使用 Vite proxy 代理 `/api` 和 `/ws` 到 FastAPI；本计划不要求 FastAPI 托管前端 `dist`。

**Tech Stack:** Vite, React 18, TypeScript, React Router v6, Zustand, Ant Design Mobile, vite-plugin-pwa, Vitest, Testing Library, Playwright, existing FastAPI backend.

**Depends on:** Plan 1-5 completed. Use `py -3.12 -m pytest` for backend tests on this machine because PATH `python` is 3.8.10.

---

## File Structure

```
student-planner/
├── app/
│   ├── agent/tool_executor.py
│   ├── routers/auth.py
│   ├── routers/schedule_import.py
│   ├── schemas/user.py
│   └── services/schedule_upload_cache.py
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── stores/
│   │   ├── types/
│   │   └── test/
│   ├── public/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   └── playwright.config.ts
└── tests/
    ├── test_auth.py
    ├── test_schedule_import_api.py
    ├── test_schedule_upload_cache.py
    ├── test_schedule_tools.py
    └── test_bulk_import.py
```

---

### Task 1: Spec 入仓 + 后端桥接

**Files:**
- Create: `docs/superpowers/specs/2026-03-30-frontend-pwa-design.md`
- Create: `student-planner/app/services/schedule_upload_cache.py`
- Create: `student-planner/tests/test_schedule_upload_cache.py`
- Modify: `docs/superpowers/plans/2026-03-30-plan6-frontend-pwa.md`
- Modify: `AGENTS.md`
- Modify: `student-planner/app/schemas/user.py`
- Modify: `student-planner/app/routers/auth.py`
- Modify: `student-planner/app/routers/schedule_import.py`
- Modify: `student-planner/app/agent/tool_executor.py`
- Modify: `student-planner/pyproject.toml`
- Test: `student-planner/tests/test_auth.py`
- Test: `student-planner/tests/test_schedule_import_api.py`
- Test: `student-planner/tests/test_schedule_tools.py`
- Test: `student-planner/tests/test_bulk_import.py`

- [x] **Step 1: Copy frontend spec into repo**
- [x] **Step 2: Create this Plan 6 file and update AGENTS.md**
- [x] **Step 3: Write failing backend bridge tests**
- [x] **Step 4: Run tests to verify they fail**
- [x] **Step 5: Implement backend bridge**
- [x] **Step 6: Run tests to verify they pass**
- [x] **Step 7: Commit**

Run: `cd student-planner && py -3.12 -m pytest tests/test_auth.py tests/test_schedule_import_api.py tests/test_schedule_upload_cache.py tests/test_schedule_tools.py tests/test_bulk_import.py -v`

---

### Task 2: 前端脚手架

**Files:**
- Create: `student-planner/frontend/*`
- Modify: `.gitignore`
- Modify: `AGENTS.md`

- [x] **Step 1: Scaffold Vite React TypeScript app**
- [x] **Step 2: Add dependencies and scripts**
- [x] **Step 3: Configure Vite and PWA basics**
- [x] **Step 4: Run scaffold checks**
- [x] **Step 5: Update AGENTS.md and commit**

Run: `cd student-planner/frontend && npm install && npm run typecheck && npm test && npm run build`

---

### Task 3: 应用外壳与认证

**Files:**
- Create/modify frontend API client, auth store, route guard, login/register pages, app shell, and shell tests.
- Modify: `AGENTS.md`

- [x] **Step 1: Write failing auth and routing tests**
- [x] **Step 2: Implement API client, DTOs, auth store, and route guards**
- [x] **Step 3: Implement login/register pages**
- [x] **Step 4: Implement mobile app shell with persistent tab state**
- [x] **Step 5: Run `npm run typecheck && npm test && npm run build`**
- [x] **Step 6: Update AGENTS.md to Task 4 and commit**

---

### Task 4: 聊天页

**Files:**
- Create/modify frontend chat store, WebSocket client, chat page, ask_user cards, upload sheet, speech input, and tests.
- Modify: `AGENTS.md`

- [x] **Step 1: Write failing chat reducer, WebSocket, and ask_user card tests**
- [x] **Step 2: Implement WebSocket token handshake and reconnect**
- [x] **Step 3: Implement message list, progress card, and tool-name mapping**
- [x] **Step 4: Implement ask_user confirm/select/review cards**
- [x] **Step 5: Implement attachment upload and Web Speech fallback**
- [x] **Step 6: Run `npm run typecheck && npm test && npm run build`**
- [x] **Step 7: Update AGENTS.md to Task 5 and commit**

---

### Task 5: 日历页

**Files:**
- Create/modify frontend calendar store, calendar page, task sheet, calendar tests.
- Modify: `AGENTS.md`

- [x] **Step 1: Write failing calendar data and interaction tests**
- [x] **Step 2: Implement day timeline from courses and tasks**
- [x] **Step 3: Implement task add/edit/complete flows**
- [x] **Step 4: Implement swipe day switching and pinch month view**
- [x] **Step 5: Run `npm run typecheck && npm test && npm run build`**
- [x] **Step 6: Update AGENTS.md to Task 6 and commit**

---

### Task 6: “我的”相关页面

**Files:**
- Create/modify frontend me pages, course grid, preferences form, notification settings, push subscription utilities, tests.
- Modify: `AGENTS.md`

- [x] **Step 1: Write failing me page, preferences, and notification tests**
- [x] **Step 2: Implement `/me` menu and logout**
- [x] **Step 3: Implement `/me/courses` weekly course grid and CRUD/import entry**
- [x] **Step 4: Implement `/me/preferences` saved via `PATCH /api/auth/me`**
- [x] **Step 5: Implement `/me/notifications` push subscribe/unsubscribe**
- [x] **Step 6: Run `npm run typecheck && npm test && npm run build`**
- [x] **Step 7: Update AGENTS.md to Task 7 and commit**

---

### Task 7: PWA 与最终验证

**Files:**
- Modify frontend PWA config, public icons/service worker setup, Playwright tests.
- Modify: `AGENTS.md`

- [x] **Step 1: Write or update Playwright smoke tests**
- [x] **Step 2: Add manifest, icons, service worker static cache, push listener, and notification click handling**
- [x] **Step 3: Verify API is network-only and WebSocket is uncached**
- [x] **Step 4: Run frontend verification**
- [x] **Step 5: Run backend regression**
- [x] **Step 6: Update AGENTS.md final status and commit**

Run frontend: `cd student-planner/frontend && npm run typecheck && npm test && npm run build && npm run e2e`

Run backend: `cd student-planner && py -3.12 -m pytest -v`
