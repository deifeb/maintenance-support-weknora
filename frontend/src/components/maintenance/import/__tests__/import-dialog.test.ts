import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

async function source(name: string): Promise<string> {
  return readFile(new URL(`../${name}`, import.meta.url), 'utf8')
}

test('import dialog source provides the complete permission-safe, lifecycle-safe import experience', async () => {
  const [dialog, mapping, preview, result] = await Promise.all([
    source('MasterDataImportDialog.vue'), source('ImportMappingStep.vue'),
    source('ImportPreviewStep.vue'), source('ImportTaskResult.vue'),
  ])

  for (const token of ['open: boolean', 'resourceKey: string', 'canImport: boolean', "(event: 'close')", "(event: 'completed')", 'downloadTemplate', 'downloadErrors', 'createImportDialogLifecycle', 'visibilitychange', 'removeEventListener', 'dispose', 'setVisible']) {
    assert.match(dialog, new RegExp(token.replaceAll('.', '\\.')))
  }
  assert.match(dialog, /canImport/)
  assert.match(dialog, /canConfirmImport/)
  assert.match(dialog, /canExecuteImport/)
  assert.match(dialog, /const busy =/)
  assert.match(dialog, /finally/)
  assert.match(dialog, /workflowBusy/)
  assert.match(dialog, /lifecycle\.reportWorkflowError/)
  assert.match(dialog, /\(event: 'error'/)
  assert.match(dialog, /:disabled="busy/)
  assert.match(result, /busy/)
  assert.match(result, /:disabled="busy"/)
  assert.doesNotMatch(dialog, /tenant_id|tenantId|Maintenance API|VITE_MAINTENANCE|Authorization/i)
  assert.match(mapping, /source_headers/)
  assert.match(mapping, /suggested_mapping/)
  assert.match(preview, /total_rows/)
  for (const token of ['sheet', 'row', 'field', 'code', 'message', 'warnings', 'errors']) assert.match(preview, new RegExp(token))
  for (const token of ['queued', 'running', 'completed', 'failed', 'expired', 'total_rows', 'created', 'updated']) assert.match(result, new RegExp(token))
})
