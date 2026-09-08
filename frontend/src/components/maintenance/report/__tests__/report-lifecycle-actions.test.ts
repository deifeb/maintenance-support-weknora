import assert from 'node:assert/strict'
import test from 'node:test'

import {
  createReportLifecycleController,
  getReportActions,
} from '../report-actions.ts'

test('lifecycle controller calls the allowed typed mutation then refreshes', async () => {
  const calls: string[] = []
  const controller = createReportLifecycleController({
    reportId: 42,
    actions: ['view', 'validate'],
    mutations: {
      validate: async (reportId) => { calls.push(`validate:${reportId}`) },
    },
    refresh: async () => { calls.push('refresh') },
  })

  await controller.run('validate')
  assert.deepEqual(calls, ['validate:42', 'refresh'])
  assert.equal(
    controller.messageFor({ code: 'REPORT_VALIDATION_REQUIRED', request_id: 'r-1' }),
    'maintenance.reports.errors.validationRequired',
  )
})

test('lifecycle controller rejects an action not granted by the server state', async () => {
  const calls: string[] = []
  const controller = createReportLifecycleController({
    reportId: 42,
    actions: ['view'],
    mutations: { generate: async () => { calls.push('generate') } },
    refresh: async () => { calls.push('refresh') },
  })

  await assert.rejects(controller.run('generate'), /not allowed/)
  assert.deepEqual(calls, [])
})

test('final version hides immutable lifecycle controls and regeneration explains copied sources', () => {
  const actions = getReportActions({
    role: 'ADMIN', jobStatus: 'FINALIZED', versionStatus: 'FINAL', versionGenerated: true,
  })
  assert.equal(actions.includes('generate'), false)
  assert.equal(actions.includes('validate'), false)
  assert.equal(actions.includes('finalize'), false)
  assert.equal(actions.includes('regenerate'), true)
  assert.equal(
    createReportLifecycleController.regenerateExplanation,
    'A new version is created, its source snapshot is copied from the current report version, and no business source data is recalculated.',
  )
})

test('unknown errors use the generic key and expose only their request ID', () => {
  const controller = createReportLifecycleController({ reportId: 42, actions: [], mutations: {}, refresh: async () => {} })
  const error = { code: 'PRIVATE_BACKEND_DETAIL', message: 'do not display', request_id: 'request-42' }
  assert.equal(controller.messageFor(error), 'maintenance.reports.errors.generic')
  assert.equal(controller.requestIdFor(error), 'request-42')
})
