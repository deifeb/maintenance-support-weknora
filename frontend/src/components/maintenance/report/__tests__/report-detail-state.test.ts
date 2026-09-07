import { afterEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'

import ReportProvenancePanel from '../ReportProvenancePanel.vue'
import ReportVersionTimeline from '../ReportVersionTimeline.vue'
import ReportDetail from '@/views/maintenance/reports/ReportDetail.vue'
import type { MaintenanceResult } from '@/api/maintenance/types'
import type { ReportDetail as ReportDetailData, ReportVersionSummary } from '@/api/maintenance/reports'

const mocks = vi.hoisted(() => ({ getReport: vi.fn(), listReportVersions: vi.fn() }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ hasRole: () => false }) }))
vi.mock('@/api/maintenance/reports', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/maintenance/reports')>()
  return { ...actual, reportApi: { getReport: mocks.getReport, listReportVersions: mocks.listReportVersions } }
})

enableAutoUnmount(afterEach)
afterEach(() => vi.resetAllMocks())

const detail: ReportDetailData = {
  report_id: 7, report_code: 'RPT-7', report_type: 'MANAGEMENT_DECISION', title: 'Weekly report',
  status: 'DRAFT', version_id: 9, version_number: 2, parent_version_id: 8, template_version: 'v3',
  input_digest: 'input-digest', generation_mode: 'MANUAL', generated_at: '2026-09-07T00:00:00Z',
  source_versions: { capture_mode: 'AUTHORITATIVE_CREATE', provenance_completeness: 'AUTHORITATIVE', sources: [] },
  sections: [], citations: [],
}
const version: ReportVersionSummary = { id: 9, version_number: 2, status: 'DRAFT', parent_version_id: 8, template_version: 'v3', content_digest: 'content-digest', input_digest: 'input-digest', generation_mode: 'MANUAL', generated_at: '2026-09-07T00:00:00Z' }
function result<T>(data: T): MaintenanceResult<T> { return { data, meta: { request_id: 'request-1', tenant_id: 'tenant-1' } } }
function deferred<T>() { let resolve!: (value: T) => void; let reject!: (reason: unknown) => void; const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej }); return { promise, resolve, reject } }

describe('report detail rendered state', () => {
  it('fails closed for malformed provenance and never renders private values', () => {
    const wrapper = mount(ReportProvenancePanel, {
      props: { sources: [{ type: 'AI_SESSION', id: 7, version: 'v2', lineage_id: 'lineage-1', digest: 'digest', source_snapshot_json: 'snapshot-secret', tenant_id: 'tenant-secret', database_record_json: 'database-secret', token: 'token-secret' }] as never },
    })
    expect(wrapper.get('.report-provenance-panel__unavailable').text()).toBe('Source provenance is unavailable.')
    for (const forbidden of ['source_snapshot_json', 'snapshot-secret', 'tenant_id', 'tenant-secret', 'database_record_json', 'database-secret', 'token', 'token-secret']) expect(wrapper.text()).not.toContain(forbidden)
    expect(wrapper.find('table').exists()).toBe(false)
  })

  it('renders immutable timeline lineage and generation evidence', () => {
    const wrapper = mount(ReportVersionTimeline, { props: { versions: [version] } })
    for (const value of ['Parent version', '8', 'v3', 'MANUAL', '2026-09-07T00:00:00Z', 'content-digest']) expect(wrapper.text()).toContain(value)
    expect(wrapper.findAll('button')).toHaveLength(0)
  })

  it('keeps the invalid route state when a previous valid request resolves late', async () => {
    const report = deferred<MaintenanceResult<ReportDetailData>>(); const versions = deferred<MaintenanceResult<ReportVersionSummary[]>>()
    mocks.getReport.mockReturnValueOnce(report.promise); mocks.listReportVersions.mockReturnValueOnce(versions.promise)
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/reports/:reportId', name: 'maintenanceReportDetail', component: ReportDetail }] })
    await router.push('/reports/7'); await router.isReady()
    const wrapper = mount(RouterView, { global: { plugins: [router] } }); await flushPromises()
    await router.push('/reports/0'); await flushPromises()
    report.resolve(result({ ...detail, title: 'STALE report' })); versions.resolve(result([version])); await flushPromises()
    expect(wrapper.text()).toContain('The report identifier is invalid.')
    expect(wrapper.text()).not.toContain('STALE report')
    expect(wrapper.text()).not.toContain('content-digest')
  })
})
