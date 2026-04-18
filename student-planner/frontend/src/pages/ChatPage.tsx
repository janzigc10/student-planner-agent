import { useEffect, useMemo, useRef, useState } from 'react'
import type { ChangeEvent, FormEvent, MutableRefObject } from 'react'

import { api, getStoredToken } from '../api/client'
import { MicIcon, PlusIcon, SendIcon } from '../components/icons'
import type { ChatServerEvent, PendingAsk, ToolProgress } from '../stores/chatStore'
import { useChatStore } from '../stores/chatStore'

type SpeechRecognitionInstance = {
  lang: string
  interimResults: boolean
  start: () => void
  onresult: ((event: { results: { 0: { transcript: string } }[] }) => void) | null
}

type AttachmentKind = 'image' | 'spreadsheet'

interface PendingAttachment {
  id: string
  file: File
  kind: AttachmentKind
}

interface CoursePreview {
  name: string
  timeLine: string | null
  metaLine: string | null
}

const CHAT_RESPONSE_TIMEOUT_MS = 30000
const DEFAULT_CONFIRM_OPTIONS = ['确认', '取消']
const WEEKDAY_LABELS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

function wsUrl() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws/chat`
}

function sendJson(socketRef: MutableRefObject<WebSocket | null>, payload: unknown) {
  if (socketRef.current?.readyState === WebSocket.OPEN) {
    socketRef.current.send(JSON.stringify(payload))
    return true
  }
  return false
}

function buildAttachmentPrompt(fileId: string, kind: AttachmentKind) {
  return kind === 'image'
    ? `我上传了课表图片 file_id=${fileId}，请解析并展示确认卡片。`
    : `我上传了课表文件 file_id=${fileId}，请解析并展示确认卡片。`
}

function buildAttachmentConfirmation(kind: AttachmentKind, count: number) {
  return kind === 'image' ? `已发送 ${count} 张课表图片` : '已发送 1 个课表文件'
}

function detectAttachmentKind(file: File): AttachmentKind | null {
  const name = file.name.toLowerCase()
  if (
    file.type === 'image/png' ||
    file.type === 'image/jpeg' ||
    file.type === 'image/jpg' ||
    file.type === 'image/webp' ||
    /\.(png|jpe?g|webp)$/i.test(name)
  ) {
    return 'image'
  }
  if (
    file.type === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' ||
    file.type === 'application/vnd.ms-excel' ||
    /\.(xls|xlsx)$/i.test(name)
  ) {
    return 'spreadsheet'
  }
  return null
}

function asText(value: unknown): string | null {
  if (typeof value === 'string') {
    const trimmed = value.trim()
    return trimmed ? trimmed : null
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  return null
}

function pickText(record: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const maybe = asText(record[key])
    if (maybe) {
      return maybe
    }
  }
  return null
}

function normalizeWeekday(value: unknown): string | null {
  if (typeof value === 'number' && Number.isInteger(value) && value >= 1 && value <= 7) {
    return WEEKDAY_LABELS[value - 1] ?? null
  }
  const numeric = Number(value)
  if (Number.isInteger(numeric) && numeric >= 1 && numeric <= 7) {
    return WEEKDAY_LABELS[numeric - 1] ?? null
  }
  return asText(value)
}

function formatWeekRange(record: Record<string, unknown>) {
  const weekStart = Number(record.week_start)
  const weekEnd = Number(record.week_end)
  if (Number.isFinite(weekStart) && Number.isFinite(weekEnd)) {
    return `${weekStart}-${weekEnd}周`
  }
  return pickText(record, ['week_range', 'week', 'week_text', '周次', '周数'])
}

function getCourseEntries(data: unknown): unknown[] | null {
  if (Array.isArray(data)) {
    return data
  }
  if (!data || typeof data !== 'object') {
    return null
  }
  const courses = (data as { courses?: unknown }).courses
  return Array.isArray(courses) ? courses : null
}

function toCoursePreview(entry: unknown, index: number): CoursePreview {
  if (typeof entry === 'string') {
    return { name: entry.trim() || `课程 ${index + 1}`, timeLine: null, metaLine: null }
  }
  if (!entry || typeof entry !== 'object') {
    return {
      name: asText(entry) ?? `课程 ${index + 1}`,
      timeLine: null,
      metaLine: null,
    }
  }

  const record = entry as Record<string, unknown>
  const name =
    pickText(record, ['name', 'course_name', 'title', '课程', '课程名', '课程名称', '名称', '科目']) ??
    `课程 ${index + 1}`
  const startTime = pickText(record, ['start_time', 'startTime', '开始时间'])
  const endTime = pickText(record, ['end_time', 'endTime', '结束时间'])
  const weekdayLabel = normalizeWeekday(record.weekday)

  let timeLine: string | null = null
  if (weekdayLabel && startTime && endTime) {
    timeLine = `${weekdayLabel} · ${startTime}-${endTime}`
  } else {
    const rowSegments = Object.entries(record)
      .filter(([key]) => /^周[一二三四五六日天]/.test(key))
      .map(([key, value]) => {
        const text = asText(value)
        return text ? `${key} ${text}` : null
      })
      .filter((segment): segment is string => segment !== null)
    if (rowSegments.length > 0) {
      timeLine = rowSegments.join(' · ')
    } else {
      timeLine = pickText(record, ['time', '时间'])
    }
  }

  const metaParts = [
    pickText(record, ['location', 'classroom', 'place', '地点', '教室', '上课地点']),
    pickText(record, ['teacher', '教师', '老师']),
    formatWeekRange(record),
  ].filter((part): part is string => Boolean(part))
  const metaLine = metaParts.length > 0 ? metaParts.join(' · ') : null

  return { name, timeLine, metaLine }
}

function stringifyDetailValue(value: unknown): string {
  if (value == null) {
    return '—'
  }
  if (typeof value === 'string') {
    return value
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  if (Array.isArray(value)) {
    return value.map((item) => stringifyDetailValue(item)).join('，')
  }
  if (typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, nested]) => `${key}: ${stringifyDetailValue(nested)}`)
      .join('；')
  }
  return String(value)
}

function isInlineTextAsk(pendingAsk: PendingAsk | null) {
  return pendingAsk !== null && pendingAsk.type === 'review' && pendingAsk.options.length === 0 && pendingAsk.data == null
}

function anchorOrder(anchorMessageId: string | null, messageOrderMap: Map<string, number>, tailOrder: number, offset: number) {
  if (anchorMessageId && messageOrderMap.has(anchorMessageId)) {
    return (messageOrderMap.get(anchorMessageId) ?? tailOrder) + offset
  }
  return tailOrder + offset
}

function progressSummary(progress: ToolProgress[]) {
  const total = progress.length
  const done = progress.filter((item) => item.status === 'done').length
  const running = progress.find((item) => item.status === 'running') ?? null
  const current = running ?? progress.at(-1) ?? null
  const hasRunning = running !== null
  const fillRaw = total > 0 ? (done / total) * 100 : 0
  const fillPercent = hasRunning ? Math.max(fillRaw, 40) : fillRaw

  return {
    total,
    done,
    currentLabel: current?.label ?? null,
    ratio: `${done}/${total}`,
    fillPercent,
    hasRunning,
  }
}

export function ChatPage() {
  const socketRef = useRef<WebSocket | null>(null)
  const reconnectRef = useRef(0)
  const reconnectTimerRef = useRef<number | null>(null)
  const responseTimeoutRef = useRef<number | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const {
    answerAsk,
    appendUserMessage,
    applyServerEvent,
    error,
    isSending,
    messages,
    pendingAsk,
    progress,
    progressAnchorMessageId,
  } = useChatStore()
  const [draft, setDraft] = useState('')
  const [askDraft, setAskDraft] = useState('')
  const [pendingAttachments, setPendingAttachments] = useState<PendingAttachment[]>([])
  const [attachmentError, setAttachmentError] = useState<string | null>(null)
  const hasSpeech = typeof window !== 'undefined' && 'webkitSpeechRecognition' in window
  const inlineTextAsk = isInlineTextAsk(pendingAsk)
  const shouldRenderAskCard = pendingAsk !== null && !inlineTextAsk && !(pendingAsk.answered && progress.length > 0)

  const messageOrderMap = useMemo(
    () => new Map(messages.map((message, index) => [message.id, (index + 1) * 10])),
    [messages],
  )
  const tailOrder = messages.length > 0 ? messages.length * 10 : 0
  const askCardOrder = shouldRenderAskCard ? anchorOrder(pendingAsk.anchorMessageId, messageOrderMap, tailOrder, 0.2) : null
  const progressCardOrder =
    progress.length > 0 ? anchorOrder(progressAnchorMessageId, messageOrderMap, tailOrder, 0.1) : null
  const progressInfo = useMemo(() => progressSummary(progress), [progress])
  const canSend = draft.trim().length > 0 || pendingAttachments.length > 0

  const coursePreviews = useMemo(() => {
    if (!pendingAsk || pendingAsk.type !== 'review' || pendingAsk.data == null) {
      return null
    }
    const courseEntries = getCourseEntries(pendingAsk.data)
    if (!courseEntries) {
      return null
    }
    return courseEntries.map((entry, index) => toCoursePreview(entry, index))
  }, [pendingAsk])

  const reviewCount = useMemo(() => {
    if (!pendingAsk || pendingAsk.type !== 'review' || pendingAsk.data == null || !coursePreviews) {
      return coursePreviews?.length ?? 0
    }
    if (typeof pendingAsk.data === 'object' && pendingAsk.data !== null) {
      const rawCount = (pendingAsk.data as { count?: unknown }).count
      const numericCount = Number(rawCount)
      if (Number.isFinite(numericCount) && numericCount > 0) {
        return numericCount
      }
    }
    return coursePreviews.length
  }, [coursePreviews, pendingAsk])

  function clearResponseTimeout() {
    if (responseTimeoutRef.current !== null) {
      window.clearTimeout(responseTimeoutRef.current)
      responseTimeoutRef.current = null
    }
  }

  function startResponseTimeout() {
    clearResponseTimeout()
    responseTimeoutRef.current = window.setTimeout(() => {
      responseTimeoutRef.current = null
      applyServerEvent({ type: 'error', message: '助手暂时没有响应，请重试' })
    }, CHAT_RESPONSE_TIMEOUT_MS)
  }

  useEffect(() => {
    let closed = false

    function connect() {
      const token = getStoredToken()
      if (!token || closed) {
        return
      }
      const socket = new WebSocket(wsUrl())
      socketRef.current = socket
      socket.onopen = () => {
        reconnectRef.current = 0
        socket.send(JSON.stringify({ token }))
      }
      socket.onmessage = (event) => {
        clearResponseTimeout()
        applyServerEvent(JSON.parse(event.data) as ChatServerEvent)
      }
      socket.onclose = () => {
        const waitingForResponse = responseTimeoutRef.current !== null
        clearResponseTimeout()
        if (waitingForResponse) {
          applyServerEvent({ type: 'error', message: '聊天连接已断开，请重试' })
        }
        if (closed) {
          return
        }
        const delay = Math.min(30000, 1000 * 2 ** reconnectRef.current)
        reconnectRef.current += 1
        reconnectTimerRef.current = window.setTimeout(connect, delay)
      }
    }

    connect()
    return () => {
      closed = true
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current)
      }
      clearResponseTimeout()
      socketRef.current?.close()
    }
  }, [applyServerEvent])

  useEffect(() => {
    setAskDraft('')
  }, [pendingAsk?.question, pendingAsk?.type])

  async function submit(event: FormEvent) {
    event.preventDefault()
    const message = draft.trim()
    const attachments = pendingAttachments

    if (attachments.length > 0 && message) {
      setAttachmentError('文字草稿和附件不能一起发送，请分开发送。')
      return
    }

    if (attachments.length > 0) {
      try {
        const uploadResponse = await api.uploadSchedule(attachments.map((item) => item.file))
        const sent = sendJson(socketRef, { message: buildAttachmentPrompt(uploadResponse.file_id, uploadResponse.kind) })
        if (!sent) {
          setAttachmentError('聊天连接不可用，请稍后重试')
          return
        }
        appendUserMessage(buildAttachmentConfirmation(uploadResponse.kind, uploadResponse.source_file_count))
        setPendingAttachments([])
        setAttachmentError(null)
        startResponseTimeout()
      } catch (uploadError) {
        setAttachmentError(uploadError instanceof Error ? uploadError.message : '课表上传失败')
      }
      return
    }

    if (!message) {
      return
    }

    const shouldAnswerPendingAsk = pendingAsk !== null && !pendingAsk.answered
    const payload = shouldAnswerPendingAsk ? { answer: message } : { message }
    const sent = sendJson(socketRef, payload)
    if (!sent) {
      applyServerEvent({ type: 'error', message: '聊天连接不可用，请稍后重试' })
      return
    }

    appendUserMessage(message)
    if (shouldAnswerPendingAsk) {
      answerAsk(message)
    }
    setDraft('')
    startResponseTimeout()
  }

  function submitAnswer(answer: string) {
    const normalized = answer.trim()
    if (!normalized) {
      return
    }

    const sent = sendJson(socketRef, { answer: normalized })
    if (!sent) {
      applyServerEvent({ type: 'error', message: '聊天连接不可用，请稍后重试' })
      return
    }

    answerAsk(normalized)
    startResponseTimeout()
  }

  function addPendingAttachments(files: File[]) {
    if (files.length === 0) {
      return
    }

    const kinds = files.map(detectAttachmentKind)
    if (kinds.some((kind) => kind === null)) {
      setAttachmentError('暂不支持该附件类型，仅支持 png、jpg、jpeg、webp、xls、xlsx')
      return
    }

    const nextKind = kinds[0]
    if (kinds.some((kind) => kind !== nextKind)) {
      setAttachmentError('不能同时添加图片和表格')
      return
    }

    const existingKind = pendingAttachments[0]?.kind ?? null
    if (existingKind && existingKind !== nextKind) {
      setAttachmentError('不能同时添加图片和表格')
      return
    }

    if (nextKind === 'image' && pendingAttachments.filter((item) => item.kind === 'image').length + files.length > 3) {
      setAttachmentError('最多只能添加 3 张图片')
      return
    }

    if (
      nextKind === 'spreadsheet' &&
      pendingAttachments.filter((item) => item.kind === 'spreadsheet').length + files.length > 1
    ) {
      setAttachmentError('最多只能添加 1 个表格')
      return
    }

    setPendingAttachments((current) => [
      ...current,
      ...files.map((file) => ({
        id: crypto.randomUUID(),
        file,
        kind: nextKind,
      })),
    ])
    setAttachmentError(null)
  }

  function uploadSchedule(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.currentTarget.files ?? [])
    addPendingAttachments(files)
    event.currentTarget.value = ''
  }

  function removeAttachment(id: string) {
    setPendingAttachments((current) => current.filter((attachment) => attachment.id !== id))
    setAttachmentError(null)
  }

  function startSpeech() {
    const SpeechRecognition = (window as unknown as { webkitSpeechRecognition: new () => SpeechRecognitionInstance })
      .webkitSpeechRecognition
    const recognition = new SpeechRecognition()
    recognition.lang = 'zh-CN'
    recognition.interimResults = false
    recognition.onresult = (event) => {
      setDraft(event.results[0][0].transcript)
    }
    recognition.start()
  }

  function openAttachmentPicker() {
    fileInputRef.current?.click()
  }

  return (
    <main className="page chat-page">
      <div className="message-list">
        {messages.map((message, index) => (
          <div
            className={`message message--${message.role}`}
            key={message.id}
            style={{ order: (index + 1) * 10 }}
          >
            {message.content}
          </div>
        ))}

        {progress.length > 0 && progressCardOrder !== null ? (
          <section className="progress-card" aria-label="处理进度" style={{ order: progressCardOrder }}>
            <div className="progress-card__header">
              <strong>{isSending ? '正在处理...' : '处理完成'}</strong>
              <span className="progress-card__ratio">{progressInfo.ratio}</span>
            </div>
            <div
              className="progress-card__track"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={progressInfo.total}
              aria-valuenow={progressInfo.done}
            >
              <span
                className={`progress-card__fill${progressInfo.hasRunning ? ' progress-card__fill--running' : ''}`}
                style={{ width: `${progressInfo.fillPercent}%` }}
              />
            </div>
            <p className="progress-card__hint">
              当前：{progressInfo.currentLabel ?? (isSending ? '等待确认' : '已完成')}
            </p>
            {progress.map((item) => (
              <div className="progress-card__item" key={item.name}>
                <span
                  className={`progress-card__status ${
                    item.status === 'done' ? 'progress-card__status--done' : 'progress-card__status--running'
                  }`}
                  aria-hidden="true"
                >
                  {item.status === 'done' ? '✓' : '…'}
                </span>
                <span>{item.label}</span>
              </div>
            ))}
          </section>
        ) : null}

        {shouldRenderAskCard && askCardOrder !== null && pendingAsk ? (
          <section className="ask-card" aria-label="需要确认" style={{ order: askCardOrder }}>
            <p>{pendingAsk.question}</p>

            {pendingAsk.type === 'review' && pendingAsk.data != null ? (
              coursePreviews ? (
                <section className="ask-card__schedule">
                  <header className="ask-card__schedule-head">
                    <strong>识别课程 {reviewCount}</strong>
                    <span>请确认信息是否正确</span>
                  </header>
                  <div className="ask-card__schedule-list" aria-label="识别课程列表">
                    {coursePreviews.length > 0 ? (
                      coursePreviews.map((course, index) => (
                        <article className="ask-card__schedule-item" key={`${course.name}-${index}`}>
                          <p className="ask-card__schedule-name">{course.name}</p>
                          {course.timeLine ? <p className="ask-card__schedule-line">{course.timeLine}</p> : null}
                          {course.metaLine ? (
                            <p className="ask-card__schedule-line ask-card__schedule-line--muted">{course.metaLine}</p>
                          ) : null}
                        </article>
                      ))
                    ) : (
                      <p className="ask-card__schedule-empty">未识别到课程内容，请返回检查文件。</p>
                    )}
                  </div>
                </section>
              ) : pendingAsk.data && typeof pendingAsk.data === 'object' && !Array.isArray(pendingAsk.data) ? (
                <dl className="ask-card__kv" aria-label="确认详情">
                  {Object.entries(pendingAsk.data as Record<string, unknown>)
                    .filter(([key]) => key !== 'courses')
                    .map(([key, value]) => (
                      <div className="ask-card__kv-row" key={key}>
                        <dt>{key}</dt>
                        <dd>{stringifyDetailValue(value)}</dd>
                      </div>
                    ))}
                </dl>
              ) : (
                <p className="ask-card__plain">{stringifyDetailValue(pendingAsk.data)}</p>
              )
            ) : null}

            {pendingAsk.answered ? (
              <p>已选择：{pendingAsk.answered}</p>
            ) : (
              <div className="ask-card__actions">
                {pendingAsk.type === 'confirm' ? (
                  (pendingAsk.options.length > 0 ? pendingAsk.options : DEFAULT_CONFIRM_OPTIONS).map((option) => (
                    <button type="button" key={option} onClick={() => submitAnswer(option)}>
                      {option}
                    </button>
                  ))
                ) : pendingAsk.type === 'select' ? (
                  pendingAsk.options.length > 0 ? (
                    pendingAsk.options.map((option) => (
                      <button type="button" key={option} onClick={() => submitAnswer(option)}>
                        {option}
                      </button>
                    ))
                  ) : (
                    <p role="alert" className="status-inline status-inline--warning">
                      选项缺失，请重新发送或联系管理员。
                    </p>
                  )
                ) : pendingAsk.type === 'review' && pendingAsk.data ? (
                  (pendingAsk.options.length > 0 ? pendingAsk.options : DEFAULT_CONFIRM_OPTIONS).map((option) => (
                    <button type="button" key={option} onClick={() => submitAnswer(option)}>
                      {option}
                    </button>
                  ))
                ) : (
                  <>
                    <input
                      aria-label="回复内容"
                      value={askDraft}
                      onChange={(event) => setAskDraft(event.target.value)}
                      placeholder="请输入你的补充信息"
                    />
                    <button type="button" onClick={() => submitAnswer(askDraft)}>
                      提交
                    </button>
                  </>
                )}
              </div>
            )}
          </section>
        ) : null}

        {error ? (
          <p role="alert" className="status-inline status-inline--error" style={{ order: tailOrder + 9 }}>
            {error}
          </p>
        ) : null}
      </div>

      {pendingAttachments.length > 0 ? (
        <section className="attachment-tray" aria-label="待发送附件">
          <strong>待发送附件 {pendingAttachments.length}</strong>
          <div className="attachment-tray__items">
            {pendingAttachments.map((attachment) => (
              <div className="attachment-tray__item" key={attachment.id}>
                <span>{attachment.file.name}</span>
                <button type="button" onClick={() => removeAttachment(attachment.id)}>
                  移除 {attachment.file.name}
                </button>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {attachmentError ? (
        <p role="alert" className="status-inline status-inline--error">
          {attachmentError}
        </p>
      ) : null}

      <form className="chat-input" onSubmit={submit}>
        <button
          type="button"
          className="icon-button chat-input__icon-btn"
          aria-label="语音输入"
          onClick={startSpeech}
          disabled={!hasSpeech}
        >
          <MicIcon className="icon" />
        </button>
        <input aria-label="输入消息" value={draft} onChange={(event) => setDraft(event.target.value)} />
        {canSend ? (
          <button type="submit" className="primary-button chat-input__action-btn" aria-label="发送消息">
            <SendIcon className="icon" />
          </button>
        ) : (
          <button
            type="button"
            className="icon-button chat-input__action-btn"
            aria-label="添加附件"
            onClick={openAttachmentPicker}
          >
            <PlusIcon className="icon" />
          </button>
        )}
        <input
          ref={fileInputRef}
          className="chat-input__file-input"
          aria-label="上传课表"
          type="file"
          accept="image/*,.xls,.xlsx"
          capture="environment"
          multiple
          onChange={uploadSchedule}
        />
      </form>
    </main>
  )
}
