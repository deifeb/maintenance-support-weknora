import assert from 'node:assert/strict'
import test from 'node:test'

import {
  MAINTENANCE_CARD_REGISTRY,
  applyMaintenanceCardSnapshot,
  isSafeMaintenanceNavigationPath,
  normalizeMaintenanceCards,
} from './maintenanceCards'

const expectedRegistry = {
  SCENARIO_DRAFT: 'AI_SESSION_SNAPSHOT',
  CALCULATION: 'CALCULATION_GROUP',
  MODEL_COMPARISON: 'CALCULATION_GROUP',
  INVENTORY_GAP: 'ALLOCATION_PLAN',
  REVIEW_FINDING: 'DEMAND_REVIEW_FINDING',
  REPORT: 'AI_REPORT_JOB',
} as const

const sampleCard = (overrides: Record<string, unknown> = {}) => ({
  schema_version: '1.0',
  type: 'CALCULATION',
  title: 'Calculation ready',
  summary: 'Exact-turn calculation snapshot.',
  status: 'completed',
  target: {
    object_type: 'CALCULATION_GROUP',
    object_id: 41,
    observed_version: 7,
    navigation_path: '/platform/maintenance/calculations/41',
  },
  observed_at: '2026-08-30T09:30:00Z',
  payload: {
    scenario: 'baseline',
  },
  ...overrides,
})

test('maintenance card registry covers all six v1 card types with authoritative object types', () => {
  assert.deepEqual(
    Object.fromEntries(
      Object.entries(MAINTENANCE_CARD_REGISTRY).map(([type, entry]) => [
        type,
        entry.objectType,
      ]),
    ),
    expectedRegistry,
  )
})

test('normalizeMaintenanceCards keeps a valid v1 snapshot unchanged', () => {
  const raw = sampleCard()

  const cards = normalizeMaintenanceCards([raw])

  assert.equal(cards.length, 1)
  assert.deepEqual(cards[0], raw)
})

test('normalizeMaintenanceCards fails closed per-card for unknown schema or type', () => {
  const valid = sampleCard()
  const unknownSchema = sampleCard({
    schema_version: '2.0',
    title: 'must be ignored',
  })
  const unknownType = sampleCard({
    type: 'UNSUPPORTED_CARD',
    title: 'must also be ignored',
  })

  const cards = normalizeMaintenanceCards([
    unknownSchema,
    valid,
    unknownType,
  ])

  assert.equal(cards.length, 1)
  assert.deepEqual(cards[0], valid)
})

test('normalizeMaintenanceCards rejects a card whose target object type does not match its registry entry', () => {
  const mismatched = sampleCard({
    target: {
      object_type: 'ALLOCATION_PLAN',
      object_id: 41,
      observed_version: 7,
      navigation_path: '/platform/maintenance/calculations/41',
    },
  })

  assert.deepEqual(normalizeMaintenanceCards([mismatched]), [])
})

test('maintenance navigation accepts only same-origin maintenance paths', () => {
  assert.equal(
    isSafeMaintenanceNavigationPath('/platform/maintenance/calculations/41'),
    true,
  )
  assert.equal(
    isSafeMaintenanceNavigationPath('/platform/maintenance/reports/job-7'),
    true,
  )
  assert.equal(
    isSafeMaintenanceNavigationPath(
      '/platform/maintenance/scenarios/new?session_id=session-17',
    ),
    true,
  )
  assert.equal(
    isSafeMaintenanceNavigationPath(
      '/platform/maintenance/reports?report_id=7',
    ),
    true,
  )

  for (const unsafe of [
    'https://example.com/platform/maintenance/calculations/41',
    '//example.com/platform/maintenance/calculations/41',
    'javascript:alert(1)',
    '/platform/users',
    '/platform/maintenanceevil/calculations/41',
    ' /platform/maintenance/calculations/41',
    '/platform/maintenance/../users',
    '/platform/maintenance\\calculations\\41',
  ]) {
    assert.equal(
      isSafeMaintenanceNavigationPath(unsafe),
      false,
      `unsafe navigation path accepted: ${unsafe}`,
    )
  }
})

test('normalizeMaintenanceCards fails closed when navigation is not safe', () => {
  const cards = normalizeMaintenanceCards([
    sampleCard({
      target: {
        object_type: 'CALCULATION_GROUP',
        object_id: 41,
        observed_version: 7,
        navigation_path: 'https://example.com/steal',
      },
    }),
  ])

  assert.deepEqual(cards, [])
})

test('normalizeMaintenanceCards returns no cards for malformed non-array input', () => {
  assert.deepEqual(normalizeMaintenanceCards(null), [])
  assert.deepEqual(normalizeMaintenanceCards({}), [])
  assert.deepEqual(normalizeMaintenanceCards('not-an-array'), [])
})

test('applyMaintenanceCardSnapshot replaces history cards instead of appending', () => {
  const older = sampleCard({
    target: {
      object_type: 'CALCULATION_GROUP',
      object_id: 41,
      observed_version: 6,
      navigation_path: '/platform/maintenance/calculations/41',
    },
  })
  const terminal = sampleCard({
    target: {
      object_type: 'CALCULATION_GROUP',
      object_id: 41,
      observed_version: 7,
      navigation_path: '/platform/maintenance/calculations/41',
    },
  })
  const message: Record<string, unknown> = {
    maintenance_cards: [older],
  }

  const first = applyMaintenanceCardSnapshot(message, [terminal])

  assert.deepEqual(first, [terminal])
  assert.deepEqual(message.maintenance_cards, [terminal])
  assert.equal((message.maintenance_cards as unknown[]).length, 1)

  const second = applyMaintenanceCardSnapshot(message, [terminal])

  assert.deepEqual(second, [terminal])
  assert.deepEqual(message.maintenance_cards, [terminal])
  assert.equal((message.maintenance_cards as unknown[]).length, 1)
})

test('applyMaintenanceCardSnapshot preserves valid history cards when terminal field is missing or malformed', () => {
  const history = sampleCard()
  const message: Record<string, unknown> = {
    maintenance_cards: [history],
  }

  assert.deepEqual(
    applyMaintenanceCardSnapshot(message, undefined),
    [history],
  )
  assert.deepEqual(message.maintenance_cards, [history])

  assert.deepEqual(
    applyMaintenanceCardSnapshot(message, { not: 'an-array' }),
    [history],
  )
  assert.deepEqual(message.maintenance_cards, [history])
})

test('applyMaintenanceCardSnapshot accepts an authoritative empty terminal snapshot', () => {
  const message: Record<string, unknown> = {
    maintenance_cards: [sampleCard()],
  }

  const cards = applyMaintenanceCardSnapshot(message, [])

  assert.deepEqual(cards, [])
  assert.deepEqual(message.maintenance_cards, [])
})

test('applyMaintenanceCardSnapshot fails closed for invalid cards in an authoritative array', () => {
  const message: Record<string, unknown> = {
    maintenance_cards: [sampleCard()],
  }

  const cards = applyMaintenanceCardSnapshot(message, [
    sampleCard({
      schema_version: '2.0',
    }),
  ])

  assert.deepEqual(cards, [])
  assert.deepEqual(message.maintenance_cards, [])
})
