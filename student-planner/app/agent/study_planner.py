import json
from typing import Any

from app.agent.llm_client import AsyncOpenAI, chat_completion, create_llm_client

PLAN_PROMPT = """你是一个复习计划生成器。根据以下信息生成复习计划：

考试列表：
{exams}

可用时间段：
{slots}

复习策略：{strategy}
- balanced：每门课均匀分配时间
- intensive：考前几天集中复习
- spaced：间隔重复，越早开始越好

要求：
1. 每个任务必须在一个空闲时段内，不能跨时段
2. 难度高的课程分配更多时间
3. 同一门课的复习任务不要连续安排（除非时间不够）
4. 每个任务的时长在 1-2 小时之间
5. 任务标题格式：\"课程名 - 具体内容\"
6. description 要具体，写清楚复习哪些章节/知识点

示例输入：
考试：高等数学(4月5日, hard), 线性代数(4月5日, medium)
空闲：3月30日 10:00-12:00, 14:00-17:00; 3月31日 10:00-12:00, 14:00-16:00
策略：balanced

示例输出：
[
  {{
    \"title\": \"高数 - 极限与连续\",
    \"exam_name\": \"高等数学\",
    \"date\": \"2026-03-30\",
    \"start_time\": \"10:00\",
    \"end_time\": \"12:00\",
    \"description\": \"复习第1-3章：极限定义、夹逼定理、连续性判断、间断点分类\"
  }},
  {{
    \"title\": \"线代 - 行列式与矩阵\",
    \"exam_name\": \"线性代数\",
    \"date\": \"2026-03-30\",
    \"start_time\": \"14:00\",
    \"end_time\": \"16:00\",
    \"description\": \"复习第1-2章：行列式计算、矩阵运算、逆矩阵求法\"
  }},
  {{
    \"title\": \"高数 - 微分与积分\",
    \"exam_name\": \"高等数学\",
    \"date\": \"2026-03-30\",
    \"start_time\": \"16:00\",
    \"end_time\": \"17:00\",
    \"description\": \"复习第4-5章：导数计算、微分中值定理、不定积分基本方法\"
  }},
  {{
    \"title\": \"线代 - 向量与线性方程组\",
    \"exam_name\": \"线性代数\",
    \"date\": \"2026-03-31\",
    \"start_time\": \"10:00\",
    \"end_time\": \"12:00\",
    \"description\": \"复习第3-4章：向量空间、线性相关性、齐次/非齐次方程组求解\"
  }},
  {{
    \"title\": \"高数 - 综合练习\",
    \"exam_name\": \"高等数学\",
    \"date\": \"2026-03-31\",
    \"start_time\": \"14:00\",
    \"end_time\": \"16:00\",
    \"description\": \"做2套历年真题，重点关注计算题和证明题\"
  }}
]

注意示例中的特点：
- 高数(hard)分配了3个时段，线代(medium)分配了2个时段 — 难度高的课更多时间
- 高数和线代交替安排，没有连续复习同一门课
- 最后一个任务是综合练习，不只是看书
- description 具体到章节和知识点

输出格式（严格 JSON）：
[
  {{
    \"title\": \"课程名 - 具体内容\",
    \"exam_name\": \"课程全名\",
    \"date\": \"YYYY-MM-DD\",
    \"start_time\": \"HH:MM\",
    \"end_time\": \"HH:MM\",
    \"description\": \"具体复习内容，包含章节和知识点\"
  }}
]

只输出 JSON 数组，不要输出其他内容。"""


async def generate_study_plan(
    exams: list[dict[str, Any]],
    available_slots: dict[str, Any],
    strategy: str = "balanced",
    llm_client: AsyncOpenAI | None = None,
) -> list[dict[str, Any]]:
    """Use LLM to generate a study plan."""
    if llm_client is None:
        llm_client = create_llm_client()

    prompt = PLAN_PROMPT.format(
        exams=json.dumps(exams, ensure_ascii=False, indent=2),
        slots=json.dumps(available_slots, ensure_ascii=False, indent=2),
        strategy=strategy,
    )

    response = await chat_completion(
        llm_client,
        [{"role": "user", "content": prompt}],
    )

    content = response.get("content", "").strip()
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1])

    try:
        tasks = json.loads(content)
        if not isinstance(tasks, list):
            return []
        return tasks
    except json.JSONDecodeError:
        return []