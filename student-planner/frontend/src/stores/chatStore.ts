import { create } from 'zustand'

import { createClientId } from '../createClientId'

export type MessageRole = 'assistant' | 'user'
export type ToolStatus = 'running' | 'done'
export type AskType = 'confirm' | 'select' | 'review'

export interface ChatMessage {
  id: string
  role: MessageRole
  content: string
  result?: ChatMessageResult
  answerKind?: ChatAnswerKind
  grounding?: ChatGrounding
}

export interface ToolProgress {
  name: string
  label: string
  status: ToolStatus
}

export interface PendingAsk {
  question: string
  type: AskType
  options: string[]
  data: unknown
  answered?: string
  anchorMessageId: string | null
}

export interface ChatMessageResult {
  tone: 'success' | 'warning'
  eyebrow: string
  title: string
  body: string | null
  chips: string[]
}

export type ChatAnswerKind = 'rag'

export interface ChatGroundingItem {
  label: string
  text: string
}

export interface ChatGrounding {
  kind: 'memory' | 'rag'
  label: string
  empty_label?: string
  count?: number
  items: ChatGroundingItem[]
}

export interface ChatStateSnapshot {
  messages: ChatMessage[]
  streamingMessageId: string | null
  progress: ToolProgress[]
  progressAnchorMessageId: string | null
  pendingAsk: PendingAsk | null
  error: string | null
  isSending: boolean
}

export type ChatServerEvent =
  | { type: 'connected'; session_id: string }
  | { type: 'tool_call'; name: string; args?: unknown }
  | { type: 'tool_result'; name: string; result?: unknown }
  | {
      type: 'result'
      message_id?: string
      content: string
      tone?: ChatMessageResult['tone']
      eyebrow?: string
      title?: string
      body?: string | null
      chips?: string[]
    }
  | {
      type: 'text_delta'
      delta: string
      message_id?: string
      answer_kind?: ChatAnswerKind
      grounding?: ChatGrounding
    }
  | {
      type: 'text'
      content: string
      message_id?: string
      result?: ChatMessageResult
      answer_kind?: ChatAnswerKind
      grounding?: ChatGrounding
    }
  | { type: 'ask_user'; question: string; ask_type?: AskType; mode?: AskType; options?: string[]; data?: unknown }
  | { type: 'error'; message: string; code?: string; recoverable?: boolean }
  | { type: 'done' }

const toolLabels: Record<string, string> = {
  add_course: '新增课程',
  get_free_slots: '查询空闲时间',
  create_study_plan: '生成复习计划',
  create_work_plan: '生成作业计划',
  parse_schedule: '解析课表',
  parse_schedule_image: '识别课表图片',
  save_schedule_metadata: '补全课表信息',
  bulk_import_courses: '导入课程',
  list_courses: '查看课表',
  update_course: '更新课程',
  delete_course: '删除课程',
  list_tasks: '查看任务',
  create_task: '创建任务',
  update_task: '更新任务',
  complete_task: '完成任务',
  set_reminder: '设置提醒',
  recall_memory: '检索记忆',
  ask_user: '等待确认',
}

export function toolLabel(name: string) {
  return toolLabels[name] ?? '处理中'
}

function clearError(state: ChatStateSnapshot): ChatStateSnapshot {
  if (state.error === null) {
    return state
  }
  return { ...state, error: null }
}

function mergeAnswerMetadata(
  message: ChatMessage,
  event: { answer_kind?: ChatAnswerKind; grounding?: ChatGrounding },
): Pick<ChatMessage, 'answerKind' | 'grounding'> {
  return {
    answerKind: event.answer_kind ?? message.answerKind,
    grounding: event.grounding ?? message.grounding,
  }
}

export function createInitialChatState(): ChatStateSnapshot {
  return {
    messages: [{ id: 'welcome', role: 'assistant', content: '你好！我是你的学习规划助手，有什么可以帮你的？' }],
    streamingMessageId: null,
    progress: [],
    progressAnchorMessageId: null,
    pendingAsk: null,
    error: null,
    isSending: false,
  }
}

export function reduceChatEvent(state: ChatStateSnapshot, event: ChatServerEvent): ChatStateSnapshot {
  if (event.type === 'connected') {
    return {
      ...clearError(state),
      streamingMessageId: null,
      pendingAsk: null,
      progress: [],
      progressAnchorMessageId: null,
      isSending: false,
    }
  }

  if (event.type === 'tool_call') {
    const nextProgress = state.progress.filter((item) => item.name !== event.name)
    const nextAnchorMessageId = state.progress.length === 0 ? (state.messages.at(-1)?.id ?? null) : state.progressAnchorMessageId
    return {
      ...clearError(state),
      progress: [...nextProgress, { name: event.name, label: toolLabel(event.name), status: 'running' }],
      progressAnchorMessageId: nextAnchorMessageId,
      isSending: true,
    }
  }

  if (event.type === 'tool_result') {
    return {
      ...clearError(state),
      progress: state.progress.map((item) => (item.name === event.name ? { ...item, status: 'done' } : item)),
    }
  }

  if (event.type === 'text_delta') {
    if (!event.delta) {
      return state
    }

    const messageId = event.message_id ?? state.streamingMessageId ?? createClientId()
    const shouldClearAnsweredAsk = Boolean(state.pendingAsk?.answered)
    const messageIndex = state.messages.findIndex((message) => message.id === messageId)
    const nextMessages: ChatMessage[] =
      messageIndex >= 0
        ? state.messages.map((message, index) =>
            index === messageIndex
              ? {
                  ...message,
                  role: 'assistant' as const,
                  content: `${message.content}${event.delta}`,
                  ...mergeAnswerMetadata(message, event),
                }
              : message,
          )
        : [
            ...state.messages,
            {
              id: messageId,
              role: 'assistant' as const,
              content: event.delta,
              answerKind: event.answer_kind,
              grounding: event.grounding,
            },
          ]

    return {
      ...clearError(state),
      messages: nextMessages,
      streamingMessageId: messageId,
      pendingAsk: shouldClearAnsweredAsk ? null : state.pendingAsk,
      isSending: true,
    }
  }

  if (event.type === 'text') {
    const messageId = event.message_id ?? state.streamingMessageId ?? createClientId()
    const shouldClearAnsweredAsk = Boolean(state.pendingAsk?.answered)
    const messageIndex = state.messages.findIndex((message) => message.id === messageId)
    const nextMessages: ChatMessage[] =
      messageIndex >= 0
        ? state.messages.map((message, index) =>
            index === messageIndex
              ? {
                  ...message,
                  role: 'assistant' as const,
                  content: event.content,
                  result: event.result ?? message.result,
                  ...mergeAnswerMetadata(message, event),
                }
              : message,
          )
        : [
            ...state.messages,
            {
              id: messageId,
              role: 'assistant' as const,
              content: event.content,
              result: event.result,
              answerKind: event.answer_kind,
              grounding: event.grounding,
            },
          ]

    return {
      ...clearError(state),
      messages: nextMessages,
      streamingMessageId: null,
      pendingAsk: shouldClearAnsweredAsk ? null : state.pendingAsk,
    }
  }

  if (event.type === 'result') {
    const messageId = event.message_id ?? state.streamingMessageId ?? createClientId()
    const shouldClearAnsweredAsk = Boolean(state.pendingAsk?.answered)
    const result: ChatMessageResult = {
      tone: event.tone ?? 'success',
      eyebrow: event.eyebrow ?? (event.tone === 'warning' ? '需要确认' : '已完成'),
      title: event.title || event.content,
      body: event.body ?? null,
      chips: event.chips ?? [],
    }
    const messageIndex = state.messages.findIndex((message) => message.id === messageId)
    const nextMessages: ChatMessage[] =
      messageIndex >= 0
        ? state.messages.map((message, index) =>
            index === messageIndex
              ? { ...message, role: 'assistant' as const, content: event.content, result }
              : message,
          )
        : [...state.messages, { id: messageId, role: 'assistant' as const, content: event.content, result }]

    return {
      ...clearError(state),
      messages: nextMessages,
      streamingMessageId: null,
      pendingAsk: shouldClearAnsweredAsk ? null : state.pendingAsk,
    }
  }

  if (event.type === 'ask_user') {
    const inferredType: AskType =
      event.ask_type ?? event.mode ?? ((event.options?.length ?? 0) > 0 ? 'select' : 'review')
    const inlineReviewAsk = inferredType === 'review' && (event.options?.length ?? 0) === 0 && event.data == null
    return {
      ...clearError(state),
      streamingMessageId: null,
      progress: [],
      progressAnchorMessageId: null,
      isSending: false,
      messages: inlineReviewAsk
        ? [...state.messages, { id: createClientId(), role: 'assistant' as const, content: event.question }]
        : state.messages,
      pendingAsk: {
        question: event.question,
        type: inferredType,
        options: event.options ?? [],
        data: event.data ?? null,
        anchorMessageId: state.messages.at(-1)?.id ?? null,
      },
    }
  }

  if (event.type === 'error') {
    return {
      ...state,
      error: event.message,
      isSending: false,
      streamingMessageId: null,
      progress: [],
      progressAnchorMessageId: null,
    }
  }

  if (event.type === 'done') {
    return {
      ...clearError(state),
      isSending: false,
      streamingMessageId: null,
      progress: [],
      progressAnchorMessageId: null,
      pendingAsk: state.pendingAsk?.answered ? null : state.pendingAsk,
    }
  }

  return state
}

interface ChatStore extends ChatStateSnapshot {
  appendUserMessage: (content: string) => void
  applyServerEvent: (event: ChatServerEvent) => void
  answerAsk: (answer: string) => void
}

export const useChatStore = create<ChatStore>((set) => ({
  ...createInitialChatState(),
  appendUserMessage(content) {
    set((state) => ({
      messages: [...state.messages, { id: createClientId(), role: 'user' as const, content }],
      isSending: true,
      streamingMessageId: null,
      error: null,
    }))
  },
  applyServerEvent(event) {
    set((state) => reduceChatEvent(state, event))
  },
  answerAsk(answer) {
    set((state) => {
      if (!state.pendingAsk) {
        return state
      }
      return {
        ...state,
        pendingAsk: { ...state.pendingAsk, answered: answer },
        isSending: true,
        error: null,
      }
    })
  },
}))
