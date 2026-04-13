import { Outlet, useLocation, useNavigate } from 'react-router-dom'

const tabs = [
  { path: '/chat', label: '聊天', icon: '💬' },
  { path: '/calendar', label: '日历', icon: '📅' },
  { path: '/me', label: '我的', icon: '👤' },
]

function pageTitle(pathname: string) {
  if (pathname.startsWith('/calendar')) {
    return new Intl.DateTimeFormat('zh-CN', {
      month: 'long',
      day: 'numeric',
      weekday: 'short',
    }).format(new Date())
  }
  if (pathname.startsWith('/me')) {
    return '我的'
  }
  return 'Assistant'
}

export function AppShell() {
  const location = useLocation()
  const navigate = useNavigate()

  return (
    <div className="app-frame">
      <header className="top-bar">
        <span />
        <div className="top-bar__title">{pageTitle(location.pathname)}</div>
        {location.pathname.startsWith('/calendar') ? (
          <button className="top-bar__action" type="button" aria-label="添加任务">
            +
          </button>
        ) : (
          <span />
        )}
      </header>
      <Outlet />
      <nav className="tab-bar" aria-label="主导航">
        {tabs.map((tab) => (
          <button
            key={tab.path}
            type="button"
            aria-current={location.pathname.startsWith(tab.path) ? 'page' : undefined}
            onClick={() => navigate(tab.path)}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </nav>
    </div>
  )
}
