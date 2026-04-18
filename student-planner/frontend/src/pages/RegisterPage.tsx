import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { useAuthStore } from '../stores/authStore'

export function RegisterPage() {
  const navigate = useNavigate()
  const register = useAuthStore((state) => state.register)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')

  async function submit(event: FormEvent) {
    event.preventDefault()
    await register(username, password)
    navigate('/login', { replace: true })
  }

  return (
    <main className="auth-page">
      <h1>注册</h1>
      <p className="auth-page__subtitle">创建账号，开启更智能的时间规划。</p>
      <form className="auth-form" onSubmit={submit}>
        <label>
          用户名
          <input value={username} onChange={(event) => setUsername(event.target.value)} />
        </label>
        <label>
          密码
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
        </label>
        <button className="primary-button" type="submit">
          注册
        </button>
      </form>
      <p className="auth-page__link">
        已有账号？<Link to="/login">登录</Link>
      </p>
    </main>
  )
}
