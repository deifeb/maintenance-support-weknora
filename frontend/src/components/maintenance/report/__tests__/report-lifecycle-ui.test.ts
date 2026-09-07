import { afterEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { ref } from 'vue'

import ReportGenerationDialog from '../ReportGenerationDialog.vue'
import ReportLifecycleActions from '../ReportLifecycleActions.vue'
import ReportRegenerateDialog from '../ReportRegenerateDialog.vue'
import { registerReportReader } from '../report-mutation-state'

const mocks = vi.hoisted(() => ({
  create: vi.fn(), generate: vi.fn(), validate: vi.fn(), finalize: vi.fn(), regenerate: vi.fn(),
}))
vi.mock('@/api/maintenance/reports', () => ({ reportApi: { createReportJob: mocks.create, generateReport: mocks.generate, validateReport: mocks.validate, finalizeReport: mocks.finalize, regenerateReport: mocks.regenerate } }))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string, values?: Record<string, string>) => values ? `${key}:${values.requestId}` : key }) }))

enableAutoUnmount(afterEach)
afterEach(() => { vi.resetAllMocks() })
const deferred = <T,>() => { let resolve!: (value: T) => void; const promise = new Promise<T>((done) => { resolve = done }); return { promise, resolve } }

async function fillDemandCalculation(wrapper: ReturnType<typeof mount>, sourceType: string) {
  await wrapper.find('input').setValue('Demand report')
  await wrapper.find('select').setValue('DEMAND_CALCULATION')
  await wrapper.get('fieldset button').trigger('click')
  const selects = wrapper.findAll('.report-generation-dialog__source select')
  await selects[0].setValue(sourceType)
  const inputs = wrapper.findAll('.report-generation-dialog__source input')
  await inputs[0].setValue('7'); await inputs[1].setValue('v1')
}

describe('report lifecycle production components', () => {
  it('keeps refresh attached to the mutated report when the component receives a new report ID', async () => {
    const mutation = deferred<unknown>(); mocks.validate.mockReturnValue(mutation.promise)
    const read42 = vi.fn().mockResolvedValue(undefined), read43 = vi.fn().mockResolvedValue(undefined)
    const remove42 = registerReportReader(42, read42), remove43 = registerReportReader(43, read43)
    try {
      const wrapper = mount(ReportLifecycleActions, { props: { reportId: 42, jobStatus: 'VALIDATING_NUMBERS', versionStatus: 'DRAFT', versionGenerated: true, actions: ['validate'], refresh: vi.fn() } })
      await wrapper.get('button').trigger('click')
      await wrapper.setProps({ reportId: 43 })
      mutation.resolve({}); await flushPromises()
      expect(read42).toHaveBeenCalledTimes(1)
      expect(read43).not.toHaveBeenCalled()
    } finally { remove42(); remove43() }
  })
  it('rejects a policy-disallowed source combination before create and submits a valid combination', async () => {
    mocks.create.mockResolvedValue({})
    const wrapper = mount(ReportGenerationDialog, { props: { open: true, refresh: vi.fn() } })
    await fillDemandCalculation(wrapper, 'AI_SESSION')
    await wrapper.findAll('button').find((button) => button.text() === 'maintenance.reports.actions.create')!.trigger('click')
    expect(mocks.create).not.toHaveBeenCalled()
    expect(wrapper.get('[role="alert"]').text()).toContain('maintenance.reports.createDialog.invalid')
    await wrapper.find('.report-generation-dialog__source select').setValue('CALCULATION_RUN')
    await wrapper.findAll('button').find((button) => button.text() === 'maintenance.reports.actions.create')!.trigger('click')
    await flushPromises()
    expect(mocks.create).toHaveBeenCalledWith(expect.objectContaining({ report_type: 'DEMAND_CALCULATION', source_refs: [{ type: 'CALCULATION_RUN', id: 7, version: 'v1' }] }))
  })

  it('serializes lifecycle mutation through an awaited parent refresh and hides disallowed actions', async () => {
    const refresh = deferred<void>(); mocks.validate.mockResolvedValue({})
    const wrapper = mount(ReportLifecycleActions, { props: { reportId: 42, jobStatus: 'VALIDATING_NUMBERS', versionStatus: 'DRAFT', versionGenerated: true, actions: ['view', 'validate'], refresh: () => refresh.promise } })
    expect(wrapper.text()).not.toContain('maintenance.reports.actions.generate')
    const button = wrapper.get('button'); await button.trigger('click'); await button.trigger('click')
    expect(mocks.validate).toHaveBeenCalledTimes(1); expect(button.attributes('disabled')).toBeDefined()
    refresh.resolve(); await flushPromises(); expect(button.attributes('disabled')).toBeUndefined()
  })

  it('maps sensitive lifecycle errors to a key and request ID without rendering backend text', async () => {
    mocks.validate.mockRejectedValue({ code: 'UNKNOWN', message: 'secret-backend-value', request_id: 'r-secret' })
    const wrapper = mount(ReportLifecycleActions, { props: { reportId: 42, jobStatus: 'VALIDATING_NUMBERS', versionStatus: 'DRAFT', versionGenerated: true, actions: ['validate'], refresh: vi.fn() } })
    await wrapper.get('button').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('maintenance.reports.errors.generic')
    expect(wrapper.text()).toContain('r-secret')
    expect(wrapper.text()).not.toContain('secret-backend-value')
  })

  it('does not mount or invoke regenerate without a granted action and serializes an allowed refresh', async () => {
    const absent = mount(ReportRegenerateDialog, { props: { open: true, reportId: 42, allowed: false, refresh: vi.fn() } })
    expect(absent.find('[role="dialog"]').exists()).toBe(false); expect(mocks.regenerate).not.toHaveBeenCalled()
    const refresh = deferred<void>(); mocks.regenerate.mockResolvedValue({})
    const wrapper = mount(ReportRegenerateDialog, { props: { open: true, reportId: 42, allowed: true, refresh: () => refresh.promise } })
    await wrapper.findAll('button')[0].trigger('click'); await wrapper.findAll('button')[0].trigger('click')
    expect(mocks.regenerate).toHaveBeenCalledTimes(1); expect(wrapper.findAll('button')[0].attributes('disabled')).toBeDefined()
    refresh.resolve(); await flushPromises()
  })
})
