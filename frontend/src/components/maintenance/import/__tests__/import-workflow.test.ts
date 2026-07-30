import assert from 'node:assert/strict'
import test from 'node:test'

import type {
  ImportTaskUploadResult,
  ImportTaskView,
} from '@/api/maintenance/imports.ts'
import type { MaintenanceClientError, MaintenanceResult } from '@/api/maintenance/types.ts'
import type { ImportTaskPolling, ImportTaskPollingOptions } from '../useImportTaskPolling.ts'
import { createImportTaskPolling } from '../useImportTaskPolling.ts'
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

function deferred<T>(): {
  promise: Promise<T>
  resolve(value: T): void
  reject(error: unknown): void
} {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
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

test('execute poller inherits visibility and activity changes made while execution is pending', async () => {
  for (const [setter, initialVisible, initialActive] of [
    ['setVisible', false, true],
    ['setActive', true, false],
  ] as const) {
    const pendingExecute = deferred<MaintenanceResult<ImportTaskView>>()
    let loads = 0
    const workflow = createImportWorkflow({
      api: {
        downloadTemplate: async () => new Blob(), downloadErrors: async () => new Blob(), exportResource: async () => new Blob(),
        uploadTask: async () => result(upload()), previewTask: async () => result(task('PREVIEW_VALID')),
        executeTask: async () => pendingExecute.promise,
        getTask: async () => { loads += 1; return result(task('RUNNING')) },
      },
      createPoller: (options) => createImportTaskPolling(options),
    })

    workflow.selectFile({ name: 'parts.xlsx' } as File)
    await workflow.upload(); await workflow.preview(); workflow.confirm()
    const executing = workflow.execute()
    workflow[setter](false)
    pendingExecute.resolve(result(task('QUEUED')))
    await executing
    assert.equal(loads, 0, `${setter} must pause a poller created after execute resolves`)

    workflow[setter](true)
    await Promise.resolve()
    assert.equal(loads, 1, `${setter} must resume the deferred poller immediately`)
    workflow.dispose()
  }
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
  const deferredRevokes: Array<() => void> = []
  const lifecycle = createImportDialogLifecycle({
    workflow,
    api: {
      downloadTemplate: async () => new Blob(['template']), downloadErrors: async () => new Blob(['errors']), exportResource: async () => new Blob(),
      uploadTask: async () => result(upload()), previewTask: async () => result(task('PREVIEW_VALID')),
      executeTask: async () => result(task('RUNNING')), getTask: async () => result(task('RUNNING')),
    },
    objectUrls: { createObjectURL: () => 'blob:task', revokeObjectURL: (url) => revoked.push(url) },
    triggerDownload: (url, filename) => downloads.push([url, filename]),
    defer: (callback) => deferredRevokes.push(callback),
    onError: () => assert.fail('unexpected lifecycle error'),
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
  assert.deepEqual(revoked, [])
  assert.equal(deferredRevokes.length, 2)
  deferredRevokes.forEach((callback) => callback())
  assert.deepEqual(revoked, ['blob:task', 'blob:task'])
  lifecycle.completed()
  assert.deepEqual(events, ['close', 'completed', 'close'])
  lifecycle.dispose()
  assert.deepEqual(revoked, ['blob:task', 'blob:task'])
})

test('workflow serializes upload, preview, execute, and retry requests while exposing busy state', async () => {
  const pendingUpload = deferred<MaintenanceResult<ImportTaskUploadResult>>()
  const pendingPreview = deferred<MaintenanceResult<ImportTaskView>>()
  const pendingExecute = deferred<MaintenanceResult<ImportTaskView>>()
  const pendingStatus = deferred<MaintenanceResult<ImportTaskView>>()
  const calls = { upload: 0, preview: 0, execute: 0, status: 0 }
  const busy: boolean[] = []
  const workflow = createImportWorkflow({
    api: {
      downloadTemplate: async () => new Blob(), downloadErrors: async () => new Blob(), exportResource: async () => new Blob(),
      uploadTask: async () => { calls.upload += 1; return pendingUpload.promise },
      previewTask: async () => { calls.preview += 1; return pendingPreview.promise },
      executeTask: async () => { calls.execute += 1; return pendingExecute.promise },
      getTask: async () => { calls.status += 1; return pendingStatus.promise },
    },
    createPoller: () => ({ start: async () => undefined, stop: () => undefined, setVisible: () => undefined, setActive: () => undefined }),
  })
  workflow.subscribe((_state, isBusy) => busy.push(isBusy))

  workflow.selectFile({ name: 'parts.xlsx' } as File)
  const uploads = [workflow.upload(), workflow.upload()]
  assert.equal(calls.upload, 1)
  assert.equal(workflow.busy, true)
  pendingUpload.resolve(result(upload()))
  await Promise.all(uploads)
  assert.equal(workflow.busy, false)

  const previews = [workflow.preview(), workflow.preview()]
  assert.equal(calls.preview, 1)
  pendingPreview.resolve(result(task('PREVIEW_VALID')))
  await Promise.all(previews)

  workflow.confirm()
  const executes = [workflow.execute(), workflow.execute()]
  assert.equal(calls.execute, 1)
  pendingExecute.resolve(result(task('QUEUED')))
  await Promise.all(executes)

  const retries = [workflow.retryStatus(), workflow.retryStatus()]
  assert.equal(calls.status, 1)
  pendingStatus.resolve(result(task('RUNNING')))
  await Promise.all(retries)
  assert.equal(workflow.busy, false)
  assert.ok(busy.includes(true))
  assert.equal(busy.at(-1), false)
})

test('lifecycle shares the workflow request gate and reports normalized download errors without rejection', async () => {
  const pendingUpload = deferred<MaintenanceResult<ImportTaskUploadResult>>()
  let uploadCalls = 0
  let templateCalls = 0
  let errorDownloadCalls = 0
  const reported: MaintenanceClientError[] = []
  const workflow = createImportWorkflow({
    api: {
      downloadTemplate: async () => new Blob(), downloadErrors: async () => new Blob(), exportResource: async () => new Blob(),
      uploadTask: async () => { uploadCalls += 1; return pendingUpload.promise },
      previewTask: async () => result(task('PREVIEW_VALID')), executeTask: async () => result(task('QUEUED')),
      getTask: async () => result(task('RUNNING')),
    },
  })
  const lifecycle = createImportDialogLifecycle({
    workflow,
    api: {
      downloadTemplate: async () => { templateCalls += 1; throw new Error('offline') },
      downloadErrors: async () => { errorDownloadCalls += 1; throw error(503, 'DOWNLOAD_UNAVAILABLE', true) },
    },
    objectUrls: { createObjectURL: () => 'unused', revokeObjectURL: () => undefined },
    triggerDownload: () => assert.fail('failed downloads must not trigger'),
    onError: (next) => reported.push(next),
    onCompleted: () => undefined,
    onClose: () => undefined,
  })

  workflow.selectFile({ name: 'parts.xlsx' } as File)
  const uploading = workflow.upload()
  await lifecycle.downloadTemplate()
  assert.equal(uploadCalls, 1)
  assert.equal(templateCalls, 0)
  pendingUpload.resolve(result(upload()))
  await uploading

  await lifecycle.downloadTemplate()
  await lifecycle.downloadErrors('task-1')
  assert.equal(workflow.busy, false)
  assert.equal(errorDownloadCalls, 1)
  assert.deepEqual(reported.map((next) => [next.status, next.code, next.retryable]), [
    [undefined, 'IMPORT_REQUEST_FAILED', true],
    [503, 'DOWNLOAD_UNAVAILABLE', true],
  ])

  lifecycle.reportWorkflowError(reported[1])
  lifecycle.reportWorkflowError(reported[1])
  lifecycle.reportWorkflowError(null)
  lifecycle.reportWorkflowError(reported[1])
  assert.equal(reported.length, 4)
})
