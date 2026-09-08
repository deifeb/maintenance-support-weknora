import assert from 'node:assert/strict'
import test from 'node:test'

import type {
  MaintenancePermissions,
} from '../../../stores/maintenance/permission-matrix.ts'
import * as lifecycle from '../demand-list-lifecycle.ts'

const {
  canEditDemandListItem,
  demandListActions,
} = lifecycle

type CalculationGroupStatus =
  | 'PENDING'
  | 'RUNNING'
  | 'COMPLETED'
  | 'PARTIALLY_COMPLETED'
  | 'FAILED'
  | 'CANCELLED'
  | 'INTERRUPTED'

type GenerationComparison = {
  group_status: CalculationGroupStatus
  rows: Array<{
    decision: Record<string, unknown> | null
    candidates: Record<
      string,
      { status: 'SUCCEEDED' | 'NO_RESULT' }
    >
  }>
}

type GenerationHelper = (
  comparison: GenerationComparison | null,
  permissions: MaintenancePermissions,
) => boolean

function generationHelper(): GenerationHelper {
  return (
    lifecycle as unknown as Record<string, unknown>
  ).canOfferDemandListGeneration as GenerationHelper
}

const viewer: MaintenancePermissions = {
  view: true,
  exportData: true,
  editMasterData: false,
  importMasterData: false,
  runCalculation: false,
  handleReview: false,
  reserveInventory: false,
  issueReturnInventory: false,
  transferInventory: false,
  adjustInventory: false,
  confirmHighRisk: false,
  publishRules: false,
  editDemandList: false,
  publishDemandList: false,
}

const contributor: MaintenancePermissions = {
  ...viewer,
  editDemandList: true,
}

const admin: MaintenancePermissions = {
  ...contributor,
  publishDemandList: true,
}

function eligibleComparison(
  overrides: Partial<GenerationComparison> = {},
): GenerationComparison {
  return {
    group_status: 'COMPLETED',
    rows: [
      {
        decision: { id: 1 },
        candidates: {
          primary: { status: 'SUCCEEDED' },
          alternative: { status: 'NO_RESULT' },
        },
      },
    ],
    ...overrides,
  }
}

test('demand-list actions follow exact status and capabilities', () => {
  assert.deepEqual(
    demandListActions('DRAFT', viewer),
    [],
  )
  assert.deepEqual(
    demandListActions('DRAFT', contributor),
    ['edit', 'submit'],
  )
  assert.deepEqual(
    demandListActions('DRAFT', admin),
    ['edit', 'submit'],
  )
  assert.deepEqual(
    demandListActions('PENDING_CONFIRMATION', contributor),
    [],
  )
  assert.deepEqual(
    demandListActions('PENDING_CONFIRMATION', admin),
    ['confirm'],
  )
  assert.deepEqual(
    demandListActions('CONFIRMED', admin),
    ['publish'],
  )
  assert.deepEqual(
    demandListActions('PUBLISHED', contributor),
    [],
  )
  assert.deepEqual(
    demandListActions('PUBLISHED', admin),
    ['derive', 'void'],
  )
  assert.deepEqual(
    demandListActions('VOIDED', admin),
    [],
  )
})

test('item editing is limited to capable users on DRAFT', () => {
  assert.equal(
    canEditDemandListItem('DRAFT', contributor),
    true,
  )
  assert.equal(
    canEditDemandListItem('DRAFT', admin),
    true,
  )
  assert.equal(
    canEditDemandListItem('DRAFT', viewer),
    false,
  )

  for (const status of [
    'PENDING_CONFIRMATION',
    'CONFIRMED',
    'PUBLISHED',
    'VOIDED',
  ] as const) {
    assert.equal(
      canEditDemandListItem(status, admin),
      false,
    )
  }
})

test('generation requires demand-list edit capability and terminal status', () => {
  const canGenerate = generationHelper()

  assert.equal(
    canGenerate(eligibleComparison(), viewer),
    false,
  )
  assert.equal(
    canGenerate(eligibleComparison(), contributor),
    true,
  )
  assert.equal(
    canGenerate(
      eligibleComparison({ group_status: 'RUNNING' }),
      contributor,
    ),
    false,
  )
  assert.equal(
    canGenerate(
      eligibleComparison({ group_status: 'PENDING' }),
      admin,
    ),
    false,
  )
})

test('generation requires rows, saved decisions, and a successful cell per row', () => {
  const canGenerate = generationHelper()

  assert.equal(
    canGenerate(
      eligibleComparison({ rows: [] }),
      contributor,
    ),
    false,
  )
  assert.equal(
    canGenerate(
      eligibleComparison({
        rows: [
          {
            decision: null,
            candidates: {
              primary: { status: 'SUCCEEDED' },
            },
          },
        ],
      }),
      contributor,
    ),
    false,
  )
  assert.equal(
    canGenerate(
      eligibleComparison({
        rows: [
          {
            decision: { id: 1 },
            candidates: {
              primary: { status: 'NO_RESULT' },
            },
          },
        ],
      }),
      contributor,
    ),
    false,
  )
})

test('generation accepts every terminal group status when row evidence is complete', () => {
  const canGenerate = generationHelper()

  for (const group_status of [
    'COMPLETED',
    'PARTIALLY_COMPLETED',
    'FAILED',
    'CANCELLED',
    'INTERRUPTED',
  ] as const) {
    assert.equal(
      canGenerate(
        eligibleComparison({ group_status }),
        contributor,
      ),
      true,
    )
  }
})
