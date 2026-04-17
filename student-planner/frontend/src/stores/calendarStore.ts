import { create } from 'zustand'

import { api } from '../api/client'
import type { Course, Task } from '../types/api'

export type CalendarEvent =
  | { kind: 'course'; id: string; title: string; detail: string; start_time: string; end_time: string; source: Course }
  | { kind: 'task'; id: string; title: string; detail: string; start_time: string; end_time: string; source: Task }

function weekdayForDate(date: string) {
  const day = new Date(`${date}T00:00:00`).getDay()
  return day === 0 ? 7 : day
}

export function eventsForDate(date: string, courses: Course[], tasks: Task[]): CalendarEvent[] {
  const weekday = weekdayForDate(date)
  return [
    ...courses
      .filter((course) => course.weekday === weekday)
      .map((course) => ({
        kind: 'course' as const,
        id: course.id,
        title: course.name,
        detail: course.location ?? course.teacher ?? '',
        start_time: course.start_time,
        end_time: course.end_time,
        source: course,
      })),
    ...tasks
      .filter((task) => task.scheduled_date === date)
      .map((task) => ({
        kind: 'task' as const,
        id: task.id,
        title: task.title,
        detail: task.description ?? task.status,
        start_time: task.start_time,
        end_time: task.end_time,
        source: task,
      })),
  ].sort((left, right) => left.start_time.localeCompare(right.start_time))
}

function toDateString(date: Date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

interface CalendarStore {
  currentDate: string
  courses: Course[]
  tasks: Task[]
  isLoading: boolean
  error: string | null
  setCurrentDate: (date: string) => void
  shiftDate: (days: number) => void
  load: () => Promise<void>
  completeTask: (taskId: string) => Promise<void>
  createTask: (body: Parameters<typeof api.createTask>[0]) => Promise<void>
}

export const useCalendarStore = create<CalendarStore>((set, get) => ({
  currentDate: toDateString(new Date()),
  courses: [],
  tasks: [],
  isLoading: false,
  error: null,
  setCurrentDate(date) {
    set({ currentDate: date })
  },
  shiftDate(days) {
    const next = new Date(`${get().currentDate}T00:00:00`)
    next.setDate(next.getDate() + days)
    set({ currentDate: toDateString(next) })
    void get().load()
  },
  async load() {
    set({ isLoading: true, error: null })
    try {
      const { currentDate } = get()
      const [courses, tasks] = await Promise.all([api.listCourses(), api.listTasks(currentDate, currentDate)])
      set({ courses, tasks, isLoading: false })
    } catch (error) {
      set({ error: error instanceof Error ? error.message : '加载日历失败', isLoading: false })
    }
  },
  async completeTask(taskId) {
    const updated = await api.updateTask(taskId, { status: 'completed' })
    set((state) => ({ tasks: state.tasks.map((task) => (task.id === taskId ? updated : task)) }))
  },
  async createTask(body) {
    try {
      const task = await api.createTask(body)
      set((state) => ({ tasks: [...state.tasks, task], error: null }))
    } catch (error) {
      set({ error: error instanceof Error ? error.message : '新增任务失败' })
    }
  },
}))
