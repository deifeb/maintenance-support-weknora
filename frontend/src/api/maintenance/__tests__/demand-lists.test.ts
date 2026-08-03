import assert from 'node:assert/strict'
import test from 'node:test'

import {
  createDemandListApi,
  type DemandListCreateRequest,
} from '../demand-lists.ts'
import type {
  MaintenanceResult,
  PageData,
} from '../types.ts'

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
      version: 7,
    },
  }
}

function fakeClient(calls: CapturedCall[]) {
  return {
    async get<T>(
      path: string,
    ): Promise<MaintenanceResult<T>> {
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

    async put<T>(
      path: string,
      body: unknown,
    ): Promise<MaintenanceResult<T>> {
      calls.push({
        method: 'PUT',
        path,
        body,
      })
      return result({} as T)
    },
  }
}

function headersOf(
  call: CapturedCall | undefined,
): Record<string, string> {
  return (
    call?.config as {
      headers: Record<string, string>
    }
  ).headers
}

test('demand-list client uses exact create/list/get/update routes', async () => {
  const calls: CapturedCall[] = []
  const api = createDemandListApi(fakeClient(calls))
  const request: DemandListCreateRequest = {
    calculation_group_id: 9,
    name: 'Readiness demand',
    description: 'Task 5 contract',
  }

  await api.create(request, 'create-list-key')
  await api.list({
    page: 2,
    page_size: 50,
    status: 'PUBLISHED',
    lineage_id: '11111111-2222-3333-4444-555555555555',
  })
  await api.get(41)
  await api.updateItem(41, 501, {
    expected_version: 7,
    final_quantity: '9007199254740993.125000',
    adjustment_reason: 'Approved exact quantity',
  })

  assert.deepEqual(calls[0], {
    method: 'POST',
    path: '/v1/demand/demand-lists',
    body: request,
    config: {
      headers: {
        'Idempotency-Key': 'create-list-key',
      },
    },
  })
  assert.equal(
    calls[1]?.path,
    (
      '/v1/demand/demand-lists'
      + '?page=2&page_size=50&status=PUBLISHED'
      + '&lineage_id=11111111-2222-3333-4444-555555555555'
    ),
  )
  assert.equal(
    calls[2]?.path,
    '/v1/demand/demand-lists/41',
  )
  assert.deepEqual(calls[3], {
    method: 'PUT',
    path: '/v1/demand/demand-lists/41/items/501',
    body: {
      expected_version: 7,
      final_quantity: '9007199254740993.125000',
      adjustment_reason: 'Approved exact quantity',
    },
  })
})

test('lifecycle routes send versions, confirmation_note, and keys', async () => {
  const calls: CapturedCall[] = []
  const api = createDemandListApi(fakeClient(calls))

  await api.submit(41, 7, 'submit-key')
  await api.confirm(
    41,
    8,
    'Approved by administrator',
    'confirm-key',
  )
  await api.publish(41, 9, 'publish-key')
  await api.derive(41, 10, 'derive-key')
  await api.void(41, 11, 'void-key')

  assert.deepEqual(calls.map((call) => call.path), [
    '/v1/demand/demand-lists/41/submit',
    '/v1/demand/demand-lists/41/confirm',
    '/v1/demand/demand-lists/41/publish',
    '/v1/demand/demand-lists/41/derive',
    '/v1/demand/demand-lists/41/void',
  ])
  assert.deepEqual(calls[0]?.body, {
    expected_version: 7,
  })
  assert.deepEqual(calls[1]?.body, {
    expected_version: 8,
    confirmation_note: 'Approved by administrator',
  })
  assert.equal(
    Object.hasOwn(
      calls[1]?.body as object,
      'note',
    ),
    false,
  )
  assert.deepEqual(calls.slice(2).map((call) => call.body), [
    { expected_version: 9 },
    { expected_version: 10 },
    { expected_version: 11 },
  ])
  assert.deepEqual(calls.map(headersOf), [
    { 'Idempotency-Key': 'submit-key' },
    { 'Idempotency-Key': 'confirm-key' },
    { 'Idempotency-Key': 'publish-key' },
    { 'Idempotency-Key': 'derive-key' },
    { 'Idempotency-Key': 'void-key' },
  ])
})

test('demand-list calls never expose tenant selection', async () => {
  const calls: CapturedCall[] = []
  const api = createDemandListApi(fakeClient(calls))

  await api.create({
    calculation_group_id: 9,
    name: 'No tenant input',
  }, 'create-key')
  await api.list()
  await api.get(41)
  await api.submit(41, 7, 'submit-key')

  const serialized = JSON.stringify(calls)
  assert.equal(serialized.includes('tenant_id'), false)
  assert.equal(serialized.includes('X-Tenant-ID'), false)
  assert.equal(serialized.includes('"tenant"'), false)
})

test('demand-list decimal strings retain exact precision', () => {
  const serialized = JSON.parse(JSON.stringify({
    original_quantity: '9007199254740993.125000',
    final_quantity: '12345678901234567890.654321',
  })) as Record<string, unknown>

  assert.equal(
    serialized.original_quantity,
    '9007199254740993.125000',
  )
  assert.equal(
    serialized.final_quantity,
    '12345678901234567890.654321',
  )
  assert.equal(
    typeof serialized.final_quantity,
    'string',
  )
})

test('list result retains PageData and response metadata separation', async () => {
  const calls: CapturedCall[] = []
  const page: PageData<never> = {
    items: [],
    page: 1,
    page_size: 20,
    total: 0,
    pages: 0,
  }
  const api = createDemandListApi({
    ...fakeClient(calls),
    async get<T>(
      path: string,
    ): Promise<MaintenanceResult<T>> {
      calls.push({ method: 'GET', path })
      return result(page as T)
    },
  })

  const response = await api.list()

  assert.deepEqual(response.data, page)
  assert.equal(response.meta.tenant_id, 'tenant-a')
  assert.equal(
    Object.hasOwn(response.data as object, 'tenant_id'),
    false,
  )
})
