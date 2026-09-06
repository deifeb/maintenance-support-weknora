import assert from 'node:assert/strict'
import test from 'node:test'
import { createServer, type ViteDevServer } from 'vite'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia } from 'pinia'
import { normalizeReportListQuery } from '../report-types.ts'

let vite: ViteDevServer | undefined
async function load(path: string): Promise<any> { vite ??= await createServer({ configFile: 'vite.config.ts', appType: 'custom', logLevel: 'error', server: { middlewareMode: true }, optimizeDeps: { noDiscovery: true } }); return vite.ssrLoadModule(path) }
const messages = { 'en-US': { maintenance: { pages: { reports: 'Reports' }, reports: { description: 'Description', createComingSoon: '', loading: 'Loading', empty: 'Empty', filters: { keyword: 'Keyword', keywordPlaceholder: '', reportType: 'Type', jobStatus: 'Job', versionStatus: 'Version', sourceType: 'Source', all: 'All' }, columns: { code: 'Code', title: 'Title', type: 'Type', jobStatus: 'Job', version: 'Version', progress: 'Progress', created: 'Created', updated: 'Updated', actions: 'Actions' }, actions: { apply: 'Apply', clear: 'Clear', retry: 'Retry', previous: 'Previous', next: 'Next', create: 'Create', view: 'Open', export: 'Export', generate: 'Generate', validate: 'Validate', finalize: 'Finalize', regenerate: 'Regenerate' } } } } }
const item = { report_id: 7, report_code: 'RPT-7', title: 'Status', report_type: 'DEMAND_CALCULATION', job_status: 'BUILDING_SKELETON', progress_percent: 10, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z', session_id: null, error_code: null, latest_version: { id: 3, version_number: 1, status: 'DRAFT' } }
const deferred = <T,>() => { let resolve!: (v: T) => void; let reject!: (e: unknown) => void; return { promise: new Promise<T>((res, rej) => { resolve = res; reject = rej }), resolve, reject } }

test('normalizes backend-valid query values', () => assert.deepEqual(normalizeReportListQuery({ page: 0, page_size: 201, report_type: 'fake', job_status: 'fake', source_type: 'FUTURE', source_version: 'x'.repeat(129) }), { page: 1, page_size: 20, source_type: 'FUTURE', sort_by: 'created_at', sort_order: 'desc' }))

test('component test dependencies are available for report list interaction coverage', async () => {
  const { mount } = await import('@vue/test-utils')
  const { default: Table } = await load('/src/components/maintenance/report/ReportListTable.vue')
  assert.equal(typeof mount, 'function')
  assert.ok(Table)
})

test.after(async () => { await vite?.close() })
