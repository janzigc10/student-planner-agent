export interface User {
  id: string
  username: string
  preferences: Record<string, unknown> | null
  current_semester_start: string | null
}

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface Course {
  id: string
  user_id: string
  name: string
  teacher: string | null
  location: string | null
  weekday: number
  start_time: string
  end_time: string
  week_start: number
  week_end: number
}

export interface Task {
  id: string
  user_id: string
  exam_id: string | null
  title: string
  description: string | null
  scheduled_date: string
  start_time: string
  end_time: string
  status: 'pending' | 'completed' | 'skipped'
}
