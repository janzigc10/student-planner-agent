import { useAuthStore } from '../stores/authStore'

export function MePage() {
  const logout = useAuthStore((state) => state.logout)

  return (
    <main className="page">
      <button className="primary-button" type="button" onClick={logout}>
        退出登录
      </button>
    </main>
  )
}
