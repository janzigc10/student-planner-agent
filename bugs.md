# Student Planner 已知问题与环境坑

## 2026-07-31 两阶段正式流程与本机环境已就绪
- `scripts/run_course_rag_benchmark_v2.py --formal` 已能按 `main development -> main test -> challenge holdout` 执行，并对 frozen gate、模型/检索合同及各层 hash 做强校验。用户已授权继续整理干净基线并执行唯一正式运行；基线建立前使用 native venv 重跑 RAG/LangGraph/Benchmark 合同为 `112 passed`，前端 Chat/store 为 `64 passed / 2 skipped`，typecheck、build、`py_compile`、corpus/challenge validator 和 `git diff --check` 均通过。
- 正式 runtime 禁止 Embedding、Reranker 与 Vector Store 静默 fallback。ignored 的 `student-planner/.venv-native/` 已安装项目依赖、`langchain-text-splitters`、OpenAI SDK、`chromadb 1.5.9` 和测试依赖；`_chroma_runtime_available()` 实测为 `(True, '')`。Anaconda 的 Chroma probe 仍会以 `3221225477` 失败，正式命令必须使用 `.venv-native\Scripts\python.exe`，不能改回 Anaconda。
- 只检查配置是否存在、不打印任何 secret 后，当前 `.env` 已满足 `embedding_provider=dashscope`、Embedding Key 已配置、`reranker_provider=qwen3`、Reranker Key 与 base URL 已配置。正式在线 endpoint 的实际连通性和配额只会在干净基线的唯一正式运行中验证。
- canonical 28 题 challenge 仍未运行任何指标。离线两阶段 smoke 使用的是测试临时目录中的 24 题 synthetic fixture，只验证控制流和防泄漏合同；不得把其输出解释为课程 benchmark 结果。

## 2026-07-30 Benchmark v2 challenge 已冻结，但尚未人工复核或正式运行
- 已创建 `student-planner/data/rag/course_challenge_v1/`：28 条与主集 ID/文本零重复的 holdout query、842 个四模式 Top-20 去重候选、逐题 qrels、冻结配置、内部 candidate pool、盲审 TSV/JSONL 和独立 review key；validator 已确认四门课各 7 条、七种 query type、`full 20 / partial 4 / none 4`，数据集 SHA-256 为 `9b3e603a58645929905335e7bf2cf3fb74f0501bfee166e55d412635c711edf5`。
- 当前 qrels 是模型编写难题规范加 deterministic source-truth 自动标签，证据等级保持 `llm_assisted_unreviewed`，`human_review_status=not_reviewed`。候选 pooling 使用本地 hash embedding 和 local-feature rerank，仅用于扩大判定覆盖，不是正式四模式结果。因此当前仍不得称为人工 gold、人工标注准确率或外部真实课程泛化；若不做人审，只能在论文中明确报告为“未人工复核的独立 synthetic challenge”。
- challenge 尚未运行任何正式指标。唯一一次正式读取其结果前，必须先用主集 development 完成 gate 选择并保存选中 config；之后不得根据 challenge 结果调参。旧在线 pilot 已查看完整主集结果，主集 56 条 test 仍标记为 `internal_test_exposed_by_pilot`。

## 2026-07-30 本机 Python 3.12 启动器缺少课程 RAG 切块依赖
- `py -3.12` 指向 `C:\Users\Chen\AppData\Local\Programs\Python\Python312\python.exe`，当前缺少 `langchain-text-splitters`，会在 `write_corpus_artifacts()` 报 `RuntimeError: langchain-text-splitters is required for course-rag-chunker-v1`。本轮没有擅自安装依赖，改用已有 `C:\Users\Chen\anaconda3\python.exe` 完成 v2 测试与离线 smoke。RAG runtime 测试 fixture 已显式清空 Embedding/Reranker 在线凭据，避免本地 `.env` 的真实配置污染单元测试。

## 2026-07-29 大学英语移除后旧在线评测已过期
- `data/rag/course_v1` 已冻结为论文基线 `rag-course-v1.1 / rag-course-golden-v1.1`：4 门课程、49 份资料、552 个 chunks、80 条查询和 2295 条 qrels，`corpus_manifest_sha256=8ac077eb690cba2db97fe1d3335a00b19d2a2f933a1b9e6a40cca723b93c52d7`。此前 `output/rag/course_v1_qwen_online_smoke/` 基于 5 门课程、689 chunks、100 条查询生成，其排序指标和逐题结果只能作为历史诊断，不能与当前语料版本混用；下一次正式比较使用新输出目录并记录当前 manifest hash，不再等待人工复核。

## 2026-07-29 评测输出目录复用会保留旧失败标记
- `scripts/evaluate_course_rag.py` 在失败时写入 `failed_run.json`，但之后若使用同一 `--output-dir` 成功重跑，不会删除旧失败文件，成功 `run_manifest.json` 还会把它列入 outputs。本次真实 Qwen comparison smoke 的第一次运行因受限网络失败、批准联网后复用同一目录成功，因此四个模式 JSONL、summary 和 chart 均为成功新结果，但目录内仍含第一次的旧 `failed_run.json`。正式论文运行必须使用全新空输出目录；后续可让 runner 在开始前拒绝非空目录或显式区分 attempt 子目录。
- 2026-07-30 v2 已修复：所有 run 在开始前拒绝非空输出目录；若 preflight 针对既有非空目录失败，failure manifest 写到目标目录旁边的新文件，不再向原目录加入旧失败标记。旧 `course_v1_qwen_online_smoke/failed_run.json` 仍是历史产物，不会自动清理。

## 2026-07-28 课程 RAG 正式评测的外部前置项
- 代码已实现 `qwen3-rerank` 的 OpenAI-compatible `/reranks` 合同，并通过 stub/失败合同测试；但当前账号所在地域/workspace 的真实 base URL、配额、计费与在线稳定性尚未用实际凭据验证。正式 `hybrid_rerank` benchmark 不允许 `LocalFeatureReranker` 静默替代，缺少配置或在线调用失败应让该 run 失败。
- `data/rag/course_v1` 的 80 条查询、2295 条 qrels 和 answerability/evidence requirements 是确定性生成的 synthetic 数据，manifest 明确标记 `human_review_status=synthetic_unreviewed`。因人力限制不执行人工复核，论文只能把指标解释为同一自动构造数据合同上的相对比较，不得称为人工 golden set、人工标注准确率、真实课程效果，也不能把离线 fallback smoke 宣传为真实 Qwen 或生产结论。

## 2026-06-21 追加：multi-exam study plan 已在 LangGraph worktree 修复
- 当前 `D:\tmp\student-planner-langgraph-final` worktree 中，上一条记录里的 `generates a multi-exam study plan with tasks for both exams` 不再是当前失败项。根因复核后确认：不是 `scope` 必填问题，而是模型在 `get_free_slots` 后绕过真实 `create_study_plan` 工具调用，输出了普通文本形式的伪 `[TOOL_SUMMARY:create_study_plan:*]` 和计划预览，导致没有 `create_study_plan` agent log、没有结构化 review、没有确认后 `create_task` 写库。
- 当前修复把 `scope` / `weak_areas` 保持为 exam 级选填字段；用户提供时按课程绑定，未提供时允许默认计划。同时对完整 ISO 日期考试复习请求走确定性 LangGraph study-plan workflow：`get_free_slots -> create_study_plan -> plan_review_write -> confirmed_write/create_task`。
- 验证：后端定向 `21 passed`；真实浏览器定向 `$env:AGENT_E2E_PYTHON='D:\tmp\student-planner-langgraph-final\student-planner\.venv-native\Scripts\python.exe'; $env:AGENT_E2E_DATABASE_URL='sqlite+aiosqlite:///./agent_loop_e2e_langgraph_multiexam_fix.db'; npm.cmd run e2e:agent-loop -- --grep "multi-exam" --reporter=list --global-timeout=420000` -> `1 passed (34.5s)`。
- 当前仍需另行处理的尾部项是 `adjusts an existing assignment plan to a lower daily limit`。它仍倾向于过期 E2E/日期窗口问题：测试创建的是 `2026-06-09/10` 任务，而当前日期已经是 `2026-06-21`，现有“未来 30 天”查询不会命中过去任务。

## 2026-06-21 LangGraph worktree 真实浏览器 E2E 复测结果
- 已修复相对主 tree 的明确回归：在 `D:\tmp\student-planner-langgraph-final\student-planner\frontend` 运行 `$env:AGENT_E2E_PYTHON='D:\tmp\student-planner-langgraph-final\student-planner\.venv-native\Scripts\python.exe'; $env:AGENT_E2E_DATABASE_URL='sqlite+aiosqlite:///./agent_loop_e2e_langgraph_fix.db'; npm.cmd run e2e:agent-loop -- --grep "assignment report plan|reschedules a confirmed plan task|keeps one task stable" --reporter=list --global-timeout=600000`，结果为 `3 passed (3.1m)`。对应截图：`D:\tmp\student-planner-langgraph-final\output\playwright\agent-loop-e2e-work-plan-confirmed-write-generates-an-assignment-report-plan-and-writes-confirmed-staged-tasks.png`、`D:\tmp\student-planner-langgraph-final\output\playwright\agent-loop-e2e-plan-write-active-reschedule-reschedules-a-confirmed-plan-task-when-the-original-slot-conflicts-before-write.png`、`D:\tmp\student-planner-langgraph-final\output\playwright\agent-loop-e2e-repeated-task-reminder-updates-keeps-one-task-stable-across-repeated-task-and-reminder-updates.png`。UI 复核：作业计划写入卡、冲突自动重排卡视觉正常；重复任务场景未再显示 `[TOOL_SUMMARY]` 到聊天 UI。
- 修复后全量真实浏览器 Agent Loop E2E：在同一目录运行 `$env:AGENT_E2E_PYTHON='D:\tmp\student-planner-langgraph-final\student-planner\.venv-native\Scripts\python.exe'; $env:AGENT_E2E_DATABASE_URL='sqlite+aiosqlite:///./agent_loop_e2e_langgraph_full_after_fix.db'; npm.cmd run e2e:agent-loop -- --reporter=list --global-timeout=900000`，结果为 `10 passed, 2 failed (12.2m)`。通过项已覆盖 RAG retrieval、task+reminder 创建、task/reminder 更新、重复 task 稳定复用、缺参数恢复、课程 rename、缺少考试信息追问、单考试复习计划写入、作业报告计划写入、冲突自动重排。
- 剩余失败 1：`generates a multi-exam study plan with tasks for both exams` 仍因 240s timeout 失败。UI 截图显示用户已提供两个考试、范围和每日 2 小时，但系统给出绿色“已完成”卡：“复习计划已经生成，但里面没有可写入日程的完整任务时间。请补充考试范围或每日可复习时间后再试。” 视觉排版可读，但语义状态误导。截图：`D:\tmp\student-planner-langgraph-final\student-planner\frontend\test-results\agent-loop-Agent-Loop-E2E--32be2-n-with-tasks-for-both-exams\test-failed-1.png`。主 tree 对照也失败，先按既有尾部质量问题处理，不单独归因于 LangGraph worktree。
- 剩余失败 2：`adjusts an existing assignment plan to a lower daily limit` 仍因 240s timeout 失败。UI 显示“我查了未来 30 天的任务，但没有找到包含「机器学习报告」的待办任务，所以没有做调整。” 视觉排版正常，失败点是功能语义：没有找到前置计划任务并调整。截图：`D:\tmp\student-planner-langgraph-final\student-planner\frontend\test-results\agent-loop-Agent-Loop-E2E--e885b-plan-to-a-lower-daily-limit\test-failed-1.png`。主 tree 对照也失败，先按既有尾部质量问题处理，不单独归因于 LangGraph worktree。
- 当前主 tree 复核：在 `D:\student_time_plan\student-planner\frontend` 运行 `$env:AGENT_E2E_BACKEND_PORT='8021'; $env:AGENT_E2E_FRONTEND_PORT='5188'; $env:AGENT_E2E_DATABASE_URL='sqlite+aiosqlite:///./agent_loop_e2e_main_remaining_compare.db'; npm.cmd run e2e:agent-loop -- --grep "multi-exam|lower daily" --reporter=list --global-timeout=600000`，结果为 `2 failed`，两条都是 240s timeout。因此这两条不是 LangGraph worktree 独有回归。
- 注意：`output/playwright/*.json` 作为测试证据仍会记录模型内部消息历史中的 `[TOOL_SUMMARY:*]`，这不是用户可见 UI；本次回归修复的是聊天事件流中把该文本当普通 assistant 文本渲染的问题。

## 2026-06-20 LangGraph worktree 真实浏览器 E2E 暴露的问题
- 命令：在 `D:\tmp\student-planner-langgraph-final\student-planner\frontend` 运行 `$env:AGENT_E2E_PYTHON='D:\tmp\student-planner-langgraph-final\student-planner\.venv-native\Scripts\python.exe'; $env:AGENT_E2E_DATABASE_URL='sqlite+aiosqlite:///./agent_loop_e2e_langgraph_browser.db'; npm.cmd run e2e:agent-loop -- --reporter=list --global-timeout=900000`。结果：12 个 Playwright 真实浏览器用例中 7 个通过，4 个失败，1 个因全局超时未完整执行；`.last-run.json` 状态为 `timedout`。
- 作业/assignment plan 路由回归：`generates an assignment report plan and writes confirmed staged tasks` 和 `reschedules a confirmed plan task when the original slot conflicts before write` 都把“2026-07-03 要交机器学习报告，帮我拆成任务”显示为“当前知识库没有足够资料，无法基于本地资料可靠回答这个问题”，没有进入 work-plan 追问、review 卡片或确认后写任务链路。截图：`student-planner/frontend/test-results/agent-loop-Agent-Loop-E2E--1d6e2-ites-confirmed-staged-tasks/test-failed-1.png`、`student-planner/frontend/test-results/agent-loop-Agent-Loop-E2E--424ff-slot-conflicts-before-write/test-failed-1.png`。
- 多考试复习计划回归：`generates a multi-exam study plan with tasks for both exams` 超时，UI 显示绿色完成卡“复习计划已经生成，但里面没有可写入日程的完整任务时间”，并提示补充范围/每日可复习时间；这与用户已提供两个考试日期、范围和每日 2 小时的输入不一致，也会让用户误以为流程已完成。截图：`student-planner/frontend/test-results/agent-loop-Agent-Loop-E2E--32be2-n-with-tasks-for-both-exams/test-failed-1.png`。
- 用户可见内部摘要泄露：`keeps one task stable across repeated task and reminder updates` 超时前，Playwright snapshot 中出现用户可见的 `[TOOL_SUMMARY:update_task:v1] {...}` 段落。该内容属于内部工具摘要，不应显示在聊天 UI；同时该路径应验证同一 task 被复用且旧 reminder 删除。截图：`student-planner/frontend/test-results/agent-loop-Agent-Loop-E2E--df7d3-d-task-and-reminder-updates/test-failed-1.png`，error context 记录了该内部摘要文本。
- 主 tree 对照：在 `D:\student_time_plan\student-planner\frontend` 运行 `$env:AGENT_E2E_BACKEND_PORT='8021'; $env:AGENT_E2E_FRONTEND_PORT='5188'; $env:AGENT_E2E_DATABASE_URL='sqlite+aiosqlite:///./agent_loop_e2e_main_compare.db'; npm.cmd run e2e:agent-loop -- --grep "assignment report plan|reschedules a confirmed plan task|multi-exam|keeps one task stable|lower daily" --reporter=list --global-timeout=600000`，结果为 5 个对照用例中 3 个通过、2 个失败。主 tree 通过了 `keeps one task stable across repeated task and reminder updates`、`generates an assignment report plan and writes confirmed staged tasks`、`reschedules a confirmed plan task when the original slot conflicts before write`；因此 worktree 在作业计划路由和重复任务可见输出上相对主 tree 有明确回归。主 tree 也超时的 `multi-exam` 与 `lower daily limit` 先按既有尾部问题或测试脆弱性处理，不能单独归因于 LangGraph worktree。
- 已通过的真实浏览器场景包括：LangGraph RAG retrieval event、创建 task+reminder、更新 task 并改写 reminder、缺参数恢复后写库、课程 rename、缺少考试信息时追问、单考试复习计划确认写入。通过用例截图保存在 `D:\tmp\student-planner-langgraph-final\output\playwright\agent-loop-e2e-*.png`；其中单考试复习计划成功卡片视觉正常，显示“已把 6 条复习任务写入日程”与记录数徽标。

## 2026-06-19 LangGraph WS smoke harness 坑
- PowerShell inline Python / WebSocket smoke 中，中文 prompt 和确认答案容易因为 shell/console 编码或测试桩字符串匹配出现误判；做 LangGraph action live smoke 时，优先使用文件化 Python/Node/Playwright harness，或在 prompt 中加入 ASCII anchor，同时确认最终发送给 `/ws/chat` 的 JSON 是 UTF-8。
- `websockets.connect()` 默认 `max_size=1048576`，遇到课表/计划 review card 这种较大 payload 时可能以 `1009 message too big` 关闭连接；真实 backend smoke 建议显式传 `max_size=None`。
- 本轮临时 OpenAI-compatible stub 对 `ask_user` 恢复后的 messages 重建不够稳，可能重复发 `ask_user` 或工具调用，导致 `Agent loop reached the maximum number of iterations.`；这类失败先归因到 harness，需用事件流、DB invariant 和代码级 action graph tests 交叉判断，不要直接当成产品链路失败。

## 长期环境约束
- 当前 PATH 上的默认 `python` 不是项目测试使用的版本；后端测试统一使用 `py -3.12 -m pytest`。
- `py -3.12 -m pip install -e ".[dev]"` 仍会因为 setuptools 顶层包识别冲突失败；当前做法是安装 `pyproject.toml` 中的直接依赖与测试依赖继续验证。
- Python 3.12 环境需要保留 `openai` 依赖，认证相关依赖需保持 `bcrypt<5`。
- 2026-06-13 确认 Chroma 本地向量引擎在当前 Anaconda Python 3.12 环境不可直接依赖：`chromadb` 1.5.9、1.4.1、1.0.21 都会在 `collection.upsert()` 触发 native access violation，退出码 `3221225477`；`chromadb` 0.4/0.5 需要编译 `chroma-hnswlib`，本机没有 Microsoft Visual C++ Build Tools，安装失败。改用系统原生 Python 3.12 创建的 `student-planner/.venv-native` 后，`chromadb 1.5.9` 的 upsert/query 和真实 RAG Chroma 持久化均已通过。当前 RAG 代码仍会先用 subprocess 探针检测 Chroma，失败时自动退到 SQLite 持久化 fallback，避免主进程崩溃和重复 embed 文档库。
- 2026-06-14 隔离 worktree `D:\tmp\student-planner-langgraph-final` 首次执行 Git 时也会触发 `dubious ownership`，需要加入 `safe.directory`；不能只给主仓库 `D:\student_time_plan` 配 safe directory。
- 2026-06-14 在 native venv 跑 pytest 时，默认临时目录 `C:\Users\Chen\AppData\Local\Temp\pytest-of-Chen` 可能报 `PermissionError: [WinError 5] 拒绝访问`；本 worktree 的可行做法是先设置 `TMP` / `TEMP` 为 `D:\tmp\pytest-tmp-native`，再运行 `.\.venv-native\Scripts\python.exe -m pytest ...`。
- 后端全量 `py -3.12 -m pytest -q` 若与前端 `npm test` / `npm run build` 并行执行，测试共享的 SQLite `test.db` 偶发会在 teardown 报 `database is locked`；基线验证请串行跑，若遇到该报错先单独重跑后端全量确认。
- PWA 真机安装不能直接依赖局域网 HTTP 地址；`http://<LAN-IP>:4173` 下 `navigator.serviceWorker` 不可用，后续 Task 3 需要先准备 HTTPS origin（临时隧道、同域 HTTPS 环境或受信本地证书）。
- 当前临时 HTTPS 方案使用 Cloudflare Quick Tunnel：地址是随机的 `trycloudflare.com` 子域名，服务重启后 URL 可能变化，且官方明确说明这类 account-less tunnel 没有 uptime guarantee，不适合作为长期正式入口。
- `rg.exe` 在当前环境可能无法执行，检索时改用 PowerShell 的 `Get-ChildItem` 与 `Select-String`。
- PowerShell 写文件要避免 UTF-8 with BOM，防止 `pyproject.toml` 等文件解析失败。
- 首次在该仓库执行 git 操作时，若触发 `dubious ownership`，需要先把 `D:\student_time_plan` 加入 git `safe.directory`。

## 已确认并需要记住的问题
- 2026-06-02 已修复复习计划任务拆解 live E2E 暴露的确认写入缺口：旧问题是对“下周四（2026-06-11）有大学英语3考试，帮我做一个复习计划”这类完整请求，Agent 能先确认考试信息并生成候选复习任务，但用户确认后没有稳定逐条调用 `create_task`，导致 `tasks=[] / reminders=[]`。根因是 `create_study_plan` 的候选任务没有在 review/确认链路中被确定性保留和落库；后续 live 还暴露过模型会把 `available_slots` 压缩成摘要，导致 `create_study_plan` 参数不完整。当前修复是在 `create_study_plan` 成功后立即发结构化 review `ask_user`，确认后由本地确定性分支逐条调用 `create_task`，并在模型传摘要 `available_slots` 时复用最近一次真实 `get_free_slots` 结果。验证：后端定向 `35 passed, 1 warning`，前端 typecheck PASS，沙箱外 `npm.cmd run e2e:agent-loop -- --grep "study plan" --reporter=list --global-timeout=420000` 为 `2 passed (56.0s)`。
- 2026-06-01 真实课表截图 OCR 质量问题：用户指定的两张课表图 `C:\Users\Chen\Desktop\微信图片_20260419104519.jpg`（第 3 周）和 `C:\Users\Chen\Desktop\微信图片_20260419104523.jpg`（第 4 周）通过真实 vision provider 后，上传/异步状态链路能完成，但 OCR 输出明显错误。问题包括：竖排课程名被拆成多门课，例如“机器人流程自动化”被拆成“机器人程动 / 流自化”等；“大学生就业指导”被拆成“大生业导 / 学就指导”；第 4 周图出现 weekday 左移，把周三/周四识别成周二/周三；最终两图合并得到 `count=13`，而人工核对应为 6 条。结论：图片上传、轮询、合并状态链路通，但真实 OCR 质量暂不达标；后续如果要继续课表图片能力，优先改 OCR prompt/后处理/视觉解析策略，而不是再查上传链路。
- 2026-06-01 Plan 12 live E2E 曾暴露一个已修复的能力表缺口：连续修改同一个普通任务时，用户第二轮说“不提醒/取消提醒”，模型会回复“没有删除提醒工具”，因为 `update_task` 工具描述和 Agent 规则没有明确暴露 `reminder_advance_minutes=null` 可以删除已有 task reminder。现已在 `tools.py`、`Agent.md`、`prompt.py` 和 task routing hint 中补齐，并用 `test_tools_schema.py` 锁住契约；沙箱外 live E2E 已通过 `4 passed (3.0m)`，连续多轮 evidence 确认同一个 task 被复用且旧 reminder 不残留。
- 2026-05-31 已修复上一条 Agent E2E 暴露的核心参数丢失：当前源码在 `run_agent_loop` 执行工具前会做 `tool_preflight`，把用户明确表达的“提前 N 分钟 / 准点 / 不提醒”补齐到 `create_task` / `update_task` 的 reminder 参数；同时当用户明确是“修改已有任务”时，会给 LLM task routing hint，并在 LLM 误调 `create_task` 时用内部工具错误拦截，要求改走 `list_tasks -> update_task`。后续 Task 7 又补上通用 required-slot/schema guard：工具缺必填参数或 enum 值非法时，不执行、不落库、不向前端暴露坏 tool call，而是把内部错误回传给 LLM 修正；显式“不提醒/取消提醒”现在会传入 `reminder_advance_minutes=None` 删除已有 task reminder。最新验证：preflight/Agent task 定向 `17 passed`，Plan 9 定向 `57 passed`，后端全量 `229 passed`；当前 `5174 -> 8001` 真实链路 smoke 已通过，`update_task` 参数包含 `reminder_advance_minutes=15`，数据库最终无旧 task/reminder 残留。
- 2026-05-31 Agent E2E smoke 确认：真实创建任务+提醒路径可以跑通，但“多轮修改任务时间+提醒提前分钟”仍会分叉。复现路径是在 `http://127.0.0.1:5174/chat` 登录临时账号后，先创建“明天下午3点到4点提醒我复习线性代数，提前30分钟提醒”，再说“把刚才的复习线性代数任务改到明天下午4点到5点，提前15分钟提醒”。结果是 `update_task` 只收到 `start_time/end_time`，没有收到 `reminder_advance_minutes=15`；任务时间会更新，但旧 reminder 仍停在 `14:30 / advance_minutes=30`。这不是后端 task/reminder 同步 API 的单元回归失败，而是 Agent 工具调用层没有把提醒修改意图稳定路由进 `update_task.reminder_advance_minutes`。
- 旧版本地数据库可能停留在 `courses.week_type` schema；如果再次出现 `no such column: courses.week_pattern`，优先检查 Alembic 版本并执行兼容迁移 `c4c3b8a92f1d`。
- WebSocket 重连曾导致旧确认卡片仍可见但 answer 落到新会话；相关保护已修复，但若再次出现类似“确认后不继续”，先检查 `pendingAsk` 清理和后端等待态。
- `schedule_parser` 曾把 `1-16周` 误识别为节次，并在空行分块时把“操场”拆成独立课程；相关回归测试已经补齐，后续改解析逻辑时需要重点回归。
- IAB 或本地撤销可能把 `student-planner/frontend/src/pages/ChatPage.tsx` 写入 Git 冲突标记；如果前端突然无法编译，优先全局检索 `<<<<<<<|=======|>>>>>>>`。
- 2026-05-01 确认过一条容易误判的推送坑：仅在手机系统里给已安装 PWA / Chrome 开通知权限，不代表项目已经完成 Web Push 订阅。当前前端只有在 `/me/notifications` 页点击“开启推送通知”时才会调用 `pushManager.subscribe()` 并把订阅写入后端；如果部署环境缺失 `SP_VAPID_PRIVATE_KEY` / `SP_VAPID_PUBLIC_KEY`，这一步会根本走不通，数据库里 `users.push_subscription` 也会保持为空。
- 2026-05-01 又确认了一条前端侧静默失败坑：如果浏览器本地已经残留 `PushSubscription`，但服务器端 `users.push_subscription` 为空，旧版通知页会继续直接调用 `pushManager.subscribe()`，失败时也没有任何用户可见错误，因此看起来“权限都开了”但后端始终是 `0` 订阅。现已改成先读本机订阅和 `/api/push/status`，必要时复用现有订阅重新同步，并显示明确错误/状态文案。

## 已延期但仍待处理
- Plan 8 手机侧测试已由用户补充确认 OK；PWA 安装、独立窗口、冷启动、登录、聊天、课表图片导入、确认导入、日历查看、课程编辑、推送展示和通知点击跳转不再列为当前待补验项。
- Chat 确认后空窗和课表图片异步解析反馈的前端代码侧已补齐；若手机实测仍有摩擦，按真实路径重新记录到“高摩擦”问题后再修。

## 近期确认的部署坑
- 2026-06-01 Agent Loop live E2E 环境坑：`npm.cmd run e2e:agent-loop -- --reporter=list --global-timeout=600000` 在普通沙箱里可能因为后端访问 live LLM provider 失败而卡住，失败特征是前端反复出现“确认”后报“聊天暂时不可用，请稍后重试”，后端日志出现 `openai.APIConnectionError` / `PermissionError: [WinError 5] 拒绝访问。`。同一套 harness 在沙箱外权限下已通过 `4 passed (3.0m)`；因此后续判断 Agent Loop live E2E 结果时，需要区分代码闭环失败和沙箱网络失败。
- 2026-05-31 本地 smoke 额外确认：当前打开的 `5174` 页面如果连着旧 `8001` 进程，会复现旧工具结果和旧 reminder 分叉；修改 Agent 后必须重启 `8001` 后端，不能只看源码测试通过。另一个本地测试坑是 PowerShell here-string 管道给 `python -` 时中文可能变成 `???`，会让意图识别 smoke 失真；需要用真实浏览器输入、Node/Playwright，或在 Python smoke 中使用 Unicode escape。
- 2026-05-31 本地 E2E 入口确认：`5174 -> 8001` 是当前可用的 Student Planner 前后端组合，`5174/ws/chat` 可以握手；`5173` 虽能返回前端 HTML，但 `/api/auth/me` 为 `404`，不适合作为当前 smoke 入口；`8000/health` 返回的是 EngGo，不是 Student Planner。现有 `student-planner/frontend` 的 Playwright 配置仍默认使用 `5173`，因此只跑 `npm.cmd run e2e` 容易得到误导性的“通过”。
- 服务器部署目录必须包含 `student-planner/Agent.md`。如果 `/opt/student-planner/current/Agent.md` 缺失，后端在构造系统提示词时会抛 `FileNotFoundError`，前端聊天会显示“聊天暂时不可用，请稍后重试”。2026-04-23 已在临时 HTTPS 服务器补齐该文件，并用公网 WebSocket smoke 验证普通聊天恢复。
- 2026-04-25 出现过“本地已修、线上仍复现旧课表导入问题”的部署回退：腾讯云测试机上的 `/opt/student-planner/current/app/agent/loop.py`、`tool_executor.py`、`services/schedule_parser.py` 哈希一度落后于本地工作树，导致真机仍会看到旧的补信息提问和错误周次结果。后续每次声称“已部署”前，都先比对这几份关键文件哈希并重启 `student-planner-backend`。

## 不要重复走的失败路径
- 不要把 `AGENTS.md` 当成长期 session 流水账；历史过程应压缩为当前快照或单独归档。
- 不要在未确认设计变更时直接改实现；先记录问题，再决定是否调整 spec / plan。
- 不要把移动端/PWA 的附件入口继续做成“`button` 调 `ref.click()` + `display:none` 文件输入”的组合；2026-04-25 已确认这会导致真机上聊天页加号点击无反应。优先使用原生 `label[for=file-input]` 或其他保留原生文件选择交互链的实现。
## 2026-05-02 新确认的能力错配坑
- agent 工具层与 HTTP/数据库真实能力不一致时，真机对话会出现“先承诺能做，执行时才翻车”的假成功。
- 线上已确认案例：`2026-05-02 16:57` 的“17.00提醒我去做饭”会话里，assistant 先承诺“创建做饭任务”，随后实际只调用了 `list_tasks`，接着错误地调用 `update_task(task_id="new")`，最后才返回 `Task not found`。
- 根因不是数据库或提醒服务挂了，而是当时 agent 只有 `update_task` 没有 `create_task`，模型在能力表不完整的情况下自己脑补了“可创建”。
- 后续凡是新增了 HTTP/后端能力，尤其是 `task / reminder / study plan` 相关，都要同步检查 `app/agent/tools.py`、`app/agent/tool_executor.py`、`Agent.md / system prompt` 是否同时更新；只改 API 不改 agent，会在真机真实对话里以“先答应后打脸”的形式暴露出来。

## 2026-05-03 新确认的提醒调度坑
- `/api/reminders/` 路由之前只负责写库，不负责把新 reminder 挂进 APScheduler；因此用户在 UI/真机上“成功创建提醒”后，数据库里能看到 `reminders.status='pending'`，但后台完全没有 `fire_reminder` 日志，提醒也就永远不会真正发送。
- 线上已确认案例：用户 `96a50612-9a83-44c0-a826-06e035cd999c` 的任务 `去洗澡`（`2026-05-02 19:20-19:50`）对应 reminder `62b100df-611f-4077-9a39-ec5288dbf1fe` 一直停在 `pending`，直到人工排查才发现根因是路由漏掉了 `schedule_reminder_job`。
- 结论：任务/课程 reminder 不能只测数据库写入成功，还要确认创建路径调用了 `schedule_reminder_job`，删除路径调用了 `cancel_reminder_job`；否则看起来“提醒创建成功”，实际上只是写了一条永远不会被执行的记录。

## 2026-05-06 新确认的任务/提醒分叉坑
- 仅仅“创建了任务”不等于“创建了这个任务对应时间的提醒”。此前日历页 `/calendar` 的“添加任务”弹层只调用 `/api/tasks/`，不会一起创建 reminder；因此用户在 UI 里看到 `11:01-11:31` 的任务时，很容易误以为这条任务天然带有 `11:01` 的提醒，但数据库里根本可能没有对应 reminder，或者 reminder 挂成了别的时间。
- 线上已确认案例：`2026-05-03 11:01` 的 `去洗澡` 任务存在，但对应 reminder 实际是 `2026-05-03T22:55:00`；因此“11:01 没弹”不是推送链当时没发，而是系统根本没把这条任务当成 `11:01` 的提醒来调度。
- 结论：后续任务创建入口必须显式暴露 reminder 选项，并且由后端在同一个 task 路径里负责 task/reminder 一体化创建与同步；否则前端、agent 和提醒系统各走各的，用户只会看到“任务时间”和“提醒时间”分叉。
## 2026-05-09 新确认的 scheduler 运行态坑
- 即使 task reminder 已经正确写入数据库，也不代表它一定会按时触发。线上 `2026-05-09 11:20` 的 `去做饭` 案例表明：`tasks` 和 `reminders` 记录都存在且时间正确，但 reminder 仍然卡在 `pending`，同时后台在对应时间窗没有任何 `fire_reminder` 执行日志。
- 这说明还存在一层调度器运行态风险：创建 reminder 时如果生产进程内的 APScheduler 没有真正处于运行态，或者 run_date 已经擦边过去，job 会被静默丢掉，只留下数据库里的 `pending` 记录，让用户误以为“提醒系统没发”。
- 当前兜底修法已加入：`schedule_reminder_job()` 在 scheduler 未运行时会先自启动，并且对 `fire_time <= now` 的提醒直接钳到 `now`。如果后续真机仍复现“库里有 pending、日志里没 fire”，就要继续检查生产进程内 scheduler 的真实运行态，而不是再回头怀疑前端权限或 VAPID。
## 2026-05-09 新确认的部署网络阻塞
- 当前测试服务器 `101.33.229.161` 上，Student Planner 应用层已经能正确创建 task/reminder，也能把 due reminder 从数据库里捞出来执行；但真正发 Web Push 的最后一跳被部署环境网络拦住。
- 已确认的硬证据：
  - 服务器直连 `fcm.googleapis.com:443` 超时；
  - `gost.service` 在跑，监听 `:18080`，但走它访问 `fcm.googleapis.com` 和 `www.google.com` 都失败；
    - HTTP 代理方式：`CONNECT tunnel failed, response 503`
    - SOCKS5 方式：`Can't complete SOCKS5 connection`
- 对用户真实 subscription 在服务器上直接调用 `send_push()`，返回 `HTTPSConnectionPool(... fcm.googleapis.com ...) Failed to establish a new connection: [Errno 101] Network is unreachable`。
- 结论：如果部署环境不能访问 Google/FCM，那么前端权限、VAPID、scheduler、task/reminder 写库都修好也没法让手机收到推送。后续别再把这个问题误判成“页面没传对提醒时间”或“应用没 schedule”。
- 2026-05-24 已确认旧 `gost` 上游拒绝连接，并已停用/备份坏代理：`gost.service` 不再加载，`:18080` 不再监听，`/root/.bashrc` 里的 `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` 已注释。清理后服务器直连 FCM 仍超时，所以后续若继续用这台大陆机，需要配置新的可用代理；否则直接切到“本地电脑开 VPN + 本地部署 + 手机 HTTPS 访问”的验证路径。

## 2026-05-17 本地方案 B 验证坑与新观察
- 本机 `127.0.0.1:8000` 可能被其他项目占用；本轮实际发现 EngGo 后端占用了 `127.0.0.1:8000`，而 Student Planner 绑定 `0.0.0.0:8000` 后，`localhost:8000` 仍会落到 EngGo。后续本地方案 B 推荐直接使用 Student Planner 后端 `8001`，并通过 `STUDENT_PLANNER_BACKEND_ORIGIN=http://127.0.0.1:8001` 指定前端 proxy。
- 本地 `.env` 里的 VAPID key 可能为空；若 `/api/push/status` 显示 `vapid_configured=false`，先补 `SP_VAPID_PRIVATE_KEY` / `SP_VAPID_PUBLIC_KEY`，否则手机只能授权，无法完成真实 Web Push 订阅。
- `localtunnel` 会先要求输入 tunnel password/IP，本轮值为 `156.229.160.167`；这个不是应用登录，也不是后端鉴权。
- Vite preview 默认会拒绝 `*.loca.lt` Host，表现为 localtunnel 进入后出现 HTTP 400/403，响应体包含 `Blocked request. This host (...) is not allowed.`。修法是把 `.loca.lt` 加入 `preview.allowedHosts`。
- 本地方案 B 已证明“直接测试推送”链路可通：账号 `111` 写入真实 FCM subscription；直接 `send_push()` 返回 `201`；用户手机收到测试推送。随后 `10:48` task reminder 到点后状态从 `pending` 变为 `sent`，但用户明确说明没有看到这条 `10:48` 可见通知。后续要把 `sent` 理解为后端/FCM accepted，不要等同于设备已展示；若数据库已从 `pending` 变为 `sent` 但手机没弹，应继续查 service worker 展示条件、payload、前后台状态和浏览器通知策略。
- 待查新观察：本轮手机端创建的任务标题入库为 `혼넜레`，通知文本也出现问号乱码；但用同一 API 发送标准 UTF-8 JSON 创建 `中文编码检查` 能正确入库。因此这不是后端/SQLite 对中文的通用不支持，更像 mobile/localtunnel 页面输入链路或临时测试输入的编码异常。若再次复现，请记录输入前的原文、页面、浏览器/PWA 状态和数据库实际标题。
- 新确认一条 Web Push 默认值坑：`pywebpush.webpush()` 的默认 `ttl=0` 会让推送服务在设备不可立即送达时丢弃消息，但调用方仍可能拿到 FCM accepted / HTTP 201。当前已改为显式 `ttl=3600`，避免学生提醒因为手机短暂休眠或网络切换而被立即丢弃。
- 新确认一条本地方案 B 启动坑：只有“沙箱外启动”的本地后端才和用户电脑 VPN 处在同一条可访问 FCM 的网络路径里；普通沙箱内 `send_push()` 会失败并返回 `HTTPSConnectionPool(... fcm.googleapis.com ...) NewConnectionError`。如果本地 scheduled reminder 卡在 `pending`，先检查后端启动权限与 FCM 出网，再看 scheduler 逻辑。
- 已确认本地方案 B 的正向闭环：沙箱外后端启动后，通过真实 `/api/tasks/` 创建的 `11:15` scheduled reminder 到点变为 `sent`，用户手机收到 Chrome 通知弹窗。后续如果再出现 `sent` 但无弹窗，应优先检查手机通知权限、Chrome/PWA 前后台状态、系统省电策略、service worker 展示逻辑和通知点击路径，而不是回退怀疑 task/reminder 写库。
## 2026-05-31 Agent Execution Loop V1 测试告警
- Agent Execution Loop V1 的定向后端回归已通过 `42 passed`，后端全量回归已通过 `214 passed`。pytest 过程中仍有非阻塞告警：`test_agent_loop_can_create_task_then_set_reminder`、`test_reminders.py::test_list_reminders`、`test_reminders.py::test_delete_reminder` 会触发 `coroutine 'run_coroutine_job' was never awaited`，原因是部分旧测试路径没有 mock 掉 APScheduler job；定向回归中还出现过 `.pytest_cache` 写入 `D:\student_time_plan\student-planner\.pytest_cache\v\cache\nodeids` 的 `Permission denied`。这些当前不影响 V1 功能判断，但后续做测试清洁度时应单独处理。
