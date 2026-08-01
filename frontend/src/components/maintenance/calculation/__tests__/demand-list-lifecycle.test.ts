import assert from 'node:assert/strict'
import test from 'node:test'

import type {
  MaintenancePermissions,
} from '../../../stores/maintenance/permission-matrix.ts'
import {
  canEditDemandListItem,
  demandListActions,
} from '../demand-list-lifecycle.ts'

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
