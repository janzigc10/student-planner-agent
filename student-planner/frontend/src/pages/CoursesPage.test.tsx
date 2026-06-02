import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '../api/client'
import { CoursesPage } from './CoursesPage'

describe('CoursesPage', () => {
  beforeEach(() => {
    vi.spyOn(api, 'listCourses').mockResolvedValue([])
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('shows background parsing feedback for image schedule uploads', async () => {
    const file = new File(['image'], 'schedule.png', { type: 'image/png' })
    const uploadSpy = vi.spyOn(api, 'uploadSchedule').mockResolvedValue({
      file_id: 'schedule-file',
      kind: 'image',
      status: 'processing',
      count: 0,
      source_file_count: 1,
      courses: [],
    })

    render(<CoursesPage />)

    await userEvent.upload(screen.getByLabelText('导入课表'), file)

    await waitFor(() => {
      expect(uploadSpy).toHaveBeenCalledWith(file)
    })
    expect(await screen.findByText('已收到课表图片，正在后台解析。请回到聊天页查看进度并确认导入。')).toBeInTheDocument()
  })
})
