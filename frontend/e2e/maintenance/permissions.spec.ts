import { expect, test } from '@playwright/test'

import { storageStatePath } from './fixtures'

test.describe('viewer permissions', () => {
  test.use({ storageState: storageStatePath('tenant-a-viewer') })

  test('viewer sees scenarios without creation controls', async ({ page }) => {
    await page.goto('/platform/maintenance/scenarios')

    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await expect(page.getByRole('button', { name: /新建情景|create scenario/i })).toHaveCount(0)
  })
})

test.describe('contributor permissions', () => {
  test.use({ storageState: storageStatePath('tenant-a-contributor') })

  test('contributor can start a scenario draft', async ({ page }) => {
    await page.goto('/platform/maintenance/scenarios')

    await expect(page.getByRole('button', { name: /新建情景|create scenario/i })).toBeVisible()
  })
})
