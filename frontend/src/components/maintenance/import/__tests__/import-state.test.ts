import assert from 'node:assert/strict'
import test from 'node:test'

import {
  canConfirmImport,
  canExecuteImport,
  createImportState,
  importReducer,
} from '../import-state.ts'
import type { ImportTaskView } from '@/api/maintenance/imports.ts'
import type { MaintenanceClientError } from '@/api/maintenance/types.ts'

function task(
  status: ImportTaskView['status'],
  overrides: Partial<ImportTaskView> = {},
): ImportTaskView {
  return {
    task_id: 'task-1',
    status,
    original_filename: 'parts.xlsx',
    file_sha256: 'hash',
    template_version: 'v1',
    sheets: [],
    preview: {},
    errors: [],
    warnings: [],
    can_execute: true,
    created_at: '2026-07-30T00:00:00Z',
    expires_at: '2026-07-31T00:00:00Z',
    started_at: null,
    finished_at: null,
    result: null,
    error_code: null,
    error_message: null,
    ...overrides,
  }
}

test('reducer follows the explicit upload, preview, confirmation, and execution phases', () => {
  let state = createImportState('parts')
  assert.equal(state.phase, 'idle')

  state = importReducer(state, {
    type: 'FILE_SELECTED',
    fileName: 'parts.xlsx',
  })
  assert.equal(state.phase, 'selected')
  assert.equal(state.generation, 1)

  state = importReducer(state, {
    type: 'TASK_UPLOADED',
    generation: state.generation,
    task: {
      task_id: 'task-1',
      status: 'UPLOADED',
      original_filename: 'parts.xlsx',
      file_sha256: 'hash',
      template_version: 'v1',
      sheets: [],
      expires_at: '2026-07-31T00:00:00Z',
    },
  })
  assert.equal(state.phase, 'uploaded')

  state = importReducer(state, {
    type: 'TASK_UPDATED',
    generation: state.generation,
    taskId: 'task-1',
    task: task('PREVIEW_VALID'),
  })
  assert.equal(state.phase, 'previewed')
  assert.equal(canConfirmImport(state), true)
  assert.equal(canExecuteImport(state), false)

  state = importReducer(state, { type: 'CONFIRMED' })
  assert.equal(state.phase, 'confirmed')
  assert.equal(canExecuteImport(state), true)

  state = importReducer(state, {
    type: 'TASK_UPDATED',
    generation: state.generation,
    taskId: 'task-1',
    task: task('QUEUED'),
  })
  assert.equal(state.phase, 'queued')

  state = importReducer(state, {
    type: 'TASK_UPDATED',
    generation: state.generation,
    taskId: 'task-1',
    task: task('RUNNING'),
  })
  assert.equal(state.phase, 'running')

  state = importReducer(state, {
    type: 'TASK_UPDATED',
    generation: state.generation,
    taskId: 'task-1',
    task: task('COMPLETED'),
  })
  assert.equal(state.phase, 'completed')
})

test('execute requires a valid preview and explicit confirmation', () => {
  const state = createImportState('parts')
  assert.equal(canConfirmImport(state), false)
  assert.equal(canExecuteImport(state), false)

  const previewed = importReducer(
    importReducer(
      importReducer(state, { type: 'FILE_SELECTED', fileName: 'parts.xlsx' }),
      {
        type: 'TASK_UPLOADED',
        generation: 1,
        task: {
          task_id: 'task-1', status: 'UPLOADED', original_filename: 'parts.xlsx',
          file_sha256: 'hash', template_version: 'v1', sheets: [], expires_at: 'tomorrow',
        },
      },
    ),
    { type: 'TASK_UPDATED', generation: 1, taskId: 'task-1', task: task('PREVIEW_VALID', { can_execute: false }) },
  )
  assert.equal(canConfirmImport(previewed), true)
  assert.equal(canExecuteImport(importReducer(previewed, { type: 'CONFIRMED' })), false)
})

test('a new file or resource invalidates prior tasks and stale results by identity', () => {
  const selected = importReducer(createImportState('parts'), {
    type: 'FILE_SELECTED',
    fileName: 'parts.xlsx',
  })
  const uploaded = importReducer(selected, {
    type: 'TASK_UPLOADED',
    generation: 1,
    task: {
      task_id: 'task-1', status: 'UPLOADED', original_filename: 'parts.xlsx',
      file_sha256: 'hash', template_version: 'v1', sheets: [], expires_at: 'tomorrow',
    },
  })
  const replacement = importReducer(uploaded, {
    type: 'FILE_SELECTED',
    fileName: 'replacement.xlsx',
  })
  assert.equal(replacement.generation, 2)
  assert.equal(replacement.task, null)
  assert.equal(replacement.phase, 'selected')

  const staleUpdate = importReducer(replacement, {
    type: 'TASK_UPDATED', generation: 1, taskId: 'task-1', task: task('COMPLETED'),
  })
  assert.strictEqual(staleUpdate, replacement)

  const error: MaintenanceClientError = {
    code: 'REQUEST_FAILED', message: 'late response', retryable: true,
  }
  const staleFailure = importReducer(replacement, {
    type: 'REQUEST_FAILED', generation: 1, taskId: 'task-1', error,
  })
  assert.strictEqual(staleFailure, replacement)

  const changedResource = importReducer(replacement, {
    type: 'RESOURCE_CHANGED', resourceKey: 'warehouses',
  })
  assert.equal(changedResource.resourceKey, 'warehouses')
  assert.equal(changedResource.generation, 3)
  assert.equal(changedResource.phase, 'idle')
})

test('failed and expired backend tasks are terminal phases', () => {
  for (const [status, phase] of [['FAILED', 'failed'], ['EXPIRED', 'expired']] as const) {
    const state = importReducer(
      importReducer(createImportState('parts'), { type: 'FILE_SELECTED', fileName: 'parts.xlsx' }),
      {
        type: 'TASK_UPDATED', generation: 1, taskId: undefined, task: task(status),
      },
    )
    assert.equal(state.phase, phase)
  }
})
