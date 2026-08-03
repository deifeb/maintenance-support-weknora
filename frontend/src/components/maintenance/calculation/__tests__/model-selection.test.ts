import assert from 'node:assert/strict'
import test from 'node:test'

import type {
  ModelRecommendationSet,
} from '../../../../api/maintenance/model-recommendations.ts'
import {
  buildCandidateRows,
  initialCandidateSelection,
  validateCandidateSelection,
} from '../model-selection.ts'

const recommendationFixture: ModelRecommendationSet = {
  scenario_version_id: 17,
  primary: {
    candidate_key: 'EXPONENTIAL:ANALYTICAL',
    reliability_model: 'EXPONENTIAL',
    execution_mode: 'ANALYTICAL',
    applicable: true,
    score: 91,
    reasons: ['Complete failure-rate evidence'],
    missing_requirements: [],
    parameter_sources: {
      FAILURE_RATE: 'MASTER_DATA',
    },
    risk: 'LOW',
    rule_version: 'MODEL-RECOMMENDATION-1',
  },
  items: [
    {
      candidate_key: 'EXPONENTIAL:ANALYTICAL',
      reliability_model: 'EXPONENTIAL',
      execution_mode: 'ANALYTICAL',
      applicable: true,
      score: 91,
      reasons: ['Complete failure-rate evidence'],
      missing_requirements: [],
      parameter_sources: {
        FAILURE_RATE: 'MASTER_DATA',
      },
      risk: 'LOW',
      rule_version: 'MODEL-RECOMMENDATION-1',
    },
    {
      candidate_key: 'WEIBULL:ANALYTICAL',
      reliability_model: 'WEIBULL',
      execution_mode: 'ANALYTICAL',
      applicable: false,
      score: 72,
      reasons: ['Shape parameter is unavailable'],
      missing_requirements: ['WEIBULL_SHAPE'],
      parameter_sources: {},
      risk: 'HIGH',
      rule_version: 'MODEL-RECOMMENDATION-1',
    },
  ],
  rule_version: 'MODEL-RECOMMENDATION-1',
  warnings: [],
}

test('inapplicable candidates are visible but disabled', () => {
  const rows = buildCandidateRows(recommendationFixture)
  const weibull = rows.find(
    (row) => row.candidateKey === 'WEIBULL:ANALYTICAL',
  )

  assert.equal(rows.length, 2)
  assert.equal(weibull?.disabled, true)
  assert.deepEqual(
    weibull?.missingRequirements,
    ['WEIBULL_SHAPE'],
  )
})

test('primary applicable candidate is selected by default', () => {
  assert.deepEqual(
    initialCandidateSelection(recommendationFixture),
    ['EXPONENTIAL:ANALYTICAL'],
  )
})

test('selection requires the primary and rejects inapplicable candidates', () => {
  assert.deepEqual(
    validateCandidateSelection(
      recommendationFixture,
      [
        'EXPONENTIAL:ANALYTICAL',
        'WEIBULL:ANALYTICAL',
      ],
    ),
    {
      valid: false,
      invalidCandidateKeys: ['WEIBULL:ANALYTICAL'],
      missingPrimary: false,
    },
  )
})
