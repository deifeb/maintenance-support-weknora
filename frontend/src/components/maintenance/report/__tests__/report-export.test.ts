import assert from 'node:assert/strict'
import test from 'node:test'

import { createReportExportController } from '../report-actions.ts'

test('downloads every supported report format using the server supplied filename and content type', async () => {
  const downloads: Array<{ filename: string; type: string }> = []
  const calls: Array<{ reportId: number; format: string }> = []
  const cleanup: string[] = []
  const controller = createReportExportController({
    reportId: 42,
    actions: ['view', 'export'],
    exportReport: async (reportId, format) => {
      calls.push({ reportId, format })
      return {
        blob: new Blob(['report']),
        filename: format === 'DOCX' ? 'RPT-1-v2.docx' : `RPT-1-v2.${format.toLowerCase()}`,
        contentType: format === 'DOCX'
          ? 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
          : format === 'JSON' ? 'application/json' : 'text/markdown',
      }
    },
    createObjectURL: (blob) => { downloads.push({ filename: '', type: blob.type }); return 'blob:report' },
    revokeObjectURL: (url) => { assert.equal(url, 'blob:report'); cleanup.push(`revoke:${url}`) },
    createAnchor: () => ({
      href: '', download: '',
      click() { downloads.at(-1)!.filename = this.download },
      remove() { cleanup.push('remove') },
    }),
  })

  for (const format of ['MARKDOWN', 'JSON', 'DOCX'] as const) await controller.download(format)

  assert.deepEqual(calls, [
    { reportId: 42, format: 'MARKDOWN' }, { reportId: 42, format: 'JSON' }, { reportId: 42, format: 'DOCX' },
  ])
  assert.deepEqual(downloads, [
    { filename: 'RPT-1-v2.markdown', type: 'text/markdown' },
    { filename: 'RPT-1-v2.json', type: 'application/json' },
    { filename: 'RPT-1-v2.docx', type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' },
  ])
  assert.equal(downloads[2].filename.includes('/'), false)
  assert.deepEqual(cleanup, ['remove', 'revoke:blob:report', 'remove', 'revoke:blob:report', 'remove', 'revoke:blob:report'])
})

test('does not click an anchor and exposes only mapped feedback for an export failure', async () => {
  let clicked = false
  const controller = createReportExportController({
    reportId: 42,
    actions: ['view', 'export'],
    exportReport: async () => { throw { code: 'PRIVATE_BACKEND_DETAIL', message: 'C:\\secret\\report.docx', request_id: 'request-42' } },
    createObjectURL: () => { throw new Error('must not create url') },
    revokeObjectURL: () => {},
    createAnchor: () => ({ href: '', download: '', click() { clicked = true }, remove() {} }),
  })

  await assert.rejects(controller.download('DOCX'))
  assert.equal(clicked, false)
  assert.equal(controller.messageFor({ code: 'PRIVATE_BACKEND_DETAIL' }), 'maintenance.reports.errors.generic')
  assert.equal(controller.requestIdFor({ request_id: 'request-42' }), 'request-42')
})

test('removes the anchor and revokes the URL when clicking or removal throws', async () => {
  const cleanup: string[] = []
  const controller = createReportExportController({
    reportId: 42,
    actions: ['export'],
    exportReport: async () => ({ blob: new Blob(['report']), filename: 'RPT-1-v2.docx', contentType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' }),
    createObjectURL: () => 'blob:report',
    revokeObjectURL: (url) => { cleanup.push(`revoke:${url}`) },
    createAnchor: () => ({
      href: '', download: '',
      click() { cleanup.push('click'); throw { code: 'PRIVATE_BACKEND_DETAIL', message: 'C:\\secret\\report.docx', request_id: 'request-42' } },
      remove() { cleanup.push('remove'); throw new Error('remove failure') },
    }),
  })

  await assert.rejects(controller.download('DOCX'))
  assert.deepEqual(cleanup, ['click', 'remove', 'revoke:blob:report'])
})
