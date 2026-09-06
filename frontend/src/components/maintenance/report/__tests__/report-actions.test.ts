import assert from 'node:assert/strict'
import test from 'node:test'

import { getReportActions, reportErrorMessageKey } from '../report-actions.ts'

test('viewer actions are limited to read-only report affordances', () => {
  assert.deepEqual(
    getReportActions({
      role: 'VIEWER',
      jobStatus: 'READY_FOR_REVIEW',
      versionStatus: 'REVIEWED',
    }),
    ['view', 'versions', 'export'],
  )
})

test('contributors gain report workflow actions and admins can finalize', () => {
  assert.deepEqual(
    getReportActions({
      role: 'CONTRIBUTOR',
      jobStatus: 'READY_FOR_REVIEW',
      versionStatus: 'REVIEWED',
      backendAllowsRegenerate: true,
    }),
    ['view', 'versions', 'export', 'create', 'generate', 'validate', 'regenerate'],
  )
  assert.equal(
    getReportActions({
      role: 'ADMIN',
      jobStatus: 'READY_FOR_REVIEW',
      versionStatus: 'REVIEWED',
    }).includes('finalize'),
    true,
  )
})

test('final reports do not expose immutable lifecycle actions but retain allowed regeneration', () => {
  const actions = getReportActions({
    role: 'CONTRIBUTOR',
    jobStatus: 'FINALIZED',
    versionStatus: 'FINAL',
    backendAllowsRegenerate: true,
  })

  assert.equal(actions.includes('generate'), false)
  assert.equal(actions.includes('validate'), false)
  assert.equal(actions.includes('finalize'), false)
  assert.equal(actions.includes('regenerate'), true)
})

test('report errors have known translated keys and a safe fallback', () => {
  assert.equal(
    reportErrorMessageKey('REPORT_SOURCE_CONFLICT'),
    'maintenance.reports.errors.sourceConflict',
  )
  assert.equal(
    reportErrorMessageKey('untrusted-error'),
    'maintenance.reports.errors.generic',
  )
})
