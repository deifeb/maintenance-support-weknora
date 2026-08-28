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

export type DecimalString = string

export type AllocationRuleStatus =
  | 'DRAFT'
  | 'SIMULATED'
  | 'PUBLISHED'
  | 'RETIRED'

export type AllocationSimulationStatus =
  | 'PENDING'
  | 'RUNNING'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED'

export type AllocationSimulationProgressPhase =
  | 'QUEUED'
  | 'RUNNING'
  | 'TERMINAL'

export type AllocationPlanStatus =
  | 'DRAFT'
  | 'PREVIEWED'
  | 'CONFIRMED'
  | 'EXECUTING'
  | 'COMPLETED'
  | 'PARTIALLY_COMPLETED'
  | 'FAILED'
  | 'VOIDED'

export type AllocationExecutionOutcome =
  | 'RESERVED'
  | 'GAP_RETAINED'
  | 'CONFLICT'

export interface AllocationRuleListQuery {
  page?: number
  page_size?: number
  status?: AllocationRuleStatus
  lineage_id?: string
}

export interface AllocationPlanListQuery {
  page?: number
  page_size?: number
  status?: AllocationPlanStatus
  source_demand_list_id?: number
  rule_id?: number
}

export interface AllocationRuleNormalizationBounds {
  min: DecimalString
  max: DecimalString
}

export interface AllocationRuleDraftRequest {
  scope: Record<string, unknown>
  effective_from?: string | null
  effective_to?: string | null
  hard_rules: Record<string, unknown>
  weights: Record<string, DecimalString>
  normalization: Record<
    string,
    AllocationRuleNormalizationBounds
  >
  lineage_id: string
  change_reason: string
}

export interface AllocationRulePublishRequest {
  expected_version: number
}

export interface AllocationRuleRetireRequest {
  expected_version: number
}

export interface AllocationSimulationSubmitRequest {
  expected_rule_version: number
  baseline_rule_id?: number | null
  source_demand_list_id: number
  sample_ref?: string | null
}

export interface AllocationSimulationProgressRead {
  phase: AllocationSimulationProgressPhase
  percent: number | null
}

export interface AllocationSimulationResultsSummaryRead {
  total_rows: number
  demand_item_count: number
  high_priority_regression: DecimalString
}

export interface AllocationSimulationSummaryRead {
  id: number
  status: AllocationSimulationStatus
  version: number
  progress: AllocationSimulationProgressRead
  blockers: Record<string, unknown>[]
  results_summary: AllocationSimulationResultsSummaryRead
  completed_at: string | null
  error_code: string | null
  error_summary: string | null
}

export interface AllocationRuleRead {
  id: number
  lineage_id: string
  version_number: number
  status: AllocationRuleStatus
  scope: Record<string, unknown>
  effective_from: string | null
  effective_to: string | null
  hard_rules: Record<string, unknown>
  weights: Record<string, DecimalString>
  normalization: Record<
    string,
    AllocationRuleNormalizationBounds
  >
  change_reason: string
  published_by_user_id: string | null
  published_by_request_id: string | null
  published_at: string | null
  version: number
  created_at: string
  updated_at: string
  latest_simulation: AllocationSimulationSummaryRead | null
}

export interface AllocationRuleActionResult {
  rule_id: number
  status: AllocationRuleStatus
  version: number
  version_number: number
}

export interface AllocationPlanCreateRequest {
  source_demand_list_id: number
  expected_source_version: number
}

export interface AllocationPlanVersionRequest {
  expected_version: number
}

export type AllocationPlanPreviewRequest =
  AllocationPlanVersionRequest

export type AllocationPlanConfirmRequest =
  AllocationPlanVersionRequest

export type AllocationPlanExecuteRequest =
  AllocationPlanVersionRequest

export type AllocationPlanVoidRequest =
  AllocationPlanVersionRequest

export type AllocationPlanRegenerateRequest =
  AllocationPlanVersionRequest

export interface AllocationPlanSummaryRead {
  id: number
  source_demand_list_id: number
  source_demand_list_version: number
  rule_id: number
  inventory_fingerprint: string
  status: AllocationPlanStatus
  version: number
  created_at: string
  updated_at: string
}

export interface AllocationPlanLineEditRequest {
  expected_plan_version: number
  expected_line_version: number
  allocated_quantity: DecimalString
  reason: string
}

export interface AllocationPlanLineRead {
  id: number
  plan_id: number
  demand_list_item_id: number
  spare_part_id: number
  recommended_balance_id: number | null
  recommended_lot_id: number | null
  recommended_serial_item_id: number | null
  demand_quantity: DecimalString
  allocated_quantity: DecimalString
  gap_quantity: DecimalString
  risks: Record<string, unknown>[]
  manual_override: Record<string, unknown> | null
  expected_balance_version: number | null
  reservation_id: number | null
  result: Record<string, unknown> | null
  version: number
}

export interface AllocationPlanRead
  extends AllocationPlanSummaryRead {
  lines: AllocationPlanLineRead[]
}

export interface AllocationPlanActionResult {
  plan_id: number
  event_id: number
  status: AllocationPlanStatus
  version: number
}

export interface AllocationPlanExecutionLineResult {
  line_id: number
  outcome: AllocationExecutionOutcome
  reservation_id: number | null
  error_code: string | null
  cause_code: string | null
  retryable: boolean
  suggested_action: string | null
  details: Record<string, unknown>
}

export interface AllocationPlanExecutionResult {
  plan_id: number
  execution_id: number
  execution_as_of: string
  status: AllocationPlanStatus
  version: number
  line_results: AllocationPlanExecutionLineResult[]
}

export interface AllocationPlanRegenerationResult {
  source_plan_id: number
  new_plan_id: number
  event_id: number
  status: AllocationPlanStatus
  version: number
}

export interface AllocationApiClient {
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

const BASE_PATH = '/v1/allocations'

const defaultClient: AllocationApiClient = {
  get: maintenanceGet,
  post: maintenancePost,
  put: maintenancePut,
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

export function createAllocationApi(
  client: AllocationApiClient = defaultClient,
) {
  return {
    listRules(
      query: AllocationRuleListQuery = {},
    ): Promise<MaintenanceResult<
      PageData<AllocationRuleRead>
    >> {
      const suffix = buildQuery({
        page: query.page,
        page_size: query.page_size,
        status: query.status,
        lineage_id: query.lineage_id,
      })

      return client.get<PageData<AllocationRuleRead>>(
        `${BASE_PATH}/rules${suffix ? `?${suffix}` : ''}`,
      )
    },

    createRule(
      request: AllocationRuleDraftRequest,
    ): Promise<MaintenanceResult<AllocationRuleRead>> {
      return client.post<AllocationRuleRead>(
        `${BASE_PATH}/rules`,
        request,
      )
    },

    simulateRule(
      ruleId: number,
      request: AllocationSimulationSubmitRequest,
      idempotencyKey: string,
    ): Promise<MaintenanceResult<
      AllocationSimulationSummaryRead
    >> {
      return client.post<AllocationSimulationSummaryRead>(
        `${BASE_PATH}/rules/${identifier(ruleId)}/simulate`,
        request,
        idempotencyConfig(idempotencyKey),
      )
    },

    publishRule(
      ruleId: number,
      request: AllocationRulePublishRequest,
      idempotencyKey: string,
    ): Promise<MaintenanceResult<
      AllocationRuleActionResult
    >> {
      return client.post<AllocationRuleActionResult>(
        `${BASE_PATH}/rules/${identifier(ruleId)}/publish`,
        request,
        idempotencyConfig(idempotencyKey),
      )
    },

    retireRule(
      ruleId: number,
      request: AllocationRuleRetireRequest,
    ): Promise<MaintenanceResult<
      AllocationRuleActionResult
    >> {
      return client.post<AllocationRuleActionResult>(
        `${BASE_PATH}/rules/${identifier(ruleId)}/retire`,
        request,
      )
    },

    listPlans(
      query: AllocationPlanListQuery = {},
    ): Promise<MaintenanceResult<
      PageData<AllocationPlanSummaryRead>
    >> {
      const suffix = buildQuery({
        page: query.page,
        page_size: query.page_size,
        status: query.status,
        source_demand_list_id:
          query.source_demand_list_id,
        rule_id: query.rule_id,
      })

      return client.get<PageData<AllocationPlanSummaryRead>>(
        `${BASE_PATH}/plans${suffix ? `?${suffix}` : ''}`,
      )
    },

    createPlan(
      request: AllocationPlanCreateRequest,
      idempotencyKey: string,
    ): Promise<MaintenanceResult<AllocationPlanRead>> {
      return client.post<AllocationPlanRead>(
        `${BASE_PATH}/plans`,
        request,
        idempotencyConfig(idempotencyKey),
      )
    },

    getPlan(
      planId: number,
    ): Promise<MaintenanceResult<AllocationPlanRead>> {
      return client.get<AllocationPlanRead>(
        `${BASE_PATH}/plans/${identifier(planId)}`,
      )
    },

    previewPlan(
      planId: number,
      request: AllocationPlanPreviewRequest,
    ): Promise<MaintenanceResult<AllocationPlanRead>> {
      return client.post<AllocationPlanRead>(
        `${BASE_PATH}/plans/${identifier(planId)}/preview`,
        request,
      )
    },

    editPlanLine(
      planId: number,
      lineId: number,
      request: AllocationPlanLineEditRequest,
    ): Promise<MaintenanceResult<
      AllocationPlanLineRead
    >> {
      return client.put<AllocationPlanLineRead>(
        (
          `${BASE_PATH}/plans/${identifier(planId)}`
          + `/lines/${identifier(lineId)}`
        ),
        request,
      )
    },

    confirmPlan(
      planId: number,
      request: AllocationPlanConfirmRequest,
      idempotencyKey: string,
    ): Promise<MaintenanceResult<
      AllocationPlanActionResult
    >> {
      return client.post<AllocationPlanActionResult>(
        `${BASE_PATH}/plans/${identifier(planId)}/confirm`,
        request,
        idempotencyConfig(idempotencyKey),
      )
    },

    executePlan(
      planId: number,
      request: AllocationPlanExecuteRequest,
      idempotencyKey: string,
    ): Promise<MaintenanceResult<
      AllocationPlanExecutionResult
    >> {
      return client.post<AllocationPlanExecutionResult>(
        `${BASE_PATH}/plans/${identifier(planId)}/execute`,
        request,
        idempotencyConfig(idempotencyKey),
      )
    },

    voidPlan(
      planId: number,
      request: AllocationPlanVoidRequest,
    ): Promise<MaintenanceResult<
      AllocationPlanActionResult
    >> {
      return client.post<AllocationPlanActionResult>(
        `${BASE_PATH}/plans/${identifier(planId)}/void`,
        request,
      )
    },

    regeneratePlan(
      planId: number,
      request: AllocationPlanRegenerateRequest,
      idempotencyKey: string,
    ): Promise<MaintenanceResult<
      AllocationPlanRegenerationResult
    >> {
      return client.post<AllocationPlanRegenerationResult>(
        `${BASE_PATH}/plans/${identifier(planId)}/regenerate`,
        request,
        idempotencyConfig(idempotencyKey),
      )
    },
  }
}

export const allocationApi = createAllocationApi()
