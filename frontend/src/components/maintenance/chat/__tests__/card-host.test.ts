import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildMaintenanceCardRenderItems,
} from '../card-host'

const sampleCard = (type: string) => ({
  schema_version: '1.0',
  type,
  title: `${type} title`,
  summary: `${type} summary`,
  status: 'ready',
  target: {
    object_type: type === 'SCENARIO_DRAFT'
      ? 'AI_SESSION_SNAPSHOT'
      : type === 'INVENTORY_GAP'
        ? 'ALLOCATION_PLAN'
        : type === 'REVIEW_FINDING'
          ? 'DEMAND_REVIEW_FINDING'
          : type === 'REPORT'
            ? 'AI_REPORT_JOB'
            : 'CALCULATION_GROUP',
    object_id: 1,
    observed_version: 1,
    navigation_path: '/platform/maintenance/dashboard',
  },
  observed_at: '2026-08-30T10:00:00Z',
  payload: {},
})

test('zero maintenance cards produces zero render items', () => {
  assert.deepEqual(buildMaintenanceCardRenderItems([]), [])
  assert.deepEqual(buildMaintenanceCardRenderItems(undefined), [])
  assert.deepEqual(buildMaintenanceCardRenderItems(null), [])
})

test('approved v1 cards produce one render item each with a loader', () => {
  const types = [
    'SCENARIO_DRAFT',
    'CALCULATION',
    'MODEL_COMPARISON',
    'INVENTORY_GAP',
    'REVIEW_FINDING',
    'REPORT',
  ]

  for (const type of types) {
    const items = buildMaintenanceCardRenderItems([sampleCard(type)])
    assert.equal(items.length, 1, `${type} should render`)
    assert.equal(items[0]?.card.type, type)
    assert.equal(typeof items[0]?.loader, 'function')
  }
})

test('unknown schema or type is ignored instead of producing a fallback card', () => {
  const valid = sampleCard('CALCULATION')
  const unknownType = {
    ...sampleCard('CALCULATION'),
    type: 'UNKNOWN_CARD',
  }
  const unknownSchema = {
    ...sampleCard('CALCULATION'),
    schema_version: '2.0',
  }

  const items = buildMaintenanceCardRenderItems([
    unknownType,
    valid,
    unknownSchema,
  ])

  assert.equal(items.length, 1)
  assert.equal(items[0]?.card.type, 'CALCULATION')
})
