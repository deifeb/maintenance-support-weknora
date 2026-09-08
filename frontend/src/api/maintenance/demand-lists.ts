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
  ReliabilityModel,
} from './model-recommendations'

export type DecimalString = string

export type DemandListStatus =
  | 'DRAFT'
  | 'PENDING_CONFIRMATION'
  | 'CONFIRMED'
  | 'PUBLISHED'
  | 'VOIDED'

export type DemandListEventType =
  | 'CREATED'
  | 'ITEM_UPDATED'
  | 'SUBMITTED'
  | 'CONFIRMED'
  | 'PUBLISHED'
  | 'DERIVED'
  | 'VOIDED'

export type DemandListDecisionType =
  | 'SYSTEM_RECOMMENDATION'
  | 'ALTERNATIVE_CANDIDATE'
  | 'MANUAL_QUANTITY'

export type DemandExecutionMode =
  | 'AUTO'
  | 'ANALYTICAL'
  | 'MONTE_CARLO'
  | 'COMPARE'

export interface DemandListCreateRequest {
  calculation_group_id: number
  name: string
  description?: string | null
}

export interface DemandListItemUpdateRequest {
  expected_version: number
  final_quantity: DecimalString
  adjustment_reason: string
}

export interface DemandListListQuery {
  page?: number
  page_size?: number
  status?: DemandListStatus
  lineage_id?: string
}

export interface DemandListItem {
  id: number
  demand_list_id: number
  spare_part_id: number
  spare_part_code_snapshot: string
  spare_part_name_snapshot: string
  spare_part_unit_snapshot: string
  criticality_level_snapshot: string | null
  source_calculation_group_id: number | null
  source_group_child_id: number | null
  source_calculation_id: number | null
  source_calculation_run_id: number | null
  source_result_id: number | null
  reliability_model: ReliabilityModel | null
  execution_mode: DemandExecutionMode | null
  original_quantity: DecimalString
  final_quantity: DecimalString
  decision_type: DemandListDecisionType | null
  decision_reason: string | null
  decision_risk: string | null
  requires_admin_confirmation: boolean
  confirmed_by_admin: boolean
  risk_rule_version: string | null
  source_snapshot_json: Record<string, unknown>
  decision_snapshot_json:
    | Record<string, unknown>
    | null
  interval_snapshot_json:
    | Record<string, unknown>
    | null
  parameter_snapshot_json:
    | Record<string, unknown>
    | null
  warning_snapshot_json: string[] | null
  inventory_snapshot_json:
    | Record<string, unknown>
    | null
  version: number
  created_at: string
  updated_at: string
}

export interface DemandListEvent {
  id: number
  demand_list_id: number
  event_type: DemandListEventType
  actor_user_id: string
  actor_roles_json: string[]
  request_id: string
  idempotency_key: string | null
  request_hash: string | null
  before_summary_json:
    | Record<string, unknown>
    | null
  after_summary_json:
    | Record<string, unknown>
    | null
  response_snapshot_json:
    | Record<string, unknown>
    | null
  occurred_at: string
}

export interface DemandListSummary {
  id: number
  name: string
  description: string | null
  lineage_id: string
  version_number: number
  derived_from_id: number | null
  scenario_version_id: number
  calculation_group_id: number
  status: DemandListStatus
  is_current: boolean
  superseded_by_id: number | null
  superseded_at: string | null
  version: number
  created_by_user_id: string
  created_by_request_id: string
  created_at: string
  updated_at: string
}

export interface DemandList
  extends DemandListSummary {
  submitted_by_user_id: string | null
  submitted_by_request_id: string | null
  submitted_at: string | null
  confirmed_by_user_id: string | null
  confirmed_by_request_id: string | null
  confirmed_at: string | null
  published_by_user_id: string | null
  published_by_request_id: string | null
  published_at: string | null
  voided_by_user_id: string | null
  voided_by_request_id: string | null
  voided_at: string | null
  items: DemandListItem[]
  events: DemandListEvent[]
}

export interface DemandListApiClient {
  get<T>(
    path: string,
  ): Promise<MaintenanceResult<T>>
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

const defaultClient: DemandListApiClient = {
  get: maintenanceGet,
  post: maintenancePost,
  put: maintenancePut,
}

const BASE_PATH = '/v1/demand/demand-lists'

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

function transitionBody(
  expectedVersion: number,
): {
  expected_version: number
} {
  return {
    expected_version: expectedVersion,
  }
}

export function createDemandListApi(
  client: DemandListApiClient = defaultClient,
) {
  return {
    create(
      request: DemandListCreateRequest,
      idempotencyKey: string,
    ): Promise<MaintenanceResult<DemandList>> {
      return client.post<DemandList>(
        BASE_PATH,
        request,
        idempotencyConfig(idempotencyKey),
      )
    },

    list(
      query: DemandListListQuery = {},
    ): Promise<MaintenanceResult<
      PageData<DemandListSummary>
    >> {
      const suffix = buildQuery({
        page: query.page,
        page_size: query.page_size,
        status: query.status,
        lineage_id: query.lineage_id,
      })

      return client.get<
        PageData<DemandListSummary>
      >(
        BASE_PATH + (suffix ? `?${suffix}` : ''),
      )
    },

    get(
      demandListId: number,
    ): Promise<MaintenanceResult<DemandList>> {
      return client.get<DemandList>(
        `${BASE_PATH}/${identifier(demandListId)}`,
      )
    },

    updateItem(
      demandListId: number,
      itemId: number,
      request: DemandListItemUpdateRequest,
    ): Promise<MaintenanceResult<DemandList>> {
      return client.put<DemandList>(
        (
          `${BASE_PATH}/${identifier(demandListId)}`
          + `/items/${identifier(itemId)}`
        ),
        request,
      )
    },

    submit(
      demandListId: number,
      expectedVersion: number,
      idempotencyKey: string,
    ): Promise<MaintenanceResult<DemandList>> {
      return client.post<DemandList>(
        (
          `${BASE_PATH}/${identifier(demandListId)}`
          + '/submit'
        ),
        transitionBody(expectedVersion),
        idempotencyConfig(idempotencyKey),
      )
    },

    confirm(
      demandListId: number,
      expectedVersion: number,
      confirmationNote: string,
      idempotencyKey: string,
    ): Promise<MaintenanceResult<DemandList>> {
      return client.post<DemandList>(
        (
          `${BASE_PATH}/${identifier(demandListId)}`
          + '/confirm'
        ),
        {
          expected_version: expectedVersion,
          confirmation_note: confirmationNote,
        },
        idempotencyConfig(idempotencyKey),
      )
    },

    publish(
      demandListId: number,
      expectedVersion: number,
      idempotencyKey: string,
    ): Promise<MaintenanceResult<DemandList>> {
      return client.post<DemandList>(
        (
          `${BASE_PATH}/${identifier(demandListId)}`
          + '/publish'
        ),
        transitionBody(expectedVersion),
        idempotencyConfig(idempotencyKey),
      )
    },

    derive(
      demandListId: number,
      expectedVersion: number,
      idempotencyKey: string,
    ): Promise<MaintenanceResult<DemandList>> {
      return client.post<DemandList>(
        (
          `${BASE_PATH}/${identifier(demandListId)}`
          + '/derive'
        ),
        transitionBody(expectedVersion),
        idempotencyConfig(idempotencyKey),
      )
    },

    void(
      demandListId: number,
      expectedVersion: number,
      idempotencyKey: string,
    ): Promise<MaintenanceResult<DemandList>> {
      return client.post<DemandList>(
        (
          `${BASE_PATH}/${identifier(demandListId)}`
          + '/void'
        ),
        transitionBody(expectedVersion),
        idempotencyConfig(idempotencyKey),
      )
    },
  }
}

export const demandListApi =
  createDemandListApi()
