import { defineStore } from 'pinia'
import { reactive } from 'vue'

import {
  demandReviewApi,
  type DemandReviewBatchDecisionRequest,
  type DemandReviewDecisionRequest,
  type DemandReviewListQuery,
  type DemandReviewPublicRead,
  type DemandReviewRunRequest,
  type DemandReviewSummaryRead,
  type DemandReviewTransitionRequest,
} from '../../api/maintenance/demand-reviews'
import {
  normalizeMaintenanceError,
} from '../../api/maintenance/client'
import type {
  MaintenanceClientError,
  MaintenanceResult,
  PageData,
} from '../../api/maintenance/types'

export interface DemandReviewStoreApi {
  listReviews(
    query?: DemandReviewListQuery,
  ): Promise<MaintenanceResult<
    PageData<DemandReviewSummaryRead>
  >>
  runReview(
    demandListId: number,
    request: DemandReviewRunRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<DemandReviewPublicRead>>
  getReview(
    reviewId: number,
  ): Promise<MaintenanceResult<DemandReviewPublicRead>>
  decideFinding(
    reviewId: number,
    findingId: number,
    request: DemandReviewDecisionRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<DemandReviewPublicRead>>
  batchDecide(
    reviewId: number,
    request: DemandReviewBatchDecisionRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<DemandReviewPublicRead>>
  deriveReview(
    reviewId: number,
    request: DemandReviewTransitionRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<DemandReviewPublicRead>>
  voidReview(
    reviewId: number,
    request: DemandReviewTransitionRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<DemandReviewPublicRead>>
}

export type DemandReviewCommandKind =
  | 'review.run'
  | 'review.decide'
  | 'review.batch'
  | 'review.derive'
  | 'review.void'

export type DemandReviewCommandState =
  | { phase: 'idle' }
  | {
      phase: 'running'
      kind: DemandReviewCommandKind
      identity: string
    }
  | {
      phase: 'uncertain'
      kind: DemandReviewCommandKind
      identity: string
      error: MaintenanceClientError
    }
  | {
      phase: 'conflicted'
      kind: DemandReviewCommandKind
      identity: string
      error: MaintenanceClientError
    }
  | {
      phase: 'succeeded'
      kind: DemandReviewCommandKind
      identity: string
    }
  | {
      phase: 'failed'
      kind: DemandReviewCommandKind
      identity: string
      error: MaintenanceClientError
    }

export interface DemandReviewListSlice {
  items: DemandReviewSummaryRead[]
  query: DemandReviewListQuery
  page: number
  pageSize: number
  total: number
  pages: number
  loading: boolean
  error: MaintenanceClientError | null
  generation: number
}

export interface DemandReviewDetailSlice {
  item: DemandReviewPublicRead | null
  loading: boolean
  error: MaintenanceClientError | null
  generation: number
}

interface DemandReviewCommandHolder {
  current: DemandReviewCommandState
}

function createListSlice(): DemandReviewListSlice {
  return reactive({
    items: [] as DemandReviewSummaryRead[],
    query: {} as DemandReviewListQuery,
    page: 1,
    pageSize: 20,
    total: 0,
    pages: 0,
    loading: false,
    error: null as MaintenanceClientError | null,
    generation: 0,
  }) as DemandReviewListSlice
}

function createDetailSlice(): DemandReviewDetailSlice {
  return reactive({
    item: null as DemandReviewPublicRead | null,
    loading: false,
    error: null as MaintenanceClientError | null,
    generation: 0,
  }) as DemandReviewDetailSlice
}

const defaultStoreApi: DemandReviewStoreApi =
  demandReviewApi

function defaultCommandKey(): string {
  return (
    globalThis.crypto?.randomUUID?.()
    ?? `demand-review-${Date.now()}-${Math.random().toString(16).slice(2)}`
  )
}

function canonicalBatchRequest(
  request: DemandReviewBatchDecisionRequest,
): DemandReviewBatchDecisionRequest {
  return {
    ...request,
    decisions: [...request.decisions].sort(
      (left, right) => (
        left.finding_id - right.finding_id
      ),
    ),
  }
}

function commandIdentity(
  kind: DemandReviewCommandKind,
  objectIds: number[],
  body: unknown,
): string {
  return JSON.stringify([
    kind,
    objectIds,
    body,
  ])
}

export function createDemandReviewState(
  api: DemandReviewStoreApi = defaultStoreApi,
  createCommandKey: () => string = defaultCommandKey,
) {
  const reviews = createListSlice()
  const reviewDetail = createDetailSlice()
  const command = reactive<DemandReviewCommandHolder>({
    current: { phase: 'idle' },
  })
  const pendingCommandKeys = new Map<string, string>()

  async function fetchReviews(
    query: DemandReviewListQuery = {},
  ): Promise<void> {
    const generation = ++reviews.generation
    reviews.loading = true
    reviews.error = null
    reviews.query = { ...query }

    try {
      const response = await api.listReviews(query)
      if (generation !== reviews.generation) return

      reviews.items = response.data.items
      reviews.page = response.data.page
      reviews.pageSize = response.data.page_size
      reviews.total = response.data.total
      reviews.pages = response.data.pages
    } catch (value) {
      if (generation === reviews.generation) {
        reviews.error = normalizeMaintenanceError(value)
      }
      throw value
    } finally {
      if (generation === reviews.generation) {
        reviews.loading = false
      }
    }
  }

  async function fetchReviewDetail(
    reviewId: number,
  ): Promise<void> {
    const generation = ++reviewDetail.generation
    reviewDetail.loading = true
    reviewDetail.error = null

    try {
      const response = await api.getReview(reviewId)
      if (generation !== reviewDetail.generation) return
      reviewDetail.item = response.data
    } catch (value) {
      if (generation === reviewDetail.generation) {
        reviewDetail.error = normalizeMaintenanceError(value)
      }
      throw value
    } finally {
      if (generation === reviewDetail.generation) {
        reviewDetail.loading = false
      }
    }
  }

  function keyForIdentity(identity: string): string {
    const pending = pendingCommandKeys.get(identity)
    if (pending !== undefined) return pending

    const created = createCommandKey()
    pendingCommandKeys.set(identity, created)
    return created
  }

  function classifyCommandFailure(
    kind: DemandReviewCommandKind,
    identity: string,
    value: unknown,
  ): MaintenanceClientError {
    const error = normalizeMaintenanceError(value)

    if (error.status === 409) {
      pendingCommandKeys.delete(identity)
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

    pendingCommandKeys.delete(identity)
    command.current = {
      phase: 'failed',
      kind,
      identity,
      error,
    }
    return error
  }

  async function runCommand(
    kind: DemandReviewCommandKind,
    objectIds: number[],
    identityBody: unknown,
    operation: (
      idempotencyKey: string,
    ) => Promise<MaintenanceResult<DemandReviewPublicRead>>,
  ): Promise<DemandReviewPublicRead> {
    const identity = commandIdentity(
      kind,
      objectIds,
      identityBody,
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
      )
    }
  }

  function runReview(
    demandListId: number,
    request: DemandReviewRunRequest,
  ): Promise<DemandReviewPublicRead> {
    return runCommand(
      'review.run',
      [demandListId],
      request,
      (key) => api.runReview(
        demandListId,
        request,
        key,
      ),
    )
  }

  function decideFinding(
    reviewId: number,
    findingId: number,
    request: DemandReviewDecisionRequest,
  ): Promise<DemandReviewPublicRead> {
    return runCommand(
      'review.decide',
      [reviewId, findingId],
      request,
      (key) => api.decideFinding(
        reviewId,
        findingId,
        request,
        key,
      ),
    )
  }

  function batchDecide(
    reviewId: number,
    request: DemandReviewBatchDecisionRequest,
  ): Promise<DemandReviewPublicRead> {
    return runCommand(
      'review.batch',
      [reviewId],
      canonicalBatchRequest(request),
      (key) => api.batchDecide(
        reviewId,
        request,
        key,
      ),
    )
  }

  function deriveReview(
    reviewId: number,
    request: DemandReviewTransitionRequest,
  ): Promise<DemandReviewPublicRead> {
    return runCommand(
      'review.derive',
      [reviewId],
      request,
      (key) => api.deriveReview(
        reviewId,
        request,
        key,
      ),
    )
  }

  function voidReview(
    reviewId: number,
    request: DemandReviewTransitionRequest,
  ): Promise<DemandReviewPublicRead> {
    return runCommand(
      'review.void',
      [reviewId],
      request,
      (key) => api.voidReview(
        reviewId,
        request,
        key,
      ),
    )
  }

  function dispose(): void {
    reviews.generation += 1
    reviewDetail.generation += 1
    reviews.loading = false
    reviewDetail.loading = false
    pendingCommandKeys.clear()
    command.current = { phase: 'idle' }
  }

  return {
    reviews,
    reviewDetail,
    fetchReviews,
    fetchReviewDetail,
    get commandState() {
      return command.current
    },
    runReview,
    decideFinding,
    batchDecide,
    deriveReview,
    voidReview,
    dispose,
  }
}

export const useDemandReviewStore = defineStore(
  'maintenanceDemandReview',
  () => createDemandReviewState(),
)
