import type {
  CandidateRecommendation,
  ModelRecommendationSet,
} from '../../../api/maintenance/model-recommendations'

export interface CandidateSelectionRow {
  candidateKey: string
  reliabilityModel: string
  executionMode: string
  score: number
  risk: string
  primary: boolean
  disabled: boolean
  reasons: string[]
  missingRequirements: string[]
  parameterSources: Record<string, string>
}

export interface CandidateSelectionValidation {
  valid: boolean
  invalidCandidateKeys: string[]
  missingPrimary: boolean
}

function toRow(
  candidate: CandidateRecommendation,
  primaryKey: string | null,
): CandidateSelectionRow {
  return {
    candidateKey: candidate.candidate_key,
    reliabilityModel: candidate.reliability_model,
    executionMode: candidate.execution_mode,
    score: candidate.score,
    risk: candidate.risk,
    primary: candidate.candidate_key === primaryKey,
    disabled: !candidate.applicable,
    reasons: [...candidate.reasons],
    missingRequirements: [
      ...candidate.missing_requirements,
    ],
    parameterSources: {
      ...candidate.parameter_sources,
    },
  }
}

export function buildCandidateRows(
  recommendation: ModelRecommendationSet,
): CandidateSelectionRow[] {
  const primaryKey = (
    recommendation.primary?.candidate_key ?? null
  )
  return recommendation.items.map(
    (candidate) => toRow(candidate, primaryKey),
  )
}

export function initialCandidateSelection(
  recommendation: ModelRecommendationSet,
): string[] {
  const primary = recommendation.primary
  return primary?.applicable
    ? [primary.candidate_key]
    : []
}

export function validateCandidateSelection(
  recommendation: ModelRecommendationSet,
  selectedCandidateKeys: string[],
): CandidateSelectionValidation {
  const candidates = new Map(
    recommendation.items.map(
      (candidate) => [
        candidate.candidate_key,
        candidate,
      ],
    ),
  )
  const invalidCandidateKeys = (
    selectedCandidateKeys.filter((key) => {
      const candidate = candidates.get(key)
      return candidate === undefined
        || !candidate.applicable
    })
  )
  const primaryKey = (
    recommendation.primary?.candidate_key ?? null
  )
  const missingPrimary = (
    primaryKey === null
    || !selectedCandidateKeys.includes(primaryKey)
  )

  return {
    valid: (
      selectedCandidateKeys.length > 0
      && invalidCandidateKeys.length === 0
      && !missingPrimary
    ),
    invalidCandidateKeys,
    missingPrimary,
  }
}
