import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const source = readFileSync(
  new URL('../master-data/MasterDataListPage.vue', import.meta.url),
  'utf8',
)

test('page renders registry-authorized template, export, and import actions', () => {
  assert.match(source, /visibleMasterDataTransferActions\(/)
  assert.match(source, /MasterDataImportDialog/)
  assert.match(source, /transferActions\.includes\('template'\)/)
  assert.match(source, /transferActions\.includes\('export'\)/)
  assert.match(source, /transferActions\.includes\('import'\)/)
})

test('export forwards only the current applied server-table filters', () => {
  assert.match(
    source,
    /masterDataTransferApi\.exportResource\(\s*transfer\.exportKey,\s*\{\s*keyword:\s*keyword\.value,\s*include_inactive:\s*includeInactive\.value,\s*sort_by:\s*sortBy\.value,\s*sort_order:\s*sortOrder\.value,\s*\},\s*\)/,
  )
  assert.doesNotMatch(source, /tenant_id|tenantId/)
})

test('page closes and invalidates the old import dialog before route table reset', () => {
  assert.match(
    source,
    /importDialogOpen\.value\s*=\s*false[\s\S]*importGeneration\.value\s*\+=\s*1[\s\S]*await nextTick\(\)[\s\S]*reset\(/,
  )
  assert.match(source, /@completed="handleImportCompleted"/)
  assert.match(source, /generation\s*!==\s*importGeneration\.value/)
})

test('download uses a sanitized xlsx filename and revokes the object URL after click', () => {
  assert.match(source, /replace\(\/\[\^a-zA-Z0-9._-\]\+\/g, '-'/)
  assert.match(source, /URL\.createObjectURL\(/)
  assert.match(source, /URL\.revokeObjectURL\(/)
  assert.match(source, /\.xlsx/)
})
