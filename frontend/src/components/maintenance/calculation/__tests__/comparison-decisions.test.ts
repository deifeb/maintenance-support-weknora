import assert from 'node:assert/strict'
import test from 'node:test'

import {
  presentCandidateCell,
  validateDecision,
} from '../comparison-decisions.ts'

test('missing candidate result renders NO_RESULT and is not selectable', () => {
  const cell = presentCandidateCell({
    child_id: 8,
    candidate_key: 'BINOMIAL:ANALYTICAL',
    reliability_model: 'BINOMIAL',
    execution_mode: 'ANALYTICAL',
    status: 'NO_RESULT',
    item_status: null,
    recommended_quantity: null,
    expected_demand: null,
    p50: null,
    p95: null,
    p99: null,
    usable_inventory: null,
    net_demand_gap: null,
    shortage_risk_level: null,
    warnings: [],
  })

  assert.equal(cell.label, 'NO_RESULT')
  assert.equal(cell.selectable, false)
})

test('alternative or manual quantity requires a reason', () => {
  assert.equal(validateDecision({
    selectedCandidateKey: 'EXPONENTIAL:ANALYTICAL',
    systemCandidateKey: 'WEIBULL:ANALYTICAL',
    finalQuantity: '12',
    originalQuantity: '14',
    reason: '',
  }).valid, false)
})

test('unchanged system recommendation is valid without a reason', () => {
  assert.deepEqual(validateDecision({
    selectedCandidateKey: 'WEIBULL:ANALYTICAL',
    systemCandidateKey: 'WEIBULL:ANALYTICAL',
    finalQuantity: '14.000000',
    originalQuantity: '14',
    reason: '',
  }), {
    valid: true,
    reasonRequired: false,
    quantityValid: true,
  })
})
