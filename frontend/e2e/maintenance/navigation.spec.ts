import { expect, test } from '@playwright/test'

import { storageStatePath } from './fixtures'

test.use({ storageState: storageStatePath('tenant-a-viewer') })

test('viewer reaches the maintenance shell through Vite and the proxy', async ({ page }) => {
  await page.goto('/platform/maintenance/')

  await expect(page).toHaveURL(/\/platform\/maintenance\/dashboard$/)
  await expect(page.locator('main.maintenance-shell')).toBeVisible()
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
})

test('viewer can navigate the public maintenance workspaces', async ({ page }) => {
  const routes = [
    '/platform/maintenance/master-data',
    '/platform/maintenance/scenarios',
    '/platform/maintenance/inventory-gap',
    '/platform/maintenance/reports',
  ]

  for (const route of routes) {
    await page.goto(route)
    await expect(page).toHaveURL(new RegExp(`${route.replaceAll('/', '\\/')}$`))
    await expect(page.locator('main.maintenance-shell')).toBeVisible()
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  }
})
