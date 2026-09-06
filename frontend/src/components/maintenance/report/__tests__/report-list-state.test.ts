import assert from 'node:assert/strict'
import test from 'node:test'
import { createServer, type ViteDevServer } from 'vite'
import { createSSRApp } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createI18n } from 'vue-i18n'
import { normalizeReportListQuery } from '../report-types.ts'

let vite: ViteDevServer | undefined

async function module(path: string): Promise<Record<string, any>> {
  vite ??= await createServer({ configFile: 'vite.config.ts', appType: 'custom', logLevel: 'error', server: { middlewareMode: true } })
  return vite.ssrLoadModule(path)
}

test('normalizes only backend-valid report list query values', () => {
  assert.deepEqual(
    normalizeReportListQuery({ keyword: '', source_type: 'FUTURE_SOURCE', page: 0, page_size: 201, report_type: 'fake', job_status: 'fake', version_status: 'fake', generator: 'fake', source_version: 'x'.repeat(129) }),
    { page: 1, page_size: 20, source_type: 'FUTURE_SOURCE', sort_by: 'created_at', sort_order: 'desc' },
  )
  assert.deepEqual(
    normalizeReportListQuery({ page: '2', page_size: '200', keyword: ' report ', source_id: '7', source_version: 'v3', report_type: 'DEMAND_CALCULATION', job_status: 'BUILDING_SKELETON', version_status: 'DRAFT' }),
    { page: 2, page_size: 200, keyword: 'report', source_id: 7, source_version: 'v3', report_type: 'DEMAND_CALCULATION', job_status: 'BUILDING_SKELETON', version_status: 'DRAFT', sort_by: 'created_at', sort_order: 'desc' },
  )
})

test('real report table render exposes only actions returned for the current role', async () => {
  const { default: ReportListTable } = await module('/src/components/maintenance/report/ReportListTable.vue')
  const app = createSSRApp(ReportListTable, { role: 'VIEWER', reports: [{ report_id: 7, report_code: 'RPT-7', title: 'Status', report_type: 'DEMAND_CALCULATION', job_status: 'BUILDING_SKELETON', progress_percent: 10, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z', session_id: null, error_code: null, latest_version: { id: 3, version_number: 1, status: 'DRAFT' } }] })
  app.use(createI18n({ legacy: false, locale: 'en-US', messages: { 'en-US': { maintenance: { reports: { columns: { code: 'Code', title: 'Title', type: 'Type', jobStatus: 'Job', version: 'Version', progress: 'Progress', created: 'Created', updated: 'Updated', actions: 'Actions' }, actions: { view: 'Open', export: 'Export', generate: 'Generate', validate: 'Validate', finalize: 'Finalize', regenerate: 'Regenerate' } } } } } }))
  const html = await renderToString(app)
  assert.match(html, /RPT-7/)
  assert.match(html, />Open</)
  assert.match(html, />Export</)
  assert.doesNotMatch(html, />Generate</)
  assert.doesNotMatch(html, />Validate</)
  assert.doesNotMatch(html, />Finalize</)
})

test.after(async () => { await vite?.close() })
