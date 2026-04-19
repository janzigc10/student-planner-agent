import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '../api/client'
import { createInitialChatState, useChatStore } from '../stores/chatStore'
import { ChatPage } from './ChatPage'

function createFile(name: string, type: string) {
  return new File(['content'], name, { type })
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
    queueMicrotask(() => this.onopen?.())
  }
}

function readOrder(node: Node) {
  const raw = (node as HTMLElement).style.order
  return raw ? Number(raw) : 0
}

function expectNodeBefore(first: Node, second: Node) {
  expect(readOrder(first)).toBeLessThan(readOrder(second))
}

describe('ChatPage attachment drafting', () => {
  beforeEach(() => {
    window.localStorage.clear()
    window.localStorage.setItem('student-planner-token', 'stored-token')
    useChatStore.setState(createInitialChatState())
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.spyOn(api, 'uploadSchedule').mockRejectedValue(new Error('should not upload during drafting'))
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

    render(<ChatPage />)

    const socket = MockWebSocket.instances[0]
    expect(socket).toBeDefined()
    if (!socket) {
      return
    }
    socket.readyState = 0

    const input = screen.getByLabelText('上传课表')
    await user.upload(input, createFile('math-1.png', 'image/png'))
    await user.click(screen.getByRole('button', { name: '发送消息' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('聊天连接不可用，请稍后重试')
    expect(screen.getByRole('region', { name: '待发送附件' })).toHaveTextContent('待发送附件 1')
    expect(screen.getByText('math-1.png')).toBeInTheDocument()
    expect(screen.queryByText('已发送 1 张课表图片')).not.toBeInTheDocument()
    expect(socket.send).not.toHaveBeenCalledWith(
      JSON.stringify({
        message: '我上传了课表图片 file_id=schedule-file-3，请解析并展示确认卡片。',
      }),
    )
  })

  it('does not append a text message when the websocket cannot send it', async () => {
    const user = userEvent.setup()

    render(<ChatPage />)

    const socket = MockWebSocket.instances[0]
    expect(socket).toBeDefined()
    if (!socket) {
      return
    }
    socket.readyState = 0

    await user.type(screen.getByLabelText('输入消息'), '帮我安排今天的复习')
    await user.click(screen.getByRole('button', { name: '发送消息' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('聊天连接不可用，请稍后重试')
    expect(screen.getByLabelText('输入消息')).toHaveValue('帮我安排今天的复习')
    expect(screen.queryByText('帮我安排今天的复习')).not.toBeInTheDocument()
    expect(socket.send).not.toHaveBeenCalledWith(
      JSON.stringify({
        message: '帮我安排今天的复习',
      }),
    )
  })

  it('routes plain review follow-up answers through the main input as ask_user answers', async () => {
    const user = userEvent.setup()
    render(<ChatPage />)

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
    render(<ChatPage />)

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
    render(<ChatPage />)

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
    expect(screen.getByText('正在继续处理，请稍候…')).toBeInTheDocument()
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  })

  it('renders a dynamic progress card with ratio and current step', () => {
    render(<ChatPage />)

    act(() => {
      useChatStore.getState().applyServerEvent({
        type: 'tool_call',
        name: 'parse_schedule',
      })
    })

    expect(screen.getByRole('progressbar')).toBeInTheDocument()
    expect(screen.getByText('当前：解析课表')).toBeInTheDocument()

    act(() => {
      useChatStore.getState().applyServerEvent({
        type: 'tool_result',
        name: 'parse_schedule',
      })
    })

    expect(screen.getByText('1/1')).toBeInTheDocument()
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
    expect(screen.getByText('教学楼A301 · 张老师 · 1-16周')).toBeInTheDocument()
    expect(screen.getByText('周二：第3-4节 10:00-11:40')).toBeInTheDocument()
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
    const followupReply = screen.getByText('这是后续回复')

    expect(askCard).toBeTruthy()
    expectNodeBefore(askCard as HTMLElement, followupReply)
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
      fireEvent.click(screen.getByRole('button', { name: '发送消息' }))

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
