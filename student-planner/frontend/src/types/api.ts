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
