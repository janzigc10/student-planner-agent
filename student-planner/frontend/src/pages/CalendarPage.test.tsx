import { render, screen, waitFor } from '@testing-library/react'
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

    expect(screen.queryByLabelText('月视图')).not.toBeInTheDocument()
    expect(screen.getByText('2026-03-01')).toBeInTheDocument()

    await waitFor(() => {
      expect(api.listTasks).toHaveBeenLastCalledWith('2026-03-01', '2026-03-01')
    })
  })

  it('changes day by exactly one day when tapping previous and next buttons', async () => {
    const user = userEvent.setup()
    const { container } = renderCalendarShell()

    await waitFor(() => {
      expect(api.listTasks).toHaveBeenCalledWith('2026-03-30', '2026-03-30')
    })

    const dayButtons = container.querySelectorAll<HTMLButtonElement>('.calendar-actions button')
    const previousButton = dayButtons[0]
    const nextButton = dayButtons[1]

    expect(previousButton).toBeDefined()
    expect(nextButton).toBeDefined()

    await user.click(nextButton)

    expect(screen.getByText('2026-03-31')).toBeInTheDocument()
    await waitFor(() => {
      expect(api.listTasks).toHaveBeenLastCalledWith('2026-03-31', '2026-03-31')
    })

    await user.click(previousButton)

    expect(screen.getByText('2026-03-30')).toBeInTheDocument()
    await waitFor(() => {
      expect(api.listTasks).toHaveBeenLastCalledWith('2026-03-30', '2026-03-30')
    })
  })

})
