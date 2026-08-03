import {
  buildQuery,
  maintenanceGet,
  maintenancePost,
  maintenancePut,
} from './client'
import type {
  MaintenanceResult,
  PageData,
} from './types'
import type {
  CandidateExecutionMode,
  ReliabilityModel,
} from './model-recommendations'

export type DecimalString = string

export type CalculationGroupStatus =
  | 'PENDING'
  | 'RUNNING'
  | 'COMPLETED'
  | 'PARTIALLY_COMPLETED'
  | 'FAILED'
  | 'CANCELLED'
  | 'INTERRUPTED'

export type ChildCalculationStatus =
  | 'PENDING'
  | 'RUNNING'
  | 'SUCCEEDED'
  | 'PARTIAL_SUCCESS'
  | 'FAILED'
  | 'CANCELLED'
  | 'INTERRUPTED'

export interface CalculationGroupChild {
  id: number
  candidate_key: string
  reliability_model: ReliabilityModel
  execution_mode: CandidateExecutionMode
  calculation_id: number
  calculation_status: ChildCalculationStatus
  progress_percent: DecimalString
  attempt_number: number
  is_primary: boolean
  selection_reason: string | null
  current_stage?: string | null
  warnings?: string[]
  terminal_error?: string | null
}

export interface CalculationGroup {
  id: number
  scenario_version_id: number
  status: CalculationGroupStatus
  primary_candidate_key: string
  recommendation_snapshot: Record<string, unknown>
  parameter_snapshot: Record<string, unknown>
  last_event_sequence: number
  version: number
  created_by_user_id: string
  created_by_request_id: string
  created_at: string
  updated_at: string
  current_children: CalculationGroupChild[]
}

export interface CalculationGroupEvent {
  id: number
  group_id: number
  child_id: number | null
  sequence: number
  event_type: string
  payload: Record<string, unknown>
  occurred_at: string
}

export interface CalculationDecision {
  id: number
  group_id: number
  spare_part_id: number
  source_child_id: number
  selected_child_id: number
  original_quantity: DecimalString
  final_quantity: DecimalString
  decision_type:
    | 'SYSTEM_RECOMMENDATION'
    | 'ALTERNATIVE_CANDIDATE'
    | 'MANUAL_QUANTITY'
  reason: string | null
  risk: string
  requires_admin_confirmation: boolean
  confirmed_by_admin: boolean
  risk_rule_version: 'DEMAND-DECISION-RISK-1'
  version: number
  updated_at: string
}

export interface ComparisonCandidateCell {
  child_id: number
  candidate_key: string
  reliability_model: ReliabilityModel
  execution_mode: CandidateExecutionMode
  status: 'SUCCEEDED' | 'NO_RESULT'
  item_status: string | null
  recommended_quantity: DecimalString | null
  expected_demand: DecimalString | null
  p50: DecimalString | null
  p95: DecimalString | null
  p99: DecimalString | null
  usable_inventory: DecimalString | null
  net_demand_gap: DecimalString | null
  shortage_risk_level: string | null
  warnings: string[]
}

export interface CalculationComparisonRow {
  spare_part_id: number
  spare_part_code: string
  spare_part_name: string
  criticality_level: string | null
  system_child_id: number
  candidates: Record<string, ComparisonCandidateCell>
  decision: CalculationDecision | null
}

export interface CalculationGroupComparison {
  group_id: number
  group_status: CalculationGroupStatus
  primary_candidate_key: string
  candidate_keys: string[]
  risk_rule_version: 'DEMAND-DECISION-RISK-1'
  rows: CalculationComparisonRow[]
}

export interface CalculationDecisionSaveRequest {
  expected_version: number
  selected_child_id: number
  final_quantity: DecimalString
  reason: string | null
}

export interface CalculationGroupCreateRequest {
  scenario_version_id: number
  primary_candidate_key: string
  selected_candidate_keys: string[]
  random_seed: number
}

export interface CalculationGroupListQuery {
  page?: number
  page_size?: number
  status?: CalculationGroupStatus
}

export interface CalculationGroupApiClient {
  get<T>(path: string): Promise<MaintenanceResult<T>>
  post<T>(
    path: string,
    body: unknown,
    config?: unknown,
  ): Promise<MaintenanceResult<T>>
  put<T>(
    path: string,
    body: unknown,
  ): Promise<MaintenanceResult<T>>
}

const defaultClient: CalculationGroupApiClient = {
  get: maintenanceGet,
  post: maintenancePost,
  put: maintenancePut,
}

function identifier(value: number): string {
  return encodeURIComponent(String(value))
}

function idempotencyConfig(
  idempotencyKey: string,
): { headers: Record<string, string> } {
  return {
    headers: {
      'Idempotency-Key': idempotencyKey,
    },
  }
}

export function createCalculationGroupApi(
  client: CalculationGroupApiClient = defaultClient,
) {
  return {
    create(
      request: CalculationGroupCreateRequest,
      idempotencyKey: string,
    ): Promise<MaintenanceResult<CalculationGroup>> {
      return client.post<CalculationGroup>(
        '/v1/demand/calculation-groups',
        request,
        idempotencyConfig(idempotencyKey),
      )
    },

    list(
      query: CalculationGroupListQuery = {},
    ): Promise<MaintenanceResult<
      PageData<CalculationGroup>
    >> {
      const suffix = buildQuery({
        page: query.page,
        page_size: query.page_size,
        status: query.status,
      })
      return client.get<PageData<CalculationGroup>>(
        (
          '/v1/demand/calculation-groups'
          + (suffix ? `?${suffix}` : '')
        ),
      )
    },

    get(
      groupId: number,
    ): Promise<MaintenanceResult<CalculationGroup>> {
      return client.get<CalculationGroup>(
        (
          '/v1/demand/calculation-groups/'
          + identifier(groupId)
        ),
      )
    },

    retryFailed(
      groupId: number,
      idempotencyKey: string,
    ): Promise<MaintenanceResult<CalculationGroup>> {
      return client.post<CalculationGroup>(
        (
          '/v1/demand/calculation-groups/'
          + `${identifier(groupId)}/retry-failed`
        ),
        {},
        idempotencyConfig(idempotencyKey),
      )
    },

    cancelRunning(
      groupId: number,
      idempotencyKey: string,
    ): Promise<MaintenanceResult<CalculationGroup>> {
      return client.post<CalculationGroup>(
        (
          '/v1/demand/calculation-groups/'
          + `${identifier(groupId)}/cancel-running`
        ),
        {},
        idempotencyConfig(idempotencyKey),
      )
    },

    getEvents(
      groupId: number,
      afterSequence = 0,
    ): Promise<MaintenanceResult<
      CalculationGroupEvent[]
    >> {
      return client.get<CalculationGroupEvent[]>(
        (
          '/v1/demand/calculation-groups/'
          + `${identifier(groupId)}/events?`
          + buildQuery({
            after_sequence: afterSequence,
          })
        ),
      )
    },

    comparison(
      groupId: number,
    ): Promise<MaintenanceResult<
      CalculationGroupComparison
    >> {
      return client.get<CalculationGroupComparison>(
        (
          '/v1/demand/calculation-groups/'
          + `${identifier(groupId)}/comparison`
        ),
      )
    },

    saveDecision(
      groupId: number,
      sparePartId: number,
      request: CalculationDecisionSaveRequest,
    ): Promise<MaintenanceResult<CalculationDecision>> {
      return client.put<CalculationDecision>(
        (
          '/v1/demand/calculation-groups/'
          + `${identifier(groupId)}/decisions/`
          + identifier(sparePartId)
        ),
        request,
      )
    },
  }
}

export function calculationGroupEventStreamUrl(
  groupId: number,
  lastSequence: number,
): string {
  return (
    '/api/maintenance/v1/demand/calculation-groups/'
    + `${identifier(groupId)}/events/stream?`
    + buildQuery({
      last_event_sequence: lastSequence,
    })
  )
}

export const calculationGroupApi =
  createCalculationGroupApi()
