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

test('lifecycle action matrix requires server generation and review state', () => {
  assert.deepEqual(
    getReportActions({
      role: 'CONTRIBUTOR',
      jobStatus: 'CREATED', versionStatus: 'DRAFT', versionGenerated: false,
    }),
    ['view', 'versions', 'export', 'create', 'generate'],
  )
  assert.deepEqual(getReportActions({ role: 'CONTRIBUTOR', jobStatus: 'VALIDATING_NUMBERS', versionStatus: 'DRAFT', versionGenerated: true }), ['view', 'versions', 'export', 'create', 'validate', 'regenerate'])
  assert.equal(
    getReportActions({
      role: 'ADMIN', jobStatus: 'READY_FOR_REVIEW', versionStatus: 'REVIEWED', versionGenerated: true, hasUnresolvedFindings: false,
    }).includes('finalize'),
    true,
  )
  assert.equal(getReportActions({ role: 'ADMIN', jobStatus: 'READY_FOR_REVIEW', versionStatus: 'REVIEWED', versionGenerated: true, hasUnresolvedFindings: true }).includes('finalize'), false)
})

test('final reports do not expose immutable lifecycle actions but retain allowed regeneration', () => {
  const actions = getReportActions({
    role: 'CONTRIBUTOR',
    jobStatus: 'FINALIZED',
    versionStatus: 'FINAL',
      versionGenerated: true,
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
