import { useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent, TouchEvent } from 'react'

import { eventsForDate, useCalendarStore } from '../stores/calendarStore'

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

export function CalendarPage() {
  const {
    completeTask,
    courses,
    createTask,
    currentDate,
    error,
    isLoading,
    load,
    setCurrentDate,
    shiftDate,
    tasks,
  } = useCalendarStore()
  const [isMonthView, setIsMonthView] = useState(false)
  const [isAdding, setIsAdding] = useState(false)
  const [title, setTitle] = useState('')
  const [startTime, setStartTime] = useState('10:00')
  const [endTime, setEndTime] = useState('11:00')
  const [description, setDescription] = useState('')
  const touchStartXRef = useRef<number | null>(null)
  const events = useMemo(() => eventsForDate(currentDate, courses, tasks), [courses, currentDate, tasks])

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

  const monthDays = useMemo(() => {
    const [year, month] = currentDate.split('-').map((value) => Number(value))
    if (!Number.isFinite(year) || !Number.isFinite(month)) {
      return 31
    }
    return new Date(year, month, 0).getDate()
  }, [currentDate])

  function selectMonthDay(day: number) {
    const [year, month] = currentDate.split('-').map((value) => Number(value))
    if (!Number.isFinite(year) || !Number.isFinite(month)) {
      setIsMonthView(false)
      return
    }
    const nextDate = toDateString(new Date(year, month - 1, day))
    setCurrentDate(nextDate)
    void load()
    setIsMonthView(false)
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    await createTask({
      title,
      description,
      scheduled_date: currentDate,
      start_time: startTime,
      end_time: endTime,
    })
    setTitle('')
    setDescription('')
    setIsAdding(false)
  }

  function handleTouchStart(event: TouchEvent<HTMLElement>) {
    if (isInteractiveTarget(event.target)) {
      touchStartXRef.current = null
      return
    }

    if (event.touches.length >= 2) {
      setIsMonthView(true)
      return
    }
    touchStartXRef.current = event.touches[0]?.clientX ?? null
  }

  function handleTouchEnd(event: TouchEvent<HTMLElement>) {
    if (isInteractiveTarget(event.target)) {
      touchStartXRef.current = null
      return
    }

    const startX = touchStartXRef.current
    const endX = event.changedTouches[0]?.clientX
    touchStartXRef.current = null
    if (startX === null || endX === undefined) {
      return
    }
    const delta = endX - startX
    if (delta > 60) shiftDate(-1)
    if (delta < -60) shiftDate(1)
  }

  if (isMonthView) {
    return (
      <main className="page calendar-page">
        <button className="primary-button" type="button" onClick={() => setIsMonthView(false)}>
          回到日视图
        </button>
        <div className="month-grid" aria-label="月视图">
          {Array.from({ length: monthDays }, (_, index) => index + 1).map((day) => (
            <button type="button" key={day} onClick={() => selectMonthDay(day)}>
              {day}
              <span className="dot dot--course" />
              <span className="dot dot--task" />
            </button>
          ))}
        </div>
      </main>
    )
  }

  return (
    <main className="page calendar-page">
      <div className="calendar-actions">
        <button type="button" onClick={() => shiftDate(-1)}>
          前一天
        </button>
        <strong>{currentDate}</strong>
        <button type="button" onClick={() => shiftDate(1)}>
          后一天
        </button>
        <button type="button" onClick={() => setIsMonthView(true)}>
          月视图
        </button>
        <button type="button" onClick={() => setIsAdding(true)}>
          添加任务
        </button>
      </div>
      {isLoading ? <p>正在加载...</p> : null}
      {error ? <p role="alert">{error}</p> : null}
      <section className="timeline" aria-label="日视图" onTouchStart={handleTouchStart} onTouchEnd={handleTouchEnd}>
        {events.length === 0 ? <p>今天还没有安排。</p> : null}
        {events.map((event) => (
          <article className={`timeline-item timeline-item--${event.kind}`} key={`${event.kind}-${event.id}`}>
            <time>
              {event.start_time}-{event.end_time}
            </time>
            <div>
              <strong>{event.kind === 'course' ? '📚 ' : '📝 '}{event.title}</strong>
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
        <form className="sheet-form" onSubmit={submit}>
          <h2>添加任务</h2>
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
          <button className="primary-button" type="submit">
            保存
          </button>
        </form>
      ) : null}
    </main>
  )
}
