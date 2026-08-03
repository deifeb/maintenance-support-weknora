import assert from 'node:assert/strict'
import test from 'node:test'

import { createMasterDataTransferApi } from '../imports.ts'
import type { MaintenanceResult } from '../types.ts'

function result<T>(data: T): MaintenanceResult<T> {
  return {
    data,
    meta: {
      request_id: 'request-1',
      tenant_id: 'tenant-1',
    },
  }
}

test('transfer API uses the exact task paths, payloads, and encoded exports', async () => {
  const calls: Array<{
    method: 'download' | 'get' | 'post'
    path: string
    body?: unknown
    config?: unknown
  }> = []
  const template = new Blob(['template'])
  const errors = new Blob(['errors'])
  const exportFile = new Blob(['export'])
  const client = {
    download: async (path: string): Promise<Blob> => {
      calls.push({ method: 'download', path })
      return path.includes('errors.xlsx')
        ? errors
        : path.includes('exports')
          ? exportFile
          : template
    },
    get: async <T>(path: string): Promise<MaintenanceResult<T>> => {
      calls.push({ method: 'get', path })
      return result({ task_id: 'task/id' } as T)
    },
    post: async <T>(
      path: string,
      body: unknown,
      config?: unknown,
    ): Promise<MaintenanceResult<T>> => {
      calls.push({ method: 'post', path, body, config })
      return result({ task_id: 'task/id' } as T)
    },
  }
  const api = createMasterDataTransferApi(client)
  const file = new File(['rows'], 'master-data.xlsx', {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  })
  const mapping = {
    Parts: { 'Part Code': 'code' },
  }

  assert.strictEqual(await api.downloadTemplate(), template)
  await api.uploadTask(file)
  await api.previewTask('task/id', mapping)
  await api.executeTask('task/id')
  await api.getTask('task/id')
  assert.strictEqual(await api.downloadErrors('task/id'), errors)
  assert.strictEqual(
    await api.exportResource('spare parts/active', {
      keyword: 'pump & valve',
      include_inactive: true,
      sort_by: 'code',
      sort_order: 'desc',
    }),
    exportFile,
  )

  assert.deepEqual(calls.map(({ body, ...call }) => call), [
    {
      method: 'download',
      path: '/v1/master-data/import/template',
    },
    {
      method: 'post',
      path: '/v1/master-data/import/tasks',
      config: {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      },
    },
    {
      method: 'post',
      path: '/v1/master-data/import/tasks/task%2Fid/preview',
      config: undefined,
    },
    {
      method: 'post',
      path: '/v1/master-data/import/tasks/task%2Fid/execute',
      config: undefined,
    },
    {
      method: 'get',
      path: '/v1/master-data/import/tasks/task%2Fid',
    },
    {
      method: 'download',
      path: '/v1/master-data/import/tasks/task%2Fid/errors.xlsx',
    },
    {
      method: 'download',
      path: '/v1/master-data/exports/spare%20parts%2Factive?keyword=pump+%26+valve&include_inactive=true&sort_by=code&sort_order=desc',
    },
  ])

  const upload = calls[1]?.body
  assert.ok(upload instanceof FormData)
  assert.strictEqual(upload.get('file'), file)
  assert.deepEqual(calls[2]?.body, { mapping })
  assert.deepEqual(calls[3]?.body, {})
})

test('transfer API never serializes tenant fields into export queries', async () => {
  const paths: string[] = []
  const client = {
    download: async (path: string): Promise<Blob> => {
      paths.push(path)
      return new Blob()
    },
    get: async <T>(): Promise<MaintenanceResult<T>> => result({} as T),
    post: async <T>(): Promise<MaintenanceResult<T>> => result({} as T),
  }
  const api = createMasterDataTransferApi(client)

  await api.exportResource('parts', {
    keyword: 'pump',
    tenant_id: 'tenant-should-not-leave-the-browser',
  } as unknown as {
    keyword: string
  })

  assert.deepEqual(paths, [
    '/v1/master-data/exports/parts?keyword=pump',
  ])
})
