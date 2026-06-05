import { useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent, TouchEvent } from 'react'

import { CourseIcon, TaskIcon } from '../components/icons'
import { useAuthStore } from '../stores/authStore'
import { courseOccursOnDate, eventsForDate, useCalendarStore } from '../stores/calendarStore'

function toDateString(date: Date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function isInteractiveTarget(target: EventTarget | null) {
  if (!(target instanceof Element)) {
    return false
  }
  return target.closest('button, input, textarea, select, a, label') !== null
}

const WEEK_LABELS = ['一', '二', '三', '四', '五', '六', '日']
const WEEKDAY_FULL_LABELS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

function dateMeta(date: string) {
  const parsed = new Date(`${date}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) {
    return { monthDay: date, weekday: '', day: '' }
  }
  return {
    monthDay: `${parsed.getMonth() + 1}月${parsed.getDate()}日`,
    weekday: WEEKDAY_FULL_LABELS[parsed.getDay()] ?? '',
    day: String(parsed.getDate()),
  }
}

function weekStripDates(currentDate: string) {
  const base = new Date(`${currentDate}T00:00:00`)
  if (Number.isNaN(base.getTime())) {
    return []
  }
  const weekday = base.getDay() === 0 ? 7 : base.getDay()
  const monday = new Date(base)
  monday.setDate(base.getDate() - weekday + 1)
  return Array.from({ length: 7 }, (_, index) => {
    const item = new Date(monday)
    item.setDate(monday.getDate() + index)
    return {
      date: toDateString(item),
      day: item.getDate(),
      label: WEEK_LABELS[index] ?? '',
    }
  })
}

export function CalendarPage() {
  const user = useAuthStore((state) => state.user)
  const semesterStart = user?.current_semester_start ?? null
  const {
    completeTask,
    courses,
    createTask,
    currentDate,
    error,
    isLoading,
    load,
    setCurrentDate,
    setViewMode,
    shiftDate,
    shiftMonth,
    tasks,
    viewMode,
  } = useCalendarStore()
  const isMonthView = viewMode === 'month'
  const [isAdding, setIsAdding] = useState(false)
  const [title, setTitle] = useState('')
  const [startTime, setStartTime] = useState('10:00')
  const [endTime, setEndTime] = useState('11:00')
  const [description, setDescription] = useState('')
  const initialReminderValue = useMemo(() => {
    const value = user?.preferences?.default_reminder_minutes
    if (typeof value === 'number' && value >= 0) {
      return String(value)
    }
    return 'none'
  }, [user?.preferences])
  const [reminderAdvanceMinutes, setReminderAdvanceMinutes] = useState(initialReminderValue)
  const dayTouchStartXRef = useRef<number | null>(null)
  const monthTouchStartXRef = useRef<number | null>(null)
  const events = useMemo(
    () => eventsForDate(currentDate, courses, tasks, semesterStart),
    [courses, currentDate, semesterStart, tasks],
  )
  const selectedDateMeta = useMemo(() => dateMeta(currentDate), [currentDate])
  const weekDates = useMemo(() => weekStripDates(currentDate), [currentDate])
  const pendingTasks = tasks.filter((task) => task.status !== 'completed').length
  const courseCount = events.filter((event) => event.kind === 'course').length
  const taskCount = events.filter((event) => event.kind === 'task').length
  const nextEvent = events[0] ?? null

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    function openTaskSheet() {
      setIsAdding(true)
    }
    window.addEventListener('calendar:add-task', openTaskSheet)
    return () => {
      window.removeEventListener('calendar:add-task', openTaskSheet)
    }
  }, [])

  useEffect(() => {
    if (!isAdding) {
      return
    }
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previousOverflow
    }
  }, [isAdding])

  const monthMeta = useMemo(() => {
    const [year, month, day] = currentDate.split('-').map((value) => Number(value))
    const fallback = new Date()
    if (!Number.isFinite(year) || !Number.isFinite(month) || !Number.isFinite(day)) {
      return {
        year: fallback.getFullYear(),
        month: fallback.getMonth() + 1,
        selectedDay: fallback.getDate(),
        daysInMonth: 31,
        leadingEmpty: 0,
      }
    }

    const firstWeekday = new Date(year, month - 1, 1).getDay()
    return {
      year,
      month,
      selectedDay: day,
      daysInMonth: new Date(year, month, 0).getDate(),
      leadingEmpty: (firstWeekday + 6) % 7,
    }
  }, [currentDate])

  const monthCells = useMemo(() => {
    const days = Array.from({ length: monthMeta.daysInMonth }, (_, index) => index + 1)
    const withLeading = [...Array.from({ length: monthMeta.leadingEmpty }, () => null), ...days]
    const trailingCount = (7 - (withLeading.length % 7)) % 7
    return [...withLeading, ...Array.from({ length: trailingCount }, () => null)]
  }, [monthMeta.daysInMonth, monthMeta.leadingEmpty])

  function selectMonthDay(day: number) {
    const [year, month] = currentDate.split('-').map((value) => Number(value))
    if (!Number.isFinite(year) || !Number.isFinite(month)) {
      setViewMode('day')
      return
    }
    const nextDate = toDateString(new Date(year, month - 1, day))
    setCurrentDate(nextDate)
    void load()
    setViewMode('day')
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    await createTask({
      title,
      description,
      scheduled_date: currentDate,
      start_time: startTime,
      end_time: endTime,
      reminder_advance_minutes: reminderAdvanceMinutes === 'none' ? null : Number(reminderAdvanceMinutes),
    })
    setTitle('')
    setDescription('')
    setReminderAdvanceMinutes(initialReminderValue)
    setIsAdding(false)
  }

  function closeTaskSheet() {
    setIsAdding(false)
  }

  function handleTouchStart(event: TouchEvent<HTMLElement>) {
    if (isInteractiveTarget(event.target)) {
      dayTouchStartXRef.current = null
      return
    }

    if (event.touches.length >= 2) {
      setViewMode('month')
      return
    }
    dayTouchStartXRef.current = event.touches[0]?.clientX ?? null
  }

  function handleTouchEnd(event: TouchEvent<HTMLElement>) {
    if (isInteractiveTarget(event.target)) {
      dayTouchStartXRef.current = null
      return
    }

    const startX = dayTouchStartXRef.current
    const endX = event.changedTouches[0]?.clientX
    dayTouchStartXRef.current = null
    if (startX === null || endX === undefined) {
      return
    }
    const delta = endX - startX
    if (delta > 60) shiftDate(-1)
    if (delta < -60) shiftDate(1)
  }

  function handleMonthTouchStart(event: TouchEvent<HTMLElement>) {
    monthTouchStartXRef.current = event.touches[0]?.clientX ?? null
  }

  function handleMonthTouchEnd(event: TouchEvent<HTMLElement>) {
    const startX = monthTouchStartXRef.current
    const endX = event.changedTouches[0]?.clientX
    monthTouchStartXRef.current = null
    if (startX === null || endX === undefined) {
      return
    }
    const delta = endX - startX
    if (delta < -60) shiftMonth(-1)
    if (delta > 60) shiftMonth(1)
  }

  if (isMonthView) {
    const today = new Date()
    const isCurrentMonthToday = today.getFullYear() === monthMeta.year && today.getMonth() + 1 === monthMeta.month

    return (
      <main className="page calendar-page calendar-page--month">
        <section className="calendar-overview">
          <span className="eyebrow">Month Plan</span>
          <h1>{monthMeta.month} 月排程</h1>
          <p>课程、任务和复习计划会按日期聚合，点选日期进入当天 agenda。</p>
        </section>
        <section className="month-card" onTouchStart={handleMonthTouchStart} onTouchEnd={handleMonthTouchEnd}>
          <div className="month-card__header">
            <div>
              <p className="month-card__title">
                {monthMeta.year} / {String(monthMeta.month).padStart(2, '0')}
              </p>
              <p className="month-card__subtitle">月视图</p>
            </div>
          </div>
          <div className="month-weekdays" aria-hidden="true">
            {WEEK_LABELS.map((label) => (
              <span key={label}>{label}</span>
            ))}
          </div>
          <div className="month-grid" aria-label="月视图">
            {monthCells.map((day, index) => {
              if (day === null) {
                return <span className="month-grid__blank" key={`blank-${index}`} aria-hidden="true" />
              }

              const isSelected = day === monthMeta.selectedDay
              const isToday = isCurrentMonthToday && day === today.getDate()
              const cell = new Date(monthMeta.year, monthMeta.month - 1, day)
              const weekday = cell.getDay() === 0 ? 7 : cell.getDay()
              const cellDate = toDateString(cell)
              const hasCourse = courses.some((course) => courseOccursOnDate(course, cellDate, semesterStart))
              const hasTask = isSelected && tasks.length > 0
              const classes = [
                'month-grid__day',
                isSelected ? 'month-grid__day--selected' : '',
                isToday ? 'month-grid__day--today' : '',
                weekday >= 6 ? 'month-grid__day--weekend' : '',
              ]
                .filter(Boolean)
                .join(' ')

              return (
                <button type="button" key={day} className={classes} onClick={() => selectMonthDay(day)}>
                  <span className="month-grid__day-number">{day}</span>
                  <span className="month-grid__meta" aria-hidden="true">
                    {hasCourse ? <span className="dot dot--course" /> : null}
                    {hasTask ? <span className="dot dot--task" /> : null}
                  </span>
                </button>
              )
            })}
          </div>
        </section>
      </main>
    )
  }

  return (
    <main className="page calendar-page" onTouchStart={handleTouchStart} onTouchEnd={handleTouchEnd}>
      <section className="calendar-overview">
        <div>
          <span className="eyebrow">Today</span>
          <h1>{selectedDateMeta.monthDay}</h1>
          <p>{selectedDateMeta.weekday} · {courseCount} 门课 · {taskCount} 个任务</p>
        </div>
        <div className="calendar-overview__next">
          <span>下一项</span>
          <strong>{nextEvent ? `${nextEvent.start_time} ${nextEvent.title}` : '暂无安排'}</strong>
        </div>
      </section>
      <section className="week-strip" aria-label="本周日期">
        {weekDates.map((item) => (
          <button
            type="button"
            key={item.date}
            className={`week-strip__day${item.date === currentDate ? ' week-strip__day--selected' : ''}`}
            onClick={() => {
              setCurrentDate(item.date)
              void load()
            }}
          >
            <span>{item.label}</span>
            <strong>{item.day}</strong>
          </button>
        ))}
      </section>
      {isLoading ? <p>正在加载...</p> : null}
      {error ? <p role="alert">{error}</p> : null}
      <section className="agenda-summary" aria-label="日程摘要">
        <div>
          <span>待办</span>
          <strong>{pendingTasks}</strong>
        </div>
        <div>
          <span>课程</span>
          <strong>{courseCount}</strong>
        </div>
        <div>
          <span>任务</span>
          <strong>{taskCount}</strong>
        </div>
      </section>
      <section className="timeline" aria-label="日视图">
        {events.length === 0 ? (
          <div className="timeline-empty">
            <strong>今天还没有安排。</strong>
            <span>可以让 Agent 帮你拆复习计划，或者点击右上角添加一个任务。</span>
          </div>
        ) : null}
        {events.map((event) => (
          <article className={`timeline-item timeline-item--${event.kind}`} key={`${event.kind}-${event.id}`}>
            <time>
              {event.start_time}-{event.end_time}
            </time>
            <div>
              <strong className="timeline-item__title">
                {event.kind === 'course' ? <CourseIcon className="icon timeline-item__icon" /> : <TaskIcon className="icon timeline-item__icon" />}
                <span>{event.title}</span>
              </strong>
              <p>{event.detail}</p>
              {event.kind === 'task' ? (
                <button type="button" onClick={() => void completeTask(event.id)}>
                  标记完成
                </button>
              ) : null}
            </div>
          </article>
        ))}
      </section>
      {isAdding ? (
        <div className="task-sheet" role="dialog" aria-modal="true" aria-label="添加任务">
          <button className="task-sheet__backdrop" type="button" aria-label="关闭添加任务弹窗" onClick={closeTaskSheet} />
          <form className="sheet-form task-sheet__panel" onSubmit={submit}>
            <div className="task-sheet__header">
              <h2>添加任务</h2>
              <button className="task-sheet__close" type="button" aria-label="关闭添加任务" onClick={closeTaskSheet}>
                ×
              </button>
            </div>
            <label>
              标题
              <input value={title} onChange={(event) => setTitle(event.target.value)} required />
            </label>
            <label>
              开始时间
              <input type="time" value={startTime} onChange={(event) => setStartTime(event.target.value)} required />
            </label>
            <label>
              结束时间
              <input type="time" value={endTime} onChange={(event) => setEndTime(event.target.value)} required />
            </label>
            <label>
              描述
              <textarea value={description} onChange={(event) => setDescription(event.target.value)} />
            </label>
            <label>
              提醒
              <select value={reminderAdvanceMinutes} onChange={(event) => setReminderAdvanceMinutes(event.target.value)}>
                <option value="none">不提醒</option>
                <option value="0">准点提醒</option>
                <option value="15">提前15分钟</option>
                <option value="30">提前30分钟</option>
                <option value="60">提前1小时</option>
              </select>
            </label>
            <button className="primary-button" type="submit">
              保存
            </button>
          </form>
        </div>
      ) : null}
    </main>
  )
}
