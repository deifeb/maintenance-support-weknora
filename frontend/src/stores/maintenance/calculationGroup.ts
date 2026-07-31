import { defineStore } from 'pinia'
import {
  ref,
  shallowRef,
} from 'vue'

import {
  calculationGroupApi,
  type CalculationGroup,
  type CalculationGroupCreateRequest,
  type CalculationGroupEvent,
  type CalculationGroupListQuery,
} from '../../api/maintenance/calculation-groups'
import {
  normalizeMaintenanceError,
} from '../../api/maintenance/client'
import type {
  MaintenanceClientError,
  MaintenanceResult,
  PageData,
} from '../../api/maintenance/types'
import {
  initialCalculationGroupEventState,
  reduceGroupEvent,
} from '../../components/maintenance/calculation/calculation-group-reducer'
import {
  createResumableSSE,
  type ResumableSSEConnectionState,
  type ResumableSSEController,
} from '../../composables/maintenance/useResumableSSE'

export interface CalculationGroupStoreApi {
  create(
    request: CalculationGroupCreateRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<CalculationGroup>>
  list(
    query?: CalculationGroupListQuery,
  ): Promise<MaintenanceResult<
    PageData<CalculationGroup>
  >>
  get(
    groupId: number,
  ): Promise<MaintenanceResult<CalculationGroup>>
  retryFailed(
    groupId: number,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<CalculationGroup>>
  cancelRunning(
    groupId: number,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<CalculationGroup>>
  getEvents(
    groupId: number,
    afterSequence?: number,
  ): Promise<MaintenanceResult<
    CalculationGroupEvent[]
  >>
}

type SSEFactory = () => ResumableSSEController

const terminalStatuses = new Set([
  'COMPLETED',
  'PARTIALLY_COMPLETED',
  'FAILED',
  'CANCELLED',
  'INTERRUPTED',
])

export function createCalculationGroupState(
  api: CalculationGroupStoreApi =
    calculationGroupApi,
  createSSE: SSEFactory = () => createResumableSSE(),
) {
  const group = ref<CalculationGroup | null>(null)
  const groups = ref<CalculationGroup[]>([])
  const total = ref(0)
  const currentSequence = ref(0)
  const connectionState = ref<
    ResumableSSEConnectionState
  >('idle')
  const loading = ref(false)
  const mutating = ref(false)
  const error = ref<MaintenanceClientError | null>(
    null,
  )
  const selectedStatus = ref<
    CalculationGroup['status'] | undefined
  >(undefined)
  const page = ref(1)
  const pageSize = ref(20)
  const eventState = shallowRef(
    initialCalculationGroupEventState(0),
  )
  let requestGeneration = 0
  const sse = createSSE()

  function connect(): void {
    const current = group.value
    if (
      current === null
      || terminalStatuses.has(current.status)
    ) {
      sse.stop()
      connectionState.value = 'stopped'
      return
    }
    sse.start({
      groupId: current.id,
      lastSequence: currentSequence.value,
      onStateChange(value) {
        connectionState.value = value
      },
      onError(value) {
        error.value = normalizeMaintenanceError(value)
      },
      onEvent(value) {
        applyEvent({
          id: value.sequence,
          group_id: value.groupId,
          child_id: value.childId ?? null,
          sequence: value.sequence,
          event_type: value.type,
          payload: value.payload,
          occurred_at: value.occurredAt ?? '',
        })
      },
    })
  }

  function applyGroup(value: CalculationGroup): void {
    group.value = value
    currentSequence.value = value.last_event_sequence
    eventState.value = initialCalculationGroupEventState(
      value.id,
      value,
    )
  }

  function applyEvent(value: CalculationGroupEvent): void {
    const reduced = reduceGroupEvent(
      eventState.value,
      value,
    )
    if (reduced === eventState.value) return
    eventState.value = reduced
    currentSequence.value = reduced.lastSequence
    group.value = reduced.group
    if (
      reduced.requiresReload
      && group.value !== null
    ) {
      void load(group.value.id)
      return
    }
    if (
      group.value !== null
      && terminalStatuses.has(group.value.status)
    ) {
      sse.stop()
    }
  }

  async function load(groupId: number): Promise<void> {
    const generation = ++requestGeneration
    loading.value = true
    error.value = null
    try {
      const response = await api.get(groupId)
      if (generation !== requestGeneration) return
      applyGroup(response.data)
      connect()
    } catch (value) {
      if (generation === requestGeneration) {
        error.value = normalizeMaintenanceError(value)
      }
      throw value
    } finally {
      if (generation === requestGeneration) {
        loading.value = false
      }
    }
  }

  async function list(): Promise<void> {
    const generation = ++requestGeneration
    loading.value = true
    error.value = null
    try {
      const response = await api.list({
        page: page.value,
        page_size: pageSize.value,
        status: selectedStatus.value,
      })
      if (generation !== requestGeneration) return
      groups.value = response.data.items
      total.value = response.data.total
    } catch (value) {
      if (generation === requestGeneration) {
        error.value = normalizeMaintenanceError(value)
      }
      throw value
    } finally {
      if (generation === requestGeneration) {
        loading.value = false
      }
    }
  }

  function beginMutation(): void {
    if (mutating.value) {
      throw new Error(
        'Calculation group mutation is already in progress',
      )
    }
    mutating.value = true
    error.value = null
  }

  async function runMutation(
    operation: () => Promise<
      MaintenanceResult<CalculationGroup>
    >,
  ): Promise<CalculationGroup> {
    beginMutation()
    try {
      const response = await operation()
      applyGroup(response.data)
      connect()
      return response.data
    } catch (value) {
      error.value = normalizeMaintenanceError(value)
      throw value
    } finally {
      mutating.value = false
    }
  }

  function create(
    request: CalculationGroupCreateRequest,
    idempotencyKey: string,
  ): Promise<CalculationGroup> {
    return runMutation(
      () => api.create(request, idempotencyKey),
    )
  }

  async function retryFailed(
    idempotencyKey: string,
  ): Promise<CalculationGroup> {
    if (mutating.value) {
      throw new Error(
        'Calculation group mutation is already in progress',
      )
    }
    const current = group.value
    if (current === null) {
      throw new Error('Calculation group is not loaded')
    }
    return runMutation(
      () => api.retryFailed(
        current.id,
        idempotencyKey,
      ),
    )
  }

  async function cancelRunning(
    idempotencyKey: string,
  ): Promise<CalculationGroup> {
    if (mutating.value) {
      throw new Error(
        'Calculation group mutation is already in progress',
      )
    }
    const current = group.value
    if (current === null) {
      throw new Error('Calculation group is not loaded')
    }
    return runMutation(
      () => api.cancelRunning(
        current.id,
        idempotencyKey,
      ),
    )
  }

  function reconnect(): void {
    connect()
  }

  function dispose(): void {
    requestGeneration += 1
    sse.stop()
  }

  return {
    group,
    groups,
    total,
    currentSequence,
    connectionState,
    loading,
    mutating,
    error,
    selectedStatus,
    page,
    pageSize,
    load,
    list,
    create,
    retryFailed,
    cancelRunning,
    reconnect,
    applyEvent,
    dispose,
  }
}

export const useCalculationGroupStore = defineStore(
  'maintenanceCalculationGroup',
  () => createCalculationGroupState(),
)
