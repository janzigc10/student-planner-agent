# Plan 8: 真机内测与体验收尾 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不扩张产品范围的前提下，把 Student Planner 跑成可持续真机自用的版本：先打通手机访问与 PWA 安装，再完成核心链路 smoke，并以暴露的问题驱动首轮稳定性与体验补洞。

**Architecture:** 保持现有 FastAPI + WebSocket + React PWA 架构不变，不提前引入原生 App 封装层。执行顺序固定为“回归基线 -> 真机接入 -> PWA 验收 -> 核心 smoke -> 定向修补 -> 再评估推送与封装”，任何新问题先记录到 `bugs.md`，确认优先级后再改实现。

**Tech Stack:** FastAPI, WebSocket, React 18, TypeScript, Vite, vite-plugin-pwa, Zustand, pytest, Vitest, Playwright/manual mobile browser checks

---

## File Structure

- Create: `docs/superpowers/plans/2026-04-21-plan8-mobile-beta-stabilization.md` - 维护 Plan 8 的唯一执行清单。
- Modify: `progress.md` - 保持“当前阶段 / 最近完成 / 当前优先级”与 Plan 8 同步。
- Modify: `bugs.md` - 按致命 / 高摩擦 / 低优先级记录真机发现的问题。
- Modify: `student-planner/frontend/vite.config.ts` - 真机访问、PWA manifest、preview/install/update 行为相关配置。
- Modify: `student-planner/frontend/src/sw.ts` - PWA 缓存、通知点击、更新接管等行为。
- Modify: `student-planner/frontend/src/main.tsx` - PWA 注册或启动流程若需补强时的落点。
- Modify: `student-planner/frontend/public/pwa.svg` - 手机桌面图标若需重做时的落点。
- Modify: `student-planner/frontend/src/api/client.ts` - 手机访问链路、错误提示、超时处理若需补强时的落点。
- Modify: `student-planner/frontend/src/api/client.test.ts` - API 客户端契约回归。
- Modify: `student-planner/frontend/src/pages/ChatPage.tsx` - Chat 真机体验、确认后衔接、图片解析反馈。
- Modify: `student-planner/frontend/src/pages/ChatPage.test.tsx` - Chat 真机回归测试。
- Modify: `student-planner/frontend/src/stores/chatStore.ts` - `pendingAsk` / `progress` / `isSending` 状态收口。
- Modify: `student-planner/frontend/src/stores/chatStore.test.ts` - chat store 回归。
- Modify: `student-planner/frontend/src/pages/CalendarPage.tsx` - 真机日历触控与信息密度微调。
- Modify: `student-planner/frontend/src/pages/CalendarPage.test.tsx` - 日历页回归。
- Modify: `student-planner/frontend/src/pages/CoursesPage.tsx` - 课表查看 / 编辑 / 导入入口的真机修补。
- Modify: `student-planner/frontend/src/components/AppShell.tsx` - 底部导航命中区域或壳层交互微调。
- Modify: `student-planner/frontend/src/index.css` - 触控命中、动画节奏、文案密度、间距统一。
- Modify: `student-planner/app/main.py` - 若真机接入暴露健康检查或启动相关问题，这里是入口。
- Modify: `student-planner/app/config.py` - 若访问链路需要显式配置，这里是配置落点。
- Modify: `student-planner/app/routers/chat.py` - 若 WebSocket 等待态或重连顺序在真机上复现问题，这里是后端落点。
- Modify: `student-planner/app/routers/schedule_import.py` - 若图片解析轮询 / 状态载荷不足，这里是后端落点。
- Modify: `student-planner/tests/test_chat_ws.py` - WebSocket 行为回归。
- Modify: `student-planner/tests/test_schedule_import_api.py` - 上传状态 / 轮询契约回归。
- Modify: `student-planner/tests/test_schedule_tools.py` - 课表解析链路回归。
- Create: `docs/superpowers/specs/2026-04-21-android-packaging-evaluation.md` - PWA 稳定后补写 Android 封装评估结论。

### Task 1: 激活 Plan 8 并锁定回归基线

**Files:**
- Modify: `docs/superpowers/plans/2026-04-21-plan8-mobile-beta-stabilization.md`
- Modify: `progress.md`
- Modify: `bugs.md`

- [x] **Step 1: 保存 Plan 8，并把 `progress.md` 更新为“Plan 8 已激活”的当前快照**

要求：

- `progress.md` 的“当前阶段”明确当前活跃计划为 Plan 8。
- “最近完成”新增一条，说明已完成 Plan 8 规划。
- 不把本计划之外的历史流水重新塞回 `AGENTS.md`。

- [x] **Step 2: 重新跑当前本地回归基线，只有绿灯才进入真机环节**

Run from `D:\student_time_plan\student-planner`:

```bash
py -3.12 -m pytest -q
```

Run from `D:\student_time_plan`:

```bash
npm --prefix student-planner/frontend test
npm --prefix student-planner/frontend run build
```

Expected:

- 后端全量回归 PASS
- 前端全量回归 PASS
- 前端构建 PASS

- [x] **Step 3: 如果基线失败，先把失败项记录进 `bugs.md`，并在进入真机任务前修回绿色**

记录模板：

```md
## 致命
- 路径：
- 命令：
- 预期：
- 实际：
- 暂定 owner：
```

- [x] **Step 4: 提交文档与基线快照**

```bash
git add docs/superpowers/plans/2026-04-21-plan8-mobile-beta-stabilization.md progress.md bugs.md
git commit -m "docs: activate plan 8 mobile beta stabilization"
```

### Task 2: 打通手机访问当前前后端与 WebSocket

**Files:**
- Modify: `progress.md`
- Modify: `bugs.md`
- Modify: `student-planner/frontend/vite.config.ts`
- Modify: `student-planner/frontend/src/api/client.ts`
- Modify: `student-planner/frontend/src/api/client.test.ts`
- Modify: `student-planner/frontend/src/pages/ChatPage.tsx`
- Modify: `student-planner/app/main.py`
- Modify: `student-planner/app/config.py`
- Modify: `student-planner/app/routers/chat.py`
- Modify: `student-planner/tests/test_chat_ws.py`

- [x] **Step 1: 先起一套手机可访问的本地环境，再决定是否需要临时公网环境**

Run from `D:\student_time_plan\student-planner`:

```bash
py -3.12 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Run from `D:\student_time_plan`:

```bash
npm --prefix student-planner/frontend run dev -- --host 0.0.0.0 --port 5173
```

- [x] **Step 2: 在手机上验证最小可达性：`/health`、`/chat`、发送一条普通消息**

手机检查项：

1. 打开 `http://<LAN-IP>:8000/health`，确认返回 `{"status":"ok"}`。
2. 打开 `http://<LAN-IP>:5173/chat`，确认页面可加载。
3. 登录后发送一条“测试消息”，确认能走通 WebSocket 收发。

- [x] **Step 3: 如果访问链路失败，先写最窄的失败回归，再改代码**

优先级：

1. 若问题在请求 URL 或错误提示，优先改 `student-planner/frontend/src/api/client.ts` 并先补 `student-planner/frontend/src/api/client.test.ts`。
2. 若问题在 WebSocket 握手 / 等待态 / 重连顺序，优先补 `student-planner/tests/test_chat_ws.py`。
3. 只有当前端定位充分时，才动 `student-planner/app/routers/chat.py`。

前端测试示意：

```ts
it('surfaces backend detail messages when the mobile access path is reachable but the request fails', async () => {
  // mock fetch -> 4xx/5xx
  // assert the client exposes the backend detail instead of a generic network error
})
```

后端测试示意：

```python
def test_chat_websocket_keeps_the_session_open_until_first_real_reply(client) -> None:
    # authenticate
    # send one user message
    # assert the socket does not drop before the first follow-up event
```

- [x] **Step 4: 实现最小修复，优先修访问链路，不改业务协议**

约束：

- 优先修 host / URL / timeout / reconnect / 错误文案。
- 不顺手改聊天交互和视觉细节。
- 不引入新的部署抽象层。

- [x] **Step 5: 回归并复测手机访问链路**

Run:

```bash
npm --prefix student-planner/frontend test -- src/api/client.test.ts src/pages/ChatPage.test.tsx
py -3.12 -m pytest tests/test_chat_ws.py -v
```

然后在手机上重做 Step 2 的 3 项检查。

- [x] **Step 6: 更新 `bugs.md` 与 `progress.md`，明确接下来进入 PWA 安装验收**

```bash
git add progress.md bugs.md student-planner/frontend/vite.config.ts student-planner/frontend/src/api/client.ts student-planner/frontend/src/api/client.test.ts student-planner/frontend/src/pages/ChatPage.tsx student-planner/app/main.py student-planner/app/config.py student-planner/app/routers/chat.py student-planner/tests/test_chat_ws.py
git commit -m "fix: unblock mobile access path"
```

### Task 3: 验收 PWA 安装、启动和更新链路

**Files:**
- Modify: `progress.md`
- Modify: `bugs.md`
- Modify: `student-planner/frontend/vite.config.ts`
- Modify: `student-planner/frontend/src/sw.ts`
- Modify: `student-planner/frontend/src/main.tsx`
- Modify: `student-planner/frontend/public/pwa.svg`

- [x] **Step 1: 用 production build + preview 验收 PWA，而不是只看 dev server**

Run from `D:\student_time_plan`:

```bash
npm --prefix student-planner/frontend run build
npm --prefix student-planner/frontend run preview -- --host 0.0.0.0 --port 4173
```

- [ ] **Step 2: 在手机上完整验证 PWA 安装链路**

手机检查项：

1. 从 `http://<LAN-IP>:4173/chat` 进入并安装。
2. 桌面图标显示正常。
3. 以独立窗口打开，而不是浏览器 tab。
4. 冷启动落到 `/chat`。
5. 重新构建后能拿到新版本，不会长时间卡旧缓存。

- [ ] **Step 3: 如果 PWA 行为不对，先判断是配置问题还是应用问题**

判断规则：

- manifest / 图标 / `start_url` / `display` 问题：优先查 `student-planner/frontend/vite.config.ts` 和 `student-planner/frontend/public/pwa.svg`
- 缓存 / 接管 / 点击通知回前台问题：优先查 `student-planner/frontend/src/sw.ts`
- 启动后页面状态异常：优先查 `student-planner/frontend/src/main.tsx`

若需要补 service worker 行为，可参考最小代码骨架：

```ts
self.addEventListener('message', (event) => {
  if (event.data?.type === 'SKIP_WAITING') {
    self.skipWaiting()
  }
})
```

- [ ] **Step 4: 只做最小 PWA 修补，不重做外壳设计**

约束：

- 不改页面结构。
- 不引入新的离线能力范围。
- 只修安装、启动、更新、图标清晰度、通知跳转这几类验收问题。

- [ ] **Step 5: 重新 build + preview + 手机重验，并把结果写回 `progress.md` / `bugs.md`**

```bash
git add progress.md bugs.md student-planner/frontend/vite.config.ts student-planner/frontend/src/sw.ts student-planner/frontend/src/main.tsx student-planner/frontend/public/pwa.svg
git commit -m "fix: stabilize pwa install and update flow"
```

### Task 4: 跑手机核心流程 smoke，并把问题分级收口

**Files:**
- Modify: `progress.md`
- Modify: `bugs.md`

- [ ] **Step 1: 在手机上完整跑一轮核心流程**

固定路径：

1. 登录
2. 聊天
3. 上传课表图片
4. 确认导入
5. 查看日历
6. 编辑一门课程

- [ ] **Step 2: 每发现一个问题，立即按统一模板写入 `bugs.md`**

模板：

```md
## 高摩擦
- 路径：聊天 -> 上传课表图片 -> 点击确认
- 预期：
- 实际：
- 复现频率：
- 手机端独有 / 桌面也复现：
- 暂定 owner：
```

- [ ] **Step 3: 只选择一个最高价值的问题进入下一任务，不并行开多条修复线**

选择顺序：

1. 致命问题
2. 高摩擦问题
3. 已知优先项中的 Chat 空窗衔接
4. 课表图片异步解析反馈
5. 视觉微调

- [ ] **Step 4: 更新 `progress.md`，明确“下一步修什么、为什么是它”**

```bash
git add progress.md bugs.md
git commit -m "docs: record mobile smoke findings"
```

### Task 5: 加固 Chat 在“确认后继续处理”之间的衔接体验

**Files:**
- Modify: `progress.md`
- Modify: `bugs.md`
- Modify: `student-planner/frontend/src/pages/ChatPage.tsx`
- Modify: `student-planner/frontend/src/pages/ChatPage.test.tsx`
- Modify: `student-planner/frontend/src/stores/chatStore.ts`
- Modify: `student-planner/frontend/src/stores/chatStore.test.ts`
- Modify: `student-planner/app/routers/chat.py`
- Modify: `student-planner/tests/test_chat_ws.py`

- [ ] **Step 1: 先把真机复现到的具体症状写成失败测试**

如果复现的是已知问题，优先覆盖这两类场景：

```tsx
it('keeps the answered ask visible with a bridge hint until the first follow-up event arrives', async () => {
  // click confirm
  // assert "已选择：确认"
  // assert "正在继续处理，请稍候…"
})
```

```ts
it('does not clear an answered ask before the follow-up activity is visible', () => {
  // reduce ask_user -> answerAsk -> done/tool_call/text sequence
  // assert pendingAsk is not cleared too early
})
```

- [ ] **Step 2: 运行 Chat 定向回归，确认测试先失败**

Run:

```bash
npm --prefix student-planner/frontend test -- src/pages/ChatPage.test.tsx src/stores/chatStore.test.ts
```

- [ ] **Step 3: 先做前端最小修补，只有在事件顺序确实有问题时才动后端**

优先落点：

1. `student-planner/frontend/src/stores/chatStore.ts`
2. `student-planner/frontend/src/pages/ChatPage.tsx`
3. 如果前端状态机正确但真机仍断流，再查 `student-planner/app/routers/chat.py`

约束：

- 不改现有 `ask_user` 协议结构。
- 不顺手重做消息列表。
- 只补“确认后到下一次可见反馈前”的连续感。

- [ ] **Step 4: 跑定向回归；若动了后端，再补 WebSocket 回归**

Run:

```bash
npm --prefix student-planner/frontend test -- src/pages/ChatPage.test.tsx src/stores/chatStore.test.ts
py -3.12 -m pytest tests/test_chat_ws.py -v
```

- [ ] **Step 5: 用手机重新验证“点击确认 -> 继续处理 -> 出现下一条反馈”这一段体验**

通过标准：

- 没有无反馈空档
- 已选答案不会异常丢失
- 出错时会解锁发送态并给出提示

- [ ] **Step 6: 更新 `progress.md` / `bugs.md`，然后提交**

```bash
git add progress.md bugs.md student-planner/frontend/src/pages/ChatPage.tsx student-planner/frontend/src/pages/ChatPage.test.tsx student-planner/frontend/src/stores/chatStore.ts student-planner/frontend/src/stores/chatStore.test.ts student-planner/app/routers/chat.py student-planner/tests/test_chat_ws.py
git commit -m "fix: smooth chat confirmation bridge"
```

### Task 6: 补齐课表图片异步解析的手机反馈

**Files:**
- Modify: `progress.md`
- Modify: `bugs.md`
- Modify: `student-planner/frontend/src/pages/ChatPage.tsx`
- Modify: `student-planner/frontend/src/pages/ChatPage.test.tsx`
- Modify: `student-planner/frontend/src/api/client.ts`
- Modify: `student-planner/frontend/src/types/api.ts`
- Modify: `student-planner/app/routers/schedule_import.py`
- Modify: `student-planner/tests/test_schedule_import_api.py`
- Modify: `student-planner/tests/test_schedule_tools.py`

- [ ] **Step 1: 在现有上传轮询测试上补一条失败用例，锁定真机里最别扭的反馈缺口**

优先覆盖：

1. 进度条是否持续到真正 `PARSED`
2. 失败后是否恢复待发附件
3. 多张图片时文案是否清楚表达当前阶段

测试方向示意：

```tsx
it('keeps the image parse bridge visible until the parsed status is received and then clears it once', async () => {
  // upload -> POLLING -> PARSED
  // assert bridge stays visible during parsing
  // assert it clears only after completion
})
```

- [ ] **Step 2: 跑图片上传相关定向回归，确认测试先失败**

Run:

```bash
npm --prefix student-planner/frontend test -- src/pages/ChatPage.test.tsx
```

- [ ] **Step 3: 先做前端 UI-first 修复；只有接口信息不够时才动后端**

优先落点：

1. `student-planner/frontend/src/pages/ChatPage.tsx`
2. `student-planner/frontend/src/api/client.ts`
3. `student-planner/frontend/src/types/api.ts`
4. 只有载荷确实不够时，再改 `student-planner/app/routers/schedule_import.py`

- [ ] **Step 4: 运行前后端定向回归**

Run:

```bash
npm --prefix student-planner/frontend test -- src/pages/ChatPage.test.tsx src/api/client.test.ts
py -3.12 -m pytest tests/test_schedule_import_api.py tests/test_schedule_tools.py -v
```

- [ ] **Step 5: 在手机上分别用 1 张图和 2 张图重跑上传流程**

通过标准：

- 解析中有连续反馈
- 解析失败能恢复可重试状态
- 成功后稳定进入确认卡

- [ ] **Step 6: 更新 `progress.md` / `bugs.md`，然后提交**

```bash
git add progress.md bugs.md student-planner/frontend/src/pages/ChatPage.tsx student-planner/frontend/src/pages/ChatPage.test.tsx student-planner/frontend/src/api/client.ts student-planner/frontend/src/types/api.ts student-planner/app/routers/schedule_import.py student-planner/tests/test_schedule_import_api.py student-planner/tests/test_schedule_tools.py
git commit -m "fix: polish mobile schedule image feedback"
```

### Task 7: 做一轮前端视觉细节与触控微调

**Files:**
- Modify: `progress.md`
- Modify: `bugs.md`
- Modify: `student-planner/frontend/src/index.css`
- Modify: `student-planner/frontend/src/components/AppShell.tsx`
- Modify: `student-planner/frontend/src/pages/ChatPage.tsx`
- Modify: `student-planner/frontend/src/pages/CalendarPage.tsx`
- Modify: `student-planner/frontend/src/pages/CoursesPage.tsx`
- Modify: `student-planner/frontend/src/pages/ChatPage.test.tsx`
- Modify: `student-planner/frontend/src/pages/CalendarPage.test.tsx`

- [ ] **Step 1: 把真机观察到的 UI 问题收敛成最多 5 个明确 tweak**

允许进入本轮的 tweak 类型：

1. 触控命中区域
2. 动效节奏
3. 分页 / 操作按钮可见性
4. 文案密度
5. 小屏间距与层级

- [ ] **Step 2: 需要改语义或交互时，先补最窄的失败测试；纯 CSS 微调不强行新增测试**

Run:

```bash
npm --prefix student-planner/frontend test -- src/pages/ChatPage.test.tsx src/pages/CalendarPage.test.tsx
```

- [ ] **Step 3: 只做小范围 CSS / markup 修补，不重开新一轮视觉重构**

约束：

- 不换主题方向
- 不重写页面结构
- 不引入与当前目标无关的新动效

- [ ] **Step 4: 跑前端回归与构建**

Run:

```bash
npm --prefix student-planner/frontend test -- src/pages/ChatPage.test.tsx src/pages/CalendarPage.test.tsx
npm --prefix student-planner/frontend run build
```

- [ ] **Step 5: 在手机上回看聊天页、日历页、课程页，确认 tweak 确实降低摩擦**

- [ ] **Step 6: 更新 `progress.md` / `bugs.md`，然后提交**

```bash
git add progress.md bugs.md student-planner/frontend/src/index.css student-planner/frontend/src/components/AppShell.tsx student-planner/frontend/src/pages/ChatPage.tsx student-planner/frontend/src/pages/CalendarPage.tsx student-planner/frontend/src/pages/CoursesPage.tsx student-planner/frontend/src/pages/ChatPage.test.tsx student-planner/frontend/src/pages/CalendarPage.test.tsx
git commit -m "fix: tune mobile interaction details"
```

### Task 8: 验证推送闭环并给出 Android 封装决策

**Files:**
- Modify: `progress.md`
- Modify: `bugs.md`
- Modify: `student-planner/frontend/src/sw.ts`
- Modify: `student-planner/frontend/src/pages/NotificationsPage.tsx`
- Modify: `student-planner/app/routers/push.py`
- Create: `docs/superpowers/specs/2026-04-21-android-packaging-evaluation.md`

- [ ] **Step 1: 只有在 Task 1 至 Task 7 稳定后，才进入移动推送验证**

手机检查项：

1. 申请通知权限
2. 完成订阅
3. 触发一条测试通知
4. 点击通知后回到正确页面

- [ ] **Step 2: 若推送闭环有问题，先补最小回归，再做最小修复**

优先级：

1. `student-planner/frontend/src/sw.ts`
2. `student-planner/frontend/src/pages/NotificationsPage.tsx`
3. `student-planner/app/routers/push.py`

- [ ] **Step 3: 补写 Android 封装评估结论，明确是继续 PWA、走 TWA 还是走 Capacitor**

Write to `docs/superpowers/specs/2026-04-21-android-packaging-evaluation.md`:

```md
# Android Packaging Evaluation

## Current PWA Status
## TWA
## Capacitor
## Recommendation
## Minimum Change Scope
## Not Doing Yet
```

- [ ] **Step 4: 更新 `progress.md`，把项目下一阶段切到“推送收尾”或“封装预研”**

```bash
git add progress.md bugs.md student-planner/frontend/src/sw.ts student-planner/frontend/src/pages/NotificationsPage.tsx student-planner/app/routers/push.py docs/superpowers/specs/2026-04-21-android-packaging-evaluation.md
git commit -m "docs: decide next mobile delivery track"
```
