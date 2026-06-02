# Student Planner 当前进度

## 当前阶段
2026-05-31 更新：当前活跃工作临时切到 Plan 9「Agent Execution Loop V1」，目标是先把 Agent 从“能说会做的 MVP”推进到“工具执行闭环可验证”的 V1。Plan 9 已完成后端核心实现与回归：课程有效周统一判断、课表离散单双周解析、课程提醒按真实有效周创建、`create_task`/`update_task` 支持 task reminder 一体化同步、Agent 多轮确认后修改任务时间与提醒的回归用例已覆盖。定向测试命令：`C:\Users\Chen\anaconda3\python.exe -m pytest -q tests/test_schedule_parser.py tests/test_course_occurrence.py tests/test_tool_executor.py tests/test_set_reminder_scheduling.py tests/test_auto_reminder.py tests/test_bulk_import.py tests/test_agent_loop_task_creation.py tests/test_tools_schema.py`，结果 `42 passed`；后端全量命令：`C:\Users\Chen\anaconda3\python.exe -m pytest -q`，结果 `214 passed`。
2026-05-31 追加更新：Plan 9 Task 7 已把 Agent 执行前校验从单点 reminder 补参扩展到通用 required-slot/schema guard，并补上“取消提醒”和“工具缺必填参数后恢复”的行为回归。最新验证：`tests/test_tool_preflight.py + tests/test_agent_loop_task_creation.py` 为 `17 passed`；Plan 9 定向集合为 `57 passed`；后端全量为 `229 passed`。
2026-06-01 追加更新：Plan 8 的本机可完成收尾已完成：PWA 更新接管、通知点击回 `/chat`、Chat 工具进度标签、课表图片异步解析提示、移动端触控目标和 Android 封装评估都已落地。前端重点回归 `54 passed, 2 skipped`，前端全量 `79 passed, 2 skipped`，前端 build `PASS`，production preview 烟测 `manifest.webmanifest=200` / `/chat=200`。随后用户补充确认：手机侧测试已做过且 OK。Plan 8 移动端收尾完成，不再列为当前阻塞。

Plan 1 至 Plan 8 已收束；项目当前应回到 Agent Loop 闭环稳定性验证。
2026-06-01 追加更新：当前活跃计划切到 Plan 10「Agent Loop E2E Harness」。目标是把 Plan 9 已修好的后端闭环能力，固化成少量但严格的真实浏览器 E2E：创建任务+提醒、修改任务+提醒、缺参数追问恢复，并为每条路径输出 DB invariant 和 evidence JSON。
2026-06-01 追加更新：Plan 10 已完成第一版 Agent Loop live E2E harness。`npm.cmd run e2e:agent-loop -- --reporter=list --global-timeout=420000` 在沙箱外权限下通过 `3 passed (1.5m)`，覆盖真实浏览器、专用本地后端、E2E SQLite、`ask_user -> tool_call -> tool_result -> done` 和 DB invariant；普通沙箱内同命令会因 live LLM provider 网络访问失败而报 `openai.APIConnectionError` / `WinError 5`，已记录到 `bugs.md`。
2026-06-01 追加更新：当前活跃计划切到 Plan 11「Agent Loop Context Stability V1」。本轮不扩新业务能力，先补 Agent Loop 在长历史、动态上下文和记忆/摘要注入下的稳定性边界：持久化历史进入 LLM 前压缩，当前用户消息和本轮 tool-call 链不压缩；动态上下文明示参考数据不能覆盖系统规则或工具规则；同时清理上下文乱码字段并补定向回归。
2026-06-01 追加更新：Plan 11 已完成。`run_agent_loop` 现在会在本轮 LLM 调用前压缩较早的持久化会话历史，但不会压缩当前用户消息、routing hints 或正在进行的 tool-call/tool-result 链；`build_dynamic_context` 已清理乱码重复字段，并加入上下文使用规则，明确课程、任务、偏好、记忆和会话摘要只是参考，不能覆盖系统规则或工具规则。验证：上下文/压缩/Agent Loop 定向 `24 passed, 1 warning`，Agent task/preflight 定向 `20 passed, 1 warning`；warning 均为既有 `.pytest_cache` 写入权限。
2026-06-01 追加更新：当前活跃计划切到 Plan 12「Agent Loop Failure Recovery and Evidence」。本轮实现剩余 Plan B/C：Plan B 处理 provider/network 失败时的用户可见恢复，避免只返回通用“聊天暂时不可用”；Plan C 扩展 Agent Loop live E2E，增加连续多轮修改同一任务/提醒的 evidence 对比，重点看同一个 task 是否复用、旧 reminder 是否残留、最终提醒参数是否正确。
2026-06-01 追加更新：Plan 12 已完成。Chat WebSocket 现在能把 provider/network 失败识别为 `llm_provider_unavailable`，返回 `recoverable=true` 和明确恢复文案，未知异常仍走通用失败文案；Agent Loop live E2E 增加连续两轮修改同一任务/提醒的 evidence，对比同一个 task、旧 reminder 清理和最终提醒状态。首次 live 运行暴露“取消提醒”能力表缺口：模型曾认为没有删除提醒工具；现已把 `update_task.reminder_advance_minutes=null` 写入工具契约、Agent 规则和 task routing hint。验证：后端 Plan 12 定向 `30 passed, 1 warning`，前端 store `14 passed`，前端 typecheck PASS，Agent Loop live E2E 沙箱外 `4 passed (3.0m)`。
2026-06-02 追加更新：围绕“下周四有大学英语3考试，帮我做复习计划”补了一组学习计划 live E2E 审计。结果是：模糊请求会先追问考试信息且不落库，这条通过；但完整考试信息场景在沙箱外 live E2E 中失败，Agent 能调用 `get_free_slots` 和 `create_study_plan` 生成 9 条候选复习任务，却在确认后没有继续调用 `create_task` 写入任务，最终 DB 中 `tasks=[] / reminders=[]`。因此复习计划任务拆解不能算已稳定闭环，问题不在“生成计划能力完全没有”，而在“review 确认后的结构化落库链路”。

## 最近完成
- 已新增学习计划拆解 live E2E 场景到 [agent-loop.spec.ts](/D:/student_time_plan/student-planner/frontend/e2e-agent/agent-loop.spec.ts)：一条覆盖“下周有一门考试”这类信息不足请求，要求 Agent 先 `ask_user` 追问且不写库；一条覆盖“2026-06-11 大学英语3考试”完整请求，要求 `get_free_slots -> create_study_plan -> create_task` 并写入 2026-06-03 至 2026-06-10 范围内的复习任务。验证：`npm.cmd run e2e:agent-loop -- --list` 列出 6 条 live 用例，`npm.cmd run typecheck` PASS；定向 live E2E 的信息不足用例通过，但完整写入用例在普通沙箱和沙箱外权限下都超时失败。沙箱外 DB 证据显示 `create_study_plan` 曾成功返回 9 条候选任务，但后续只进入 review/再次查询，没有调用 `create_task`，所以这是产品链路缺口，不是单纯 provider 网络问题。
- 已维护 GitHub 展示入口 README：根目录 [README.md](/D:/student_time_plan/README.md) 现在明确把 Agent 定位为 ReAct / function calling 风格的工具调用闭环，而不是严格 Plan-and-Execute；补充了 `Thought -> Action(tool_call) -> Observation(tool_result) -> Final` 的说明、`create_study_plan` 只是候选计划生成工具的边界，以及面试表述建议。子项目 [student-planner/README.md](/D:/student_time_plan/student-planner/README.md) 同步增加了实现级说明，指向 `loop.py`、`tools.py`、`tool_executor.py`、`tool_preflight.py` 和 `study_planner.py`。
- 已用用户提供的图片做了一轮安全侧检查：在本机找到的候选图片 [26535DI8P0VR242F.png](/C:/Users/Chen/Desktop/26535DI8P0VR242F.png) 实际是个人简历截图，不是课表图；由于真实 OCR 会把图片发送给外部 vision provider，本轮未在没有明确授权的情况下外发。已把 OCR prompt 收紧为“非大学课表/无周几节次网格时，不要从简历、项目经历、普通文档中提取课程”，并补上图片异步上传解析为空时的回归，确保非课表图片可以以 `PARSED + count=0` 收束，不误导成课程导入。随后继续修复 Chat shortcut 的空结果边界：空课程不再触发“共0条，确认是否导入？”确认卡，也不会追问学期开始日期/总周数，而是直接提示“没有从这张图片里识别到课程信息”。用该真实图片文件跑了不外发的本地上传探针：`image_size=3779334`，初始 `status=processing`，最终 `status=PARSED / progress=100 / count=0 / courses=[]`。验证：`tests/test_agent_loop.py::test_schedule_import_shortcut_handles_empty_image_parse_without_review_card tests/test_schedule_ocr.py tests/test_schedule_import_api.py tests/test_schedule_tools.py` 为 `34 passed, 5 warnings`，warnings 为 openpyxl deprecation 和既有 `.pytest_cache` 权限。
- 用户随后指出真正用于测试的是两张课表截图：[微信图片_20260419104519.jpg](/C:/Users/Chen/Desktop/微信图片_20260419104519.jpg) 和 [微信图片_20260419104523.jpg](/C:/Users/Chen/Desktop/微信图片_20260419104523.jpg)，上一条只看了桌面最新文件是误判。已用这两张真实文件跑不外发的本地多图上传/合并探针：第 3 周图片 `size=533142`，第 4 周图片 `size=517719`，初始 `status=processing / source_file_count=2`，最终 `status=PARSED / progress=100 / count=6`。按图中课程构造 mock OCR 结果后，后端合并得到：自然语言处理（周三 1-2，全周）、自然语言处理（周四 1-2，全周）、机器人流程自动化（周三 3-4，全周）、大模型微调技术（周三 5-6，单周）、大模型微调技术（周四 5-6，全周）、大学生就业指导（周三 9-10，全周）。真实 vision OCR 仍未跑，因为审批要求用户在说明外发风险后明确同意把这两张课表图发送给当前 vision provider。
- 用户明确要求后，已把这两张课表图发送给当前 vision provider 跑真实 OCR，并同时跑完整 `/api/schedule/upload` 异步解析链路。链路状态是通的：初始 `status=processing / source_file_count=2`，中途 `PARSING / progress=52 / count=8`，最终 `status=PARSED / progress=100 / count=13`。但 OCR 质量不合格：第 3 周图被识别成 8 条，竖排课程名拆裂；第 4 周图被识别成 5 条且部分 weekday 左移；最终合并为 13 条而人工应为 6 条。典型错误包括“机器人流程自动化”拆成“机器人程动 / 流自化”，“大学生就业指导”拆成“大生业导 / 学就指导”，第 4 周若干课程从周三/周四错成周二/周三。结论：上传/轮询/状态链路通，真实 OCR 识别质量暂不达标，已写入 `bugs.md`。
- 已完成 Plan 12「Agent Loop Failure Recovery and Evidence」：新增 [设计 spec](/D:/student_time_plan/docs/superpowers/specs/2026-06-01-agent-loop-failure-recovery-and-evidence-design.md) 和 [执行 plan](/D:/student_time_plan/docs/superpowers/plans/2026-06-01-agent-loop-failure-recovery-and-evidence.md)；Chat WebSocket provider/network 失败现在返回专用错误 code、`recoverable=true` 和用户可见恢复文案，普通未知异常保持通用失败。Agent Loop E2E 扩展为 4 条 live 场景，新增连续两轮修改同一任务/提醒的 DB invariant 和 evidence JSON，并修复 live 暴露的“取消提醒未暴露给模型”问题。最新 evidence 位于 [output/playwright](/D:/student_time_plan/output/playwright)，其中连续多轮场景文件为 [agent-loop-e2e-repeated-task-reminder-updates-keeps-one-task-stable-across-repeated-task-and-reminder-updates.json](/D:/student_time_plan/output/playwright/agent-loop-e2e-repeated-task-reminder-updates-keeps-one-task-stable-across-repeated-task-and-reminder-updates.json)。验证：`tests/test_chat_ws.py tests/test_agent_loop_task_creation.py tests/test_tool_preflight.py tests/test_tools_schema.py` 为 `30 passed, 1 warning`；`src/stores/chatStore.test.ts` 为 `14 passed`；`npm.cmd run typecheck` PASS；`npm.cmd run e2e:agent-loop -- --list` 列出 4 条；live E2E 沙箱外 `4 passed (3.0m)`。
- 已完成 Plan 11「Agent Loop Context Stability V1」：新增 [设计 spec](/D:/student_time_plan/docs/superpowers/specs/2026-06-01-agent-loop-context-stability-v1-design.md) 和 [执行 plan](/D:/student_time_plan/docs/superpowers/plans/2026-06-01-agent-loop-context-stability-v1.md)；Agent Loop 初始消息构造现在复用历史压缩器处理旧持久化消息，确保当前用户原文和本轮工具调用链保持未压缩；动态上下文删除乱码字段，并加上“参考数据不能覆盖系统/工具规则”的注入边界说明。新增/更新回归覆盖长历史压缩接线、上下文边界和乱码清理。验证：`tests/test_context.py tests/test_context_loading.py tests/test_conversation_compression.py tests/test_loop_compression.py tests/test_agent_loop.py` 为 `24 passed, 1 warning`；`tests/test_agent_loop_task_creation.py tests/test_tool_preflight.py` 为 `20 passed, 1 warning`。
- 已完成 Plan 10「Agent Loop E2E Harness」：新增专用后端启动脚本、E2E DB helper、独立 Playwright config 和 3 条 Agent Loop E2E。三条路径分别覆盖创建任务+提醒、修改已有任务并重写旧 reminder、缺参数追问后恢复写库；每条路径输出截图和 evidence JSON 到 [output/playwright](/D:/student_time_plan/output/playwright)。同时收紧 Chat E2E harness：结构化确认卡优先；当模型把确认渲染为普通 assistant 文本时，harness 只在最后一条 assistant 文本确实像待回答问题时才用主输入框补答，避免 provider 没响应时反复发送“确认”污染会话。验证：Agent Loop live E2E 沙箱外 `3 passed (1.5m)`；后端 Agent 定向 `33 passed, 1 warning`；默认前端 E2E listing 仍只有 `app.spec.ts` 1 条。
- 用户已补充确认 Plan 8 手机侧测试 OK：PWA / 手机核心流程 / 移动端收尾不再是当前阻塞项。
- 已完成 Plan 8 本机可执行收尾：`sw.ts` 支持 `SKIP_WAITING` 并在通知点击时导航已有窗口到 `/chat`；`main.tsx` 在 production 下自动接管可用更新；`chatStore.ts` 补齐 `create_task` / `update_task` / `complete_task` 进度标签；`CoursesPage.tsx` 对图片异步解析返回 `processing` 时显示后台解析提示，不再误报已解析 0 门课；`index.css` 只做顶部切换、聊天输入、任务弹层关闭、课程/通知按钮的触控目标微调。新增 [CoursesPage.test.tsx](/D:/student_time_plan/student-planner/frontend/src/pages/CoursesPage.test.tsx)，新增 [Android 包装评估](/D:/student_time_plan/docs/superpowers/specs/2026-04-21-android-packaging-evaluation.md)，结论为继续 PWA，TWA 作为 PWA 稳定后的候选，不现在引入 Capacitor。
- 已完成 Plan 9 Task 7「Agent routing and tool preflight evals」：`tool_preflight` 现在会在工具执行前检查 schema 必填参数和 enum 值，缺关键字段时不会把坏 tool call 暴露给前端或落库，而是把内部工具错误回传给 LLM 让它追问或重试；同时修复显式“不要/不提醒”时 `reminder_advance_minutes=None` 没有进入 `update_task` 的边界问题。新增回归覆盖：取消已有 task reminder、多轮更新时删除 reminder、`create_task` 缺 `scheduled_date` 被 preflight 拦截后通过 `ask_user` 恢复。验证结果：窄定向 `17 passed`，Plan 9 定向 `57 passed`，后端全量 `229 passed`。
- 已修复 2026-05-31 Agent E2E smoke 暴露的“修改任务时间时漏传提醒提前分钟”问题：新增 [tool_preflight.py](/D:/student_time_plan/student-planner/app/agent/tool_preflight.py)，在 `create_task` / `update_task` / `set_reminder` 执行前从用户已确认文本中提取低歧义提醒槽位（如“提前15分钟”“准点提醒”“不提醒”），并补齐或纠正 `reminder_advance_minutes` / `advance_minutes`；同时对“把已有任务改到/修改/调整”这类请求增加 task routing hint 和 create-task guard，防止模型把修改误走成新建。已补回归：[test_tool_preflight.py](/D:/student_time_plan/student-planner/tests/test_tool_preflight.py) 和 [test_agent_loop_task_creation.py](/D:/student_time_plan/student-planner/tests/test_agent_loop_task_creation.py)。验证结果：窄定向 `23 passed`，Plan 9 定向 `51 passed`，后端全量 `223 passed`。真实 smoke 已在 fresh backend 与当前 `5174 -> 8001` 链路通过：临时账号 `smoke_live_guard_1780231311195` 的 `linear algebra review` 从 `2026-07-26 15:00-16:00` 更新到 `2026-07-27 16:00-17:00`，`update_task` 实际参数包含 `reminder_advance_minutes=15`，最终只保留一条 `2026-07-27T15:45:00 / advance_minutes=15` reminder，无旧任务和旧 reminder 残留。当前 `8001` 后端已重启到当前源码，监听 PID 为 `41240`。
- 已完成 2026-05-31 Agent E2E smoke（子 agent + Playwright 真实浏览器）：当前本地有效入口是 `http://127.0.0.1:5174/chat`，其 `/api` 与 `/ws/chat` 指向 Student Planner 后端 `127.0.0.1:8001`。已有 `npm.cmd run e2e` 基础用例通过 `1 passed`，但只覆盖登录页。真实 Agent 创建路径已通过：临时账号输入“明天下午3点到4点提醒我复习线性代数，提前30分钟提醒”，确认后走通 `ask_user -> create_task -> set_reminder -> done`，数据库中任务与 reminder 正确落库。真实多轮修改路径暴露 bug：输入“把刚才的复习线性代数任务改到明天下午4点到5点，提前15分钟提醒”后，模型只把 `start_time/end_time` 传给 `update_task`，没有带 `reminder_advance_minutes=15`，导致任务时间已更新但旧 reminder 仍停留在 `14:30 / advance_minutes=30`。子 agent 证据文件位于 [output/playwright/smoke-b-evidence.json](/D:/student_time_plan/output/playwright/smoke-b-evidence.json)、[output/playwright/smoke-b-update-evidence.json](/D:/student_time_plan/output/playwright/smoke-b-update-evidence.json)，对应截图位于 [output/playwright/smoke-b-create-complete.png](/D:/student_time_plan/output/playwright/smoke-b-create-complete.png)、[output/playwright/smoke-b-update-complete.png](/D:/student_time_plan/output/playwright/smoke-b-update-complete.png)。
- 已修复 2026-05-01 真机通知页“看起来开启了，其实没订阅成功”的静默失败问题：后端新增 `/api/push/status` 只读状态接口，前端 [NotificationsPage.tsx](/D:/student_time_plan/student-planner/frontend/src/pages/NotificationsPage.tsx) 现在会同时显示通知权限 / 本机订阅 / 服务器订阅 / VAPID 配置状态；若浏览器里已有 `PushSubscription` 但后端未保存，会提示“重新同步”，并在点击“开启推送通知”时直接复用已有订阅回写服务端，不再盲目重复 `pushManager.subscribe()`。相关定向回归已通过：后端推送链 `12 passed`，前端通知页 `2 passed`，前端 build `PASS`，并已同步到部署机 `101.33.229.161`。
- 已定位并修复 2026-05-01 真机 PWA 提醒不弹窗的主阻塞：部署环境 `/opt/student-planner/shared/.env` 中 `SP_VAPID_PRIVATE_KEY` / `SP_VAPID_PUBLIC_KEY` 一直为空，导致 Web Push 无法完成订阅；同时数据库里 `users_with_push_subscription=0`，说明手机端此前也没有任何一次真正把订阅入库。现已在服务器生成并写入新的 VAPID 密钥、重启 `student-planner-backend`，并用本机回环 smoke 跑通了 `/api/push/vapid-key` 与 `/api/push/subscribe`。后续真机上仍需进入通知页手动点一次“开启推送通知”完成真实订阅。
- 已修复 2026-04-25 服务器课表文件导入回退到旧逻辑的问题：线上 `/opt/student-planner/current/app/agent/loop.py`、`tool_executor.py`、`services/schedule_parser.py` 与本地修复版哈希不一致，导致真机仍会复现旧的补信息提问与周次处理。现已同步这 3 个后端文件并重启 `student-planner-backend`；通过临时 HTTPS 入口做了真实 smoke：课表文件补充提问不再泄露 `missing_periods` / `missing_semester_fields`，确认卡恢复结构化 review，导入后的单周 / 双周 / 第 1 周课程都保留正确周次。
- 已修复 2026-04-25 真机 PWA 聊天页“加号无反应”问题：附件入口原先依赖 `button + ref.click()` 去触发一个 `display:none` 的文件输入，在手机/PWA 环境下不稳定。现已改为原生 `label[for=file-input]` 触发链，并保留键盘 fallback；前端全量测试 `74 passed, 2 skipped`、前端 build `PASS`。
- 已修复 2026-04-23 真机 PWA 聊天红字报错：服务器部署目录缺失 `Agent.md`，导致后端构造系统提示词时抛 `FileNotFoundError` 并返回“聊天暂时不可用，请稍后重试”。已补齐 `/opt/student-planner/current/Agent.md`，公网 WebSocket smoke 已验证 `connected`、流式文本与 `done` 正常返回。
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
1. 主线继续放在 Agent Loop 闭环稳定性。长历史/上下文注入边界、provider/network 可见恢复、连续任务/提醒 evidence 已分别在 Plan 11/12 收口；课表图片真实 OCR 已确认质量不达标；复习计划 live E2E 已确认“生成候选计划后确认写入任务”未闭环。下一步若继续 Agent Loop，应优先修复复习计划 review 确认后的结构化落库，再扩课程修改/删除歧义、课表解析确认后导入、记忆 recall/save 的确认边界。
2. 若后续日常手机自用暴露新问题，先写入 `bugs.md` 并只挑最高价值问题进入修复，不重开移动端大改。
3. Android 封装暂不启动；当前结论仍是继续 PWA，TWA 只作为以后有分发诉求时的候选。

## 下一 Session 第一件事
- 如果继续 Agent Loop：优先修“复习计划生成后写入任务”链路。建议先让 `create_study_plan` 返回的完整候选任务在 review `ask_user` 中保持结构化数据，并在用户确认后确定性地逐条调用 `create_task`，再复跑 `npm.cmd run e2e:agent-loop -- --grep "study plan" --reporter=list --global-timeout=420000`（沙箱外权限）。修复完成后再扩课程纠错/合并/删除或课表解析确认后导入的 live E2E。
- Plan 8 手机验收已由用户补充确认 OK；除非出现新问题，不再从移动端收尾继续。

## 当前阻塞 / 风险
- 用户真正指定的两张 `微信图片_20260419104519.jpg` / `微信图片_20260419104523.jpg` 是课表图；真实 OCR 测试会外发图片到 vision provider，需要用户明确授权后再跑。无授权时只做本地多图上传/合并探针、负向回归和 prompt/状态链路保护。
- 复习计划任务拆解目前只证明了“能生成候选计划”，还没有证明“确认后能稳定写入任务”。2026-06-02 live E2E 里 `create_study_plan` 成功返回 9 条候选任务，但后续未调用 `create_task`，最终 DB 里没有复习任务。对外表述时应说复习计划生成是候选能力，写入闭环仍待修复。
- Agent Loop live E2E 依赖真实 provider；普通沙箱可能报 `openai.APIConnectionError` / `WinError 5`，应按环境坑处理。判断代码闭环是否失败时优先看沙箱外运行结果、DB invariant、agent_logs 和 evidence JSON。
- 旧 session 的完整交接历史还没有单独归档成 `handoff` 文档；当前依赖本文件做滚动交接、依赖 `bugs.md` 保存长期问题。

## 真机自用待办池
- 自用问题记录机制：后续日常使用中遇到的问题持续写入 `bugs.md`，并区分致命、高摩擦、低优先级。
- App 封装预研：当前结论是继续 PWA，PWA 稳定后再考虑 TWA；暂不引入 Capacitor。

## 最近验证基线
- 最近一次学习计划拆解 live E2E 审计：`npm.cmd run e2e:agent-loop -- --list`（在 `student-planner/frontend`）列出 6 条 live 用例；`npm.cmd run typecheck` PASS；`npm.cmd run e2e:agent-loop -- --grep "study plan" --reporter=list --global-timeout=420000` 普通沙箱下信息不足用例通过、完整写入用例因 provider 失败/超时未通过；沙箱外权限重跑后信息不足用例仍通过，完整写入用例仍失败。失败证据：`create_study_plan` 生成 9 条候选任务，但没有后续 `create_task`，DB 最终 `tasks=[] / reminders=[]`。
- 最近一次课表图片解析负向回归：`C:\Users\Chen\anaconda3\python.exe -m pytest -q tests\test_agent_loop.py::test_schedule_import_shortcut_handles_empty_image_parse_without_review_card tests\test_schedule_ocr.py tests\test_schedule_import_api.py tests\test_schedule_tools.py`，`34 passed, 5 warnings`；warnings 为 openpyxl deprecation 和 `.pytest_cache` 写入权限。
- 最近一次 Plan 12 后端定向回归：`C:\Users\Chen\anaconda3\python.exe -m pytest -q tests\test_chat_ws.py tests\test_agent_loop_task_creation.py tests\test_tool_preflight.py tests\test_tools_schema.py`，`30 passed, 1 warning`；warning 为 `.pytest_cache` 写入权限。
- 最近一次 Plan 12 前端 store 回归：`npm.cmd test -- src/stores/chatStore.test.ts`（在 `student-planner/frontend`，沙箱外权限），`14 passed`；普通沙箱中 Vitest setup 绝对路径可能失败。
- 最近一次 Agent Loop live E2E：`npm.cmd run e2e:agent-loop -- --reporter=list --global-timeout=600000`（在 `student-planner/frontend`，沙箱外权限），`4 passed (3.0m)`。
- 最近一次 Agent Loop E2E 范围检查：`npm.cmd run e2e:agent-loop -- --list`（在 `student-planner/frontend`），列出 4 条 live 用例。
- 最近一次前端类型检查：`npm.cmd run typecheck`（在 `student-planner/frontend`），PASS。
- 最近一次 Plan 11 上下文稳定性定向回归：`C:\Users\Chen\anaconda3\python.exe -m pytest -q tests\test_context.py tests\test_context_loading.py tests\test_conversation_compression.py tests\test_loop_compression.py tests\test_agent_loop.py`，`24 passed, 1 warning`；warning 为 `.pytest_cache` 写入权限。
- 最近一次 Plan 11 Agent task/preflight 保护回归：`C:\Users\Chen\anaconda3\python.exe -m pytest -q tests\test_agent_loop_task_creation.py tests\test_tool_preflight.py`，`20 passed, 1 warning`；warning 为 `.pytest_cache` 写入权限。
- 最近一次 Agent Loop live E2E：`npm.cmd run e2e:agent-loop -- --reporter=list --global-timeout=420000`（在 `student-planner/frontend`，沙箱外权限），`3 passed (1.5m)`。
- 最近一次 Agent Loop 定向后端回归：`C:\Users\Chen\anaconda3\python.exe -m pytest -q tests/test_agent_loop_task_creation.py tests/test_agent_loop.py tests/test_tool_preflight.py`，`33 passed, 1 warning`；warning 为 `.pytest_cache` 写入权限。
- 最近一次默认前端 E2E 范围检查：`npm.cmd run e2e -- --list`（在 `student-planner/frontend`），只列出 `app.spec.ts` 1 条默认用例。
- 最近一次全量后端回归：`C:\Users\Chen\anaconda3\python.exe -m pytest -q`，`229 passed, 51 warnings`。
- 最近一次全量前端回归：`npm.cmd test`（在 `student-planner/frontend`），`79 passed, 2 skipped`。
- 最近一次前端构建：`npm.cmd run build`（在 `student-planner/frontend`），`PASS`。
- 最近一次 production preview 烟测：`npm.cmd run preview -- --host 127.0.0.1 --port 4173` 后验证 `manifest.webmanifest=200`、`/chat=200`。
- 最近一次 Plan 8 前端重点回归：`npm.cmd test -- src/stores/chatStore.test.ts src/pages/CoursesPage.test.tsx src/pages/ChatPage.test.tsx src/pages/NotificationsPage.test.tsx`，`54 passed, 2 skipped`。
- 最近一次 Task 2 定向前端回归：`npm --prefix student-planner/frontend test -- src/createClientId.test.ts src/stores/chatStore.test.ts src/pages/ChatPage.test.tsx`，`50 passed`。
- 最近一次 Task 2 定向后端回归：`py -3.12 -m pytest tests/test_chat_ws.py -v`，`4 passed`。
- 最近一轮 Chat 页定向回归：`npm --prefix student-planner/frontend test -- src/pages/ChatPage.test.tsx`，`38 passed, 2 skipped`。
- 最近一轮线上课表文件 smoke：通过 `https://browsing-gibson-cons-aggregate.trycloudflare.com` 注册临时账号、上传混合周次表格、补节次时间和学期信息、确认导入，最终 `/api/courses/` 返回的 `week_pattern` / `week_text` 与预期一致。
- 最近一轮线上推送链 smoke：部署机已生成非空 VAPID 键并重启后端；从服务器本机新注册临时账号后，`GET /api/push/vapid-key` 返回非空 `public_key`，`POST /api/push/subscribe` 返回 `{"status":"subscribed"}`，随后已清理临时假订阅，当前生产数据库再次回到 `users_with_push_subscription=0`。
## 2026-05-02 Agent 任务能力修复
- 已确认并修复一个真实线上能力错配：后端 HTTP 层一直支持 `POST /api/tasks/`，但 agent 工具层之前只有 `list_tasks / update_task / complete_task / set_reminder`，没有 `create_task`，导致真机对话里先口头承诺“我来帮你创建任务”，真正执行时却退化成 `update_task(task_id="new") -> Task not found`。
- 本地已补齐 `create_task` tool definition、tool executor 冲突校验、`update_task("new")` 明确错误提示，以及系统提示里的任务/提醒硬规则；定向回归 `32 passed`，其中包含新的 agent-loop 回归：`17.00提醒我去做饭` 现在能走通“确认 -> create_task -> set_reminder”。
- 服务器 `101.33.229.161` 已同步新的 `app/agent/tools.py`、`app/agent/tool_executor.py`、`app/agent/prompt.py` 并重启 `student-planner-backend.service`；远端已确认 `create_task` 同时存在于 `TOOL_DEFINITIONS` 和 `TOOL_HANDLERS`。
- 下一步需要用户在手机上复测两条真实路径：
  - `17点提醒我去做饭`
  - `下周四要考试，大学英语3，帮我做个复习计划吧`，并在确认后观察是否真正写入日程

## 2026-05-03 Reminder 路由调度修复
- 已定位昨天 `2026-05-02 19:20` 真机“创建了提醒但完全不弹”的直接根因：`/api/reminders/` 路由此前只写入 `reminders` 表，没有调用 `schedule_reminder_job`，所以提醒会永远停留在数据库 `pending` 状态，后台也没有任何 `fire_reminder` 执行日志。
- 本地已给 [reminders.py](/D:/student_time_plan/student-planner/app/routers/reminders.py) 补上“创建后立即 schedule / 删除时 cancel”逻辑，并补齐对应回归；当前任务链 + 提醒调度链定向回归共 `40 passed`。
- 服务器 `101.33.229.161` 已同步新的 `app/routers/reminders.py` 并重启 `student-planner-backend.service`；远端确认 `schedule_reminder_job` / `cancel_reminder_job` 已在路由中生效。
- 那条已经错过的旧提醒 `62b100df-611f-4077-9a39-ec5288dbf1fe` 为避免服务重启后补发迟到通知，已从 `pending` 改为 `failed`。后续请再创建一个未来几分钟的新提醒做真机复测。

## 2026-05-06 Task + Reminder 一体化修复
- 已确认当前真机问题不只是“推送不发”，而是“任务”和“提醒”仍然是松散分开的两套流程：日历页此前只调用 `/api/tasks/` 创建任务，不会同步创建 reminder；因此用户能看到 `11:01-11:31` 的任务，但数据库里实际挂在这条任务上的提醒却可能是完全不同的时间（例如 `22:55`），导致用户误以为“11:01 的提醒没有发”。
- 已在后端 [tasks.py](/D:/student_time_plan/student-planner/app/routers/tasks.py) 和 [task.py](/D:/student_time_plan/student-planner/app/schemas/task.py) 中新增 `reminder_advance_minutes` 支持：创建任务时可选同步创建 task reminder；更新任务时间时会同步重算已有 task reminder；删除任务时会同步取消并删除关联 reminder。
- 已在前端 [CalendarPage.tsx](/D:/student_time_plan/student-planner/frontend/src/pages/CalendarPage.tsx) 中把“添加任务”弹层扩成可选提醒模式，支持“不提醒 / 准点提醒 / 提前15分钟 / 提前30分钟 / 提前1小时”，并透传到 `/api/tasks/`。
- 本地定向验证已通过：
  - 后端 `test_tasks.py + test_reminders.py + reminder scheduler` 共 `18 passed`
  - 前端 `CalendarPage.test.tsx` `8 passed`
  - 前端 build `PASS`
- 服务器 `101.33.229.161` 已同步新的 `app/routers/tasks.py`、`app/schemas/task.py` 和前端 build 产物，并重启 `student-planner-backend.service`；远端已确认 `TaskCreate` 现在包含 `reminder_advance_minutes`，且 `tasks` 路由中存在 reminder 同步逻辑。
- 仍待最终真机确认的一点：远端“临时账号 -> 直接调 `/api/tasks/` -> 检查 `/api/reminders/`”的本机 smoke 在 SSH 下超时，因此这轮我不宣称线上已百分百实测成功；下一步应直接在手机上新建一个 5 分钟后的任务，并在创建时明确选中“准点提醒”或“提前15分钟”进行真机验证。
## 2026-05-09 Scheduler 自启动兜底修复
- 已继续收窄真机不弹提醒的根因：`2026-05-09 11:20` 的 `去做饭` 任务与对应 reminder 都已正确落库，但 reminder 一直停在 `pending`，而 `journalctl` 在 `11:20` 时间窗没有任何 `fire_reminder` 执行痕迹，说明问题已经不在前端传参或写库，而在调度执行层。
- 已在 [reminder_scheduler.py](/D:/student_time_plan/student-planner/app/services/reminder_scheduler.py) 中增加兜底：`schedule_reminder_job()` 现在会在 scheduler 未运行时先 `start()`，并把已经到点/刚过点的 `fire_time` 钳到 `now`，避免整分创建或 scheduler 停止时 job 被静默丢失。
- 本地 scheduler 相关回归 `8 passed`；服务器 `101.33.229.161` 已同步新的 `app/services/reminder_scheduler.py` 并重启后端。
- 为避免服务重启后补发一串过期提醒，这次同步前已把数据库中 `6` 条“已经过期但仍是 pending”的旧 reminder 统一改为 `failed`；当前库里不再残留过期 pending reminder。
- 下一步仍需用户在手机上新建一个 5 分钟后的任务提醒做真机验证；如果再失败，要继续查的是“生产进程里 APScheduler 运行态与 job 注入时机”，而不是权限/VAPID。
## 2026-05-09 推送链最终定位与下一步建议
- 本轮已经把应用层可见的问题基本排干净：task/reminder 一体化创建、`/api/reminders/` 写库后立即 schedule、scheduler 未启动时自启动、到点 pending reminder 的定时 sweep、`send_push()` 的超时与广义异常兜底都已补上，本地相关定向回归通过。
- 线上真实定位结果已经收敛到“服务器出网到 Google/FCM 不通”：
  - 服务器直连 `fcm.googleapis.com:443` 超时；
  - 服务器上的 `gost.service` 虽然在跑，监听 `:18080`，但走该代理访问 `fcm.googleapis.com` / `www.google.com` 都失败（HTTP CONNECT 返回 `503`，SOCKS5 返回连接完成失败）；
  - 直接用用户真实 push subscription 在服务器上调用 `send_push()`，得到的明确错误是 `Failed to establish a new connection: [Errno 101] Network is unreachable` 指向 `fcm.googleapis.com`。
- 因此当前阻塞点已经不是 Student Planner 代码逻辑，而是部署环境网络能力：这台大陆测试机既不能直连 Google/FCM，也不能通过现有 gost 代理打通该链路。
- 下一 session 最现实的两条路：
  1. 优先检查/修复服务器上的代理链（`gost -> 上游节点 -> Google/FCM`），确认能从服务器访问 `https://fcm.googleapis.com`；
  2. 如果不继续折腾大陆服务器，改走“本地电脑开 VPN + 本地运行后端 + 临时 HTTPS 暴露给手机”的方案做真机推送验证。该方案要求测试期间电脑、后端进程和 VPN 都保持在线。
- 本轮停在“记录并交接”，不再继续改代码；下个 session 请先按上面两条路线二选一，再继续推进真机提醒验证。

## 2026-05-24 失效 gost 代理清理
- 已登录测试服务器 `101.33.229.161` 确认代理现状：`/root/.bashrc` 曾把 `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` 指向 `http://127.0.0.1:18080`，但 `gost` 上游 `67.209.185.22:6758` 已拒绝连接，导致所有走本地代理的请求返回 `CONNECT tunnel failed, response 503`。
- 已按“停用并备份”方式清理坏代理：`gost.service` 已不再被 systemd 加载，`:18080` 已不再监听；`/root/.bashrc` 中三条代理变量已注释，备份保留在 `/root/.bashrc.proxybak.*`，旧 unit 备份保留在 `/root/gost.service.bak`。
- 清理后新 SSH 登录环境已无 `http_proxy` / `https_proxy` / `all_proxy` 变量；`127.0.0.1:8000` 后端和 `127.0.0.1:8080` Nginx 仍在运行。直接访问 `https://fcm.googleapis.com` 仍超时，因此删除坏代理只是避免误走坏链路，不代表大陆服务器已经能发 Web Push。

## 2026-05-17 方案 B 本地 VPN 推送验证
- 已按“本地电脑开 VPN + 本地后端 + localtunnel HTTPS 给手机”的方案完成一次真机推送验证。因本机 `127.0.0.1:8000` 已有 EngGo 后端占用，本轮 Student Planner 后端改跑 `0.0.0.0:8001`，前端 production preview 跑 `0.0.0.0:4173`，并通过 `STUDENT_PLANNER_BACKEND_ORIGIN=http://127.0.0.1:8001` 让 Vite proxy 指向正确后端。
- 本地 `.env` 原先 `SP_VAPID_PRIVATE_KEY` / `SP_VAPID_PUBLIC_KEY` 为空，本轮已生成本地测试 VAPID key；后端 `/api/push/status` 对登录用户返回 `vapid_configured=true`。
- localtunnel 第一轮地址为 `https://loud-rice-joke.loca.lt`，输入 tunnel password 后被 Vite preview Host 校验拦截；已在 [vite.config.ts](/D:/student_time_plan/student-planner/frontend/vite.config.ts) 加入 `preview.allowedHosts: ['.loca.lt']`，并把 `server/preview` proxy 统一为可配置的 `backendProxy`。前端 build 已通过。
- 当前可用的本地 HTTPS 入口为 `https://flat-parts-travel.loca.lt/register`；localtunnel password/IP 为 `156.229.160.167`。已从外部验证 `/chat`、`/register` 返回 `200`，`/api/push/status` 返回本地 Student Planner 后端的未登录 `403`。
- 账号 `111` 已完成真实手机 push subscription 写入，数据库里 `users.push_subscription` 非空。直接调用 `send_push()` 返回 `ok=True, status_code=201`，用户手机端确认收到一条测试推送。
- 手机端创建的 `10:48` 任务已同步生成 task reminder；对应 reminder `b8f5092d-cd85-4d5f-b103-d76bdeeb3e94` 在到点后从 `pending` 变为 `sent`。但用户随后明确说明没有看到 `10:48` 这条可见通知，因此本轮只能证明：本地可访问 FCM 的环境下，后端调度会执行并被 FCM accepted；尚未证明 scheduled reminder 能稳定在手机系统通知栏展示。下一步应继续查“FCM accepted 但设备未展示”的差异，而腾讯云环境失败仍应按“服务器到 FCM 出网不通”处理。
- 仍有一个新观察：本轮手机端创建的任务标题入库为 `혼넜레`，通知里也出现“Student...B / 一堆问号”之类乱码。用同一 API 通过标准 UTF-8 创建 `中文编码检查` 能正确入库，说明后端/SQLite/推送通道本身支持中文；后续若复现，应单独查 mobile/localtunnel 页面输入链路或该次测试输入来源的编码问题。
- 用户反馈未看到 `10:48 sent` 后，已继续定位出两个容易混淆的因素：
  - `pywebpush.webpush()` 默认 `ttl=0`，即 FCM 不会在设备暂时不可达时缓存消息；现已在 [push_service.py](/D:/student_time_plan/student-planner/app/services/push_service.py) 显式设置 `ttl=3600`，并补了 `tests/test_push_service.py` 断言。
  - 用普通沙箱/Node detached 启动的本地后端不能访问 `fcm.googleapis.com`，会导致 reminder job 执行后继续保持 `pending` 等待重试；方案 B 必须用沙箱外权限启动本地后端，当前有效后端 PID 为 `66860`，监听 `0.0.0.0:8001`。
- 干净复测结果：通过真实 `/api/tasks/` 创建 `11:15` 的 `TTL clean scheduled test`，对应 reminder `0e294d41-9694-45ad-8490-30cbe9b987a5` 到点后变为 `sent`；用户随后确认手机收到 Chrome 弹窗，测试任务已删除。因此在“沙箱外本地后端 + 可访问 FCM + Web Push TTL=3600”的路径下，scheduled task reminder 已完成后端调度、FCM accepted、手机通知展示闭环。
