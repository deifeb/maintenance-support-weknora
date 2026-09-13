import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { reactive } from 'vue'

import PlanExecutionSummary from '../PlanExecutionSummary.vue'

const mocks = vi.hoisted(() => ({
  allocationStore: {
    planDetail: {
      item: null as Record<string, unknown> | null,
      loading: false,
      error: null,
    },
    fetchPlanDetail: vi.fn(),
    executePlan: vi.fn(),
    retryPlan: vi.fn(),
  },
  permissionsStore: {
    can: vi.fn(() => true),
  },
  route: {
    params: { planId: '71' },
  },
  router: {
    push: vi.fn(),
    replace: vi.fn(),
  },
}))

vi.mock('@/stores/maintenance/allocation', () => ({
  useAllocationStore: () => mocks.allocationStore,
}))
vi.mock('@/stores/maintenance/permissions', () => ({
  useMaintenancePermissionsStore: () => mocks.permissionsStore,
}))
vi.mock('vue-router', () => ({
  useRoute: () => mocks.route,
  useRouter: () => mocks.router,
}))

enableAutoUnmount(afterEach)

const execution = {
  plan_id: 71,
  execution_id: 902,
  execution_as_of: '2026-08-27T12:00:00Z',
  status: 'PARTIALLY_COMPLETED' as const,
  version: 4,
  line_results: [
    {
      line_id: 101,
      outcome: 'CONFLICT' as const,
      reservation_id: null,
      error_code: 'ALLOCATION_INVENTORY_CONFLICT',
      cause_code: 'INVENTORY_VERSION_CONFLICT',
      retryable: true,
      suggested_action: 'retry',
      details: {},
    },
    {
      line_id: 102,
      outcome: 'CONFLICT' as const,
      reservation_id: null,
      error_code: 'ALLOCATION_INVENTORY_CONFLICT',
      cause_code: 'RULE_VERSION_CONFLICT',
      retryable: false,
      suggested_action: 'regenerate',
      details: {},
    },
    {
      line_id: 103,
      outcome: 'RESERVED' as const,
      reservation_id: 44,
      error_code: null,
      cause_code: null,
      retryable: false,
      suggested_action: null,
      details: {},
    },
  ],
}

describe('allocation execution retry controls', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.route.params.planId = '71'
  })

  it('renders retry only for retryable conflicts and emits the line id', async () => {
    const wrapper = mount(PlanExecutionSummary, {
      props: {
        execution,
        canRegenerate: true,
        canRetry: true,
        retryingLineId: null,
      },
    })

    const retry = wrapper.get('tbody button')
    expect(retry.text()).toBe('Retry line')
    expect(wrapper.findAll('button')).toHaveLength(2)
    expect(wrapper.findAll('button')[0].text()).toBe('Regenerate plan')

    await retry.trigger('click')
    expect(wrapper.emitted('retry')).toEqual([[101]])
    expect(wrapper.findAll('tr[data-outcome="CONFLICT"] button')).toHaveLength(1)
  })

  it('disables the retry command while its line is pending', () => {
    const wrapper = mount(PlanExecutionSummary, {
      props: {
        execution,
        canRegenerate: true,
        canRetry: true,
        retryingLineId: 101,
      },
    })

    const retry = wrapper.get('tbody button')
    expect(retry.attributes('disabled')).toBeDefined()
    expect(retry.text()).toBe('Retrying…')
  })
})

describe('allocation plan detail retry command', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.permissionsStore.can.mockReturnValue(true)
    mocks.allocationStore.planDetail.item = reactive({
      id: 71,
      source_demand_list_id: 41,
      source_demand_list_version: 8,
      rule_id: 17,
      inventory_fingerprint: 'inventory-71',
      status: 'CONFIRMED',
      version: 5,
      created_at: '2026-08-27T10:00:00Z',
      updated_at: '2026-08-27T10:00:00Z',
      lines: [],
    })
    mocks.allocationStore.fetchPlanDetail.mockResolvedValue(undefined)
    mocks.allocationStore.executePlan.mockResolvedValue(execution)
    vi.spyOn(window, 'confirm').mockReturnValue(true)
  })

  it('retries the selected line with the current plan version and refreshes detail', async () => {
    const retryDeferred = deferred<typeof execution>()
    mocks.allocationStore.retryPlan.mockReturnValue(retryDeferred.promise)

    const { default: AllocationPlanDetail } = await import(
      '@/views/maintenance/inventory-gap/AllocationPlanDetail.vue'
    )
    const wrapper = mount(AllocationPlanDetail, {
      global: { stubs: { AllocationPlanTable: true } },
    })

    await wrapper.get('.allocation-plan-detail__actions button').trigger('click')
    await flushPromises()
    const retry = wrapper.get('tbody button')
    expect(retry.text()).toBe('Retry line')

    await retry.trigger('click')
    await wrapper.vm.$nextTick()
    expect(mocks.allocationStore.retryPlan).toHaveBeenCalledWith(71, {
      expected_version: 5,
      line_ids: [101],
    })
    expect(retry.attributes('disabled')).toBeDefined()

    retryDeferred.resolve(execution)
    await flushPromises()
    expect(mocks.allocationStore.fetchPlanDetail).toHaveBeenCalledTimes(3)
    expect(retry.attributes('disabled')).toBeUndefined()
  })
})

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}
