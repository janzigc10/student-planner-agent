# 学生时间规划 Agent — 设计文档

## 1. 产品定位

AI 驱动的学生时间规划工具，解决两个核心痛点：

1. **课前提醒** — 导入课表后自动在课前推送提醒（课程名、时间、地点），不用手动打开 App 查课表
2. **AI 任务拆解** — 输入考试/deadline，Agent 自动拆解成复习小任务并排进日历

目标用户：大学生。先做 Android 端（PWA），后续可扩展 iOS。

## 2. 技术栈

| 层 | 技术 | 说明 |
|---|---|---|
| 前端 | React PWA | 薄客户端，只做渲染和交互 |
| 后端 | FastAPI | API + Agent 核心 + 定时任务 |
| 数据库 | SQLite（开发）/ PostgreSQL（生产） | |
| 定时任务 | APScheduler | 课前提醒、任务提醒调度 |
| 推送 | Web Push API | Android Chrome 完全支持后台推送 |
| LLM | 国产大模型（可切换） | OpenAI 兼容接口，provider 可配置 |

选择依据：
- FastAPI + React 是上一版已验证的技术栈，问题在架构设计而非技术栈本身
- PWA 在 Android 上推送体验接近原生 App，开发成本远低于 React Native
- 国产模型价格便宜，大部分兼容 OpenAI API 格式

## 3. 架构设计

### 3.1 整体架构

```
┌──────────────────────────────────────────────┐
│              React PWA（薄客户端）              │
│  只做 UI 渲染 + 用户交互，零业务逻辑            │
└──────────────────┬───────────────────────────┘
                   │ REST API + WebSocket（流式）
┌──────────────────▼───────────────────────────┐
│              FastAPI 后端                      │
│                                               │
│  ┌─────────────────────────────────────────┐  │
│  │         Agent 核心（Plan & Execute）      │  │
│  │  Planner: 用户输入 → LLM 理解意图        │  │
│  │           → 拆解成步骤序列               │  │
│  │  Executor: 逐步执行，调用工具            │  │
│  │  Logger: 每步决策记录日志                │  │
│  └─────────────────────────────────────────┘  │
│                                               │
│  ┌──────────┐ ┌────────────┐ ┌────────────┐  │
│  │ 工具集    │ │ APScheduler │ │ Web Push   │  │
│  │(确定性的) │ │ (定时任务)  │ │ (推送)     │  │
│  └──────────┘ └────────────┘ └────────────┘  │
│                                               │
│  ┌──────────────────────────────────────────┐ │
│  │ LLM 适配层（可切换 provider）             │ │
│  └──────────────────────────────────────────┘ │
└──────────────────┬───────────────────────────┘
            ┌──────▼──────┐
            │  SQLite/PG  │
            └─────────────┘
```

### 3.2 核心原则

**Plan & Execute 模式**（参考 Claude Code、Codex 等现代 Agent 产品的架构）：

- LLM 负责：理解用户意图、选择工具、构造参数、解读结果、决定下一步
- 确定性代码负责：工具执行、权限检查、状态持久化、定时调度
- 分工总结：**LLM 决定"做什么"和"为什么"，确定性代码负责"怎么执行"和"是否允许"**

**防漂移机制**（吸取上一版教训 + 参考业界实践）：

1. 结构化反馈 — 工具执行结果直接喂回 LLM，提供纠正信号
2. 上下文注入 — 每次 LLM 调用都带上当前时间、今日日程摘要
3. 权限门控 — 关键操作（写入日历、修改计划）通过 `ask_user` 工具请求用户确认
4. 决策日志 — 每步记录 LLM 推理过程，可回溯调试
5. 精确数据 — 时间按精确时段返回（不是"上午/下午"粗粒度），避免 LLM 误判时间冲突

### 3.3 Prompt 分层：Agent.md + 动态上下文

参考 Claude Code 读取 CLAUDE.md 的模式，Agent 的 system prompt 由两部分组合：

**Agent.md（静态规则文件，版本控制）：**
- Agent 身份和行为准则
- 工具列表和使用说明
- 硬性规则（如：关键操作必须用 ask_user 确认、时间必须精确到小时）
- 输出格式要求
- 修改 Agent.md 即可调整 agent 行为，不用改代码

**动态上下文（运行时由代码注入）：**
```
当前时间：2026-03-29 15:30（周六）
当前学期：第8周

用户今天的日程：
- 无课
- 14:00-15:00 复习高数（已完成）
- 16:00-18:00 空闲

用户偏好：
- 最早学习时间：08:00
- 最晚学习时间：22:00
- 午休：12:00-13:30
- 最短有效时段：30分钟
```

**最终 system prompt = Agent.md 内容 + 动态上下文**

好处：
- 调试 agent 行为时大部分只需编辑 Agent.md，不用动代码重新部署
- Agent.md 可以 git 版本控制，行为变更有迹可循
- 静态规则和动态数据职责分离，结构清晰

这样用户说"今天下午""明天""下周一"时，LLM 能正确解析为具体日期。

## 4. Agent 工具集

LLM 通过 function calling 调用以下工具，工具本身是确定性的 Python 函数：

### 课表相关
- `parse_schedule(file)` — 解析 Excel/WPS 课表文件，返回结构化课程列表
- `parse_schedule_image(image)` — 解析课表图片/截图，返回结构化课程列表
- `add_course(课程信息)` — 添加单门课程
- `list_courses()` — 查看当前课表
- `delete_course(id)` — 删除课程

### 任务相关
- `create_study_plan(exams, free_slots, strategy)` — 根据考试列表和空闲时段生成复习计划
- `list_tasks(date_range)` — 查看指定日期范围的任务列表
- `update_task(id, changes)` — 修改单个任务（时间、内容等）
- `complete_task(id)` — 标记任务完成

### 提醒相关
- `set_reminder(event_id, advance_minutes)` — 为课程或任务设置提醒
- `list_reminders()` — 查看提醒列表

### 日历相关
- `get_free_slots(date_range)` — 查询空闲时间段（精确到小时，排除已有课程和任务）
- `get_calendar_view(date_range)` — 获取日历视图（课程 + 任务 + 空闲）

### 记忆相关
- `recall_memory(query)` — 检索用户的冷记忆（历史决策、旧习惯等），按需加载

### 用户交互
- `ask_user(question, options)` — 请求用户确认或选择（权限门控）

### 工具设计原则
- 每个工具职责单一，输入输出明确
- `get_free_slots` 返回精确时段（起止时间 + 时长），不用"上午/下午"粗粒度
- `ask_user` 是关键操作的门控，Agent 不能跳过用户确认直接执行写操作

### 关键工具 Schema 详细定义

**get_free_slots：**
```json
{
  "name": "get_free_slots",
  "description": "查询指定日期范围内用户的空闲时间段。返回每天的空闲时段列表，精确到分钟。已排除课程和已安排的任务。",
  "parameters": {
    "start_date": "开始日期，格式 YYYY-MM-DD",
    "end_date": "结束日期，格式 YYYY-MM-DD",
    "min_duration_minutes": "最短有效时段（分钟），默认30。短于此的碎片时间不返回"
  },
  "returns": {
    "slots": [
      {
        "date": "2026-03-30",
        "weekday": "周一",
        "free_periods": [
          {"start": "10:00", "end": "12:00", "duration_minutes": 120},
          {"start": "16:00", "end": "18:00", "duration_minutes": 120}
        ],
        "occupied": [
          {"start": "08:00", "end": "10:00", "type": "course", "name": "高等数学"}
        ]
      }
    ],
    "summary": "3.30-4.4 共 12 个空闲段，总计 24 小时"
  }
}
```

返回同时包含 `free_periods` 和 `occupied`，LLM 能看到完整时间画面，不会犯"4点以后没时间"的错误。

**create_study_plan：**
```json
{
  "name": "create_study_plan",
  "description": "根据考试列表和可用时间，生成复习计划。内部使用 LLM 生成方案，输出结构化任务列表。",
  "parameters": {
    "exams": [
      {"course_name": "高等数学", "exam_date": "2026-04-05", "difficulty": "hard"}
    ],
    "available_slots": "get_free_slots 的返回结果",
    "strategy": "balanced（均衡）/ intensive（考前密集）/ spaced（间隔重复）"
  },
  "returns": {
    "tasks": [
      {
        "title": "高数 - 极限与连续复习",
        "exam_name": "高等数学",
        "date": "2026-03-30",
        "start_time": "10:00",
        "end_time": "12:00",
        "description": "复习第1-3章：极限定义、求极限方法、连续性判断"
      }
    ]
  }
}
```

**ask_user：**
```json
{
  "name": "ask_user",
  "description": "向用户展示信息并请求确认或选择。用于关键操作前的确认。",
  "parameters": {
    "question": "要问用户的问题",
    "type": "confirm（是/否确认）/ select（从选项中选择）/ review（展示计划请求确认或修改）",
    "options": ["选项1", "选项2"],
    "data": "需要展示给用户的结构化数据（如任务列表）"
  }
}
```

### 错误处理策略

| 场景 | 处理方式 |
|------|---------|
| 工具调用参数错误 | 返回错误信息给 LLM，LLM 自行修正参数重试（最多2次） |
| 工具执行失败（如数据库错误） | 返回错误给 LLM，LLM 告知用户"出了点问题"并建议重试 |
| 用户拒绝确认 | LLM 询问用户想怎么调整，不重复提交同样方案 |
| 时间冲突 | 工具返回冲突详情，LLM 向用户解释并提供替代时段 |
| LLM 调用不存在的工具 | Executor 拦截，返回"工具不存在"，LLM 换一个工具 |
| LLM 连续调用 ask_user | Executor 拦截，提示"请先执行一步操作再询问用户" |

## 5. Agent Loop 流程

### 5.1 核心循环

```python
while True:
    response = llm.call(
        system_prompt=build_context(user),  # 注入当前时间、日程、偏好
        messages=conversation_history,
        tools=TOOL_DEFINITIONS
    )

    if response.has_tool_calls:
        for tool_call in response.tool_calls:
            result = execute_tool(tool_call)
            log_step(user, session, tool_call, result)  # 记录决策日志
            conversation_history.append(tool_call, result)
    else:
        # LLM 输出纯文本，任务完成
        break
```

### 5.2 示例流程 — "4月5号有三门考试"

```
用户: "4月5号有高数、线代、概率论三门考试"

→ Loop 1: LLM 理解意图，请求确认
  调用: ask_user("确认：4月5日有以下考试？", ["高等数学", "线性代数", "概率论"])
  用户: 确认 ✓

→ Loop 2: LLM 查询空闲时间
  调用: get_free_slots("2026-03-29", "2026-04-04")
  返回: [{date: "3.30", slots: ["10:00-12:00", "14:00-17:00"]}, ...]

→ Loop 3: LLM 生成复习计划
  调用: create_study_plan(exams=[...], free_slots=[...], strategy="balanced")
  返回: [{title: "高数-极限复习", date: "3.30", time: "10:00-12:00"}, ...]

→ Loop 4: LLM 请求确认计划
  调用: ask_user("复习计划如下，确认吗？", [任务列表], 可修改)
  用户: 确认 ✓

→ Loop 5: LLM 设置提醒
  调用: set_reminder(每个任务)

→ LLM 纯文本回复: "搞定了，复习计划已安排，提醒已设置。"
→ Loop 结束
```

### 5.3 示例流程 — 课前提醒

```
用户导入课表后，系统自动执行（不经过 Agent Loop）：

1. parse_schedule() 解析出所有课程
2. 为每节课创建 Reminder（默认提前15分钟）
3. APScheduler 注册定时任务
4. 到时间 → Web Push 推送: "10:00 高等数学 @ 教学楼A301"
```

课前提醒是确定性流程，不需要 LLM 参与。

### 5.4 示例流程 — 任务调整（上一版的大坑）

用户对已有计划不满意，要求修改时间。这次用 Plan & Execute 模式处理，跟创建任务没有本质区别 — 都是 LLM 选工具。

```
用户: "把高数复习从15:00改到17:00"

→ Loop 1: LLM 理解意图，检查 17:00 是否空闲
  调用: get_free_slots("2026-03-30", "2026-03-30")
  返回: 17:00-18:00 空闲 ✓

→ Loop 2: LLM 更新任务
  调用: update_task(task_id, {start_time: "17:00", end_time: "18:00"})
  返回: 更新成功

→ Loop 3: LLM 确认
  调用: ask_user("已把高数复习改到17:00-18:00，提醒也一起更新了。OK？")
  用户: 确认 ✓

→ LLM 纯文本回复: "搞定了。"
→ Loop 结束
```

如果目标时段有冲突：
```
→ Loop 1: get_free_slots 返回 17:00-18:00 已有"线代复习"
→ Loop 2: LLM 调用 ask_user
  "17:00-18:00 已经安排了线代复习。你想：
   A) 把高数改到 18:00-19:00（空闲）
   B) 把线代和高数互换时间
   C) 取消这次修改"
→ 用户选择后继续执行
```

上一版这个功能失败是因为把"重新规划"做成复杂的多步状态机，LLM 控制流程容易漂移。这次 `update_task` 就是一个普通工具调用，简单直接。

## 6. 数据模型

### User（用户）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| name | String | 用户名 |
| push_subscription | JSON | Web Push 订阅信息 |
| preferences | JSON | 偏好：最早/最晚学习时间、午休时段、最短有效时段 |
| current_semester_start | Date | 当前学期开始日期（用于计算第几周） |

### Course（课程）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| user_id | UUID | 外键 → User |
| name | String | 课程名 |
| teacher | String | 教师（可选） |
| location | String | 上课地点 |
| weekday | Integer | 周几（1-7） |
| start_time | Time | 开始时间 |
| end_time | Time | 结束时间 |
| week_start | Integer | 第几周开始 |
| week_end | Integer | 第几周结束 |

### Exam（考试/Deadline）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| user_id | UUID | 外键 → User |
| course_id | UUID | 外键 → Course（可选） |
| type | Enum | exam / assignment / other |
| date | Date | 日期 |
| description | String | 描述 |

### Task（任务）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| user_id | UUID | 外键 → User |
| exam_id | UUID | 外键 → Exam（可选） |
| title | String | 任务标题 |
| description | String | 任务描述 |
| scheduled_date | Date | 安排日期 |
| start_time | Time | 开始时间 |
| end_time | Time | 结束时间 |
| status | Enum | pending / completed / skipped |

### Reminder（提醒）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| user_id | UUID | 外键 → User |
| target_type | Enum | course / task |
| target_id | UUID | 关联的课程或任务 ID |
| remind_at | DateTime | 提醒时间 |
| status | Enum | pending / sent / failed |

### AgentLog（Agent 决策日志）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| user_id | UUID | 外键 → User |
| session_id | String | 会话 ID |
| step | Integer | 第几步 |
| tool_called | String | 调用的工具名 |
| tool_args | JSON | 工具参数 |
| tool_result | JSON | 工具返回结果 |
| llm_reasoning | Text | LLM 的推理过程 |
| timestamp | DateTime | 时间戳 |

## 7. 课表导入

### MVP 同时支持两种方式

#### 方式一：图片上传（拍照/截图）— 最方便

用户拍课表照片或截图 → 上传 → LLM 多模态识别 → 结构化提取 → 用户确认

技术方案：使用支持图片输入的国产模型（DeepSeek-VL、Qwen-VL、GLM-4V 等）

提取 Prompt：
```
这是一张大学课表的照片/截图。请提取所有课程信息，输出 JSON 格式：
[{
  "name": "课程名",
  "teacher": "教师（如果能看到）",
  "location": "教室（如果能看到）",
  "weekday": 1-7,
  "period": "第几节课（如 1-2节）",
  "weeks": "周次（如 1-16周）"
}]
如果某些信息看不清或不存在，对应字段填 null。
```

图片识别边界情况：

| 情况 | 处理 |
|------|------|
| 照片模糊/歪斜 | LLM 尽力识别，识别不了的字段填 null，用户确认时补充 |
| 课表是手写的 | 现代多模态模型能识别大部分手写体，准确率降低，需用户仔细确认 |
| 截图只有部分课表 | 识别能看到的部分，提示"看起来不完整，要不要再传一张？" |
| 图片不是课表 | LLM 返回空或报错，提示"这好像不是课表" |
| 超级课程表等 App 截图 | 格式标准，识别率高 |

#### 方式二：Excel/WPS 导入

支持格式：`.xlsx`、`.xls`、`.et`（WPS 需另存为 `.xlsx`）

解析库：`openpyxl`（.xlsx）+ `xlrd`（.xls）

解析策略：
1. 先用 LLM 理解表格结构（将 Excel 内容转为文本描述后让 LLM 提取）
2. LLM 提取失败则回退到规则解析（识别常见格式：行=时间段，列=星期）
3. 解析结果展示给用户确认后再写入

Excel 边界情况：

| 情况 | 处理 |
|------|------|
| 一个格子里有多门课（单双周） | LLM 拆分成两条记录，标注单/双周 |
| 缺少地点信息 | 标记为"未知"，提示用户补充 |
| 缺少周次信息 | 默认 1-16 周，提示用户确认 |
| 完全无法解析 | 告诉用户"这个格式我没看懂"，引导用图片方式或手动输入 |
| 文件太大（超过 100 门课） | 大概率不是课表，提示用户检查 |

#### 后续迭代
- 手动输入（表单方式逐门添加，作为兜底方案）

### 作息时间表与"第N节课"转换

很多课表只写"第1-2节"不写具体时间，每个学校作息不同。

处理流程：
```
图片/Excel 识别出: "高等数学 第1-2节 周一 教学楼A301"
                    ↓
系统检查: 用户有没有配置过作息时间表？
                    ↓
    ┌─── 有 → 自动转换: 第1-2节 = 08:00-09:40
    │
    └─── 没有 → Agent 通过 ask_user 追问:
         "你的课表用的是'第几节课'，我需要知道你们学校的作息时间。
          第1-2节 = ?:?? - ?:??
          第3-4节 = ?:?? - ?:??
          ..."
                    ↓
         用户回答后 → 存入 User.preferences.school_schedule
                    → 热记忆，以后不用再问
```

作息时间表数据结构：
```json
{
  "school_schedule": {
    "period_1_2": {"start": "08:00", "end": "09:40"},
    "period_3_4": {"start": "10:00", "end": "11:40"},
    "period_5_6": {"start": "14:00", "end": "15:40"},
    "period_7_8": {"start": "16:00", "end": "17:40"},
    "period_9_10": {"start": "19:00", "end": "20:40"}
  }
}
```

Agent.md 中写入规则："当课表中出现'第N节课'但用户未配置作息时间表时，必须先追问作息时间。"

## 8. 推送方案

### Web Push（PWA）

技术方案：
- Service Worker 注册 + Push API 订阅
- 后端使用 `pywebpush` 库发送推送
- VAPID 密钥对认证

推送内容：
- 课前提醒："10:00 高等数学 @ 教学楼A301"（默认提前15分钟）
- 任务提醒："该复习线性代数了（10:00-12:00）"

PWA 配置：
- `manifest.json`：应用名称、图标、主题色、启动 URL
- Service Worker：推送接收 + 离线缓存
- 引导用户"添加到主屏幕"

平台支持：
- Android Chrome：完全支持，浏览器关闭也能收到推送
- iOS Safari：16.4+ 支持，需先添加到主屏幕，体验不如 Android
- 桌面浏览器：Chrome / Firefox / Edge 均支持

## 9. 前端设计（待细化）

当前确定的原则：
- 薄客户端，零业务逻辑
- 三个主要页面：聊天页、日历页、课表页
- Agent 确认交互使用结构化卡片（按钮/选择题），不是纯文本
- 聊天框支持语音转文字（Web Speech API）

具体 UI 设计、交互细节、组件结构待后续细化。

## 10. LLM 适配层

设计为可切换的 provider：
- 统一接口，兼容 OpenAI API 格式
- 配置文件指定 provider（API endpoint、model name、API key）
- 支持国产模型：DeepSeek、智谱 GLM、通义千问等
- 切换 provider 只需改配置，不改代码

## 11. 上一版教训 & 本版应对

| 上一版问题 | 本版应对 |
|-----------|---------|
| LLM 控制复杂工作流，导致漂移 | Plan & Execute 模式：LLM 选工具，工具确定性执行 |
| 时间粒度太粗（上午/下午） | `get_free_slots` 返回精确时段（起止时间 + 时长） |
| 出问题无法回溯 | AgentLog 记录每步决策，可追踪推理过程 |
| 多套控制机制共存 | 单一 Agent Loop，一条路径 |
| 只靠单元测试验证 | 真实对话 transcript 作为验收标准 |

## 12. 补充说明

### 12.1 create_study_plan 内部实现

`create_study_plan` 工具内部使用 LLM 生成复习方案（因为需要理解课程内容来合理分配复习重点），但输出必须是结构化的 JSON（任务列表），不是自由文本。如果 LLM 输出格式不合规，工具层做校验和重试。

### 12.2 Memory 系统、上下文管理与对话生命周期

这三个问题是一条链：多轮对话 → 上下文越来越脏 → 需要上下文管理策略 → 需要 memory 把重要信息持久化。

#### 12.2.1 分层存储架构

```
┌─────────────────────────────────────────────────────┐
│  Layer 1: 工作记忆（Working Memory）                  │
│  = 当前会话的 conversation_history                    │
│  生命周期：单次会话                                    │
│  内容：用户消息 + LLM 回复 + 工具调用/结果             │
│  特点：最新最完整，但会膨胀                            │
├─────────────────────────────────────────────────────┤
│  Layer 2: 短期记忆（Session Summary）                 │
│  = 会话结束时的摘要                                    │
│  生命周期：跨会话，保留最近 30 天                       │
│  内容：这次对话做了什么、确认了什么、改了什么            │
│  用途：用户下次来时，Agent 知道"上次我们聊到哪了"       │
├─────────────────────────────────────────────────────┤
│  Layer 3: 长期记忆（Persistent Memory）               │
│  = 从对话中提取的持久化事实                            │
│  生命周期：永久（除非用户删除或过期）                   │
│  内容：用户偏好、学习习惯、重要决策                     │
│  用途：个性化 Agent 行为                               │
└─────────────────────────────────────────────────────┘
```

#### 12.2.2 长期记忆（Memory）详细设计

**存什么：**
- 用户偏好："我喜欢早上复习数学，晚上看文科"
- 学习习惯："我一般一次最多集中2小时"
- 历史决策："上次高数复习用的是分章节策略，效果不错"
- 课程难度认知："用户觉得概率论最难，需要更多时间"

**不存什么：**
- 具体的日程安排（已在 Task/Course 表中）
- 对话原文（太大，存摘要就够）
- 临时性信息（"今天心情不好不想学习"）

**数据模型：**

```
Memory 表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| user_id | UUID | 外键 → User |
| category | Enum | preference / habit / decision / knowledge |
| content | Text | 记忆内容（自然语言描述） |
| source_session_id | String | 从哪次对话提取的 |
| created_at | DateTime | 创建时间 |
| last_accessed | DateTime | 最后被使用的时间 |
| relevance_score | Float | 相关性评分（用于检索排序） |
```

**写入时机：**
- 会话结束时，用 LLM 从对话中提取值得记住的信息
- 提取 prompt："从以下对话中提取用户的偏好、习惯或重要决策，输出结构化 JSON"

**读取时机 — 热/温/冷三层加载：**

```
热记忆（always-on）→ 注入 System Prompt
  - preference 类全部加载（用户偏好，一般不超过10条）
  - 作息时间表（school_schedule）
  - 占用少，价值高，几乎每次都用得上

温记忆（session-start）→ 对话开头注入一次
  - 上次会话摘要
  - 最近7天内创建的 memory
  - 只注入一次，后续可被压缩

冷记忆（on-demand）→ recall_memory 工具按需检索
  - 历史决策、旧的学习习惯
  - LLM 觉得需要时主动调用 recall_memory(query) 检索
  - 零固定开销，不浪费 token
```

这样 system prompt 保持精简，大部分记忆通过工具按需加载。

**遗忘机制：**
- 90天未被访问 → 标记为 stale，不再自动加载
- 180天未被访问 → 自动归档（不删除，但不参与检索）
- 用户说"我现在喜欢晚上复习了" → 覆盖旧的 preference
- 新学期开始 → 课程相关的 memory 批量标记为 outdated
- 用户主动说"忘掉之前的xxx" → 删除对应 memory

**防记错机制：**
1. LLM 提取的 memory 不直接写入，先用 ask_user 确认："我记住了：你觉得概率论最难。对吗？"
2. 只提取用户明确表达的事实，不推断（用户说"我数学不好"→ 记录；用户考了60分 → 不推断"数学不好"）
3. 每条 memory 带 source_session_id，出问题能追溯来源

#### 12.2.3 上下文窗口管理（防止上下文变脏）

**问题：** 用户聊了10轮，中间5次工具调用，每次工具返回一大堆 JSON。context window 里大部分是历史工具结果，真正有用的信息被淹没。

**策略：三级压缩**

```
第一级：工具结果即时压缩
  工具返回完整 JSON 后，立即生成摘要版本
  完整版存入 AgentLog（用于调试）
  摘要版留在 conversation_history（用于后续推理）

  例：get_free_slots 返回了7天的详细时段
  → 摘要："3.30-4.4 共有 12 个空闲时段，总计 24 小时可用"
  → 完整数据已传给 create_study_plan 工具，不需要在 history 里重复

第二级：滑动窗口 + 摘要
  当 conversation_history 超过 token 阈值（如模型上下文的 70%）时：
  - 保留最近 6 轮完整对话
  - 更早的对话压缩成摘要段落
  - 摘要由 LLM 生成："之前的对话中，用户导入了课表（15门课），
    设置了3门考试的复习计划，确认了所有提醒"

第三级：会话切割
  当单次会话过长（超过 20 轮或 token 接近上限）时：
  - 生成当前会话摘要
  - 存入 Session Summary
  - 开启新会话，将摘要作为新会话的初始上下文
```

**工具结果摘要规则：**

| 工具 | 完整结果 | 摘要版（留在 history 中） |
|------|---------|------------------------|
| get_free_slots | 每天每个时段的详细列表 | "X天内共Y个空闲段，共Z小时" |
| list_courses | 所有课程的完整信息 | "共N门课，周一到周五分布" |
| create_study_plan | 完整任务列表 | "生成了N个复习任务，覆盖X门课" |
| list_tasks | 所有任务详情 | "本周有N个任务，M个已完成" |

#### 12.2.4 对话生命周期

**新会话的触发条件：**
- 用户主动开始新对话
- 距离上次消息超过 2 小时（自动视为新会话）
- 上下文窗口触发第三级压缩时

**新会话的初始上下文构成：**
```
Agent.md（静态规则）
+ 动态上下文（当前时间、今日日程、用户偏好）
+ Memory 摘要（该用户的长期记忆，top 10 条相关的）
+ 上次会话摘要（如果距离上次 < 24小时）
```

**会话结束时的处理：**
1. 生成会话摘要（LLM 总结这次对话做了什么）
2. 提取 memory（从对话中提取值得长期记住的信息）
3. 存储到 SessionSummary 表和 Memory 表

**新增数据模型：**

```
SessionSummary 表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| user_id | UUID | 外键 → User |
| session_id | String | 会话 ID |
| summary | Text | 会话摘要 |
| actions_taken | JSON | 本次会话执行的操作列表 |
| created_at | DateTime | 创建时间 |

ConversationMessage 表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| session_id | String | 会话 ID |
| role | Enum | user / assistant / tool_call / tool_result |
| content | Text | 消息内容 |
| is_compressed | Boolean | 是否已被压缩（压缩后 content 存摘要） |
| timestamp | DateTime | 时间戳 |
```

### 12.3 用户认证

MVP 阶段使用简单的用户名 + 密码认证（JWT token）。不做复杂的 OAuth 或第三方登录。

### 12.4 Agent.md 内容概要

Agent.md 是给 LLM 的"工作手册"，代码只负责加载它，不硬编码任何 prompt。

包含内容：
- 身份定义：你是一个大学生时间规划助手
- 行为准则：写操作必须 ask_user 确认、时间精确到分钟、不编造信息、信息不完整时追问
- 工具使用指南：每个工具什么时候该用/不该用、参数怎么填
- 错误处理：失败最多重试2次、用户拒绝时询问调整方向、时间冲突时提供替代方案
- 语言规则：面向用户用中文，代码/日志/变量名用英文
- 特殊规则：课表出现"第N节课"但无作息时间表时必须先追问
- Few-Shot 示例对话：5个典型场景（添加考试、查课表、调整任务、模糊请求、第N节课追问），展示意图识别→工具选择→参数构造的完整思路
- 时间解析规则表：用户自然语言时间表达（"明天""下周三""4.5号"等）到精确日期的转换规则
- create_study_plan 的 prompt 也包含 few-shot 示例，展示"好的复习计划长什么样"

代码中的加载方式：
```python
def build_system_prompt(user):
    agent_md = open("Agent.md").read()          # 静态规则
    context = build_dynamic_context(user)        # 动态上下文
    hot_memory = load_hot_memory(user)           # 热记忆
    return f"{agent_md}\n\n{context}\n\n{hot_memory}"
```

### 12.5 并发安全

同一用户同一时间只允许一个活跃的 Agent 会话。第二个请求排队等待或提示"你有一个正在进行的对话"。避免两个 Agent Loop 同时写入同一时间段导致冲突。

### 12.6 任务冲突检测

`update_task` 和 `create_study_plan` 写入任务前，必须再次检查时间冲突。即使之前 `get_free_slots` 返回了空闲，写入时也要做最终校验（因为两次调用之间可能有其他任务被创建）。

### 12.7 课表变更的级联更新

用户修改课表（如某门课换了时间）后，系统自动检测已安排的任务是否与新课表冲突。如果冲突，通过 Agent 通知用户并建议调整，不自动删除或移动任务。

### 12.8 推送失败重试

Web Push 可能失败（用户关了通知权限、token 过期等）。处理策略：
- 失败后重试最多3次，间隔递增（1分钟、5分钟、15分钟）
- 连续失败超过3次 → 标记该 push_subscription 为失效
- 用户下次打开 App 时提示重新授权通知权限
