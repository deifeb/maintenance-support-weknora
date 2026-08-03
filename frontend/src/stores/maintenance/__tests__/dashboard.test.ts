import assert from 'node:assert/strict'
import test from 'node:test'

import {
  createDashboardApi,
  type DashboardSummary,
} from '../../../api/maintenance/dashboard.ts'
import type { MaintenanceResult } from '../../../api/maintenance/types.ts'
import { createDashboardState } from '../dashboard.ts'

const summary: DashboardSummary = {
  metrics: [
    {
      key: 'active_equipment_count',
      value: 3,
      trend: null,
    },
  ],
  recent_tasks: [],
  risk_items: [],
  risk_distribution: {
    LOW: 1,
    MEDIUM: 0,
    HIGH: 0,
    BLOCKING: 0,
  },
  generated_at: '2026-07-28T00:00:00Z',
}

function result(
  data: DashboardSummary,
): MaintenanceResult<DashboardSummary> {
  return {
    data,
    meta: {
      request_id: 'dashboard-request',
      tenant_id: 'tenant-a',
    },
  }
}

test('dashboard API requests one aggregate summary endpoint', async () => {
  const calls: string[] = []
  const api = createDashboardApi({
    async get<T>(path: string): Promise<MaintenanceResult<T>> {
      calls.push(path)
      return result(summary) as unknown as MaintenanceResult<T>
    },
  })

  const response = await api.getSummary()

  assert.deepEqual(calls, ['/v1/dashboard/summary'])
  assert.equal(response.data.generated_at, summary.generated_at)
})

test('refresh stores summary and clears a stale error', async () => {
  let shouldFail = true
  const state = createDashboardState(async () => {
    if (shouldFail) {
      throw {
        status: 503,
        message: 'Service unavailable',
      }
    }
    return result(summary)
  })

  await state.refresh()
  assert.equal(state.error.value?.code, 'MAINTENANCE_CLIENT_ERROR')

  shouldFail = false
  await state.refresh()

  assert.deepEqual(state.summary.value, summary)
  assert.equal(state.error.value, null)
  assert.equal(state.loading.value, false)
})

test('refresh normalizes failures and preserves last good summary', async () => {
  let callCount = 0
  const state = createDashboardState(async () => {
    callCount += 1

    if (callCount === 1) {
      return result(summary)
    }

    throw {
      status: 409,
      error: {
        code: 'DASHBOARD_CONFLICT',
        message: 'Dashboard changed',
      },
      meta: {
        request_id: 'request-conflict',
      },
    }
  })

  await state.refresh()
  await state.refresh()

  assert.deepEqual(state.summary.value, summary)
  assert.deepEqual(state.error.value, {
    status: 409,
    code: 'DASHBOARD_CONFLICT',
    message: 'Dashboard changed',
    request_id: 'request-conflict',
    retryable: false,
  })
})

test('concurrent refresh calls do not overlap', async () => {
  let resolveRequest: (
    value: MaintenanceResult<DashboardSummary>
  ) => void = () => undefined
  let callCount = 0
  const pending = new Promise<MaintenanceResult<DashboardSummary>>(
    (resolve) => {
      resolveRequest = resolve
    },
  )
  const state = createDashboardState(async () => {
    callCount += 1
    return pending
  })

  const first = state.refresh()
  const second = state.refresh()

  assert.equal(callCount, 1)
  assert.equal(state.loading.value, true)

  resolveRequest(result(summary))
  await Promise.all([first, second])

  assert.equal(callCount, 1)
  assert.equal(state.loading.value, false)
  assert.deepEqual(state.summary.value, summary)
})
