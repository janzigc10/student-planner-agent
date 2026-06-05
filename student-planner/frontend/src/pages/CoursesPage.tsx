import { useEffect, useState } from 'react'
import type { ChangeEvent } from 'react'

import { api } from '../api/client'
import type { Course } from '../types/api'
import { BookIcon, PaperclipIcon } from '../components/icons'

const weekdays = [
  { label: '周一', short: '一' },
  { label: '周二', short: '二' },
  { label: '周三', short: '三' },
  { label: '周四', short: '四' },
  { label: '周五', short: '五' },
  { label: '周六', short: '六' },
  { label: '周日', short: '日' },
]

export function CoursesPage() {
  const [courses, setCourses] = useState<Course[]>([])
  const [message, setMessage] = useState('')
  const [selectedWeekday, setSelectedWeekday] = useState<number | null>(null)

  async function loadCourses() {
    setCourses(await api.listCourses())
  }

  useEffect(() => {
    void loadCourses()
  }, [])

  async function removeCourse(courseId: string) {
    await api.deleteCourse(courseId)
    await loadCourses()
  }

  async function importSchedule(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return
    const result = await api.uploadSchedule(file)
    if (result.kind === 'image' && result.status === 'processing') {
      setMessage('已收到课表图片，正在后台解析。请回到聊天页查看进度并确认导入。')
      return
    }
    setMessage(`已解析 ${result.count} 门课，请回到聊天页确认导入。`)
  }

  const selectedDayCourses = selectedWeekday ? courses.filter((course) => course.weekday === selectedWeekday) : []
  const selectedDayLabel = selectedWeekday ? weekdays[selectedWeekday - 1]?.label ?? '' : ''

  return (
    <main className="page courses-page">
      <section className="settings-hero">
        <div>
          <span className="eyebrow">Schedule Source</span>
          <h1>课表管理</h1>
          <p>导入课表后，Agent 会基于课程时间安排任务和提醒。</p>
        </div>
        <label className="primary-button import-button">
          <PaperclipIcon className="icon" />
          <span>导入课表</span>
          <input aria-label="导入课表" type="file" accept="image/*,.xls,.xlsx" onChange={importSchedule} />
        </label>
      </section>
      {message ? <p className="status-inline status-inline--success">{message}</p> : null}
      {courses.length === 0 ? (
        <section className="empty-panel">
          <BookIcon className="icon" />
          <strong>还没有课程</strong>
          <span>上传课表图片或 Excel，确认后会按周几自动整理到下面的课表里。</span>
        </section>
      ) : null}
      <div className="course-day-picker" aria-label="周课表">
        {weekdays.map((weekday, index) => {
          const dayCourses = courses.filter((course) => course.weekday === index + 1)
          const firstCourse = dayCourses[0] ?? null
          const dayNumber = index + 1
          const isSelected = selectedWeekday === dayNumber

          return (
            <button
              aria-pressed={isSelected}
              className={`course-day-button ${isSelected ? 'course-day-button--active' : ''}`}
              key={weekday.label}
              type="button"
              onClick={() => setSelectedWeekday(isSelected ? null : dayNumber)}
            >
              <strong>{weekday.short}</strong>
              <span>{dayCourses.length > 0 ? `${dayCourses.length} 门课` : '空'}</span>
              <small>{firstCourse ? firstCourse.start_time : '无安排'}</small>
            </button>
          )
        })}
      </div>
      {selectedWeekday ? (
        <section className="course-day-panel" aria-label={`${selectedDayLabel}课程明细`}>
          <header>
            <div>
              <h2>{selectedDayLabel}</h2>
              <p>{selectedDayCourses.length > 0 ? `${selectedDayCourses.length} 门课` : '暂无课程'}</p>
            </div>
            <button type="button" onClick={() => setSelectedWeekday(null)}>
              收起
            </button>
          </header>
          {selectedDayCourses.length > 0 ? (
            selectedDayCourses.map((course) => (
              <article key={course.id}>
                <strong className="course-grid__title">
                  <BookIcon className="icon" />
                  <span>{course.name}</span>
                </strong>
                <p>{course.start_time}-{course.end_time}</p>
                <p>{course.location}</p>
                <button type="button" onClick={() => void removeCourse(course.id)}>
                  删除
                </button>
              </article>
            ))
          ) : (
            <p className="course-day-panel__empty">这一天还没有课程。</p>
          )}
        </section>
      ) : (
        <p className="course-picker-hint">点选某一天查看课程明细。</p>
      )}
    </main>
  )
}
