import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { useAuthStore } from '../stores/authStore'

export function LoginPage() {
  const navigate = useNavigate()
  const login = useAuthStore((state) => state.login)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError('')
    try {
      await login(username, password)
      navigate('/chat', { replace: true })
    } catch {
      setError('登录失败，请检查用户名和密码')
    }
  }

  return (
    <main className="auth-page">
      <h1>登录</h1>
      <p className="auth-page__subtitle">欢迎回来，继续你的学习计划。</p>
      <form className="auth-form" onSubmit={submit}>
        <label>
          用户名
          <input value={username} onChange={(event) => setUsername(event.target.value)} />
        </label>
        <label>
          密码
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
        </label>
        {error ? <p role="alert">{error}</p> : null}
        <button className="primary-button" type="submit">
          登录
        </button>
      </form>
      <p className="auth-page__link">
        还没有账号？<Link to="/register">注册</Link>
      </p>
    </main>
  )
}
