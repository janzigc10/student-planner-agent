import { Outlet, useLocation, useNavigate } from 'react-router-dom'

import { useCalendarStore } from '../stores/calendarStore'
import {
  CalendarIcon,
  ChatIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  PlusIcon,
  TaskIcon,
  UserIcon,
} from './icons'

const tabs = [
  { path: '/chat', label: '聊天', icon: ChatIcon },
  { path: '/calendar', label: '日历', icon: CalendarIcon },
  { path: '/me', label: '我的', icon: UserIcon },
]

function pageTitle(pathname: string, currentDate: string) {
  if (pathname.startsWith('/chat')) {
    return '聊天'
  }
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
  return '学习规划'
}

export function AppShell() {
  const location = useLocation()
  const navigate = useNavigate()
  const currentDate = useCalendarStore((state) => state.currentDate)
  const calendarViewMode = useCalendarStore((state) => state.viewMode)
  const setCalendarViewMode = useCalendarStore((state) => state.setViewMode)
  const shiftDate = useCalendarStore((state) => state.shiftDate)
  const shiftMonth = useCalendarStore((state) => state.shiftMonth)
  const isSubPage = location.pathname.startsWith('/me/')
  const isCalendarRoute = location.pathname === '/calendar'
  const canOpenTaskSheet = isCalendarRoute && calendarViewMode === 'day'
  const calendarToggleLabel = calendarViewMode === 'month' ? '日视图' : '月视图'
  const previousLabel = calendarViewMode === 'month' ? '上个月' : '上一天'
  const nextLabel = calendarViewMode === 'month' ? '下个月' : '下一天'
  const title = pageTitle(location.pathname, currentDate)

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

  function shiftCalendar(step: number) {
    if (calendarViewMode === 'month') {
      shiftMonth(step)
      return
    }
    shiftDate(step)
  }

  return (
    <div className="app-frame">
      <header className="top-bar">
        <div className="top-bar__leading">
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
            <span className="top-bar__brand-mark">SP</span>
          )}
        </div>
        <div className="top-bar__center">
          {isCalendarRoute ? (
            <div className="top-bar__title top-bar__calendar-title">
              <button className="top-bar__nav" type="button" aria-label={previousLabel} onClick={() => shiftCalendar(-1)}>
                <ChevronLeftIcon className="icon" />
              </button>
              <span>日历</span>
              <button className="top-bar__nav" type="button" aria-label={nextLabel} onClick={() => shiftCalendar(1)}>
                <ChevronRightIcon className="icon" />
              </button>
            </div>
          ) : (
            <>
              <div className="top-bar__title">{title}</div>
              <div className="top-bar__subtitle">学习计划工作台</div>
            </>
          )}
        </div>
        <div className="top-bar__trailing">
          {canOpenTaskSheet ? (
            <button className="top-bar__action top-bar__action--primary" type="button" aria-label="添加任务" onClick={openCalendarTaskSheet}>
              <PlusIcon className="icon icon--plus" />
            </button>
          ) : (
            <span className="top-bar__sync">在线</span>
          )}
        </div>
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
