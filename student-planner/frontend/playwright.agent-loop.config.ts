import { defineConfig, devices } from '@playwright/test'

const backendPort = Number(process.env.AGENT_E2E_BACKEND_PORT ?? 8011)
const frontendPort = Number(process.env.AGENT_E2E_FRONTEND_PORT ?? 5178)
const backendOrigin = `http://127.0.0.1:${backendPort}`
const frontendOrigin = `http://127.0.0.1:${frontendPort}`
const defaultWindowsPython = 'C:\\Users\\Chen\\anaconda3\\python.exe'
const python = process.env.AGENT_E2E_PYTHON ?? (process.platform === 'win32' ? defaultWindowsPython : 'python')
const databaseUrl = process.env.AGENT_E2E_DATABASE_URL ?? 'sqlite+aiosqlite:///./agent_loop_e2e.db'

function quote(value: string) {
  return value.includes(' ') ? `"${value}"` : value
}

export default defineConfig({
  testDir: './e2e-agent',
  timeout: 150_000,
  expect: {
    timeout: 20_000,
  },
  fullyParallel: false,
  workers: 1,
  webServer: [
    {
      command: `${quote(python)} scripts/start_agent_e2e_backend.py --host 127.0.0.1 --port ${backendPort}`,
      cwd: '..',
      url: `${backendOrigin}/health`,
      timeout: 120_000,
      reuseExistingServer: !process.env.CI,
      env: {
        ...process.env,
        SP_DATABASE_URL: databaseUrl,
        PYTHONIOENCODING: 'utf-8',
      },
    },
    {
      command: `node ./node_modules/vite/bin/vite.js --host 127.0.0.1 --port ${frontendPort}`,
      url: frontendOrigin,
      timeout: 120_000,
      reuseExistingServer: !process.env.CI,
      env: {
        ...process.env,
        STUDENT_PLANNER_BACKEND_ORIGIN: backendOrigin,
      },
    },
  ],
  use: {
    baseURL: frontendOrigin,
    ...devices['Pixel 5'],
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
})
