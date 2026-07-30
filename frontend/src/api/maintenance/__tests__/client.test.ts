import assert from 'node:assert/strict'
import test from 'node:test'

import {
  createMaintenanceClient,
  normalizeMaintenanceError,
  unwrapMaintenanceResponse,
  type MaintenanceRequestAdapter,
} from '../client.ts'

test('unwrap returns data and metadata together', () => {
  const result = unwrapMaintenanceResponse({
    success: true,
    data: { id: 7 },
    message: 'ok',
    meta: {
      request_id: 'r-1',
      tenant_id: 't-1',
      version: 3,
    },
  })

  assert.deepEqual(result, {
    data: { id: 7 },
    meta: {
      request_id: 'r-1',
      tenant_id: 't-1',
      version: 3,
    },
  })
})

test('unwrap rejects malformed maintenance responses', () => {
  assert.throws(
    () => unwrapMaintenanceResponse({ data: {} } as never),
    /Invalid maintenance response/,
  )
  assert.throws(
    () =>
      unwrapMaintenanceResponse({
        success: true,
        data: {},
        message: 'ok',
        meta: {
          request_id: '',
          tenant_id: 't-1',
        },
      }),
    /Invalid maintenance response/,
  )
})

test('normalizes structured maintenance errors', () => {
  const result = normalizeMaintenanceError({
    status: 409,
    error: {
      code: 'VERSION_CONFLICT',
      message: 'The record changed.',
      details: {
        expected_version: 3,
      },
    },
    meta: {
      request_id: 'r-2',
    },
  })

  assert.deepEqual(result, {
    status: 409,
    code: 'VERSION_CONFLICT',
    message: 'The record changed.',
    details: {
      expected_version: 3,
    },
    request_id: 'r-2',
    retryable: false,
  })
})

test('marks transport and server errors as retryable', () => {
  assert.deepEqual(
    normalizeMaintenanceError({
      message: 'Network unavailable',
    }),
    {
      code: 'MAINTENANCE_CLIENT_ERROR',
      message: 'Network unavailable',
      retryable: true,
    },
  )

  assert.equal(
    normalizeMaintenanceError({
      status: 503,
      message: 'Service unavailable',
    }).retryable,
    true,
  )
})

test('unwrap rejects a response without the required message', () => {
  assert.throws(
    () =>
      unwrapMaintenanceResponse({
        success: true,
        data: {},
        meta: {
          request_id: 'r-3',
          tenant_id: 't-1',
        },
      } as never),
    /Invalid maintenance response/,
  )
})

test('maintenance client routes every method through the maintenance prefix', async () => {
  const calls: Array<{
    method: string
    url: string
    body?: unknown
    config?: unknown
  }> = []

  const response = {
    success: true as const,
    data: { ok: true },
    message: 'ok',
    meta: {
      request_id: 'r-4',
      tenant_id: 't-1',
    },
  }

  const adapter: MaintenanceRequestAdapter = {
    get: async <T>(url: string): Promise<T> => {
      calls.push({ method: 'get', url })
      return response as unknown as T
    },
    post: async <T>(
      url: string,
      body?: unknown,
      config?: unknown,
    ): Promise<T> => {
      calls.push({ method: 'post', url, body, config })
      return response as unknown as T
    },
    put: async <T>(url: string, body?: unknown): Promise<T> => {
      calls.push({ method: 'put', url, body })
      return response as unknown as T
    },
    patch: async <T>(url: string, body?: unknown): Promise<T> => {
      calls.push({ method: 'patch', url, body })
      return response as unknown as T
    },
    del: async <T>(url: string, body?: unknown): Promise<T> => {
      calls.push({ method: 'delete', url, body })
      return response as unknown as T
    },
  }

  const client = createMaintenanceClient(async () => adapter)
  const body = { code: 'P-1' }
  const config = { headers: { 'Idempotency-Key': 'i-1' } }

  await client.get('/parts?page=1')
  await client.post('/parts', body, config)
  await client.put('/parts/1', body)
  await client.patch('/parts/1', body)
  await client.delete('/parts/1', body)

  assert.deepEqual(calls, [
    { method: 'get', url: '/api/maintenance/parts?page=1' },
    { method: 'post', url: '/api/maintenance/parts', body, config },
    { method: 'put', url: '/api/maintenance/parts/1', body },
    { method: 'patch', url: '/api/maintenance/parts/1', body },
    { method: 'delete', url: '/api/maintenance/parts/1', body },
  ])
})

test('maintenance client normalizes failures from every HTTP method', async () => {
  const failure = {
    status: 409,
    error: {
      code: 'VERSION_CONFLICT',
      message: 'The record changed.',
      details: { expected_version: 4 },
    },
    meta: { request_id: 'r-5' },
  }

  const reject = async <T>(): Promise<T> => {
    throw failure
  }

  const adapter: MaintenanceRequestAdapter = {
    get: reject,
    post: reject,
    put: reject,
    patch: reject,
    del: reject,
  }

  const client = createMaintenanceClient(async () => adapter)
  const operations = [
    () => client.get('/parts'),
    () => client.post('/parts', {}),
    () => client.put('/parts/1', {}),
    () => client.patch('/parts/1', {}),
    () => client.delete('/parts/1'),
  ]

  for (const operation of operations) {
    await assert.rejects(operation, (error: unknown) => {
      assert.deepEqual(error, {
        status: 409,
        code: 'VERSION_CONFLICT',
        message: 'The record changed.',
        details: { expected_version: 4 },
        request_id: 'r-5',
        retryable: false,
      })
      return true
    })
  }
})

test('maintenance client downloads blobs through the maintenance prefix', async () => {
  const download = new Blob(['template'])
  const calls: Array<{ url: string, config: unknown }> = []
  const adapter: MaintenanceRequestAdapter = {
    get: async <T>(url: string, config?: unknown): Promise<T> => {
      calls.push({ url, config })
      return download as T
    },
    post: async <T>(): Promise<T> => undefined as T,
    put: async <T>(): Promise<T> => undefined as T,
    patch: async <T>(): Promise<T> => undefined as T,
    del: async <T>(): Promise<T> => undefined as T,
  }

  const client = createMaintenanceClient(async () => adapter)

  const result = await client.download('/v1/master-data/import/template')

  assert.strictEqual(result, download)
  assert.deepEqual(calls, [{
    url: '/api/maintenance/v1/master-data/import/template',
    config: { responseType: 'blob' },
  }])
})

test('maintenance client normalizes download failures', async () => {
  const adapter: MaintenanceRequestAdapter = {
    get: async <T>(): Promise<T> => {
      throw {
        status: 503,
        error: {
          code: 'EXPORT_UNAVAILABLE',
          message: 'Export service unavailable.',
        },
      }
    },
    post: async <T>(): Promise<T> => undefined as T,
    put: async <T>(): Promise<T> => undefined as T,
    patch: async <T>(): Promise<T> => undefined as T,
    del: async <T>(): Promise<T> => undefined as T,
  }

  const client = createMaintenanceClient(async () => adapter)

  await assert.rejects(
    () => client.download('/v1/master-data/exports/parts'),
    (error: unknown) => {
      assert.deepEqual(error, {
        status: 503,
        code: 'EXPORT_UNAVAILABLE',
        message: 'Export service unavailable.',
        retryable: true,
      })
      return true
    },
  )
})
