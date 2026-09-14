import { expect, test } from '@playwright/test'

import { storageStatePath } from './fixtures'

test.describe('tenant-scoped maintenance data', () => {
  test.describe('tenant-a viewer', () => {
    test.use({ storageState: storageStatePath('tenant-a-viewer') })

    test('loads only through the current authenticated scope', async ({ page }) => {
      const maintenanceRequests: string[] = []
      page.on('request', (request) => {
        if (request.url().includes('/api/maintenance')) maintenanceRequests.push(request.url())
      })

      await page.goto('/platform/maintenance/master-data?resource=equipmentModels')
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      await expect(page.locator('table')).toBeVisible()

      expect(maintenanceRequests.length).toBeGreaterThan(0)
      for (const requestUrl of maintenanceRequests) {
        expect(requestUrl).not.toMatch(/[?&]tenant_id=/i)
      }
    })
  })

  test.describe('tenant-b admin', () => {
    test.use({ storageState: storageStatePath('tenant-b-admin') })

    test('receives an independent scoped page', async ({ page }) => {
      await page.goto('/platform/maintenance/master-data?resource=equipmentModels')
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      await expect(page.locator('table')).toBeVisible()
    })
  })
})
