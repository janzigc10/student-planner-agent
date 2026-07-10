import { afterEach, describe, expect, it, vi } from 'vitest'

import { createInitialChatState, reduceChatEvent, toolLabel, useChatStore } from './chatStore'

afterEach(() => {
  vi.unstubAllGlobals()
  useChatStore.setState(createInitialChatState())
})

describe('chat event reducer', () => {
  it('tracks tool progress from tool_call and tool_result events', () => {
    let state = createInitialChatState()

    state = reduceChatEvent(state, { type: 'tool_call', name: 'get_free_slots', args: {} })
    expect(state.progress).toEqual([{ name: 'get_free_slots', label: '查询空闲时间', status: 'running' }])

    state = reduceChatEvent(state, { type: 'tool_result', name: 'get_free_slots', result: { count: 1 } })
    expect(state.progress[0].status).toBe('done')
  })

  it('uses concrete labels for task mutation progress', () => {
    expect(toolLabel('create_task')).toBe('创建任务')
    expect(toolLabel('update_task')).toBe('更新任务')
    expect(toolLabel('complete_task')).toBe('完成任务')
  })

  it('adds assistant text and stores ask_user cards', () => {
    let state = createInitialChatState()

    state = reduceChatEvent(state, { type: 'text', content: '搞定了' })
    state = reduceChatEvent(state, {
      type: 'ask_user',
      question: '确认吗？',
      ask_type: 'confirm',
      options: ['确认', '取消'],
      data: { exams: ['高数'] },
    })

    expect(state.messages.at(-1)).toMatchObject({ role: 'assistant', content: '搞定了' })
    expect(state.pendingAsk?.question).toBe('确认吗？')
  })

  it('clears stale errors when later server events arrive', () => {
    let state = createInitialChatState()

    state = reduceChatEvent(state, { type: 'error', message: '助手暂时没有响应，请重试' })
    expect(state.error).toBe('助手暂时没有响应，请重试')

    state = reduceChatEvent(state, { type: 'tool_call', name: 'get_free_slots', args: {} })
    expect(state.error).toBeNull()
    expect(state.progress).toEqual([{ name: 'get_free_slots', label: '查询空闲时间', status: 'running' }])
  })

  it('accepts recoverable provider error metadata while showing the message', () => {
    const state = reduceChatEvent(createInitialChatState(), {
      type: 'error',
      code: 'llm_provider_unavailable',
      recoverable: true,
      message: '模型服务暂时连接不上，刚才的操作还没有执行。请稍后重试，或检查当前网络/模型服务配置。',
    })

    expect(state.error).toBe('模型服务暂时连接不上，刚才的操作还没有执行。请稍后重试，或检查当前网络/模型服务配置。')
    expect(state.isSending).toBe(false)
    expect(state.progress).toEqual([])
  })

  it('renders review follow-up asks as assistant text when there is no structured payload', () => {
    let state = createInitialChatState()

    state = reduceChatEvent(state, {
      type: 'ask_user',
      question: '请补充第1-2节与第3-4节时间',
      ask_type: 'review',
    })

    expect(state.messages.at(-1)).toMatchObject({
      role: 'assistant',
      content: '请补充第1-2节与第3-4节时间',
    })
    expect(state.pendingAsk?.type).toBe('review')
    expect(state.pendingAsk?.data).toBeNull()
    expect(state.pendingAsk?.options).toEqual([])
  })

  it('clears stale pending asks when websocket reconnects', () => {
    let state = createInitialChatState()

    state = reduceChatEvent(state, {
      type: 'ask_user',
      question: '确认导入吗？',
      ask_type: 'confirm',
      options: ['确认', '取消'],
    })
    expect(state.pendingAsk).not.toBeNull()

    state = reduceChatEvent(state, { type: 'connected', session_id: 'new-session' })
    expect(state.pendingAsk).toBeNull()
    expect(state.progress).toEqual([])
    expect(state.isSending).toBe(false)
  })

  it('hides progress immediately when ask_user arrives', () => {
    let state = createInitialChatState()

    state = reduceChatEvent(state, { type: 'tool_call', name: 'parse_schedule', args: {} })
    expect(state.progress.length).toBeGreaterThan(0)
    expect(state.isSending).toBe(true)

    state = reduceChatEvent(state, {
      type: 'ask_user',
      question: '请确认导入',
      ask_type: 'confirm',
      options: ['确认', '取消'],
      data: { count: 1 },
    })

    expect(state.progress).toEqual([])
    expect(state.progressAnchorMessageId).toBeNull()
    expect(state.isSending).toBe(false)
    expect(state.pendingAsk).not.toBeNull()
  })

  it('clears answered pending ask after follow-up assistant text', () => {
    let state = createInitialChatState()

    state = reduceChatEvent(state, {
      type: 'ask_user',
      question: '请确认导入',
      ask_type: 'confirm',
      options: ['确认', '取消'],
      data: { count: 1 },
    })
    state = {
      ...state,
      pendingAsk: state.pendingAsk ? { ...state.pendingAsk, answered: '确认' } : null,
    }

    state = reduceChatEvent(state, { type: 'text', content: '已为你完成导入。' })
    expect(state.pendingAsk).toBeNull()
  })

  it('clears answered pending ask on done event', () => {
    let state = createInitialChatState()

    state = reduceChatEvent(state, {
      type: 'ask_user',
      question: '请确认导入',
      ask_type: 'confirm',
      options: ['确认', '取消'],
      data: { count: 1 },
    })
    state = {
      ...state,
      pendingAsk: state.pendingAsk ? { ...state.pendingAsk, answered: '确认' } : null,
    }

    state = reduceChatEvent(state, { type: 'done' })
    expect(state.pendingAsk).toBeNull()
  })

  it('builds assistant content incrementally from text_delta events', () => {
    let state = createInitialChatState()

    state = reduceChatEvent(state, { type: 'text_delta', message_id: 'stream-1', delta: 'Hello ' })
    state = reduceChatEvent(state, { type: 'text_delta', message_id: 'stream-1', delta: 'world' })

    expect(state.messages.at(-1)).toMatchObject({
      id: 'stream-1',
      role: 'assistant',
      content: 'Hello world',
    })
  })

  it('final text event with same message_id should not duplicate streamed message', () => {
    let state = createInitialChatState()

    state = reduceChatEvent(state, { type: 'text_delta', message_id: 'stream-2', delta: 'Hello ' })
    state = reduceChatEvent(state, { type: 'text', message_id: 'stream-2', content: 'Hello world!' })

    const streamedMessages = state.messages.filter((message) => message.id === 'stream-2')
    expect(streamedMessages).toHaveLength(1)
    expect(streamedMessages[0]?.content).toBe('Hello world!')
  })

  it('keeps RAG answer metadata across streamed and final text events', () => {
    let state = createInitialChatState()
    const grounding = {
      kind: 'rag' as const,
      label: '基于长期记忆',
      items: [{ label: '偏好', text: '高数复习优先安排在晚上' }],
    }

    state = reduceChatEvent(state, {
      type: 'text_delta',
      message_id: 'rag-stream',
      delta: '我记得',
      answer_kind: 'rag',
      grounding,
    })
    state = reduceChatEvent(state, {
      type: 'text',
      message_id: 'rag-stream',
      content: '我记得你更适合晚上复习高数。',
    })

    expect(state.messages.at(-1)).toMatchObject({
      id: 'rag-stream',
      answerKind: 'rag',
      grounding,
      content: '我记得你更适合晚上复习高数。',
    })
  })

  it('merges structured result and final text events with the same message id', () => {
    let state = createInitialChatState()

    state = reduceChatEvent(state, {
      type: 'result',
      message_id: 'result-1',
      content: '已把 2 条复习任务写入日程。',
      tone: 'success',
      eyebrow: '已完成',
      title: '已把 2 条复习任务写入日程。',
      chips: ['2 条记录'],
    })
    state = reduceChatEvent(state, {
      type: 'text',
      message_id: 'result-1',
      content: '已把 2 条复习任务写入日程。',
    })

    const resultMessages = state.messages.filter((message) => message.id === 'result-1')
    expect(resultMessages).toHaveLength(1)
    expect(resultMessages[0]?.result).toMatchObject({
      tone: 'success',
      title: '已把 2 条复习任务写入日程。',
      chips: ['2 条记录'],
    })
  })

  it('appends a user message even when crypto.randomUUID is unavailable', () => {
    vi.stubGlobal('crypto', {} as Crypto)

    expect(() => useChatStore.getState().appendUserMessage('测试消息')).not.toThrow()

    const lastMessage = useChatStore.getState().messages.at(-1)
    expect(lastMessage).toMatchObject({
      role: 'user',
      content: '测试消息',
    })
    expect(lastMessage?.id).toMatch(/^client-/)
  })

  it('creates assistant message ids without crypto.randomUUID when text arrives without message_id', () => {
    vi.stubGlobal('crypto', {} as Crypto)

    const state = reduceChatEvent(createInitialChatState(), { type: 'text', content: '补充反馈' })

    expect(state.messages.at(-1)).toMatchObject({
      role: 'assistant',
      content: '补充反馈',
    })
    expect(state.messages.at(-1)?.id).toMatch(/^client-/)
  })
})
