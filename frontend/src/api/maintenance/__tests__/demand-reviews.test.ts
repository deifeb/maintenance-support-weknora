import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'
import { dirname, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const modulePath = resolve(here, '../demand-reviews.ts')
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
  put?<T>(
    path: string,
    body: unknown,
    config?: unknown,
  ): Promise<MaintenanceResultLike<T>>
}

type ReviewPut = <T>(
  path: string,
  body: unknown,
  config?: unknown,
) => Promise<MaintenanceResultLike<T>>

function result<T>(data: T): MaintenanceResultLike<T> {
  return {
    data,
    meta: {
      request_id: 'request-a',
      tenant_id: 'tenant-a',
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

function fakeClient(
  calls: CapturedCall[],
): FakeClient {
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
  }
}

function fakeReviewPut(
  calls: CapturedCall[],
): ReviewPut {
  return async <T>(
    path: string,
    body: unknown,
    config?: unknown,
  ): Promise<MaintenanceResultLike<T>> => {
    calls.push({
      method: 'PUT',
      path,
      body,
      config,
    })
    return result({} as T)
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

test('demand review typed API production module is present', () => {
  assert.equal(
    modulePresent,
    true,
    'Task 6 GREEN must create frontend/src/api/maintenance/demand-reviews.ts',
  )
})

test(
  'formal demand review type unions are independent and complete',
  { skip: !modulePresent },
  () => {
    const source = readFileSync(modulePath, 'utf8')

    for (const token of [
      'DemandReviewStatus',
      'CREATED',
      'RUNNING',
      'OPEN',
      'READY_TO_DERIVE',
      'DERIVED',
      'FAILED',
      'VOIDED',
      'DemandReviewDecisionStatus',
      'PENDING',
      'ACCEPTED',
      'REJECTED',
      'EDIT_ACCEPTED',
      'DemandReviewSeverity',
      'LOW',
      'MEDIUM',
      'HIGH',
      'CRITICAL',
      'DecimalString',
    ]) {
      assert.equal(
        source.includes(token),
        true,
        `missing formal demand-review type token: ${token}`,
      )
    }

    assert.doesNotMatch(
      source,
      /from\s+['"][^'"]*ai[-_/]?review[^'"]*['"]/i,
      'formal review DTOs must not reuse AI review authority types',
    )
  },
)

test(
  'typed API uses exactly the seven formal routes and five idempotent writes',
  { skip: !modulePresent },
  async () => {
    const { createDemandReviewApi } = await loadModule()
    const calls: CapturedCall[] = []
    const api = createDemandReviewApi(
      fakeClient(calls),
      fakeReviewPut(calls),
    )

    const runRequest = {
      expected_source_version: 7,
    }
    const decisionRequest = {
      expected_review_version: 3,
      expected_finding_version: 2,
      action: 'EDIT_ACCEPTED',
      final_quantity: '12.500000',
      reason: 'Approved exact quantity',
    }
    const batchRequest = {
      expected_review_version: 4,
      decisions: [
        {
          finding_id: 502,
          expected_finding_version: 3,
          action: 'REJECTED',
          reason: 'Not applicable',
        },
        {
          finding_id: 501,
          expected_finding_version: 2,
          action: 'ACCEPTED',
          reason: null,
        },
      ],
    }
    const deriveRequest = {
      expected_review_version: 5,
    }
    const voidRequest = {
      expected_review_version: 6,
    }

    await api.listReviews({
      page: 2,
      page_size: 50,
      status: 'OPEN',
      source_demand_list_id: 41,
      sort_by: 'updated_at',
      sort_order: 'asc',
    })
    await api.runReview(41, runRequest, 'run-key')
    await api.getReview(701)
    await api.decideFinding(
      701,
      501,
      decisionRequest,
      'decision-key',
    )
    await api.batchDecide(
      701,
      batchRequest,
      'batch-key',
    )
    await api.deriveReview(
      701,
      deriveRequest,
      'derive-key',
    )
    await api.voidReview(
      701,
      voidRequest,
      'void-key',
    )

    assert.deepEqual(
      calls.map((call) => [call.method, call.path]),
      [
        [
          'GET',
          (
            '/v1/reviews/demand-lists'
            + '?page=2&page_size=50&status=OPEN'
            + '&source_demand_list_id=41'
            + '&sort_by=updated_at&sort_order=asc'
          ),
        ],
        [
          'POST',
          '/v1/reviews/demand-lists/41/run',
        ],
        [
          'GET',
          '/v1/reviews/demand-lists/701',
        ],
        [
          'PUT',
          (
            '/v1/reviews/demand-lists/701'
            + '/findings/501/decision'
          ),
        ],
        [
          'POST',
          '/v1/reviews/demand-lists/701/batch-decisions',
        ],
        [
          'POST',
          '/v1/reviews/demand-lists/701/derive',
        ],
        [
          'POST',
          '/v1/reviews/demand-lists/701/void',
        ],
      ],
    )

    assert.deepEqual(calls[1]?.body, runRequest)
    assert.deepEqual(calls[3]?.body, decisionRequest)
    assert.deepEqual(calls[4]?.body, batchRequest)
    assert.deepEqual(calls[5]?.body, deriveRequest)
    assert.deepEqual(calls[6]?.body, voidRequest)

    const writes = calls.filter(
      (call) => call.method !== 'GET',
    )
    assert.equal(writes.length, 5)
    assert.deepEqual(writes.map(headersOf), [
      { 'Idempotency-Key': 'run-key' },
      { 'Idempotency-Key': 'decision-key' },
      { 'Idempotency-Key': 'batch-key' },
      { 'Idempotency-Key': 'derive-key' },
      { 'Idempotency-Key': 'void-key' },
    ])
  },
)

test(
  'browser write payloads exclude tenant inventory master-data and finding authority',
  { skip: !modulePresent },
  async () => {
    const { createDemandReviewApi } = await loadModule()
    const calls: CapturedCall[] = []
    const api = createDemandReviewApi(
      fakeClient(calls),
      fakeReviewPut(calls),
    )

    await api.runReview(
      41,
      { expected_source_version: 7 },
      'run-key',
    )
    await api.decideFinding(
      701,
      501,
      {
        expected_review_version: 3,
        expected_finding_version: 2,
        action: 'ACCEPTED',
        reason: null,
      },
      'decision-key',
    )
    await api.batchDecide(
      701,
      {
        expected_review_version: 4,
        decisions: [{
          finding_id: 501,
          expected_finding_version: 3,
          action: 'REJECTED',
          reason: 'Not applicable',
        }],
      },
      'batch-key',
    )
    await api.deriveReview(
      701,
      { expected_review_version: 5 },
      'derive-key',
    )
    await api.voidReview(
      701,
      { expected_review_version: 6 },
      'void-key',
    )

    const keys = new Set()
    for (const call of calls) {
      if (call.method !== 'GET') {
        collectObjectKeys(call.body, keys)
      }
    }

    for (const forbidden of [
      'tenant',
      'tenant_id',
      'items',
      'inventory',
      'inventory_evidence',
      'current_inventory',
      'master_data',
      'master_data_evidence',
      'finding_key',
      'rule_code',
      'finding_type',
      'severity',
      'blocking',
      'requires_admin_acceptance',
      'evidence_snapshot',
      'suggestion_snapshot',
    ]) {
      assert.equal(
        keys.has(forbidden),
        false,
        `browser payload must not carry authority field ${forbidden}`,
      )
    }
  },
)

test(
  'single-decision PUT remains module-local and preserves Idempotency-Key config',
  { skip: !modulePresent },
  async () => {
    const source = readFileSync(modulePath, 'utf8')
    assert.match(
      source,
      /async\s+function\s+reviewPut\s*</,
    )
    assert.match(
      source,
      /await\s+import\(\s*['"]@\/utils\/request['"]\s*\)/,
    )
    assert.match(
      source,
      /unwrapMaintenanceResponse/,
    )
    assert.match(
      source,
      /normalizeMaintenanceError/,
    )
    assert.doesNotMatch(
      source,
      /\bmaintenancePut\b/,
      'shared maintenancePut must not be broadened solely for review PUT',
    )

    const { createDemandReviewApi } = await loadModule()
    const calls: CapturedCall[] = []
    const client = fakeClient(calls)
    client.put = async <T>(
      _path: string,
      _body: unknown,
      _config?: unknown,
    ): Promise<MaintenanceResultLike<T>> => {
      assert.fail(
        'single decision must use module-local reviewPut, not shared client.put',
      )
    }
    const api = createDemandReviewApi(
      client,
      fakeReviewPut(calls),
    )

    await api.decideFinding(
      701,
      501,
      {
        expected_review_version: 3,
        expected_finding_version: 2,
        action: 'REJECTED',
        reason: 'Not applicable',
      },
      'decision-key',
    )

    assert.deepEqual(calls, [{
      method: 'PUT',
      path: (
        '/v1/reviews/demand-lists/701'
        + '/findings/501/decision'
      ),
      body: {
        expected_review_version: 3,
        expected_finding_version: 2,
        action: 'REJECTED',
        reason: 'Not applicable',
      },
      config: {
        headers: {
          'Idempotency-Key': 'decision-key',
        },
      },
    }])
  },
)
