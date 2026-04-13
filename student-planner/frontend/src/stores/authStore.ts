import { create } from 'zustand'

import { api, clearToken, getStoredToken, storeToken } from '../api/client'
import type { User } from '../types/api'

interface AuthState {
  token: string | null
  user: User | null
  isBootstrapping: boolean
  login: (username: string, password: string) => Promise<void>
  register: (username: string, password: string) => Promise<void>
  bootstrap: () => Promise<void>
  logout: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  token: getStoredToken(),
  user: null,
  isBootstrapping: false,
  async login(username, password) {
    const tokenResponse = await api.login(username, password)
    storeToken(tokenResponse.access_token)
    const user = await api.me()
    set({ token: tokenResponse.access_token, user })
  },
  async register(username, password) {
    await api.register(username, password)
  },
  async bootstrap() {
    set({ isBootstrapping: true })
    try {
      const user = await api.me()
      set({ token: getStoredToken(), user, isBootstrapping: false })
    } catch {
      clearToken()
      set({ token: null, user: null, isBootstrapping: false })
    }
  },
  logout() {
    clearToken()
    set({ token: null, user: null, isBootstrapping: false })
  },
}))
