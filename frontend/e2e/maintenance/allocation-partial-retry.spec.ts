import { expect, test, type Page } from '@playwright/test'
import { readFile } from 'node:fs/promises'

import { storageStatePath } from './fixtures'

test.use({ storageState: storageStatePath('tenant-a-admin') })
test.setTimeout(120_000)

async function readAllocationFixture(): Promise<{
  plan_id: number
  line_ids: number[]
  failed_line_id: number
}> {
  const path = process.env.E2E_FIXTURE_MANIFEST_PATH
  if (!path) throw new Error('E2E_FIXTURE_MANIFEST_PATH is required')
  const manifest = JSON.parse(await readFile(path, 'utf8')) as {
    allocation?: { plan_id?: unknown; line_ids?: unknown; failed_line_id?: unknown }
  }
  const allocation = manifest.allocation
  if (
    !allocation
    || !Number.isInteger(allocation.plan_id)
    || !Array.isArray(allocation.line_ids)
    || allocation.line_ids.length < 2
    || !allocation.line_ids.every((id) => Number.isInteger(id))
    || !Number.isInteger(allocation.failed_line_id)
  ) throw new Error('allocation fixture manifest is incomplete')
  return allocation as { plan_id: number; line_ids: number[]; failed_line_id: number }
}

async function maintenanceFetch(
  page: Page,
  path: string,
  init?: RequestInit,
): Promise<{ status: number; payload: any }> {
  return page.evaluate(async ({ path, init }) => {
    const token = localStorage.getItem('weknora_token')
    const tenantId = localStorage.getItem('weknora_selected_tenant_id')
    const headers = new Headers(init?.headers)
    if (token) headers.set('Authorization', `Bearer ${token}`)
    if (tenantId) headers.set('X-Tenant-ID', tenantId)
    const response = await fetch(`/api/maintenance${path}`, {
      ...init,
      headers,
      credentials: 'include',
    })
    return { status: response.status, payload: await response.json() }
  }, { path, init })
}

test('executes a partial allocation and retries only the failed line', async ({ page }) => {
  const fixture = await readAllocationFixture()
  const allocationRequests: Array<{
    url: string
    method: string
    body: string | undefined
    idempotencyKey: string | undefined
  }> = []
  page.on('request', (request) => {
    if (!request.url().includes('/api/maintenance/v1/allocations/plans/')) return
    allocationRequests.push({
      url: request.url(),
      method: request.method(),
      body: request.postData(),
      idempotencyKey: request.headers()['idempotency-key'],
    })
  })

  await page.goto(`/platform/maintenance/inventory-gap/allocations/${fixture.plan_id}`)
  await expect(page.getByRole('heading', { name: `Allocation plan #${fixture.plan_id}` })).toBeVisible()

  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Execute' }).click()
  const summary = page.locator('.plan-execution-summary')
  await expect(summary).toBeVisible({ timeout: 30_000 })
  await expect(summary.locator('strong')).toHaveText('PARTIALLY_COMPLETED')

  const reservedRow = summary.locator('tbody tr[data-outcome="RESERVED"]')
  const conflictRow = summary.locator('tbody tr[data-outcome="CONFLICT"]')
  await expect(reservedRow).toHaveCount(1)
  await expect(conflictRow).toHaveCount(1)
  await expect(conflictRow).toContainText('yes')
  await expect(conflictRow).toContainText('retry')
  const successfulReservation = await reservedRow.locator('td').nth(2).innerText()
  const failedLineId = Number((await conflictRow.locator('td').first().innerText()).replace('#', ''))
  expect(failedLineId).toBe(fixture.failed_line_id)

  const retryButton = conflictRow.getByRole('button', { name: /^Retry$/i })
  await expect(retryButton).toHaveCount(1)
  await retryButton.click()

  await expect(summary.locator('strong')).toHaveText('COMPLETED', { timeout: 30_000 })
  const retryRequest = allocationRequests.find(
    (request) => request.method === 'POST' && request.url().endsWith('/retry'),
  )
  expect(retryRequest).toBeDefined()
  const retryBody = JSON.parse(retryRequest?.body ?? '{}') as { expected_version?: number; line_ids?: number[] }
  expect(retryBody.line_ids).toEqual([failedLineId])
  expect(retryRequest?.idempotencyKey).toBeTruthy()

  const detail = await maintenanceFetch(page, `/v1/allocations/plans/${fixture.plan_id}`)
  expect(detail.status).toBe(200)
  const lines = detail.payload.data?.lines ?? detail.payload.lines
  expect(lines).toHaveLength(2)
  expect(lines.every((line: { reservation_id: number | null }) => line.reservation_id !== null)).toBeTruthy()
  const successfulLine = lines.find((line: { reservation_id: number | null }) => successfulReservation.includes(`#${line.reservation_id}`))
  expect(successfulLine).toBeDefined()

  const replay = await maintenanceFetch(page, `/v1/allocations/plans/${fixture.plan_id}/retry`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'Idempotency-Key': retryRequest?.idempotencyKey ?? '',
    },
    body: JSON.stringify(retryBody),
  })
  expect(replay.status).toBe(200)
  const replayLines = replay.payload.data?.line_results ?? replay.payload.line_results
  expect(replayLines).toHaveLength(1)
  const replayDetail = await maintenanceFetch(page, `/v1/allocations/plans/${fixture.plan_id}`)
  const replayStoredLines = replayDetail.payload.data?.lines ?? replayDetail.payload.lines
  expect(replayStoredLines.map((line: { reservation_id: number | null }) => line.reservation_id))
    .toEqual(lines.map((line: { reservation_id: number | null }) => line.reservation_id))

  expect(allocationRequests.every((request) => !/[?&]tenant_id=/i.test(request.url))).toBeTruthy()
})
