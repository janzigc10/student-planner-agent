import type { Course, Task, TokenResponse, User } from '../types/api'

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
  const isFormData = options.body instanceof FormData
  const response = await fetch(path, {
    ...options,
    headers: {
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
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
  uploadSchedule(file: File) {
    const formData = new FormData()
    formData.append('file', file)
    return request<{ file_id: string; kind: 'spreadsheet' | 'image'; count: number; courses: unknown[] }>(
      '/api/schedule/upload',
      {
        method: 'POST',
        body: formData,
      },
    )
  },
  listCourses() {
    return request<Course[]>('/api/courses/')
  },
  listTasks(dateFrom: string, dateTo: string) {
    return request<Task[]>(`/api/tasks/?date_from=${dateFrom}&date_to=${dateTo}`)
  },
  createTask(body: {
    title: string
    description?: string
    scheduled_date: string
    start_time: string
    end_time: string
    exam_id?: string
  }) {
    return request<Task>('/api/tasks/', {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },
  updateTask(taskId: string, body: Partial<Pick<Task, 'title' | 'description' | 'scheduled_date' | 'start_time' | 'end_time' | 'status'>>) {
    return request<Task>(`/api/tasks/${taskId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    })
  },
}
