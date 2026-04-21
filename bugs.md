# Student Planner 已知问题与环境坑

## 长期环境约束
- 当前 PATH 上的默认 `python` 不是项目测试使用的版本；后端测试统一使用 `py -3.12 -m pytest`。
- `py -3.12 -m pip install -e ".[dev]"` 仍会因为 setuptools 顶层包识别冲突失败；当前做法是安装 `pyproject.toml` 中的直接依赖与测试依赖继续验证。
- Python 3.12 环境需要保留 `openai` 依赖，认证相关依赖需保持 `bcrypt<5`。
- 后端全量 `py -3.12 -m pytest -q` 若与前端 `npm test` / `npm run build` 并行执行，测试共享的 SQLite `test.db` 偶发会在 teardown 报 `database is locked`；基线验证请串行跑，若遇到该报错先单独重跑后端全量确认。
- PWA 真机安装不能直接依赖局域网 HTTP 地址；`http://<LAN-IP>:4173` 下 `navigator.serviceWorker` 不可用，后续 Task 3 需要先准备 HTTPS origin（临时隧道、同域 HTTPS 环境或受信本地证书）。
- 当前临时 HTTPS 方案使用 Cloudflare Quick Tunnel：地址是随机的 `trycloudflare.com` 子域名，服务重启后 URL 可能变化，且官方明确说明这类 account-less tunnel 没有 uptime guarantee，不适合作为长期正式入口。
- `rg.exe` 在当前环境可能无法执行，检索时改用 PowerShell 的 `Get-ChildItem` 与 `Select-String`。
- PowerShell 写文件要避免 UTF-8 with BOM，防止 `pyproject.toml` 等文件解析失败。
- 首次在该仓库执行 git 操作时，若触发 `dubious ownership`，需要先把 `D:\student_time_plan` 加入 git `safe.directory`。

## 已确认并需要记住的问题
- 旧版本地数据库可能停留在 `courses.week_type` schema；如果再次出现 `no such column: courses.week_pattern`，优先检查 Alembic 版本并执行兼容迁移 `c4c3b8a92f1d`。
- WebSocket 重连曾导致旧确认卡片仍可见但 answer 落到新会话；相关保护已修复，但若再次出现类似“确认后不继续”，先检查 `pendingAsk` 清理和后端等待态。
- `schedule_parser` 曾把 `1-16周` 误识别为节次，并在空行分块时把“操场”拆成独立课程；相关回归测试已经补齐，后续改解析逻辑时需要重点回归。
- IAB 或本地撤销可能把 `student-planner/frontend/src/pages/ChatPage.tsx` 写入 Git 冲突标记；如果前端突然无法编译，优先全局检索 `<<<<<<<|=======|>>>>>>>`。

## 已延期但仍待处理
- 课表图片异步解析的前端进度展示尚未补齐，需要前端轮询或 WebSocket 进度消费。
- Chat 在“确认后到下一次 `tool_call` 前”的轻量过渡方案尚未完成，目前保持稳定版“仅显示已选择”。

## 不要重复走的失败路径
- 不要把 `AGENTS.md` 当成长期 session 流水账；历史过程应压缩为当前快照或单独归档。
- 不要在未确认设计变更时直接改实现；先记录问题，再决定是否调整 spec / plan。
