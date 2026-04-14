import { render, screen } from '@testing-library/react'
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
  onclose: (() => void) | null = null

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
    queueMicrotask(() => this.onopen?.())
  }
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

    await user.click(screen.getByRole('button', { name: '发送' }))

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
    expect(screen.queryByRole('region', { name: '待发送附件' })).not.toBeInTheDocument()
  })

  it('keeps pending attachments when upload fails on send', async () => {
    const user = userEvent.setup()
    vi.spyOn(api, 'uploadSchedule').mockRejectedValue(new Error('upload failed'))

    render(<ChatPage />)

    const input = screen.getByLabelText('上传课表')
    await user.upload(input, createFile('math-1.png', 'image/png'))

    await user.click(screen.getByRole('button', { name: '发送' }))

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

    await user.click(screen.getByRole('button', { name: '发送' }))

    expect(uploadSchedule).toHaveBeenCalledTimes(1)
    expect(uploadSchedule).toHaveBeenCalledWith([expect.objectContaining({ name: 'schedule.xlsx' })])
    expect(MockWebSocket.instances[0]?.send).toHaveBeenLastCalledWith(
      JSON.stringify({
        message: '我上传了课表文件 file_id=schedule-file-2，请解析并展示确认卡片。',
      }),
    )
    expect(await screen.findByText('已发送 1 个课表文件')).toBeInTheDocument()
    expect(screen.queryByText('schedule.xlsx')).not.toBeInTheDocument()
  })
})
