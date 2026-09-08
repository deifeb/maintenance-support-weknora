import { afterEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'

import ReportProvenancePanel from '../ReportProvenancePanel.vue'
import ReportVersionTimeline from '../ReportVersionTimeline.vue'
import ReportExportActions from '../ReportExportActions.vue'
import ReportLifecycleActions from '../ReportLifecycleActions.vue'
import ReportSections from '../ReportSections.vue'
import { pendingReportMutations } from '../report-mutation-state'
import ReportDetail from '@/views/maintenance/reports/ReportDetail.vue'
import en from '@/i18n/locales/en-US'
import zh from '@/i18n/locales/zh-CN'
import type { MaintenanceResult } from '@/api/maintenance/types'
import type { ReportDetail as ReportDetailData, ReportVersionSummary } from '@/api/maintenance/reports'

const mocks = vi.hoisted(() => ({ getReport: vi.fn(), listReportVersions: vi.fn(), hasRole: vi.fn(), regenerate: vi.fn(), validate: vi.fn(), language: '' }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ hasRole: mocks.hasRole }) }))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => mocks.language ? key.split('.').reduce((obj: any, part) => obj?.[part], mocks.language === 'zh' ? zh : en) ?? key : key }) }))
vi.mock('@/api/maintenance/reports', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/maintenance/reports')>()
  return { ...actual, reportApi: { getReport: mocks.getReport, listReportVersions: mocks.listReportVersions, regenerateReport: mocks.regenerate, validateReport: mocks.validate } }
})

enableAutoUnmount(afterEach)
afterEach(() => { vi.resetAllMocks(); mocks.language = '' })

const detail: ReportDetailData = {
  report_id: 7, report_code: 'RPT-7', report_type: 'MANAGEMENT_DECISION', title: 'Weekly report',
  status: 'DRAFT', job_status: 'READY_FOR_REVIEW', version_id: 9, version_number: 2, parent_version_id: 8, template_version: 'v3',
  input_digest: 'input-digest', generation_mode: 'MANUAL', generated_at: '2026-09-07T00:00:00Z',
  source_versions: { capture_mode: 'AUTHORITATIVE_CREATE', provenance_completeness: 'AUTHORITATIVE', sources: [] },
  sections: [], citations: [],
}
const version: ReportVersionSummary = { id: 9, version_number: 2, status: 'DRAFT', parent_version_id: 8, template_version: 'v3', content_digest: 'content-digest', input_digest: 'input-digest', generation_mode: 'MANUAL', generated_at: '2026-09-07T00:00:00Z' }
function result<T>(data: T): MaintenanceResult<T> { return { data, meta: { request_id: 'request-1', tenant_id: 'tenant-1' } } }
function deferred<T>() { let resolve!: (value: T) => void; let reject!: (reason: unknown) => void; const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej }); return { promise, resolve, reject } }

describe('report detail rendered state', () => {
  async function mountDetail(data = detail) {
    mocks.hasRole.mockImplementation((role: string) => role === 'admin')
    mocks.getReport.mockResolvedValue(result(data)); mocks.listReportVersions.mockResolvedValue(result([version]))
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/reports/:reportId', component: ReportDetail }, { path: '/away', component: { template: '<p>Away</p>' } }] })
    await router.push('/reports/7'); await router.isReady()
    const wrapper = mount(RouterView, { global: { plugins: [router] } }); await flushPromises()
    return { wrapper, router }
  }

  it('renders detail and presentation copy in both supported languages', async () => {
    for (const [language, expected] of [['en', ['Back to reports', 'Refresh', 'Source provenance', 'Version timeline', 'Validation findings', 'Report sections']], ['zh', ['返回报表中心', '刷新', '来源追溯', '版本时间线', '校验结果', '报表章节']]] as const) {
      mocks.language = language
      const { wrapper } = await mountDetail()
      for (const text of expected) expect(wrapper.text()).toContain(text)
      expect(wrapper.text()).not.toContain('maintenance.reports.')
      wrapper.unmount()
    }
  })

  it('holds a report mutation lock across refresh, full detail unmount and reload', async () => {
    const mutation = deferred<unknown>(); const reload = deferred<MaintenanceResult<ReportDetailData>>()
    mocks.regenerate.mockReturnValue(mutation.promise)
    const { wrapper, router } = await mountDetail()
    await wrapper.get('.report-detail > button').trigger('click')
    await wrapper.get('[role="dialog"] button').trigger('click')
    const refresh = wrapper.findAll('header button')[1]
    expect(refresh.attributes('disabled')).toBeDefined()
    await refresh.trigger('click'); await flushPromises()
    expect(mocks.getReport).toHaveBeenCalledTimes(1)
    expect(wrapper.get('.report-detail > button').attributes('disabled')).toBeDefined()
    expect(wrapper.get('.report-lifecycle-actions button').attributes('disabled')).toBeDefined()
    await router.push('/away'); await router.push('/reports/7'); await flushPromises()
    expect(wrapper.findAll('header button')[1].attributes('disabled')).toBeDefined()
    await wrapper.get('.report-detail > button').trigger('click')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    mocks.getReport.mockReturnValueOnce(reload.promise)
    mutation.resolve({}); await flushPromises()
    expect(wrapper.findAll('header button')[1].attributes('disabled')).toBeDefined()
    expect(mocks.regenerate).toHaveBeenCalledTimes(1)
    reload.resolve(result(detail)); await flushPromises()
    expect(wrapper.findAll('header button')[1].attributes('disabled')).toBeUndefined()
  })

  it('treats persisted sections with a null generation timestamp as generated', async () => {
    const { wrapper } = await mountDetail({ ...detail, generated_at: null, sections: [{ section_code: 'legacy', title: 'Persisted section', content: 'Evidence' }] })
    expect(wrapper.findComponent(ReportLifecycleActions).props('actions')).toContain('validate')
    expect(wrapper.findComponent(ReportLifecycleActions).props('actions')).not.toContain('generate')
    expect(wrapper.get('.report-detail > button').exists()).toBe(true)
  })

  it('does not refresh another report after its original reader is unregistered by route reuse', async () => {
    const mutation = deferred<unknown>()
    mocks.regenerate.mockReturnValue(mutation.promise)
    const { wrapper, router } = await mountDetail()
    const detailInstanceId = wrapper.findComponent(ReportDetail).vm.$.uid
    await wrapper.get('.report-detail > button').trigger('click')
    await wrapper.get('[role="dialog"] button').trigger('click')
    expect(pendingReportMutations.has(7)).toBe(true)
    mocks.getReport.mockImplementation((reportId: number) => Promise.resolve(result({ ...detail, report_id: reportId, title: `Report ${reportId}` })))
    await router.push('/reports/8'); await flushPromises()
    expect(wrapper.findComponent(ReportDetail).vm.$.uid).toBe(detailInstanceId)
    await wrapper.get('.report-detail > button').trigger('click')
    const report8Dialog = wrapper.get('[role="dialog"]').element
    mutation.resolve({}); await flushPromises()
    expect(mocks.getReport.mock.calls.map(([reportId]) => reportId)).toEqual([7, 8])
    expect(mocks.listReportVersions.mock.calls.map(([reportId]) => reportId)).toEqual([7, 8])
    expect(wrapper.get('[role="dialog"]').element).toBe(report8Dialog)
    expect(wrapper.get('[role="dialog"] button').attributes('disabled')).toBeUndefined()
    expect(pendingReportMutations.has(7)).toBe(false)
    expect(pendingReportMutations.has(8)).toBe(false)
    expect(mocks.regenerate).toHaveBeenCalledExactlyOnceWith(7)
  })

  it('renders backend-shaped public citation evidence without unknown private fields', () => {
    const wrapper = mount(ReportSections, { props: { sections: [], citations: [{ citation_id: 'cite-1', source_type: 'WEKNORA_DOCUMENT', source_name: 'Maintenance manual', document_version: 'v4', page_number: 12, chunk_reference: 'chunk-8', knowledge_node: 'node-3', database_record_json: { secret: 'private-record' }, token: 'private-token' }] as never } })
    for (const value of ['Maintenance manual', 'v4', '12', 'chunk-8', 'node-3']) expect(wrapper.text()).toContain(value)
    for (const value of ['undefined', 'private-record', 'private-token', 'database_record_json']) expect(wrapper.text()).not.toContain(value)
  })
  it('fails closed for malformed provenance and never renders private values', () => {
    const wrapper = mount(ReportProvenancePanel, {
      props: { sources: [{ type: 'AI_SESSION', id: 7, version: 'v2', lineage_id: 'lineage-1', digest: 'digest', source_snapshot_json: 'snapshot-secret', tenant_id: 'tenant-secret', database_record_json: 'database-secret', token: 'token-secret' }] as never },
    })
    expect(wrapper.get('.report-provenance-panel__unavailable').text()).toBe('maintenance.reports.presentation.noProvenance')
    for (const forbidden of ['source_snapshot_json', 'snapshot-secret', 'tenant_id', 'tenant-secret', 'database_record_json', 'database-secret', 'token', 'token-secret']) expect(wrapper.text()).not.toContain(forbidden)
    expect(wrapper.find('table').exists()).toBe(false)
  })

  it('renders immutable timeline lineage and generation evidence', () => {
    const wrapper = mount(ReportVersionTimeline, { props: { versions: [version] } })
    for (const value of ['maintenance.reports.presentation.parentVersion', '8', 'v3', 'MANUAL', '2026-09-07T00:00:00Z', 'content-digest']) expect(wrapper.text()).toContain(value)
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
    expect(wrapper.text()).toContain('maintenance.reports.detail.invalidId')
    expect(wrapper.text()).not.toContain('STALE report')
    expect(wrapper.text()).not.toContain('content-digest')
  })

  it('passes the loaded detail report ID to the viewer-permitted mounted export control', async () => {
    mocks.getReport.mockResolvedValue(result(detail)); mocks.listReportVersions.mockResolvedValue(result([version]))
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/reports/:reportId', name: 'maintenanceReportDetail', component: ReportDetail }] })
    await router.push('/reports/7'); await router.isReady()
    const wrapper = mount(RouterView, { global: { plugins: [router] } })
    await flushPromises()
    const exportActions = wrapper.findComponent(ReportExportActions)
    expect(exportActions.exists()).toBe(true)
    expect(exportActions.props('reportId')).toBe(detail.report_id)
    expect(exportActions.props('actions')).toContain('export')
    expect(exportActions.text()).toContain('maintenance.reports.actions.export')
  })
})
