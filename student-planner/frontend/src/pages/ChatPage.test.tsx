import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '../api/client'
import { createInitialChatState, useChatStore } from '../stores/chatStore'
import { ChatPage } from './ChatPage'

function createFile(name: string, type: string) {
  return new File(['content'], name, { type })
}

function createUploadStatus(
  overrides: Partial<{
    file_id: string
    kind: 'image' | 'spreadsheet'
    status: 'QUEUED' | 'PARSING' | 'PARSED' | 'FAILED' | 'READY' | 'NEED_PERIOD_TIMES'
    progress: number
    error: string | null
    courses: unknown[]
    count: number
    missing_periods: string[]
    source_file_count: number
  }> = {},
) {
  return {
    file_id: 'schedule-file-status',
    kind: 'image' as const,
    status: 'PARSED' as const,
    progress: 100,
    error: null,
    courses: [],
    count: 0,
    missing_periods: [],
    source_file_count: 1,
    ...overrides,
  }
}

class MockWebSocket {
  static OPEN = 1
  static instances: MockWebSocket[] = []

  readonly url: string
  readonly send = vi.fn()
  readonly close = vi.fn()
  readyState = MockWebSocket.OPEN
  onopen: (() => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
    queueMicrotask(() => {
      this.onopen?.()
      this.onmessage?.(
        new MessageEvent('message', {
          data: JSON.stringify({ type: 'connected', session_id: 'mock-session' }),
        }),
      )
    })
  }
}

function readOrder(node: Node) {
  const raw = (node as HTMLElement).style.order
  return raw ? Number(raw) : 0
}

function expectNodeBefore(first: Node, second: Node) {
  expect(readOrder(first)).toBeLessThan(readOrder(second))
}

async function renderReadyChatPage() {
  const result = render(<ChatPage />)
  await act(async () => {
    await Promise.resolve()
  })
  return result
}

describe('ChatPage attachment drafting', () => {
  beforeEach(() => {
    window.localStorage.clear()
    window.localStorage.setItem('student-planner-token', 'stored-token')
    useChatStore.setState(createInitialChatState())
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.spyOn(api, 'uploadSchedule').mockRejectedValue(new Error('should not upload during drafting'))
    vi.spyOn(api, 'getScheduleUploadStatus').mockResolvedValue(createUploadStatus())
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('keeps two selected images in the pending tray instead of uploading immediately', async () => {
    render(<ChatPage />)

    const input = screen.getByLabelText('上传课表')
    await userEvent.upload(input, [
      createFile('math-1.png', 'image/png'),
      createFile('math-2.jpg', 'image/jpeg'),
    ])

    expect(api.uploadSchedule).not.toHaveBeenCalled()
    expect(await screen.findByRole('region', { name: '待发送附件' })).toHaveTextContent('待发送附件 2')
    expect(screen.getByText('math-1.png')).toBeInTheDocument()
    expect(screen.getByText('math-2.jpg')).toBeInTheDocument()
  })

  it('shows a plus-only primary action when no draft and no pending attachments', () => {
    render(<ChatPage />)

    expect(screen.getByRole('button', { name: '添加附件' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '发送消息' })).not.toBeInTheDocument()
    expect(screen.queryByText('附件')).not.toBeInTheDocument()
    expect(screen.queryByText('语音')).not.toBeInTheDocument()
    expect(screen.queryByText('发送')).not.toBeInTheDocument()
  })

  it('keeps the primary add-attachment trigger wired to the native file input element', () => {
    const { container } = render(<ChatPage />)

    const trigger = container.querySelector('.chat-input__action-btn')
    const input = container.querySelector('.chat-input__file-input')

    expect(trigger).toBeTruthy()
    expect(input).toBeTruthy()
    expect(trigger?.tagName).toBe('LABEL')
    expect(trigger).toHaveAttribute('for', input?.getAttribute('id'))
  })

  it.skip('uses a native file input trigger for the primary add-attachment control', () => {
    render(<ChatPage />)

    const trigger = screen.getByRole('button', { name: '娣诲姞闄勪欢' })
    const input = screen.getByLabelText('涓婁紶璇捐〃')

    expect(trigger.tagName).toBe('LABEL')
    expect(trigger).toHaveAttribute('for', input.getAttribute('id'))
  })

  it('switches primary action from plus to send when user types a message', async () => {
    const user = userEvent.setup()
    render(<ChatPage />)

    expect(screen.getByRole('button', { name: '添加附件' })).toBeInTheDocument()
    await user.type(screen.getByLabelText('输入消息'), '你好')

    expect(screen.getByRole('button', { name: '发送消息' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '添加附件' })).not.toBeInTheDocument()
  })

  it('shows send action when there are pending attachments even without draft text', async () => {
    render(<ChatPage />)

    const input = screen.getByLabelText('上传课表')
    await userEvent.upload(input, createFile('math-1.png', 'image/png'))

    expect(screen.getByRole('button', { name: '发送消息' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '添加附件' })).not.toBeInTheDocument()
  })

  it('keeps an add-more control visible after selecting one attachment', async () => {
    render(<ChatPage />)

    const input = screen.getByLabelText('上传课表')
    await userEvent.upload(input, createFile('math-1.png', 'image/png'))

    expect(screen.getByRole('button', { name: '继续添加附件' })).toBeInTheDocument()
  })

  it('keeps the add-more attachment trigger wired to the same native file input element', async () => {
    const { container } = render(<ChatPage />)

    const input = container.querySelector('.chat-input__file-input') as HTMLInputElement
    await userEvent.upload(input, createFile('math-1.png', 'image/png'))

    const trigger = container.querySelector('.attachment-tray__add-button')
    const fileInput = container.querySelector('.chat-input__file-input')

    expect(trigger).toBeTruthy()
    expect(fileInput).toBeTruthy()
    expect(trigger?.tagName).toBe('LABEL')
    expect(trigger).toHaveAttribute('for', fileInput?.getAttribute('id'))
  })

  it.skip('uses a native file input trigger for the add-more attachment control', async () => {
    render(<ChatPage />)

    const input = screen.getByLabelText('涓婁紶璇捐〃')
    await userEvent.upload(input, createFile('math-1.png', 'image/png'))

    const trigger = screen.getByRole('button', { name: '缁х画娣诲姞闄勪欢' })
    expect(trigger.tagName).toBe('LABEL')
    expect(trigger).toHaveAttribute('for', input.getAttribute('id'))
  })

  it('blocks mixed spreadsheet and image attachments', async () => {
    render(<ChatPage />)

    const input = screen.getByLabelText('上传课表')
    await userEvent.upload(input, createFile('math.png', 'image/png'))
    await userEvent.upload(input, createFile('schedule.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'))

    expect(await screen.findByRole('alert')).toHaveTextContent('不能同时添加图片和表格')
    expect(screen.getByRole('region', { name: '待发送附件' })).toHaveTextContent('待发送附件 1')
    expect(screen.queryByText('schedule.xlsx')).not.toBeInTheDocument()
  })

  it('blocks more than three images', async () => {
    render(<ChatPage />)

    const input = screen.getByLabelText('上传课表')
    await userEvent.upload(input, [
      createFile('1.png', 'image/png'),
      createFile('2.png', 'image/png'),
      createFile('3.png', 'image/png'),
      createFile('4.png', 'image/png'),
    ])

    expect(await screen.findByRole('alert')).toHaveTextContent('最多只能添加 3 张图片')
    expect(screen.queryByRole('region', { name: '待发送附件' })).not.toBeInTheDocument()
    expect(screen.queryByText('4.png')).not.toBeInTheDocument()
  })

  it('blocks unsupported attachment types before they enter the tray', async () => {
    render(<ChatPage />)

    const input = screen.getByLabelText('上传课表')
    await userEvent.upload(input, createFile('animation.gif', 'image/gif'))

    expect(await screen.findByRole('alert')).toHaveTextContent('暂不支持该附件类型')
    expect(screen.queryByRole('region', { name: '待发送附件' })).not.toBeInTheDocument()
    expect(screen.queryByText('animation.gif')).not.toBeInTheDocument()
    expect(api.uploadSchedule).not.toHaveBeenCalled()
  })

  it('allows removing a pending attachment from the tray', async () => {
    render(<ChatPage />)

    const input = screen.getByLabelText('上传课表')
    await userEvent.upload(input, [
      createFile('1.png', 'image/png'),
      createFile('2.png', 'image/png'),
    ])

    await userEvent.click(screen.getByRole('button', { name: '移除 1.png' }))

    expect(screen.getByRole('region', { name: '待发送附件' })).toHaveTextContent('待发送附件 1')
    expect(screen.queryByText('1.png')).not.toBeInTheDocument()
    expect(screen.getByText('2.png')).toBeInTheDocument()
  })

  it('uploads pending images only when sending and emits the stable parse prompt', async () => {
    const user = userEvent.setup()
    const uploadSchedule = vi.spyOn(api, 'uploadSchedule').mockResolvedValue({
      file_id: 'schedule-file-1',
      kind: 'image',
      count: 2,
      source_file_count: 2,
      courses: [],
    })
    const getScheduleUploadStatus = vi.spyOn(api, 'getScheduleUploadStatus').mockResolvedValue(
      createUploadStatus({
        file_id: 'schedule-file-1',
        source_file_count: 2,
      }),
    )

    render(<ChatPage />)

    const input = screen.getByLabelText('上传课表')
    await user.upload(input, [
      createFile('math-1.png', 'image/png'),
      createFile('math-2.jpg', 'image/jpeg'),
    ])

    expect(uploadSchedule).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: '发送消息' }))

    expect(uploadSchedule).toHaveBeenCalledTimes(1)
    expect(uploadSchedule).toHaveBeenCalledWith([
      expect.objectContaining({ name: 'math-1.png' }),
      expect.objectContaining({ name: 'math-2.jpg' }),
    ])
    expect(getScheduleUploadStatus).toHaveBeenCalledWith('schedule-file-1')
    expect(MockWebSocket.instances[0]?.send).toHaveBeenLastCalledWith(
      JSON.stringify({
        message: '我上传了课表图片 file_id=schedule-file-1，请解析并展示确认卡片。',
      }),
    )
    expect(await screen.findByText('已发送 2 张课表图片')).toBeInTheDocument()
    expect(screen.getByText('课表图片')).toBeInTheDocument()
    expect(screen.getByText('共 2 张，等待助手解析')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: '待发送附件' })).not.toBeInTheDocument()
  })

  it('keeps polling image parse status until parsed before sending websocket parse prompt', async () => {
    const user = userEvent.setup()
    vi.spyOn(api, 'uploadSchedule').mockResolvedValue({
      file_id: 'schedule-file-poll',
      kind: 'image',
      count: 0,
      source_file_count: 2,
      courses: [],
    })
    const getScheduleUploadStatus = vi
      .spyOn(api, 'getScheduleUploadStatus')
      .mockResolvedValueOnce(
        createUploadStatus({
          file_id: 'schedule-file-poll',
          status: 'PARSING',
          progress: 52,
          source_file_count: 2,
        }),
      )
      .mockResolvedValueOnce(
        createUploadStatus({
          file_id: 'schedule-file-poll',
          status: 'PARSED',
          progress: 100,
          source_file_count: 2,
        }),
      )

    render(<ChatPage />)

    const input = screen.getByLabelText('上传课表')
    await user.upload(input, [
      createFile('math-1.png', 'image/png'),
      createFile('math-2.jpg', 'image/jpeg'),
    ])
    await user.click(screen.getByRole('button', { name: '发送消息' }))

    await waitFor(() => {
      expect(getScheduleUploadStatus).toHaveBeenCalledTimes(2)
    }, { timeout: 4000 })
    expect(MockWebSocket.instances[0]?.send).toHaveBeenLastCalledWith(
      JSON.stringify({
        message: '我上传了课表图片 file_id=schedule-file-poll，请解析并展示确认卡片。',
      }),
    )
  })

  it('restores pending attachments when image parse status becomes failed', async () => {
    const user = userEvent.setup()
    vi.spyOn(api, 'uploadSchedule').mockResolvedValue({
      file_id: 'schedule-file-failed',
      kind: 'image',
      count: 0,
      source_file_count: 1,
      courses: [],
    })
    vi.spyOn(api, 'getScheduleUploadStatus').mockResolvedValue(
      createUploadStatus({
        file_id: 'schedule-file-failed',
        status: 'FAILED',
        progress: 100,
        error: 'vision parser down',
      }),
    )

    render(<ChatPage />)

    const input = screen.getByLabelText('上传课表')
    await user.upload(input, createFile('math-1.png', 'image/png'))
    await user.click(screen.getByRole('button', { name: '发送消息' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('vision parser down')
    expect(screen.getByRole('region', { name: '待发送附件' })).toHaveTextContent('待发送附件 1')
    expect(screen.getByText('math-1.png')).toBeInTheDocument()
    expect(MockWebSocket.instances[0]?.send).not.toHaveBeenCalledWith(
      JSON.stringify({
        message: '我上传了课表图片 file_id=schedule-file-failed，请解析并展示确认卡片。',
      }),
    )
  })

  it('prevents duplicate attachment sends while upload is still in progress', async () => {
    const user = userEvent.setup()
    let resolveUpload:
      | ((value: { file_id: string; kind: 'image'; count: number; source_file_count: number; courses: [] }) => void)
      | null = null
    const uploadSchedule = vi.spyOn(api, 'uploadSchedule').mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveUpload = resolve as typeof resolveUpload
        }),
    )
    const getScheduleUploadStatus = vi.spyOn(api, 'getScheduleUploadStatus').mockResolvedValue(
      createUploadStatus({
        file_id: 'schedule-file-dup',
      }),
    )

    render(<ChatPage />)

    const input = screen.getByLabelText('上传课表')
    await user.upload(input, createFile('math-1.png', 'image/png'))

    const sendButton = screen.getByRole('button', { name: '发送消息' })
    fireEvent.click(sendButton)
    fireEvent.click(sendButton)

    expect(uploadSchedule).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('region', { name: 'image-parse-bridge' })).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '18')
    expect(screen.queryByText('正在发送，请稍候…')).not.toBeInTheDocument()
    expect(screen.queryByText('已上传，正在调用视觉模型识别课表。')).not.toBeInTheDocument()
    expect(screen.queryByText('视觉模型处理中')).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: '待发送附件' })).not.toBeInTheDocument()

    await act(async () => {
      if (!resolveUpload) {
        throw new Error('upload resolver not set')
      }
      resolveUpload({
        file_id: 'schedule-file-dup',
        kind: 'image',
        count: 1,
        source_file_count: 1,
        courses: [],
      })
      await Promise.resolve()
    })

    await waitFor(() => {
      expect(screen.queryByRole('region', { name: 'image-parse-bridge' })).not.toBeInTheDocument()
    })
    expect(getScheduleUploadStatus).toHaveBeenCalledWith('schedule-file-dup')
  })

  it('keeps pending attachments when upload fails on send', async () => {
    const user = userEvent.setup()
    vi.spyOn(api, 'uploadSchedule').mockRejectedValue(new Error('upload failed'))

    render(<ChatPage />)

    const input = screen.getByLabelText('上传课表')
    await user.upload(input, createFile('math-1.png', 'image/png'))

    await user.click(screen.getByRole('button', { name: '发送消息' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('upload failed')
    expect(screen.getByRole('region', { name: '待发送附件' })).toHaveTextContent('待发送附件 1')
    expect(screen.getByText('math-1.png')).toBeInTheDocument()
    expect(MockWebSocket.instances[0]?.send).not.toHaveBeenLastCalledWith(
      JSON.stringify({
        message: '我上传了课表图片 file_id=schedule-file-1，请解析并展示确认卡片。',
      }),
    )
  })

  it('uploads pending spreadsheet files only when sending and appends a friendly message', async () => {
    const user = userEvent.setup()
    const uploadSchedule = vi.spyOn(api, 'uploadSchedule').mockResolvedValue({
      file_id: 'schedule-file-2',
      kind: 'spreadsheet',
      count: 1,
      source_file_count: 1,
      courses: [],
    })

    render(<ChatPage />)

    const input = screen.getByLabelText('上传课表')
    await user.upload(input, createFile('schedule.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'))

    await user.click(screen.getByRole('button', { name: '发送消息' }))

    expect(uploadSchedule).toHaveBeenCalledTimes(1)
    expect(uploadSchedule).toHaveBeenCalledWith([expect.objectContaining({ name: 'schedule.xlsx' })])
    expect(MockWebSocket.instances[0]?.send).toHaveBeenLastCalledWith(
      JSON.stringify({
        message: '我上传了课表文件 file_id=schedule-file-2，请解析并展示确认卡片。',
      }),
    )
    expect(await screen.findByText('已发送 1 个课表文件')).toBeInTheDocument()
    expect(screen.getByText('课表文件')).toBeInTheDocument()
    expect(screen.getByText('共 1 个，等待助手解析')).toBeInTheDocument()
    expect(screen.queryByText('schedule.xlsx')).not.toBeInTheDocument()
  })

  it('keeps pending attachments when the websocket cannot send the parse prompt after upload', async () => {
    const user = userEvent.setup()
    vi.spyOn(api, 'uploadSchedule').mockResolvedValue({
      file_id: 'schedule-file-3',
      kind: 'image',
      count: 1,
      source_file_count: 1,
      courses: [],
    })
    const getScheduleUploadStatus = vi.spyOn(api, 'getScheduleUploadStatus').mockResolvedValue(
      createUploadStatus({
        file_id: 'schedule-file-3',
      }),
    )

    await renderReadyChatPage()

    const socket = MockWebSocket.instances[0]
    expect(socket).toBeDefined()
    if (!socket) {
      return
    }
    socket.send.mockClear()
    socket.readyState = 0

    const input = screen.getByLabelText('上传课表')
    await user.upload(input, createFile('math-1.png', 'image/png'))
    await user.click(screen.getByRole('button', { name: '发送消息' }))

    expect(await screen.findByRole('alert', undefined, { timeout: 6200 })).toHaveTextContent('聊天连接不可用，请稍后重试')
    expect(screen.getByRole('region', { name: '待发送附件' })).toHaveTextContent('待发送附件 1')
    expect(screen.getByText('math-1.png')).toBeInTheDocument()
    expect(screen.queryByText('已发送 1 张课表图片')).not.toBeInTheDocument()
    expect(getScheduleUploadStatus).toHaveBeenCalledWith('schedule-file-3')
    expect(socket.send).not.toHaveBeenCalledWith(
      JSON.stringify({
        message: '我上传了课表图片 file_id=schedule-file-3，请解析并展示确认卡片。',
      }),
    )
  }, 8000)

  it('does not append a text message when the websocket cannot send it', async () => {
    const user = userEvent.setup()

    await renderReadyChatPage()

    const socket = MockWebSocket.instances[0]
    expect(socket).toBeDefined()
    if (!socket) {
      return
    }
    socket.send.mockClear()
    socket.readyState = 0

    await user.type(screen.getByLabelText('输入消息'), '帮我安排今天的复习')
    await user.click(screen.getByRole('button', { name: '发送消息' }))

    expect(await screen.findByRole('alert', undefined, { timeout: 6200 })).toHaveTextContent('聊天连接不可用，请稍后重试')
    expect(screen.getByLabelText('输入消息')).toHaveValue('帮我安排今天的复习')
    expect(screen.queryByText('帮我安排今天的复习')).not.toBeInTheDocument()
    expect(socket.send).not.toHaveBeenCalledWith(
      JSON.stringify({
        message: '帮我安排今天的复习',
      }),
    )
  }, 8000)

  it('waits briefly for a reconnecting websocket before sending text', async () => {
    vi.useFakeTimers()

    try {
      render(<ChatPage />)

      const socket = MockWebSocket.instances[0]
      expect(socket).toBeDefined()
      if (!socket) {
        return
      }
      await act(async () => {
        await Promise.resolve()
      })
      socket.send.mockClear()
      socket.readyState = 0

      fireEvent.change(screen.getByLabelText('输入消息'), {
        target: { value: '帮我安排今天的复习' },
      })
      fireEvent.click(screen.getByRole('button', { name: '发送消息' }))

      await act(async () => {
        await vi.advanceTimersByTimeAsync(700)
      })
      expect(socket.send).not.toHaveBeenCalled()

      socket.readyState = MockWebSocket.OPEN
      socket.onmessage?.(
        new MessageEvent('message', {
          data: JSON.stringify({ type: 'connected', session_id: 'mock-reconnected-session' }),
        }),
      )
      await act(async () => {
        await vi.advanceTimersByTimeAsync(100)
        await Promise.resolve()
      })

      expect(socket.send).toHaveBeenLastCalledWith(
        JSON.stringify({
          message: '帮我安排今天的复习',
        }),
      )
      expect(screen.getByText('帮我安排今天的复习')).toBeInTheDocument()
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it('routes plain review follow-up answers through the main input as ask_user answers', async () => {
    const user = userEvent.setup()
    await renderReadyChatPage()

    act(() => {
      useChatStore.getState().applyServerEvent({
        type: 'ask_user',
        question: '请补充第1-2节和第3-4节时间',
        ask_type: 'review',
      })
    })

    expect(screen.getByText('请补充第1-2节和第3-4节时间')).toBeInTheDocument()
    expect(screen.queryByLabelText('回复内容')).not.toBeInTheDocument()

    await user.type(screen.getByLabelText('输入消息'), '1-2节 08:30-10:05，3-4节 10:20-11:55')
    await user.click(screen.getByRole('button', { name: '发送消息' }))

    expect(MockWebSocket.instances[0]?.send).toHaveBeenLastCalledWith(
      JSON.stringify({
        answer: '1-2节 08:30-10:05，3-4节 10:20-11:55',
      }),
    )
    expect(screen.getByText('1-2节 08:30-10:05，3-4节 10:20-11:55')).toBeInTheDocument()
  })

  it('routes typed text to answer channel when a confirm card is pending', async () => {
    const user = userEvent.setup()
    await renderReadyChatPage()

    act(() => {
      useChatStore.getState().applyServerEvent({
        type: 'ask_user',
        question: '请确认是否导入',
        ask_type: 'confirm',
        options: ['确认', '取消'],
        data: { count: 21 },
      })
    })

    await user.type(screen.getByLabelText('输入消息'), '没啥问题')
    await user.click(screen.getByRole('button', { name: '发送消息' }))

    expect(MockWebSocket.instances[0]?.send).toHaveBeenLastCalledWith(
      JSON.stringify({
        answer: '没啥问题',
      }),
    )
    expect(screen.getByText('没啥问题')).toBeInTheDocument()
  })

  it('shows selected option text immediately after selecting a confirm option', async () => {
    const user = userEvent.setup()
    await renderReadyChatPage()

    act(() => {
      useChatStore.getState().applyServerEvent({
        type: 'ask_user',
        question: 'Please confirm import',
        ask_type: 'confirm',
        options: ['Confirm', 'Cancel'],
        data: { count: 13 },
      })
    })

    await user.click(screen.getByRole('button', { name: 'Confirm' }))

    expect(screen.getByText('已选择：Confirm')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('确认已收到')
    expect(screen.getByText('执行确认操作')).toBeInTheDocument()
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  })

  it('shows a plan write stage after confirming a task review card', async () => {
    const user = userEvent.setup()
    await renderReadyChatPage()

    act(() => {
      useChatStore.getState().applyServerEvent({
        type: 'ask_user',
        question: '确认后写入这些任务',
        ask_type: 'review',
        options: ['确认', '取消'],
        data: {
          tasks: [{ time: '08:00-09:00', content: '背单词' }],
        },
      })
    })

    await user.click(screen.getByRole('button', { name: '确认' }))

    expect(screen.getByRole('status')).toHaveTextContent('确认已收到')
    expect(screen.getByText('写入日程任务')).toBeInTheDocument()
    expect(screen.getByText('整理写入结果')).toBeInTheDocument()
  })

  it('sends edited task review payload while displaying only the selected confirm label', async () => {
    const user = userEvent.setup()
    await renderReadyChatPage()

    act(() => {
      useChatStore.getState().applyServerEvent({
        type: 'ask_user',
        question: '确认后写入这些任务',
        ask_type: 'review',
        options: ['确认', '取消'],
        data: {
          tasks: [
            {
              title: '背单词',
              scheduled_date: '2026-06-08',
              start_time: '08:00',
              end_time: '09:00',
              description: 'Unit 1',
            },
            {
              title: '阅读训练',
              scheduled_date: '2026-06-08',
              start_time: '09:30',
              end_time: '10:30',
              description: '两篇阅读',
            },
          ],
        },
      })
    })

    const titleInputs = screen.getAllByLabelText('标题')
    await user.clear(titleInputs[0]!)
    await user.type(titleInputs[0]!, '背单词精修')
    await user.click(screen.getAllByRole('button', { name: '删除这条' })[1]!)
    await user.click(screen.getByRole('button', { name: '确认' }))

    const rawPayload = MockWebSocket.instances[0]?.send.mock.calls.at(-1)?.[0]
    expect(typeof rawPayload).toBe('string')
    const payload = JSON.parse(rawPayload as string) as { answer: string }
    expect(payload.answer).toContain('review_override=')
    const override = JSON.parse(payload.answer.split('review_override=')[1])
    expect(override.tasks).toHaveLength(1)
    expect(override.tasks[0]).toMatchObject({
      title: '背单词精修',
      scheduled_date: '2026-06-08',
      start_time: '08:00',
      end_time: '09:00',
      description: 'Unit 1',
    })
    expect(screen.getByText('已选择：确认')).toBeInTheDocument()
    expect(screen.queryByText(/review_override/)).not.toBeInTheDocument()
  })

  it('renders a dynamic progress card with ratio and current step', async () => {
    await renderReadyChatPage()

    act(() => {
      useChatStore.getState().applyServerEvent({
        type: 'tool_call',
        name: 'parse_schedule',
      })
    })

    expect(screen.getByRole('progressbar')).toBeInTheDocument()
    expect(screen.getByText('解析课表')).toBeInTheDocument()
    expect(screen.getByText('理解需求')).toBeInTheDocument()
    expect(screen.getAllByText('解析课表结构').length).toBeGreaterThan(0)

    act(() => {
      useChatStore.getState().applyServerEvent({
        type: 'tool_result',
        name: 'parse_schedule',
      })
    })

    expect(screen.getByText('1/1')).toBeInTheDocument()
    expect(screen.getByText('课表结构已解析')).toBeInTheDocument()
    expect(screen.getAllByText('整理最终回复').length).toBeGreaterThan(0)
  })

  it('renders common assistant markdown as readable rich text', async () => {
    await renderReadyChatPage()

    act(() => {
      useChatStore.getState().applyServerEvent({
        type: 'text',
        message_id: 'markdown-message',
        content: '### 今晚计划总览\n- **19:00-20:30** 英语六级复习\n- **20:45-22:15** 高等数学复习',
      })
    })

    expect(screen.getByText('今晚计划总览')).toBeInTheDocument()
    expect(screen.getByText('19:00-20:30')).toBeInTheDocument()
    expect(screen.queryByText(/###/)).not.toBeInTheDocument()
    expect(screen.queryByText(/\*\*/)).not.toBeInTheDocument()
  })

  it('renders RAG answer grounding from server metadata', async () => {
    const { container } = await renderReadyChatPage()

    act(() => {
      useChatStore.getState().applyServerEvent({
        type: 'text',
        message_id: 'rag-message',
        content: '我记得你更适合晚上复习高数，可以优先安排 19:00 后的整块时间。',
        answer_kind: 'rag',
        grounding: {
          kind: 'rag',
          label: '基于长期记忆',
          items: [{ label: '偏好', text: '高数复习优先安排在晚上' }],
        },
      })
    })

    expect(container.querySelector('.message--rag')).toBeTruthy()
    expect(screen.getByLabelText('基于长期记忆')).toHaveTextContent('偏好')
    expect(screen.getByLabelText('基于长期记忆')).toHaveTextContent('高数复习优先安排在晚上')
    expect(screen.getByText(/可以优先安排 19:00 后/)).toBeInTheDocument()
  })

  it('renders task write success replies as result cards', () => {
    const { container } = render(<ChatPage />)

    act(() => {
      useChatStore.getState().applyServerEvent({
        type: 'text',
        message_id: 'task-result-message',
        content: '已把 2 条复习任务写入日程，其中 1 条因原时间冲突已自动重排。',
      })
    })

    expect(container.querySelector('.assistant-result--success')).toBeTruthy()
    expect(screen.getByLabelText('已完成')).toHaveTextContent('已把 2 条复习任务写入日程')
    expect(screen.getByText('2 条记录')).toBeInTheDocument()
    expect(screen.getByText('含自动重排')).toBeInTheDocument()
  })

  it('renders structured result events without keyword classification', () => {
    const { container } = render(<ChatPage />)

    act(() => {
      useChatStore.getState().applyServerEvent({
        type: 'result',
        message_id: 'structured-result',
        content: 'Plan write completed',
        tone: 'success',
        eyebrow: '已完成',
        title: '已写入计划',
        body: '2 条任务已经落到日程。',
        chips: ['2 条记录'],
      })
      useChatStore.getState().applyServerEvent({
        type: 'text',
        message_id: 'structured-result',
        content: 'Plan write completed',
      })
    })

    expect(container.querySelector('.assistant-result--success')).toBeTruthy()
    expect(screen.getByLabelText('已完成')).toHaveTextContent('已写入计划')
    expect(screen.getByText('2 条任务已经落到日程。')).toBeInTheDocument()
    expect(screen.getByText('2 条记录')).toBeInTheDocument()
  })

  it('renders streamed assistant deltas as one growing message bubble', async () => {
    await renderReadyChatPage()

    act(() => {
      useChatStore.getState().applyServerEvent({
        type: 'text_delta',
        message_id: 'stream-msg-1',
        delta: 'Hello ',
      })
      useChatStore.getState().applyServerEvent({
        type: 'text_delta',
        message_id: 'stream-msg-1',
        delta: 'world',
      })
      useChatStore.getState().applyServerEvent({
        type: 'text',
        message_id: 'stream-msg-1',
        content: 'Hello world!',
      })
    })

    expect(screen.getByText('Hello world!')).toBeInTheDocument()
    expect(screen.queryAllByText('Hello world!')).toHaveLength(1)
  })

  it('replaces the progress card with ask card when ask_user arrives', () => {
    const { container } = render(<ChatPage />)

    act(() => {
      useChatStore.getState().applyServerEvent({
        type: 'tool_call',
        name: 'parse_schedule',
      })
    })
    expect(screen.getByRole('progressbar')).toBeInTheDocument()

    act(() => {
      useChatStore.getState().applyServerEvent({
        type: 'ask_user',
        question: '请确认解析结果',
        ask_type: 'confirm',
        options: ['确认', '取消'],
        data: { count: 21 },
      })
    })

    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
    expect(container.querySelector('.ask-card')).toBeTruthy()
  })

  it('keeps progress card after the welcome message in timeline order', () => {
    const { container } = render(<ChatPage />)

    act(() => {
      useChatStore.getState().applyServerEvent({
        type: 'tool_call',
        name: 'parse_schedule',
      })
    })

    const progressCard = container.querySelector('.progress-card')
    const welcomeMessage = screen.getByText('你好！我是你的学习规划助手，有什么可以帮你的？')

    expect(progressCard).toBeTruthy()
    expectNodeBefore(welcomeMessage, progressCard as HTMLElement)
  })

  it('keeps ask card after the welcome message in timeline order', () => {
    const { container } = render(<ChatPage />)

    act(() => {
      useChatStore.getState().applyServerEvent({
        type: 'ask_user',
        question: '请确认解析结果',
        ask_type: 'confirm',
        options: ['确认', '取消'],
        data: { count: 21 },
      })
    })

    const askCard = container.querySelector('.ask-card')
    const welcomeMessage = screen.getByText('你好！我是你的学习规划助手，有什么可以帮你的？')

    expect(askCard).toBeTruthy()
    expectNodeBefore(welcomeMessage, askCard as HTMLElement)
  })

  it('renders schedule review ask data as readable course cards instead of raw JSON', () => {
    render(<ChatPage />)

    act(() => {
      useChatStore.getState().applyServerEvent({
        type: 'ask_user',
        question: '以下是从文件中解析出的课表，请确认信息。',
        ask_type: 'review',
        options: ['确认', '取消'],
        data: {
          kind: 'spreadsheet',
          count: 2,
          courses: [
            {
              name: '高等数学',
              weekday: 1,
              start_time: '08:00',
              end_time: '09:40',
              location: '教学楼A301',
              teacher: '张老师',
              week_start: 1,
              week_end: 16,
            },
            '周二：第3-4节 10:00-11:40',
          ],
        },
      })
    })

    expect(screen.getByLabelText('识别课程列表')).toBeInTheDocument()
    expect(screen.getByText('高等数学')).toBeInTheDocument()
    expect(screen.getByText('周一 · 08:00-09:40')).toBeInTheDocument()
    expect(screen.getByText('教学楼A301 · 张老师 · 第1-16周')).toBeInTheDocument()
    expect(screen.getByText('周二：第3-4节 10:00-11:40')).toBeInTheDocument()
    expect(screen.queryByText('"courses"')).not.toBeInTheDocument()
  })

  it('renders odd or even week labels from week_text in review cards', () => {
    render(<ChatPage />)

    act(() => {
      useChatStore.getState().applyServerEvent({
        type: 'ask_user',
        question: '请确认识别结果',
        ask_type: 'review',
        options: ['确认', '取消'],
        data: {
          kind: 'image',
          count: 1,
          courses: [
            {
              name: '自然语言处理',
              weekday: 3,
              start_time: '08:30',
              end_time: '10:05',
              location: 'A301',
              week_start: 1,
              week_end: 18,
              week_pattern: 'odd',
              week_text: '第1-18周(单周)',
            },
          ],
        },
      })
    })

    expect(screen.getByText('A301 · 第1-18周(单周)')).toBeInTheDocument()
  })

  it('renders review cards when ask_user data is a stringified JSON payload', () => {
    const { container } = render(<ChatPage />)

    act(() => {
      useChatStore.getState().applyServerEvent({
        type: 'ask_user',
        question: '请确认识别结果',
        ask_type: 'review',
        options: ['确认', '取消'],
        data: JSON.stringify({
          count: 1,
          courses: [
            {
              name: '自然语言处理',
              weekday: 3,
              start_time: '08:30',
              end_time: '10:05',
              location: 'A301',
              week_text: '第1-18周(单周)',
            },
          ],
        }),
      })
    })

    expect(screen.getByText('自然语言处理')).toBeInTheDocument()
    expect(container.querySelector('.ask-card__schedule-list')).toBeTruthy()
    expect(screen.queryByText('"courses"')).not.toBeInTheDocument()
  })

  it('renders row-style schedule data with Chinese headers and keeps the course title', () => {
    render(<ChatPage />)

    act(() => {
      useChatStore.getState().applyServerEvent({
        type: 'ask_user',
        question: '以下是从文件中解析出的课表，请确认内容是否正确。',
        ask_type: 'review',
        options: ['确认', '取消'],
        data: {
          courses: [
            {
              周一: '第3-4节 10:20-11:55',
              周一晚: '第7-8节 16:00-17:35',
              周三: '第3-4节 10:20-11:55',
              周次: '第1周（全部）',
              地点: '会展-315(校企工坊)',
              序号: 1,
              教师: '张志英',
              课程: '专业综合实践II',
            },
          ],
          summary: '共识别 21 条记录',
        },
      })
    })

    expect(screen.getByText('专业综合实践II')).toBeInTheDocument()
    expect(screen.getByText(/会展-315/)).toBeInTheDocument()
    expect(screen.queryByText('未命名课程')).not.toBeInTheDocument()
  })

  it('renders serialized Chinese course list strings as readable schedule cards', () => {
    render(<ChatPage />)

    act(() => {
      useChatStore.getState().applyServerEvent({
        type: 'ask_user',
        question: '以下是从文件中识别出的课表，请确认是否导入？',
        ask_type: 'review',
        options: ['确认', '取消'],
        data: {
          共识别课程条目: 2,
          课程列表:
            '周次:第1周；地点:会展-315(校企工坊)；教师:张志英；时间:10:20-11:55；星期:周二；课程:专业综合实践II，周次:第2-9周；地点:励志楼C202；教师:宋元跃；时间:18:45-20:25；星期:周二；课程:大学生就业指导',
        },
      })
    })

    expect(screen.getByLabelText('识别课程列表')).toBeInTheDocument()
    expect(screen.getByText('专业综合实践II')).toBeInTheDocument()
    expect(screen.getByText('大学生就业指导')).toBeInTheDocument()
    expect(screen.getByText('周二 · 10:20-11:55')).toBeInTheDocument()
    expect(screen.getByText('会展-315(校企工坊) · 张志英 · 第1周')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '确认' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '取消' })).toBeInTheDocument()
  })

  it('hides raw OCR table text when a structured schedule review card is available', () => {
    const { container } = render(<ChatPage />)

    act(() => {
      useChatStore.getState().applyServerEvent({
        type: 'ask_user',
        question:
          'OCR 识别完成，发现的问题：1. 课程名可能有误。完整课程列表如下：|#|课程名|星期|时间|1|自然语言处理|周三|08:30-10:05|请确认后导入。',
        ask_type: 'review',
        options: ['纭', '鍙栨秷'],
        data: {
          count: 1,
          courses: [
            {
              name: '自然语言处理',
              weekday: 3,
              start_time: '08:30',
              end_time: '10:05',
              location: 'A301',
              week_text: '第1-18周',
            },
          ],
        },
      })
    })

    expect(container.querySelector('.ask-card__schedule-list')).toBeTruthy()
    expect(screen.getByText(/OCR 识别完成/)).toBeInTheDocument()
    expect(screen.getByText(/发现的问题：1\. 课程名可能有误/)).toBeInTheDocument()
    expect(screen.queryByText(/\|#\|课程名\|星期\|时间/)).not.toBeInTheDocument()
  })

  it('renders non-schedule review data as key-value rows instead of a JSON blob', () => {
    render(<ChatPage />)

    act(() => {
      useChatStore.getState().applyServerEvent({
        type: 'ask_user',
        question: '确认复习计划信息',
        ask_type: 'review',
        options: ['确认', '取消'],
        data: {
          考试科目: '高等数学',
          考试日期: '2026-04-25',
          复习区间: '2026-04-13 至 2026-04-24',
        },
      })
    })

    expect(screen.getByLabelText('确认详情')).toBeInTheDocument()
    expect(screen.getByText('考试科目')).toBeInTheDocument()
    expect(screen.getByText('高等数学')).toBeInTheDocument()
    expect(screen.queryByText('"考试科目"')).not.toBeInTheDocument()
  })

  it('renders plan arrays as task cards instead of key-value text', () => {
    const { container } = render(<ChatPage />)

    act(() => {
      useChatStore.getState().applyServerEvent({
        type: 'ask_user',
        question: '你觉得这个时间安排怎么样？确认后我帮你创建任务并设置提醒。',
        ask_type: 'review',
        options: ['确认', '取消'],
        data: {
          plan: [
            { time: '19:00-20:30', content: '英语六级复习', duration: '1.5h' },
            { time: '20:45-22:15', content: '高等数学复习', duration: '1.5h' },
          ],
        },
      })
    })

    expect(container.querySelector('.ask-card__plan-list')).toBeTruthy()
    expect(screen.getByText('计划任务 2')).toBeInTheDocument()
    expect(screen.getByDisplayValue('英语六级复习')).toBeInTheDocument()
    expect(screen.getByDisplayValue('高等数学复习')).toBeInTheDocument()
    expect(screen.getByText('19:00-20:30')).toBeInTheDocument()
    expect(screen.queryByText('plan')).not.toBeInTheDocument()
  })

  it('keeps long task plans compact with an expandable remainder', () => {
    render(<ChatPage />)

    act(() => {
      useChatStore.getState().applyServerEvent({
        type: 'ask_user',
        question: '确认后写入这些任务',
        ask_type: 'review',
        options: ['确认', '取消'],
        data: {
          tasks: [
            { time: '08:00-09:00', content: '任务一' },
            { time: '09:15-10:15', content: '任务二' },
            { time: '10:30-11:30', content: '任务三' },
            { time: '14:00-15:00', content: '任务四' },
            { time: '15:15-16:15', content: '任务五' },
          ],
        },
      })
    })

    expect(screen.getByText('计划任务 5')).toBeInTheDocument()
    expect(screen.getByText('展开剩余 2 条任务')).toBeInTheDocument()
  })

  it('keeps review ask card anchored in the timeline so new user messages render below it', () => {
    const { container } = render(<ChatPage />)

    act(() => {
      useChatStore.getState().applyServerEvent({
        type: 'ask_user',
        question: '请确认解析结果',
        ask_type: 'review',
        options: ['确认', '取消'],
        data: {
          count: 1,
          courses: [{ name: '高等数学', weekday: 1, start_time: '08:00', end_time: '09:40' }],
        },
      })
      useChatStore.getState().appendUserMessage('1')
    })

    const askCard = container.querySelector('.ask-card')
    const newestUserMessage = screen.getByText('1')

    expect(askCard).toBeTruthy()
    expectNodeBefore(askCard as HTMLElement, newestUserMessage)
  })

  it('keeps review ask card anchored so later assistant replies render below it', () => {
    const { container } = render(<ChatPage />)

    act(() => {
      useChatStore.getState().applyServerEvent({
        type: 'ask_user',
        question: '请确认解析结果',
        ask_type: 'review',
        options: ['确认', '取消'],
        data: {
          count: 1,
          courses: [{ name: '高等数学', weekday: 1, start_time: '08:00', end_time: '09:40' }],
        },
      })
      useChatStore.getState().applyServerEvent({
        type: 'text',
        content: '这是后续回复',
      })
    })

    const askCard = container.querySelector('.ask-card')
    const followupReply = screen.getByText('这是后续回复').closest('.message')

    expect(askCard).toBeTruthy()
    expect(followupReply).toBeTruthy()
    expectNodeBefore(askCard as HTMLElement, followupReply as HTMLElement)
  })

  it('keeps progress card anchored in the timeline so new user messages render below it', () => {
    const { container } = render(<ChatPage />)

    act(() => {
      useChatStore.getState().applyServerEvent({
        type: 'tool_call',
        name: 'parse_schedule',
      })
      useChatStore.getState().appendUserMessage('继续')
    })

    const progressCard = container.querySelector('.progress-card')
    const newestUserMessage = screen.getByText('继续')

    expect(progressCard).toBeTruthy()
    expectNodeBefore(progressCard as HTMLElement, newestUserMessage)
  })

  it('shows a timeout error when the server never responds after a text send', async () => {
    vi.useFakeTimers()

    try {
      render(<ChatPage />)

      fireEvent.change(screen.getByLabelText('输入消息'), {
        target: { value: '帮我安排今天的复习' },
      })
      await act(async () => {
        await Promise.resolve()
      })
      fireEvent.click(screen.getByRole('button', { name: '发送消息' }))

      await act(async () => {
        await Promise.resolve()
        await Promise.resolve()
      })

      expect(MockWebSocket.instances[0]?.send).toHaveBeenLastCalledWith(
        JSON.stringify({
          message: '帮我安排今天的复习',
        }),
      )
      expect(screen.getByText('帮我安排今天的复习')).toBeInTheDocument()

      await act(async () => {
        await vi.advanceTimersByTimeAsync(30000)
      })

      expect(screen.getByRole('alert')).toHaveTextContent('助手暂时没有响应，请重试')
    } finally {
      vi.useRealTimers()
    }
  })
})
