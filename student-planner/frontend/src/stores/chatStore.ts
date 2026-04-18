import { create } from 'zustand'

export type MessageRole = 'assistant' | 'user'
export type ToolStatus = 'running' | 'done'
export type AskType = 'confirm' | 'select' | 'review'

export interface ChatMessage {
  id: string
  role: MessageRole
  content: string
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

export interface ChatStateSnapshot {
  messages: ChatMessage[]
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
  | { type: 'text'; content: string }
  | { type: 'ask_user'; question: string; ask_type?: AskType; mode?: AskType; options?: string[]; data?: unknown }
  | { type: 'error'; message: string }
  | { type: 'done' }

const toolLabels: Record<string, string> = {
  get_free_slots: '查询空闲时间',
  create_study_plan: '生成复习计划',
  parse_schedule: '解析课表',
  parse_schedule_image: '识别课表图片',
  list_courses: '查看课表',
  list_tasks: '查看任务',
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

export function createInitialChatState(): ChatStateSnapshot {
  return {
    messages: [{ id: 'welcome', role: 'assistant', content: '你好！我是你的学习规划助手，有什么可以帮你的？' }],
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

  if (event.type === 'text') {
    const shouldClearAnsweredAsk = Boolean(state.pendingAsk?.answered)
    return {
      ...clearError(state),
      messages: [...state.messages, { id: crypto.randomUUID(), role: 'assistant', content: event.content }],
      pendingAsk: shouldClearAnsweredAsk ? null : state.pendingAsk,
    }
  }

  if (event.type === 'ask_user') {
    const inferredType: AskType =
      event.ask_type ?? event.mode ?? ((event.options?.length ?? 0) > 0 ? 'select' : 'review')
    const inlineReviewAsk = inferredType === 'review' && (event.options?.length ?? 0) === 0 && event.data == null
    return {
      ...clearError(state),
      progress: [],
      progressAnchorMessageId: null,
      isSending: false,
      messages: inlineReviewAsk
        ? [...state.messages, { id: crypto.randomUUID(), role: 'assistant', content: event.question }]
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
    return { ...state, error: event.message, isSending: false, progress: [], progressAnchorMessageId: null }
  }

  if (event.type === 'done') {
    return {
      ...clearError(state),
      isSending: false,
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
      messages: [...state.messages, { id: crypto.randomUUID(), role: 'user', content }],
      isSending: true,
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
