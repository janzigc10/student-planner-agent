import { Outlet, useLocation, useNavigate } from 'react-router-dom'

import { useCalendarStore } from '../stores/calendarStore'
import { CalendarIcon, ChatIcon, ChevronLeftIcon, PlusIcon, TaskIcon, UserIcon } from './icons'

const tabs = [
  { path: '/chat', label: '聊天', icon: ChatIcon },
  { path: '/calendar', label: '日历', icon: CalendarIcon },
  { path: '/me', label: '我的', icon: UserIcon },
]

function pageTitle(pathname: string, currentDate: string) {
  if (pathname.startsWith('/calendar')) {
    const [year, month, day] = currentDate.split('-').map((value) => Number(value))
    const date = Number.isFinite(year) && Number.isFinite(month) && Number.isFinite(day)
      ? new Date(year, month - 1, day)
      : new Date()
    return new Intl.DateTimeFormat('zh-CN', {
      month: 'long',
      day: 'numeric',
      weekday: 'short',
    }).format(date)
  }
  if (pathname === '/me/courses') {
    return '课表管理'
  }
  if (pathname === '/me/preferences') {
    return '偏好设置'
  }
  if (pathname === '/me/notifications') {
    return '通知设置'
  }
  if (pathname === '/me') {
    return '我的'
  }
  return 'Assistant'
}

export function AppShell() {
  const location = useLocation()
  const navigate = useNavigate()
  const currentDate = useCalendarStore((state) => state.currentDate)
  const calendarViewMode = useCalendarStore((state) => state.viewMode)
  const setCalendarViewMode = useCalendarStore((state) => state.setViewMode)
  const isSubPage = location.pathname.startsWith('/me/')
  const isCalendarRoute = location.pathname === '/calendar'
  const canOpenTaskSheet = isCalendarRoute && calendarViewMode === 'day'
  const calendarToggleLabel = calendarViewMode === 'month' ? '日视图' : '月视图'

  function openCalendarTaskSheet() {
    window.dispatchEvent(new Event('calendar:add-task'))
  }

  function goBack() {
    if (location.pathname.startsWith('/me/')) {
      navigate('/me')
      return
    }
    navigate(-1)
  }

  function toggleCalendarViewMode() {
    setCalendarViewMode(calendarViewMode === 'month' ? 'day' : 'month')
  }

  return (
    <div className="app-frame">
      <header className="top-bar">
        {isSubPage ? (
          <button className="top-bar__back" type="button" aria-label="返回上一页" onClick={goBack}>
            <ChevronLeftIcon className="icon" />
            <span>返回</span>
          </button>
        ) : isCalendarRoute ? (
          <button className="top-bar__action" type="button" aria-label={calendarToggleLabel} onClick={toggleCalendarViewMode}>
            {calendarViewMode === 'month' ? <TaskIcon className="icon" /> : <CalendarIcon className="icon" />}
          </button>
        ) : (
          <span />
        )}
        <div className="top-bar__title">{pageTitle(location.pathname, currentDate)}</div>
        {canOpenTaskSheet ? (
          <button className="top-bar__action" type="button" aria-label="添加任务" onClick={openCalendarTaskSheet}>
            <PlusIcon className="icon icon--plus" />
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
            className="tab-bar__item"
            aria-current={location.pathname.startsWith(tab.path) ? 'page' : undefined}
            onClick={() => navigate(tab.path)}
          >
            <tab.icon className="icon tab-bar__icon" />
            <span>{tab.label}</span>
          </button>
        ))}
      </nav>
    </div>
  )
}
