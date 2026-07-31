import { maintenancePost } from './client'
import type { MaintenanceResult } from './types'

export type ReliabilityModel =
  | 'EXPONENTIAL'
  | 'WEIBULL'
  | 'BINOMIAL'
  | 'NEGATIVE_BINOMIAL'
  | 'EMPIRICAL'

export type CandidateExecutionMode =
  | 'ANALYTICAL'
  | 'MONTE_CARLO'

export type RecommendationRisk =
  | 'LOW'
  | 'MEDIUM'
  | 'HIGH'

export interface CandidateRecommendation {
  candidate_key: string
  reliability_model: ReliabilityModel
  execution_mode: CandidateExecutionMode
  applicable: boolean
  score: number
  reasons: string[]
  missing_requirements: string[]
  parameter_sources: Record<string, string>
  risk: RecommendationRisk
  rule_version: 'MODEL-RECOMMENDATION-1'
}

export interface ModelRecommendationSet {
  scenario_version_id: number
  primary: CandidateRecommendation | null
  items: CandidateRecommendation[]
  rule_version: 'MODEL-RECOMMENDATION-1'
  warnings: Array<Record<string, unknown>>
}

export interface RecommendationApiClient {
  post<T>(
    path: string,
    body: unknown,
    config?: unknown,
  ): Promise<MaintenanceResult<T>>
}

const defaultClient: RecommendationApiClient = {
  post: maintenancePost,
}

export function createRecommendationApi(
  client: RecommendationApiClient = defaultClient,
) {
  return {
    recommend(
      scenarioVersionId: number,
    ): Promise<MaintenanceResult<ModelRecommendationSet>> {
      return client.post<ModelRecommendationSet>(
        '/v1/demand/model-recommendations',
        { scenario_version_id: scenarioVersionId },
      )
    },
  }
}

export const recommendationApi = createRecommendationApi()
