import { Link, useNavigate } from 'react-router-dom'

import { BellIcon, BookIcon, ChevronRightIcon, ExitIcon, SlidersIcon } from '../components/icons'
import { useAuthStore } from '../stores/authStore'

export function MePage() {
  const navigate = useNavigate()
  const user = useAuthStore((state) => state.user)
  const logout = useAuthStore((state) => state.logout)

  function signOut() {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <main className="page me-page">
      <section className="profile-card">
        <div className="profile-card__avatar">{user?.username?.slice(0, 1).toUpperCase() || 'S'}</div>
        <div>
          <span className="eyebrow">Student Planner</span>
          <h1>{user?.username ?? '我的账号'}</h1>
          <p>课表、任务、提醒和偏好都在这里管理。</p>
        </div>
      </section>
      <section className="profile-stats" aria-label="账户状态">
        <div>
          <span>课表</span>
          <strong>同步</strong>
        </div>
        <div>
          <span>提醒</span>
          <strong>可用</strong>
        </div>
        <div>
          <span>Agent</span>
          <strong>在线</strong>
        </div>
      </section>
      <nav className="me-menu" aria-label="我的菜单">
        <Link to="/me/courses">
          <span className="me-menu__item-main">
            <BookIcon className="icon" />
            <span>课表管理</span>
          </span>
          <ChevronRightIcon className="icon me-menu__item-arrow" />
        </Link>
        <Link to="/me/preferences">
          <span className="me-menu__item-main">
            <SlidersIcon className="icon" />
            <span>偏好设置</span>
          </span>
          <ChevronRightIcon className="icon me-menu__item-arrow" />
        </Link>
        <Link to="/me/notifications">
          <span className="me-menu__item-main">
            <BellIcon className="icon" />
            <span>通知设置</span>
          </span>
          <ChevronRightIcon className="icon me-menu__item-arrow" />
        </Link>
      </nav>
      <button className="primary-button" type="button" onClick={signOut}>
        <ExitIcon className="icon" />
        <span>退出登录</span>
      </button>
    </main>
  )
}
