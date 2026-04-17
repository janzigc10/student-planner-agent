import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '../api/client'
import { eventsForDate, useCalendarStore } from './calendarStore'

describe('calendar events', () => {
  it('combines matching courses and tasks sorted by start time', () => {
    const events = eventsForDate(
      '2026-03-30',
      [
        {
          id: 'course-1',
          user_id: 'user-1',
          name: '高等数学',
          teacher: null,
          location: '教学楼A301',
          weekday: 1,
          start_time: '08:00',
          end_time: '09:40',
          week_start: 1,
          week_end: 16,
        },
      ],
      [
        {
          id: 'task-1',
          user_id: 'user-1',
          exam_id: null,
          title: '复习线代',
          description: '第1-3章',
          scheduled_date: '2026-03-30',
          start_time: '10:00',
          end_time: '12:00',
          status: 'pending',
        },
      ],
    )

    expect(events.map((event) => event.title)).toEqual(['高等数学', '复习线代'])
  })
})

describe('calendar date shifting', () => {
  beforeEach(() => {
    vi.spyOn(api, 'listCourses').mockResolvedValue([])
    vi.spyOn(api, 'listTasks').mockResolvedValue([])
    useCalendarStore.setState({
      currentDate: '2026-03-30',
      courses: [],
      tasks: [],
      isLoading: false,
      error: null,
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('moves to the next day once when shifting forward by one day', () => {
    useCalendarStore.getState().shiftDate(1)

    expect(useCalendarStore.getState().currentDate).toBe('2026-03-31')
  })

  it('moves to the previous day once when shifting backward by one day', () => {
    useCalendarStore.getState().shiftDate(-1)

    expect(useCalendarStore.getState().currentDate).toBe('2026-03-29')
  })
})
