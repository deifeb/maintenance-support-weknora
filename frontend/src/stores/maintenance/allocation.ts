import { defineStore } from 'pinia'
import { reactive } from 'vue'

import {
  allocationApi,
  type AllocationPlanActionResult,
  type AllocationPlanConfirmRequest,
  type AllocationPlanCreateRequest,
  type AllocationPlanExecuteRequest,
  type AllocationPlanExecutionResult,
  type AllocationPlanLineEditRequest,
  type AllocationPlanLineRead,
  type AllocationPlanListQuery,
  type AllocationPlanPreviewRequest,
  type AllocationPlanRead,
  type AllocationPlanRegenerateRequest,
  type AllocationPlanRegenerationResult,
  type AllocationPlanSummaryRead,
  type AllocationPlanVoidRequest,
  type AllocationRuleActionResult,
  type AllocationRuleDraftRequest,
  type AllocationRuleListQuery,
  type AllocationRulePublishRequest,
  type AllocationRuleRead,
  type AllocationRuleRetireRequest,
  type AllocationSimulationSubmitRequest,
  type AllocationSimulationSummaryRead,
} from '../../api/maintenance/allocations'
import {
  normalizeMaintenanceError,
} from '../../api/maintenance/client'
import type {
  MaintenanceClientError,
  MaintenanceResult,
  PageData,
} from '../../api/maintenance/types'

export interface AllocationStoreApi {
  listRules(
    query?: AllocationRuleListQuery,
  ): Promise<MaintenanceResult<
    PageData<AllocationRuleRead>
  >>
  createRule(
    request: AllocationRuleDraftRequest,
  ): Promise<MaintenanceResult<AllocationRuleRead>>
  simulateRule(
    ruleId: number,
    request: AllocationSimulationSubmitRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<
    AllocationSimulationSummaryRead
  >>
  publishRule(
    ruleId: number,
    request: AllocationRulePublishRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<
    AllocationRuleActionResult
  >>
  retireRule(
    ruleId: number,
    request: AllocationRuleRetireRequest,
  ): Promise<MaintenanceResult<
    AllocationRuleActionResult
  >>
  listPlans(
    query?: AllocationPlanListQuery,
  ): Promise<MaintenanceResult<
    PageData<AllocationPlanSummaryRead>
  >>
  createPlan(
    request: AllocationPlanCreateRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<AllocationPlanRead>>
  getPlan(
    planId: number,
  ): Promise<MaintenanceResult<AllocationPlanRead>>
  previewPlan(
    planId: number,
    request: AllocationPlanPreviewRequest,
  ): Promise<MaintenanceResult<AllocationPlanRead>>
  editPlanLine(
    planId: number,
    lineId: number,
    request: AllocationPlanLineEditRequest,
  ): Promise<MaintenanceResult<
    AllocationPlanLineRead
  >>
  confirmPlan(
    planId: number,
    request: AllocationPlanConfirmRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<
    AllocationPlanActionResult
  >>
  executePlan(
    planId: number,
    request: AllocationPlanExecuteRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<
    AllocationPlanExecutionResult
  >>
  voidPlan(
    planId: number,
    request: AllocationPlanVoidRequest,
  ): Promise<MaintenanceResult<
    AllocationPlanActionResult
  >>
  regeneratePlan(
    planId: number,
    request: AllocationPlanRegenerateRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<
    AllocationPlanRegenerationResult
  >>
}

export type AllocationCommandKind =
  | 'rule.create'
  | 'rule.simulate'
  | 'rule.publish'
  | 'rule.retire'
  | 'plan.create'
  | 'plan.preview'
  | 'plan.edit-line'
  | 'plan.confirm'
  | 'plan.execute'
  | 'plan.void'
  | 'plan.regenerate'

export type AllocationCommandState =
  | { phase: 'idle' }
  | {
      phase: 'running'
      kind: AllocationCommandKind
      identity: string
    }
  | {
      phase: 'uncertain'
      kind: AllocationCommandKind
      identity: string
      error: MaintenanceClientError
    }
  | {
      phase: 'conflicted'
      kind: AllocationCommandKind
      identity: string
      error: MaintenanceClientError
    }
  | {
      phase: 'succeeded'
      kind: AllocationCommandKind
      identity: string
    }
  | {
      phase: 'failed'
      kind: AllocationCommandKind
      identity: string
      error: MaintenanceClientError
    }

export interface AllocationRuleListSlice {
  items: AllocationRuleRead[]
  query: AllocationRuleListQuery
  page: number
  pageSize: number
  total: number
  pages: number
  loading: boolean
  error: MaintenanceClientError | null
  generation: number
}

export interface AllocationPlanListSlice {
  items: AllocationPlanSummaryRead[]
  query: AllocationPlanListQuery
  page: number
  pageSize: number
  total: number
  pages: number
  loading: boolean
  error: MaintenanceClientError | null
  generation: number
}

export interface AllocationPlanDetailSlice {
  item: AllocationPlanRead | null
  loading: boolean
  error: MaintenanceClientError | null
  generation: number
}

interface AllocationCommandHolder {
  current: AllocationCommandState
}

function createRuleListSlice(): AllocationRuleListSlice {
  return reactive({
    items: [] as AllocationRuleRead[],
    query: {} as AllocationRuleListQuery,
    page: 1,
    pageSize: 20,
    total: 0,
    pages: 0,
    loading: false,
    error: null as MaintenanceClientError | null,
    generation: 0,
  }) as AllocationRuleListSlice
}

function createPlanListSlice(): AllocationPlanListSlice {
  return reactive({
    items: [] as AllocationPlanSummaryRead[],
    query: {} as AllocationPlanListQuery,
    page: 1,
    pageSize: 20,
    total: 0,
    pages: 0,
    loading: false,
    error: null as MaintenanceClientError | null,
    generation: 0,
  }) as AllocationPlanListSlice
}

function createPlanDetailSlice(): AllocationPlanDetailSlice {
  return reactive({
    item: null as AllocationPlanRead | null,
    loading: false,
    error: null as MaintenanceClientError | null,
    generation: 0,
  }) as AllocationPlanDetailSlice
}

function defaultCommandKey(): string {
  const randomUUID = globalThis.crypto?.randomUUID
  if (typeof randomUUID !== 'function') {
    throw new Error(
      'crypto.randomUUID is required for allocation commands',
    )
  }
  return randomUUID.call(globalThis.crypto)
}

function commandIdentity(
  kind: AllocationCommandKind,
  objectIds: number[],
  body: unknown,
): string {
  return JSON.stringify([
    kind,
    objectIds,
    body,
  ])
}

function clearRecord<T>(
  record: Record<number, T>,
): void {
  const stringRecord = record as unknown as Record<string, T>
  for (const key of Object.keys(stringRecord)) {
    delete stringRecord[key]
  }
}

export function createAllocationState(
  api: AllocationStoreApi = allocationApi,
  createCommandKey: () => string = defaultCommandKey,
) {
  const rules = createRuleListSlice()
  const plans = createPlanListSlice()
  const planDetail = createPlanDetailSlice()

  const ruleById = reactive<
    Record<number, AllocationRuleRead>
  >({})
  const simulationByRuleId = reactive<
    Record<number, AllocationSimulationSummaryRead>
  >({})

  const command = reactive<AllocationCommandHolder>({
    current: { phase: 'idle' },
  })
  const pendingCommandKeys = new Map<string, string>()

  let lifecycleGeneration = 0
  const simulationRefreshGeneration = new Map<number, number>()

  function cacheSimulation(
    ruleId: number,
    simulation: AllocationSimulationSummaryRead | null,
  ): void {
    if (simulation === null) {
      delete simulationByRuleId[ruleId]
      return
    }

    simulationByRuleId[ruleId] = simulation
  }

  function cacheRule(
    rule: AllocationRuleRead,
  ): void {
    ruleById[rule.id] = rule
    cacheSimulation(
      rule.id,
      rule.latest_simulation,
    )
  }

  function replaceVisibleRule(
    rule: AllocationRuleRead,
  ): void {
    const index = rules.items.findIndex(
      (item) => item.id === rule.id,
    )
    if (index < 0) return

    rules.items = rules.items.map((item, itemIndex) =>
      itemIndex === index ? rule : item,
    )
  }

  function replaceVisiblePlanSummary(
    planId: number,
    patch: Partial<AllocationPlanSummaryRead>,
  ): void {
    const index = plans.items.findIndex(
      (item) => item.id === planId,
    )
    if (index < 0) return

    plans.items = plans.items.map((item, itemIndex) =>
      itemIndex === index
        ? { ...item, ...patch }
        : item,
    )
  }

  function applyRuleAction(
    result: AllocationRuleActionResult,
  ): void {
    const cached = ruleById[result.rule_id]
    if (cached === undefined) return

    const updated: AllocationRuleRead = {
      ...cached,
      status: result.status,
      version: result.version,
      version_number: result.version_number,
    }
    cacheRule(updated)
    replaceVisibleRule(updated)
  }

  function applyPlanAction(
    result: AllocationPlanActionResult,
  ): void {
    replaceVisiblePlanSummary(
      result.plan_id,
      {
        status: result.status,
        version: result.version,
      },
    )

    if (planDetail.item?.id !== result.plan_id) {
      return
    }

    planDetail.item = {
      ...planDetail.item,
      status: result.status,
      version: result.version,
    }
  }

  function applyExecutionResult(
    result: AllocationPlanExecutionResult,
  ): void {
    replaceVisiblePlanSummary(
      result.plan_id,
      {
        status: result.status,
        version: result.version,
      },
    )

    if (planDetail.item?.id !== result.plan_id) {
      return
    }

    planDetail.item = {
      ...planDetail.item,
      status: result.status,
      version: result.version,
    }
  }

  async function fetchRules(
    query: AllocationRuleListQuery = {},
  ): Promise<void> {
    const generation = ++rules.generation
    rules.loading = true
    rules.error = null
    rules.query = { ...query }

    try {
      const response = await api.listRules(query)
      if (generation !== rules.generation) return

      rules.items = response.data.items
      rules.page = response.data.page
      rules.pageSize = response.data.page_size
      rules.total = response.data.total
      rules.pages = response.data.pages

      for (const rule of response.data.items) {
        cacheRule(rule)
      }
    } catch (value) {
      const error = normalizeMaintenanceError(value)
      if (generation === rules.generation) {
        rules.error = error
      }
      throw error
    } finally {
      if (generation === rules.generation) {
        rules.loading = false
      }
    }
  }

  async function fetchPlans(
    query: AllocationPlanListQuery = {},
  ): Promise<void> {
    const generation = ++plans.generation
    plans.loading = true
    plans.error = null
    plans.query = { ...query }

    try {
      const response = await api.listPlans(query)
      if (generation !== plans.generation) return

      plans.items = response.data.items
      plans.page = response.data.page
      plans.pageSize = response.data.page_size
      plans.total = response.data.total
      plans.pages = response.data.pages
    } catch (value) {
      const error = normalizeMaintenanceError(value)
      if (generation === plans.generation) {
        plans.error = error
      }
      throw error
    } finally {
      if (generation === plans.generation) {
        plans.loading = false
      }
    }
  }

  async function fetchPlanDetail(
    planId: number,
  ): Promise<void> {
    const generation = ++planDetail.generation
    planDetail.loading = true
    planDetail.error = null

    try {
      const response = await api.getPlan(planId)
      if (generation !== planDetail.generation) return

      planDetail.item = response.data
    } catch (value) {
      const error = normalizeMaintenanceError(value)
      if (generation === planDetail.generation) {
        planDetail.error = error
      }
      throw error
    } finally {
      if (generation === planDetail.generation) {
        planDetail.loading = false
      }
    }
  }

  async function refreshRuleSimulation(
    ruleId: number,
    lineageId: string,
  ): Promise<AllocationSimulationSummaryRead | null> {
    const lifecycle = lifecycleGeneration
    const refreshGeneration = (
      (simulationRefreshGeneration.get(ruleId) ?? 0)
      + 1
    )
    simulationRefreshGeneration.set(
      ruleId,
      refreshGeneration,
    )

    let page = 1

    while (true) {
      let response: MaintenanceResult<
        PageData<AllocationRuleRead>
      >

      try {
        response = await api.listRules({
          lineage_id: lineageId,
          page,
          page_size: 100,
        })
      } catch (value) {
        throw normalizeMaintenanceError(value)
      }

      if (
        lifecycle !== lifecycleGeneration
        || simulationRefreshGeneration.get(ruleId)
          !== refreshGeneration
      ) {
        return null
      }

      const target = response.data.items.find(
        (item) => (
          item.id === ruleId
          && item.lineage_id === lineageId
        ),
      )

      if (target !== undefined) {
        cacheRule(target)
        replaceVisibleRule(target)
        return target.latest_simulation
      }

      if (page >= response.data.pages) {
        return null
      }

      page += 1
    }
  }

  function keyForIdentity(
    identity: string,
  ): string {
    const pending = pendingCommandKeys.get(identity)
    if (pending !== undefined) {
      return pending
    }

    const created = createCommandKey()
    pendingCommandKeys.set(identity, created)
    return created
  }

  function classifyCommandFailure(
    kind: AllocationCommandKind,
    identity: string,
    value: unknown,
    strict: boolean,
  ): MaintenanceClientError {
    const error = normalizeMaintenanceError(value)

    if (error.status === 409) {
      if (strict) {
        pendingCommandKeys.delete(identity)
      }
      command.current = {
        phase: 'conflicted',
        kind,
        identity,
        error,
      }
      return error
    }

    if (error.retryable) {
      command.current = {
        phase: 'uncertain',
        kind,
        identity,
        error,
      }
      return error
    }

    if (strict) {
      pendingCommandKeys.delete(identity)
    }
    command.current = {
      phase: 'failed',
      kind,
      identity,
      error,
    }
    return error
  }

  async function runStrictCommand<T>(
    kind: AllocationCommandKind,
    objectIds: number[],
    body: unknown,
    operation: (
      idempotencyKey: string,
    ) => Promise<MaintenanceResult<T>>,
  ): Promise<T> {
    const identity = commandIdentity(
      kind,
      objectIds,
      body,
    )
    const key = keyForIdentity(identity)

    command.current = {
      phase: 'running',
      kind,
      identity,
    }

    try {
      const response = await operation(key)
      pendingCommandKeys.delete(identity)
      command.current = {
        phase: 'succeeded',
        kind,
        identity,
      }
      return response.data
    } catch (value) {
      throw classifyCommandFailure(
        kind,
        identity,
        value,
        true,
      )
    }
  }

  async function runNonStrictCommand<T>(
    kind: AllocationCommandKind,
    objectIds: number[],
    body: unknown,
    operation: () => Promise<MaintenanceResult<T>>,
  ): Promise<T> {
    const identity = commandIdentity(
      kind,
      objectIds,
      body,
    )

    command.current = {
      phase: 'running',
      kind,
      identity,
    }

    try {
      const response = await operation()
      command.current = {
        phase: 'succeeded',
        kind,
        identity,
      }
      return response.data
    } catch (value) {
      throw classifyCommandFailure(
        kind,
        identity,
        value,
        false,
      )
    }
  }

  async function createRule(
    request: AllocationRuleDraftRequest,
  ): Promise<AllocationRuleRead> {
    const rule = await runNonStrictCommand(
      'rule.create',
      [],
      request,
      () => api.createRule(request),
    )
    cacheRule(rule)
    return rule
  }

  async function simulateRule(
    ruleId: number,
    request: AllocationSimulationSubmitRequest,
  ): Promise<AllocationSimulationSummaryRead> {
    const simulation = await runStrictCommand(
      'rule.simulate',
      [ruleId],
      request,
      (key) => api.simulateRule(
        ruleId,
        request,
        key,
      ),
    )

    cacheSimulation(ruleId, simulation)

    const cached = ruleById[ruleId]
    if (cached !== undefined) {
      const updated: AllocationRuleRead = {
        ...cached,
        latest_simulation: simulation,
      }
      cacheRule(updated)
      replaceVisibleRule(updated)
    }

    return simulation
  }

  async function publishRule(
    ruleId: number,
    request: AllocationRulePublishRequest,
  ): Promise<AllocationRuleActionResult> {
    const result = await runStrictCommand(
      'rule.publish',
      [ruleId],
      request,
      (key) => api.publishRule(
        ruleId,
        request,
        key,
      ),
    )
    applyRuleAction(result)
    return result
  }

  async function retireRule(
    ruleId: number,
    request: AllocationRuleRetireRequest,
  ): Promise<AllocationRuleActionResult> {
    const result = await runNonStrictCommand(
      'rule.retire',
      [ruleId],
      request,
      () => api.retireRule(
        ruleId,
        request,
      ),
    )
    applyRuleAction(result)
    return result
  }

  async function createPlan(
    request: AllocationPlanCreateRequest,
  ): Promise<AllocationPlanRead> {
    return runStrictCommand(
      'plan.create',
      [],
      request,
      (key) => api.createPlan(
        request,
        key,
      ),
    )
  }

  async function previewPlan(
    planId: number,
    request: AllocationPlanPreviewRequest,
  ): Promise<AllocationPlanRead> {
    const result = await runNonStrictCommand(
      'plan.preview',
      [planId],
      request,
      () => api.previewPlan(
        planId,
        request,
      ),
    )

    replaceVisiblePlanSummary(
      result.id,
      result,
    )
    if (planDetail.item?.id === planId) {
      planDetail.item = result
    }
    return result
  }

  async function editPlanLine(
    planId: number,
    lineId: number,
    request: AllocationPlanLineEditRequest,
  ): Promise<AllocationPlanLineRead> {
    const result = await runNonStrictCommand(
      'plan.edit-line',
      [planId, lineId],
      request,
      () => api.editPlanLine(
        planId,
        lineId,
        request,
      ),
    )

    if (planDetail.item?.id === planId) {
      planDetail.item = {
        ...planDetail.item,
        lines: planDetail.item.lines.map(
          (line) => (
            line.id === result.id
              ? result
              : line
          ),
        ),
      }
    }

    return result
  }

  async function confirmPlan(
    planId: number,
    request: AllocationPlanConfirmRequest,
  ): Promise<AllocationPlanActionResult> {
    const result = await runStrictCommand(
      'plan.confirm',
      [planId],
      request,
      (key) => api.confirmPlan(
        planId,
        request,
        key,
      ),
    )
    applyPlanAction(result)
    return result
  }

  async function executePlan(
    planId: number,
    request: AllocationPlanExecuteRequest,
  ): Promise<AllocationPlanExecutionResult> {
    const result = await runStrictCommand(
      'plan.execute',
      [planId],
      request,
      (key) => api.executePlan(
        planId,
        request,
        key,
      ),
    )
    applyExecutionResult(result)
    return result
  }

  async function voidPlan(
    planId: number,
    request: AllocationPlanVoidRequest,
  ): Promise<AllocationPlanActionResult> {
    const result = await runNonStrictCommand(
      'plan.void',
      [planId],
      request,
      () => api.voidPlan(
        planId,
        request,
      ),
    )
    applyPlanAction(result)
    return result
  }

  async function regeneratePlan(
    planId: number,
    request: AllocationPlanRegenerateRequest,
  ): Promise<AllocationPlanRegenerationResult> {
    return runStrictCommand(
      'plan.regenerate',
      [planId],
      request,
      (key) => api.regeneratePlan(
        planId,
        request,
        key,
      ),
    )
  }

  function dispose(): void {
    lifecycleGeneration += 1

    rules.generation += 1
    plans.generation += 1
    planDetail.generation += 1

    rules.items = []
    rules.query = {}
    rules.page = 1
    rules.pageSize = 20
    rules.total = 0
    rules.pages = 0
    rules.loading = false
    rules.error = null

    plans.items = []
    plans.query = {}
    plans.page = 1
    plans.pageSize = 20
    plans.total = 0
    plans.pages = 0
    plans.loading = false
    plans.error = null

    planDetail.item = null
    planDetail.loading = false
    planDetail.error = null

    clearRecord(ruleById)
    clearRecord(simulationByRuleId)
    simulationRefreshGeneration.clear()
    pendingCommandKeys.clear()
    command.current = { phase: 'idle' }
  }

  return {
    rules,
    plans,
    planDetail,
    ruleById,
    simulationByRuleId,
    fetchRules,
    fetchPlans,
    fetchPlanDetail,
    refreshRuleSimulation,
    get commandState() {
      return command.current
    },
    createRule,
    simulateRule,
    publishRule,
    retireRule,
    createPlan,
    previewPlan,
    editPlanLine,
    confirmPlan,
    executePlan,
    voidPlan,
    regeneratePlan,
    dispose,
  }
}

export const useAllocationStore = defineStore(
  'maintenanceAllocation',
  () => createAllocationState(),
)
