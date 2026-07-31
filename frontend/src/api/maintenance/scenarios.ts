import {
  maintenanceGet,
  maintenancePost,
  maintenancePut,
} from './client'
import type { MaintenanceResult } from './types'

export type DecimalString = string
export type ScenarioDraftOrigin = 'MANUAL' | 'AI'
export type ScenarioFieldSource =
  | 'MASTER_DATA'
  | 'USER_INPUT'
  | 'AI_INFERRED'
  | 'SYSTEM_DEFAULT'
  | 'DERIVED'
export type ScenarioFieldRisk =
  | 'LOW'
  | 'MEDIUM'
  | 'HIGH'
  | 'BLOCKING'
export type ScenarioVersionStatus =
  | 'DRAFT'
  | 'PUBLISHED'
  | 'RETIRED'
export type MissingParameterPolicy =
  | 'STRICT'
  | 'WARN_AND_SKIP'
  | 'FALLBACK'
export type DemandExecutionMode =
  | 'AUTO'
  | 'ANALYTICAL'
  | 'MONTE_CARLO'
  | 'COMPARE'
export type AgeDistributionType =
  | 'FIXED'
  | 'UNIFORM'
  | 'NORMAL'
  | 'TRIANGULAR'
export type ShockApplicationMode =
  | 'FAILURE_RATE'
  | 'FAILURE_PROBABILITY'
  | 'EQUIVALENT_AGE'

export interface ScenarioFieldState<T = unknown> {
  value: T | null
  source: ScenarioFieldSource
  confidence: DecimalString | null
  risk: ScenarioFieldRisk
  confirmed: boolean
  evidence_refs: string[]
}

export interface ScenarioDraftAgeGroup {
  group_code: string
  group_name: string
  distribution_type: AgeDistributionType
  proportion: DecimalString
  fixed_hours?: DecimalString | null
  minimum_hours?: DecimalString | null
  maximum_hours?: DecimalString | null
  mean_hours?: DecimalString | null
  std_hours?: DecimalString | null
  mode_hours?: DecimalString | null
  sort_order?: number
}

export interface ScenarioDraftFleetGroup {
  client_key: string
  group_code: string
  group_name: string
  configuration_version_id: number
  initial_quantity: number
  default_initial_age_hours?: DecimalString | null
  description?: string | null
  age_groups: ScenarioDraftAgeGroup[]
}

export interface ScenarioDraftFleetUsage {
  fleet_group_key: string
  active_quantity: number
  utilization_override?: DecimalString | null
  equipment_intensity_factor?: DecimalString
  environment_factor_override?: DecimalString | null
  is_active?: boolean
  notes?: string | null
}

export interface ScenarioDraftShock {
  shock_code: string
  shock_name: string
  probability: DecimalString
  multiplier: DecimalString
  application_mode: ShockApplicationMode
  fleet_group_key?: string | null
  maximum_occurrences?: number
  notes?: string | null
}

export interface ScenarioDraftStage {
  client_key: string
  stage_code: string
  stage_name: string
  stage_order: number
  duration_hours: DecimalString
  utilization_rate?: DecimalString
  mission_intensity_factor?: DecimalString
  environment_factor?: DecimalString
  temperature_factor?: DecimalString
  dust_factor?: DecimalString
  humidity_factor?: DecimalString
  vibration_factor?: DecimalString
  maintenance_level?: string | null
  description?: string | null
  fleet_usages: ScenarioDraftFleetUsage[]
  shocks: ScenarioDraftShock[]
}

export interface ScenarioDraftFields {
  [key: string]: ScenarioFieldState | undefined
  mission_code?: ScenarioFieldState<string>
  start_at?: ScenarioFieldState<string>
  end_at?: ScenarioFieldState<string>
  priority?: ScenarioFieldState<string>
  equipment_model_id?: ScenarioFieldState<number>
  configuration_version_id?: ScenarioFieldState<number>
  fleet_groups?: ScenarioFieldState<
    ScenarioDraftFleetGroup[]
  >
  stages?: ScenarioFieldState<ScenarioDraftStage[]>
  reliability_profiles?: ScenarioFieldState<
    Array<Record<string, unknown>>
  >
  service_level?: ScenarioFieldState<DecimalString>
  execution_preference?: ScenarioFieldState<
    DemandExecutionMode
  >
  missing_parameter_policy?: ScenarioFieldState<
    MissingParameterPolicy
  >
}

export interface ScenarioDraftPayload {
  scenario_name: string
  current_step: number
  fields: ScenarioDraftFields
}

export interface ScenarioDraftEnvelope {
  session_id: number
  snapshot_id: number
  version: number
  origin: ScenarioDraftOrigin
  draft: ScenarioDraftPayload
  completion: Record<string, boolean>
  blocking_fields: string[]
  updated_at: string
  permissions?: string[]
}

export interface ScenarioDraftCreateRequest {
  title: string
  sensitivity_level?: string
}

export interface ScenarioDraftSaveRequest {
  expected_version: number
  draft: ScenarioDraftPayload
}

export interface ScenarioValidationResult {
  valid: boolean
  issues: Array<Record<string, unknown>>
}

export interface ScenarioMaterializeResult {
  scenario_id: number
  scenario_version_id: number
  status: 'DRAFT'
  validation: ScenarioValidationResult
  replayed: boolean
}

export interface ScenarioVersionSummary {
  id: number
  status: ScenarioVersionStatus
  scenario_template_id?: number
  version_code?: string
  version_name?: string
  default_service_level?: DecimalString
  updated_at?: string
}

export interface ScenarioApiClient {
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

const defaultScenarioClient: ScenarioApiClient = {
  get: maintenanceGet,
  post: maintenancePost,
  put: maintenancePut,
}

function identifier(value: number): string {
  return encodeURIComponent(String(value))
}

export function createScenarioApi(
  client: ScenarioApiClient = defaultScenarioClient,
) {
  return {
    createDraft(
      request: ScenarioDraftCreateRequest,
    ): Promise<MaintenanceResult<ScenarioDraftEnvelope>> {
      return client.post<ScenarioDraftEnvelope>(
        '/v1/demand/scenario-drafts',
        {
          title: request.title,
          sensitivity_level: (
            request.sensitivity_level ?? 'INTERNAL'
          ),
        },
      )
    },

    getDraft(
      sessionId: number,
    ): Promise<MaintenanceResult<ScenarioDraftEnvelope>> {
      return client.get<ScenarioDraftEnvelope>(
        `/v1/demand/scenario-drafts/${identifier(sessionId)}`,
      )
    },

    saveDraft(
      sessionId: number,
      request: ScenarioDraftSaveRequest,
    ): Promise<MaintenanceResult<ScenarioDraftEnvelope>> {
      return client.put<ScenarioDraftEnvelope>(
        `/v1/demand/scenario-drafts/${identifier(sessionId)}`,
        request,
      )
    },

    validateDraft(
      sessionId: number,
    ): Promise<MaintenanceResult<ScenarioDraftEnvelope>> {
      return client.post<ScenarioDraftEnvelope>(
        (
          `/v1/demand/scenario-drafts/`
          + `${identifier(sessionId)}/validate`
        ),
        {},
      )
    },

    materialize(
      sessionId: number,
      expectedVersion: number,
      idempotencyKey: string,
    ): Promise<MaintenanceResult<ScenarioMaterializeResult>> {
      return client.post<ScenarioMaterializeResult>(
        (
          `/v1/demand/scenario-drafts/`
          + `${identifier(sessionId)}/materialize`
        ),
        { expected_version: expectedVersion },
        {
          headers: {
            'Idempotency-Key': idempotencyKey,
          },
        },
      )
    },

    publishVersion(
      versionId: number,
    ): Promise<MaintenanceResult<ScenarioVersionSummary>> {
      return client.post<ScenarioVersionSummary>(
        (
          `/v1/demand/scenario-versions/`
          + `${identifier(versionId)}/publish`
        ),
        {},
      )
    },
  }
}

export const scenarioApi = createScenarioApi()
