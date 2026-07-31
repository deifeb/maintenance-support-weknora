import { defineStore } from 'pinia'
import {
  computed,
  ref,
  shallowRef,
} from 'vue'
import {
  scenarioApi,
  type ScenarioDraftEnvelope,
  type ScenarioDraftPayload,
  type ScenarioFieldState,
  type ScenarioMaterializeResult,
  type ScenarioVersionSummary,
} from '../../api/maintenance/scenarios'
import { normalizeMaintenanceError } from '../../api/maintenance/client'
import type {
  MaintenanceClientError,
  MaintenanceResult,
} from '../../api/maintenance/types'
import {
  createAutosaveController,
  type AutosaveState,
  type AutosaveTimerAdapter,
} from '../../composables/maintenance/useDebouncedAutosave'

export interface ScenarioDraftApi {
  createDraft(
    request: {
      title: string
      sensitivity_level?: string
    },
  ): Promise<MaintenanceResult<ScenarioDraftEnvelope>>
  getDraft(
    sessionId: number,
  ): Promise<MaintenanceResult<ScenarioDraftEnvelope>>
  saveDraft(
    sessionId: number,
    request: {
      expected_version: number
      draft: ScenarioDraftPayload
    },
  ): Promise<MaintenanceResult<ScenarioDraftEnvelope>>
  materialize(
    sessionId: number,
    expectedVersion: number,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<ScenarioMaterializeResult>>
  publishVersion(
    versionId: number,
  ): Promise<MaintenanceResult<ScenarioVersionSummary>>
}

export interface ScenarioDraftStateOptions {
  autosaveDelayMs?: number
  timers?: AutosaveTimerAdapter
}

interface PendingDraftSave {
  sessionId: number
  draft: ScenarioDraftPayload
}

function cloneDraft(
  draft: ScenarioDraftPayload,
): ScenarioDraftPayload {
  return JSON.parse(
    JSON.stringify(draft),
  ) as ScenarioDraftPayload
}

function cloneField(
  field: ScenarioFieldState,
): ScenarioFieldState {
  return JSON.parse(
    JSON.stringify(field),
  ) as ScenarioFieldState
}

function actualConflictVersion(
  error: unknown,
): number | null {
  const normalized = normalizeMaintenanceError(
    error,
  )
  if (
    normalized.code
    !== 'SCENARIO_DRAFT_VERSION_CONFLICT'
    || typeof normalized.details !== 'object'
    || normalized.details === null
  ) {
    return null
  }
  const value = (
    normalized.details as Record<string, unknown>
  ).actual_version
  return typeof value === 'number' ? value : null
}

export function createScenarioDraftState(
  api: ScenarioDraftApi = scenarioApi,
  options: ScenarioDraftStateOptions = {},
) {
  const sessionId = ref<number | null>(null)
  const version = ref<number | null>(null)
  const origin = ref<
    ScenarioDraftEnvelope['origin'] | null
  >(null)
  const draft = ref<ScenarioDraftPayload | null>(
    null,
  )
  const serverDraft = ref<
    ScenarioDraftPayload | null
  >(null)
  const completion = ref<Record<string, boolean>>(
    {},
  )
  const blockingFields = ref<string[]>([])
  const permissions = ref<string[]>([])
  const updatedAt = ref<string | null>(null)
  const loading = ref(false)
  const error = ref<
    MaintenanceClientError | null
  >(null)
  const materialized = ref<
    ScenarioMaterializeResult | null
  >(null)
  let loadGeneration = 0

  const autosave = shallowRef<
    AutosaveState<PendingDraftSave>
  >({
    status: 'idle',
    dirty: false,
  })

  function applyEnvelope(
    envelope: ScenarioDraftEnvelope,
    applyOptions: {
      replaceLocal: boolean
    },
  ): void {
    sessionId.value = envelope.session_id
    version.value = envelope.version
    origin.value = envelope.origin
    completion.value = {
      ...envelope.completion,
    }
    blockingFields.value = [
      ...envelope.blocking_fields,
    ]
    permissions.value = [
      ...(envelope.permissions ?? []),
    ]
    updatedAt.value = envelope.updated_at
    serverDraft.value = cloneDraft(envelope.draft)
    if (applyOptions.replaceLocal) {
      draft.value = cloneDraft(envelope.draft)
    }
  }

  const autosaveController = (
    createAutosaveController<PendingDraftSave>({
      delayMs: options.autosaveDelayMs ?? 800,
      timers: options.timers,
      onStateChange(nextState) {
        autosave.value = nextState
        if (nextState.error !== undefined) {
          error.value = normalizeMaintenanceError(
            nextState.error,
          )
        } else if (
          nextState.status === 'saved'
          || nextState.status === 'idle'
        ) {
          error.value = null
        }
      },
      async save(value) {
        const expectedVersion = version.value
        if (
          expectedVersion === null
          || sessionId.value !== value.sessionId
        ) {
          throw new Error(
            'Scenario draft session changed before save',
          )
        }
        const response = await api.saveDraft(
          value.sessionId,
          {
            expected_version: expectedVersion,
            draft: value.draft,
          },
        )
        if (
          sessionId.value === value.sessionId
          && response.data.session_id
          === value.sessionId
        ) {
          applyEnvelope(
            response.data,
            { replaceLocal: false },
          )
        }
        return {
          version: response.data.version,
        }
      },
    })
  )

  function scheduleCurrent(): void {
    if (
      sessionId.value === null
      || draft.value === null
    ) {
      return
    }
    autosaveController.schedule({
      sessionId: sessionId.value,
      draft: cloneDraft(draft.value),
    })
  }

  async function load(
    targetSessionId: number,
  ): Promise<void> {
    const generation = ++loadGeneration
    autosaveController.reset()
    loading.value = true
    error.value = null
    materialized.value = null
    try {
      const response = await api.getDraft(
        targetSessionId,
      )
      if (
        generation !== loadGeneration
        || response.data.session_id
        !== targetSessionId
      ) {
        return
      }
      applyEnvelope(
        response.data,
        { replaceLocal: true },
      )
    } catch (value) {
      if (generation === loadGeneration) {
        error.value = normalizeMaintenanceError(
          value,
        )
      }
    } finally {
      if (generation === loadGeneration) {
        loading.value = false
      }
    }
  }

  async function createManual(
    title: string,
    sensitivityLevel = 'INTERNAL',
  ): Promise<number> {
    const generation = ++loadGeneration
    autosaveController.reset()
    loading.value = true
    error.value = null
    try {
      const response = await api.createDraft({
        title,
        sensitivity_level: sensitivityLevel,
      })
      if (generation !== loadGeneration) {
        throw new Error(
          'Scenario draft creation was superseded',
        )
      }
      applyEnvelope(
        response.data,
        { replaceLocal: true },
      )
      return response.data.session_id
    } catch (value) {
      if (generation === loadGeneration) {
        error.value = normalizeMaintenanceError(
          value,
        )
      }
      throw value
    } finally {
      if (generation === loadGeneration) {
        loading.value = false
      }
    }
  }

  function updateField(
    fieldName: string,
    field: ScenarioFieldState,
  ): void {
    if (draft.value === null) return
    draft.value = {
      ...cloneDraft(draft.value),
      fields: {
        ...draft.value.fields,
        [fieldName]: cloneField(field),
      },
    }
    scheduleCurrent()
  }

  function rename(name: string): void {
    if (draft.value === null) return
    draft.value = {
      ...cloneDraft(draft.value),
      scenario_name: name,
    }
    scheduleCurrent()
  }

  function setCurrentStep(step: number): void {
    if (draft.value === null) return
    draft.value = {
      ...cloneDraft(draft.value),
      current_step: step,
    }
    scheduleCurrent()
  }

  function replaceDraft(
    value: ScenarioDraftPayload,
  ): void {
    draft.value = cloneDraft(value)
    scheduleCurrent()
  }

  async function reloadServerDraft(): Promise<void> {
    if (sessionId.value === null) return
    await load(sessionId.value)
  }

  function discardLocalChanges(): void {
    if (serverDraft.value === null) return
    autosaveController.reset()
    draft.value = cloneDraft(serverDraft.value)
    error.value = null
  }

  async function flushSave(): Promise<void> {
    await autosaveController.flush()
  }

  async function retrySave(): Promise<void> {
    await autosaveController.retry()
  }

  async function materialize(
    idempotencyKey: string,
  ): Promise<ScenarioMaterializeResult> {
    await flushSave()
    if (
      autosave.value.dirty
      || autosave.value.status === 'error'
      || autosave.value.status === 'conflict'
    ) {
      throw new Error(
        'Scenario draft must be saved before materialization',
      )
    }
    if (blockingFields.value.length > 0) {
      throw new Error(
        'Scenario draft has blocking fields',
      )
    }
    if (
      sessionId.value === null
      || version.value === null
    ) {
      throw new Error('Scenario draft is not loaded')
    }
    const targetSession = sessionId.value
    const response = await api.materialize(
      targetSession,
      version.value,
      idempotencyKey,
    )
    if (sessionId.value !== targetSession) {
      throw new Error(
        'Scenario draft changed during materialization',
      )
    }
    materialized.value = response.data
    return response.data
  }

  const canPublish = computed(() => (
    permissions.value.includes(
      'SCENARIO_PUBLISH',
    )
  ))

  async function publishVersion(
    versionId: number,
  ): Promise<ScenarioVersionSummary> {
    if (!canPublish.value) {
      throw new Error(
        'SCENARIO_PUBLISH permission is required',
      )
    }
    const response = await api.publishVersion(
      versionId,
    )
    return response.data
  }

  const conflictServerVersion = computed(() => (
    actualConflictVersion(
      autosave.value.error,
    )
  ))

  function dispose(): void {
    loadGeneration += 1
    autosaveController.dispose()
  }

  return {
    sessionId,
    version,
    origin,
    draft,
    completion,
    blockingFields,
    permissions,
    updatedAt,
    loading,
    error,
    autosave,
    materialized,
    canPublish,
    conflictServerVersion,
    load,
    createManual,
    updateField,
    rename,
    setCurrentStep,
    replaceDraft,
    reloadServerDraft,
    retrySave,
    flushSave,
    discardLocalChanges,
    materialize,
    publishVersion,
    dispose,
  }
}

export const useScenarioDraftStore = defineStore(
  'maintenanceScenarioDraft',
  () => createScenarioDraftState(),
)
