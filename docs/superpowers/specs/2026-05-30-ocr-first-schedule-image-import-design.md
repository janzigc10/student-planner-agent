# OCR-first 课表图片导入设计

## 状态

Draft，已由用户确认方向：图片课表导入从“视觉大模型直读图片”改为“OCR 提取 + 规则结构化 + LLM 审核/修正 + 用户确认”。

## 背景

当前图片课表导入链路位于 `student-planner/app/routers/schedule_import.py`、`student-planner/app/agent/schedule_ocr.py` 和 `student-planner/app/agent/tool_executor.py`。图片上传后会进入后台解析任务，实际解析由 `schedule_ocr.py` 把图片 base64 后作为 `image_url` 传给视觉模型，默认模型为 `qwen-vl-plus`。

这个方案短期可用，但把图片导入闭环绑定在多模态模型上。如果后续主模型换成纯文本模型，或视觉模型响应不稳定，图片课表导入会直接失去基础能力。用户明确希望改成 OCR-first：先由 OCR 做感知，再由普通文本 LLM 做审核和纠错。

## 目标

1. 图片课表导入不再硬依赖多模态模型。
2. 保留现有上传接口、异步解析状态、确认卡、补充节次时间、补充学期信息和 `bulk_import_courses` 流程。
3. 引入可替换、可 mock 的 OCR provider 接口，让真实 OCR 引擎可以后接。
4. 把 LLM 从“看图识别者”降级为“文本审核者”，只处理 OCR 和规则结构化后的文本结果。
5. 让 OCR、布局还原、课程结构化、LLM 审核、用户确认分别可测试、可定位。

## 非目标

1. 第一版不必须接入真实 OCR 引擎。可以先落接口和 mock provider，保证架构闭环和测试闭环。
2. 第一版不追求覆盖所有学校课表截图样式。
3. 不改 Excel 课表导入链路。
4. 不删除现有视觉模型解析能力；它可以先作为 fallback 或 compatibility adapter 保留。
5. 不跳过用户确认。所有写入仍必须经过确认卡。

## 推荐方案

采用“可 mock OCR provider + OCR-first pipeline”的分层方案。

整体链路：

```text
图片上传
-> OCRProvider.extract()
-> OCR blocks(text, bbox, confidence)
-> 课表布局还原
-> RawCourse 候选课程
-> 文本 LLM 审核/修正
-> cache PARSED/FAILED/NEED_PERIOD_TIMES
-> parse_schedule_image tool
-> ask_user 确认卡
-> bulk_import_courses
```

第一版先实现接口、数据结构、mock provider 和 pipeline 边界。真实 OCR provider 作为下一步接入。

## 模块设计

### OCR provider

新增服务模块，例如：

`student-planner/app/services/ocr_provider.py`

核心数据结构：

```python
class OCRBlock(BaseModel):
    text: str
    confidence: float | None = None
    bbox: tuple[float, float, float, float] | None = None

class OCRResult(BaseModel):
    blocks: list[OCRBlock]
    provider: str
    raw: dict[str, Any] | None = None

class OCRProvider(Protocol):
    async def extract(self, image_bytes: bytes, mime_type: str) -> OCRResult:
        ...
```

第一版实现：

1. `MockOCRProvider`：测试使用，输入图片不重要，直接返回固定 OCR blocks。
2. `VisionOCRCompatibilityProvider`：可选，用现有视觉模型能力模拟 OCR 输出，便于过渡。

后续真实实现：

1. `RapidOCRProvider`
2. `PaddleOCRProvider`
3. `CloudOCRProvider`

调用方只能依赖 `OCRProvider` 接口，不依赖具体 OCR 产品。

### 图片课表解析 pipeline

新增服务模块，例如：

`student-planner/app/services/schedule_image_pipeline.py`

职责：

1. 调用 OCR provider 得到 blocks。
2. 根据坐标和文本识别表头、星期列、节次行。
3. 把文字块归属到课表格子。
4. 从格子文本里提取课程名、教师、地点、周次、单双周。
5. 输出 `RawCourse` 列表、低置信度提示和解析警告。

输入：

```python
image_bytes: bytes
mime_type: str
fallback_week_number: int | None
prefer_parity_from_week_hint: bool
ocr_provider: OCRProvider
```

输出：

```python
class ScheduleImageParseResult(BaseModel):
    courses: list[RawCourse]
    warnings: list[str]
    low_confidence_blocks: list[OCRBlock]
    ocr_provider: str
```

### 文本 LLM 审核器

新增服务模块，例如：

`student-planner/app/services/schedule_image_auditor.py`

职责：

1. 只接收 OCR 文本块和初步课程 JSON，不接收图片。
2. 检查课程名、地点、教师、周次、单双周是否明显混乱。
3. 输出修正后的课程候选和 warnings。
4. 如果 LLM 不可用，pipeline 仍返回规则结构化结果。

约束：

1. 不允许凭空补齐不存在的课程。
2. 不允许把低置信度内容改成高置信度事实。
3. 对不确定项返回 warning，交给确认卡展示。
4. 输出必须是 JSON，不接受自由文本作为最终结果。

### 兼容现有 `parse_schedule_image`

现有 agent tool 名称 `parse_schedule_image` 保持不变。前端上传接口也保持不变。

后台解析任务中的 `parse_schedule_image(...)` 可以改为调用新 pipeline。当前 `schedule_ocr.py` 可先作为 compatibility wrapper 保留，避免一次重命名带来大范围改动。

## 错误处理

1. OCR provider 初始化失败：上传状态进入 `FAILED`，错误提示为“课表图片 OCR 服务不可用，请稍后重试或上传表格文件”。
2. OCR 无文字块：进入 `FAILED`，提示图片不清晰或格式不适合识别。
3. OCR 有文字但无法还原课程：进入 `PARSED` 但课程为空，并在确认卡或提示里说明未识别到可导入课程。
4. 低置信度课程：仍进入确认卡，但携带 warning，让用户确认前可见。
5. LLM 审核失败：不中断导入，返回规则结构化结果并记录审核失败 warning。
6. 多张图片部分失败：成功图片继续合并，失败图片加入 warning；如果全部失败才进入 `FAILED`。

## 测试计划

### 单元测试

1. `MockOCRProvider` 返回固定 OCR blocks。
2. OCR blocks 可以还原为 `RawCourse`。
3. 缺坐标、低置信度、空 OCR 结果都能得到明确状态。
4. 周次、单双周、节次解析沿用现有规则并补回归。
5. LLM 审核器关闭时 pipeline 仍能工作。
6. LLM 审核器返回修正 JSON 时能正确应用。
7. LLM 审核器异常时只产生 warning，不阻断。

### API/工具测试

1. `/schedule/upload` 图片上传仍返回 `processing`。
2. `/schedule/upload/{file_id}` 最终能返回 `PARSED` 和课程列表。
3. `parse_schedule_image` tool 仍能从 cache 读取结果。
4. `NEED_PERIOD_TIMES`、`READY`、`FAILED` 状态保持兼容。
5. Excel 上传测试保持不变。

### 回归测试

1. 多张图片合并。
2. 单双周合并成全周。
3. 缺学期开始日期和总周数时继续追问。
4. 用户确认后仍走 `bulk_import_courses`。

## 迁移策略

第一阶段只改内部结构，不改外部接口：

1. 新增 OCR provider 抽象和 mock provider。
2. 新增 pipeline，并用测试覆盖。
3. 将图片上传后台任务接到 pipeline。
4. 保留视觉模型作为 fallback 或 compatibility provider。

第二阶段接真实 OCR：

1. 选定 OCR provider。
2. 增加配置项，如 `SP_SCHEDULE_OCR_PROVIDER`。
3. 增加 provider 初始化失败的明确错误。
4. 用真实截图跑 smoke。

第三阶段增强确认卡：

1. 展示低置信度项。
2. 展示 OCR/LLM warnings。
3. 支持用户在确认前编辑课程项。

## 配置建议

新增配置项：

```text
SP_SCHEDULE_OCR_PROVIDER=mock|rapidocr|paddleocr|cloud|vision_fallback
SP_SCHEDULE_IMAGE_AUDIT_ENABLED=true|false
```

默认开发环境可以先用 `mock` 或 `vision_fallback`，生产环境在接入真实 OCR 后切到真实 provider。

`mock` 只用于测试和本地架构验证，不能作为生产环境配置。生产环境如果没有真实 OCR provider，应明确失败或临时启用 `vision_fallback`，不能静默返回伪造课程。

## 成功标准

1. 不启用视觉模型时，图片课表导入链路仍可通过 mock provider 完整跑通。
2. 现有 Excel 导入测试不受影响。
3. 现有确认卡、补信息、导入流程不变。
4. 解析失败时能明确告诉用户是 OCR 不可用、图片无文字、布局无法还原，还是 LLM 审核失败。
5. 后续接入真实 OCR provider 时，只需要新增 provider 实现，不需要重写上传和 agent tool 链路。

## 风险

1. 课表截图布局复杂，纯规则还原第一版可能覆盖有限。
2. 本地 OCR 依赖可能较重，Windows 和服务器安装需要单独验证。
3. 云 OCR 稳定但增加账号、费用和隐私配置。
4. LLM 审核如果提示词不严，可能把不确定内容“修正”成幻觉。
5. 确认卡如果不展示 warning，用户仍可能误以为解析结果是确定事实。

## 待确认问题

1. 第一版真实 OCR provider 选 RapidOCR、PaddleOCR，还是云 OCR。
2. 是否在第一版 UI 确认卡展示低置信度和 warning。
3. 是否保存原始 OCR blocks 供后续调试；如果保存，需要定义过期时间和隐私边界。
4. 视觉模型 fallback 是否默认关闭，还是仅在 OCR provider 不可用时启用。
