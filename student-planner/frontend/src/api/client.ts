import type { TokenResponse, User } from '../types/api'

const TOKEN_KEY = 'student-planner-token'

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

export function getStoredToken() {
  return window.localStorage.getItem(TOKEN_KEY)
}

export function storeToken(token: string) {
  window.localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken() {
  window.localStorage.removeItem(TOKEN_KEY)
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getStoredToken()
  const response = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  })

  if (response.status === 401 || response.status === 403) {
    clearToken()
  }

  if (!response.ok) {
    throw new ApiError(response.statusText || '请求失败', response.status)
  }

  return (await response.json()) as T
}

export const api = {
  login(username: string, password: string) {
    return request<TokenResponse>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
  },
  register(username: string, password: string) {
    return request<User>('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
  },
  me() {
    return request<User>('/api/auth/me')
  },
}
