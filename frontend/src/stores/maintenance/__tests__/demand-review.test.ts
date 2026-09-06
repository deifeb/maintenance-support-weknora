import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'
import { dirname, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const modulePath = resolve(here, '../demandReview.ts')
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

interface ReviewSummaryLike {
  id: number
  source_demand_list_id: number
  source_demand_list_version: number
  source_lineage_id: string
  source_version_number: number
  status: string
  rule_set_version: string
  input_hash: string
  total_finding_count: number
  blocking_finding_count: number
  pending_finding_count: number
  pending_blocking_finding_count: number
  derived_demand_list_id: number | null
  version: number
  created_at: string
  updated_at: string
  [key: string]: unknown
}

interface ReviewLike extends ReviewSummaryLike {
  failure_code: string | null
  failure_summary: string | null
  findings: unknown[]
  decisions: unknown[]
  events: unknown[]
}

interface PageLike<T> {
  items: T[]
  page: number
  page_size: number
  total: number
  pages: number
}

interface RunRequestLike {
  expected_source_version: number
}

interface TransitionRequestLike {
  expected_review_version: number
}

interface DecisionRequestLike {
  expected_review_version: number
  expected_finding_version: number
  action: string
  final_quantity?: string
  reason?: string | null
}

interface BatchDecisionItemLike {
  finding_id: number
  expected_finding_version: number
  action: string
  final_quantity?: string
  reason?: string | null
}

interface BatchRequestLike {
  expected_review_version: number
  decisions: BatchDecisionItemLike[]
}

interface DemandReviewApiLike {
  listReviews(
    query?: Record<string, unknown>,
  ): Promise<MaintenanceResultLike<PageLike<ReviewSummaryLike>>>
  runReview(
    demandListId: number,
    request: RunRequestLike,
    idempotencyKey: string,
  ): Promise<MaintenanceResultLike<ReviewLike>>
  getReview(
    reviewId: number,
  ): Promise<MaintenanceResultLike<ReviewLike>>
  decideFinding(
    reviewId: number,
    findingId: number,
    request: DecisionRequestLike,
    idempotencyKey: string,
  ): Promise<MaintenanceResultLike<ReviewLike>>
  batchDecide(
    reviewId: number,
    request: BatchRequestLike,
    idempotencyKey: string,
  ): Promise<MaintenanceResultLike<ReviewLike>>
  deriveReview(
    reviewId: number,
    request: TransitionRequestLike,
    idempotencyKey: string,
  ): Promise<MaintenanceResultLike<ReviewLike>>
  voidReview(
    reviewId: number,
    request: TransitionRequestLike,
    idempotencyKey: string,
  ): Promise<MaintenanceResultLike<ReviewLike>>
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
      request_id: 'request-a',
      tenant_id: 'tenant-a',
      version,
    },
  }
}

function summary(
  id: number,
  overrides: Partial<ReviewSummaryLike> = {},
): ReviewSummaryLike {
  return {
    id,
    source_demand_list_id: 41,
    source_demand_list_version: 7,
    source_lineage_id: '11111111-2222-3333-4444-555555555555',
    source_version_number: 1,
    status: 'OPEN',
    rule_set_version: 'v1',
    input_hash: `hash-${id}`,
    total_finding_count: 2,
    blocking_finding_count: 1,
    pending_finding_count: 2,
    pending_blocking_finding_count: 1,
    derived_demand_list_id: null,
    version: 3,
    created_at: '2026-08-18T10:00:00Z',
    updated_at: '2026-08-18T10:00:00Z',
    ...overrides,
  }
}

function review(
  id: number,
  overrides: Partial<ReviewLike> = {},
): ReviewLike {
  return {
    ...summary(id),
    failure_code: null,
    failure_summary: null,
    findings: [],
    decisions: [],
    events: [],
    ...overrides,
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
  },
  meta: {
    request_id: 'retryable-request',
  },
}

const conflictFailure = {
  status: 409,
  error: {
    code: 'REVIEW_VERSION_CONFLICT',
    message: 'Demand review version conflict',
    details: {
      expected_version: 3,
      actual_version: 4,
      conflict_object: 'demand_review',
      retryable: false,
    },
  },
  meta: {
    request_id: 'conflict-request',
  },
}

const nonRetryableFailure = {
  status: 422,
  error: {
    code: 'VALIDATION_ERROR',
    message: 'Invalid review command',
  },
  meta: {
    request_id: 'validation-request',
  },
}

function apiStub(
  overrides: Partial<DemandReviewApiLike> = {},
): DemandReviewApiLike {
  return {
    async listReviews() {
      return result(page<ReviewSummaryLike>([]))
    },
    async runReview(
      demandListId: number,
      _request: RunRequestLike,
      _idempotencyKey: string,
    ) {
      return result(review(701, {
        source_demand_list_id: demandListId,
      }))
    },
    async getReview(reviewId: number) {
      return result(review(reviewId))
    },
    async decideFinding(
      reviewId: number,
      _findingId: number,
      _request: DecisionRequestLike,
      _idempotencyKey: string,
    ) {
      return result(review(reviewId, {
        version: 4,
      }))
    },
    async batchDecide(
      reviewId: number,
      _request: BatchRequestLike,
      _idempotencyKey: string,
    ) {
      return result(review(reviewId, {
        version: 4,
      }))
    },
    async deriveReview(
      reviewId: number,
      _request: TransitionRequestLike,
      _idempotencyKey: string,
    ) {
      return result(review(reviewId, {
        status: 'DERIVED',
        version: 4,
        derived_demand_list_id: 42,
      }))
    },
    async voidReview(
      reviewId: number,
      _request: TransitionRequestLike,
      _idempotencyKey: string,
    ) {
      return result(review(reviewId, {
        status: 'VOIDED',
        version: 4,
      }))
    },
    ...overrides,
  }
}

async function loadModule(): Promise<Record<string, any>> {
  return import(moduleUrl)
}

test('demand review state production module is present', () => {
  assert.equal(
    modulePresent,
    true,
    'Task 6 GREEN must create frontend/src/stores/maintenance/demandReview.ts',
  )
})

test(
  'formal review store does not import AI review authority',
  { skip: !modulePresent },
  () => {
    const source = readFileSync(modulePath, 'utf8')
    assert.doesNotMatch(
      source,
      /from\s+['"][^'"]*ai[-_/]?review[^'"]*['"]/i,
    )
  },
)

test(
  'newer list generation defeats a late older list response',
  { skip: !modulePresent },
  async () => {
    const { createDemandReviewState } = await loadModule()
    const first = deferred<MaintenanceResultLike<PageLike<ReviewSummaryLike>>>()
    const second = deferred<MaintenanceResultLike<PageLike<ReviewSummaryLike>>>()
    let calls = 0

    const state = createDemandReviewState(apiStub({
      listReviews: async () => {
        calls += 1
        return calls === 1
          ? first.promise
          : second.promise
      },
    }))

    const older = state.fetchReviews({ status: 'OPEN' })
    const newer = state.fetchReviews({
      status: 'READY_TO_DERIVE',
    })

    second.resolve(result(page([
      summary(702, { status: 'READY_TO_DERIVE' }),
    ])))
    await newer

    first.resolve(result(page([
      summary(701, { status: 'OPEN' }),
    ])))
    await older

    assert.deepEqual(
      state.reviews.items.map((item: ReviewSummaryLike) => item.id),
      [702],
    )
    assert.equal(
      state.reviews.query.status,
      'READY_TO_DERIVE',
    )
    assert.equal(state.reviews.loading, false)
  },
)

test(
  'newer detail generation defeats a late older detail response',
  { skip: !modulePresent },
  async () => {
    const { createDemandReviewState } = await loadModule()
    const first = deferred<MaintenanceResultLike<ReviewLike>>()
    const second = deferred<MaintenanceResultLike<ReviewLike>>()
    let calls = 0

    const state = createDemandReviewState(apiStub({
      getReview: async () => {
        calls += 1
        return calls === 1
          ? first.promise
          : second.promise
      },
    }))

    const older = state.fetchReviewDetail(701)
    const newer = state.fetchReviewDetail(702)

    second.resolve(result(review(702, {
      failure_summary: 'new detail',
    })))
    await newer

    first.resolve(result(review(701, {
      failure_summary: 'stale detail',
    })))
    await older

    assert.equal(state.reviewDetail.item?.id, 702)
    assert.equal(
      state.reviewDetail.item?.failure_summary,
      'new detail',
    )
    assert.equal(state.reviewDetail.loading, false)
  },
)

test(
  'dispose invalidates list and detail generations',
  { skip: !modulePresent },
  async () => {
    const { createDemandReviewState } = await loadModule()
    const listPending = deferred<MaintenanceResultLike<PageLike<ReviewSummaryLike>>>()
    const detailPending = deferred<MaintenanceResultLike<ReviewLike>>()

    const state = createDemandReviewState(apiStub({
      listReviews: async () => listPending.promise,
      getReview: async () => detailPending.promise,
    }))

    const listLoad = state.fetchReviews({ status: 'OPEN' })
    const detailLoad = state.fetchReviewDetail(701)
    const listGeneration = state.reviews.generation
    const detailGeneration = state.reviewDetail.generation

    state.dispose()

    assert.ok(state.reviews.generation > listGeneration)
    assert.ok(
      state.reviewDetail.generation > detailGeneration,
    )

    listPending.resolve(result(page([
      summary(701),
    ])))
    detailPending.resolve(result(review(701)))
    await Promise.all([listLoad, detailLoad])

    assert.deepEqual(state.reviews.items, [])
    assert.equal(state.reviewDetail.item, null)
    assert.equal(state.reviews.loading, false)
    assert.equal(state.reviewDetail.loading, false)
  },
)

test(
  'list failure does not overwrite detail state',
  { skip: !modulePresent },
  async () => {
    const { createDemandReviewState } = await loadModule()
    const state = createDemandReviewState(apiStub({
      listReviews: async () => {
        throw retryableFailure
      },
      getReview: async (id) => result(review(id)),
    }))

    await state.fetchReviewDetail(701)
    await assert.rejects(
      () => state.fetchReviews({ status: 'OPEN' }),
    )

    assert.equal(state.reviewDetail.item?.id, 701)
    assert.equal(state.reviewDetail.error, null)
    assert.equal(
      state.reviews.error?.code,
      'SERVICE_UNAVAILABLE',
    )
  },
)

test(
  'detail failure does not overwrite list state',
  { skip: !modulePresent },
  async () => {
    const { createDemandReviewState } = await loadModule()
    const state = createDemandReviewState(apiStub({
      listReviews: async () => result(page([
        summary(701),
      ])),
      getReview: async () => {
        throw retryableFailure
      },
    }))

    await state.fetchReviews({ status: 'OPEN' })
    await assert.rejects(
      () => state.fetchReviewDetail(701),
    )

    assert.deepEqual(
      state.reviews.items.map((item: ReviewSummaryLike) => item.id),
      [701],
    )
    assert.equal(state.reviews.error, null)
    assert.equal(
      state.reviewDetail.error?.code,
      'SERVICE_UNAVAILABLE',
    )
  },
)

test(
  'retryable failure preserves the same logical command key until success',
  { skip: !modulePresent },
  async () => {
    const { createDemandReviewState } = await loadModule()
    const keys: string[] = []
    let calls = 0
    const state = createDemandReviewState(
      apiStub({
        runReview: async (id, _request, key) => {
          keys.push(key)
          calls += 1
          if (calls === 1) throw retryableFailure
          return result(review(701, {
            source_demand_list_id: id,
          }))
        },
      }),
      keyFactory('run-key-1', 'run-key-2'),
    )

    const request = {
      expected_source_version: 7,
    }

    await assert.rejects(
      () => state.runReview(41, request),
    )
    assert.equal(
      state.commandState.phase,
      'uncertain',
    )

    await state.runReview(41, request)
    await state.runReview(41, request)

    assert.deepEqual(keys, [
      'run-key-1',
      'run-key-1',
      'run-key-2',
    ])
  },
)

test(
  'network ambiguity preserves the same logical command key',
  { skip: !modulePresent },
  async () => {
    const { createDemandReviewState } = await loadModule()
    const keys: string[] = []
    let calls = 0
    const state = createDemandReviewState(
      apiStub({
        deriveReview: async (id, _request, key) => {
          keys.push(key)
          calls += 1
          if (calls === 1) {
            throw new Error('connection reset')
          }
          return result(review(id, {
            status: 'DERIVED',
            version: 4,
            derived_demand_list_id: 42,
          }))
        },
      }),
      keyFactory('derive-key-1', 'derive-key-2'),
    )

    const request = {
      expected_review_version: 3,
    }

    await assert.rejects(
      () => state.deriveReview(701, request),
    )
    await state.deriveReview(701, request)

    assert.deepEqual(keys, [
      'derive-key-1',
      'derive-key-1',
    ])
  },
)

test(
  '409 conflict releases the key and preserves expected and actual version details',
  { skip: !modulePresent },
  async () => {
    const { createDemandReviewState } = await loadModule()
    const keys: string[] = []
    let calls = 0
    const state = createDemandReviewState(
      apiStub({
        decideFinding: async (
          id,
          _findingId,
          _request,
          key,
        ) => {
          keys.push(key)
          calls += 1
          if (calls === 1) throw conflictFailure
          return result(review(id, { version: 4 }))
        },
      }),
      keyFactory('decision-key-1', 'decision-key-2'),
    )

    const request = {
      expected_review_version: 3,
      expected_finding_version: 2,
      action: 'ACCEPTED',
      reason: null,
    }

    await assert.rejects(
      () => state.decideFinding(701, 501, request),
    )

    assert.equal(
      state.commandState.phase,
      'conflicted',
    )
    assert.deepEqual(
      state.commandState.error.details,
      conflictFailure.error.details,
    )

    await state.decideFinding(701, 501, request)

    assert.deepEqual(keys, [
      'decision-key-1',
      'decision-key-2',
    ])
  },
)

test(
  'non-retryable failure releases the logical command key',
  { skip: !modulePresent },
  async () => {
    const { createDemandReviewState } = await loadModule()
    const keys: string[] = []
    let calls = 0
    const state = createDemandReviewState(
      apiStub({
        voidReview: async (id, _request, key) => {
          keys.push(key)
          calls += 1
          if (calls === 1) throw nonRetryableFailure
          return result(review(id, {
            status: 'VOIDED',
            version: 4,
          }))
        },
      }),
      keyFactory('void-key-1', 'void-key-2'),
    )

    const request = {
      expected_review_version: 3,
    }

    await assert.rejects(
      () => state.voidReview(701, request),
    )
    assert.equal(
      state.commandState.phase,
      'failed',
    )

    await state.voidReview(701, request)

    assert.deepEqual(keys, [
      'void-key-1',
      'void-key-2',
    ])
  },
)

test(
  'changed object IDs or server body start a new logical command identity',
  { skip: !modulePresent },
  async () => {
    const { createDemandReviewState } = await loadModule()
    const keys: string[] = []
    const state = createDemandReviewState(
      apiStub({
        runReview: async (_id, _request, key) => {
          keys.push(key)
          throw retryableFailure
        },
      }),
      keyFactory(
        'run-key-1',
        'run-key-2',
        'run-key-3',
      ),
    )

    await assert.rejects(
      () => state.runReview(
        41,
        { expected_source_version: 7 },
      ),
    )
    await assert.rejects(
      () => state.runReview(
        42,
        { expected_source_version: 7 },
      ),
    )
    await assert.rejects(
      () => state.runReview(
        41,
        { expected_source_version: 8 },
      ),
    )

    assert.deepEqual(keys, [
      'run-key-1',
      'run-key-2',
      'run-key-3',
    ])
  },
)

test(
  'batch logical identity sorts decisions by finding_id',
  { skip: !modulePresent },
  async () => {
    const { createDemandReviewState } = await loadModule()
    const keys: string[] = []
    let calls = 0
    const state = createDemandReviewState(
      apiStub({
        batchDecide: async (id, _request, key) => {
          keys.push(key)
          calls += 1
          if (calls === 1) throw retryableFailure
          return result(review(id, { version: 4 }))
        },
      }),
      keyFactory('batch-key-1', 'batch-key-2'),
    )

    const finding1 = {
      finding_id: 501,
      expected_finding_version: 2,
      action: 'ACCEPTED',
      reason: null,
    }
    const finding2 = {
      finding_id: 502,
      expected_finding_version: 3,
      action: 'REJECTED',
      reason: 'Not applicable',
    }

    await assert.rejects(
      () => state.batchDecide(701, {
        expected_review_version: 3,
        decisions: [finding2, finding1],
      }),
    )
    await state.batchDecide(701, {
      expected_review_version: 3,
      decisions: [finding1, finding2],
    })

    assert.deepEqual(keys, [
      'batch-key-1',
      'batch-key-1',
    ])
  },
)

test(
  'dispose clears pending command keys',
  { skip: !modulePresent },
  async () => {
    const { createDemandReviewState } = await loadModule()
    const keys: string[] = []
    let calls = 0
    const state = createDemandReviewState(
      apiStub({
        runReview: async (id, _request, key) => {
          keys.push(key)
          calls += 1
          if (calls === 1) throw retryableFailure
          return result(review(701, {
            source_demand_list_id: id,
          }))
        },
      }),
      keyFactory('run-key-1', 'run-key-2'),
    )

    const request = {
      expected_source_version: 7,
    }

    await assert.rejects(
      () => state.runReview(41, request),
    )
    state.dispose()
    await state.runReview(41, request)

    assert.deepEqual(keys, [
      'run-key-1',
      'run-key-2',
    ])
  },
)
