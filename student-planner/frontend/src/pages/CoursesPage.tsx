import { useEffect, useState } from 'react'
import type { ChangeEvent } from 'react'

import { api } from '../api/client'
import type { Course } from '../types/api'
import { BookIcon, PaperclipIcon } from '../components/icons'

const weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

export function CoursesPage() {
  const [courses, setCourses] = useState<Course[]>([])
  const [message, setMessage] = useState('')

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
    setMessage(`已解析 ${result.count} 门课，请回到聊天页确认导入。`)
  }

  return (
    <main className="page">
      <label className="primary-button import-button">
        <PaperclipIcon className="icon" />
        <span>导入课表</span>
        <input aria-label="导入课表" type="file" accept="image/*,.xls,.xlsx" onChange={importSchedule} />
      </label>
      {message ? <p className="status-inline status-inline--success">{message}</p> : null}
      <div className="course-grid" aria-label="周课表">
        {weekdays.map((weekday, index) => (
          <section key={weekday}>
            <h2>{weekday}</h2>
            {courses
              .filter((course) => course.weekday === index + 1)
              .map((course) => (
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
              ))}
          </section>
        ))}
      </div>
    </main>
  )
}
