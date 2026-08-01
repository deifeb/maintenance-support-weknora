import { defineStore } from 'pinia'
import { ref } from 'vue'

import {
  demandListApi,
  type DecimalString,
  type DemandList,
  type DemandListCreateRequest,
  type DemandListItemUpdateRequest,
} from '../../api/maintenance/demand-lists'
import {
  normalizeMaintenanceError,
} from '../../api/maintenance/client'
import type {
  MaintenanceClientError,
  MaintenanceResult,
} from '../../api/maintenance/types'

export interface DemandListStoreApi {
  create(
    request: DemandListCreateRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<DemandList>>
  get(
    demandListId: number,
  ): Promise<MaintenanceResult<DemandList>>
  updateItem(
    demandListId: number,
    itemId: number,
    request: DemandListItemUpdateRequest,
  ): Promise<MaintenanceResult<DemandList>>
  submit(
    demandListId: number,
    expectedVersion: number,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<DemandList>>
  confirm(
    demandListId: number,
    expectedVersion: number,
    confirmationNote: string,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<DemandList>>
  publish(
    demandListId: number,
    expectedVersion: number,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<DemandList>>
  derive(
    demandListId: number,
    expectedVersion: number,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<DemandList>>
  void(
    demandListId: number,
    expectedVersion: number,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<DemandList>>
}

export function createDemandListState(
  api: DemandListStoreApi = demandListApi,
) {
  const current = ref<DemandList | null>(null)
  const loading = ref(false)
  const mutating = ref(false)
  const error = ref<MaintenanceClientError | null>(
    null,
  )

  let requestGeneration = 0

  function apply(
    value: DemandList,
  ): void {
    current.value = value
  }

  async function load(
    demandListId: number,
  ): Promise<DemandList> {
    const generation = ++requestGeneration
    loading.value = true
    error.value = null

    try {
      const response = await api.get(demandListId)
      if (generation === requestGeneration) {
        apply(response.data)
      }
      return response.data
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
        'Demand list mutation is already in progress',
      )
    }

    mutating.value = true
    error.value = null
  }

  function requireCurrent(): DemandList {
    const value = current.value
    if (value === null) {
      throw new Error('Demand list is not loaded')
    }
    return value
  }

  async function runMutation(
    operation: () => Promise<
      MaintenanceResult<DemandList>
    >,
    options: {
      sourceId: number | null
      allowResultIdChange: boolean
    },
  ): Promise<DemandList> {
    const generation = requestGeneration
    beginMutation()

    try {
      const response = await operation()

      if (generation === requestGeneration) {
        const active = current.value
        const sourceMatches = (
          options.sourceId === null
          || active?.id === options.sourceId
        )
        const resultMatches = (
          options.allowResultIdChange
          || options.sourceId === null
          || response.data.id === options.sourceId
        )

        if (sourceMatches && resultMatches) {
          apply(response.data)
        }
      }

      return response.data
    } catch (value) {
      if (generation === requestGeneration) {
        error.value = normalizeMaintenanceError(value)
      }
      throw value
    } finally {
      mutating.value = false
    }
  }

  function create(
    request: DemandListCreateRequest,
    idempotencyKey: string,
  ): Promise<DemandList> {
    return runMutation(
      () => api.create(
        request,
        idempotencyKey,
      ),
      {
        sourceId: null,
        allowResultIdChange: true,
      },
    )
  }

  async function updateItem(
    itemId: number,
    finalQuantity: DecimalString,
    adjustmentReason: string,
  ): Promise<DemandList> {
    const source = requireCurrent()

    return runMutation(
      () => api.updateItem(
        source.id,
        itemId,
        {
          expected_version: source.version,
          final_quantity: finalQuantity,
          adjustment_reason: adjustmentReason,
        },
      ),
      {
        sourceId: source.id,
        allowResultIdChange: false,
      },
    )
  }

  async function submit(
    idempotencyKey: string,
  ): Promise<DemandList> {
    const source = requireCurrent()

    return runMutation(
      () => api.submit(
        source.id,
        source.version,
        idempotencyKey,
      ),
      {
        sourceId: source.id,
        allowResultIdChange: false,
      },
    )
  }

  async function confirm(
    confirmationNote: string,
    idempotencyKey: string,
  ): Promise<DemandList> {
    const source = requireCurrent()

    return runMutation(
      () => api.confirm(
        source.id,
        source.version,
        confirmationNote,
        idempotencyKey,
      ),
      {
        sourceId: source.id,
        allowResultIdChange: false,
      },
    )
  }

  async function publish(
    idempotencyKey: string,
  ): Promise<DemandList> {
    const source = requireCurrent()

    return runMutation(
      () => api.publish(
        source.id,
        source.version,
        idempotencyKey,
      ),
      {
        sourceId: source.id,
        allowResultIdChange: false,
      },
    )
  }

  async function derive(
    idempotencyKey: string,
  ): Promise<DemandList> {
    const source = requireCurrent()

    return runMutation(
      () => api.derive(
        source.id,
        source.version,
        idempotencyKey,
      ),
      {
        sourceId: source.id,
        allowResultIdChange: true,
      },
    )
  }

  async function voidList(
    idempotencyKey: string,
  ): Promise<DemandList> {
    const source = requireCurrent()

    return runMutation(
      () => api.void(
        source.id,
        source.version,
        idempotencyKey,
      ),
      {
        sourceId: source.id,
        allowResultIdChange: false,
      },
    )
  }

  function dispose(): void {
    requestGeneration += 1
  }

  return {
    current,
    loading,
    mutating,
    error,
    create,
    load,
    updateItem,
    submit,
    confirm,
    publish,
    derive,
    voidList,
    dispose,
  }
}

export const useDemandListStore = defineStore(
  'maintenanceDemandList',
  () => createDemandListState(),
)
