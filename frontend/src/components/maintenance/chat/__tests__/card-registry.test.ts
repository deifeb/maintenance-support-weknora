import assert from 'node:assert/strict'
import test from 'node:test'

import {
  MAINTENANCE_CARD_COMPONENT_LOADERS,
  getMaintenanceCardComponentLoader,
} from '../card-registry'

const expectedTypes = [
  'SCENARIO_DRAFT',
  'CALCULATION',
  'MODEL_COMPARISON',
  'INVENTORY_GAP',
  'REVIEW_FINDING',
  'REPORT',
] as const

test('renderer registry contains all six v1 maintenance card types', () => {
  assert.deepEqual(
    Object.keys(MAINTENANCE_CARD_COMPONENT_LOADERS).sort(),
    [...expectedTypes].sort(),
  )

  for (const type of expectedTypes) {
    assert.equal(
      typeof MAINTENANCE_CARD_COMPONENT_LOADERS[type],
      'function',
      `${type} must map to a Vue component loader`,
    )
  }
})

test('renderer lookup returns the registered loader for every approved type', () => {
  for (const type of expectedTypes) {
    assert.equal(
      getMaintenanceCardComponentLoader(type),
      MAINTENANCE_CARD_COMPONENT_LOADERS[type],
    )
  }
})

test('renderer lookup fails closed for unknown or malformed types', () => {
  assert.equal(getMaintenanceCardComponentLoader('UNKNOWN_CARD'), undefined)
  assert.equal(getMaintenanceCardComponentLoader(''), undefined)
  assert.equal(getMaintenanceCardComponentLoader(null), undefined)
  assert.equal(getMaintenanceCardComponentLoader(undefined), undefined)
  assert.equal(getMaintenanceCardComponentLoader({}), undefined)
})
