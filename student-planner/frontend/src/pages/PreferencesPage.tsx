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
    <main className="page preferences-page">
      <section className="settings-intro">
        <div>
          <span className="eyebrow">Planning</span>
          <h1>规划规则</h1>
          <p>学习窗口、课节时间和提醒默认值会进入空闲时间计算。</p>
        </div>
        <div className="settings-summary" aria-label="规划规则摘要">
          <div>
            <span>学习窗口</span>
            <strong>{earliest}-{latest}</strong>
          </div>
          <div>
            <span>默认提醒</span>
            <strong>{defaultReminder}分钟</strong>
          </div>
        </div>
      </section>
      <form className="settings-form settings-form--compact" onSubmit={submit}>
        <details className="settings-accordion">
          <summary>
            <SlidersIcon className="icon" />
            <div>
              <h2>学期与空闲时间</h2>
              <p>{semesterStart || '未设置'} · {earliest}-{latest}</p>
            </div>
          </summary>
          <div className="settings-accordion__body">
            <label className="settings-row">
              <span>
                <strong>学期开始</strong>
                <small>课程有效周从这里开始计算</small>
              </span>
              <input type="date" value={semesterStart} onChange={(event) => setSemesterStart(event.target.value)} />
            </label>
            <div className="settings-row settings-row--split">
              <span>
                <strong>学习窗口</strong>
                <small>Agent 只在这段时间内排学习任务</small>
              </span>
              <div className="time-pair">
                <label>
                  <span>最早</span>
                  <input type="time" value={earliest} onChange={(event) => setEarliest(event.target.value)} />
                </label>
                <label>
                  <span>最晚</span>
                  <input type="time" value={latest} onChange={(event) => setLatest(event.target.value)} />
                </label>
              </div>
            </div>
            <label className="settings-row">
              <span>
                <strong>午休时段</strong>
                <small>这段时间默认避开</small>
              </span>
              <input value={lunchBreak} onChange={(event) => setLunchBreak(event.target.value)} />
            </label>
          </div>
        </details>

        <details className="settings-accordion">
          <summary>
            <SlidersIcon className="icon" />
            <div>
              <h2>课节与提醒</h2>
              <p>默认提前 {defaultReminder} 分钟 · {periodSchedule.split('\n').filter(Boolean).length} 条课节</p>
            </div>
          </summary>
          <div className="settings-accordion__body">
            <label className="settings-row settings-row--stacked">
              <span>
                <strong>作息时间表</strong>
                <small>一行一个课节映射，例如 1-2=08:00-09:40</small>
              </span>
              <textarea value={periodSchedule} onChange={(event) => setPeriodSchedule(event.target.value)} />
            </label>
            <label className="settings-row">
              <span>
                <strong>默认提前提醒</strong>
                <small>新任务默认使用这个提醒时间</small>
              </span>
              <select value={defaultReminder} onChange={(event) => setDefaultReminder(event.target.value)}>
                <option value="15">15分钟</option>
                <option value="30">30分钟</option>
                <option value="60">1小时</option>
              </select>
            </label>
          </div>
        </details>

        <button className="primary-button settings-save" type="submit">
          保存
        </button>
      </form>
    </main>
  )
}
