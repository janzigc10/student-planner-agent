# Student Planner 当前进度

## 当前阶段
Plan 1 至 Plan 7 已全部完成，项目当前进入真机自用内测阶段：先把产品放到手机里真实使用，验证核心链路是否跑通，并在日常使用中持续暴露问题。当前活跃计划为 Plan 8《真机内测与体验收尾》，Task 2《打通手机访问当前前后端与 WebSocket》已完成，Task 3《验收 PWA 安装、启动和更新链路》已启动，当前已补上临时 HTTPS 测试环境，下一步是在手机上完成 PWA 安装与启动验收。

## 最近完成
- 已将当前版本部署到腾讯云测试机 `101.33.229.161`：后端运行在 `127.0.0.1:8000`、Nginx 反代运行在 `127.0.0.1:8080`，并通过 Cloudflare Quick Tunnel 暴露临时 HTTPS 入口 `https://browsing-gibson-cons-aggregate.trycloudflare.com`。
- 已在外部验证临时 HTTPS 环境：`/health`、`/chat`、`manifest.webmanifest` 正常返回；浏览器里 `isSecureContext=true`，`navigator.serviceWorker` 可用且已有 `1` 条注册。
- 已起本地 `0.0.0.0:8000` 后端、`0.0.0.0:5173` dev server 和 `0.0.0.0:4173` preview，并用 LAN 地址 `192.168.3.105` 验证了 `/health`、`/chat`、注册登录与普通消息收发链路。
- 已修复前端在部分浏览器环境下 `crypto.randomUUID is not a function` 会直接打断聊天发送的问题；补了 `createClientId` 兜底与对应前端回归，当前定向测试 `50 passed`、`tests/test_chat_ws.py` 为 `4 passed`、前端 build 继续 `PASS`。
- 已确认 Task 3 的核心前置：preview 入口与 manifest 正常，但 LAN 上的 `http://192.168.3.105:4173` 不是 secure context，`navigator.serviceWorker` 不可用，真机 PWA 安装需切到 HTTPS 路径。
- 已在 `codex/plan8-mobile-beta` 分支激活 Plan 8，并串行重跑本地回归基线：后端 `194 passed`、前端 `68 passed`、前端构建 `PASS`。
- 已整理 Plan 8《真机内测与体验收尾》，后续按“回归基线 -> 真机接入 -> PWA 验收 -> 核心 smoke -> 定向修补”顺序推进。
- 将项目当前目标重新明确为“真机自用内测”，不再默认按正式上线准备推进。
- 重构文档分工：`AGENTS.md` 作为固定入口，`progress.md` 作为滚动交接，`bugs.md` 保留长期问题，`context.md` 保留项目地图。
- 确认最近一轮仍然有效的产品状态：
  - 课表图片异步解析后端已支持 `processing` 状态与轮询接口。
  - Chat 流式输出、课程周次过滤、旧数据库兼容迁移、OCR 确认卡压缩等关键修复已落地。
- 把“先 PWA 真机验证，再评估 App 封装”的两步走路线写入当前优先级与待办池。

## 当前优先级
1. 先做手机真机可用版本，采用“两步走”路线：先完成 PWA 真机安装与日常使用验证，再评估并推进 App 封装。
2. 跑通真实自用核心链路：登录、聊天、上传课表图片、确认导入、查看日历、课程编辑。
3. 在自用过程中持续记录致命问题、高摩擦问题和低优先级体验问题，再决定下一轮优化顺序。
4. 优化 Chat 在“点击确认后到下一次 `tool_call` 前”的短暂空窗体验，保持稳定前提下提升连续感。
5. 继续做前端视觉细节验收与交互微调，包括动效节奏、触控命中和文案密度。
6. 课表图片异步解析的前端进度展示可暂时后移，后续再补前端轮询或 WebSocket 进度消费。

## 下一 Session 第一件事
- 打开 `docs/superpowers/plans/2026-04-21-plan8-mobile-beta-stabilization.md`，从 Task 3 Step 2 继续，直接用手机访问临时 HTTPS 入口 `https://browsing-gibson-cons-aggregate.trycloudflare.com` 做安装验收。
- 先在手机上验证：
  - 从 `/chat` 进入并安装
  - 桌面图标、独立窗口、冷启动路径
  - 登录后聊天能继续工作
- 若 Quick Tunnel 地址失效，先到服务器上执行 `systemctl status student-planner-tunnel` 和 `grep trycloudflare /var/log/student-planner-tunnel.log`，拿新的临时地址再继续。

## 当前阻塞 / 风险
- 目前最大的前置条件不是功能本身，而是手机如何稳定访问当前前后端与 WebSocket。
- 真机 PWA 安装的 HTTPS 前置已经通过 Quick Tunnel 打通，但临时 tunnel 没有稳定 SLA，地址会在服务重启后变化。
- 真机一旦开始连续使用，可能很快会把“图片解析进度展示”和“确认后空窗体验”重新推回高优先级。
- 旧 session 的完整交接历史还没有单独归档成 `handoff` 文档；当前依赖本文件做滚动交接、依赖 `bugs.md` 保存长期问题。

## 真机自用待办池
- 真机 PWA 安装链路：确认 manifest、图标、启动页、独立窗口打开、缓存更新策略在手机端表现正常。
- 手机网络访问链路：先确定手机如何稳定访问当前前后端与 WebSocket。
- 自用核心流程 smoke：登录、聊天、上传课表图片、确认导入、查看日历、课程编辑至少各跑一轮真实手机路径。
- 自用问题记录机制：把日常使用中遇到的问题持续写入 `bugs.md`，并区分致命、高摩擦、低优先级。
- 推送闭环验证：在真机路径基本跑通后，再补移动端推送订阅、权限申请、通知点击跳转验证。
- App 封装预研：在 PWA 真机自用稳定后，评估 Android 封装路线（如 Capacitor 或 TWA）与最小改造范围。

## 最近验证基线
- 最近一次全量后端回归：`py -3.12 -m pytest -q`，`194 passed`。
- 最近一次全量前端回归：`npm --prefix student-planner/frontend test`，`68 passed`。
- 最近一次前端构建：`npm --prefix student-planner/frontend run build`，`PASS`。
- 最近一次 Task 2 定向前端回归：`npm --prefix student-planner/frontend test -- src/createClientId.test.ts src/stores/chatStore.test.ts src/pages/ChatPage.test.tsx`，`50 passed`。
- 最近一次 Task 2 定向后端回归：`py -3.12 -m pytest tests/test_chat_ws.py -v`，`4 passed`。
- 较新的改动以定向回归为主，最近一轮 Chat/OCR 相关前端验证为 `46 passed`，构建仍为 `PASS`。
