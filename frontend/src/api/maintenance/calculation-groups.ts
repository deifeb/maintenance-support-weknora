import {
  buildQuery,
  maintenanceGet,
  maintenancePost,
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
}

const defaultClient: CalculationGroupApiClient = {
  get: maintenanceGet,
  post: maintenancePost,
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
