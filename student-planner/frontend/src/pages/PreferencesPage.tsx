import { useState } from 'react'
import type { FormEvent } from 'react'

import { api } from '../api/client'
import { SlidersIcon } from '../components/icons'
import { useAuthStore } from '../stores/authStore'

export function parsePeriodSchedule(text: string) {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .reduce<Record<string, { start: string; end: string }>>((schedule, line) => {
      const [period, range] = line.split('=')
      const [start, end] = (range ?? '').split('-')
      if (period && start && end) {
        schedule[period.trim()] = { start: start.trim(), end: end.trim() }
      }
      return schedule
    }, {})
}

export function PreferencesPage() {
  const { user } = useAuthStore()
  const [semesterStart, setSemesterStart] = useState(user?.current_semester_start ?? '')
  const [periodSchedule, setPeriodSchedule] = useState('1-2=08:00-09:40\n3-4=10:00-11:40')
  const [earliest, setEarliest] = useState('08:00')
  const [latest, setLatest] = useState('22:00')
  const [lunchBreak, setLunchBreak] = useState('12:00-13:30')
  const [defaultReminder, setDefaultReminder] = useState('15')
  const setAuthState = useAuthStore.setState

  async function submit(event: FormEvent) {
    event.preventDefault()
    const updated = await api.updateMe({
      current_semester_start: semesterStart || null,
      preferences: {
        ...(user?.preferences ?? {}),
        period_schedule: parsePeriodSchedule(periodSchedule),
        earliest_study_time: earliest,
        latest_study_time: latest,
        lunch_break: lunchBreak,
        default_reminder_minutes: Number(defaultReminder),
      },
    })
    setAuthState({ user: updated })
  }

  return (
    <main className="page">
      <form className="sheet-form" onSubmit={submit}>
        <h2 className="sheet-form__title">
          <SlidersIcon className="icon" />
          <span>偏好设置</span>
        </h2>
        <label>
          学期开始日期
          <input type="date" value={semesterStart} onChange={(event) => setSemesterStart(event.target.value)} />
        </label>
        <label>
          作息时间表
          <textarea value={periodSchedule} onChange={(event) => setPeriodSchedule(event.target.value)} />
        </label>
        <label>
          最早学习时间
          <input type="time" value={earliest} onChange={(event) => setEarliest(event.target.value)} />
        </label>
        <label>
          最晚学习时间
          <input type="time" value={latest} onChange={(event) => setLatest(event.target.value)} />
        </label>
        <label>
          午休时段
          <input value={lunchBreak} onChange={(event) => setLunchBreak(event.target.value)} />
        </label>
        <label>
          默认提前提醒
          <select value={defaultReminder} onChange={(event) => setDefaultReminder(event.target.value)}>
            <option value="15">15分钟</option>
            <option value="30">30分钟</option>
            <option value="60">1小时</option>
          </select>
        </label>
        <button className="primary-button" type="submit">
          保存
        </button>
      </form>
    </main>
  )
}
