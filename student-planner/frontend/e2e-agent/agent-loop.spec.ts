import { expect, test, type Page, type TestInfo } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

interface DbTask {
  id: string
  title: string
  description: string | null
  scheduled_date: string
  start_time: string
  end_time: string
  status: string
}

interface DbReminder {
  id: string
  target_type: string
  target_id: string
  remind_at: string
  advance_minutes: number
  status: string
}

interface DbSnapshot {
  username: string
  user: { id: string; username: string } | null
  tasks: DbTask[]
  reminders: DbReminder[]
  agent_logs: Array<Record<string, unknown>>
  messages: Array<Record<string, unknown>>
}

interface ReviewPlanTask {
  title: string
  scheduled_date: string
  start_time: string
  end_time: string
  description?: string | null
}

const backendDir = path.resolve(process.cwd(), '..')
const dbHelper = path.join(backendDir, 'scripts', 'agent_loop_e2e_db.py')
const python = process.env.AGENT_E2E_PYTHON ?? (process.platform === 'win32' ? 'C:\\Users\\Chen\\anaconda3\\python.exe' : 'python')
const databaseUrl = process.env.AGENT_E2E_DATABASE_URL ?? 'sqlite+aiosqlite:///./agent_loop_e2e.db'
const outputDir = path.resolve(process.cwd(), '..', '..', 'output', 'playwright')

function db(command: 'cleanup' | 'snapshot', username: string) {
  const output = execFileSync(python, [dbHelper, command, username], {
    cwd: backendDir,
    env: {
      ...process.env,
      SP_DATABASE_URL: databaseUrl,
      PYTHONIOENCODING: 'utf-8',
    },
    encoding: 'utf8',
  })
  return output.trim()
}

function cleanupUser(username: string) {
  db('cleanup', username)
}

function snapshot(username: string): DbSnapshot {
  const raw = db('snapshot', username)
  return JSON.parse(raw) as DbSnapshot
}

function scenarioUsername(scenario: string) {
  const stamp = Date.now().toString(36)
  return `agent_e2e_${scenario}_${stamp}`
}

async function installWebSocketRecorder(page: Page) {
  await page.addInitScript(() => {
    type RecordedEvent = { direction: 'client' | 'server'; at: string; payload: unknown }
    const events: RecordedEvent[] = []
    Object.defineProperty(window, '__agentE2eEvents', {
      value: events,
      configurable: true,
    })

    const NativeWebSocket = window.WebSocket
    class RecordingWebSocket extends NativeWebSocket {
      constructor(url: string | URL, protocols?: string | string[]) {
        super(url, protocols)
        this.addEventListener('message', (event) => {
          let payload: unknown = event.data
          if (typeof event.data === 'string') {
            try {
              payload = JSON.parse(event.data)
            } catch {
              payload = event.data
            }
          }
          events.push({ direction: 'server', at: new Date().toISOString(), payload })
        })

        const originalSend = this.send.bind(this)
        this.send = ((data: Parameters<WebSocket['send']>[0]) => {
          let payload: unknown = data
          if (typeof data === 'string') {
            try {
              payload = JSON.parse(data)
            } catch {
              payload = data
            }
          }
          events.push({ direction: 'client', at: new Date().toISOString(), payload })
          return originalSend(data)
        }) as WebSocket['send']
      }
    }
    window.WebSocket = RecordingWebSocket
  })
}

async function registerAndLogin(page: Page, username: string) {
  const password = 'agent-loop-e2e-password'
  await page.goto('/register')
  await page.getByLabel('用户名').fill(username)
  await page.getByLabel('密码').fill(password)
  await page.getByRole('button', { name: '注册' }).click()
  await expect(page.getByRole('heading', { name: '登录' })).toBeVisible()

  await page.getByLabel('用户名').fill(username)
  await page.getByLabel('密码').fill(password)
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page.getByLabel('输入消息')).toBeVisible()
}

async function sendMessage(page: Page, message: string) {
  await page.getByLabel('输入消息').fill(message)
  await page.getByRole('button', { name: '发送消息' }).click()
}

async function hasInlineAsk(page: Page) {
  const assistantMessages = page.locator('.message--assistant')
  const count = await assistantMessages.count()
  if (count === 0) {
    return false
  }
  const latest = (await assistantMessages.nth(count - 1).innerText()).trim()
  return /确认|请.*(告诉|补充|输入|确认)|需要.*(日期|时间|提醒|信息)|哪天|几点|是否|吗[？?]?|[？?]$/.test(latest)
}

async function waitForAskPrompt(page: Page, timeout = 30_000) {
  const start = Date.now()
  const askCard = page.locator('section[aria-label="需要确认"]:not(.ask-card--answered)').first()
  while (Date.now() - start < timeout) {
    if (await askCard.isVisible().catch(() => false)) {
      return true
    }
    if (await hasInlineAsk(page)) {
      return true
    }
    await page.waitForTimeout(1_000)
  }
  return false
}

async function answerVisibleAsk(page: Page, answer: string, timeout = 20_000) {
  const askCard = page.locator('section[aria-label="需要确认"]:not(.ask-card--answered)').first()
  try {
    await askCard.waitFor({ state: 'visible', timeout })
  } catch {
    if (!(await hasInlineAsk(page))) {
      return false
    }
    const mainInput = page.getByLabel('输入消息')
    if (await mainInput.isVisible().catch(() => false)) {
      await mainInput.fill(answer)
      await page.getByRole('button', { name: '发送消息' }).click()
      return true
    }
    return false
  }

  const answerInput = askCard.getByLabel('回复内容')
  if (await answerInput.isVisible().catch(() => false)) {
    await answerInput.fill(answer)
    await askCard.getByRole('button', { name: '提交' }).click()
    return true
  }

  const preferred = askCard.getByRole('button', { name: /^(确认|可以|确定|是)$/ }).first()
  if (await preferred.isVisible().catch(() => false)) {
    await preferred.click()
    return true
  }

  const firstButton = askCard.getByRole('button').first()
  if (await firstButton.isVisible().catch(() => false)) {
    await firstButton.click()
    return true
  }

  return false
}

async function waitForSnapshot(
  username: string,
  predicate: (snapshot: DbSnapshot) => boolean,
  options: { timeout?: number; interval?: number } = {},
) {
  const timeout = options.timeout ?? 120_000
  const interval = options.interval ?? 2_000
  const start = Date.now()
  let last = snapshot(username)
  while (Date.now() - start < timeout) {
    last = snapshot(username)
    if (predicate(last)) {
      return last
    }
    await new Promise((resolve) => setTimeout(resolve, interval))
  }
  throw new Error(`Timed out waiting for DB invariant. Last snapshot: ${JSON.stringify(last, null, 2)}`)
}

async function driveUntilDbInvariant(
  page: Page,
  username: string,
  responses: string[],
  predicate: (snapshot: DbSnapshot) => boolean,
) {
  let responseIndex = 0
  for (let attempt = 0; attempt < 8; attempt += 1) {
    const current = snapshot(username)
    if (predicate(current)) {
      return current
    }
    const answer = responses[Math.min(responseIndex, responses.length - 1)] ?? '确认'
    const answered = await answerVisibleAsk(page, answer, 15_000)
    if (answered) {
      responseIndex += 1
      continue
    }
    await page.waitForTimeout(2_000)
  }
  return waitForSnapshot(username, predicate)
}

async function waitForLatestReviewPlanTask(page: Page, timeout = 120_000): Promise<ReviewPlanTask> {
  const start = Date.now()
  while (Date.now() - start < timeout) {
    const task = await page.evaluate(() => {
      type RecordedEvent = { direction: 'client' | 'server'; payload: unknown }
      type Payload = { type?: unknown; data?: { tasks?: unknown } }
      const events = ((window as unknown as { __agentE2eEvents?: RecordedEvent[] }).__agentE2eEvents ?? []).filter(
        (event) => event.direction === 'server',
      )
      for (let index = events.length - 1; index >= 0; index -= 1) {
        const payload = events[index]!.payload as Payload
        if (payload?.type !== 'ask_user') continue
        const tasks = payload.data?.tasks
        if (!Array.isArray(tasks) || tasks.length === 0) continue
        const first = tasks[0] as Record<string, unknown>
        if (
          typeof first.title === 'string' &&
          typeof first.scheduled_date === 'string' &&
          typeof first.start_time === 'string' &&
          typeof first.end_time === 'string'
        ) {
          return {
            title: first.title,
            scheduled_date: first.scheduled_date,
            start_time: first.start_time,
            end_time: first.end_time,
            description: typeof first.description === 'string' ? first.description : null,
          }
        }
      }
      return null
    })
    if (task) {
      return task
    }
    await page.waitForTimeout(1_000)
  }
  throw new Error('Timed out waiting for review plan task')
}

async function createTaskFromBrowser(page: Page, body: Record<string, unknown>) {
  return page.evaluate(async (payload) => {
    const token = window.localStorage.getItem('student-planner-token')
    const response = await fetch('/api/tasks/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token ?? ''}`,
      },
      body: JSON.stringify(payload),
    })
    if (!response.ok) {
      throw new Error(await response.text())
    }
    return response.json()
  }, body)
}

function taskDurationMinutes(task: Pick<DbTask, 'start_time' | 'end_time'>) {
  const [startHour, startMinute] = task.start_time.split(':').map(Number)
  const [endHour, endMinute] = task.end_time.split(':').map(Number)
  return (endHour! * 60 + endMinute!) - (startHour! * 60 + startMinute!)
}

async function writeEvidence(
  page: Page,
  testInfo: TestInfo,
  scenario: string,
  username: string,
  dbSnapshot: DbSnapshot,
  assertions: Record<string, unknown>,
  extraEvidence: Record<string, unknown> = {},
) {
  fs.mkdirSync(outputDir, { recursive: true })
  const safeTitle = testInfo.title.replace(/[^\w.-]+/g, '-').replace(/^-|-$/g, '')
  const baseName = `agent-loop-e2e-${scenario}-${safeTitle}`
  const screenshotPath = path.join(outputDir, `${baseName}.png`)
  await page.screenshot({ path: screenshotPath, fullPage: true })
  const websocketEvents = await page.evaluate(() => {
    return (window as unknown as { __agentE2eEvents?: unknown[] }).__agentE2eEvents ?? []
  })
  const evidencePath = path.join(outputDir, `${baseName}.json`)
  fs.writeFileSync(
    evidencePath,
    JSON.stringify(
      {
        scenario,
        username,
        assertions,
        db: dbSnapshot,
        websocketEvents,
        screenshotPath,
        capturedAt: new Date().toISOString(),
        ...extraEvidence,
      },
      null,
      2,
    ),
    'utf8',
  )
  testInfo.attachments.push({ name: `${scenario} evidence`, path: evidencePath, contentType: 'application/json' })
}

test.describe('Agent Loop E2E', () => {
  test('creates a task with an integrated reminder', async ({ page }, testInfo) => {
    const username = scenarioUsername('create')
    cleanupUser(username)
    await installWebSocketRecorder(page)
    await registerAndLogin(page, username)

    await sendMessage(page, '请帮我创建一个任务：2026年7月26日下午3点到4点复习线性代数，提前30分钟提醒。')
    const dbSnapshot = await driveUntilDbInvariant(page, username, ['确认'], (state) => {
      const tasks = state.tasks.filter((task) => task.title.includes('线性代数'))
      if (tasks.length !== 1) return false
      const [task] = tasks
      const reminders = state.reminders.filter((reminder) => reminder.target_id === task.id)
      return (
        task.scheduled_date === '2026-07-26' &&
        task.start_time === '15:00' &&
        task.end_time === '16:00' &&
        reminders.length === 1 &&
        reminders[0]?.advance_minutes === 30 &&
        reminders[0]?.remind_at === '2026-07-26T14:30:00'
      )
    })

    const tasks = dbSnapshot.tasks.filter((task) => task.title.includes('线性代数'))
    expect(tasks).toHaveLength(1)
    const reminders = dbSnapshot.reminders.filter((reminder) => reminder.target_id === tasks[0]!.id)
    expect(reminders).toHaveLength(1)
    await writeEvidence(page, testInfo, 'create-task-reminder', username, dbSnapshot, {
      taskId: tasks[0]!.id,
      reminderId: reminders[0]!.id,
      expectedReminder: '2026-07-26T14:30:00',
    })
  })

  test('updates an existing task and rewrites the old reminder', async ({ page }, testInfo) => {
    const username = scenarioUsername('update')
    cleanupUser(username)
    await installWebSocketRecorder(page)
    await registerAndLogin(page, username)
    const seededTask = (await createTaskFromBrowser(page, {
      title: '线性代数复习',
      scheduled_date: '2026-07-26',
      start_time: '15:00',
      end_time: '16:00',
      reminder_advance_minutes: 30,
    })) as { id: string }

    await sendMessage(page, '把刚才那个线性代数复习任务改到2026年7月27日下午4点到5点，提前15分钟提醒。')
    const dbSnapshot = await driveUntilDbInvariant(page, username, ['确认'], (state) => {
      const matchingTasks = state.tasks.filter((task) => task.title.includes('线性代数'))
      if (matchingTasks.length !== 1) return false
      const [task] = matchingTasks
      const reminders = state.reminders.filter((reminder) => reminder.target_id === task.id)
      const hasOldReminder = state.reminders.some((reminder) => reminder.remind_at === '2026-07-26T14:30:00')
      return (
        task.id === seededTask.id &&
        task.scheduled_date === '2026-07-27' &&
        task.start_time === '16:00' &&
        task.end_time === '17:00' &&
        reminders.length === 1 &&
        reminders[0]?.advance_minutes === 15 &&
        reminders[0]?.remind_at === '2026-07-27T15:45:00' &&
        !hasOldReminder
      )
    })

    const matchingTasks = dbSnapshot.tasks.filter((task) => task.title.includes('线性代数'))
    expect(matchingTasks).toHaveLength(1)
    expect(dbSnapshot.reminders.filter((reminder) => reminder.target_id === seededTask.id)).toHaveLength(1)
    expect(dbSnapshot.reminders.some((reminder) => reminder.remind_at === '2026-07-26T14:30:00')).toBe(false)
    await writeEvidence(page, testInfo, 'update-task-reminder', username, dbSnapshot, {
      taskId: seededTask.id,
      expectedReminder: '2026-07-27T15:45:00',
      oldReminderRemoved: true,
    })
  })

  test('keeps one task stable across repeated task and reminder updates', async ({ page }, testInfo) => {
    const username = scenarioUsername('repeated')
    cleanupUser(username)
    await installWebSocketRecorder(page)
    await registerAndLogin(page, username)
    const seededTask = (await createTaskFromBrowser(page, {
      title: '概率论复习',
      scheduled_date: '2026-07-26',
      start_time: '15:00',
      end_time: '16:00',
      reminder_advance_minutes: 30,
    })) as { id: string }
    const seededSnapshot = snapshot(username)

    await sendMessage(page, '把概率论复习任务改到2026年7月27日下午4点到5点，提前15分钟提醒。')
    const afterFirstUpdate = await driveUntilDbInvariant(page, username, ['确认'], (state) => {
      const matchingTasks = state.tasks.filter((task) => task.title.includes('概率论'))
      if (matchingTasks.length !== 1) return false
      const [task] = matchingTasks
      const reminders = state.reminders.filter((reminder) => reminder.target_id === task.id)
      const hasSeedReminder = state.reminders.some((reminder) => reminder.remind_at === '2026-07-26T14:30:00')
      return (
        task.id === seededTask.id &&
        task.scheduled_date === '2026-07-27' &&
        task.start_time === '16:00' &&
        task.end_time === '17:00' &&
        reminders.length === 1 &&
        reminders[0]?.advance_minutes === 15 &&
        reminders[0]?.remind_at === '2026-07-27T15:45:00' &&
        !hasSeedReminder
      )
    })

    await sendMessage(page, '再把这个概率论复习任务改到2026年7月28日上午9点到10点，不提醒。')
    const afterSecondUpdate = await driveUntilDbInvariant(page, username, ['确认'], (state) => {
      const matchingTasks = state.tasks.filter((task) => task.title.includes('概率论'))
      if (matchingTasks.length !== 1) return false
      const [task] = matchingTasks
      const reminders = state.reminders.filter((reminder) => reminder.target_id === task.id)
      const hasAnyOldReminder = state.reminders.some((reminder) =>
        ['2026-07-26T14:30:00', '2026-07-27T15:45:00'].includes(reminder.remind_at),
      )
      return (
        task.id === seededTask.id &&
        task.scheduled_date === '2026-07-28' &&
        task.start_time === '09:00' &&
        task.end_time === '10:00' &&
        reminders.length === 0 &&
        !hasAnyOldReminder
      )
    })

    const matchingTasks = afterSecondUpdate.tasks.filter((task) => task.title.includes('概率论'))
    expect(matchingTasks).toHaveLength(1)
    expect(matchingTasks[0]!.id).toBe(seededTask.id)
    expect(afterSecondUpdate.reminders.filter((reminder) => reminder.target_id === seededTask.id)).toHaveLength(0)
    expect(
      afterSecondUpdate.reminders.some((reminder) =>
        ['2026-07-26T14:30:00', '2026-07-27T15:45:00'].includes(reminder.remind_at),
      ),
    ).toBe(false)

    await writeEvidence(
      page,
      testInfo,
      'repeated-task-reminder-updates',
      username,
      afterSecondUpdate,
      {
        taskId: seededTask.id,
        reusedSingleTask: true,
        finalReminderCount: 0,
        oldRemindersRemoved: true,
      },
      {
        snapshots: {
          seeded: seededSnapshot,
          afterFirstUpdate,
          afterSecondUpdate,
        },
      },
    )
  })

  test('recovers from missing task parameters before writing to the database', async ({ page }, testInfo) => {
    const username = scenarioUsername('missing')
    cleanupUser(username)
    await installWebSocketRecorder(page)
    await registerAndLogin(page, username)

    await sendMessage(page, '帮我创建一个复习英语的任务。')
    const dbSnapshot = await driveUntilDbInvariant(
      page,
      username,
      ['2026年7月28日晚上7点到8点复习英语，提前15分钟提醒。', '确认'],
      (state) => {
        const tasks = state.tasks.filter((task) => task.title.includes('英语'))
        if (tasks.length !== 1) return false
        const [task] = tasks
        const reminders = state.reminders.filter((reminder) => reminder.target_id === task.id)
        return (
          task.scheduled_date === '2026-07-28' &&
          task.start_time === '19:00' &&
          task.end_time === '20:00' &&
          reminders.length === 1 &&
          reminders[0]?.advance_minutes === 15 &&
          reminders[0]?.remind_at === '2026-07-28T18:45:00'
        )
      },
    )

    const tasks = dbSnapshot.tasks.filter((task) => task.title.includes('英语'))
    expect(tasks).toHaveLength(1)
    expect(dbSnapshot.reminders.filter((reminder) => reminder.target_id === tasks[0]!.id)).toHaveLength(1)
    await writeEvidence(page, testInfo, 'missing-params-recovery', username, dbSnapshot, {
      taskId: tasks[0]!.id,
      expectedReminder: '2026-07-28T18:45:00',
    })
  })

  test('asks for missing exam details before decomposing a vague study plan request', async ({ page }, testInfo) => {
    const username = scenarioUsername('studyplan-missing')
    cleanupUser(username)
    await installWebSocketRecorder(page)
    await registerAndLogin(page, username)

    await sendMessage(page, '下周有一门考试，帮我拆一下复习任务。')
    const askedForMoreInfo = await waitForAskPrompt(page)
    const dbSnapshot = snapshot(username)

    expect(askedForMoreInfo).toBe(true)
    expect(dbSnapshot.tasks).toHaveLength(0)
    expect(dbSnapshot.reminders).toHaveLength(0)
    await writeEvidence(page, testInfo, 'study-plan-missing-details', username, dbSnapshot, {
      askedForMoreInfo,
      taskCount: dbSnapshot.tasks.length,
      reminderCount: dbSnapshot.reminders.length,
    })
  })

  test('generates a study plan and writes confirmed review tasks', async ({ page }, testInfo) => {
    const username = scenarioUsername('studyplan')
    cleanupUser(username)
    await installWebSocketRecorder(page)
    await registerAndLogin(page, username)

    const studyContextAnswer = '范围 Unit1-6，听力和写作薄弱，目标80分，每天最多2小时。'
    await sendMessage(page, '下周四（2026-06-11）有大学英语3考试，帮我做一个复习计划。')
    const dbSnapshot = await driveUntilDbInvariant(page, username, ['确认', studyContextAnswer, '确认', '确认'], (state) => {
      const toolNames = state.agent_logs.map((log) => String(log.tool_called ?? ''))
      const englishTasks = state.tasks.filter((task) => {
        const haystack = `${task.title}\n${task.description ?? ''}`
        return /大学英语|英语/.test(haystack)
      })
      const contextualTasks = englishTasks.filter((task) => {
        const haystack = `${task.title}\n${task.description ?? ''}`
        return /Unit\s*1|1-6|听力|写作|薄弱|80/.test(haystack)
      })
      return (
        toolNames.includes('get_free_slots') &&
        toolNames.includes('create_study_plan') &&
        toolNames.includes('create_task') &&
        englishTasks.length >= 2 &&
        contextualTasks.length >= 2 &&
        englishTasks.every((task) => {
          return (
            task.scheduled_date >= '2026-06-02' &&
            task.scheduled_date <= '2026-06-10' &&
            /^([01]\d|2[0-3]):[0-5]\d$/.test(task.start_time) &&
            /^([01]\d|2[0-3]):[0-5]\d$/.test(task.end_time)
          )
        })
      )
    })

    const toolNames = dbSnapshot.agent_logs.map((log) => String(log.tool_called ?? ''))
    const englishTasks = dbSnapshot.tasks.filter((task) => /大学英语|英语/.test(`${task.title}\n${task.description ?? ''}`))
    const contextualTasks = englishTasks.filter((task) => {
      const haystack = `${task.title}\n${task.description ?? ''}`
      return /Unit\s*1|1-6|听力|写作|薄弱|80/.test(haystack)
    })
    expect(toolNames).toContain('get_free_slots')
    expect(toolNames).toContain('create_study_plan')
    expect(toolNames).toContain('create_task')
    expect(englishTasks.length).toBeGreaterThanOrEqual(2)
    expect(contextualTasks.length).toBeGreaterThanOrEqual(2)
    expect(
      englishTasks.every((task) => task.scheduled_date >= '2026-06-02' && task.scheduled_date <= '2026-06-10'),
    ).toBe(true)
    await writeEvidence(page, testInfo, 'study-plan-confirmed-write', username, dbSnapshot, {
      taskCount: englishTasks.length,
      taskIds: englishTasks.map((task) => task.id),
      contextualTaskIds: contextualTasks.map((task) => task.id),
      studyContextHints: ['Unit1-6', '听力', '写作', '目标80分', '每天最多2小时'],
      toolSequence: toolNames,
      expectedExamDate: '2026-06-11',
    })
  })

  test('generates an assignment report plan and writes confirmed staged tasks', async ({ page }, testInfo) => {
    const username = scenarioUsername('workplan')
    cleanupUser(username)
    await installWebSocketRecorder(page)
    await registerAndLogin(page, username)

    const workContextAnswer = '需要5页PDF，包括实验结果和参考文献，现在还没开始，每天最多2小时。'
    await sendMessage(page, '2026-06-12 要交机器学习报告，帮我拆成任务。')
    const dbSnapshot = await driveUntilDbInvariant(page, username, [workContextAnswer, '确认', '确认'], (state) => {
      const toolNames = state.agent_logs.map((log) => String(log.tool_called ?? ''))
      const reportTasks = state.tasks.filter((task) => {
        const haystack = `${task.title}\n${task.description ?? ''}`
        return haystack.includes('机器学习报告')
      })
      const stagedTasks = reportTasks.filter((task) => {
        const haystack = `${task.title}\n${task.description ?? ''}`
        return /整理|资料|提纲|初稿|修改|提交|参考文献|实验结果/.test(haystack)
      })
      return (
        toolNames.includes('get_free_slots') &&
        toolNames.includes('create_work_plan') &&
        toolNames.includes('create_task') &&
        reportTasks.length >= 3 &&
        stagedTasks.length >= 3 &&
        reportTasks.every((task) => {
          return task.scheduled_date <= '2026-06-11' && taskDurationMinutes(task) <= 120
        })
      )
    })

    const toolNames = dbSnapshot.agent_logs.map((log) => String(log.tool_called ?? ''))
    const reportTasks = dbSnapshot.tasks.filter((task) => `${task.title}\n${task.description ?? ''}`.includes('机器学习报告'))
    expect(toolNames).toContain('get_free_slots')
    expect(toolNames).toContain('create_work_plan')
    expect(toolNames).toContain('create_task')
    expect(reportTasks.length).toBeGreaterThanOrEqual(3)
    expect(reportTasks.every((task) => task.scheduled_date <= '2026-06-11')).toBe(true)
    expect(reportTasks.every((task) => taskDurationMinutes(task) <= 120)).toBe(true)
    await writeEvidence(page, testInfo, 'work-plan-confirmed-write', username, dbSnapshot, {
      taskCount: reportTasks.length,
      taskIds: reportTasks.map((task) => task.id),
      workContextHints: ['5页PDF', '实验结果', '参考文献', '每天最多2小时'],
      toolSequence: toolNames,
      expectedDueDate: '2026-06-12',
    })
  })

  test('reschedules a confirmed plan task when the original slot conflicts before write', async ({ page }, testInfo) => {
    const username = scenarioUsername('reschedule')
    cleanupUser(username)
    await installWebSocketRecorder(page)
    await registerAndLogin(page, username)

    const workContextAnswer = '需要5页PDF，包括实验结果和参考文献，现在还没开始，每天最多2小时。'
    await sendMessage(page, '2026-06-12 要交机器学习报告，帮我拆成任务。')
    await expect.poll(() => waitForAskPrompt(page, 1_000), { timeout: 30_000 }).toBe(true)
    expect(await answerVisibleAsk(page, workContextAnswer)).toBe(true)

    const plannedTask = await waitForLatestReviewPlanTask(page)
    const blocker = (await createTaskFromBrowser(page, {
      title: '临时占用 - 主动重排 E2E',
      scheduled_date: plannedTask.scheduled_date,
      start_time: plannedTask.start_time,
      end_time: plannedTask.end_time,
    })) as { id: string }

    expect(await answerVisibleAsk(page, '确认')).toBe(true)
    const dbSnapshot = await waitForSnapshot(username, (state) => {
      const toolNames = state.agent_logs.map((log) => String(log.tool_called ?? ''))
      const firstTaskMatches = state.tasks.filter((task) => task.title === plannedTask.title)
      const hasConflictResult = state.agent_logs.some((log) => String(log.tool_result ?? '').includes('Time conflict'))
      const hasAutoRescheduleMessage = state.messages.some((message) => {
        return String(message.role ?? '') === 'assistant' && String(message.content ?? '').includes('自动重排')
      })
      const hasRescheduledTask = firstTaskMatches.some((task) => {
        return (
          task.scheduled_date !== plannedTask.scheduled_date ||
          task.start_time !== plannedTask.start_time ||
          task.end_time !== plannedTask.end_time
        )
      })
      return (
        toolNames.filter((name) => name === 'get_free_slots').length >= 2 &&
        toolNames.filter((name) => name === 'create_task').length >= 2 &&
        hasConflictResult &&
        hasAutoRescheduleMessage &&
        hasRescheduledTask
      )
    })

    const toolNames = dbSnapshot.agent_logs.map((log) => String(log.tool_called ?? ''))
    const firstTaskMatches = dbSnapshot.tasks.filter((task) => task.title === plannedTask.title)
    const rescheduledTask = firstTaskMatches.find((task) => {
      return (
        task.scheduled_date !== plannedTask.scheduled_date ||
        task.start_time !== plannedTask.start_time ||
        task.end_time !== plannedTask.end_time
      )
    })
    expect(rescheduledTask).toBeTruthy()
    expect(dbSnapshot.tasks.some((task) => task.id === blocker.id)).toBe(true)
    expect(
      dbSnapshot.agent_logs.some((log) => {
        return String(log.tool_called ?? '') === 'create_task' && String(log.tool_result ?? '').includes('Time conflict')
      }),
    ).toBe(true)
    expect(toolNames.filter((name) => name === 'get_free_slots').length).toBeGreaterThanOrEqual(2)
    await writeEvidence(page, testInfo, 'plan-write-active-reschedule', username, dbSnapshot, {
      plannedTask,
      blockerId: blocker.id,
      rescheduledTask,
      toolSequence: toolNames,
    })
  })

  test('generates a multi-exam study plan with tasks for both exams', async ({ page }, testInfo) => {
    const username = scenarioUsername('multiexam')
    cleanupUser(username)
    await installWebSocketRecorder(page)
    await registerAndLogin(page, username)

    await sendMessage(
      page,
      '2026-06-10 有高等数学考试，范围第1-5章；2026-06-12 有大学英语3考试，范围 Unit1-6，听力薄弱。帮我做复习计划，每天最多2小时。',
    )
    const dbSnapshot = await driveUntilDbInvariant(page, username, ['确认', '确认', '确认'], (state) => {
      const toolNames = state.agent_logs.map((log) => String(log.tool_called ?? ''))
      const mathTasks = state.tasks.filter((task) => /高等数学|高数/.test(`${task.title}\n${task.description ?? ''}`))
      const englishTasks = state.tasks.filter((task) => /大学英语|英语|Unit/.test(`${task.title}\n${task.description ?? ''}`))
      return (
        toolNames.includes('get_free_slots') &&
        toolNames.includes('create_study_plan') &&
        toolNames.includes('create_task') &&
        mathTasks.length >= 1 &&
        englishTasks.length >= 1 &&
        state.tasks.every((task) => task.scheduled_date <= '2026-06-11')
      )
    })

    const toolNames = dbSnapshot.agent_logs.map((log) => String(log.tool_called ?? ''))
    const mathTasks = dbSnapshot.tasks.filter((task) => /高等数学|高数/.test(`${task.title}\n${task.description ?? ''}`))
    const englishTasks = dbSnapshot.tasks.filter((task) => /大学英语|英语|Unit/.test(`${task.title}\n${task.description ?? ''}`))
    expect(toolNames).toContain('create_study_plan')
    expect(mathTasks.length).toBeGreaterThanOrEqual(1)
    expect(englishTasks.length).toBeGreaterThanOrEqual(1)
    await writeEvidence(page, testInfo, 'multi-exam-study-plan', username, dbSnapshot, {
      mathTaskIds: mathTasks.map((task) => task.id),
      englishTaskIds: englishTasks.map((task) => task.id),
      toolSequence: toolNames,
      expectedExamDates: ['2026-06-10', '2026-06-12'],
    })
  })

  test('adjusts an existing assignment plan to a lower daily limit', async ({ page }, testInfo) => {
    const username = scenarioUsername('planadjust')
    cleanupUser(username)
    await installWebSocketRecorder(page)
    await registerAndLogin(page, username)
    const firstTask = (await createTaskFromBrowser(page, {
      title: '机器学习报告 - 完成初稿',
      scheduled_date: '2026-06-09',
      start_time: '09:00',
      end_time: '11:00',
    })) as { id: string }
    const secondTask = (await createTaskFromBrowser(page, {
      title: '机器学习报告 - 修改完善',
      scheduled_date: '2026-06-10',
      start_time: '14:00',
      end_time: '16:00',
    })) as { id: string }

    await sendMessage(page, '机器学习报告计划太满了，改成每天最多1小时。')
    const dbSnapshot = await driveUntilDbInvariant(page, username, ['确认'], (state) => {
      const toolNames = state.agent_logs.map((log) => String(log.tool_called ?? ''))
      const reportTasks = state.tasks.filter((task) => [firstTask.id, secondTask.id].includes(task.id))
      return (
        toolNames.includes('list_tasks') &&
        toolNames.includes('update_task') &&
        reportTasks.length === 2 &&
        reportTasks.every((task) => taskDurationMinutes(task) <= 60)
      )
    })

    const toolNames = dbSnapshot.agent_logs.map((log) => String(log.tool_called ?? ''))
    const reportTasks = dbSnapshot.tasks.filter((task) => [firstTask.id, secondTask.id].includes(task.id))
    expect(toolNames).toContain('list_tasks')
    expect(toolNames).toContain('update_task')
    expect(reportTasks).toHaveLength(2)
    expect(reportTasks.every((task) => taskDurationMinutes(task) <= 60)).toBe(true)
    await writeEvidence(page, testInfo, 'plan-adjustment-daily-limit', username, dbSnapshot, {
      taskIds: [firstTask.id, secondTask.id],
      durations: reportTasks.map((task) => ({ id: task.id, durationMinutes: taskDurationMinutes(task) })),
      dailyLimitMinutes: 60,
      toolSequence: toolNames,
    })
  })
})
