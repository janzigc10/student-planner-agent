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
})
