import { describe, expect, it } from 'vitest'

import { createInitialChatState, reduceChatEvent } from './chatStore'

describe('chat event reducer', () => {
  it('tracks tool progress from tool_call and tool_result events', () => {
    let state = createInitialChatState()

    state = reduceChatEvent(state, { type: 'tool_call', name: 'get_free_slots', args: {} })
    expect(state.progress).toEqual([{ name: 'get_free_slots', label: '查询空闲时间', status: 'running' }])

    state = reduceChatEvent(state, { type: 'tool_result', name: 'get_free_slots', result: { count: 1 } })
    expect(state.progress[0].status).toBe('done')
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
})
