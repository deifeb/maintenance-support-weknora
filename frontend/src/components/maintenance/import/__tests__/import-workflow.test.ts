import assert from 'node:assert/strict'
import test from 'node:test'

import type {
  ImportTaskUploadResult,
  ImportTaskView,
} from '@/api/maintenance/imports.ts'
import type { MaintenanceClientError, MaintenanceResult } from '@/api/maintenance/types.ts'
import type { ImportTaskPolling, ImportTaskPollingOptions } from '../useImportTaskPolling.ts'
import {
  createImportDialogLifecycle,
  createImportWorkflow,
} from '../import-workflow.ts'

function result<T>(data: T): MaintenanceResult<T> {
  return { data, meta: { request_id: 'request-1', tenant_id: 'server-only' } }
}

function upload(): ImportTaskUploadResult {
  return {
    task_id: 'task-1', status: 'UPLOADED', original_filename: 'parts.xlsx',
    file_sha256: 'hash', template_version: 'v1', expires_at: 'tomorrow',
    sheets: [{
      name: 'Parts', source_headers: ['Code'], suggested_mapping: { Code: 'code' },
      required_fields: ['code'],
    }],
  }
}

function task(status: string, overrides: Partial<ImportTaskView> = {}): ImportTaskView {
  return {
    ...upload(), status, sheets: [{ name: 'Parts', total_rows: 3, valid_rows: 2, invalid_rows: 1 }],
    preview: { Parts: [{ code: 'P-1' }] }, errors: [], warnings: [], can_execute: true,
    created_at: 'now', started_at: null, finished_at: null, result: null,
    error_code: null, error_message: null, ...overrides,
  }
}

function error(status: number, code: string, retryable = false): MaintenanceClientError {
  return { status, code, message: code, retryable }
}

test('workflow uploads the selected file, previews edited mappings, confirms, executes, and polls', async () => {
  const selected = { name: 'parts.xlsx' } as File
  const calls: unknown[] = []
  let pollOptions: ImportTaskPollingOptions | undefined
  let starts = 0
  let stops = 0
  const workflow = createImportWorkflow({
    api: {
      downloadTemplate: async () => new Blob(),
      downloadErrors: async () => new Blob(),
      exportResource: async () => new Blob(),
      uploadTask: async (file) => { calls.push(['upload', file]); return result(upload()) },
      previewTask: async (taskId, mapping) => { calls.push(['preview', taskId, mapping]); return result(task('PREVIEW_VALID')) },
      executeTask: async (taskId) => { calls.push(['execute', taskId]); return result(task('QUEUED')) },
      getTask: async () => result(task('RUNNING')),
    },
    createPoller: (options) => {
      pollOptions = options
      return {
        start: async () => { starts += 1 }, stop: () => { stops += 1 },
        setVisible: () => undefined, setActive: () => undefined,
      }
    },
  })

  workflow.selectFile(selected)
  await workflow.upload()
  assert.equal(workflow.state.mapping.Parts.Code, 'code')
  workflow.setMapping('Parts', 'Code', 'part_code')
  await workflow.preview()
  assert.deepEqual(calls, [
    ['upload', selected],
    ['preview', 'task-1', { Parts: { Code: 'part_code' } }],
  ])

  await assert.rejects(workflow.execute(), /confirmation/i)
  workflow.confirm()
  await workflow.execute()
  assert.deepEqual(calls.at(-1), ['execute', 'task-1'])
  assert.equal(workflow.state.phase, 'queued')
  assert.equal(starts, 1)
  assert.ok(pollOptions)
  pollOptions.onTask(task('COMPLETED', {
    result: { imported: true, total_rows: 3, created: { parts: 2 }, updated: { parts: 1 } },
  }))
  assert.equal(workflow.state.phase, 'completed')
  workflow.selectFile({ name: 'replacement.xlsx' } as File)
  assert.equal(stops, 1)
  assert.equal(workflow.state.phase, 'selected')
  workflow.dispose()
})

test('workflow invalidates stale requests, maps missing tasks to expired, and retains actionable errors', async () => {
  let resolveUpload: ((value: MaintenanceResult<ImportTaskUploadResult>) => void) | undefined
  let getTaskError: MaintenanceClientError | undefined
  let previewError = error(422, 'INVALID_MAPPING')
  const workflow = createImportWorkflow({
    resourceKey: 'parts',
    api: {
      downloadTemplate: async () => new Blob(), downloadErrors: async () => new Blob(), exportResource: async () => new Blob(),
      uploadTask: () => new Promise((resolve) => { resolveUpload = resolve }),
      previewTask: async () => { throw previewError },
      executeTask: async () => result(task('QUEUED')),
      getTask: async () => {
        if (getTaskError) throw getTaskError
        return result(task('RUNNING'))
      },
    },
    createPoller: () => ({ start: async () => undefined, stop: () => undefined, setVisible: () => undefined, setActive: () => undefined }),
  })

  workflow.selectFile({ name: 'old.xlsx' } as File)
  const pendingUpload = workflow.upload()
  workflow.selectFile({ name: 'new.xlsx' } as File)
  resolveUpload?.(result(upload()))
  await pendingUpload
  assert.equal(workflow.state.fileName, 'new.xlsx')
  assert.equal(workflow.state.task, null)

  workflow.selectFile({ name: 'parts.xlsx' } as File)
  resolveUpload = undefined
  const freshUpload = workflow.upload()
  resolveUpload?.(result(upload()))
  await freshUpload
  await workflow.preview()
  assert.equal(workflow.state.error?.status, 422)
  assert.equal(workflow.state.error?.retryable, false)
  previewError = error(409, 'PREVIEW_CONFLICT')
  await workflow.preview()
  assert.equal(workflow.state.error?.status, 409)
  assert.equal(workflow.state.error?.retryable, false)

  getTaskError = error(404, 'TASK_NOT_FOUND')
  await workflow.retryStatus()
  assert.equal(workflow.state.phase, 'expired')
  assert.equal(workflow.state.error, null)

  workflow.selectFile({ name: 'retry.xlsx' } as File)
  resolveUpload = undefined
  const retryUpload = workflow.upload()
  resolveUpload?.(result(upload()))
  await retryUpload
  getTaskError = error(503, 'UPSTREAM_UNAVAILABLE', true)
  await workflow.retryStatus()
  assert.equal(workflow.state.error?.status, 503)
  assert.equal(workflow.state.error?.retryable, true)

  workflow.reset('parts')
  assert.equal(workflow.state.phase, 'selected')
  assert.equal(workflow.state.fileName, null)
})

test('invalid previews cannot be confirmed or executed', async () => {
  const workflow = createImportWorkflow({
    api: {
      downloadTemplate: async () => new Blob(), downloadErrors: async () => new Blob(), exportResource: async () => new Blob(),
      uploadTask: async () => result(upload()),
      previewTask: async () => result(task('PREVIEW_INVALID', { can_execute: false })),
      executeTask: async () => { assert.fail('invalid preview must not execute') },
      getTask: async () => result(task('RUNNING')),
    },
  })
  workflow.selectFile({ name: 'parts.xlsx' } as File)
  await workflow.upload()
  await workflow.preview()
  workflow.confirm()
  assert.equal(workflow.state.phase, 'previewed')
  await assert.rejects(workflow.execute(), /confirmation/i)
})

test('dialog lifecycle cancels stale polling, sanitizes downloads, and emits completion before close', async () => {
  let pollOptions: ImportTaskPollingOptions | undefined
  const visibility: boolean[] = []
  const workflow = createImportWorkflow({
    resourceKey: 'parts',
    api: {
      downloadTemplate: async () => new Blob(['template']), downloadErrors: async () => new Blob(['errors']), exportResource: async () => new Blob(),
      uploadTask: async () => result(upload()), previewTask: async () => result(task('PREVIEW_VALID')),
      executeTask: async () => result(task('RUNNING')), getTask: async () => result(task('RUNNING')),
    },
    createPoller: (options) => {
      pollOptions = options
      return { start: async () => undefined, stop: () => undefined, setVisible: (visible) => visibility.push(visible), setActive: () => undefined }
    },
  })
  const events: string[] = []
  const downloads: Array<[string, string]> = []
  const revoked: string[] = []
  const lifecycle = createImportDialogLifecycle({
    workflow,
    api: {
      downloadTemplate: async () => new Blob(['template']), downloadErrors: async () => new Blob(['errors']), exportResource: async () => new Blob(),
      uploadTask: async () => result(upload()), previewTask: async () => result(task('PREVIEW_VALID')),
      executeTask: async () => result(task('RUNNING')), getTask: async () => result(task('RUNNING')),
    },
    objectUrls: { createObjectURL: () => 'blob:task', revokeObjectURL: (url) => revoked.push(url) },
    triggerDownload: (url, filename) => downloads.push([url, filename]),
    onCompleted: () => events.push('completed'), onClose: () => events.push('close'),
  })

  workflow.selectFile({ name: 'parts.xlsx' } as File)
  await workflow.upload(); await workflow.preview(); workflow.confirm(); await workflow.execute()
  assert.ok(pollOptions)
  lifecycle.setVisible(false)
  assert.deepEqual(visibility, [false])
  lifecycle.close()
  pollOptions.onTask(task('COMPLETED'))
  assert.equal(workflow.state.phase, 'selected')
  await lifecycle.downloadTemplate()
  await lifecycle.downloadErrors('../../unsafe task:id')
  assert.deepEqual(downloads, [
    ['blob:task', 'master-data-import-template.xlsx'],
    ['blob:task', 'import-errors-unsafe-task-id.xlsx'],
  ])
  assert.deepEqual(revoked, ['blob:task', 'blob:task'])
  lifecycle.completed()
  assert.deepEqual(events, ['close', 'completed', 'close'])
  lifecycle.dispose()
  assert.deepEqual(revoked, ['blob:task', 'blob:task'])
})
