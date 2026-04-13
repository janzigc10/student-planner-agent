import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'
import { useAuthStore } from './stores/authStore'

describe('app auth routing', () => {
  beforeEach(() => {
    window.localStorage.clear()
    useAuthStore.setState({ token: null, user: null, isBootstrapping: false })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('redirects protected routes to login when no token exists', async () => {
    window.history.pushState({}, '', '/calendar')

    render(<App />)

    expect(await screen.findByRole('heading', { name: '登录' })).toBeInTheDocument()
  })

  it('restores a stored token and renders the mobile shell', async () => {
    window.localStorage.setItem('student-planner-token', 'saved-token')
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          id: 'user-1',
          username: 'chen',
          preferences: {},
          current_semester_start: null,
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    window.history.pushState({}, '', '/chat')
    useAuthStore.setState({ token: 'saved-token', user: null, isBootstrapping: false })

    render(<App />)

    expect(await screen.findByText('Assistant')).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: '主导航' })).toBeInTheDocument()
  })

  it('logs in and stores the returned token', async () => {
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ access_token: 'new-token', token_type: 'bearer' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: 'user-1',
            username: 'alice',
            preferences: {},
            current_semester_start: null,
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      )
    window.history.pushState({}, '', '/login')

    render(<App />)
    await userEvent.type(screen.getByLabelText('用户名'), 'alice')
    await userEvent.type(screen.getByLabelText('密码'), 'pass123')
    await userEvent.click(screen.getByRole('button', { name: '登录' }))

    await waitFor(() => {
      expect(window.localStorage.getItem('student-planner-token')).toBe('new-token')
    })
    expect(await screen.findByText('Assistant')).toBeInTheDocument()
  })
})
