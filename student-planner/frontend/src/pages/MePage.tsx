import { Link, useNavigate } from 'react-router-dom'

import { BellIcon, BookIcon, ChevronRightIcon, ExitIcon, SlidersIcon } from '../components/icons'
import { useAuthStore } from '../stores/authStore'

export function MePage() {
  const navigate = useNavigate()
  const logout = useAuthStore((state) => state.logout)

  function signOut() {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <main className="page me-page">
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
