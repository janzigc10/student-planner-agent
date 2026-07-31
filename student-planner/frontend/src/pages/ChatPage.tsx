import { useEffect, useMemo, useRef, useState } from 'react'
import type { ChangeEvent, FormEvent, KeyboardEvent, MouseEvent, MutableRefObject, ReactNode } from 'react'

import { api, getStoredToken } from '../api/client'
import { createClientId } from '../createClientId'
import { MicIcon, PaperclipIcon, PlusIcon, SendIcon } from '../components/icons'
import type { ChatGrounding, ChatMessageResult, ChatServerEvent, PendingAsk, ToolProgress } from '../stores/chatStore'
import type { ScheduleUploadStatusResponse } from '../types/api'
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

interface TaskPreview {
  title: string
  date: string | null
  time: string | null
  description: string | null
}

interface EditableTaskDraft {
  id: string
  title: string
  scheduled_date: string
  start_time: string
  end_time: string
  description: string
  removed: boolean
}

interface CourseActionPreview {
  action: string
  courseName: string
  nextName: string | null
  timeLine: string | null
  metaLine: string | null
  reason: string | null
}

interface ScheduleReviewNotice {
  title: string
  note: string | null
}

type AssistantResultView = ChatMessageResult

const CHAT_RESPONSE_TIMEOUT_MS = 30000
const IMAGE_PARSE_BRIDGE_START = 18
const IMAGE_PARSE_BRIDGE_MAX = 92
const IMAGE_PARSE_BRIDGE_TICK_MS = 260
const IMAGE_PARSE_BRIDGE_FINISH_DELAY_MS = 180
const IMAGE_PARSE_POLL_INTERVAL_MS = 1500
const IMAGE_PARSE_POLL_TIMEOUT_MS = 90000
const ATTACHMENT_INPUT_ID = 'chat-attachment-input'
const DEFAULT_CONFIRM_OPTIONS = ['确认', '取消']
const WEEKDAY_LABELS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
const DEFAULT_THINKING_STEPS = ['理解你的需求', '检查日程上下文', '整理回复格式']
const TOOL_THINKING_COPY: Record<string, { running: string; done: string }> = {
  add_course: { running: '新增课程记录', done: '课程记录已新增' },
  get_free_slots: { running: '查询可用时间', done: '可用时间已确认' },
  create_study_plan: { running: '生成复习计划', done: '复习计划已生成' },
  create_work_plan: { running: '拆解作业计划', done: '作业计划已生成' },
  parse_schedule: { running: '解析课表结构', done: '课表结构已解析' },
  parse_schedule_image: { running: '识别课表图片', done: '课表图片已识别' },
  save_schedule_metadata: { running: '补全课表信息', done: '课表信息已补全' },
  bulk_import_courses: { running: '导入课程', done: '课程已导入' },
  list_courses: { running: '读取课程列表', done: '课程列表已读取' },
  update_course: { running: '更新课程信息', done: '课程信息已更新' },
  delete_course: { running: '删除错误课程', done: '错误课程已删除' },
  list_tasks: { running: '读取已有任务', done: '已有任务已读取' },
  create_task: { running: '写入日程任务', done: '日程任务已写入' },
  update_task: { running: '更新日程任务', done: '日程任务已更新' },
  complete_task: { running: '完成任务', done: '任务已完成' },
  set_reminder: { running: '设置提醒', done: '提醒已设置' },
  recall_memory: { running: '读取学习记忆', done: '学习记忆已读取' },
  ask_user: { running: '等待你的确认', done: '确认已收到' },
}
const TASK_PREVIEW_VISIBLE_COUNT = 3
const COURSE_PREVIEW_VISIBLE_COUNT = 4
const COURSE_ACTION_VISIBLE_COUNT = 3
const COURSE_ENTRY_KEYS = ['courses', 'course_list', 'courseList', '课程列表', '课程清单', '课表列表'] as const
const TASK_ENTRY_KEYS = ['tasks', 'task_list', 'taskList', 'plan', 'plans', '计划', '计划任务', '任务列表'] as const
const COURSE_ACTION_KEYS = ['actions', 'course_actions', 'courseActions', '修改动作'] as const
const REVIEW_COUNT_KEYS = ['count', 'course_count', 'courseCount', 'total', '共识别课程条目', '识别课程数', '课程数量'] as const

const SCHEDULE_REVIEW_RAW_MARKERS = ['完整课程列表如下', '课程列表如下', '课程明细如下', '|#|'] as const
const SCHEDULE_REVIEW_ISSUE_MARKERS = ['发现的问题：', '发现的问题:', '疑似 OCR 错误：', '疑似 OCR 错误:', '疑似OCR错误：', '疑似OCR错误:'] as const
const SCHEDULE_REVIEW_NOTE_END_MARKERS = ['完整课程列表如下', '课程列表如下', '课程明细如下', '|#|', '请确认后导入', '确认无误后我将导入课表', '确认后我将导入课表'] as const

type UploadReceiptKind = 'image' | 'spreadsheet'

interface UploadReceiptMeta {
  kind: UploadReceiptKind
  count: number
  text: string
}

interface ImageParseBridgeState {
  count: number
  progress: number
}

function wsUrl() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws/chat`
}

function sendJson(
  socketRef: MutableRefObject<WebSocket | null>,
  connectionReadyRef: MutableRefObject<boolean>,
  payload: unknown,
) {
  if (socketRef.current?.readyState === WebSocket.OPEN && connectionReadyRef.current) {
    socketRef.current.send(JSON.stringify(payload))
    return true
  }
  return false
}

async function waitForSocketReady(
  socketRef: MutableRefObject<WebSocket | null>,
  connectionReadyRef: MutableRefObject<boolean>,
  timeoutMs = 5000,
) {
  if (socketRef.current?.readyState === WebSocket.OPEN && connectionReadyRef.current) {
    return true
  }

  const startedAt = Date.now()
  return new Promise<boolean>((resolve) => {
    function tick() {
      if (socketRef.current?.readyState === WebSocket.OPEN && connectionReadyRef.current) {
        resolve(true)
        return
      }
      if (Date.now() - startedAt >= timeoutMs) {
        resolve(false)
        return
      }
      window.setTimeout(tick, 100)
    }
    tick()
  })
}

async function sendJsonWhenReady(
  socketRef: MutableRefObject<WebSocket | null>,
  connectionReadyRef: MutableRefObject<boolean>,
  payload: unknown,
) {
  if (sendJson(socketRef, connectionReadyRef, payload)) {
    return true
  }
  if (!(await waitForSocketReady(socketRef, connectionReadyRef))) {
    return false
  }
  return sendJson(socketRef, connectionReadyRef, payload)
}

function buildAttachmentPrompt(fileId: string, kind: AttachmentKind) {
  return kind === 'image'
    ? `我上传了课表图片 file_id=${fileId}，请解析并展示确认卡片。`
    : `我上传了课表文件 file_id=${fileId}，请解析并展示确认卡片。`
}

function buildAttachmentConfirmation(kind: AttachmentKind, count: number) {
  return kind === 'image' ? `已发送 ${count} 张课表图片` : '已发送 1 个课表文件'
}

function parseUploadReceipt(content: string): UploadReceiptMeta | null {
  const parsed = content.match(/^已发送\s+(\d+)\s+(张课表图片|个课表文件)$/)
  if (!parsed) {
    return null
  }
  const count = Number(parsed[1])
  if (!Number.isInteger(count) || count <= 0) {
    return null
  }
  const typeText = parsed[2]
  return {
    kind: typeText.includes('图片') ? 'image' : 'spreadsheet',
    count,
    text: content,
  }
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
  const weekText = pickText(record, ['week_text', 'week_range', 'week', '周次', '周数'])
  if (weekText) {
    return weekText
  }

  const weekStart = Number(record.week_start)
  const weekEnd = Number(record.week_end)
  if (Number.isFinite(weekStart) && Number.isFinite(weekEnd)) {
    const rawPattern = asText(record.week_pattern)?.toLowerCase()
    if (rawPattern === 'odd') {
      return `第${weekStart}-${weekEnd}周(单周)`
    }
    if (rawPattern === 'even') {
      return `第${weekStart}-${weekEnd}周(双周)`
    }
    return `第${weekStart}-${weekEnd}周`
  }
  return null
}

function tryParseJsonPayload(value: string): unknown | null {
  const text = value.trim()
  if (!text || (!text.startsWith('{') && !text.startsWith('['))) {
    return null
  }
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

function normalizeReviewData(data: unknown): unknown {
  if (typeof data === 'string') {
    const parsed = tryParseJsonPayload(data)
    if (parsed !== null) {
      return normalizeReviewData(parsed)
    }
    return data
  }
  if (Array.isArray(data)) {
    return data.map((item) => normalizeReviewData(item))
  }
  if (data && typeof data === 'object') {
    return Object.fromEntries(
      Object.entries(data as Record<string, unknown>).map(([key, value]) => [key, normalizeReviewData(value)]),
    )
  }
  return data
}

function getCourseEntries(data: unknown): unknown[] | null {
  if (Array.isArray(data)) {
    return data
  }
  if (typeof data === 'string') {
    const parsed = tryParseJsonPayload(data)
    if (parsed !== null) {
      return getCourseEntries(parsed)
    }
    return null
  }
  if (!data || typeof data !== 'object') {
    return null
  }
  const record = data as Record<string, unknown>
  for (const key of COURSE_ENTRY_KEYS) {
    const value = record[key]
    if (Array.isArray(value)) {
      return value
    }
    if (typeof value === 'string') {
      const chunks = value
        .replace(/\r\n/g, '\n')
        .split('\n')
        .map((item) => item.trim())
        .filter(Boolean)
      if (chunks.length > 1) {
        return chunks
      }
      const rows = value
        .split(/，(?=周次[:：])/)
        .map((item) => item.trim())
        .filter(Boolean)
      if (rows.length > 0) {
        return rows
      }
    }
  }
  return null
}

function getArrayEntries(data: unknown, keys: readonly string[]) {
  if (typeof data === 'string') {
    const parsed = tryParseJsonPayload(data)
    if (parsed !== null) {
      return getArrayEntries(parsed, keys)
    }
    return null
  }
  if (Array.isArray(data)) {
    return data
  }
  if (!data || typeof data !== 'object') {
    return null
  }
  const record = data as Record<string, unknown>
  for (const key of keys) {
    const value = record[key]
    if (Array.isArray(value)) {
      return value
    }
  }
  return null
}

function pickSerializedField(text: string, keys: string[]) {
  for (const key of keys) {
    const escaped = key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    const match = text.match(new RegExp(`${escaped}\\s*[:：]\\s*([^；;，,\\n]+)`))
    if (match?.[1]) {
      return match[1].trim()
    }
  }
  return null
}

function reviewCountFromData(data: unknown) {
  if (typeof data === 'string') {
    const parsed = tryParseJsonPayload(data)
    if (parsed !== null) {
      return reviewCountFromData(parsed)
    }
    return null
  }
  if (!data || typeof data !== 'object') {
    return null
  }
  const record = data as Record<string, unknown>
  for (const key of REVIEW_COUNT_KEYS) {
    const numericCount = Number(record[key])
    if (Number.isFinite(numericCount) && numericCount > 0) {
      return numericCount
    }
  }
  return null
}

function compactReviewText(text: string) {
  return text.replace(/\r\n/g, '\n').replace(/[ \t]+/g, ' ').replace(/\n{3,}/g, '\n\n').trim()
}

function findFirstMarkerIndex(text: string, markers: readonly string[]) {
  let matchIndex = -1
  for (const marker of markers) {
    const index = text.indexOf(marker)
    if (index >= 0 && (matchIndex === -1 || index < matchIndex)) {
      matchIndex = index
    }
  }
  return matchIndex
}

function extractScheduleReviewNote(question: string) {
  const normalized = compactReviewText(question)
  for (const marker of SCHEDULE_REVIEW_ISSUE_MARKERS) {
    const startIndex = normalized.indexOf(marker)
    if (startIndex < 0) {
      continue
    }

    let note = normalized.slice(startIndex)
    const nextText = note.slice(marker.length)
    const endIndex = findFirstMarkerIndex(nextText, SCHEDULE_REVIEW_NOTE_END_MARKERS)
    if (endIndex >= 0) {
      note = note.slice(0, marker.length + endIndex)
    }

    note = note.trim()
    if (note) {
      return note
    }
  }
  return null
}

function buildScheduleReviewNotice(question: string, reviewCount: number): ScheduleReviewNotice | null {
  const normalized = compactReviewText(question)
  if (!normalized) {
    return null
  }

  const hasRawTable = SCHEDULE_REVIEW_RAW_MARKERS.some((marker) => normalized.includes(marker))
  if (!hasRawTable && normalized.length <= 140) {
    return { title: normalized, note: null }
  }

  const title =
    reviewCount > 0
      ? `OCR 识别完成，已整理为 ${reviewCount} 条课程卡片，请确认信息是否正确后再导入。`
      : 'OCR 识别完成，请确认信息是否正确后再导入。'

  return {
    title,
    note: extractScheduleReviewNote(normalized),
  }
}

function toCoursePreview(entry: unknown, index: number): CoursePreview {
  if (typeof entry === 'string') {
    const raw = entry.trim()
    if (!raw) {
      return { name: `课程 ${index + 1}`, timeLine: null, metaLine: null }
    }
    const name = pickSerializedField(raw, ['课程', '课程名', '课程名称', '科目']) ?? raw
    const weekday = pickSerializedField(raw, ['星期', '周几', 'weekday'])
    const time = pickSerializedField(raw, ['时间', 'time'])
    const location = pickSerializedField(raw, ['地点', '教室', 'location'])
    const teacher = pickSerializedField(raw, ['教师', '老师', 'teacher'])
    const weekRange = pickSerializedField(raw, ['周次', '周数', 'week', 'week_range'])
    const timeLine = weekday && time ? `${weekday} · ${time}` : time ?? weekday ?? null
    const metaParts = [location, teacher, weekRange].filter((part): part is string => Boolean(part))
    const metaLine = metaParts.length > 0 ? metaParts.join(' · ') : null

    return { name, timeLine, metaLine }
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

function formatDateLabel(value: unknown) {
  const text = asText(value)
  if (!text) {
    return null
  }
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (!match) {
    return text
  }
  const date = new Date(`${text}T00:00:00`)
  const weekday = Number.isNaN(date.getTime())
    ? null
    : new Intl.DateTimeFormat('zh-CN', { weekday: 'short' }).format(date)
  return `${Number(match[2])}月${Number(match[3])}日${weekday ? ` ${weekday}` : ''}`
}

function toTaskPreview(entry: unknown, index: number): TaskPreview {
  if (!entry || typeof entry !== 'object') {
    return {
      title: asText(entry) ?? `任务 ${index + 1}`,
      date: null,
      time: null,
      description: null,
    }
  }

  const record = entry as Record<string, unknown>
  const title = pickText(record, ['title', 'name', 'content', '任务', '任务名', '标题', '内容']) ?? `任务 ${index + 1}`
  const date = formatDateLabel(record.scheduled_date ?? record.date ?? record.日期)
  const startTime = pickText(record, ['start_time', 'startTime', '开始时间'])
  const endTime = pickText(record, ['end_time', 'endTime', '结束时间'])
  const time = startTime && endTime ? `${startTime}-${endTime}` : startTime ?? endTime ?? pickText(record, ['time', '时间'])
  const rawDescription = pickText(record, ['description', 'note', '说明', '描述', '内容'])
  const description = rawDescription && rawDescription !== title ? rawDescription : null

  return { title, date, time, description }
}

function parseTimeRange(value: unknown) {
  const text = asText(value)
  if (!text) {
    return { start_time: '', end_time: '' }
  }
  const match = text.match(/(\d{1,2}:\d{2})\s*[-~～—–到]\s*(\d{1,2}:\d{2})/)
  if (!match) {
    return { start_time: '', end_time: '' }
  }
  return {
    start_time: match[1] ?? '',
    end_time: match[2] ?? '',
  }
}

function toEditableTaskDraft(entry: unknown, index: number): EditableTaskDraft {
  const fallbackTitle = `任务 ${index + 1}`
  if (!entry || typeof entry !== 'object') {
    return {
      id: createClientId(),
      title: asText(entry) ?? fallbackTitle,
      scheduled_date: '',
      start_time: '',
      end_time: '',
      description: '',
      removed: false,
    }
  }

  const record = entry as Record<string, unknown>
  const range = parseTimeRange(record.time ?? record.时间)
  return {
    id: createClientId(),
    title: pickText(record, ['title', 'name', 'content', '任务', '任务名', '标题', '内容']) ?? fallbackTitle,
    scheduled_date: pickText(record, ['scheduled_date', 'date', '日期']) ?? '',
    start_time: pickText(record, ['start_time', 'startTime', '开始时间']) ?? range.start_time,
    end_time: pickText(record, ['end_time', 'endTime', '结束时间']) ?? range.end_time,
    description: pickText(record, ['description', 'note', '说明', '描述']) ?? '',
    removed: false,
  }
}

function taskDraftToPreview(task: EditableTaskDraft): TaskPreview {
  const time = task.start_time && task.end_time ? `${task.start_time}-${task.end_time}` : task.start_time || task.end_time || null
  return {
    title: task.title || '未命名任务',
    date: formatDateLabel(task.scheduled_date),
    time,
    description: task.description || null,
  }
}

function taskDraftToPayload(task: EditableTaskDraft) {
  return {
    title: task.title.trim(),
    scheduled_date: task.scheduled_date,
    start_time: task.start_time,
    end_time: task.end_time,
    description: task.description.trim(),
  }
}

function isConfirmOption(option: string) {
  const normalized = option.trim().toLowerCase()
  return /^(确认|可以|确定|好|行|是|yes|ok)/.test(normalized)
}

function toCourseActionPreview(entry: unknown, index: number): CourseActionPreview {
  const fallback = {
    action: 'update',
    courseName: `课程 ${index + 1}`,
    nextName: null,
    timeLine: null,
    metaLine: null,
    reason: null,
  }

  if (!entry || typeof entry !== 'object') {
    return fallback
  }

  const record = entry as Record<string, unknown>
  const course = record.course && typeof record.course === 'object' ? (record.course as Record<string, unknown>) : {}
  const updates = record.updates && typeof record.updates === 'object' ? (record.updates as Record<string, unknown>) : {}
  const action = pickText(record, ['action', '动作']) ?? fallback.action
  const courseName = pickText(course, ['name', 'course_name', '课程名', '课程']) ?? fallback.courseName
  const nextName = pickText(updates, ['name', 'course_name', '课程名', '课程']) ?? null
  const weekdayLabel = normalizeWeekday(course.weekday)
  const startTime = pickText(course, ['start_time', 'startTime'])
  const endTime = pickText(course, ['end_time', 'endTime'])
  const timeLine = weekdayLabel && startTime && endTime ? `${weekdayLabel} · ${startTime}-${endTime}` : null
  const metaParts = [
    pickText(course, ['location', 'classroom', 'place', '地点', '教室']),
    pickText(course, ['teacher', '教师', '老师']),
    formatWeekRange(course),
  ].filter((part): part is string => Boolean(part))
  const metaLine = metaParts.length > 0 ? metaParts.join(' · ') : null
  const reason = pickText(record, ['reason', '原因', '说明'])

  return { action, courseName, nextName, timeLine, metaLine, reason }
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
  const hasRunning = running !== null
  const fillRaw = total > 0 ? (done / total) * 100 : 0
  const fillPercent = hasRunning ? Math.max(fillRaw, 40) : fillRaw

  return {
    total,
    done,
    ratio: `${done}/${total}`,
    fillPercent,
    hasRunning,
  }
}

function dedupeSteps(steps: string[]) {
  return steps.filter((step, index) => step && steps.indexOf(step) === index)
}

function describeToolStep(item: ToolProgress) {
  const copy = TOOL_THINKING_COPY[item.name]
  if (copy) {
    return item.status === 'done' ? copy.done : copy.running
  }
  return item.status === 'done' ? `${item.label}完成` : `正在${item.label}`
}

function renderInlineRichText(text: string, keyPrefix: string): ReactNode[] {
  const parts: ReactNode[] = []
  const pattern = /(\*\*([^*]+)\*\*|`([^`]+)`)/g
  let cursor = 0
  let match: RegExpExecArray | null
  let index = 0

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > cursor) {
      parts.push(text.slice(cursor, match.index))
    }

    if (match[2]) {
      parts.push(
        <strong className="message__strong" key={`${keyPrefix}-strong-${index}`}>
          {match[2]}
        </strong>,
      )
    } else if (match[3]) {
      parts.push(
        <code className="message__code" key={`${keyPrefix}-code-${index}`}>
          {match[3]}
        </code>,
      )
    }

    cursor = pattern.lastIndex
    index += 1
  }

  if (cursor < text.length) {
    parts.push(text.slice(cursor))
  }

  return parts
}

function renderRichTextContent(content: string, keyPrefix: string): ReactNode {
  const lines = content.replace(/\r\n/g, '\n').split('\n')
  const blocks: ReactNode[] = []
  let listItems: ReactNode[] = []
  let listKind: 'ol' | 'ul' | null = null

  function flushList() {
    if (listItems.length === 0 || listKind === null) {
      return
    }
    const ListTag = listKind
    blocks.push(
      <ListTag className="message__list" key={`${keyPrefix}-list-${blocks.length}`}>
        {listItems}
      </ListTag>,
    )
    listItems = []
    listKind = null
  }

  lines.forEach((line, lineIndex) => {
    const trimmed = line.trim()
    if (!trimmed) {
      flushList()
      return
    }

    const heading = trimmed.match(/^(#{1,3})\s+(.+)$/)
    if (heading) {
      flushList()
      const headingText = heading[2] ?? ''
      blocks.push(
        <p className="message__heading" key={`${keyPrefix}-heading-${lineIndex}`}>
          {renderInlineRichText(headingText, `${keyPrefix}-heading-${lineIndex}`)}
        </p>,
      )
      return
    }

    const unordered = trimmed.match(/^[-*•]\s+(.+)$/)
    if (unordered) {
      const itemText = unordered[1] ?? ''
      if (listKind !== 'ul') {
        flushList()
        listKind = 'ul'
      }
      listItems.push(
        <li key={`${keyPrefix}-li-${lineIndex}`}>
          {renderInlineRichText(itemText, `${keyPrefix}-li-${lineIndex}`)}
        </li>,
      )
      return
    }

    const ordered = trimmed.match(/^\d+[.)]\s+(.+)$/)
    if (ordered) {
      const itemText = ordered[1] ?? ''
      if (listKind !== 'ol') {
        flushList()
        listKind = 'ol'
      }
      listItems.push(
        <li key={`${keyPrefix}-oli-${lineIndex}`}>
          {renderInlineRichText(itemText, `${keyPrefix}-oli-${lineIndex}`)}
        </li>,
      )
      return
    }

    flushList()
    blocks.push(
      <p className="message__paragraph" key={`${keyPrefix}-p-${lineIndex}`}>
        {renderInlineRichText(trimmed, `${keyPrefix}-p-${lineIndex}`)}
      </p>,
    )
  })

  flushList()

  if (blocks.length === 0) {
    return null
  }

  return blocks
}

function splitResultText(content: string) {
  const normalized = content.replace(/\r\n/g, '\n').replace(/[ \t]+/g, ' ').replace(/\n{3,}/g, '\n\n').trim()
  const firstSentence = normalized.match(/^(.+?[。！？!?])(?:\s*(.+))?$/s)
  if (!firstSentence) {
    return { title: normalized, body: null }
  }

  const title = firstSentence[1]?.trim() ?? normalized
  const body = firstSentence[2]?.trim() || null
  return { title, body }
}

function classifyAssistantResult(content: string): AssistantResultView | null {
  const text = content.trim()
  if (!text || text.includes('```') || /^#{1,6}\s/m.test(text)) {
    return null
  }

  const hasUnresolvedConflict = /冲突/.test(text) && !/自动重排/.test(text)
  const hasFailureSignal = /(未写入|没有写入成功|暂时没有|失败|参数不完整|请调整后再试)/.test(text) || hasUnresolvedConflict
  const hasCompletionTarget = /(写入日程|创建.*任务|导入课表|更新课表|设置提醒|安排妥当|自动重排)/.test(text)
  const hasSuccessSignal = /(已把|已写入|已经|成功|安排妥当)/.test(text)

  if (!hasFailureSignal && !(hasCompletionTarget && hasSuccessSignal)) {
    return null
  }

  const { title, body } = splitResultText(text)
  const chips: string[] = []
  const count = text.match(/(\d+)\s*条/)
  if (count?.[1]) {
    chips.push(`${count[1]} 条记录`)
  }
  if (/自动重排/.test(text)) {
    chips.push('含自动重排')
  }
  if (/未写入|没有写入成功|失败/.test(text)) {
    chips.push('需要处理')
  }

  return {
    tone: hasFailureSignal ? 'warning' : 'success',
    eyebrow: hasFailureSignal ? '需要确认' : '已完成',
    title,
    body,
    chips,
  }
}

function thinkingStepsFromProgress(progress: ToolProgress[]) {
  if (progress.length === 0) {
    return DEFAULT_THINKING_STEPS
  }

  const hasRunning = progress.some((item) => item.status === 'running')
  return dedupeSteps([
    '理解需求',
    ...progress.map((item) => describeToolStep(item)),
    hasRunning ? '整理执行结果' : '整理最终回复',
  ])
}

function activeStepFromProgress(progress: ToolProgress[]) {
  const running = progress.find((item) => item.status === 'running')
  if (running) {
    return describeToolStep(running)
  }
  if (progress.length > 0) {
    return '整理最终回复'
  }
  return null
}

function thinkingStepsFromAnsweredAsk(pendingAsk: PendingAsk | null, normalizedAskData: unknown) {
  if (!pendingAsk?.answered) {
    return DEFAULT_THINKING_STEPS
  }

  if (pendingAsk.type === 'review') {
    if (getArrayEntries(normalizedAskData, TASK_ENTRY_KEYS)) {
      return ['确认已收到', '写入日程任务', '整理写入结果']
    }
    if (getArrayEntries(normalizedAskData, COURSE_ACTION_KEYS)) {
      return ['确认已收到', '更新课表信息', '整理更新结果']
    }
    if (getCourseEntries(normalizedAskData)) {
      return ['确认已收到', '导入课表课程', '整理导入结果']
    }
  }

  return ['确认已收到', '执行确认操作', '整理结果']
}

function ThinkingOrb() {
  return (
    <span className="thinking-orb" aria-hidden="true">
      <span />
      <span />
      <span />
    </span>
  )
}

function ThinkingTrail({ activeStep, steps }: { activeStep: string; steps: string[] }) {
  return (
    <div className="thinking-card__trail" aria-label="处理阶段">
      {steps.map((step) => (
        <span className={step === activeStep ? 'is-active' : undefined} key={step}>
          {step}
        </span>
      ))}
    </div>
  )
}

function ThinkingStatus({
  activeStep,
  steps,
  title,
}: {
  activeStep: string
  steps: string[]
  title: string
}) {
  return (
    <section className="thinking-card" role="status" aria-live="polite">
      <div className="thinking-card__head">
        <ThinkingOrb />
        <strong>{title}</strong>
      </div>
      <p className="thinking-card__active">{activeStep}</p>
      <ThinkingTrail activeStep={activeStep} steps={steps} />
    </section>
  )
}

function AssistantResultCard({ result, messageId }: { result: AssistantResultView; messageId: string }) {
  return (
    <section className={`assistant-result assistant-result--${result.tone}`} aria-label={result.eyebrow}>
      <div className="assistant-result__mark" aria-hidden="true">
        {result.tone === 'success' ? '✓' : '!'}
      </div>
      <div className="assistant-result__content">
        <span className="assistant-result__eyebrow">{result.eyebrow}</span>
        <p className="assistant-result__title">{result.title}</p>
        {result.body ? (
          <div className="assistant-result__body">{renderRichTextContent(result.body, `${messageId}-result`)}</div>
        ) : null}
        {result.chips.length > 0 ? (
          <div className="assistant-result__chips" aria-label="结果摘要">
            {result.chips.map((chip) => (
              <span key={chip}>{chip}</span>
            ))}
          </div>
        ) : null}
      </div>
    </section>
  )
}

function RagGrounding({ grounding }: { grounding?: ChatGrounding }) {
  if (!grounding) {
    return null
  }

  const items = grounding.items.slice(0, 3)
  return (
    <aside className="rag-grounding" aria-label={grounding.label}>
      <span className="rag-grounding__label">{grounding.label}</span>
      {items.length > 0 ? (
        <ul className="rag-grounding__list">
          {items.map((item, index) => (
            <li key={`${item.label}-${index}`}>
              <strong>{item.label}</strong>
              {item.source ? <small>{item.source}</small> : null}
              <span>{item.text}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p>{grounding.empty_label ?? '没有命中相关长期记忆'}</p>
      )}
    </aside>
  )
}

function TaskPreviewItem({ task, index }: { task: TaskPreview; index: number }) {
  return (
    <article className="ask-card__plan-item">
      <div className="ask-card__plan-marker" aria-hidden="true">
        {index + 1}
      </div>
      <div className="ask-card__plan-body">
        <div className="ask-card__plan-meta">
          <span>{task.date ?? '安排'}</span>
          <strong>{task.time ?? '待安排'}</strong>
        </div>
        <p className="ask-card__plan-title">{task.title}</p>
        {task.description ? <p className="ask-card__plan-desc">{task.description}</p> : null}
      </div>
    </article>
  )
}

function EditableTaskPreviewItem({
  index,
  onChange,
  onRemove,
  onRestore,
  task,
}: {
  index: number
  onChange: (patch: Partial<Omit<EditableTaskDraft, 'id' | 'removed'>>) => void
  onRemove: () => void
  onRestore: () => void
  task: EditableTaskDraft
}) {
  const preview = taskDraftToPreview(task)
  if (task.removed) {
    return (
      <article className="ask-card__plan-item ask-card__plan-item--removed">
        <div className="ask-card__plan-marker" aria-hidden="true">
          {index + 1}
        </div>
        <div className="ask-card__plan-body">
          <p className="ask-card__plan-title">{preview.title}</p>
          <p className="ask-card__plan-desc">这条任务不会写入日程。</p>
          <button className="ask-card__link-button" type="button" onClick={onRestore}>
            恢复
          </button>
        </div>
      </article>
    )
  }

  return (
    <article className="ask-card__plan-item ask-card__plan-item--editable">
      <div className="ask-card__plan-marker" aria-hidden="true">
        {index + 1}
      </div>
      <div className="ask-card__plan-body">
        <div className="ask-card__plan-meta">
          <span>{preview.date ?? '安排'}</span>
          <strong>{preview.time ?? '待安排'}</strong>
        </div>
        <label className="ask-card__task-field">
          标题
          <input value={task.title} onChange={(event) => onChange({ title: event.target.value })} />
        </label>
        <div className="ask-card__task-grid">
          <label className="ask-card__task-field">
            日期
            <input type="date" value={task.scheduled_date} onChange={(event) => onChange({ scheduled_date: event.target.value })} />
          </label>
          <label className="ask-card__task-field">
            开始
            <input type="time" value={task.start_time} onChange={(event) => onChange({ start_time: event.target.value })} />
          </label>
          <label className="ask-card__task-field">
            结束
            <input type="time" value={task.end_time} onChange={(event) => onChange({ end_time: event.target.value })} />
          </label>
        </div>
        <label className="ask-card__task-field">
          备注
          <textarea value={task.description} onChange={(event) => onChange({ description: event.target.value })} />
        </label>
        <button className="ask-card__link-button ask-card__link-button--danger" type="button" onClick={onRemove}>
          删除这条
        </button>
      </div>
    </article>
  )
}

function CourseActionPreviewItem({ action }: { action: CourseActionPreview }) {
  return (
    <article className={`ask-card__course-action ask-card__course-action--${action.action}`}>
      <div className="ask-card__course-action-main">
        <p>
          {action.nextName ? (
            <>
              <span>{action.courseName}</span>
              <strong>→</strong>
              <span>{action.nextName}</span>
            </>
          ) : (
            <span>{action.courseName}</span>
          )}
        </p>
        {action.timeLine ? <span>{action.timeLine}</span> : null}
        {action.metaLine ? <span>{action.metaLine}</span> : null}
      </div>
      {action.reason ? <p className="ask-card__plan-desc">{action.reason}</p> : null}
    </article>
  )
}

function CoursePreviewItem({ course }: { course: CoursePreview }) {
  return (
    <article className="ask-card__schedule-item">
      <p className="ask-card__schedule-name">{course.name}</p>
      {course.timeLine ? <p className="ask-card__schedule-line">{course.timeLine}</p> : null}
      {course.metaLine ? <p className="ask-card__schedule-line ask-card__schedule-line--muted">{course.metaLine}</p> : null}
    </article>
  )
}

function isUploadParsed(status: ScheduleUploadStatusResponse['status']) {
  return status === 'PARSED' || status === 'READY' || status === 'NEED_PERIOD_TIMES'
}

export function ChatPage() {
  const socketRef = useRef<WebSocket | null>(null)
  const connectionReadyRef = useRef(false)
  const reconnectRef = useRef(0)
  const reconnectTimerRef = useRef<number | null>(null)
  const responseTimeoutRef = useRef<number | null>(null)
  const sendGuardRef = useRef(false)
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
    streamingMessageId,
  } = useChatStore()
  const [draft, setDraft] = useState('')
  const [askDraft, setAskDraft] = useState('')
  const [pendingAttachments, setPendingAttachments] = useState<PendingAttachment[]>([])
  const [attachmentError, setAttachmentError] = useState<string | null>(null)
  const [isBusySending, setIsBusySending] = useState(false)
  const [imageParseBridge, setImageParseBridge] = useState<ImageParseBridgeState | null>(null)
  const [thinkingStepIndex, setThinkingStepIndex] = useState(0)
  const [taskDrafts, setTaskDrafts] = useState<EditableTaskDraft[] | null>(null)
  const hasSpeech = typeof window !== 'undefined' && 'webkitSpeechRecognition' in window
  const inlineTextAsk = isInlineTextAsk(pendingAsk)
  const hasConversation =
    messages.some((message) => message.id !== 'welcome') || pendingAsk !== null || progress.length > 0 || isBusySending
  const shouldRenderAskCard = pendingAsk !== null && !inlineTextAsk && !(pendingAsk.answered && progress.length > 0)
  const isAskBridgePending = Boolean(pendingAsk?.answered && isSending && progress.length === 0)

  const messageOrderMap = useMemo(
    () => new Map(messages.map((message, index) => [message.id, (index + 1) * 10])),
    [messages],
  )
  const tailOrder = messages.length > 0 ? messages.length * 10 : 0
  // CSS `order` only accepts integers; keep cards on integer slots between messages.
  const askCardOrder = shouldRenderAskCard ? anchorOrder(pendingAsk.anchorMessageId, messageOrderMap, tailOrder, 2) : null
  const progressCardOrder =
    progress.length > 0 ? anchorOrder(progressAnchorMessageId, messageOrderMap, tailOrder, 1) : null
  const imageParseBridgeOrder = imageParseBridge ? tailOrder + 1 : null
  const progressInfo = useMemo(() => progressSummary(progress), [progress])
  const showLooseThinking = isBusySending && !imageParseBridge && progress.length === 0 && !pendingAsk?.answered
  const canSend = draft.trim().length > 0 || pendingAttachments.length > 0
  const pendingAttachmentKind = pendingAttachments[0]?.kind ?? null
  const canAddMoreAttachments =
    !isBusySending &&
    (pendingAttachmentKind === null ||
      (pendingAttachmentKind === 'image' && pendingAttachments.length < 3) ||
      (pendingAttachmentKind === 'spreadsheet' && pendingAttachments.length < 1))

  const normalizedAskData = useMemo(() => {
    if (!pendingAsk) {
      return null
    }
    if (pendingAsk.type !== 'review') {
      return pendingAsk.data
    }
    return normalizeReviewData(pendingAsk.data)
  }, [pendingAsk])

  const coursePreviews = useMemo(() => {
    if (!pendingAsk || pendingAsk.type !== 'review' || normalizedAskData == null) {
      return null
    }
    if (getArrayEntries(normalizedAskData, TASK_ENTRY_KEYS) || getArrayEntries(normalizedAskData, COURSE_ACTION_KEYS)) {
      return null
    }
    const courseEntries = getCourseEntries(normalizedAskData)
    if (!courseEntries) {
      return null
    }
    return courseEntries.map((entry, index) => toCoursePreview(entry, index))
  }, [normalizedAskData, pendingAsk])

  const taskPreviews = useMemo(() => {
    if (!pendingAsk || pendingAsk.type !== 'review' || normalizedAskData == null) {
      return null
    }
    const taskEntries = getArrayEntries(normalizedAskData, TASK_ENTRY_KEYS)
    if (!taskEntries) {
      return null
    }
    return taskEntries.map((entry, index) => toTaskPreview(entry, index))
  }, [normalizedAskData, pendingAsk])
  const activeTaskDraftCount = taskDrafts?.filter((task) => !task.removed).length ?? 0

  const courseActionPreviews = useMemo(() => {
    if (!pendingAsk || pendingAsk.type !== 'review' || normalizedAskData == null) {
      return null
    }
    const actionEntries = getArrayEntries(normalizedAskData, COURSE_ACTION_KEYS)
    if (!actionEntries) {
      return null
    }
    return actionEntries.map((entry, index) => toCourseActionPreview(entry, index))
  }, [normalizedAskData, pendingAsk])

  const reviewCount = useMemo(() => {
    if (!pendingAsk || pendingAsk.type !== 'review' || normalizedAskData == null || !coursePreviews) {
      return coursePreviews?.length ?? 0
    }
    const parsedCount = reviewCountFromData(normalizedAskData)
    if (parsedCount !== null) {
      return parsedCount
    }
    return coursePreviews.length
  }, [coursePreviews, normalizedAskData, pendingAsk])

  const scheduleReviewNotice = useMemo(() => {
    if (!pendingAsk || pendingAsk.type !== 'review' || !coursePreviews) {
      return null
    }
    return buildScheduleReviewNotice(pendingAsk.question, reviewCount)
  }, [coursePreviews, pendingAsk, reviewCount])

  const progressThinkingSteps = useMemo(() => thinkingStepsFromProgress(progress), [progress])
  const askBridgeThinkingSteps = useMemo(
    () => thinkingStepsFromAnsweredAsk(pendingAsk, normalizedAskData),
    [normalizedAskData, pendingAsk],
  )
  const visibleThinkingSteps = isAskBridgePending ? askBridgeThinkingSteps : progressThinkingSteps
  const activeProgressStep = useMemo(() => activeStepFromProgress(progress), [progress])
  const activeThinkingStep =
    activeProgressStep ??
    visibleThinkingSteps[thinkingStepIndex % visibleThinkingSteps.length] ??
    DEFAULT_THINKING_STEPS[0]

  useEffect(() => {
    if (!isBusySending && progress.length === 0 && !isAskBridgePending) {
      setThinkingStepIndex(0)
      return
    }

    const timerId = window.setInterval(() => {
      setThinkingStepIndex((current) => current + 1)
    }, 1300)

    return () => {
      window.clearInterval(timerId)
    }
  }, [isAskBridgePending, isBusySending, progress.length, visibleThinkingSteps.length])

  useEffect(() => {
    if (!imageParseBridge) {
      return
    }
    const timerId = window.setInterval(() => {
      setImageParseBridge((current) => {
        if (!current) {
          return current
        }
        const delta = current.progress < 48 ? 6 : current.progress < 74 ? 4 : 2
        const nextProgress = Math.min(IMAGE_PARSE_BRIDGE_MAX, current.progress + delta)
        return nextProgress === current.progress ? current : { ...current, progress: nextProgress }
      })
    }, IMAGE_PARSE_BRIDGE_TICK_MS)
    return () => {
      window.clearInterval(timerId)
    }
  }, [imageParseBridge?.count])

  function clearResponseTimeout() {
    if (responseTimeoutRef.current !== null) {
      window.clearTimeout(responseTimeoutRef.current)
      responseTimeoutRef.current = null
    }
  }

  function lockSending() {
    sendGuardRef.current = true
    setIsBusySending(true)
  }

  function unlockSending() {
    sendGuardRef.current = false
    setIsBusySending(false)
  }

  function startResponseTimeout() {
    clearResponseTimeout()
    responseTimeoutRef.current = window.setTimeout(() => {
      responseTimeoutRef.current = null
      unlockSending()
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
      connectionReadyRef.current = false
      socket.onopen = () => {
        reconnectRef.current = 0
        socket.send(JSON.stringify({ token }))
      }
      socket.onmessage = (event) => {
        clearResponseTimeout()
        unlockSending()
        const serverEvent = JSON.parse(event.data) as ChatServerEvent
        if (serverEvent.type === 'connected' && 'session_id' in serverEvent) {
          connectionReadyRef.current = true
        }
        applyServerEvent(serverEvent)
      }
      socket.onclose = () => {
        connectionReadyRef.current = false
        const waitingForResponse = responseTimeoutRef.current !== null
        clearResponseTimeout()
        unlockSending()
        if (waitingForResponse) {
          applyServerEvent({ type: 'error', message: '聊天连接已断开，请重试' })
        }
        if (closed) {
          return
        }
        const delay = Math.min(30000, 250 * 2 ** reconnectRef.current)
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

  useEffect(() => {
    if (!pendingAsk || pendingAsk.type !== 'review') {
      setTaskDrafts(null)
      return
    }
    const entries = getArrayEntries(normalizeReviewData(pendingAsk.data), TASK_ENTRY_KEYS)
    setTaskDrafts(entries ? entries.map(toEditableTaskDraft) : null)
  }, [pendingAsk?.data, pendingAsk?.question, pendingAsk?.type])

  function updateTaskDraft(id: string, patch: Partial<Omit<EditableTaskDraft, 'id' | 'removed'>>) {
    setTaskDrafts((current) =>
      current?.map((task) => (task.id === id ? { ...task, ...patch } : task)) ?? null,
    )
  }

  function setTaskDraftRemoved(id: string, removed: boolean) {
    setTaskDrafts((current) =>
      current?.map((task) => (task.id === id ? { ...task, removed } : task)) ?? null,
    )
  }

  function buildReviewAnswerPayload(option: string) {
    if (!pendingAsk || pendingAsk.type !== 'review' || !taskDrafts || !isConfirmOption(option)) {
      return option
    }
    const tasks = taskDrafts.filter((task) => !task.removed).map(taskDraftToPayload)
    return `${option}\nreview_override=${JSON.stringify({ tasks })}`
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    const message = draft.trim()
    const attachments = pendingAttachments

    if (sendGuardRef.current || isBusySending) {
      return
    }

    if (attachments.length > 0 && message) {
      setAttachmentError('文字草稿和附件不能一起发送，请分开发送。')
      return
    }

    if (attachments.length > 0) {
      const isImageBatch = attachments[0]?.kind === 'image'
      let bridgeShouldComplete = false
      lockSending()
      setPendingAttachments([])
      if (isImageBatch) {
        setImageParseBridge({ count: attachments.length, progress: IMAGE_PARSE_BRIDGE_START })
      }
      try {
        const uploadResponse = await api.uploadSchedule(attachments.map((item) => item.file))
        if (isImageBatch) {
          await waitForImageParseReady(uploadResponse.file_id)
        }
        const sent = await sendJsonWhenReady(socketRef, connectionReadyRef, {
          message: buildAttachmentPrompt(uploadResponse.file_id, uploadResponse.kind),
        })
        if (!sent) {
          setPendingAttachments(attachments)
          setAttachmentError('聊天连接不可用，请稍后重试')
          unlockSending()
          return
        }
        appendUserMessage(buildAttachmentConfirmation(uploadResponse.kind, uploadResponse.source_file_count))
        setAttachmentError(null)
        startResponseTimeout()
        bridgeShouldComplete = true
      } catch (uploadError) {
        setPendingAttachments(attachments)
        setAttachmentError(uploadError instanceof Error ? uploadError.message : '课表上传失败')
        unlockSending()
      } finally {
        if (isImageBatch) {
          if (bridgeShouldComplete) {
            setImageParseBridge((current) => (current ? { ...current, progress: 100 } : current))
            await new Promise<void>((resolve) => {
              window.setTimeout(resolve, IMAGE_PARSE_BRIDGE_FINISH_DELAY_MS)
            })
          }
          setImageParseBridge(null)
        }
      }
      return
    }

    if (!message) {
      return
    }

    lockSending()
    const shouldAnswerPendingAsk = pendingAsk !== null && !pendingAsk.answered
    const payload = shouldAnswerPendingAsk ? { answer: message } : { message }
    const sent = await sendJsonWhenReady(socketRef, connectionReadyRef, payload)
    if (!sent) {
      applyServerEvent({ type: 'error', message: '聊天连接不可用，请稍后重试' })
      unlockSending()
      return
    }

    appendUserMessage(message)
    if (shouldAnswerPendingAsk) {
      answerAsk(message)
    }
    setDraft('')
    startResponseTimeout()
  }

  async function submitAnswer(answer: string, payloadAnswer = answer) {
    const normalized = answer.trim()
    const payload = payloadAnswer.trim()
    if (!normalized) {
      return
    }

    if (sendGuardRef.current || isBusySending) {
      return
    }

    lockSending()
    const sent = await sendJsonWhenReady(socketRef, connectionReadyRef, { answer: payload })
    if (!sent) {
      applyServerEvent({ type: 'error', message: '聊天连接不可用，请稍后重试' })
      unlockSending()
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
        id: createClientId(),
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

  function preventAttachmentPicker(event: MouseEvent<HTMLLabelElement>) {
    event.preventDefault()
  }

  function handleAttachmentTriggerKeyDown(event: KeyboardEvent<HTMLLabelElement>) {
    if (event.key !== 'Enter' && event.key !== ' ') {
      return
    }

    event.preventDefault()
    if (isBusySending) {
      return
    }

    const input = fileInputRef.current
    if (!input) {
      return
    }

    if (typeof input.showPicker === 'function') {
      input.showPicker()
      return
    }

    input.click()
  }

  async function waitForImageParseReady(fileId: string) {
    const deadline = Date.now() + IMAGE_PARSE_POLL_TIMEOUT_MS
    while (Date.now() < deadline) {
      const status = await api.getScheduleUploadStatus(fileId)

      if (typeof status.progress === 'number') {
        setImageParseBridge((current) => {
          if (!current) {
            return current
          }
          const nextProgress = Math.max(current.progress, Math.min(100, Math.max(0, status.progress)))
          return nextProgress === current.progress ? current : { ...current, progress: nextProgress }
        })
      }

      if (isUploadParsed(status.status)) {
        return
      }
      if (status.status === 'FAILED') {
        throw new Error(status.error || '课表图片解析失败，请稍后重试')
      }

      await new Promise<void>((resolve) => {
        window.setTimeout(resolve, IMAGE_PARSE_POLL_INTERVAL_MS)
      })
    }

    throw new Error('图片解析超时，请稍后重试')
  }

  return (
    <main className={`page chat-page${hasConversation ? ' chat-page--active' : ''}`}>
      {hasConversation ? (
        <section className="chat-session-bar" aria-label="当前对话状态">
          <span>学习规划助手</span>
          <strong>Agent 在线</strong>
        </section>
      ) : (
        <section className="chat-hero" aria-label="学习规划助手">
          <div className="chat-hero__status">
            <span>今日工作台</span>
            <strong>Agent 在线</strong>
          </div>
          <h1>把学习安排说清楚就行</h1>
          <p>考试、作业、课表和提醒都可以直接发给我。我会先整理成计划，确认后再写入日程。</p>
          <div className="chat-hero__suggestions" aria-label="常用请求">
            {['帮我拆一个复习计划', '把报告安排到本周', '检查今天的空闲时间', '修改课表里的课程'].map((suggestion) => (
              <button type="button" key={suggestion} onClick={() => setDraft(suggestion)}>
                {suggestion}
              </button>
            ))}
          </div>
        </section>
      )}
      <div className="message-list">
        {messages.map((message, index) => (
          (() => {
            const uploadReceipt = message.role === 'user' ? parseUploadReceipt(message.content) : null
            const isStreamingMessage = message.role === 'assistant' && streamingMessageId === message.id
            const isRagAnswer = message.role === 'assistant' && message.answerKind === 'rag'
            const assistantResult =
              message.role === 'assistant' && !isStreamingMessage ? (message.result ?? classifyAssistantResult(message.content)) : null
            return (
              <div
                className={`message message--${message.role}${uploadReceipt ? ' message--upload-receipt' : ''}${
                  isStreamingMessage ? ' message--streaming' : ''
                }${isRagAnswer ? ' message--rag' : ''}${
                  assistantResult ? ` message--result message--result-${assistantResult.tone}` : ''
                }${
                  message.id === 'welcome' ? ' message--welcome' : ''
                }`}
                key={message.id}
                style={{ order: (index + 1) * 10 }}
                >
                {message.role === 'assistant' && isRagAnswer ? <RagGrounding grounding={message.grounding} /> : null}
                {uploadReceipt ? (
                  <div className="message__upload-receipt">
                    <span className="message__upload-tag">
                      <PaperclipIcon className="icon icon--xs" />
                      {uploadReceipt.kind === 'image' ? '课表图片' : '课表文件'}
                    </span>
                    <strong className="message__upload-main">{uploadReceipt.text}</strong>
                    <span className="message__upload-sub">
                      {uploadReceipt.kind === 'image'
                        ? `共 ${uploadReceipt.count} 张，等待助手解析`
                        : `共 ${uploadReceipt.count} 个，等待助手解析`}
                    </span>
                  </div>
                ) : assistantResult ? (
                  <AssistantResultCard result={assistantResult} messageId={message.id} />
                ) : message.role === 'assistant' ? (
                  <div className="message__rich">
                    {renderRichTextContent(message.content, message.id)}
                    {isStreamingMessage ? <span className="message__cursor" aria-hidden="true" /> : null}
                  </div>
                ) : (
                  message.content
                )}
              </div>
            )
          })()
        ))}

        {imageParseBridge && imageParseBridgeOrder !== null ? (
          <section className="progress-card progress-card--image-bridge" aria-label="image-parse-bridge" style={{ order: imageParseBridgeOrder }}>
            <div className="progress-card__header">
              <div className="progress-card__title">
                <ThinkingOrb />
                <strong>{`正在解析图片${imageParseBridge.count > 1 ? ` (${imageParseBridge.count} 张)` : ''}`}</strong>
              </div>
              <span className="progress-card__ratio">{`${Math.round(imageParseBridge.progress)}%`}</span>
            </div>
            <div
              className="progress-card__track"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(imageParseBridge.progress)}
            >
              <span className="progress-card__fill progress-card__fill--running" style={{ width: `${imageParseBridge.progress}%` }} />
            </div>
            <p className="progress-card__hint">识别课程结构，整理为可确认的课表卡片</p>
          </section>
        ) : null}

        {progress.length > 0 && progressCardOrder !== null ? (
          <section className="progress-card" aria-label="处理进度" style={{ order: progressCardOrder }}>
            <div className="progress-card__header">
              <div className="progress-card__title">
                {isSending ? <ThinkingOrb /> : null}
                <strong>{isSending ? '正在处理' : '处理完成'}</strong>
              </div>
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
              {isSending ? activeThinkingStep : '处理完成，正在整理回复'}
            </p>
            <ThinkingTrail activeStep={activeThinkingStep} steps={visibleThinkingSteps} />
            <div className="progress-card__items" aria-label="处理轨迹">
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
            </div>
          </section>
        ) : null}

        {shouldRenderAskCard && askCardOrder !== null && pendingAsk ? (
          <section
            className={`ask-card${pendingAsk.answered ? ' ask-card--answered' : ''}`}
            aria-label="需要确认"
            style={{ order: askCardOrder }}
          >
            {scheduleReviewNotice ? (
              <div className="ask-card__review-copy">
                <span className="ask-card__eyebrow">课表确认</span>
                <p className="ask-card__review-title">{scheduleReviewNotice.title}</p>
                {scheduleReviewNotice.note ? (
                  <p className="ask-card__review-note">{scheduleReviewNotice.note}</p>
                ) : null}
              </div>
            ) : (
              <div className="ask-card__intro">
                <span className="ask-card__eyebrow">
                  {pendingAsk.type === 'confirm' ? '确认操作' : pendingAsk.type === 'select' ? '选择下一步' : '需要确认'}
                </span>
                <div className="ask-card__question">{renderRichTextContent(pendingAsk.question, 'ask-question')}</div>
              </div>
            )}

            {pendingAsk.type === 'review' && normalizedAskData != null ? (
              taskPreviews ? (
                <section className="ask-card__plan" aria-label="任务计划预览">
                  <header className="ask-card__plan-head">
                    <div>
                      <strong>计划任务 {taskDrafts ? activeTaskDraftCount : taskPreviews.length}</strong>
                      <span>{taskDrafts ? '可编辑后确认' : '确认后写入日程'}</span>
                    </div>
                  </header>
                  <div className="ask-card__plan-list">
                    {taskDrafts
                      ? taskDrafts.slice(0, TASK_PREVIEW_VISIBLE_COUNT).map((task, index) => (
                          <EditableTaskPreviewItem
                            index={index}
                            key={task.id}
                            onChange={(patch) => updateTaskDraft(task.id, patch)}
                            onRemove={() => setTaskDraftRemoved(task.id, true)}
                            onRestore={() => setTaskDraftRemoved(task.id, false)}
                            task={task}
                          />
                        ))
                      : taskPreviews.slice(0, TASK_PREVIEW_VISIBLE_COUNT).map((task, index) => (
                          <TaskPreviewItem task={task} index={index} key={`${task.title}-${index}`} />
                        ))}
                    {(taskDrafts ?? taskPreviews).length > TASK_PREVIEW_VISIBLE_COUNT ? (
                      <details className="ask-card__details">
                        <summary>{`展开剩余 ${(taskDrafts ?? taskPreviews).length - TASK_PREVIEW_VISIBLE_COUNT} 条任务`}</summary>
                        <div className="ask-card__details-list">
                          {taskDrafts
                            ? taskDrafts.slice(TASK_PREVIEW_VISIBLE_COUNT).map((task, index) => (
                                <EditableTaskPreviewItem
                                  index={index + TASK_PREVIEW_VISIBLE_COUNT}
                                  key={task.id}
                                  onChange={(patch) => updateTaskDraft(task.id, patch)}
                                  onRemove={() => setTaskDraftRemoved(task.id, true)}
                                  onRestore={() => setTaskDraftRemoved(task.id, false)}
                                  task={task}
                                />
                              ))
                            : taskPreviews.slice(TASK_PREVIEW_VISIBLE_COUNT).map((task, index) => (
                                <TaskPreviewItem
                                  task={task}
                                  index={index + TASK_PREVIEW_VISIBLE_COUNT}
                                  key={`${task.title}-${index + TASK_PREVIEW_VISIBLE_COUNT}`}
                                />
                              ))}
                        </div>
                      </details>
                    ) : null}
                  </div>
                </section>
              ) : courseActionPreviews ? (
                <section className="ask-card__course-actions" aria-label="课程修改预览">
                  <header className="ask-card__plan-head">
                    <div>
                      <strong>课程维护 {courseActionPreviews.length}</strong>
                      <span>确认后更新课表</span>
                    </div>
                  </header>
                  <div className="ask-card__course-action-list">
                    {courseActionPreviews.slice(0, COURSE_ACTION_VISIBLE_COUNT).map((action, index) => (
                      <CourseActionPreviewItem action={action} key={`${action.courseName}-${index}`} />
                    ))}
                    {courseActionPreviews.length > COURSE_ACTION_VISIBLE_COUNT ? (
                      <details className="ask-card__details">
                        <summary>{`展开剩余 ${courseActionPreviews.length - COURSE_ACTION_VISIBLE_COUNT} 条修改`}</summary>
                        <div className="ask-card__details-list">
                          {courseActionPreviews.slice(COURSE_ACTION_VISIBLE_COUNT).map((action, index) => (
                            <CourseActionPreviewItem
                              action={action}
                              key={`${action.courseName}-${index + COURSE_ACTION_VISIBLE_COUNT}`}
                            />
                          ))}
                        </div>
                      </details>
                    ) : null}
                  </div>
                </section>
              ) : coursePreviews ? (
                <section className="ask-card__schedule">
                  <header className="ask-card__schedule-head">
                    <strong>识别课程 {reviewCount}</strong>
                    <span>请确认信息是否正确</span>
                  </header>
                  <div className="ask-card__schedule-list" aria-label="识别课程列表">
                    {coursePreviews.length > 0 ? (
                      <>
                        {coursePreviews.slice(0, COURSE_PREVIEW_VISIBLE_COUNT).map((course, index) => (
                          <CoursePreviewItem course={course} key={`${course.name}-${index}`} />
                        ))}
                        {coursePreviews.length > COURSE_PREVIEW_VISIBLE_COUNT ? (
                          <details className="ask-card__details">
                            <summary>{`展开剩余 ${coursePreviews.length - COURSE_PREVIEW_VISIBLE_COUNT} 门课程`}</summary>
                            <div className="ask-card__details-list">
                              {coursePreviews.slice(COURSE_PREVIEW_VISIBLE_COUNT).map((course, index) => (
                                <CoursePreviewItem course={course} key={`${course.name}-${index + COURSE_PREVIEW_VISIBLE_COUNT}`} />
                              ))}
                            </div>
                          </details>
                        ) : null}
                      </>
                    ) : (
                      <p className="ask-card__schedule-empty">未识别到课程内容，请返回检查文件。</p>
                    )}
                  </div>
                </section>
              ) : normalizedAskData && typeof normalizedAskData === 'object' && !Array.isArray(normalizedAskData) ? (
                <dl className="ask-card__kv" aria-label="确认详情">
                  {Object.entries(normalizedAskData as Record<string, unknown>)
                    .filter(([key]) => key !== 'courses')
                    .map(([key, value]) => (
                      <div className="ask-card__kv-row" key={key}>
                        <dt>{key}</dt>
                        <dd>{stringifyDetailValue(value)}</dd>
                      </div>
                    ))}
                </dl>
              ) : (
                <p className="ask-card__plain">{stringifyDetailValue(normalizedAskData)}</p>
              )
            ) : null}

            {pendingAsk.answered ? (
              <div className="ask-card__answered" role={isAskBridgePending ? 'status' : undefined} aria-live="polite">
                <p className="ask-card__answered-title">已选择：{pendingAsk.answered}</p>
                {isAskBridgePending ? (
                  <p className="ask-card__answered-hint">
                    <ThinkingOrb />
                    <span>{activeThinkingStep}</span>
                  </p>
                ) : null}
                {isAskBridgePending ? <ThinkingTrail activeStep={activeThinkingStep} steps={visibleThinkingSteps} /> : null}
              </div>
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
                    <button type="button" key={option} onClick={() => submitAnswer(option, buildReviewAnswerPayload(option))}>
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

      {pendingAttachments.length > 0 && !imageParseBridge ? (
        <section className="attachment-tray" aria-label="待发送附件">
          <div className="attachment-tray__head">
            <strong>待发送附件 {pendingAttachments.length}</strong>
            {canAddMoreAttachments ? (
              <label
                htmlFor={isBusySending ? undefined : ATTACHMENT_INPUT_ID}
                className="attachment-tray__add-button"
                aria-label="继续添加附件"
                role="button"
                aria-disabled={isBusySending}
                tabIndex={isBusySending ? -1 : 0}
                onClick={isBusySending ? preventAttachmentPicker : undefined}
                onKeyDown={handleAttachmentTriggerKeyDown}
              >
                继续添加
              </label>
            ) : null}
          </div>
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

      {showLooseThinking ? (
        <ThinkingStatus activeStep={activeThinkingStep} steps={visibleThinkingSteps} title="正在思考" />
      ) : null}

      <form className="chat-input" onSubmit={submit}>
        <button
          type="button"
          className="icon-button chat-input__icon-btn"
          aria-label="语音输入"
          onClick={startSpeech}
          disabled={!hasSpeech || isBusySending}
        >
          <MicIcon className="icon" />
        </button>
        <input aria-label="输入消息" value={draft} onChange={(event) => setDraft(event.target.value)} />
        {canSend ? (
          <button type="submit" className="primary-button chat-input__action-btn" aria-label="发送消息" disabled={isBusySending}>
            <SendIcon className="icon" />
          </button>
        ) : (
          <label
            htmlFor={isBusySending ? undefined : ATTACHMENT_INPUT_ID}
            className="icon-button chat-input__action-btn chat-input__file-trigger"
            aria-label="添加附件"
            role="button"
            aria-disabled={isBusySending}
            tabIndex={isBusySending ? -1 : 0}
            onClick={isBusySending ? preventAttachmentPicker : undefined}
            onKeyDown={handleAttachmentTriggerKeyDown}
          >
            <PlusIcon className="icon" />
          </label>
        )}
        <input
          id={ATTACHMENT_INPUT_ID}
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
