import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'
import { dirname, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const modulePath = resolve(here, '../allocations.ts')
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

interface CapturedCall {
  method: 'GET' | 'POST' | 'PUT'
  path: string
  body?: unknown
  config?: unknown
}

interface FakeClient {
  get<T>(path: string): Promise<MaintenanceResultLike<T>>
  post<T>(
    path: string,
    body: unknown,
    config?: unknown,
  ): Promise<MaintenanceResultLike<T>>
  put<T>(
    path: string,
    body: unknown,
  ): Promise<MaintenanceResultLike<T>>
}

function result<T>(data: T): MaintenanceResultLike<T> {
  return {
    data,
    meta: {
      request_id: 'request-task7-red',
      tenant_id: 'tenant-server-only',
      version: 7,
    },
  }
}

function page<T>(items: T[] = []): PageLike<T> {
  return {
    items,
    page: 1,
    page_size: 20,
    total: items.length,
    pages: items.length === 0 ? 0 : 1,
  }
}

function fakeClient(calls: CapturedCall[]): FakeClient {
  return {
    async get<T>(
      path: string,
    ): Promise<MaintenanceResultLike<T>> {
      calls.push({ method: 'GET', path })
      return result(page() as T)
    },
    async post<T>(
      path: string,
      body: unknown,
      config?: unknown,
    ): Promise<MaintenanceResultLike<T>> {
      calls.push({
        method: 'POST',
        path,
        body,
        config,
      })
      return result({} as T)
    },
    async put<T>(
      path: string,
      body: unknown,
    ): Promise<MaintenanceResultLike<T>> {
      calls.push({
        method: 'PUT',
        path,
        body,
      })
      return result({} as T)
    },
  }
}

function headersOf(
  call: CapturedCall | undefined,
): Record<string, string> {
  const config = call?.config
  if (
    typeof config !== 'object'
    || config === null
    || !('headers' in config)
  ) {
    return {}
  }

  return (
    config as {
      headers?: Record<string, string>
    }
  ).headers ?? {}
}

function collectObjectKeys(
  value: unknown,
  keys: Set<string> = new Set<string>(),
): Set<string> {
  if (Array.isArray(value)) {
    value.forEach((item) => collectObjectKeys(item, keys))
    return keys
  }

  if (typeof value !== 'object' || value === null) {
    return keys
  }

  for (const [key, nested] of Object.entries(value)) {
    keys.add(key)
    collectObjectKeys(nested, keys)
  }

  return keys
}

async function loadModule(): Promise<Record<string, any>> {
  return import(moduleUrl)
}

test('allocation typed API production module is present', () => {
  assert.equal(
    modulePresent,
    true,
    'Task 7 GREEN A must create frontend/src/api/maintenance/allocations.ts',
  )
})

test(
  'allocation API publishes exact status unions and DecimalString contract',
  { skip: !modulePresent },
  () => {
    const source = readFileSync(modulePath, 'utf8')

    for (const token of [
      'AllocationRuleStatus',
      'DRAFT',
      'SIMULATED',
      'PUBLISHED',
      'RETIRED',
      'AllocationSimulationStatus',
      'PENDING',
      'RUNNING',
      'COMPLETED',
      'FAILED',
      'CANCELLED',
      'AllocationSimulationProgressPhase',
      'QUEUED',
      'TERMINAL',
      'AllocationPlanStatus',
      'PREVIEWED',
      'CONFIRMED',
      'EXECUTING',
      'PARTIALLY_COMPLETED',
      'VOIDED',
      'AllocationExecutionOutcome',
      'RESERVED',
      'GAP_RETAINED',
      'CONFLICT',
      'DecimalString',
      'AllocationPlanRegenerationResult',
      'latest_simulation',
    ]) {
      assert.equal(
        source.includes(token),
        true,
        `missing allocation contract token: ${token}`,
      )
    }
  },
)

test(
  'typed API uses exactly the fourteen Task 6 allocation routes',
  { skip: !modulePresent },
  async () => {
    const { createAllocationApi } = await loadModule()
    const calls: CapturedCall[] = []
    const api = createAllocationApi(fakeClient(calls))

    const ruleDraft = {
      scope: {
        warehouse_ids: [11, 12],
      },
      effective_from: '2026-09-01T00:00:00Z',
      effective_to: null,
      hard_rules: {
        prohibit_expired: true,
      },
      weights: {
        priority: '0.700000',
        shortage: '0.300000',
      },
      normalization: {
        priority: {
          min: '0.000000',
          max: '1.000000',
        },
      },
      lineage_id: '11111111-2222-3333-4444-555555555555',
      change_reason: 'Task 7 API contract',
    }

    const simulationRequest = {
      expected_rule_version: 3,
      baseline_rule_id: 19,
      source_demand_list_id: 41,
      sample_ref: 'task7-red',
    }

    const publishRequest = {
      expected_version: 4,
    }

    const retireRequest = {
      expected_version: 5,
    }

    const createPlanRequest = {
      source_demand_list_id: 41,
      expected_source_version: 8,
    }

    const previewRequest = {
      expected_version: 2,
    }

    const editLineRequest = {
      expected_plan_version: 3,
      expected_line_version: 4,
      allocated_quantity: '12.5000',
      reason: 'Manual verified allocation',
    }

    const confirmRequest = {
      expected_version: 4,
    }

    const executeRequest = {
      expected_version: 5,
    }

    const voidRequest = {
      expected_version: 6,
    }

    const regenerateRequest = {
      expected_version: 7,
    }

    await api.listRules({
      page: 2,
      page_size: 50,
      status: 'SIMULATED',
      lineage_id: '11111111-2222-3333-4444-555555555555',
    })
    await api.createRule(ruleDraft)
    await api.simulateRule(
      17,
      simulationRequest,
      'simulate-key',
    )
    await api.publishRule(
      17,
      publishRequest,
      'publish-key',
    )
    await api.retireRule(17, retireRequest)

    await api.listPlans({
      page: 3,
      page_size: 25,
      status: 'CONFIRMED',
      source_demand_list_id: 41,
      rule_id: 17,
    })
    await api.createPlan(
      createPlanRequest,
      'plan-create-key',
    )
    await api.getPlan(71)
    await api.previewPlan(71, previewRequest)
    await api.editPlanLine(
      71,
      701,
      editLineRequest,
    )
    await api.confirmPlan(
      71,
      confirmRequest,
      'plan-confirm-key',
    )
    await api.executePlan(
      71,
      executeRequest,
      'plan-execute-key',
    )
    await api.voidPlan(71, voidRequest)
    await api.regeneratePlan(
      71,
      regenerateRequest,
      'plan-regenerate-key',
    )

    assert.deepEqual(
      calls.map((call) => [call.method, call.path]),
      [
        [
          'GET',
          (
            '/v1/allocations/rules'
            + '?page=2&page_size=50&status=SIMULATED'
            + '&lineage_id=11111111-2222-3333-4444-555555555555'
          ),
        ],
        ['POST', '/v1/allocations/rules'],
        ['POST', '/v1/allocations/rules/17/simulate'],
        ['POST', '/v1/allocations/rules/17/publish'],
        ['POST', '/v1/allocations/rules/17/retire'],
        [
          'GET',
          (
            '/v1/allocations/plans'
            + '?page=3&page_size=25&status=CONFIRMED'
            + '&source_demand_list_id=41&rule_id=17'
          ),
        ],
        ['POST', '/v1/allocations/plans'],
        ['GET', '/v1/allocations/plans/71'],
        ['POST', '/v1/allocations/plans/71/preview'],
        ['PUT', '/v1/allocations/plans/71/lines/701'],
        ['POST', '/v1/allocations/plans/71/confirm'],
        ['POST', '/v1/allocations/plans/71/execute'],
        ['POST', '/v1/allocations/plans/71/void'],
        ['POST', '/v1/allocations/plans/71/regenerate'],
      ],
    )

    assert.deepEqual(calls[1]?.body, ruleDraft)
    assert.deepEqual(calls[2]?.body, simulationRequest)
    assert.deepEqual(calls[3]?.body, publishRequest)
    assert.deepEqual(calls[4]?.body, retireRequest)
    assert.deepEqual(calls[6]?.body, createPlanRequest)
    assert.deepEqual(calls[8]?.body, previewRequest)
    assert.deepEqual(calls[9]?.body, editLineRequest)
    assert.deepEqual(calls[10]?.body, confirmRequest)
    assert.deepEqual(calls[11]?.body, executeRequest)
    assert.deepEqual(calls[12]?.body, voidRequest)
    assert.deepEqual(calls[13]?.body, regenerateRequest)
  },
)

test(
  'Idempotency-Key is attached only to the six strict commands',
  { skip: !modulePresent },
  async () => {
    const { createAllocationApi } = await loadModule()
    const calls: CapturedCall[] = []
    const api = createAllocationApi(fakeClient(calls))

    await api.createRule({
      scope: {},
      effective_from: null,
      effective_to: null,
      hard_rules: {},
      weights: {
        priority: '1.000000',
      },
      normalization: {},
      lineage_id: '11111111-2222-3333-4444-555555555555',
      change_reason: 'Create without strict receipt',
    })
    await api.simulateRule(
      17,
      {
        expected_rule_version: 2,
        source_demand_list_id: 41,
      },
      'simulate-key',
    )
    await api.publishRule(
      17,
      { expected_version: 3 },
      'publish-key',
    )
    await api.retireRule(
      17,
      { expected_version: 4 },
    )

    await api.createPlan(
      {
        source_demand_list_id: 41,
        expected_source_version: 8,
      },
      'create-key',
    )
    await api.previewPlan(
      71,
      { expected_version: 2 },
    )
    await api.editPlanLine(
      71,
      701,
      {
        expected_plan_version: 3,
        expected_line_version: 4,
        allocated_quantity: '4.2500',
        reason: 'RED contract',
      },
    )
    await api.confirmPlan(
      71,
      { expected_version: 4 },
      'confirm-key',
    )
    await api.executePlan(
      71,
      { expected_version: 5 },
      'execute-key',
    )
    await api.voidPlan(
      71,
      { expected_version: 6 },
    )
    await api.regeneratePlan(
      71,
      { expected_version: 7 },
      'regenerate-key',
    )

    const writes = calls.filter(
      (call) => call.method !== 'GET',
    )

    assert.deepEqual(
      writes.map(headersOf),
      [
        {},
        { 'Idempotency-Key': 'simulate-key' },
        { 'Idempotency-Key': 'publish-key' },
        {},
        { 'Idempotency-Key': 'create-key' },
        {},
        {},
        { 'Idempotency-Key': 'confirm-key' },
        { 'Idempotency-Key': 'execute-key' },
        {},
        { 'Idempotency-Key': 'regenerate-key' },
      ],
    )
  },
)

test(
  'browser allocation requests never serialize tenant authority and keep decimals as strings',
  { skip: !modulePresent },
  async () => {
    const { createAllocationApi } = await loadModule()
    const calls: CapturedCall[] = []
    const api = createAllocationApi(fakeClient(calls))

    await api.createRule({
      scope: {
        warehouse_ids: [11],
      },
      effective_from: null,
      effective_to: null,
      hard_rules: {},
      weights: {
        priority: '0.750000',
        shortage: '0.250000',
      },
      normalization: {
        priority: {
          min: '0.000000',
          max: '100.000000',
        },
      },
      lineage_id: '11111111-2222-3333-4444-555555555555',
      change_reason: 'Decimal preservation',
    })

    await api.editPlanLine(
      71,
      701,
      {
        expected_plan_version: 3,
        expected_line_version: 4,
        allocated_quantity: '12.5000',
        reason: 'Preserve exact decimal',
      },
    )

    const keys = new Set<string>()
    for (const call of calls) {
      collectObjectKeys(call.body, keys)
    }

    for (const forbidden of [
      'tenant',
      'tenant_id',
      'actor_tenant_id',
    ]) {
      assert.equal(
        keys.has(forbidden),
        false,
        `browser payload must not carry ${forbidden}`,
      )
    }

    const ruleBody = calls[0]?.body as {
      weights: Record<string, unknown>
    }
    assert.equal(
      typeof ruleBody.weights.priority,
      'string',
    )

    const lineBody = calls[1]?.body as {
      allocated_quantity: unknown
    }
    assert.equal(
      typeof lineBody.allocated_quantity,
      'string',
    )
    assert.equal(
      lineBody.allocated_quantity,
      '12.5000',
    )
  },
)
