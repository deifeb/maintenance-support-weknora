import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { createMemoryHistory, createRouter, RouterView, type LocationQueryRaw } from 'vue-router'
import ReportCenter from '@/views/maintenance/reports/ReportCenter.vue'
import ReportListTable from '../ReportListTable.vue'
import ReportFilterBar from '../ReportFilterBar.vue'
import ReportExportActions from '../ReportExportActions.vue'
import { getReportActions, type ReportRole } from '../report-actions'
import { normalizeReportListQuery, REPORT_JOB_STATUSES, type ReportListItem, type ReportListQuery } from '../report-types'
import type { MaintenanceResult, PageData } from '@/api/maintenance/types'

const mocks = vi.hoisted(() => ({ listReports: vi.fn(), exportReport: vi.fn(), hasRole: vi.fn() }))
vi.mock('@/api/maintenance/reports', () => ({ reportApi: { listReports: mocks.listReports, exportReport: mocks.exportReport } }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ hasRole: mocks.hasRole }) }))
vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string, values?: { requestId?: string }) => values?.requestId ? `${key}:${values.requestId}` : key, locale: ref('en-US') }),
}))

enableAutoUnmount(afterEach)
afterEach(() => vi.restoreAllMocks())
beforeEach(() => {
  mocks.listReports.mockReset()
  mocks.exportReport.mockReset()
  mocks.hasRole.mockReset().mockReturnValue(false)
})

const path = '/platform/maintenance/reports'
const stateKey = (state: string) => `maintenance.reports.${state}`
const actionKey = (action: string) => stateKey(`actions.${action}`)
const defaults: ReportListQuery = { page: 1, page_size: 20, sort_by: 'created_at', sort_order: 'desc' }
const item: ReportListItem = {
  report_id: 7, report_code: 'RPT-7', title: 'Status report',
  report_type: 'DEMAND_CALCULATION', job_status: 'READY_FOR_REVIEW',
  progress_percent: 100, created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-02T00:00:00Z', session_id: null, error_code: null,
  latest_version: { id: 3, version_number: 1, status: 'REVIEWED' },
}
type ListResult = MaintenanceResult<PageData<ReportListItem>>

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

function response(items: ReportListItem[] = [item], page = 1, pages = 1): ListResult {
  return {
    data: { items, page, page_size: 20, total: pages > 1 ? (pages - 1) * 20 + items.length : items.length, pages },
    meta: { request_id: 'test-request', tenant_id: 'test-tenant' },
  }
}

function request() {
  const pending = deferred<ListResult>()
  mocks.listReports.mockReturnValueOnce(pending.promise)
  return pending
}

async function mountCenter(query: LocationQueryRaw = {}) {
  // A memory router isolates navigation from the application router and Task 3.
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path, name: 'maintenanceReports', component: ReportCenter },
      { path: '/test/reports/:reportId', name: 'maintenanceReportDetail', component: defineComponent({ render: () => h('div', 'Detail fixture') }) },
    ],
  })
  await router.push({ path, query })
  await router.isReady()
  const push = vi.spyOn(router, 'push')
  const wrapper = mount(RouterView, { global: { plugins: [router] } })
  await flushPromises()
  expect(wrapper.findComponent(ReportCenter).exists()).toBe(true)
  return { wrapper, router, push }
}

describe('report center query and navigation', () => {
  it('normalizes defaults, blank filters and unsupported backend query fields', () => {
    expect(normalizeReportListQuery({
      page: 0, page_size: 201, keyword: ' ', report_type: 'fake', job_status: 'fake',
      version_status: 'fake', source_type: ' FUTURE ', source_version: 'x'.repeat(129),
      source_id: -1, session_id: 1.5, sort_by: 'updated_at', sort_order: 'invalid', generator: 'fake',
    })).toEqual(defaults)
  })

  it('preserves supported hidden source, sort and page size constraints when applying controls', async () => {
    const query: ReportListQuery = { ...defaults, page: 4, page_size: 50, source_type: 'AI_SESSION', source_id: 42, source_version: 'v2', session_id: 7, scenario_version_id: 8, calculation_run_id: 9, review_run_id: 10, sort_by: 'title', sort_order: 'asc' }
    const wrapper = mount(ReportFilterBar, { props: { query } })
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('apply')?.[0]).toEqual([query])
    await wrapper.get('input').setValue(' weekly ')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('apply')?.[1]).toEqual([{ ...query, keyword: 'weekly', page: 1 }])
  })

  it('allows exactly the backend source enum and rejects unsupported route and control values', async () => {
    const values = ['AI_SESSION', 'SCENARIO_VERSION', 'CALCULATION_RUN', 'CALCULATION_GROUP', 'DEMAND_LIST', 'DEMAND_REVIEW', 'ALLOCATION_PLAN', 'INVENTORY_STOCKTAKE']
    const wrapper = mount(ReportFilterBar, { props: { query: defaults } })
    expect(wrapper.findAll('select').at(-1)!.findAll('option').map((option) => option.attributes('value'))).toEqual(['', ...values])
    for (const value of values) expect(normalizeReportListQuery({ source_type: value }).source_type).toBe(value)
    for (const value of ['SESSION', 'FUTURE', 'unsupported']) {
      expect(normalizeReportListQuery({ source_type: value })).not.toHaveProperty('source_type')
      await wrapper.setProps({ query: { ...defaults, source_type: value } as never })
      await wrapper.get('form').trigger('submit')
      expect(wrapper.emitted('apply')?.at(-1)?.[0]).not.toHaveProperty('source_type')
    }
  })

  it('rejects report job statuses outside the C3 API allowlist', () => {
    expect(REPORT_JOB_STATUSES).toEqual([
      'CREATED', 'GENERATING_SECTIONS', 'VALIDATING_NUMBERS',
      'READY_FOR_REVIEW', 'PARTIALLY_COMPLETED', 'FAILED', 'FINALIZED',
    ])
    for (const jobStatus of ['BUILDING_SKELETON', 'VALIDATING_CITATIONS']) {
      expect(normalizeReportListQuery({ job_status: jobStatus })).not.toHaveProperty('job_status')
    }
  })

  it('dispatches a backend-valid normalized query from the URL', async () => {
    const pending = request()
    const { wrapper } = await mountCenter({
      page: '0', page_size: '201', keyword: '  quarterly report  ',
      report_type: 'MANAGEMENT_DECISION', job_status: 'PARTIALLY_COMPLETED', version_status: 'REVIEWED',
      source_type: ' AI_SESSION ', source_id: '42', source_version: ' v2 ',
      session_id: '7', scenario_version_id: '8', calculation_run_id: '9', review_run_id: '10',
      sort_by: 'title', sort_order: 'asc', generator: 'fake', date_from: '2026-01-01',
    })
    expect(mocks.listReports).toHaveBeenCalledExactlyOnceWith({
      ...defaults, keyword: 'quarterly report', report_type: 'MANAGEMENT_DECISION',
      job_status: 'PARTIALLY_COMPLETED', version_status: 'REVIEWED',
      source_type: 'AI_SESSION', source_id: 42, source_version: 'v2',
      session_id: 7, scenario_version_id: 8, calculation_run_id: 9, review_run_id: 10,
      sort_by: 'title', sort_order: 'asc',
    })
    expect(wrapper.get('input').element.value).toBe('quarterly report')
    pending.resolve(response())
    await flushPromises()
    expect(wrapper.get('tbody tr').text()).toContain(item.report_code)
  })

  it('opens a clicked row through the named detail route with its report ID', async () => {
    const pending = request()
    const { wrapper, router, push } = await mountCenter()
    pending.resolve(response())
    await flushPromises()
    await wrapper.get('tbody tr').trigger('click')
    await flushPromises()
    expect(push).toHaveBeenCalledExactlyOnceWith({ name: 'maintenanceReportDetail', params: { reportId: 7 } })
    expect(router.currentRoute.value.name).toBe('maintenanceReportDetail')
    expect(router.currentRoute.value.params).toEqual({ reportId: '7' })
    expect(wrapper.text()).toBe('Detail fixture')
  })

  it('uses authenticated admin permissions in the mounted list', async () => {
    mocks.hasRole.mockImplementation((role: string) => role === 'admin')
    const pending = request()
    const { wrapper } = await mountCenter()
    pending.resolve(response())
    await flushPromises()
    expect(wrapper.findComponent(ReportListTable).props('role')).toBe('ADMIN')
    expect(wrapper.get('tbody').text()).not.toContain(actionKey('finalize'))
  })

  it('dispatches next and previous page queries while preserving filters', async () => {
    const first = request(), second = request(), third = request()
    const { wrapper, router } = await mountCenter({ source_type: 'AI_SESSION', source_id: '7', keyword: 'weekly' })
    first.resolve(response([item], 1, 2))
    await flushPromises()
    expect(wrapper.get('footer span').text()).toBe('1 / 2')
    expect(wrapper.findAll('footer button')[0].attributes('disabled')).toBeDefined()
    await wrapper.findAll('footer button')[1].trigger('click')
    await flushPromises()
    const expected = { ...defaults, page: 2, source_type: 'AI_SESSION', source_id: 7, keyword: 'weekly' }
    expect(mocks.listReports).toHaveBeenNthCalledWith(2, expected)
    expect(router.currentRoute.value.query).toEqual(Object.fromEntries(Object.entries(expected).map(([key, value]) => [key, String(value)])))
    second.resolve(response([item], 2, 2))
    await flushPromises()
    expect(wrapper.get('footer span').text()).toBe('2 / 2')
    expect(wrapper.findAll('footer button')[1].attributes('disabled')).toBeDefined()
    await wrapper.findAll('footer button')[0].trigger('click')
    await flushPromises()
    expect(mocks.listReports).toHaveBeenNthCalledWith(3, { ...expected, page: 1 })
    third.resolve(response([item], 1, 2))
    await flushPromises()
    expect(wrapper.get('footer span').text()).toBe('1 / 2')
  })
})

describe('report table actions', () => {
  for (const role of ['VIEWER', 'CONTRIBUTOR', 'ADMIN'] as const satisfies readonly ReportRole[]) {
    for (const finalized of [false, true]) {
      it(`renders only allowed row actions and emits them for ${role}, finalized=${finalized}`, async () => {
        const report: ReportListItem = finalized
          ? { ...item, job_status: 'FINALIZED', latest_version: { ...item.latest_version!, status: 'FINAL' } }
          : item
        const wrapper = mount(ReportListTable, { props: { reports: [report], role } })
        const allowed = getReportActions({ role, jobStatus: report.job_status, versionStatus: report.latest_version!.status })
        // versions/create belong to other entry points, not the row action surface.
        const expected = allowed.filter((action) => action !== 'versions' && action !== 'create')
        const buttons = wrapper.findAll('tbody button')
        expect(buttons.map((button) => button.text())).toEqual(expected.map(actionKey))
        for (const [index, action] of expected.entries()) {
          await buttons[index].trigger('click')
          expect(wrapper.emitted(action === 'view' ? 'open' : action)).toEqual([[report.report_id]])
        }
        // Export/workflow clicks must not also bubble into row navigation.
        expect(wrapper.emitted('open')).toEqual([[report.report_id]])
        expect(wrapper.emitted('regenerate')).toBeUndefined()
      })
    }
  }

  it('keeps keyboard export activation inside the action cell and does not open the row', async () => {
    const wrapper = mount(ReportListTable, { props: { reports: [item], role: 'VIEWER' } })
    const exportButton = wrapper.findAll('tbody button').find((button) => button.text() === actionKey('export'))!
    await exportButton.trigger('keydown.enter')
    await exportButton.trigger('keydown.space')
    await exportButton.trigger('click')
    expect(wrapper.emitted('export')).toEqual([[item.report_id]])
    expect(wrapper.emitted('open')).toBeUndefined()
  })
})

describe('report export production wiring', () => {
  it('passes the selected list report ID to a viewer-permitted mounted export control without navigating', async () => {
    const pending = request()
    const { wrapper, push } = await mountCenter()
    pending.resolve(response())
    await flushPromises()
    const exportButton = wrapper.findAll('tbody button').find((button) => button.text() === actionKey('export'))!
    await exportButton.trigger('keydown.enter')
    await exportButton.trigger('click')
    await flushPromises()
    const exportActions = wrapper.findComponent(ReportExportActions)
    expect(exportActions.exists()).toBe(true)
    expect(exportActions.props('reportId')).toBe(item.report_id)
    expect(exportActions.props('actions')).toContain('export')
    expect(exportActions.text()).toContain(actionKey('export'))
    expect(push).not.toHaveBeenCalled()
  })

  it('does not emit exported and renders only safe failure feedback from the mounted list control', async () => {
    mocks.exportReport.mockRejectedValue({ code: 'PRIVATE_BACKEND_DETAIL', message: 'C:\\secret\\report.docx', request_id: 'request-42' })
    const pending = request()
    const { wrapper, push } = await mountCenter()
    pending.resolve(response())
    await flushPromises()
    await wrapper.findAll('tbody button').find((button) => button.text() === actionKey('export'))!.trigger('click')
    await flushPromises()
    const exportActions = wrapper.findComponent(ReportExportActions)
    await exportActions.find('button').trigger('click')
    await flushPromises()
    expect(exportActions.emitted('exported')).toBeUndefined()
    expect(exportActions.get('[role="alert"]').text()).toContain('maintenance.reports.errors.generic')
    expect(exportActions.text()).toContain('request-42')
    expect(exportActions.text()).not.toContain('secret\\report.docx')
    expect(push).not.toHaveBeenCalled()
  })

  it('cleans up and maps a browser click failure without emitting exported', async () => {
    mocks.exportReport.mockResolvedValue({ blob: new Blob(['report']), filename: 'RPT-7-v1.docx', contentType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
    const createObjectURL = vi.fn(() => 'blob:report')
    const revokeObjectURL = vi.fn()
    const createDescriptor = Object.getOwnPropertyDescriptor(URL, 'createObjectURL')
    const revokeDescriptor = Object.getOwnPropertyDescriptor(URL, 'revokeObjectURL')
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectURL })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => { throw { code: 'PRIVATE_BACKEND_DETAIL', message: 'C:\\secret\\report.docx', request_id: 'request-42' } })
    try {
      const wrapper = mount(ReportExportActions, { props: { reportId: item.report_id, actions: ['export'] } })
      await wrapper.get('button').trigger('click')
      await flushPromises()
      expect(wrapper.emitted('exported')).toBeUndefined()
      expect(wrapper.get('[role="alert"]').text()).toContain('maintenance.reports.errors.generic')
      expect(wrapper.text()).toContain('request-42')
      expect(wrapper.text()).not.toContain('secret\\report.docx')
      expect(createObjectURL).toHaveBeenCalledOnce()
      expect(revokeObjectURL).toHaveBeenCalledWith('blob:report')
      expect(click).toHaveBeenCalledOnce()
    } finally {
      if (createDescriptor) Object.defineProperty(URL, 'createObjectURL', createDescriptor)
      else delete (URL as typeof URL & { createObjectURL?: unknown }).createObjectURL
      if (revokeDescriptor) Object.defineProperty(URL, 'revokeObjectURL', revokeDescriptor)
      else delete (URL as typeof URL & { revokeObjectURL?: unknown }).revokeObjectURL
    }
  })
})

describe('report center asynchronous DOM states', () => {
  it('renders loading without empty results, rows, errors or pagination until resolution', async () => {
    const pending = request()
    const { wrapper } = await mountCenter()
    expect(wrapper.get('.report-center__state').text()).toBe(stateKey('loading'))
    expect(wrapper.text()).not.toContain(stateKey('empty'))
    expect(wrapper.find('tbody tr').exists()).toBe(false)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.find('footer').exists()).toBe(false)
    pending.resolve(response())
    await flushPromises()
    expect(wrapper.find('.report-center__state').exists()).toBe(false)
    expect(wrapper.get('tbody tr').text()).toContain(item.report_code)
  })

  it('renders empty results only after a successful empty response', async () => {
    const pending = request()
    const { wrapper } = await mountCenter()
    pending.resolve(response([], 1, 0))
    await flushPromises()
    expect(wrapper.get('.report-center__state').text()).toBe(stateKey('empty'))
    expect(wrapper.text()).not.toContain(stateKey('loading'))
    expect(wrapper.find('tbody tr').exists()).toBe(false)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.find('footer').exists()).toBe(false)
  })

  it('clears old rows and pages during reload and renders an exclusive error with retry', async () => {
    const first = request(), second = request(), retry = request()
    const { wrapper, router } = await mountCenter()
    first.resolve(response([item], 1, 3))
    await flushPromises()
    expect(wrapper.get('tbody tr').text()).toContain(item.report_code)
    expect(wrapper.get('footer span').text()).toBe('1 / 3')
    await router.push({ path, query: { keyword: 'broken' } })
    await flushPromises()
    expect(wrapper.get('.report-center__state').text()).toBe(stateKey('loading'))
    expect(wrapper.find('tbody tr').exists()).toBe(false)
    expect(wrapper.find('footer').exists()).toBe(false)
    second.reject({ code: 'UNKNOWN', message: 'Network unavailable secret', request_id: 'r-private' })
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('maintenance.reports.errors.generic')
    expect(wrapper.get('[role="alert"]').text()).toContain('r-private')
    expect(wrapper.get('[role="alert"]').text()).not.toContain('Network unavailable secret')
    expect(wrapper.findComponent(ReportListTable).exists()).toBe(false)
    expect(wrapper.find('table').exists()).toBe(false)
    expect(wrapper.find('tbody tr').exists()).toBe(false)
    expect(wrapper.find('footer').exists()).toBe(false)
    expect(wrapper.find('.report-center__state').exists()).toBe(false)
    expect(wrapper.text()).not.toContain(item.report_code)
    expect(wrapper.text()).not.toContain(stateKey('empty'))
    expect(wrapper.text()).not.toContain(stateKey('loading'))
    await wrapper.get('[role="alert"] button').trigger('click')
    expect(mocks.listReports).toHaveBeenNthCalledWith(3, { ...defaults, keyword: 'broken' })
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    retry.resolve(response())
    await flushPromises()
    expect(wrapper.get('tbody tr').text()).toContain(item.report_code)
  })

  it.each(['resolve', 'reject'] as const)('ignores stale %s after the current request succeeds', async (settlement) => {
    const old = request(), current = request()
    const { wrapper, router } = await mountCenter()
    await router.push({ path, query: { page: '2' } })
    await flushPromises()
    current.resolve(response([{ ...item, report_code: 'CURRENT' }], 2, 2))
    await flushPromises()
    expect(wrapper.get('tbody tr').text()).toContain('CURRENT')
    if (settlement === 'resolve') old.resolve(response([{ ...item, report_code: 'STALE' }], 1, 9))
    else old.reject(new Error('Stale failure'))
    await flushPromises()
    expect(wrapper.get('tbody tr').text()).toContain('CURRENT')
    expect(wrapper.text()).not.toContain('STALE')
    expect(wrapper.get('footer span').text()).toBe('2 / 2')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.find('.report-center__state').exists()).toBe(false)
    expect(mocks.listReports).toHaveBeenCalledTimes(2)
  })

  it('does not stop current loading when an older request settles first', async () => {
    const old = request(), current = request()
    const { wrapper, router } = await mountCenter()
    await router.push({ path, query: { page: '2' } })
    await flushPromises()
    old.resolve(response([{ ...item, report_code: 'STALE' }]))
    await flushPromises()
    expect(wrapper.get('.report-center__state').text()).toBe(stateKey('loading'))
    expect(wrapper.find('tbody tr').exists()).toBe(false)
    current.resolve(response([], 2, 0))
    await flushPromises()
    expect(wrapper.get('.report-center__state').text()).toBe(stateKey('empty'))
  })
})
