import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'
import { dirname, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const modulePath = resolve(here, '../allocation.ts')
const moduleUrl = pathToFileURL(modulePath).href
const modulePresent = existsSync(modulePath)

interface MaintenanceResultLike<T> {
  data: T
  meta: {
    request_id: string
    tenant_id: string
    version?: number
  }
}

interface PageLike<T> {
  items: T[]
  page: number
  page_size: number
  total: number
  pages: number
}

interface SimulationLike {
  id: number
  status: string
  version: number
  progress: {
    phase: string
    percent: number | null
  }
  blockers: unknown[]
  results_summary: {
    total_rows: number
    demand_item_count: number
    high_priority_regression: string
  }
  completed_at: string | null
  error_code: string | null
  error_summary: string | null
}

interface RuleLike {
  id: number
  lineage_id: string
  version_number: number
  status: string
  scope: Record<string, unknown>
  effective_from: string | null
  effective_to: string | null
  hard_rules: Record<string, unknown>
  weights: Record<string, string>
  normalization: Record<string, unknown>
  change_reason: string
  published_by_user_id: string | null
  published_by_request_id: string | null
  published_at: string | null
  version: number
  created_at: string
  updated_at: string
  latest_simulation: SimulationLike | null
}

interface PlanSummaryLike {
  id: number
  source_demand_list_id: number
  source_demand_list_version: number
  rule_id: number
  inventory_fingerprint: string
  status: string
  version: number
  created_at: string
  updated_at: string
}

interface PlanLineLike {
  id: number
  plan_id: number
  demand_list_item_id: number
  spare_part_id: number
  recommended_balance_id: number | null
  recommended_lot_id: number | null
  recommended_serial_item_id: number | null
  demand_quantity: string
  allocated_quantity: string
  gap_quantity: string
  risks: unknown[]
  manual_override: Record<string, unknown> | null
  expected_balance_version: number | null
  reservation_id: number | null
  result: Record<string, unknown> | null
  version: number
}

interface PlanLike extends PlanSummaryLike {
  lines: PlanLineLike[]
}

interface AllocationApiLike {
  listRules(
    query?: Record<string, unknown>,
  ): Promise<MaintenanceResultLike<PageLike<RuleLike>>>
  createRule(
    request: Record<string, unknown>,
  ): Promise<MaintenanceResultLike<RuleLike>>
  simulateRule(
    ruleId: number,
    request: Record<string, unknown>,
    idempotencyKey: string,
  ): Promise<MaintenanceResultLike<SimulationLike>>
  publishRule(
    ruleId: number,
    request: Record<string, unknown>,
    idempotencyKey: string,
  ): Promise<MaintenanceResultLike<Record<string, unknown>>>
  retireRule(
    ruleId: number,
    request: Record<string, unknown>,
  ): Promise<MaintenanceResultLike<Record<string, unknown>>>
  listPlans(
    query?: Record<string, unknown>,
  ): Promise<MaintenanceResultLike<PageLike<PlanSummaryLike>>>
  createPlan(
    request: Record<string, unknown>,
    idempotencyKey: string,
  ): Promise<MaintenanceResultLike<PlanLike>>
  getPlan(
    planId: number,
  ): Promise<MaintenanceResultLike<PlanLike>>
  previewPlan(
    planId: number,
    request: Record<string, unknown>,
  ): Promise<MaintenanceResultLike<PlanLike>>
  editPlanLine(
    planId: number,
    lineId: number,
    request: Record<string, unknown>,
  ): Promise<MaintenanceResultLike<PlanLineLike>>
  confirmPlan(
    planId: number,
    request: Record<string, unknown>,
    idempotencyKey: string,
  ): Promise<MaintenanceResultLike<Record<string, unknown>>>
  executePlan(
    planId: number,
    request: Record<string, unknown>,
    idempotencyKey: string,
  ): Promise<MaintenanceResultLike<Record<string, unknown>>>
  voidPlan(
    planId: number,
    request: Record<string, unknown>,
  ): Promise<MaintenanceResultLike<Record<string, unknown>>>
  regeneratePlan(
    planId: number,
    request: Record<string, unknown>,
    idempotencyKey: string,
  ): Promise<MaintenanceResultLike<{
    source_plan_id: number
    new_plan_id: number
    event_id: number
    status: string
    version: number
  }>>
}

function result<T>(
  data: T,
): MaintenanceResultLike<T> {
  const version = (
    typeof data === 'object'
    && data !== null
    && 'version' in data
    && typeof data.version === 'number'
  )
    ? data.version
    : undefined

  return {
    data,
    meta: {
      request_id: 'request-task7-red',
      tenant_id: 'tenant-server-only',
      version,
    },
  }
}

function page<T>(
  items: T[],
  overrides: Partial<PageLike<T>> = {},
): PageLike<T> {
  return {
    items,
    page: 1,
    page_size: 20,
    total: items.length,
    pages: items.length === 0 ? 0 : 1,
    ...overrides,
  }
}

function simulation(
  id: number,
  status = 'PENDING',
): SimulationLike {
  const terminal = [
    'COMPLETED',
    'FAILED',
    'CANCELLED',
  ].includes(status)

  return {
    id,
    status,
    version: 1,
    progress: {
      phase: terminal ? 'TERMINAL' : 'QUEUED',
      percent: terminal ? 100 : 0,
    },
    blockers: [],
    results_summary: {
      total_rows: 0,
      demand_item_count: 0,
      high_priority_regression: '0.000000',
    },
    completed_at: terminal
      ? '2026-08-27T12:00:00Z'
      : null,
    error_code: null,
    error_summary: null,
  }
}

function rule(
  id: number,
  overrides: Partial<RuleLike> = {},
): RuleLike {
  return {
    id,
    lineage_id: '11111111-2222-3333-4444-555555555555',
    version_number: id,
    status: 'DRAFT',
    scope: {},
    effective_from: null,
    effective_to: null,
    hard_rules: {},
    weights: {
      priority: '1.000000',
    },
    normalization: {},
    change_reason: `rule-${id}`,
    published_by_user_id: null,
    published_by_request_id: null,
    published_at: null,
    version: 1,
    created_at: '2026-08-27T10:00:00Z',
    updated_at: '2026-08-27T10:00:00Z',
    latest_simulation: null,
    ...overrides,
  }
}

function planSummary(
  id: number,
  overrides: Partial<PlanSummaryLike> = {},
): PlanSummaryLike {
  return {
    id,
    source_demand_list_id: 41,
    source_demand_list_version: 8,
    rule_id: 17,
    inventory_fingerprint: `inventory-${id}`,
    status: 'DRAFT',
    version: 1,
    created_at: '2026-08-27T10:00:00Z',
    updated_at: '2026-08-27T10:00:00Z',
    ...overrides,
  }
}

function plan(
  id: number,
  overrides: Partial<PlanLike> = {},
): PlanLike {
  return {
    ...planSummary(id),
    lines: [],
    ...overrides,
  }
}

function line(
  id: number,
  planId: number,
): PlanLineLike {
  return {
    id,
    plan_id: planId,
    demand_list_item_id: 501,
    spare_part_id: 601,
    recommended_balance_id: 701,
    recommended_lot_id: null,
    recommended_serial_item_id: null,
    demand_quantity: '12.5000',
    allocated_quantity: '10.0000',
    gap_quantity: '2.5000',
    risks: [],
    manual_override: null,
    expected_balance_version: 3,
    reservation_id: null,
    result: null,
    version: 1,
  }
}

function deferred<T>() {
  let resolve: (value: T) => void = () => undefined
  let reject: (reason?: unknown) => void = () => undefined
  const promise = new Promise<T>((resolveValue, rejectValue) => {
    resolve = resolveValue
    reject = rejectValue
  })
  return { promise, resolve, reject }
}

function keyFactory(...keys: string[]): () => string {
  let index = 0
  return () => keys[index++] ?? `unexpected-key-${index}`
}

const retryableFailure = {
  status: 503,
  error: {
    code: 'SERVICE_UNAVAILABLE',
    message: 'Response outcome is unknown',
    details: {
      retryable: true,
    },
  },
  meta: {
    request_id: 'retryable-request',
  },
}

const conflictFailure = {
  status: 409,
  error: {
    code: 'ALLOCATION_RULE_VERSION_CONFLICT',
    message: 'Allocation rule version conflict',
    details: {
      retryable: false,
    },
  },
  meta: {
    request_id: 'conflict-request',
  },
}

function apiStub(
  overrides: Partial<AllocationApiLike> = {},
): AllocationApiLike {
  return {
    async listRules() {
      return result(page<RuleLike>([]))
    },
    async createRule() {
      return result(rule(17))
    },
    async simulateRule(
      ruleId: number,
      _request: Record<string, unknown>,
      _idempotencyKey: string,
    ) {
      return result(simulation(ruleId, 'PENDING'))
    },
    async publishRule(
      ruleId: number,
      _request: Record<string, unknown>,
      _idempotencyKey: string,
    ) {
      return result({
        rule_id: ruleId,
        status: 'PUBLISHED',
        version: 3,
        version_number: 2,
      })
    },
    async retireRule(
      ruleId: number,
      _request: Record<string, unknown>,
    ) {
      return result({
        rule_id: ruleId,
        status: 'RETIRED',
        version: 4,
        version_number: 2,
      })
    },
    async listPlans() {
      return result(page<PlanSummaryLike>([]))
    },
    async createPlan(
      _request: Record<string, unknown>,
      _idempotencyKey: string,
    ) {
      return result(plan(71))
    },
    async getPlan(planId: number) {
      return result(plan(planId))
    },
    async previewPlan(
      planId: number,
      _request: Record<string, unknown>,
    ) {
      return result(plan(planId, {
        status: 'PREVIEWED',
        version: 2,
      }))
    },
    async editPlanLine(
      planId: number,
      lineId: number,
      _request: Record<string, unknown>,
    ) {
      return result(line(lineId, planId))
    },
    async confirmPlan(
      planId: number,
      _request: Record<string, unknown>,
      _idempotencyKey: string,
    ) {
      return result({
        plan_id: planId,
        event_id: 901,
        status: 'CONFIRMED',
        version: 3,
      })
    },
    async executePlan(
      planId: number,
      _request: Record<string, unknown>,
      _idempotencyKey: string,
    ) {
      return result({
        plan_id: planId,
        execution_id: 902,
        execution_as_of: '2026-08-27T12:00:00Z',
        status: 'COMPLETED',
        version: 4,
        line_results: [],
      })
    },
    async voidPlan(
      planId: number,
      _request: Record<string, unknown>,
    ) {
      return result({
        plan_id: planId,
        event_id: 903,
        status: 'VOIDED',
        version: 5,
      })
    },
    async regeneratePlan(
      planId: number,
      _request: Record<string, unknown>,
      _idempotencyKey: string,
    ) {
      return result({
        source_plan_id: planId,
        new_plan_id: 72,
        event_id: 904,
        status: 'DRAFT',
        version: 1,
      })
    },
    ...overrides,
  }
}

async function loadModule(): Promise<Record<string, any>> {
  return import(moduleUrl)
}

test('allocation state production module is present', () => {
  assert.equal(
    modulePresent,
    true,
    'Task 7 GREEN B must create frontend/src/stores/maintenance/allocation.ts',
  )
})

test(
  'allocation store source does not create tenant authority or SSE',
  { skip: !modulePresent },
  () => {
    const source = readFileSync(modulePath, 'utf8')
    assert.doesNotMatch(source, /\btenant_id\b/)
    assert.doesNotMatch(source, /\bEventSource\b/)
    assert.doesNotMatch(source, /\buseResumableSSE\b/)
  },
)

test(
  'newer rules generation defeats a late older rules response',
  { skip: !modulePresent },
  async () => {
    const { createAllocationState } = await loadModule()
    const first = deferred<
      MaintenanceResultLike<PageLike<RuleLike>>
    >()
    const second = deferred<
      MaintenanceResultLike<PageLike<RuleLike>>
    >()
    let calls = 0

    const state = createAllocationState(apiStub({
      listRules: async () => {
        calls += 1
        return calls === 1
          ? first.promise
          : second.promise
      },
    }))

    const older = state.fetchRules({ status: 'DRAFT' })
    const newer = state.fetchRules({ status: 'PUBLISHED' })

    second.resolve(result(page([
      rule(18, { status: 'PUBLISHED' }),
    ])))
    await newer

    first.resolve(result(page([
      rule(17, { status: 'DRAFT' }),
    ])))
    await older

    assert.deepEqual(
      state.rules.items.map((item: RuleLike) => item.id),
      [18],
    )
    assert.equal(state.rules.query.status, 'PUBLISHED')
    assert.equal(state.rules.loading, false)
  },
)

test(
  'newer plans generation defeats a late older plans response',
  { skip: !modulePresent },
  async () => {
    const { createAllocationState } = await loadModule()
    const first = deferred<
      MaintenanceResultLike<PageLike<PlanSummaryLike>>
    >()
    const second = deferred<
      MaintenanceResultLike<PageLike<PlanSummaryLike>>
    >()
    let calls = 0

    const state = createAllocationState(apiStub({
      listPlans: async () => {
        calls += 1
        return calls === 1
          ? first.promise
          : second.promise
      },
    }))

    const older = state.fetchPlans({ status: 'DRAFT' })
    const newer = state.fetchPlans({ status: 'CONFIRMED' })

    second.resolve(result(page([
      planSummary(72, { status: 'CONFIRMED' }),
    ])))
    await newer

    first.resolve(result(page([
      planSummary(71, { status: 'DRAFT' }),
    ])))
    await older

    assert.deepEqual(
      state.plans.items.map(
        (item: PlanSummaryLike) => item.id,
      ),
      [72],
    )
    assert.equal(state.plans.query.status, 'CONFIRMED')
    assert.equal(state.plans.loading, false)
  },
)

test(
  'newer plan detail generation defeats a late older detail response',
  { skip: !modulePresent },
  async () => {
    const { createAllocationState } = await loadModule()
    const first = deferred<MaintenanceResultLike<PlanLike>>()
    const second = deferred<MaintenanceResultLike<PlanLike>>()
    let calls = 0

    const state = createAllocationState(apiStub({
      getPlan: async () => {
        calls += 1
        return calls === 1
          ? first.promise
          : second.promise
      },
    }))

    const older = state.fetchPlanDetail(71)
    const newer = state.fetchPlanDetail(72)

    second.resolve(result(plan(72, {
      inventory_fingerprint: 'new-detail',
    })))
    await newer

    first.resolve(result(plan(71, {
      inventory_fingerprint: 'stale-detail',
    })))
    await older

    assert.equal(state.planDetail.item?.id, 72)
    assert.equal(
      state.planDetail.item?.inventory_fingerprint,
      'new-detail',
    )
    assert.equal(state.planDetail.loading, false)
  },
)

test(
  'dispose invalidates rules plans and plan detail generations',
  { skip: !modulePresent },
  async () => {
    const { createAllocationState } = await loadModule()

    const rulesPending = deferred<
      MaintenanceResultLike<PageLike<RuleLike>>
    >()
    const plansPending = deferred<
      MaintenanceResultLike<PageLike<PlanSummaryLike>>
    >()
    const detailPending = deferred<
      MaintenanceResultLike<PlanLike>
    >()

    const state = createAllocationState(apiStub({
      listRules: async () => rulesPending.promise,
      listPlans: async () => plansPending.promise,
      getPlan: async () => detailPending.promise,
    }))

    const rulesLoad = state.fetchRules()
    const plansLoad = state.fetchPlans()
    const detailLoad = state.fetchPlanDetail(71)

    const rulesGeneration = state.rules.generation
    const plansGeneration = state.plans.generation
    const detailGeneration = state.planDetail.generation

    state.dispose()

    assert.ok(state.rules.generation > rulesGeneration)
    assert.ok(state.plans.generation > plansGeneration)
    assert.ok(
      state.planDetail.generation > detailGeneration,
    )

    rulesPending.resolve(result(page([rule(17)])))
    plansPending.resolve(result(page([planSummary(71)])))
    detailPending.resolve(result(plan(71)))

    await Promise.all([
      rulesLoad,
      plansLoad,
      detailLoad,
    ])

    assert.deepEqual(state.rules.items, [])
    assert.deepEqual(state.plans.items, [])
    assert.equal(state.planDetail.item, null)
    assert.equal(state.rules.loading, false)
    assert.equal(state.plans.loading, false)
    assert.equal(state.planDetail.loading, false)
  },
)

test(
  'retryable strict failure preserves the same simulate key until success',
  { skip: !modulePresent },
  async () => {
    const { createAllocationState } = await loadModule()
    const keys: string[] = []
    let calls = 0

    const state = createAllocationState(
      apiStub({
        simulateRule: async (
          ruleId,
          _request,
          key,
        ) => {
          keys.push(key)
          calls += 1
          if (calls === 1) throw retryableFailure
          return result(simulation(ruleId, 'PENDING'))
        },
      }),
      keyFactory('simulate-key-1', 'simulate-key-2'),
    )

    const request = {
      expected_rule_version: 3,
      source_demand_list_id: 41,
    }

    await assert.rejects(
      () => state.simulateRule(17, request),
    )
    assert.equal(
      state.commandState.phase,
      'uncertain',
    )

    await state.simulateRule(17, request)
    await state.simulateRule(17, request)

    assert.deepEqual(keys, [
      'simulate-key-1',
      'simulate-key-1',
      'simulate-key-2',
    ])
  },
)

test(
  'strict conflict clears publish key before the next explicit attempt',
  { skip: !modulePresent },
  async () => {
    const { createAllocationState } = await loadModule()
    const keys: string[] = []
    let calls = 0

    const state = createAllocationState(
      apiStub({
        publishRule: async (
          ruleId,
          _request,
          key,
        ) => {
          keys.push(key)
          calls += 1
          if (calls === 1) throw conflictFailure
          return result({
            rule_id: ruleId,
            status: 'PUBLISHED',
            version: 4,
            version_number: 2,
          })
        },
      }),
      keyFactory('publish-key-1', 'publish-key-2'),
    )

    const request = {
      expected_version: 3,
    }

    await assert.rejects(
      () => state.publishRule(17, request),
    )
    assert.equal(
      state.commandState.phase,
      'conflicted',
    )

    await state.publishRule(17, request)

    assert.deepEqual(keys, [
      'publish-key-1',
      'publish-key-2',
    ])
  },
)

test(
  'non-strict create rule uncertainty is not auto-replayed',
  { skip: !modulePresent },
  async () => {
    const { createAllocationState } = await loadModule()
    let calls = 0

    const state = createAllocationState(apiStub({
      createRule: async () => {
        calls += 1
        throw retryableFailure
      },
    }))

    await assert.rejects(
      () => state.createRule({
        scope: {},
        hard_rules: {},
        weights: {
          priority: '1.000000',
        },
        normalization: {},
        lineage_id: '11111111-2222-3333-4444-555555555555',
        change_reason: 'Non-strict uncertainty',
      }),
    )

    assert.equal(calls, 1)
    assert.equal(
      state.commandState.phase,
      'uncertain',
    )
  },
)

test(
  'targeted simulation refresh scans the exact lineage for the exact rule id',
  { skip: !modulePresent },
  async () => {
    const { createAllocationState } = await loadModule()
    const queries: Record<string, unknown>[] = []

    const targetSimulation = simulation(9002, 'RUNNING')

    const state = createAllocationState(apiStub({
      listRules: async (query = {}) => {
        queries.push({ ...query })

        if (query.page === 1) {
          return result(page(
            [
              rule(16, {
                lineage_id: 'lineage-a',
                latest_simulation: simulation(
                  9001,
                  'COMPLETED',
                ),
              }),
            ],
            {
              page: 1,
              page_size: 100,
              total: 2,
              pages: 2,
            },
          ))
        }

        return result(page(
          [
            rule(17, {
              lineage_id: 'lineage-a',
              latest_simulation: targetSimulation,
            }),
          ],
          {
            page: 2,
            page_size: 100,
            total: 2,
            pages: 2,
          },
        ))
      },
    }))

    const refreshed = await state.refreshRuleSimulation(
      17,
      'lineage-a',
    )

    assert.deepEqual(queries, [
      {
        lineage_id: 'lineage-a',
        page: 1,
        page_size: 100,
      },
      {
        lineage_id: 'lineage-a',
        page: 2,
        page_size: 100,
      },
    ])
    assert.equal(refreshed?.id, 9002)
    assert.equal(
      state.ruleById[17]?.id,
      17,
    )
    assert.equal(
      state.simulationByRuleId[17]?.id,
      9002,
    )
  },
)

test(
  'targeted refresh never substitutes another rule version from the lineage',
  { skip: !modulePresent },
  async () => {
    const { createAllocationState } = await loadModule()

    const state = createAllocationState(apiStub({
      listRules: async () => result(page([
        rule(18, {
          lineage_id: 'lineage-a',
          latest_simulation: simulation(
            9018,
            'COMPLETED',
          ),
        }),
      ])),
    }))

    const refreshed = await state.refreshRuleSimulation(
      17,
      'lineage-a',
    )

    assert.equal(refreshed, null)
    assert.equal(
      state.simulationByRuleId[17],
      undefined,
    )
  },
)

test(
  'regenerate returns the new plan without replacing the source detail',
  { skip: !modulePresent },
  async () => {
    const { createAllocationState } = await loadModule()
    const keys: string[] = []

    const state = createAllocationState(
      apiStub({
        getPlan: async (planId) => result(plan(planId)),
        regeneratePlan: async (
          planId,
          _request,
          key,
        ) => {
          keys.push(key)
          return result({
            source_plan_id: planId,
            new_plan_id: 72,
            event_id: 904,
            status: 'DRAFT',
            version: 1,
          })
        },
      }),
      keyFactory('regenerate-key'),
    )

    await state.fetchPlanDetail(71)
    const regenerated = await state.regeneratePlan(
      71,
      { expected_version: 3 },
    )

    assert.equal(regenerated.source_plan_id, 71)
    assert.equal(regenerated.new_plan_id, 72)
    assert.equal(state.planDetail.item?.id, 71)
    assert.deepEqual(keys, ['regenerate-key'])
  },
)
