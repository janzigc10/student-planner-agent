import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { AppShell } from './AppShell'
import { useCalendarStore } from '../stores/calendarStore'

function renderShellAt(pathname: string) {
  return render(
    <MemoryRouter initialEntries={[pathname]}>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/chat" element={<div>chat</div>} />
          <Route path="/calendar" element={<div>calendar</div>} />
          <Route path="/me" element={<div>me</div>} />
          <Route path="/me/courses" element={<div>courses</div>} />
          <Route path="/me/preferences" element={<div>preferences</div>} />
          <Route path="/me/notifications" element={<div>notifications</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

describe('AppShell visual language', () => {
  beforeEach(() => {
    useCalendarStore.setState({ viewMode: 'day', currentDate: '2026-03-30' })
  })

  it('uses vector icons in tabs and does not render emoji labels', () => {
    const { container } = renderShellAt('/chat')

    const nav = screen.getByRole('navigation', { name: '主导航' })
    expect(nav.querySelectorAll('svg').length).toBeGreaterThanOrEqual(3)
    expect(container.textContent).not.toMatch(/[💬📅👤]/)
  })

  it('hides calendar top action when current view mode is month', () => {
    useCalendarStore.setState({ viewMode: 'month' })
    renderShellAt('/calendar')

    expect(screen.queryByLabelText('添加任务')).not.toBeInTheDocument()
  })

  it('toggles calendar view mode from the top-left icon button', async () => {
    const user = userEvent.setup()
    renderShellAt('/calendar')

    const monthButton = screen.getByRole('button', { name: '月视图' })
    expect(monthButton).toBeInTheDocument()

    await user.click(monthButton)
    expect(useCalendarStore.getState().viewMode).toBe('month')
    expect(screen.getByRole('button', { name: '日视图' })).toBeInTheDocument()
  })

  it('shows a back label button on secondary pages', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/me', '/me/courses']} initialIndex={1}>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/me" element={<div>me</div>} />
            <Route path="/me/courses" element={<div>courses</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByRole('button', { name: '返回上一页' })).toBeInTheDocument()
    expect(screen.getByText('课表管理')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '返回上一页' }))
    expect(screen.getByText('me')).toBeInTheDocument()
  })
})
