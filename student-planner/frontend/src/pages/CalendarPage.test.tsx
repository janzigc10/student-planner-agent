import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import { api } from '../api/client'
import { AppShell } from '../components/AppShell'
import { useCalendarStore } from '../stores/calendarStore'
import { CalendarPage } from './CalendarPage'

function renderCalendarShell() {
  return render(
    <MemoryRouter initialEntries={['/calendar']}>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/calendar" element={<CalendarPage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

describe('Calendar page integration', () => {
  beforeEach(() => {
    useCalendarStore.setState({
      currentDate: '2026-03-30',
      viewMode: 'day',
      courses: [],
      tasks: [],
      isLoading: false,
      error: null,
    })
    vi.spyOn(api, 'listCourses').mockResolvedValue([])
    vi.spyOn(api, 'listTasks').mockResolvedValue([])
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('opens the add-task sheet when tapping the calendar top-bar plus button', async () => {
    const user = userEvent.setup()
    renderCalendarShell()

    await waitFor(() => {
      expect(api.listTasks).toHaveBeenCalled()
    })
    expect(screen.queryByRole('heading', { name: '添加任务' })).not.toBeInTheDocument()

    await user.click(screen.getByLabelText('添加任务'))

    expect(await screen.findByRole('heading', { name: '添加任务' })).toBeInTheDocument()
    expect(screen.getByRole('dialog', { name: '添加任务' })).toBeInTheDocument()
  })

  it('switches to the selected day from month view and reloads that day timeline', async () => {
    const user = userEvent.setup()
    renderCalendarShell()

    await waitFor(() => {
      expect(api.listTasks).toHaveBeenCalledWith('2026-03-30', '2026-03-30')
    })

    await user.click(screen.getByRole('button', { name: '月视图' }))
    expect(screen.getByLabelText('月视图')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '1' }))

    expect(document.querySelector('.month-card')).not.toBeInTheDocument()
    expect(screen.getByText(/3月1日/)).toBeInTheDocument()

    await waitFor(() => {
      expect(api.listTasks).toHaveBeenLastCalledWith('2026-03-01', '2026-03-01')
    })
  })

  it('hides the top-right add button in month view and restores it in day view', async () => {
    const user = userEvent.setup()
    renderCalendarShell()

    await waitFor(() => {
      expect(api.listTasks).toHaveBeenCalled()
    })
    expect(screen.getByLabelText('添加任务')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '月视图' }))
    expect(screen.queryByLabelText('添加任务')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '日视图' }))
    expect(screen.getByLabelText('添加任务')).toBeInTheDocument()
  })

  it('switches month by swipe gestures in month view', async () => {
    const user = userEvent.setup()
    renderCalendarShell()

    await waitFor(() => {
      expect(api.listTasks).toHaveBeenCalledWith('2026-03-30', '2026-03-30')
    })

    await user.click(screen.getByRole('button', { name: '月视图' }))
    expect(screen.getByText('2026 / 03')).toBeInTheDocument()

    const monthCard = screen.getByText('月视图').closest('.month-card')
    expect(monthCard).toBeTruthy()

    fireEvent.touchStart(monthCard as Element, { touches: [{ clientX: 220 }] })
    fireEvent.touchEnd(monthCard as Element, { changedTouches: [{ clientX: 120 }] })
    await waitFor(() => {
      expect(screen.getByText('2026 / 02')).toBeInTheDocument()
      expect(api.listTasks).toHaveBeenLastCalledWith('2026-02-28', '2026-02-28')
    })

    fireEvent.touchStart(monthCard as Element, { touches: [{ clientX: 120 }] })
    fireEvent.touchEnd(monthCard as Element, { changedTouches: [{ clientX: 220 }] })
    await waitFor(() => {
      expect(screen.getByText('2026 / 03')).toBeInTheDocument()
      expect(api.listTasks).toHaveBeenLastCalledWith('2026-03-28', '2026-03-28')
    })
  })

  it('changes day by exactly one day when swiping left and right in day view', async () => {
    const { container } = renderCalendarShell()

    await waitFor(() => {
      expect(api.listTasks).toHaveBeenCalledWith('2026-03-30', '2026-03-30')
    })

    const dayView = container.querySelector<HTMLElement>('main.calendar-page')
    expect(dayView).toBeTruthy()

    fireEvent.touchStart(dayView as HTMLElement, { touches: [{ clientX: 220 }] })
    fireEvent.touchEnd(dayView as HTMLElement, { changedTouches: [{ clientX: 120 }] })
    await waitFor(() => {
      expect(api.listTasks).toHaveBeenLastCalledWith('2026-03-31', '2026-03-31')
    })

    fireEvent.touchStart(dayView as HTMLElement, { touches: [{ clientX: 120 }] })
    fireEvent.touchEnd(dayView as HTMLElement, { changedTouches: [{ clientX: 220 }] })
    await waitFor(() => {
      expect(api.listTasks).toHaveBeenLastCalledWith('2026-03-30', '2026-03-30')
    })
  })

  it('renders timeline content without emoji prefixes', async () => {
    useCalendarStore.setState({
      currentDate: '2026-03-30',
      viewMode: 'day',
      courses: [
        {
          id: 'course-1',
          user_id: 'user-1',
          name: '高等数学',
          teacher: null,
          location: '教学楼A301',
          weekday: 1,
          start_time: '08:00',
          end_time: '09:40',
          week_start: 1,
          week_end: 16,
        },
      ],
      tasks: [
        {
          id: 'task-1',
          user_id: 'user-1',
          exam_id: null,
          title: '复习线代',
          description: '第1-3章',
          scheduled_date: '2026-03-30',
          start_time: '10:00',
          end_time: '12:00',
          status: 'pending',
        },
      ],
      isLoading: false,
      error: null,
    })
    vi.mocked(api.listCourses).mockResolvedValue([])
    vi.mocked(api.listTasks).mockResolvedValue([])

    const { container } = renderCalendarShell()

    await waitFor(() => {
      expect(api.listTasks).toHaveBeenCalled()
    })
    expect(container.textContent).not.toMatch(/[📚📝]/)
  })

})
