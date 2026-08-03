import assert from 'node:assert/strict'
import test from 'node:test'

import type {
  ScenarioDraftPayload,
  ScenarioFieldState,
} from '../../../../api/maintenance/scenarios.ts'
import {
  WIZARD_STEPS,
  evaluateWizard,
} from '../scenario-validation.ts'

function field(
  value: unknown,
): ScenarioFieldState {
  return {
    value,
    source: 'USER_INPUT',
    confidence: null,
    risk: 'LOW',
    confirmed: true,
    evidence_refs: [],
  }
}

const completeDraft: ScenarioDraftPayload = {
  scenario_name: 'Thirty day readiness',
  current_step: 6,
  fields: {
    mission_code: field('MISSION-30D'),
    start_at: field('2026-08-01T00:00:00Z'),
    end_at: field('2026-08-31T00:00:00Z'),
    priority: field('HIGH'),
    equipment_model_id: field(1),
    configuration_version_id: field(2),
    fleet_groups: field([{ client_key: 'fleet-a' }]),
    stages: field([{ client_key: 'stage-a' }]),
    reliability_profiles: field([
      { status: 'confirmed' },
    ]),
    service_level: field('0.95'),
    execution_preference: field('AUTO'),
    missing_parameter_policy: field(
      'WARN_AND_SKIP',
    ),
  },
}

test('wizard exposes the exact six ordered steps', () => {
  assert.deepEqual(
    WIZARD_STEPS.map((step) => step.key),
    [
      'basics',
      'configuration',
      'mission',
      'reliabilityRepair',
      'calculation',
      'confirmation',
    ],
  )
})

test('complete wizard can reach materialization', () => {
  const result = evaluateWizard(completeDraft)

  assert.equal(result.canMaterialize, true)
  assert.deepEqual(result.blockingFields, [])
  assert.equal(result.completion.confirmation, true)
})

test('unconfirmed blocking field prevents materialization', () => {
  const result = evaluateWizard({
    ...completeDraft,
    fields: {
      ...completeDraft.fields,
      service_level: {
        value: '0.95',
        source: 'AI_INFERRED',
        confidence: '0.82',
        risk: 'BLOCKING',
        confirmed: false,
        evidence_refs: [],
      },
    },
  })

  assert.deepEqual(
    result.blockingFields,
    ['service_level'],
  )
  assert.equal(result.canMaterialize, false)
  assert.equal(result.completion.confirmation, false)
})

test('blank and empty required values remain blocking', () => {
  const result = evaluateWizard({
    ...completeDraft,
    scenario_name: '   ',
    fields: {
      ...completeDraft.fields,
      fleet_groups: field([]),
    },
  })

  assert.deepEqual(
    result.blockingFields,
    ['fleet_groups', 'scenario_name'],
  )
  assert.equal(result.completion.basics, false)
  assert.equal(result.completion.configuration, false)
})
