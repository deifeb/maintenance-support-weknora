import { maintenanceGet } from './client'
import type { MaintenanceResult } from './types'

export type DashboardScalar = number | string
export type DashboardRiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'BLOCKING'
export type DashboardTaskType = 'SCENARIO' | 'CALCULATION' | 'REVIEW' | 'REPORT'

export interface DashboardMetric {
  key: string
  value: DashboardScalar
  trend?: DashboardScalar | null
}

export interface RecentTask {
  task_type: DashboardTaskType | string
  task_id: number
  title: string
  status: string
  updated_at: string
  progress?: DashboardScalar | null
  route: string
}

export interface RiskItem {
  key: string
  risk_type: string
  entity_type: string
  entity_id: number
  title: string
  severity: DashboardRiskLevel | string
  value?: DashboardScalar | null
  detail?: string | null
  updated_at: string
  route: string
}

export interface DashboardSummary {
  metrics: DashboardMetric[]
  recent_tasks: RecentTask[]
  risk_items: RiskItem[]
  risk_distribution: Record<DashboardRiskLevel, number>
  generated_at: string
}

export interface DashboardApiClient {
  get<T>(path: string): Promise<MaintenanceResult<T>>
}

const defaultDashboardClient: DashboardApiClient = {
  get: maintenanceGet,
}

export function createDashboardApi(
  client: DashboardApiClient = defaultDashboardClient,
) {
  return {
    getSummary(): Promise<MaintenanceResult<DashboardSummary>> {
      return client.get<DashboardSummary>('/v1/dashboard/summary')
    },
  }
}

const defaultDashboardApi = createDashboardApi()

export function getDashboardSummary(
): Promise<MaintenanceResult<DashboardSummary>> {
  return defaultDashboardApi.getSummary()
}
