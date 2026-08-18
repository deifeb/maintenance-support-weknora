import {
  buildQuery,
  maintenanceGet,
  maintenancePost,
  normalizeMaintenanceError,
  unwrapMaintenanceResponse,
} from './client'
import type {
  MaintenanceResponse,
  MaintenanceResult,
  PageData,
} from './types'

export type DecimalString = string

export type DemandReviewStatus =
  | 'CREATED'
  | 'RUNNING'
  | 'OPEN'
  | 'READY_TO_DERIVE'
  | 'DERIVED'
  | 'FAILED'
  | 'VOIDED'

export type DemandReviewDecisionStatus =
  | 'PENDING'
  | 'ACCEPTED'
  | 'REJECTED'
  | 'EDIT_ACCEPTED'

export type DemandReviewDecisionAction =
  Exclude<DemandReviewDecisionStatus, 'PENDING'>

export type DemandReviewSeverity =
  | 'LOW'
  | 'MEDIUM'
  | 'HIGH'
  | 'CRITICAL'

export type DemandReviewCommandType =
  | 'RUN'
  | 'DECIDE_FINDING'
  | 'BATCH_DECIDE'
  | 'DERIVE'
  | 'VOID'

export type DemandReviewEventType =
  | 'CREATED'
  | 'RUNNING'
  | 'OPENED'
  | 'FAILED'
  | 'DECIDED'
  | 'BATCH_DECIDED'
  | 'READY_TO_DERIVE'
  | 'DERIVED'
  | 'VOIDED'

export type DemandReviewSortBy =
  | 'id'
  | 'status'
  | 'created_at'
  | 'updated_at'

export type DemandReviewSortOrder = 'asc' | 'desc'

export interface DemandReviewListQuery {
  page?: number
  page_size?: number
  status?: DemandReviewStatus
  source_demand_list_id?: number
  sort_by?: DemandReviewSortBy
  sort_order?: DemandReviewSortOrder
}

export interface DemandReviewRunRequest {
  expected_source_version: number
}

export interface DemandReviewTransitionRequest {
  expected_review_version: number
}

export interface DemandReviewDecisionRequest {
  expected_review_version: number
  expected_finding_version: number
  action: DemandReviewDecisionAction
  final_quantity?: DecimalString | null
  reason?: string | null
}

export interface DemandReviewBatchDecisionItem {
  finding_id: number
  expected_finding_version: number
  action: DemandReviewDecisionAction
  final_quantity?: DecimalString | null
  reason?: string | null
}

export interface DemandReviewBatchDecisionRequest {
  expected_review_version: number
  decisions: DemandReviewBatchDecisionItem[]
}

export interface DemandReviewFindingRead {
  id: number
  finding_key: string
  rule_code: string
  finding_type: string
  severity: DemandReviewSeverity
  blocking: boolean
  requires_admin_acceptance: boolean
  source_demand_list_item_id: number | null
  effect_key: string | null
  evidence_snapshot: Record<string, unknown>
  suggestion_snapshot: Record<string, unknown>
  decision_status: DemandReviewDecisionStatus
  version: number
}

export interface DemandReviewSummaryRead {
  id: number
  source_demand_list_id: number
  source_demand_list_version: number
  source_lineage_id: string
  source_version_number: number
  status: DemandReviewStatus
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
}

export interface DemandReviewDecisionRead {
  id: number
  finding_id: number
  action: DemandReviewDecisionStatus
  suggested_quantity: DecimalString | null
  final_quantity: DecimalString | null
  reason: string | null
  actor_user_id: string
  actor_roles: string[]
  request_id: string
  review_version_before: number
  review_version_after: number
  finding_version_before: number
  finding_version_after: number
  before_snapshot: Record<string, unknown>
  after_snapshot: Record<string, unknown>
  occurred_at: string
}

export interface DemandReviewEventRead {
  id: number
  event_type: DemandReviewEventType
  command_type: DemandReviewCommandType | null
  actor_user_id: string
  actor_roles: string[]
  request_id: string
  before_summary: Record<string, unknown> | null
  after_summary: Record<string, unknown> | null
  error_code: string | null
  occurred_at: string
}

export interface DemandReviewPublicRead
  extends DemandReviewSummaryRead {
  failure_code: string | null
  failure_summary: string | null
  findings: DemandReviewFindingRead[]
  decisions: DemandReviewDecisionRead[]
  events: DemandReviewEventRead[]
}

export interface DemandReviewApiClient {
  get<T>(
    path: string,
  ): Promise<MaintenanceResult<T>>
  post<T>(
    path: string,
    body: unknown,
    config?: unknown,
  ): Promise<MaintenanceResult<T>>
}

export type DemandReviewPut = <T>(
  path: string,
  body: unknown,
  config?: unknown,
) => Promise<MaintenanceResult<T>>

const BASE_PATH = '/v1/reviews/demand-lists'

const defaultClient: DemandReviewApiClient = {
  get: maintenanceGet,
  post: maintenancePost,
}

function identifier(value: number): string {
  return encodeURIComponent(String(value))
}

function idempotencyConfig(
  idempotencyKey: string,
): {
  headers: Record<string, string>
} {
  return {
    headers: {
      'Idempotency-Key': idempotencyKey,
    },
  }
}

async function reviewPut<T>(
  path: string,
  body: unknown,
  config?: unknown,
): Promise<MaintenanceResult<T>> {
  try {
    const { put } = await import('@/utils/request')
    const response = await put<MaintenanceResponse<T>>(
      `/api/maintenance${path}`,
      body as object,
      config,
    )
    return unwrapMaintenanceResponse(response)
  } catch (error) {
    throw normalizeMaintenanceError(error)
  }
}

export function createDemandReviewApi(
  client: DemandReviewApiClient = defaultClient,
  put: DemandReviewPut = reviewPut,
) {
  return {
    listReviews(
      query: DemandReviewListQuery = {},
    ): Promise<MaintenanceResult<
      PageData<DemandReviewSummaryRead>
    >> {
      const suffix = buildQuery({
        page: query.page,
        page_size: query.page_size,
        status: query.status,
        source_demand_list_id: query.source_demand_list_id,
        sort_by: query.sort_by,
        sort_order: query.sort_order,
      })

      return client.get<
        PageData<DemandReviewSummaryRead>
      >(
        BASE_PATH + (suffix ? `?${suffix}` : ''),
      )
    },

    runReview(
      demandListId: number,
      request: DemandReviewRunRequest,
      idempotencyKey: string,
    ): Promise<MaintenanceResult<DemandReviewPublicRead>> {
      return client.post<DemandReviewPublicRead>(
        `${BASE_PATH}/${identifier(demandListId)}/run`,
        request,
        idempotencyConfig(idempotencyKey),
      )
    },

    getReview(
      reviewId: number,
    ): Promise<MaintenanceResult<DemandReviewPublicRead>> {
      return client.get<DemandReviewPublicRead>(
        `${BASE_PATH}/${identifier(reviewId)}`,
      )
    },

    decideFinding(
      reviewId: number,
      findingId: number,
      request: DemandReviewDecisionRequest,
      idempotencyKey: string,
    ): Promise<MaintenanceResult<DemandReviewPublicRead>> {
      return put<DemandReviewPublicRead>(
        (
          `${BASE_PATH}/${identifier(reviewId)}`
          + `/findings/${identifier(findingId)}/decision`
        ),
        request,
        idempotencyConfig(idempotencyKey),
      )
    },

    batchDecide(
      reviewId: number,
      request: DemandReviewBatchDecisionRequest,
      idempotencyKey: string,
    ): Promise<MaintenanceResult<DemandReviewPublicRead>> {
      return client.post<DemandReviewPublicRead>(
        `${BASE_PATH}/${identifier(reviewId)}/batch-decisions`,
        request,
        idempotencyConfig(idempotencyKey),
      )
    },

    deriveReview(
      reviewId: number,
      request: DemandReviewTransitionRequest,
      idempotencyKey: string,
    ): Promise<MaintenanceResult<DemandReviewPublicRead>> {
      return client.post<DemandReviewPublicRead>(
        `${BASE_PATH}/${identifier(reviewId)}/derive`,
        request,
        idempotencyConfig(idempotencyKey),
      )
    },

    voidReview(
      reviewId: number,
      request: DemandReviewTransitionRequest,
      idempotencyKey: string,
    ): Promise<MaintenanceResult<DemandReviewPublicRead>> {
      return client.post<DemandReviewPublicRead>(
        `${BASE_PATH}/${identifier(reviewId)}/void`,
        request,
        idempotencyConfig(idempotencyKey),
      )
    },
  }
}

export const demandReviewApi = createDemandReviewApi()
