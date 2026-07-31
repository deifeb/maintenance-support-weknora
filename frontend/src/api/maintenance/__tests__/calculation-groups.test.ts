import assert from 'node:assert/strict'
import test from 'node:test'

import {
  createCalculationGroupApi,
  type CalculationGroupCreateRequest,
} from '../calculation-groups.ts'
import { createRecommendationApi } from '../model-recommendations.ts'
import type { MaintenanceResult } from '../types.ts'

interface CapturedCall {
  method: string
  path: string
  body?: unknown
  config?: unknown
}

function result<T>(data: T): MaintenanceResult<T> {
  return {
    data,
    meta: {
      request_id: 'request-a',
      tenant_id: 'tenant-a',
    },
  }
}

function fakeClient(calls: CapturedCall[]) {
  return {
    async get<T>(path: string): Promise<MaintenanceResult<T>> {
      calls.push({ method: 'GET', path })
      return result({} as T)
    },
    async post<T>(
      path: string,
      body: unknown,
      config?: unknown,
    ): Promise<MaintenanceResult<T>> {
      calls.push({
        method: 'POST',
        path,
        body,
        config,
      })
      return result({} as T)
    },
  }
}

test('group API uses exact paths and idempotency headers', async () => {
  const calls: CapturedCall[] = []
  const api = createCalculationGroupApi(fakeClient(calls))
  const request: CalculationGroupCreateRequest = {
    scenario_version_id: 7,
    primary_candidate_key: 'WEIBULL:ANALYTICAL',
    selected_candidate_keys: [
      'WEIBULL:ANALYTICAL',
    ],
    random_seed: 20260723,
  }

  await api.create(request, 'group-key')
  await api.retryFailed(9, 'retry-key')
  await api.cancelRunning(9, 'cancel-key')
  await api.getEvents(9, 14)

  assert.equal(
    calls[0]?.path,
    '/v1/demand/calculation-groups',
  )
  assert.equal(
    calls[1]?.path,
    '/v1/demand/calculation-groups/9/retry-failed',
  )
  assert.equal(
    calls[2]?.path,
    '/v1/demand/calculation-groups/9/cancel-running',
  )
  assert.equal(
    calls[3]?.path,
    (
      '/v1/demand/calculation-groups/9/'
      + 'events?after_sequence=14'
    ),
  )
  assert.deepEqual(
    (
      calls[0]?.config as {
        headers: Record<string, string>
      }
    ).headers,
    { 'Idempotency-Key': 'group-key' },
  )
  assert.equal(
    JSON.stringify(calls).includes('tenant'),
    false,
  )
})

test('recommendation API sends only the scenario version', async () => {
  const calls: CapturedCall[] = []
  const api = createRecommendationApi(fakeClient(calls))

  await api.recommend(17)

  assert.deepEqual(calls, [{
    method: 'POST',
    path: '/v1/demand/model-recommendations',
    body: { scenario_version_id: 17 },
    config: undefined,
  }])
})

test('decimal values remain strings in group payloads', () => {
  const serialized = JSON.parse(JSON.stringify({
    progress_percent: '12.500000',
    original_quantity: '9007199254740993.125000',
  })) as Record<string, unknown>

  assert.equal(serialized.progress_percent, '12.500000')
  assert.equal(
    serialized.original_quantity,
    '9007199254740993.125000',
  )
})
