import { expect, test } from '@playwright/test'

test('loads the mobile app auth entry', async ({ page }) => {
  await page.goto('/chat')
  await expect(page.getByRole('heading', { name: '登录' })).toBeVisible()
})
